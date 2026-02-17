"""Branch strategy detection and adaptive branch naming."""

import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class BranchStrategy(Enum):
    """Detected git branching model."""

    TRUNK_BASED = "trunk_based"
    GIT_FLOW = "git_flow"
    FEATURE_BRANCH = "feature_branch"
    PR_BASED = "pr_based"
    UNKNOWN = "unknown"


@dataclass
class BranchStrategyResult:
    """Result of branch strategy detection."""

    strategy: BranchStrategy
    reason: str

    @property
    def label(self) -> str:
        labels = {
            BranchStrategy.TRUNK_BASED: "Trunk-based",
            BranchStrategy.GIT_FLOW: "Git Flow",
            BranchStrategy.FEATURE_BRANCH: "Feature Branch",
            BranchStrategy.PR_BASED: "PR-based",
            BranchStrategy.UNKNOWN: "Unknown",
        }
        return labels[self.strategy]


class BranchStrategyDetector:
    """Infer branch strategy from repository topology and history."""

    def __init__(self, project_path: Path):
        self.path = project_path.resolve()

    def detect(self) -> BranchStrategyResult:
        branches = self._list_branches()
        if not branches:
            return BranchStrategyResult(BranchStrategy.UNKNOWN, "No branch data available.")

        has_main = "main" in branches or "master" in branches
        has_develop = "develop" in branches
        feature_like = [b for b in branches if b.startswith(("feature/", "feat/", "bugfix/", "hotfix/"))]

        if has_main and has_develop:
            return BranchStrategyResult(BranchStrategy.GIT_FLOW, "Detected both main/master and develop branches.")
        if feature_like:
            merge_commits = self._recent_merge_commits()
            if merge_commits > 0:
                return BranchStrategyResult(BranchStrategy.PR_BASED, "Feature branches merged via merge commits.")
            return BranchStrategyResult(BranchStrategy.FEATURE_BRANCH, "Feature-style branch names detected.")
        if has_main and len(branches) <= 2:
            return BranchStrategyResult(BranchStrategy.TRUNK_BASED, "Few branches and direct main development.")
        return BranchStrategyResult(BranchStrategy.UNKNOWN, "Could not confidently infer strategy.")

    def suggested_branch_name(self, task: str) -> str:
        """Return a feature branch name for a task."""
        slug = re.sub(r"[^a-z0-9]+", "-", task.lower()).strip("-")
        slug = re.sub(r"-{2,}", "-", slug)[:40] or "task"
        return f"feature/{slug}"

    def create_draft_pr(
        self,
        title: str,
        body: str,
    ) -> tuple[bool, str]:
        """Create a draft pull request with GitHub CLI."""
        if not self.gh_available():
            return False, "GitHub CLI (`gh`) is not available."
        try:
            result = subprocess.run(
                ["gh", "pr", "create", "--draft", "--title", title, "--body", body],
                cwd=self.path,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False, "Timed out or could not execute `gh pr create`."
        if result.returncode != 0:
            return False, (result.stderr.strip() or result.stdout.strip() or "Failed to create PR.")
        return True, (result.stdout.strip() or "Draft PR created.")

    def gh_available(self) -> bool:
        """Check if GitHub CLI is available in PATH."""
        try:
            result = subprocess.run(
                ["gh", "--version"],
                cwd=self.path,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    def _list_branches(self) -> list[str]:
        output = self._run_git("branch", "--format=%(refname:short)")
        return [line.strip() for line in output.splitlines() if line.strip()]

    def _recent_merge_commits(self) -> int:
        output = self._run_git("log", "--merges", "--oneline", "-30")
        return len([line for line in output.splitlines() if line.strip()])

    def _run_git(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.path,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""
        if result.returncode != 0:
            return ""
        return result.stdout.strip()
