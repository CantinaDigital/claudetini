"""Tests for fallback helper logic in sidecar dispatch routes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

SIDE_CAR_ROOT = Path(__file__).resolve().parents[1] / "app" / "python-sidecar"
if str(SIDE_CAR_ROOT) not in sys.path:
    sys.path.insert(0, str(SIDE_CAR_ROOT))

from sidecar.api.routes import dispatch as dispatch_routes  # noqa: E402


class _FakeGateResult:
    """Mock gate result for testing fallback dispatch logic."""

    def __init__(self, status: str):
        self.status = status


class _FakeGateReport:
    """Mock gate report for testing fallback dispatch logic."""

    def __init__(self, status: str):
        self.results = [_FakeGateResult(status)]


class _FakeGateRunner:
    """Mock quality gate runner for testing fallback dispatch."""

    def __init__(self, _project_path: Path):
        self.gates = {
            "lint": object(),
            "typecheck": object(),
            "documentation": object(),
        }

    def load_config(self) -> dict[str, object]:
        """Load mock gate configuration."""
        return self.gates

    def run_gate(self, gate_name: str, session_id: str | None = None) -> _FakeGateReport:
        """Run a single gate and return mock results."""
        _ = session_id
        if gate_name == "documentation":
            return _FakeGateReport("fail")
        return _FakeGateReport("pass")


def test_extract_requested_gate_names_from_prompt() -> None:
    """Test parsing gate names from quality issue prompts."""
    prompt = (
        "Fix the following quality issue:\n"
        "Issue: 3 failed gate(s): lint, typecheck, documentation\n"
        "Suggestion: Address this immediately"
    )
    parsed = dispatch_routes._extract_requested_gate_names(prompt)
    assert parsed == ["lint", "typecheck", "documentation"]


def test_classify_fallback_failure_needs_user_input() -> None:
    """Test detecting when fallback provider needs user confirmation."""
    error = "Please confirm whether you want me to proceed with these edits."
    code = dispatch_routes._classify_fallback_failure("codex", error=error, output=None)
    assert code == "needs_user_input"


def test_verify_fallback_gates_detects_success_without_fix(monkeypatch, temp_dir) -> None:
    """Test that gate verification detects when gates pass without code changes."""
    monkeypatch.setattr(dispatch_routes, "QualityGateRunner", _FakeGateRunner)

    ok, statuses, message = dispatch_routes._verify_fallback_gates(
        project_path=temp_dir,
        prompt="Issue: 3 failed gate(s): lint, typecheck, documentation",
    )

    assert ok is False
    assert statuses["documentation"] == "fail"
    assert message is not None
    assert "documentation=fail" in message


def test_build_fallback_error_detail_includes_code_and_verification() -> None:
    """Test that error details include both error code and verification results."""
    response = dispatch_routes.DispatchResponse(
        success=False,
        error="Post-run gate verification failed.",
        error_code="verification_failed",
        verification={"lint": "pass", "typecheck": "pass", "documentation": "fail"},
        provider="codex",
    )
    detail = dispatch_routes._build_fallback_error_detail(response, output="line1\nline2", output_file=None)
    assert detail is not None
    assert "Error code: verification_failed" in detail
    assert "documentation=fail" in detail
    assert "CLI output tail" in detail
