"""Git worktree lifecycle management for parallel agent execution."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

WORKTREE_DIR_NAME = ".cantina-worktrees"


@dataclass
class WorktreeInfo:
    """Metadata for a single git worktree."""

    path: Path
    branch: str
    task_index: int
    created_at: datetime = field(default_factory=datetime.now)
    status: Literal["active", "merged", "failed", "cleaned"] = "active"


class WorktreeManager:
    """Create, manage, and clean up git worktrees for parallel dispatch.

    Worktrees are created under ``<project_root>/.cantina-worktrees/``
    with branches named ``parallel/<batch_id>/<task_index>``.
    """

    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path.resolve()
        self._worktree_root = self.project_path / WORKTREE_DIR_NAME
        self._validate_repo()

    def _validate_repo(self) -> None:
        git_dir = self.project_path / ".git"
        if not git_dir.exists():
            raise ValueError(f"Not a git repository: {self.project_path}")

    def _run_git(self, *args: str, timeout: int = 60) -> tuple[str, int]:
        """Run a git command in the project root."""
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.stdout.rstrip("\n"), result.returncode
        except subprocess.TimeoutExpired:
            return "", 1
        except FileNotFoundError:
            return "", 1

    def _ensure_gitignore(self) -> None:
        """Add the worktree directory to .gitignore if not already present."""
        gitignore = self.project_path / ".gitignore"
        entry = f"/{WORKTREE_DIR_NAME}/"
        if gitignore.exists():
            content = gitignore.read_text(encoding="utf-8")
            if entry in content or WORKTREE_DIR_NAME in content:
                return
            if not content.endswith("\n"):
                content += "\n"
            content += f"{entry}\n"
            gitignore.write_text(content, encoding="utf-8")
        else:
            gitignore.write_text(f"{entry}\n", encoding="utf-8")

    def create_worktree(
        self,
        batch_id: str,
        task_index: int,
        base_ref: str = "HEAD",
    ) -> WorktreeInfo:
        """Create a new worktree for a task in a parallel batch.

        Returns:
            WorktreeInfo with the worktree path and branch name.

        Raises:
            RuntimeError: If the worktree could not be created.
        """
        self._ensure_gitignore()
        self._worktree_root.mkdir(parents=True, exist_ok=True)

        branch = f"parallel/{batch_id}/{task_index}"
        worktree_path = self._worktree_root / f"{batch_id}-{task_index}"

        # Create a new branch from base_ref and attach it to the worktree
        output, code = self._run_git(
            "worktree", "add", "-b", branch, str(worktree_path), base_ref,
        )
        if code != 0:
            raise RuntimeError(
                f"Failed to create worktree for task {task_index}: {output}"
            )

        # Symlink node_modules so TypeScript agents can compile-check
        self._symlink_node_modules(worktree_path)

        return WorktreeInfo(
            path=worktree_path,
            branch=branch,
            task_index=task_index,
        )

    def _symlink_node_modules(self, worktree_path: Path) -> None:
        """Symlink node_modules directories from the main project into a worktree.

        Git worktrees don't include gitignored directories like node_modules.
        Without this, TypeScript agents can't run tsc --noEmit or npm commands.
        """
        # Find node_modules directories in the main project (one level deep)
        for child in self.project_path.iterdir():
            if not child.is_dir() or child.name.startswith("."):
                continue
            nm = child / "node_modules"
            if nm.is_dir():
                target = worktree_path / child.name / "node_modules"
                if not target.exists() and target.parent.exists():
                    try:
                        target.symlink_to(nm)
                    except OSError:
                        pass

        # Also check root-level node_modules
        root_nm = self.project_path / "node_modules"
        if root_nm.is_dir():
            target = worktree_path / "node_modules"
            if not target.exists():
                try:
                    target.symlink_to(root_nm)
                except OSError:
                    pass

    def list_worktrees(self) -> list[WorktreeInfo]:
        """List all cantina-managed worktrees."""
        output, code = self._run_git("worktree", "list", "--porcelain")
        if code != 0:
            return []

        worktrees: list[WorktreeInfo] = []
        current_path: Path | None = None
        current_branch: str | None = None

        def _flush_entry() -> None:
            nonlocal current_path, current_branch
            if current_path and current_branch:
                if (
                    current_branch.startswith("parallel/")
                    and str(current_path).startswith(str(self._worktree_root))
                ):
                    parts = current_branch.split("/")
                    try:
                        task_index = int(parts[-1])
                    except (ValueError, IndexError):
                        task_index = -1
                    worktrees.append(
                        WorktreeInfo(
                            path=current_path,
                            branch=current_branch,
                            task_index=task_index,
                        )
                    )
            current_path = None
            current_branch = None

        for line in output.split("\n"):
            if line.startswith("worktree "):
                # Flush previous entry before starting a new one
                _flush_entry()
                current_path = Path(line[9:])
            elif line.startswith("branch refs/heads/"):
                current_branch = line[18:]
            elif line == "":
                _flush_entry()

        # Flush the last entry (porcelain output may not end with blank line)
        _flush_entry()

        return worktrees

    def remove_worktree(
        self, worktree_path: Path, force: bool = False
    ) -> tuple[bool, str]:
        """Remove a single worktree.

        Returns:
            (success, message) tuple.
        """
        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(worktree_path))

        output, code = self._run_git(*args)
        if code != 0:
            return False, output or f"Failed to remove worktree {worktree_path}"
        return True, f"Removed worktree {worktree_path}"

    def cleanup_batch(self, batch_id: str) -> int:
        """Remove all worktrees and branches for a batch.

        Returns:
            Number of worktrees cleaned up.
        """
        cleaned = 0
        worktrees = self.list_worktrees()

        for wt in worktrees:
            if wt.branch.startswith(f"parallel/{batch_id}/"):
                success, _ = self.remove_worktree(wt.path, force=True)
                if success:
                    self.delete_branch(wt.branch)
                    cleaned += 1

        # Prune stale worktree references
        self._run_git("worktree", "prune")

        # Clean up empty batch directory
        batch_dir = self._worktree_root
        if batch_dir.exists() and not any(batch_dir.iterdir()):
            try:
                batch_dir.rmdir()
            except OSError:
                pass

        return cleaned

    def cleanup_orphans(self) -> int:
        """Remove all cantina-managed worktrees and their branches.

        Call on startup to clean up after crashes. Returns count cleaned.
        """
        cleaned = 0
        worktrees = self.list_worktrees()
        for wt in worktrees:
            success, _ = self.remove_worktree(wt.path, force=True)
            if success:
                self.delete_branch(wt.branch)
                cleaned += 1
        self._run_git("worktree", "prune")
        return cleaned

    def estimate_disk_usage(self, task_count: int) -> int:
        """Estimate disk usage in bytes for N worktrees.

        Git worktrees share the object store so they are lightweight.
        The estimate is based on the working tree size.
        """
        # Approximate: get size of tracked files
        output, code = self._run_git(
            "ls-files", "-z", "--cached",
        )
        if code != 0:
            return 0

        total_bytes = 0
        for filepath in output.split("\0"):
            if not filepath:
                continue
            full = self.project_path / filepath
            try:
                total_bytes += full.stat().st_size
            except OSError:
                continue

        return total_bytes * task_count

    def merge_branch(
        self, branch: str, into: str = "HEAD"
    ) -> tuple[bool, str, list[str]]:
        """Merge a branch into the current branch (or specified target).

        Returns:
            (success, message, conflict_files) tuple.
        """
        # First check out the target if it's not HEAD
        if into != "HEAD":
            output, code = self._run_git("checkout", into)
            if code != 0:
                return False, f"Failed to checkout {into}: {output}", []

        output, code = self._run_git("merge", "--no-ff", branch, timeout=120)
        if code != 0:
            # Check for merge conflicts
            conflict_output, _ = self._run_git("diff", "--name-only", "--diff-filter=U")
            conflict_files = [
                f for f in conflict_output.split("\n") if f.strip()
            ]
            if conflict_files:
                # Abort the merge so caller can handle conflicts
                self._run_git("merge", "--abort")
                return (
                    False,
                    f"Merge conflicts in {len(conflict_files)} file(s)",
                    conflict_files,
                )
            return False, output or "Merge failed", []

        return True, f"Merged {branch} successfully", []

    def delete_branch(self, branch: str) -> bool:
        """Delete a local branch."""
        _, code = self._run_git("branch", "-D", branch)
        return code == 0

    def is_working_tree_clean(self) -> bool:
        """Check if the working tree has no uncommitted tracked changes.

        Only considers modified, staged, and deleted tracked files.
        Untracked files are ignored — they don't affect worktree operations.
        """
        output, code = self._run_git("status", "--porcelain", "--untracked-files=no")
        if code != 0:
            return False
        for line in output.split("\n"):
            if not line.strip():
                continue
            return False
        return True

    def get_dirty_files(self) -> list[str]:
        """Return list of dirty tracked files (modified, staged, deleted)."""
        output, code = self._run_git("status", "--porcelain", "--untracked-files=no")
        if code != 0:
            return []
        files = []
        for line in output.split("\n"):
            if not line.strip():
                continue
            # Format: "XY filename" — extract filename after status codes
            files.append(line[3:].strip())
        return files

    def stage_all(self) -> bool:
        """Stage all changes including untracked files."""
        _, code = self._run_git("add", "-A")
        return code == 0

    def stage_files(self, paths: list[str]) -> bool:
        """Stage specific files by path."""
        if not paths:
            return True
        _, code = self._run_git("add", "--", *paths)
        return code == 0

    def commit(self, message: str) -> tuple[bool, str]:
        """Create a commit with the given message. Returns (success, sha_or_error)."""
        _, code = self._run_git("commit", "-m", message)
        if code != 0:
            return False, "Nothing to commit or commit failed"
        sha, _ = self._run_git("rev-parse", "HEAD")
        return True, sha

    def get_current_branch(self) -> str:
        """Get the current branch name."""
        output, _ = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        return output or "unknown"

    def get_head_sha(self) -> str:
        """Get the current HEAD commit SHA."""
        output, _ = self._run_git("rev-parse", "HEAD")
        return output or ""
