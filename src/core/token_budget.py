"""Budget configuration and pre-dispatch cost enforcement."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from ..utils import parse_iso
from .cost_tracker import CostTracker, TokenUsage, estimate_cost
from .runtime import project_runtime_dir


@dataclass
class TokenBudget:
    """Budget limits in USD. None means unlimited."""

    monthly_limit_usd: float | None = None
    weekly_limit_usd: float | None = None
    per_session_limit_usd: float | None = None
    gate_budget_usd: float | None = None
    blitz_budget_usd: float | None = None
    dispatch_hard_cap_mode: bool = False

    def to_dict(self) -> dict:
        return {
            "monthly_limit_usd": self.monthly_limit_usd,
            "weekly_limit_usd": self.weekly_limit_usd,
            "per_session_limit_usd": self.per_session_limit_usd,
            "gate_budget_usd": self.gate_budget_usd,
            "blitz_budget_usd": self.blitz_budget_usd,
            "dispatch_hard_cap_mode": self.dispatch_hard_cap_mode,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TokenBudget:
        def _num(name: str) -> float | None:
            value = data.get(name)
            if value in (None, "", 0):
                return None
            try:
                parsed = float(value)
            except (TypeError, ValueError):
                return None
            return parsed if parsed > 0 else None

        return cls(
            monthly_limit_usd=_num("monthly_limit_usd"),
            weekly_limit_usd=_num("weekly_limit_usd"),
            per_session_limit_usd=_num("per_session_limit_usd"),
            gate_budget_usd=_num("gate_budget_usd"),
            blitz_budget_usd=_num("blitz_budget_usd"),
            dispatch_hard_cap_mode=bool(data.get("dispatch_hard_cap_mode", False)),
        )


@dataclass
class BudgetDecision:
    """Budget decision for a potential dispatch."""

    estimated_cost: float
    warn: bool
    exceeded: bool
    blocked: bool
    message: str


class TokenBudgetManager:
    """Manage token budget limits and threshold checks."""

    def __init__(self, project_id: str, base_dir: Path | None = None):
        self.project_id = project_id
        self.project_dir = project_runtime_dir(project_id, base_dir=base_dir)
        self.budget_file = self.project_dir / "token-budget.json"
        self._cost_tracker = CostTracker(project_id, base_dir=base_dir)

    def load_budget(self) -> TokenBudget:
        if not self.budget_file.exists():
            return TokenBudget()
        try:
            data = json.loads(self.budget_file.read_text())
        except (json.JSONDecodeError, OSError):
            return TokenBudget()
        if not isinstance(data, dict):
            return TokenBudget()
        return TokenBudget.from_dict(data)

    def save_budget(self, budget: TokenBudget) -> None:
        self.budget_file.write_text(json.dumps(budget.to_dict(), indent=2))

    def estimate_dispatch_cost(self, prompt: str) -> float:
        """Estimate session cost using prompt size and recent averages."""
        usage_guess = self.estimate_dispatch_usage(prompt)
        heuristic = estimate_cost(usage_guess, usage_guess.model)

        recent = self._recent_average_cost(source="dispatch")
        if recent is not None:
            # Blend prompt heuristic with empirical project history.
            return round(((heuristic * 0.45) + (recent * 0.55)), 4)
        return round(heuristic, 4)

    def estimate_dispatch_usage(self, prompt: str) -> TokenUsage:
        """Estimate token usage for a prompt before dispatch."""
        prompt_tokens = max(120, len(prompt) // 4)
        return TokenUsage(
            input_tokens=prompt_tokens,
            output_tokens=prompt_tokens * 3,
            model="claude-sonnet-4-5",
        )

    def estimate_dispatch_tokens(self, prompt: str) -> int:
        """Estimate total token count for a prompt."""
        return self.estimate_dispatch_usage(prompt).total_tokens

    def remaining_budget_percent(self, estimated_cost: float) -> float | None:
        """Return projected remaining budget percentage after a dispatch.

        The value is based on the most-constrained configured budget among
        weekly, monthly, and per-session limits. Returns None when no limits
        are configured.
        """
        budget = self.load_budget()
        totals = self._cost_tracker.totals()
        weekly_spent = float(totals.get("this_week", {}).get("cost", 0.0))
        monthly_spent = float(totals.get("this_month", {}).get("cost", 0.0))

        remaining_ratios: list[float] = []

        if budget.weekly_limit_usd and budget.weekly_limit_usd > 0:
            ratio = (budget.weekly_limit_usd - (weekly_spent + estimated_cost)) / budget.weekly_limit_usd
            remaining_ratios.append(max(0.0, ratio))

        if budget.monthly_limit_usd and budget.monthly_limit_usd > 0:
            ratio = (budget.monthly_limit_usd - (monthly_spent + estimated_cost)) / budget.monthly_limit_usd
            remaining_ratios.append(max(0.0, ratio))

        if budget.per_session_limit_usd and budget.per_session_limit_usd > 0:
            ratio = (budget.per_session_limit_usd - estimated_cost) / budget.per_session_limit_usd
            remaining_ratios.append(max(0.0, ratio))

        if not remaining_ratios:
            return None

        return round(min(remaining_ratios) * 100, 2)

    def estimate_blitz_range(self, sessions: int, baseline_per_session: float | None = None) -> tuple[float, float]:
        unit = baseline_per_session or self._recent_average_cost(source="dispatch") or 0.35
        low = round(sessions * unit * 0.85, 2)
        high = round(sessions * unit * 1.25, 2)
        return low, high

    def evaluate_dispatch(
        self,
        estimated_cost: float,
        blitz_mode: bool = False,
        hard_cap_mode: bool | None = None,
    ) -> BudgetDecision:
        budget = self.load_budget()
        effective_hard_cap = budget.dispatch_hard_cap_mode if hard_cap_mode is None else hard_cap_mode
        totals = self._cost_tracker.totals()
        weekly_spent = float(totals.get("this_week", {}).get("cost", 0.0))
        monthly_spent = float(totals.get("this_month", {}).get("cost", 0.0))

        checks: list[tuple[str, float, float | None]] = [
            ("weekly", weekly_spent + estimated_cost, budget.weekly_limit_usd),
            ("monthly", monthly_spent + estimated_cost, budget.monthly_limit_usd),
            ("session", estimated_cost, budget.per_session_limit_usd),
        ]

        if blitz_mode:
            blitz_spend = self._sum_cost_for_source(days=30, source="blitz") + estimated_cost
            checks.append(("blitz", blitz_spend, budget.blitz_budget_usd))

        warn = False
        exceeded = False
        messages: list[str] = []

        for label, spent, limit in checks:
            if limit is None or limit <= 0:
                continue
            ratio = spent / limit
            if ratio >= 1.0:
                exceeded = True
                messages.append(f"{label} budget exceeded (${spent:.2f}/${limit:.2f})")
            elif ratio >= 0.8:
                warn = True
                messages.append(f"{label} budget at {int(ratio * 100)}% (${spent:.2f}/${limit:.2f})")

        if exceeded and effective_hard_cap:
            message = "Budget hard cap reached. Dispatch blocked. " + "; ".join(messages)
        elif exceeded:
            message = "Budget limit reached. Continue anyway? " + "; ".join(messages)
        elif warn:
            message = "Budget warning: " + "; ".join(messages)
        else:
            message = f"Estimated cost: ${estimated_cost:.2f}"

        return BudgetDecision(
            estimated_cost=round(estimated_cost, 4),
            warn=warn,
            exceeded=exceeded,
            blocked=bool(exceeded and effective_hard_cap),
            message=message,
        )

    def status(self) -> dict:
        budget = self.load_budget()
        totals = self._cost_tracker.totals()
        weekly_cost = float(totals.get("this_week", {}).get("cost", 0.0))
        monthly_cost = float(totals.get("this_month", {}).get("cost", 0.0))

        return {
            "weekly": _status_row(weekly_cost, budget.weekly_limit_usd),
            "monthly": _status_row(monthly_cost, budget.monthly_limit_usd),
            "gate": _status_row(self._sum_cost_for_source(days=30, source="gate"), budget.gate_budget_usd),
            "blitz": _status_row(self._sum_cost_for_source(days=30, source="blitz"), budget.blitz_budget_usd),
            "per_session_limit": budget.per_session_limit_usd,
            "budget": budget.to_dict(),
        }

    def _recent_average_cost(self, source: str) -> float | None:
        events = self._events()
        values = [float(event.get("cost", 0.0)) for event in events if event.get("source") == source]
        values = [value for value in values if value > 0]
        if not values:
            return None
        recent = values[-20:]
        return sum(recent) / len(recent)

    def _sum_cost_for_source(self, days: int, source: str) -> float:
        start = datetime.now() - timedelta(days=days)
        total = 0.0
        for event in self._events():
            if event.get("source") != source:
                continue
            timestamp = parse_iso(event.get("timestamp"))
            if timestamp and timestamp >= start:
                total += float(event.get("cost", 0.0))
        return round(total, 6)

    def _events(self) -> list[dict]:
        if not self._cost_tracker.usage_file.exists():
            return []
        try:
            payload = json.loads(self._cost_tracker.usage_file.read_text())
        except (json.JSONDecodeError, OSError):
            return []
        events = payload.get("events", []) if isinstance(payload, dict) else []
        return events if isinstance(events, list) else []


def _status_row(spent: float, limit: float | None) -> dict:
    if limit is None:
        return {
            "spent": round(spent, 4),
            "limit": None,
            "ratio": 0.0,
            "warn": False,
            "exceeded": False,
            "remaining": None,
        }
    ratio = (spent / limit) if limit > 0 else 0.0
    return {
        "spent": round(spent, 4),
        "limit": round(limit, 4),
        "ratio": round(ratio, 4),
        "warn": ratio >= 0.8,
        "exceeded": ratio >= 1.0,
        "remaining": round(max(0.0, limit - spent), 4),
    }
