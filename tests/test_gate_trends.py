"""Tests for gate trend computation."""

from datetime import datetime

from src.core.gate_results import GateResultStore, GateRunReport, StoredGateResult
from src.core.gate_trends import GateTrendStore, render_sparkline


def test_gate_trends_compute_and_render(temp_dir):
    project_id = "proj123"
    store = GateResultStore(project_id, base_dir=temp_dir)
    store.save_report(
        GateRunReport(
            run_id="run-1",
            timestamp=datetime(2026, 2, 12, 10, 0, 0),
            gates=[StoredGateResult(name="tests", status="fail", summary="fail", metric=20.0)],
        )
    )
    store.save_report(
        GateRunReport(
            run_id="run-2",
            timestamp=datetime(2026, 2, 12, 11, 0, 0),
            gates=[StoredGateResult(name="tests", status="pass", summary="pass", metric=90.0)],
        )
    )

    trends = GateTrendStore(project_id, base_dir=temp_dir).compute(limit=10)
    assert "tests" in trends
    assert len(trends["tests"].results) == 2

    spark = GateTrendStore(project_id, base_dir=temp_dir).sparkline_for("tests", limit=10)
    assert len(spark) == 2
    assert spark != "-"


def test_render_sparkline_flat():
    assert render_sparkline([1.0, 1.0, 1.0]) == "███"
