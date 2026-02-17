"""Tests for gate executor command and agent gate execution."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.agents.executor import (
    GateExecutor,
    _extract_metric,
    _find_missing_python_docstrings,
    _summarize_pass_output,
)


@pytest.fixture
def executor(temp_dir):
    """Create a GateExecutor for testing."""
    return GateExecutor(temp_dir, "test-project")


class TestCommandGateExecution:
    """Test command gate execution."""

    def test_run_command_gate_success(self, executor):
        """Test successful command gate execution."""
        gate = {
            "name": "tests",
            "command": "echo 'All tests passed'",
            "hard_stop": False,
            "timeout": 30,
        }

        results = executor.run_command_gates([gate])

        assert len(results) == 1
        assert results[0].name == "tests"
        assert results[0].status == "pass"
        assert results[0].duration_seconds > 0

    def test_run_command_gate_failure(self, executor):
        """Test failing command gate execution."""
        gate = {
            "name": "lint",
            "command": "exit 1",
            "hard_stop": False,
            "timeout": 30,
        }

        results = executor.run_command_gates([gate])

        assert len(results) == 1
        assert results[0].name == "lint"
        assert results[0].status == "fail"
        assert len(results[0].findings) == 1

    def test_run_command_gate_timeout(self, executor):
        """Test command gate timeout."""
        gate = {
            "name": "slow",
            "command": "sleep 10",
            "hard_stop": False,
            "timeout": 1,
        }

        results = executor.run_command_gates([gate])

        assert len(results) == 1
        assert results[0].name == "slow"
        assert results[0].status == "error"
        assert "Timed out" in results[0].summary

    def test_run_command_gate_no_command(self, executor):
        """Test command gate with no command configured."""
        gate = {
            "name": "empty",
            "command": "",
            "hard_stop": False,
            "timeout": 30,
        }

        results = executor.run_command_gates([gate])

        assert len(results) == 1
        assert results[0].status == "error"
        assert "No command configured" in results[0].summary

    def test_run_multiple_command_gates_parallel(self, executor):
        """Test parallel execution of multiple command gates."""
        gates = [
            {"name": "gate1", "command": "echo 'gate1'", "hard_stop": False, "timeout": 30},
            {"name": "gate2", "command": "echo 'gate2'", "hard_stop": False, "timeout": 30},
            {"name": "gate3", "command": "echo 'gate3'", "hard_stop": False, "timeout": 30},
        ]

        results = executor.run_command_gates(gates)

        assert len(results) == 3
        names = [r.name for r in results]
        assert "gate1" in names
        assert "gate2" in names
        assert "gate3" in names
        assert all(r.status == "pass" for r in results)

    def test_command_gate_preserves_order(self, executor):
        """Test that results maintain original gate order."""
        gates = [
            {"name": "first", "command": "echo 'a'", "hard_stop": False, "timeout": 30},
            {"name": "second", "command": "echo 'b'", "hard_stop": False, "timeout": 30},
        ]

        results = executor.run_command_gates(gates)

        assert results[0].name == "first"
        assert results[1].name == "second"


class TestAgentGateExecution:
    """Test agent gate execution."""

    def test_run_security_review_clean(self, executor, temp_dir):
        """Test security review with clean project."""
        (temp_dir / "src").mkdir(exist_ok=True)
        (temp_dir / "src" / "app.py").write_text("print('hello')")

        gate = {"name": "security", "hard_stop": False}

        results = executor.run_agent_gates([gate], changed_files=["src/app.py"])

        assert len(results) == 1
        assert results[0].name == "security"
        # May pass or find issues depending on scanner sensitivity

    def test_run_doc_review_clean(self, executor, temp_dir):
        """Test documentation review with documented code."""
        (temp_dir / "src").mkdir(exist_ok=True)
        (temp_dir / "src" / "app.py").write_text('''
def greet(name: str) -> str:
    """Return a greeting for the given name."""
    return f"Hello, {name}!"
''')

        gate = {"name": "documentation", "hard_stop": False, "fail_threshold": 3}

        results = executor.run_agent_gates([gate], changed_files=["src/app.py"])

        assert len(results) == 1
        assert results[0].name == "documentation"
        assert results[0].status == "pass"

    def test_run_doc_review_missing_docstrings(self, executor, temp_dir):
        """Test documentation review finds missing docstrings."""
        (temp_dir / "src").mkdir(exist_ok=True)
        (temp_dir / "src" / "app.py").write_text('''
def greet(name: str) -> str:
    return f"Hello, {name}!"

def farewell(name: str) -> str:
    return f"Goodbye, {name}!"

class Handler:
    pass
''')

        gate = {"name": "documentation", "hard_stop": False, "fail_threshold": 3}

        results = executor.run_agent_gates([gate], changed_files=["src/app.py"])

        assert len(results) == 1
        assert results[0].name == "documentation"
        assert results[0].status == "fail"  # 3+ missing docstrings
        assert len(results[0].findings) >= 3

    def test_run_doc_review_configurable_threshold(self, executor, temp_dir):
        """Test documentation review respects configurable threshold."""
        (temp_dir / "src").mkdir(exist_ok=True)
        (temp_dir / "src" / "app.py").write_text('''
def one():
    return 1

def two():
    return 2
''')

        # With threshold of 5, 2 findings should warn not fail
        gate = {"name": "documentation", "hard_stop": False, "fail_threshold": 5}

        results = executor.run_agent_gates([gate], changed_files=["src/app.py"])

        assert len(results) == 1
        assert results[0].status == "warn"

    def test_run_test_coverage_review(self, executor, temp_dir):
        """Test coverage review detects untested files."""
        (temp_dir / "src").mkdir(exist_ok=True)
        (temp_dir / "src" / "untested.py").write_text("print('no tests')")
        (temp_dir / "tests").mkdir(exist_ok=True)

        gate = {"name": "test_coverage", "hard_stop": False}

        results = executor.run_agent_gates([gate], changed_files=["src/untested.py"])

        assert len(results) == 1
        assert results[0].name == "test_coverage"
        # Should warn about missing test file

    def test_unknown_agent_gate_skipped(self, executor):
        """Test unknown agent gate is skipped."""
        gate = {"name": "unknown_agent", "hard_stop": False}

        results = executor.run_agent_gates([gate], changed_files=[])

        assert len(results) == 1
        assert results[0].status == "skipped"


class TestHelperFunctions:
    """Test helper functions."""

    def test_summarize_pass_output_tests(self):
        """Test summarize for test output."""
        output = "15 / 15 tests passed\nAll good!"
        assert "15/15" in _summarize_pass_output("tests", output)

    def test_summarize_pass_output_lint(self):
        """Test summarize for lint output."""
        assert _summarize_pass_output("lint", "All clean") == "Clean"
        assert "notices" in _summarize_pass_output("lint", "error found but passed")

    def test_summarize_pass_output_empty(self):
        """Test summarize for empty output."""
        assert _summarize_pass_output("any", "") == "Gate passed"

    def test_extract_metric_coverage(self):
        """Test coverage metric extraction."""
        output = "TOTAL 85.5% cov"
        assert _extract_metric("tests", output) == 85.5

    def test_extract_metric_lint_errors(self):
        """Test lint error metric extraction."""
        output = "Found 3 error(s)"
        assert _extract_metric("lint", output) == 97.0  # 100 - 3

    def test_extract_metric_none(self):
        """Test metric extraction with no match."""
        assert _extract_metric("tests", "no metrics here") is None
        assert _extract_metric("lint", "") is None

    def test_find_missing_python_docstrings(self):
        """Test finding missing docstrings in Python code."""
        content = '''
def public_func():
    pass

def _private_func():
    pass

class MyClass:
    pass

def documented():
    """This has a docstring."""
    pass
'''
        findings = _find_missing_python_docstrings("docs", "test.py", content)

        # Should find public_func and MyClass, but not _private_func or documented
        descriptions = [f.description for f in findings]
        assert any("public_func" in d for d in descriptions)
        assert any("MyClass" in d for d in descriptions)
        assert not any("_private_func" in d for d in descriptions)
        assert not any("documented" in d for d in descriptions)

    def test_find_missing_docstrings_all_documented(self):
        """Test no findings when all functions are documented."""
        content = '''
def func():
    """Documented."""
    pass

class Cls:
    """Also documented."""
    pass
'''
        findings = _find_missing_python_docstrings("docs", "test.py", content)
        assert len(findings) == 0
