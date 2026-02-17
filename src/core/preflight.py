"""Pre-dispatch checks to reduce avoidable failed sessions."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .git_utils import GitRepo


@dataclass
class PreflightCheck:
    """Single preflight check result."""

    name: str
    level: str  # info, warn, block
    message: str
    action_hint: str | None = None


@dataclass
class PreflightResult:
    """All preflight checks."""

    checks: list[PreflightCheck] = field(default_factory=list)

    @property
    def has_blockers(self) -> bool:
        return any(check.level == "block" for check in self.checks)

    @property
    def has_warnings(self) -> bool:
        return any(check.level == "warn" for check in self.checks)

    def summary(self) -> str:
        if not self.checks:
            return "No issues detected."
        return "\n".join(f"{check.level.upper()}: {check.message}" for check in self.checks)


class PreflightChecker:
    """Run preflight checks for a project."""

    def __init__(self, project_path: Path, enabled_checks: dict[str, bool] | None = None):
        self.path = project_path.resolve()
        self.enabled_checks = enabled_checks or {}

    def run(self) -> PreflightResult:
        result = PreflightResult()
        if self.enabled_checks.get("uncommitted_changes", True):
            result.checks.extend(self._check_uncommitted_changes())
        if self.enabled_checks.get("behind_remote", True):
            result.checks.extend(self._check_branch_behind_remote())
        if self.enabled_checks.get("stale_dependencies", True):
            result.checks.extend(self._check_stale_dependencies())
        if self.enabled_checks.get("disk_space", True):
            result.checks.extend(self._check_disk_space())
        return result

    def _check_uncommitted_changes(self) -> list[PreflightCheck]:
        if not GitRepo.is_git_repo(self.path):
            return []
        repo = GitRepo(self.path)
        status = repo.get_status()
        changed = status.total_changed_files + len(status.untracked_files)
        if changed == 0:
            return []
        return [
            PreflightCheck(
                name="uncommitted_changes",
                level="warn",
                message=f"{changed} local file(s) are uncommitted.",
                action_hint="Stash or commit before starting a new session.",
            )
        ]

    def _check_branch_behind_remote(self) -> list[PreflightCheck]:
        if not GitRepo.is_git_repo(self.path):
            return []
        try:
            result = subprocess.run(
                ["git", "rev-list", "--count", "HEAD..@{u}"],
                cwd=self.path,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

        if result.returncode != 0:
            return []
        try:
            behind = int(result.stdout.strip() or "0")
        except ValueError:
            return []

        if behind <= 0:
            return []
        return [
            PreflightCheck(
                name="behind_remote",
                level="warn",
                message=f"Branch is behind upstream by {behind} commit(s).",
                action_hint="Pull latest changes before dispatch.",
            )
        ]

    def _check_stale_dependencies(self) -> list[PreflightCheck]:
        lock_candidates = ["requirements.txt", "pyproject.toml", "package-lock.json", "poetry.lock"]
        changed = []
        if GitRepo.is_git_repo(self.path):
            repo = GitRepo(self.path)
            status = repo.get_status()
            changed = status.modified_files + status.staged_files

        hits = [path for path in lock_candidates if path in changed]
        if not hits:
            return []
        return [
            PreflightCheck(
                name="stale_dependencies",
                level="warn",
                message=f"Dependency file changed: {', '.join(hits)}",
                action_hint="Install/update dependencies before session.",
            )
        ]

    def _check_disk_space(self) -> list[PreflightCheck]:
        try:
            result = subprocess.run(
                ["df", "-k", str(self.path)],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []
        if result.returncode != 0:
            return []
        lines = result.stdout.strip().splitlines()
        if len(lines) < 2:
            return []
        parts = lines[-1].split()
        if len(parts) < 4:
            return []
        try:
            available_kb = int(parts[3])
        except ValueError:
            return []
        available_gb = available_kb / (1024 * 1024)
        if available_gb >= 2:
            return []
        return [
            PreflightCheck(
                name="disk_space",
                level="block",
                message=f"Low disk space ({available_gb:.2f} GB available).",
                action_hint="Free space before running heavy sessions.",
            )
        ]
