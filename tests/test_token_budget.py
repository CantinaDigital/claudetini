"""Tests for token budget enforcement."""

from datetime import datetime

from src.core.cost_tracker import CostTracker, TokenUsage
from src.core.token_budget import TokenBudget, TokenBudgetManager


def test_budget_warning_and_status(temp_dir):
    project_id = "proj123"
    manager = TokenBudgetManager(project_id, base_dir=temp_dir)
    manager.save_budget(
        TokenBudget(
            weekly_limit_usd=1.0,
            monthly_limit_usd=5.0,
            per_session_limit_usd=0.5,
            gate_budget_usd=0.4,
            blitz_budget_usd=2.0,
        )
    )

    tracker = CostTracker(project_id, base_dir=temp_dir)
    tracker.record_usage(
        TokenUsage(input_tokens=80_000, output_tokens=20_000, model="claude-sonnet-4-5"),
        source="dispatch",
        session_id="s1",
        timestamp=datetime.now(),
    )

    estimate = manager.estimate_dispatch_cost("Implement API endpoint and tests")
    decision = manager.evaluate_dispatch(estimated_cost=estimate)

    assert estimate > 0
    assert decision.warn or decision.exceeded

    status = manager.status()
    assert status["weekly"]["limit"] == 1.0
    assert "spent" in status["monthly"]


def test_estimate_dispatch_tokens_uses_prompt_heuristic(temp_dir):
    manager = TokenBudgetManager("proj-tokens", base_dir=temp_dir)
    estimated = manager.estimate_dispatch_tokens("Short prompt")
    assert estimated >= 480


def test_remaining_budget_percent_uses_most_constrained_limit(temp_dir):
    manager = TokenBudgetManager("proj-remaining", base_dir=temp_dir)
    manager.save_budget(
        TokenBudget(
            weekly_limit_usd=1.0,
            monthly_limit_usd=2.0,
            per_session_limit_usd=0.5,
        )
    )

    remaining = manager.remaining_budget_percent(estimated_cost=0.2)
    assert remaining == 60.0

    exhausted = manager.remaining_budget_percent(estimated_cost=0.6)
    assert exhausted == 0.0
