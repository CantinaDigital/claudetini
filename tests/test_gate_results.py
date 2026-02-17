"""Tests for gate result storage and failure todo lifecycle."""

from datetime import datetime

from src.core.gate_results import (
    GateFinding,
    GateResultStore,
    GateRunReport,
    StoredGateResult,
)


def test_gate_result_store_persists_and_resolves_failure_todos(temp_dir):
    store = GateResultStore("proj123", base_dir=temp_dir)

    fail_report = GateRunReport(
        run_id="run-1",
        timestamp=datetime(2026, 2, 12, 10, 0, 0),
        session_id="session-1",
        trigger="on_session_end",
        gates=[
            StoredGateResult(
                name="documentation",
                status="fail",
                summary="Missing docstrings",
                hard_stop=False,
                findings=[
                    GateFinding(
                        source_gate="documentation",
                        severity="medium",
                        description="Missing docstring for public function",
                        file="src/app.py",
                        line=12,
                    )
                ],
            )
        ],
    )

    store.save_report(fail_report)

    latest = store.load_latest()
    assert latest is not None
    assert latest.run_id == "run-1"
    open_todos = store.open_failure_todos()
    assert len(open_todos) == 1
    assert open_todos[0].source_gate == "documentation"

    pass_report = GateRunReport(
        run_id="run-2",
        timestamp=datetime(2026, 2, 12, 11, 0, 0),
        session_id="session-1",
        trigger="on_session_end",
        gates=[
            StoredGateResult(
                name="documentation",
                status="pass",
                summary="Documentation clean",
                hard_stop=False,
            )
        ],
    )
    store.save_report(pass_report)

    assert store.open_failure_todos() == []
