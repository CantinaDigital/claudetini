"""Git history, branch, and diff operations."""

import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


def _ensure_naive(dt: datetime) -> datetime:
    """Ensure datetime is naive (no timezone info) for consistent comparisons."""
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def is_git_repo(path: Path) -> bool:
    """Check if a path is a git repository.

    Args:
        path: Path to check

    Returns:
        True if the path contains a .git directory
    """
    return (path / ".git").exists()


@dataclass
class GitCommit:
    """A single git commit."""

    sha: str
    message: str
    author: str
    timestamp: datetime
    files_changed: list[str] = field(default_factory=list)

    @property
    def short_sha(self) -> str:
        return self.sha[:7]

    @property
    def first_line(self) -> str:
        """First line of the commit message."""
        return self.message.split("\n")[0]


@dataclass
class GitStatus:
    """Current git status of the repository."""

    branch: str
    staged_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    untracked_files: list[str] = field(default_factory=list)
    submodule_issues: list[str] = field(default_factory=list)

    @property
    def has_uncommitted_changes(self) -> bool:
        return bool(self.staged_files or self.modified_files)

    @property
    def total_changed_files(self) -> int:
        return len(self.staged_files) + len(self.modified_files)


class GitRepo:
    """Git repository operations for a project."""

    def __init__(self, path: Path):
        self.path = path.resolve()
        self._validate_repo()

    def _validate_repo(self) -> None:
        """Validate this is a git repository."""
        git_dir = self.path / ".git"
        if not git_dir.exists():
            raise ValueError(f"Not a git repository: {self.path}")

    def _run_git(self, *args: str) -> tuple[str, int]:
        """Run a git command and return output and return code."""
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            # Preserve leading spaces for porcelain output parsing.
            return result.stdout.rstrip("\n"), result.returncode
        except subprocess.TimeoutExpired:
            return "", 1
        except FileNotFoundError:
            return "", 1

    def get_current_branch(self) -> str:
        """Get the current branch name."""
        output, _ = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        return output or "unknown"

    def get_status(self) -> GitStatus:
        """Get the current git status.

        Properly distinguishes between:
        - Staged files (in index, ready to commit)
        - Modified files (working tree changes, not staged)
        - Untracked files (new files not in git)
        - Submodule issues (submodules/nested repos with uncommitted changes)
        """
        branch = self.get_current_branch()

        staged = []
        modified = []
        untracked = []
        submodule_issues = []

        # Get gitlinks (submodules/nested repos) - mode 160000
        gitlinks: set[str] = set()
        ls_output, _ = self._run_git("ls-files", "--stage")
        for line in ls_output.split("\n"):
            if not line:
                continue
            # Format: mode hash stage\tfilepath
            if line.startswith("160000"):
                parts = line.split("\t", 1)
                if len(parts) > 1:
                    gitlinks.add(parts[1])

        # Get status in porcelain format
        # Format: XY filename
        # X = index/staging status, Y = working tree status
        # Lowercase letters indicate submodule issues
        output, _ = self._run_git("status", "--porcelain")

        for line in output.split("\n"):
            if not line:
                continue

            status = line[:2]
            filepath = line[3:]

            index_status = status[0]
            worktree_status = status[1]

            # Check for submodule issues:
            # 1. Lowercase status codes (submodule has modified content)
            # 2. Gitlinks (nested repos) that show as modified
            is_submodule_issue = (
                index_status.islower() or
                worktree_status.islower() or
                (filepath in gitlinks and worktree_status in "MD")
            )

            if is_submodule_issue:
                submodule_issues.append(filepath)
                continue

            # Staged changes (index has changes)
            if index_status in "MARCD":
                staged.append(filepath)

            # Working tree changes (not staged)
            if worktree_status in "MD":
                modified.append(filepath)

            # Untracked files
            if status == "??":
                untracked.append(filepath)

        return GitStatus(
            branch=branch,
            staged_files=staged,
            modified_files=modified,
            untracked_files=untracked,
            submodule_issues=submodule_issues,
        )

    def get_recent_commits(self, count: int = 10) -> list[GitCommit]:
        """Get the most recent commits."""
        # Format: hash|author|timestamp|message
        format_str = "%H|%an|%aI|%s"
        output, code = self._run_git(
            "log", f"-{count}", f"--format={format_str}"
        )

        if code != 0 or not output:
            return []

        commits = []
        for line in output.split("\n"):
            if not line:
                continue

            parts = line.split("|", 3)
            if len(parts) < 4:
                continue

            sha, author, timestamp_str, message = parts

            try:
                timestamp = _ensure_naive(datetime.fromisoformat(timestamp_str))
            except ValueError:
                timestamp = datetime.now()

            commits.append(GitCommit(
                sha=sha,
                author=author,
                timestamp=timestamp,
                message=message,
            ))

        return commits

    def get_commits_since(self, since: datetime) -> list[GitCommit]:
        """Get commits since a specific datetime."""
        since_str = since.strftime("%Y-%m-%d %H:%M:%S")
        format_str = "%H|%an|%aI|%s"
        output, code = self._run_git(
            "log", f"--since={since_str}", f"--format={format_str}"
        )

        if code != 0 or not output:
            return []

        commits = []
        for line in output.split("\n"):
            if not line:
                continue

            parts = line.split("|", 3)
            if len(parts) < 4:
                continue

            sha, author, timestamp_str, message = parts

            try:
                timestamp = _ensure_naive(datetime.fromisoformat(timestamp_str))
            except ValueError:
                continue

            commits.append(GitCommit(
                sha=sha,
                author=author,
                timestamp=timestamp,
                message=message,
            ))

        return commits

    def get_files_changed_in_commit(self, sha: str) -> list[str]:
        """Get list of files changed in a specific commit."""
        output, code = self._run_git("diff-tree", "--no-commit-id", "--name-only", "-r", sha)
        if code != 0:
            return []
        return [f for f in output.split("\n") if f]

    def get_diff_content(self, sha1: str, sha2: str) -> str:
        """Get the full diff content between two commits.

        Args:
            sha1: Starting commit SHA
            sha2: Ending commit SHA

        Returns:
            The diff content as a string
        """
        output, code = self._run_git("diff", sha1, sha2)
        if code != 0:
            return ""
        return output

    def get_diff_stats(self, from_ref: str = "HEAD~1", to_ref: str = "HEAD") -> dict:
        """Get diff statistics between two refs."""
        output, code = self._run_git("diff", "--stat", from_ref, to_ref)

        if code != 0:
            return {"files_changed": 0, "insertions": 0, "deletions": 0}

        # Parse the summary line
        lines = output.strip().split("\n")
        if not lines:
            return {"files_changed": 0, "insertions": 0, "deletions": 0}

        # Last line contains summary
        summary = lines[-1]
        stats = {"files_changed": 0, "insertions": 0, "deletions": 0}

        import re

        files_match = re.search(r"(\d+) files? changed", summary)
        if files_match:
            stats["files_changed"] = int(files_match.group(1))

        insertions_match = re.search(r"(\d+) insertions?", summary)
        if insertions_match:
            stats["insertions"] = int(insertions_match.group(1))

        deletions_match = re.search(r"(\d+) deletions?", summary)
        if deletions_match:
            stats["deletions"] = int(deletions_match.group(1))

        return stats

    def has_gitignore(self) -> bool:
        """Check if .gitignore exists."""
        return (self.path / ".gitignore").exists()

    @classmethod
    def is_git_repo(cls, path: Path) -> bool:
        """Check if a path is a git repository."""
        return (path / ".git").exists()


