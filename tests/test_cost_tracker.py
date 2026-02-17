"""Tests for cost tracking."""

from datetime import datetime, timedelta

from src.core.cost_tracker import CostTracker, TokenUsage, estimate_cost


def test_estimate_cost_default_model():
    usage = TokenUsage(input_tokens=1000, output_tokens=2000, model="unknown")
    cost = estimate_cost(usage, usage.model)
    assert cost > 0


def test_cost_tracker_totals(temp_dir):
    tracker = CostTracker("proj-1", base_dir=temp_dir)
    now = datetime.now()
    tracker.record_usage(
        TokenUsage(input_tokens=1000, output_tokens=1000),
        source="dispatch",
        timestamp=now,
    )
    tracker.record_usage(
        TokenUsage(input_tokens=500, output_tokens=500),
        source="dispatch",
        timestamp=now - timedelta(days=40),
    )

    totals = tracker.totals(now=now)
    assert totals["all_time"]["input"] == 1500
    assert totals["all_time"]["output"] == 1500
    assert totals["this_week"]["input"] == 1000
    assert totals["this_month"]["input"] == 1000

