"""Tests for QualityGateRunner orchestration."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.agents.gates import (
    GateConfig,
    GateReport,
    GateResult,
    LegacyGateResult,
    QualityGateRunner,
)


@pytest.fixture
def runner(temp_dir):
    """Create a QualityGateRunner for testing."""
    # Create minimal git structure
    git_dir = temp_dir / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir()

    return QualityGateRunner(temp_dir, project_id="test-proj")


class TestGateConfig:
    """Test GateConfig dataclass."""

    def test_gate_config_defaults(self):
        """Test GateConfig default values."""
        config = GateConfig(name="test", gate_type="command")

        assert config.enabled is True
        assert config.hard_stop is False
        assert config.timeout == 300
        assert config.fail_threshold == 3

    def test_gate_config_to_dict(self):
        """Test GateConfig serialization."""
        config = GateConfig(
            name="tests",
            gate_type="command",
            enabled=True,
            hard_stop=True,
            command="pytest",
            timeout=120,
            fail_threshold=5,
        )

        data = config.to_dict()

        assert data["enabled"] is True
        assert data["hard_stop"] is True
        assert data["command"] == "pytest"
        assert data["timeout"] == 120
        assert data["fail_threshold"] == 5


class TestGateReport:
    """Test GateReport dataclass."""

    def test_all_passed_true(self):
        """Test all_passed when all gates pass."""
        report = GateReport(
            results=[
                GateResult(name="a", status="pass", message="ok"),
                GateResult(name="b", status="pass", message="ok"),
                GateResult(name="c", status="skipped", message="disabled"),
            ]
        )

        assert report.all_passed is True

    def test_all_passed_false(self):
        """Test all_passed when some gates fail."""
        report = GateReport(
            results=[
                GateResult(name="a", status="pass", message="ok"),
                GateResult(name="b", status="fail", message="error"),
            ]
        )

        assert report.all_passed is False

    def test_has_failures(self):
        """Test has_failures property."""
        report = GateReport(
            results=[
                GateResult(name="a", status="warn", message="warning"),
                GateResult(name="b", status="fail", message="error"),
            ]
        )

        assert report.has_failures is True

    def test_hard_stop_failures(self):
        """Test hard_stop_failures filtering."""
        report = GateReport(
            results=[
                GateResult(name="a", status="fail", message="err", hard_stop=True),
                GateResult(name="b", status="fail", message="err", hard_stop=False),
                GateResult(name="c", status="pass", message="ok", hard_stop=True),
            ]
        )

        hard_stops = report.hard_stop_failures
        assert len(hard_stops) == 1
        assert hard_stops[0].name == "a"


class TestLegacyGateResult:
    """Test LegacyGateResult dataclass."""

    def test_legacy_result_creation(self):
        """Test LegacyGateResult can be created with expected fields."""
        result = LegacyGateResult(
            passed=True,
            partial=False,
            summary="All tests passed",
            finding=None,
            metric=100.0,
            cost_estimate=0.05,
        )

        assert result.passed is True
        assert result.partial is False
        assert result.summary == "All tests passed"
        assert result.metric == 100.0


class TestQualityGateRunnerConfig:
    """Test QualityGateRunner configuration handling."""

    def test_load_config_creates_default(self, runner):
        """Test default config is created if none exists."""
        gates = runner.load_config()

        assert "secrets" in gates
        assert "tests" in gates
        assert "lint" in gates
        assert gates["secrets"].hard_stop is True

    def test_load_config_preserves_existing(self, runner, temp_dir):
        """Test existing config is loaded correctly."""
        config_data = {
            "gates": {
                "tests": {
                    "enabled": False,
                    "type": "command",
                    "hard_stop": True,
                    "command": "make test",
                    "fail_threshold": 5,
                }
            }
        }
        runner.config_path.write_text(json.dumps(config_data))

        gates = runner.load_config()

        assert gates["tests"].enabled is False
        assert gates["tests"].hard_stop is True
        assert gates["tests"].command == "make test"
        assert gates["tests"].fail_threshold == 5

    def test_save_config(self, runner):
        """Test config is saved correctly."""
        runner.load_config()
        runner.gates["tests"].enabled = False
        runner.save_config()

        loaded = json.loads(runner.config_path.read_text())
        assert loaded["gates"]["tests"]["enabled"] is False

    def test_load_config_handles_corrupt_json(self, runner):
        """Test corrupt config falls back to defaults."""
        runner.config_path.write_text("not valid json {{{")

        gates = runner.load_config()

        # Should get defaults
        assert "secrets" in gates
        assert "tests" in gates


class TestQualityGateRunnerAutoDetect:
    """Test command auto-detection."""

    def test_auto_detect_python_project(self, temp_dir):
        """Test auto-detection for Python project."""
        # Create minimal git structure
        git_dir = temp_dir / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
        (git_dir / "hooks").mkdir()

        pyproject = temp_dir / "pyproject.toml"
        pyproject.write_text("""
