"""Tests for git utilities."""

import pytest
from pathlib import Path
import subprocess

from src.core.git_utils import GitRepo, GitCommit, GitStatus


class TestGitRepo:
    """Tests for GitRepo class."""

    @pytest.fixture
    def git_repo(self, temp_dir):
        """Create a real git repository for testing."""
        # Initialize git repo
        subprocess.run(
            ["git", "init"],
            cwd=temp_dir,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=temp_dir,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=temp_dir,
            capture_output=True,
        )

        # Create initial commit
        readme = temp_dir / "README.md"
        readme.write_text("# Test\n")
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=temp_dir,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=temp_dir,
            capture_output=True,
        )

        return GitRepo(temp_dir)

    def test_is_git_repo(self, git_repo):
        """Test git repo detection."""
        assert GitRepo.is_git_repo(git_repo.path) is True

    def test_is_not_git_repo(self, temp_dir):
        """Test non-git directory detection."""
        assert GitRepo.is_git_repo(temp_dir) is False

    def test_get_current_branch(self, git_repo):
        """Test getting current branch."""
        branch = git_repo.get_current_branch()
        # Could be 'main' or 'master' depending on git config
        assert branch in ("main", "master")

    def test_get_status_clean(self, git_repo):
        """Test status on clean repo."""
        status = git_repo.get_status()

        assert isinstance(status, GitStatus)
        assert status.has_uncommitted_changes is False
        assert len(status.modified_files) == 0

    def test_get_status_with_changes(self, git_repo):
        """Test status with modified files."""
        # Modify a file
        readme = git_repo.path / "README.md"
        readme.write_text("# Modified\n")

        status = git_repo.get_status()

        assert status.has_uncommitted_changes is True
        assert "README.md" in status.modified_files

    def test_get_status_with_untracked(self, git_repo):
        """Test status with untracked files."""
        # Create new file
        new_file = git_repo.path / "new_file.txt"
        new_file.write_text("New content\n")

        status = git_repo.get_status()

        assert "new_file.txt" in status.untracked_files

    def test_get_recent_commits(self, git_repo):
        """Test getting recent commits."""
        commits = git_repo.get_recent_commits(10)

        assert len(commits) == 1
        assert commits[0].message == "Initial commit"
        assert commits[0].author == "Test User"

    def test_has_gitignore(self, git_repo):
        """Test gitignore detection."""
        assert git_repo.has_gitignore() is False

        # Create .gitignore
        gitignore = git_repo.path / ".gitignore"
        gitignore.write_text("*.pyc\n")

        assert git_repo.has_gitignore() is True

    def test_invalid_repo_raises(self, temp_dir):
        """Test that invalid repo raises ValueError."""
        with pytest.raises(ValueError, match="Not a git repository"):
            GitRepo(temp_dir)


class TestGitCommit:
    """Tests for GitCommit class."""

    def test_short_sha(self):
        """Test short SHA generation."""
        commit = GitCommit(
            sha="abc123def456789",
            message="Test commit",
            author="Test",
            timestamp=None,
        )

        assert commit.short_sha == "abc123d"

    def test_first_line(self):
        """Test first line extraction from multi-line message."""
        commit = GitCommit(
            sha="abc123",
            message="First line\n\nMore details here",
            author="Test",
            timestamp=None,
        )

        assert commit.first_line == "First line"


class TestGitStatus:
    """Tests for GitStatus class."""

    def test_has_uncommitted_changes_staged(self):
        """Test uncommitted changes with staged files."""
        status = GitStatus(
            branch="main",
            staged_files=["file.py"],
            modified_files=[],
        )

        assert status.has_uncommitted_changes is True

    def test_has_uncommitted_changes_modified(self):
        """Test uncommitted changes with modified files."""
        status = GitStatus(
            branch="main",
            staged_files=[],
            modified_files=["file.py"],
        )

        assert status.has_uncommitted_changes is True

    def test_no_uncommitted_changes(self):
        """Test clean status."""
        status = GitStatus(
            branch="main",
            staged_files=[],
            modified_files=[],
        )

        assert status.has_uncommitted_changes is False

    def test_total_changed_files(self):
        """Test total changed files count."""
        status = GitStatus(
            branch="main",
            staged_files=["a.py", "b.py"],
            modified_files=["c.py"],
        )

        assert status.total_changed_files == 3
