"""Token usage and cost tracking for Phase 2."""

import fcntl
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .runtime import project_runtime_dir

logger = logging.getLogger(__name__)

# Pricing per 1M tokens (USD) - https://www.anthropic.com/pricing
PRICING = {
    # Claude 3.5 models
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet-latest": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-5-haiku-latest": {"input": 0.80, "output": 4.00},
    # Claude 3 models
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    "claude-3-opus-latest": {"input": 15.00, "output": 75.00},
    "claude-3-sonnet-20240229": {"input": 3.00, "output": 15.00},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    # Claude 4 models (when released)
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
}

# Default model for cost estimation when model is unknown
DEFAULT_MODEL = "claude-3-5-sonnet-20241022"


@dataclass
class TokenUsage:
    """Token usage for a single run."""

    input_tokens: int = 0
    output_tokens: int = 0
    model: str = DEFAULT_MODEL

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class UsageTotals:
    """Aggregated usage totals."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0

    def add(self, usage: TokenUsage) -> None:
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.cost += estimate_cost(usage, usage.model)

    def to_dict(self) -> dict:
        return {
            "input": self.input_tokens,
            "output": self.output_tokens,
            "cost": round(self.cost, 4),
        }


def estimate_cost(usage: TokenUsage, model: str | None = None) -> float:
    """Estimate cost from token usage and model pricing."""
    model = model or usage.model or DEFAULT_MODEL
    rates = PRICING.get(model, PRICING[DEFAULT_MODEL])
    return (
        (usage.input_tokens * rates["input"] / 1_000_000)
        + (usage.output_tokens * rates["output"] / 1_000_000)
    )


class CostTracker:
    """Persist and aggregate usage data per project."""

    def __init__(self, project_id: str, base_dir: Path | None = None):
        self.project_dir = project_runtime_dir(project_id, base_dir=base_dir)
        self.usage_file = self.project_dir / "usage.json"

    def record_usage(
        self,
        usage: TokenUsage,
        source: str,
        session_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> bool:
        """Record usage event with file locking for concurrent safety."""
        ts = timestamp or datetime.now()

        try:
            with open(self.usage_file, "a+") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.seek(0)
                    content = f.read()
                    data = json.loads(content) if content.strip() else {"events": []}

                    if session_id:
                        for event in data.get("events", []):
                            if event.get("session_id") == session_id and event.get("source") == source:
                                return False

                    data.setdefault("events", []).append(
                        {
                            "timestamp": ts.isoformat(),
                            "source": source,
                            "session_id": session_id,
                            "model": usage.model,
                            "input_tokens": usage.input_tokens,
                            "output_tokens": usage.output_tokens,
                            "cost": round(estimate_cost(usage, usage.model), 6),
                        }
                    )
                    # Keep recent history reasonably bounded.
                    data["events"] = data["events"][-5000:]

                    f.seek(0)
                    f.truncate()
                    f.write(json.dumps(data, indent=2))
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return True
        except OSError as e:
            logger.warning("Failed to record usage: %s", e)
            return False

    def totals(self, now: datetime | None = None) -> dict:
        """Get totals for all-time, month, and week windows."""
        data = self._load_raw()
        events = data.get("events", [])
        ts = now or datetime.now()
        week_start = ts - timedelta(days=7)
        month_start = ts - timedelta(days=30)

        all_time = UsageTotals()
        this_month = UsageTotals()
        this_week = UsageTotals()

        for event in events:
            usage = TokenUsage(
                input_tokens=int(event.get("input_tokens", 0)),
                output_tokens=int(event.get("output_tokens", 0)),
                model=event.get("model", DEFAULT_MODEL),
            )
            all_time.add(usage)

            event_time = _parse_iso(event.get("timestamp"))
            if event_time is None:
                continue
            if event_time >= month_start:
                this_month.add(usage)
            if event_time >= week_start:
                this_week.add(usage)

        return {
            "all_time": all_time.to_dict(),
            "this_month": this_month.to_dict(),
            "this_week": this_week.to_dict(),
        }

    def _load_raw(self) -> dict:
        if not self.usage_file.exists():
            return {"events": []}
        try:
            with open(self.usage_file) as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    return json.loads(f.read())
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load usage data: %s", e)
            return {"events": []}


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def parse_usage_file(path: Path) -> TokenUsage | None:
    """Parse aggregate token usage from a JSONL output file."""
    if not path.exists():
        return None
    total_in = 0
    total_out = 0
    model = DEFAULT_MODEL
    try:
        with open(path) as handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                usage = entry.get("usage")
                if not isinstance(usage, dict):
                    continue
                total_in += int(usage.get("input_tokens") or usage.get("input") or 0)
                total_out += int(usage.get("output_tokens") or usage.get("output") or 0)
                model = entry.get("model") or usage.get("model") or model
    except OSError as e:
        logger.warning("Failed to parse usage file %s: %s", path, e)
        return None

    if total_in == 0 and total_out == 0:
        return None
    return TokenUsage(input_tokens=total_in, output_tokens=total_out, model=model)
