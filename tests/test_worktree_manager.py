"""Tests for git worktree lifecycle management."""

import subprocess
from pathlib import Path

import pytest

from src.core.worktree_manager import WorktreeManager, WorktreeInfo, WORKTREE_DIR_NAME


@pytest.fixture
def git_repo(tmp_path):
    """Create a real git repository with an initial commit."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path, capture_output=True,
    )
    readme = tmp_path / "README.md"
    readme.write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path, capture_output=True,
    )
    return tmp_path


class TestWorktreeManager:
    """Tests for WorktreeManager class."""

    def test_init_validates_repo(self, tmp_path):
        """Refuse to initialize on a non-git directory."""
        with pytest.raises(ValueError, match="Not a git repository"):
            WorktreeManager(tmp_path)

    def test_init_succeeds_on_git_repo(self, git_repo):
        """Successfully initialize on a valid git repo."""
        wm = WorktreeManager(git_repo)
        assert wm.project_path == git_repo.resolve()

    def test_create_worktree(self, git_repo):
        """Create a worktree and verify its properties."""
        wm = WorktreeManager(git_repo)
        info = wm.create_worktree("batch-1", 0)

        assert info.path.exists()
        assert info.branch == "parallel/batch-1/0"
        assert info.task_index == 0
        assert info.status == "active"

        # Check that the worktree is under .cantina-worktrees/
        assert WORKTREE_DIR_NAME in str(info.path)

    def test_create_multiple_worktrees(self, git_repo):
        """Create multiple worktrees in the same batch."""
        wm = WorktreeManager(git_repo)
        info0 = wm.create_worktree("batch-2", 0)
        info1 = wm.create_worktree("batch-2", 1)

        assert info0.path != info1.path
        assert info0.branch != info1.branch
        assert info0.path.exists()
        assert info1.path.exists()

    def test_list_worktrees(self, git_repo):
        """List returns only cantina-managed worktrees."""
        wm = WorktreeManager(git_repo)
        wm.create_worktree("batch-3", 0)
        wm.create_worktree("batch-3", 1)

        worktrees = wm.list_worktrees()
        assert len(worktrees) == 2
        branches = {wt.branch for wt in worktrees}
        assert "parallel/batch-3/0" in branches
        assert "parallel/batch-3/1" in branches

    def test_remove_worktree(self, git_repo):
        """Remove a single worktree."""
        wm = WorktreeManager(git_repo)
        info = wm.create_worktree("batch-4", 0)

        assert info.path.exists()
        success, msg = wm.remove_worktree(info.path)
        assert success
        assert not info.path.exists()

    def test_cleanup_batch(self, git_repo):
        """Clean up all worktrees for a batch."""
        wm = WorktreeManager(git_repo)
        wm.create_worktree("batch-5", 0)
        wm.create_worktree("batch-5", 1)
        wm.create_worktree("batch-5", 2)

        count = wm.cleanup_batch("batch-5")
        assert count == 3

        # Verify all are gone
        worktrees = wm.list_worktrees()
        remaining = [wt for wt in worktrees if "batch-5" in wt.branch]
        assert len(remaining) == 0

    def test_gitignore_entry_added(self, git_repo):
        """Creating a worktree adds the directory to .gitignore."""
        wm = WorktreeManager(git_repo)
        wm.create_worktree("batch-6", 0)

        gitignore = git_repo / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text()
        assert WORKTREE_DIR_NAME in content

    def test_gitignore_not_duplicated(self, git_repo):
        """Don't add duplicate .gitignore entries."""
        wm = WorktreeManager(git_repo)
        wm.create_worktree("batch-7", 0)
        wm.create_worktree("batch-7", 1)

        gitignore = git_repo / ".gitignore"
        content = gitignore.read_text()
        assert content.count(WORKTREE_DIR_NAME) == 1

    def test_is_working_tree_clean(self, git_repo):
        """Working tree clean check — only tracked file modifications count."""
        wm = WorktreeManager(git_repo)
        assert wm.is_working_tree_clean()

        # Untracked files should NOT make it dirty
        (git_repo / "untracked.txt").write_text("hello")
        assert wm.is_working_tree_clean()

        # Modifying a tracked file SHOULD make it dirty
        (git_repo / "README.md").write_text("# Modified\n")
        assert not wm.is_working_tree_clean()

    def test_get_current_branch(self, git_repo):
        """Get the current branch name."""
        wm = WorktreeManager(git_repo)
        branch = wm.get_current_branch()
        assert branch in ("main", "master")

    def test_get_head_sha(self, git_repo):
        """Get the HEAD SHA."""
        wm = WorktreeManager(git_repo)
        sha = wm.get_head_sha()
        assert len(sha) == 40  # Full SHA

    def test_merge_branch_success(self, git_repo):
        """Merge a branch cleanly."""
        wm = WorktreeManager(git_repo)
        info = wm.create_worktree("batch-8", 0)

        # Make a change in the worktree
        (info.path / "new_file.txt").write_text("from worktree")
        subprocess.run(["git", "add", "."], cwd=info.path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Add file from worktree"],
            cwd=info.path, capture_output=True,
        )

        # Remove worktree first (can't merge while it's checked out)
        wm.remove_worktree(info.path, force=True)

        # Merge
        success, msg, conflicts = wm.merge_branch(info.branch)
        assert success
        assert len(conflicts) == 0
        assert (git_repo / "new_file.txt").exists()

    def test_delete_branch(self, git_repo):
        """Delete a local branch."""
        wm = WorktreeManager(git_repo)

        # Create a branch
        subprocess.run(
            ["git", "branch", "test-branch"],
            cwd=git_repo, capture_output=True,
        )

        result = wm.delete_branch("test-branch")
        assert result is True

    def test_estimate_disk_usage(self, git_repo):
        """Estimate disk usage returns a non-negative value."""
        wm = WorktreeManager(git_repo)
        estimate = wm.estimate_disk_usage(3)
        assert estimate >= 0

    def test_full_worktree_lifecycle(self, git_repo):
        """End-to-end: create worktree, write files, commit, remove, merge, verify."""
        wm = WorktreeManager(git_repo)
        original_branch = wm.get_current_branch()

        # Create worktree
        info = wm.create_worktree("lifecycle-1", 0)
        assert info.path.exists()

        # Write multiple files in the worktree (simulating an agent)
        (info.path / "module_a.py").write_text("def hello(): return 'world'\n")
        (info.path / "module_b.py").write_text("VALUE = 42\n")
        subdir = info.path / "sub"
        subdir.mkdir()
        (subdir / "nested.py").write_text("NESTED = True\n")

        # Commit inside worktree
        subprocess.run(["git", "add", "-A"], cwd=info.path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Agent wrote files"],
            cwd=info.path, capture_output=True,
        )

        # Verify commit exists on the worktree branch
        log_result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=info.path, capture_output=True, text=True,
        )
        assert "Agent wrote files" in log_result.stdout

        # Remove worktree
        wm.remove_worktree(info.path, force=True)
        assert not info.path.exists()

        # Merge branch back
        success, msg, conflicts = wm.merge_branch(info.branch, into=original_branch)
        assert success, f"Merge failed: {msg}"
        assert len(conflicts) == 0

        # Verify files landed in the main repo
        assert (git_repo / "module_a.py").exists()
        assert (git_repo / "module_b.py").exists()
        assert (git_repo / "sub" / "nested.py").exists()
        assert (git_repo / "module_a.py").read_text() == "def hello(): return 'world'\n"

        # Clean up branch
        wm.delete_branch(info.branch)

    def test_worktree_without_commit_loses_work(self, git_repo):
        """Demonstrate the bug: removing a worktree without committing destroys changes."""
        wm = WorktreeManager(git_repo)
        original_branch = wm.get_current_branch()

        info = wm.create_worktree("nocommit-1", 0)

        # Write files but do NOT commit
        (info.path / "lost_file.py").write_text("this will be lost\n")

        # Remove worktree (destroys uncommitted files)
        wm.remove_worktree(info.path, force=True)

        # Merge — nothing to merge since no commits on branch
        success, msg, conflicts = wm.merge_branch(info.branch, into=original_branch)
        # "Success" but no files — that's the bug
        assert success
        assert not (git_repo / "lost_file.py").exists(), "File should NOT exist (no commit)"

        wm.delete_branch(info.branch)

    def test_parallel_worktrees_merge_independently(self, git_repo):
        """Two worktrees writing different files merge cleanly."""
        wm = WorktreeManager(git_repo)
        original_branch = wm.get_current_branch()
        base_sha = wm.get_head_sha()

        # Create two worktrees from same base
        wt_a = wm.create_worktree("parallel-merge", 0, base_ref=base_sha)
        wt_b = wm.create_worktree("parallel-merge", 1, base_ref=base_sha)

        # Agent A writes file_a.py
        (wt_a.path / "file_a.py").write_text("AGENT_A = True\n")
        subprocess.run(["git", "add", "-A"], cwd=wt_a.path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Agent A work"],
            cwd=wt_a.path, capture_output=True,
        )

        # Agent B writes file_b.py
        (wt_b.path / "file_b.py").write_text("AGENT_B = True\n")
        subprocess.run(["git", "add", "-A"], cwd=wt_b.path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Agent B work"],
            cwd=wt_b.path, capture_output=True,
        )

        # Remove and merge A
        wm.remove_worktree(wt_a.path, force=True)
        success_a, _, conflicts_a = wm.merge_branch(wt_a.branch, into=original_branch)
        assert success_a and len(conflicts_a) == 0
        wm.delete_branch(wt_a.branch)

        # Remove and merge B
        wm.remove_worktree(wt_b.path, force=True)
        success_b, _, conflicts_b = wm.merge_branch(wt_b.branch, into=original_branch)
        assert success_b and len(conflicts_b) == 0
        wm.delete_branch(wt_b.branch)

        # Both files should exist
        assert (git_repo / "file_a.py").exists()
        assert (git_repo / "file_b.py").exists()

    def test_parallel_worktrees_conflict_detection(self, git_repo):
        """Two worktrees modifying the same file produces a merge conflict."""
        wm = WorktreeManager(git_repo)
        original_branch = wm.get_current_branch()
        base_sha = wm.get_head_sha()

        wt_a = wm.create_worktree("conflict-test", 0, base_ref=base_sha)
        wt_b = wm.create_worktree("conflict-test", 1, base_ref=base_sha)

        # Both agents modify README.md
        (wt_a.path / "README.md").write_text("# Agent A was here\n")
        subprocess.run(["git", "add", "-A"], cwd=wt_a.path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Agent A modifies README"],
            cwd=wt_a.path, capture_output=True,
        )

        (wt_b.path / "README.md").write_text("# Agent B was here\n")
        subprocess.run(["git", "add", "-A"], cwd=wt_b.path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Agent B modifies README"],
            cwd=wt_b.path, capture_output=True,
        )

        # Merge A first — should succeed
        wm.remove_worktree(wt_a.path, force=True)
        success_a, _, _ = wm.merge_branch(wt_a.branch, into=original_branch)
        assert success_a
        wm.delete_branch(wt_a.branch)

        # Merge B — should conflict
        wm.remove_worktree(wt_b.path, force=True)
        success_b, msg_b, conflicts_b = wm.merge_branch(wt_b.branch, into=original_branch)
        assert not success_b
        assert len(conflicts_b) > 0
        assert "README.md" in conflicts_b
        wm.delete_branch(wt_b.branch)