[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100

[tool.mypy]
strict = true
""")

        # Create fresh runner for this specific temp_dir
        runner = QualityGateRunner(temp_dir, project_id="test-py-proj")
        gates = runner.load_config()

        assert "pytest" in (gates["tests"].command or "")
        assert "ruff" in (gates["lint"].command or "")
        assert "mypy" in (gates["typecheck"].command or "")

    def test_auto_detect_node_project(self, temp_dir):
        """Test auto-detection for Node.js project."""
        # Create minimal git structure
        git_dir = temp_dir / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
        (git_dir / "hooks").mkdir()

        package_json = temp_dir / "package.json"
        package_json.write_text(json.dumps({
            "scripts": {
                "test": "vitest run",
                "lint": "eslint .",
            }
        }))

        runner = QualityGateRunner(temp_dir, project_id="test-node-proj")
        gates = runner.load_config()

        assert "vitest" in (gates["tests"].command or "")
        assert "npm run lint" in (gates["lint"].command or "")

    def test_auto_detect_rust_project(self, temp_dir):
        """Test auto-detection for Rust project."""
        git_dir = temp_dir / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
        (git_dir / "hooks").mkdir()

        cargo = temp_dir / "Cargo.toml"
        cargo.write_text('[package]\nname = "test"')

        runner = QualityGateRunner(temp_dir, project_id="test-rust-proj")
        gates = runner.load_config()

        assert "cargo test" in (gates["tests"].command or "")
        assert "cargo clippy" in (gates["lint"].command or "")

    def test_auto_detect_go_project(self, temp_dir):
        """Test auto-detection for Go project."""
        git_dir = temp_dir / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
        (git_dir / "hooks").mkdir()

        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module example.com/test")

        runner = QualityGateRunner(temp_dir, project_id="test-go-proj")
        gates = runner.load_config()

        assert "go test" in (gates["tests"].command or "")
        assert "golangci-lint" in (gates["lint"].command or "")


class TestQualityGateRunnerExecution:
    """Test gate execution."""

    def test_run_all_gates_basic(self, runner, temp_dir):
        """Test basic gate execution."""
        # Create a simple Python file
        (temp_dir / "src").mkdir(exist_ok=True)
        (temp_dir / "src" / "app.py").write_text('"""Module."""\nprint("hello")')

        runner.load_config()
        # Disable slow gates for test
        runner.gates["tests"].enabled = False
        runner.gates["lint"].enabled = False
        runner.gates["typecheck"].enabled = False
        runner.gates["security"].enabled = False
        runner.gates["documentation"].enabled = False
        runner.gates["test_coverage"].enabled = False

        report = runner.run_all_gates(staged_only=False)

        assert isinstance(report, GateReport)
        assert report.run_id.startswith("gate-")
        # Secrets gate always runs
        assert any(r.name == "secrets" for r in report.results)

    def test_run_all_returns_legacy_format(self, runner, temp_dir):
        """Test run_all returns legacy format."""
        runner.load_config()
        # Disable slow gates
        for gate in runner.gates.values():
            if gate.name != "secrets":
                gate.enabled = False

        results = runner.run_all(staged_only=False)

        assert isinstance(results, dict)
        assert "secrets" in results
        assert isinstance(results["secrets"], LegacyGateResult)

    def test_run_gate_single(self, runner, temp_dir):
        """Test running a single gate."""
        runner.load_config()

        report = runner.run_gate("secrets")

        assert len(report.results) == 1
        assert report.results[0].name == "secrets"

    def test_run_gate_unknown_raises(self, runner):
        """Test running unknown gate raises error."""
        runner.load_config()

        with pytest.raises(ValueError, match="Unknown gate"):
            runner.run_gate("nonexistent")


class TestQualityGateRunnerHooks:
    """Test pre-push hook management."""

    def test_install_pre_push_hook(self, runner, temp_dir):
        """Test installing pre-push hook."""
        ok, message = runner.install_pre_push_hook()

        assert ok is True
        assert "Installed" in message

        hook_file = temp_dir / ".git" / "hooks" / "pre-push"
        assert hook_file.exists()
        content = hook_file.read_text()
        assert "claudetini pre-push" in content

    def test_pre_push_hook_installed_check(self, runner):
        """Test checking if hook is installed."""
        assert runner.pre_push_hook_installed() is False

        runner.install_pre_push_hook()

        assert runner.pre_push_hook_installed() is True

    def test_remove_pre_push_hook(self, runner, temp_dir):
        """Test removing pre-push hook."""
        runner.install_pre_push_hook()
        assert runner.pre_push_hook_installed() is True

        ok, message = runner.remove_pre_push_hook()

        assert ok is True
        assert runner.pre_push_hook_installed() is False


class TestQualityGateRunnerTrends:
    """Test trend computation."""

    def test_trends_empty_initially(self, runner):
        """Test trends are empty with no history."""
        trends = runner.trends(limit=10)

        assert isinstance(trends, dict)

    def test_trends_after_runs(self, runner, temp_dir):
        """Test trends populate after gate runs."""
        runner.load_config()
        # Disable everything except secrets
        for gate in runner.gates.values():
            if gate.name != "secrets":
                gate.enabled = False

        # Run gates twice
        runner.run_all_gates(staged_only=False)
        runner.run_all_gates(staged_only=False)

        trends = runner.trends(limit=10)

        assert "secrets" in trends
        assert len(trends["secrets"]) >= 1  # Sparkline characters


class TestQualityGateRunnerLatestReport:
    """Test latest report retrieval."""

    def test_latest_report_none_initially(self, temp_dir):
        """Test no latest report initially with fresh project."""
        # Create minimal git structure
        git_dir = temp_dir / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
        (git_dir / "hooks").mkdir()

        # Use unique project_id to ensure no leftover data
        fresh_runner = QualityGateRunner(temp_dir, project_id="fresh-proj-for-latest")
        report = fresh_runner.latest_report()

        assert report is None

    def test_latest_report_after_run(self, runner):
        """Test latest report after gate run."""
        runner.load_config()
        for gate in runner.gates.values():
            if gate.name != "secrets":
                gate.enabled = False

        runner.run_all_gates(staged_only=False)

        report = runner.latest_report()

        assert report is not None
        assert isinstance(report, GateReport)
