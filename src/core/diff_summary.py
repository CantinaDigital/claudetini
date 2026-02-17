"""Human-readable diff summaries for session reports."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileChange:
    """Summary stats for a changed file."""

    path: str
    additions: int
    deletions: int
    change_type: str
    summary: str = ""


@dataclass
class DiffSummary:
    """Overall diff summary."""

    files_new: list[FileChange] = field(default_factory=list)
    files_modified: list[FileChange] = field(default_factory=list)
    files_deleted: list[str] = field(default_factory=list)
    total_additions: int = 0
    total_deletions: int = 0

    @property
    def total_files(self) -> int:
        return len(self.files_new) + len(self.files_modified) + len(self.files_deleted)


class DiffSummaryBuilder:
    """Build diff summaries from git data."""

    def __init__(self, project_path: Path):
        self.project_path = project_path.resolve()

    def build(self, from_ref: str, to_ref: str = "HEAD") -> DiffSummary:
        """Build summary for `git diff from_ref..to_ref`."""
        summary = DiffSummary()
        lines = self._run_git("diff", "--numstat", "--name-status", from_ref, to_ref)
        for line in lines.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue

            status = parts[0].strip()
            if status and status[0] in {"A", "M", "D", "R", "C"}:
                # format from name-status can look like "M\tpath" but here with numstat+name-status
                # fallback to parsing simple status rows.
                continue

            additions_str, deletions_str, path = parts[0], parts[1], parts[2]
            additions = 0 if additions_str == "-" else int(additions_str)
            deletions = 0 if deletions_str == "-" else int(deletions_str)
            summary.total_additions += additions
            summary.total_deletions += deletions

            change_type = self._change_type(from_ref, to_ref, path)
            file_change = FileChange(
                path=path,
                additions=additions,
                deletions=deletions,
                change_type=change_type,
            )
            if change_type == "new":
                summary.files_new.append(file_change)
            elif change_type == "deleted":
                summary.files_deleted.append(path)
            else:
                summary.files_modified.append(file_change)

        return summary

    def _change_type(self, from_ref: str, to_ref: str, path: str) -> str:
        status_line = self._run_git("diff", "--name-status", from_ref, to_ref, "--", path).strip()
        if not status_line:
            return "modified"
        status = status_line.split("\t")[0]
        if status.startswith("A"):
            return "new"
        if status.startswith("D"):
            return "deleted"
        if status.startswith("R"):
            return "renamed"
        return "modified"

    def _run_git(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""

        if result.returncode != 0:
            return ""
        return result.stdout

