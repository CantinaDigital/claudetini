"""Tests for preflight checks."""

import subprocess

from src.core.preflight import PreflightChecker


def _init_repo(path):
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-B", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("# Repo\n")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def test_preflight_warns_uncommitted(temp_dir):
    _init_repo(temp_dir)
    (temp_dir / "README.md").write_text("# changed\n")
    result = PreflightChecker(temp_dir).run()
    assert result.has_warnings is True


def test_preflight_respects_disabled_checks(temp_dir):
    _init_repo(temp_dir)
    (temp_dir / "README.md").write_text("# changed\n")
    checker = PreflightChecker(
        temp_dir,
        enabled_checks={
            "uncommitted_changes": False,
            "behind_remote": False,
            "stale_dependencies": False,
            "disk_space": False,
        },
    )
    result = checker.run()
    assert result.checks == []
