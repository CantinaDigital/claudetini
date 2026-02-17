"""Tests for branch strategy detection."""

import subprocess

from src.core.branch_strategy import BranchStrategy, BranchStrategyDetector


def test_branch_strategy_detects_git_flow(temp_dir):
    subprocess.run(["git", "init"], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_dir, check=True, capture_output=True)
    (temp_dir / "README.md").write_text("# Repo\n")
    subprocess.run(["git", "add", "README.md"], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-B", "main"], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "develop"], cwd=temp_dir, check=True, capture_output=True)
    result = BranchStrategyDetector(temp_dir).detect()
    assert result.strategy == BranchStrategy.GIT_FLOW


def test_suggested_branch_name(temp_dir):
    detector = BranchStrategyDetector(temp_dir)
    name = detector.suggested_branch_name("Implement OAuth Flow!")
    assert name.startswith("feature/")