class GitUtils:
    """Simplified git utilities for UI components."""

    def __init__(self, project_path: Path):
        self.path = project_path.resolve()
        self._repo = GitRepo(project_path) if GitRepo.is_git_repo(project_path) else None

    def current_branch(self) -> str:
        """Get current branch name."""
        if not self._repo:
            return "unknown"
        return self._repo.get_current_branch()

    def uncommitted_files(self) -> list[dict]:
        """Get list of uncommitted files with status."""
        if not self._repo:
            return []

        status = self._repo.get_status()
        result = []

        for f in status.staged_files:
            result.append({"path": f, "status": "A"})

        for f in status.modified_files:
            result.append({"path": f, "status": "M"})

        for f in status.untracked_files:
            result.append({"path": f, "status": "?"})

        return result

    def get_status_detailed(self) -> dict:
        """Get detailed status with staged, modified, untracked, and submodule issues separated.

        Returns a dict with:
        - staged: list of {path, status, lines} for files in the index
        - modified: list of {path, status, lines} for working tree changes
        - untracked: list of file paths
        - submodule_issues: list of submodule paths with issues
        """
        if not self._repo:
            return {"staged": [], "modified": [], "untracked": [], "submodule_issues": []}

        status = self._repo.get_status()

        # Get numstat for line changes
        numstat_output, code = self._repo._run_git("diff", "--numstat")
        line_stats: dict[str, str] = {}
        if code == 0 and numstat_output:
            for line in numstat_output.split("\n"):
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 3:
                    added, removed, fname = parts[0], parts[1], parts[2]
                    if added != "-" and removed != "-":
                        line_stats[fname] = f"+{added} -{removed}"

        # Get staged numstat separately
        staged_numstat_output, code = self._repo._run_git("diff", "--cached", "--numstat")
        staged_line_stats: dict[str, str] = {}
        if code == 0 and staged_numstat_output:
            for line in staged_numstat_output.split("\n"):
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 3:
                    added, removed, fname = parts[0], parts[1], parts[2]
                    if added != "-" and removed != "-":
                        staged_line_stats[fname] = f"+{added} -{removed}"

        staged = [
            {"path": f, "status": "A", "lines": staged_line_stats.get(f)}
            for f in status.staged_files
        ]

        modified = [
            {"path": f, "status": "M", "lines": line_stats.get(f)}
            for f in status.modified_files
        ]

        return {
            "staged": staged,
            "modified": modified,
            "untracked": status.untracked_files,
            "submodule_issues": status.submodule_issues,
        }

    def unpushed_commits(self) -> list[dict]:
        """Get list of unpushed commits."""
        if not self._repo:
            return []

        # Get unpushed commits by comparing with origin
        output, code = self._repo._run_git(
            "log", "--oneline", "@{u}..", "--format=%H|%s|%ar"
        )

        if code != 0 or not output:
            return []

        commits = []
        for line in output.split("\n"):
            if not line:
                continue

            parts = line.split("|", 2)
            if len(parts) >= 3:
                commits.append({
                    "hash": parts[0],
                    "message": parts[1],
                    "time": parts[2],
                })

        return commits

    def recent_commits(self, limit: int = 10) -> list[dict]:
        """Get recent commits formatted for UI."""
        if not self._repo:
            return []

        output, code = self._repo._run_git(
            "log", f"-{limit}",
            "--format=%H|%s|%ad|%ar|%P",
            "--date=format:%Y-%m-%d|%H:%M"
        )

        if code != 0 or not output:
            return []

        commits = []
        branch = self.current_branch()

        for line in output.split("\n"):
            if not line:
                continue

            parts = line.split("|")
            if len(parts) >= 5:
                parents = parts[4] if len(parts) > 4 else ""
                is_merge = " " in parents  # Multiple parents = merge commit

                commits.append({
                    "hash": parts[0],
                    "message": parts[1],
                    "date": parts[2],
                    "time": parts[3],
                    "branch": branch,
                    "is_merge": is_merge,
                })

        return commits

    def get_diff_summary(self, max_lines: int = 50) -> str | None:
        """Get a human-readable summary of uncommitted changes for prompt context.

        Returns a summary of staged and unstaged changes suitable for injection
        into Claude prompts. This helps Claude understand recent work context.
        """
        if not self._repo:
            return None

        status = self._repo.get_status()
        if not status.has_uncommitted_changes and not status.untracked_files:
            return None

        lines = []

        # Header with file counts
        total = status.total_changed_files + len(status.untracked_files)
        lines.append(f"**{total} files with uncommitted changes:**")
        lines.append("")

        # Staged files
        if status.staged_files:
            lines.append(f"Staged ({len(status.staged_files)}):")
            for f in status.staged_files[:10]:
                lines.append(f"  + {f}")
            if len(status.staged_files) > 10:
                lines.append(f"  ... and {len(status.staged_files) - 10} more")
            lines.append("")

        # Modified files
        if status.modified_files:
            lines.append(f"Modified ({len(status.modified_files)}):")
            for f in status.modified_files[:10]:
                lines.append(f"  ~ {f}")
            if len(status.modified_files) > 10:
                lines.append(f"  ... and {len(status.modified_files) - 10} more")
            lines.append("")

        # Get actual diff content (truncated)
        diff_output, code = self._repo._run_git("diff", "--stat")
        if code == 0 and diff_output:
            diff_lines = diff_output.split("\n")
            if len(diff_lines) > max_lines:
                diff_lines = diff_lines[:max_lines]
                diff_lines.append(f"... truncated ({len(diff_output.split(chr(10)))} total lines)")
            lines.append("```")
            lines.extend(diff_lines)
            lines.append("```")

        return "\n".join(lines)

    def get_diff(self) -> str:
        """Get the full diff of all changes (staged + unstaged).

        Returns the raw git diff output suitable for feeding to an LLM
        for commit message generation.
        """
        if not self._repo:
            return ""

        # Get diff of staged changes (index vs HEAD)
        staged_diff, _ = self._repo._run_git("diff", "--cached")

        # Get diff of unstaged changes (working tree vs index)
        unstaged_diff, _ = self._repo._run_git("diff")

        # Combine both diffs
        combined = []
        if staged_diff and staged_diff.strip():
            combined.append("# Staged changes:\n")
            combined.append(staged_diff)
        if unstaged_diff and unstaged_diff.strip():
            if combined:
                combined.append("\n# Unstaged changes:\n")
            combined.append(unstaged_diff)

        return "\n".join(combined) if combined else ""

    def list_stashes(self) -> list[dict]:
        """Get list of git stashes."""
        if not self._repo:
            return []

        output, code = self._repo._run_git(
            "stash", "list", "--format=%gd|%gs|%ar"
        )

        if code != 0 or not output:
            return []

        stashes = []
        for line in output.split("\n"):
            if not line:
                continue

            parts = line.split("|", 2)
            if len(parts) >= 3:
                stashes.append({
                    "id": parts[0],
                    "message": parts[1],
                    "time": parts[2],
                })

        return stashes

    def get_file_line_changes(self, filepath: str) -> str | None:
        """Get line changes for a specific file (+N -M format)."""
        if not self._repo:
            return None

        output, code = self._repo._run_git("diff", "--numstat", "--", filepath)
        if code != 0 or not output:
            return None

        # numstat format: added<tab>removed<tab>filename
        for line in output.split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                added = parts[0]
                removed = parts[1]
                if added != "-" and removed != "-":
                    return f"+{added} -{removed}"
        return None

    def uncommitted_files_with_lines(self) -> list[dict]:
        """Get list of uncommitted files with line change stats."""
        if not self._repo:
            return []

        status = self._repo.get_status()
        result = []

        # Get numstat for all changes at once for efficiency
        numstat_output, code = self._repo._run_git("diff", "--numstat")
        line_stats: dict[str, str] = {}
        if code == 0 and numstat_output:
            for line in numstat_output.split("\n"):
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 3:
                    added, removed, fname = parts[0], parts[1], parts[2]
                    if added != "-" and removed != "-":
                        line_stats[fname] = f"+{added} -{removed}"

        for f in status.staged_files:
            result.append({
                "path": f,
                "status": "A",
                "lines": line_stats.get(f),
            })

        for f in status.modified_files:
            result.append({
                "path": f,
                "status": "M",
                "lines": line_stats.get(f),
            })

        for f in status.untracked_files:
            result.append({
                "path": f,
                "status": "?",
                "lines": None,
            })

        return result

    def push_to_remote(self, branch: str | None = None) -> tuple[bool, str]:
        """Push current branch to origin.

        Returns (success, message).
        """
        if not self._repo:
            return False, "Not a git repository"

        target_branch = branch or self.current_branch()
        output, code = self._repo._run_git("push", "origin", target_branch)

        if code != 0:
            # Get stderr for error message
            try:
                result = subprocess.run(
                    ["git", "push", "origin", target_branch],
                    cwd=self.path,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                error_msg = result.stderr.strip() or result.stdout.strip() or "Push failed"
                return False, error_msg
            except Exception as e:
                return False, str(e)

        return True, f"Pushed to origin/{target_branch}"

    def commit_all(self, message: str, ignore_submodules: bool = True) -> tuple[bool, str, str | None]:
        """Stage all changes and commit.

        Args:
            message: Commit message.
            ignore_submodules: If True, skip submodules with dirty state (default True).

        Returns (success, message, commit_hash or None).
        """
        if not self._repo:
            return False, "Not a git repository", None

        # Check for submodule issues first
        status_output, _ = self._repo._run_git("status", "--porcelain")
        has_submodule_issues = False
        submodule_names = []
        regular_files = []

        for line in status_output.split("\n"):
            if not line:
                continue
            # Submodules with modified content show lowercase status codes
            status_code = line[:2]
            filepath = line[3:]

            # Check if this is a submodule with dirty state
            # Lowercase letters indicate submodule issues
            if status_code[0].islower() or status_code[1].islower():
                has_submodule_issues = True
                submodule_names.append(filepath)
            else:
                regular_files.append(filepath)

        if has_submodule_issues:
            if ignore_submodules:
                # Stage only regular files, not submodules
                if not regular_files:
                    return False, f"Only submodule changes detected ({', '.join(submodule_names)}). Commit changes inside submodules first.", None

                # Stage each regular file individually
                for filepath in regular_files:
                    self._repo._run_git("add", "--", filepath)
            else:
                return False, f"Submodules have uncommitted changes: {', '.join(submodule_names)}. Commit inside submodules first.", None
        else:
            # No submodule issues, stage all
            _, add_code = self._repo._run_git("add", "-A")
            if add_code != 0:
                return False, "Failed to stage changes", None

        # Commit
        output, code = self._repo._run_git("commit", "-m", message)
        if code != 0:
            if "nothing to commit" in output.lower():
                return False, "Nothing to commit", None
            # Simplify the error message
            error_msg = output.replace("\n", " ").strip()
            if len(error_msg) > 200:
                error_msg = error_msg[:200] + "..."
            return False, error_msg or "Commit failed", None

        # Get the new commit hash
        hash_output, _ = self._repo._run_git("rev-parse", "--short", "HEAD")
        commit_hash = hash_output.strip() if hash_output else None

        return True, f"Created commit {commit_hash}: {message}", commit_hash

    def stash_pop(self, stash_id: str | None = None) -> tuple[bool, str]:
        """Pop the most recent stash or specified stash.

        Returns (success, message).
        """
        if not self._repo:
            return False, "Not a git repository"

        args = ["stash", "pop"]
        if stash_id:
            args.append(stash_id)

        output, code = self._repo._run_git(*args)
        if code != 0:
            if "conflict" in output.lower():
                return False, "Stash applied with conflicts - resolve manually"
            return False, output or "Stash pop failed"

        return True, "Stash applied successfully"

    def stash_drop(self, stash_id: str | None = None) -> tuple[bool, str]:
        """Drop the most recent stash or specified stash.

        Returns (success, message).
        """
        if not self._repo:
            return False, "Not a git repository"

        args = ["stash", "drop"]
        if stash_id:
            args.append(stash_id)

        output, code = self._repo._run_git(*args)
        if code != 0:
            return False, output or "Stash drop failed"

        return True, "Stash dropped"

    def stage_files(self, files: list[str]) -> tuple[bool, str, list[str]]:
        """Stage specific files.

        Args:
            files: List of file paths to stage.

        Returns (success, message, list of staged files).
        """
        if not self._repo:
            return False, "Not a git repository", []

        if not files:
            return False, "No files specified", []

        # Get current status to identify submodules
        status = self._repo.get_status()
        submodule_set = set(status.submodule_issues)

        staged = []
        errors = []
        skipped_submodules = []

        for filepath in files:
            # Skip submodules - they can't be staged this way
            if filepath in submodule_set:
                skipped_submodules.append(filepath)
                continue

            _, code = self._repo._run_git("add", "--", filepath)
            if code == 0:
                # Verify the file was actually staged by checking status
                new_status = self._repo.get_status()
                if filepath in new_status.staged_files:
                    staged.append(filepath)
                else:
                    # git add succeeded but file not in staged (submodule edge case)
                    skipped_submodules.append(filepath)
            else:
                errors.append(filepath)

        if skipped_submodules and not staged and not errors:
            return False, f"Cannot stage submodules: {', '.join(skipped_submodules)}. Commit inside submodule first.", []

        if errors and not staged:
            return False, f"Failed to stage: {', '.join(errors)}", []

        msg = f"Staged {len(staged)} file(s)"
        if errors:
            msg += f" ({len(errors)} failed)"
        if skipped_submodules:
            msg += f" ({len(skipped_submodules)} submodules skipped)"

        return len(staged) > 0 or len(skipped_submodules) == 0, msg, staged

    def unstage_files(self, files: list[str]) -> tuple[bool, str, list[str]]:
        """Unstage specific files (remove from staging area).

        Args:
            files: List of file paths to unstage.

        Returns (success, message, list of unstaged files).
        """
        if not self._repo:
            return False, "Not a git repository", []

        if not files:
            return False, "No files specified", []

        unstaged = []
        errors = []

        for filepath in files:
            _, code = self._repo._run_git("restore", "--staged", "--", filepath)
            if code == 0:
                unstaged.append(filepath)
            else:
                errors.append(filepath)

        if errors and not unstaged:
            return False, f"Failed to unstage: {', '.join(errors)}", []

        msg = f"Unstaged {len(unstaged)} file(s)"
        if errors:
            msg += f" ({len(errors)} failed)"

        return True, msg, unstaged

    def stage_all(self) -> tuple[bool, str]:
        """Stage all changes.

        Returns (success, message).
        """
        if not self._repo:
            return False, "Not a git repository"

        _, code = self._repo._run_git("add", "-A")
        if code != 0:
            return False, "Failed to stage changes"

        return True, "All changes staged"

    def unstage_all(self) -> tuple[bool, str]:
        """Unstage all staged changes.

        Returns (success, message).
        """
        if not self._repo:
            return False, "Not a git repository"

        _, code = self._repo._run_git("reset", "HEAD")
        if code != 0:
            return False, "Failed to unstage changes"

        return True, "All changes unstaged"

    def commit_staged(self, message: str) -> tuple[bool, str, str | None]:
        """Commit only staged changes (does not auto-stage).

        Args:
            message: Commit message.

        Returns (success, message, commit_hash or None).
        """
        if not self._repo:
            return False, "Not a git repository", None

        # Check if there are staged changes
        status = self._repo.get_status()
        if not status.staged_files:
            return False, "No staged changes to commit", None

        # Commit
        output, code = self._repo._run_git("commit", "-m", message)
        if code != 0:
            error_msg = output.replace("\n", " ").strip()
            if len(error_msg) > 200:
                error_msg = error_msg[:200] + "..."
            return False, error_msg or "Commit failed", None

        # Get the new commit hash
        hash_output, _ = self._repo._run_git("rev-parse", "--short", "HEAD")
        commit_hash = hash_output.strip() if hash_output else None

        return True, f"Created commit {commit_hash}", commit_hash

    def discard_file(self, filepath: str) -> tuple[bool, str]:
        """Discard changes to a specific file (restore to last commit).

        Args:
            filepath: File path to discard.

        Returns (success, message).
        """
        if not self._repo:
            return False, "Not a git repository"

        _, code = self._repo._run_git("checkout", "--", filepath)
        if code != 0:
            return False, f"Failed to discard changes to {filepath}"

        return True, f"Discarded changes to {filepath}"

    def delete_untracked(self, filepath: str) -> tuple[bool, str]:
        """Delete an untracked file.

        Args:
            filepath: File path to delete.

        Returns (success, message).
        """
        if not self._repo:
            return False, "Not a git repository"

        full_path = self.path / filepath
        try:
            if full_path.exists():
                full_path.unlink()
                return True, f"Deleted {filepath}"
            return False, f"File not found: {filepath}"
        except Exception as e:
            return False, f"Failed to delete {filepath}: {e}"
