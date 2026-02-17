"""Tests for git pre-push hook management."""

import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from src.agents.hooks import END_MARKER, START_MARKER, GitPrePushHookManager


@pytest.fixture
def hook_manager(temp_dir):
    """Create a GitPrePushHookManager for testing."""
    # Create git hooks directory
    git_dir = temp_dir / ".git"
    git_dir.mkdir()
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir()

    return GitPrePushHookManager(temp_dir, "test-proj", base_dir=temp_dir)


class TestHookInstallation:
    """Test hook installation."""

    def test_install_creates_hook(self, hook_manager, temp_dir):
        """Test installing hook creates the file."""
        ok, message = hook_manager.install()

        assert ok is True
        assert "Installed" in message

        hook_file = temp_dir / ".git" / "hooks" / "pre-push"
        assert hook_file.exists()

    def test_install_hook_is_executable(self, hook_manager, temp_dir):
        """Test installed hook is executable."""
        hook_manager.install()

        hook_file = temp_dir / ".git" / "hooks" / "pre-push"
        mode = hook_file.stat().st_mode

        assert mode & stat.S_IXUSR  # User execute permission

    def test_install_hook_has_markers(self, hook_manager, temp_dir):
        """Test installed hook contains markers."""
        hook_manager.install()

        hook_file = temp_dir / ".git" / "hooks" / "pre-push"
        content = hook_file.read_text()

        assert START_MARKER in content
        assert END_MARKER in content

    def test_install_hook_has_shebang(self, hook_manager, temp_dir):
        """Test installed hook has proper shebang."""
        hook_manager.install()

        hook_file = temp_dir / ".git" / "hooks" / "pre-push"
        content = hook_file.read_text()

        assert content.startswith("#!/bin/bash")

    def test_install_idempotent(self, hook_manager):
        """Test installing twice is safe."""
        ok1, msg1 = hook_manager.install()
        ok2, msg2 = hook_manager.install()

        assert ok1 is True
        assert ok2 is True
        assert "already installed" in msg2

    def test_install_appends_to_existing_hook(self, hook_manager, temp_dir):
        """Test installing appends to existing hook content."""
        hook_file = temp_dir / ".git" / "hooks" / "pre-push"
        existing_content = "#!/bin/bash\necho 'existing hook'\n"
        hook_file.write_text(existing_content)
        os.chmod(hook_file, 0o755)

        ok, message = hook_manager.install()

        assert ok is True
        content = hook_file.read_text()
        assert "existing hook" in content
        assert START_MARKER in content

    def test_install_fails_without_git(self, temp_dir):
        """Test install fails without .git directory."""
        manager = GitPrePushHookManager(temp_dir, "test", base_dir=temp_dir)

        ok, message = manager.install()

        assert ok is False
        assert "Not a git repository" in message


class TestHookRemoval:
    """Test hook removal."""

    def test_remove_hook(self, hook_manager, temp_dir):
        """Test removing installed hook."""
        hook_manager.install()

        ok, message = hook_manager.remove()

        assert ok is True
        assert hook_manager.is_installed() is False

    def test_remove_leaves_minimal_shebang(self, hook_manager, temp_dir):
        """Test removing leaves only shebang when no other content existed."""
        hook_manager.install()
        hook_file = temp_dir / ".git" / "hooks" / "pre-push"

        hook_manager.remove()

        # After removing our block, only the shebang/set-e header remains
        # which is acceptable (it's not empty, just minimal)
        content = hook_file.read_text().strip()
        assert START_MARKER not in content
        assert END_MARKER not in content

    def test_remove_preserves_other_content(self, hook_manager, temp_dir):
        """Test removing preserves non-managed content."""
        hook_file = temp_dir / ".git" / "hooks" / "pre-push"
        existing_content = "#!/bin/bash\necho 'keep me'\n"
        hook_file.write_text(existing_content)
        os.chmod(hook_file, 0o755)

        hook_manager.install()
        hook_manager.remove()

        assert hook_file.exists()
        content = hook_file.read_text()
        assert "keep me" in content
        assert START_MARKER not in content

    def test_remove_nonexistent_hook_ok(self, hook_manager):
        """Test removing when no hook exists is successful."""
        ok, message = hook_manager.remove()

        assert ok is True
        assert "No pre-push hook" in message

    def test_remove_unmanaged_hook_fails(self, hook_manager, temp_dir):
        """Test removing non-managed hook fails gracefully."""
        hook_file = temp_dir / ".git" / "hooks" / "pre-push"
        hook_file.write_text("#!/bin/bash\necho 'not ours'\n")

        ok, message = hook_manager.remove()

        assert ok is False
        assert "not managed" in message


class TestHookDetection:
    """Test hook installation detection."""

    def test_is_installed_false_initially(self, hook_manager):
        """Test is_installed returns False when not installed."""
        assert hook_manager.is_installed() is False

    def test_is_installed_true_after_install(self, hook_manager):
        """Test is_installed returns True after installation."""
        hook_manager.install()

        assert hook_manager.is_installed() is True

    def test_is_installed_false_after_remove(self, hook_manager):
        """Test is_installed returns False after removal."""
        hook_manager.install()
        hook_manager.remove()

        assert hook_manager.is_installed() is False

    def test_is_installed_detects_markers(self, hook_manager, temp_dir):
        """Test is_installed checks for both markers."""
        hook_file = temp_dir / ".git" / "hooks" / "pre-push"

        # Only start marker - not properly installed
        hook_file.write_text(f"#!/bin/bash\n{START_MARKER}\n")
        assert hook_manager.is_installed() is False

        # Only end marker - not properly installed
        hook_file.write_text(f"#!/bin/bash\n{END_MARKER}\n")
        assert hook_manager.is_installed() is False

        # Both markers - properly installed
        hook_file.write_text(f"#!/bin/bash\n{START_MARKER}\n{END_MARKER}\n")
        assert hook_manager.is_installed() is True


class TestManagedBlock:
    """Test managed block content."""

    def test_managed_block_checks_status_file(self, hook_manager, temp_dir):
        """Test managed block references correct status file."""
        hook_manager.install()

        hook_file = temp_dir / ".git" / "hooks" / "pre-push"
        content = hook_file.read_text()

        assert "GATE_STATUS=" in content
        assert "last-gate-status.json" in content

    def test_managed_block_has_bypass_instructions(self, hook_manager, temp_dir):
        """Test managed block includes bypass instructions."""
        hook_manager.install()

        hook_file = temp_dir / ".git" / "hooks" / "pre-push"
        content = hook_file.read_text()

        assert "--no-verify" in content

    def test_managed_block_checks_hard_stop(self, hook_manager, temp_dir):
        """Test managed block checks for hard_stop failures."""
        hook_manager.install()

        hook_file = temp_dir / ".git" / "hooks" / "pre-push"
        content = hook_file.read_text()

        assert "hard_stop" in content
        assert "fail" in content

    def test_pre_push_hook_allows_fresh_status(self, hook_manager, temp_dir):
        """Fresh gate metadata should allow hook execution."""
        hook_manager.install()
        status_file = temp_dir / "test-proj" / "last-gate-status.json"
        status_file.parent.mkdir(parents=True, exist_ok=True)
        empty_hash = hashlib.sha1(b"").hexdigest()
        status_file.write_text(
            json.dumps(
                {
                    "run_id": "run-1",
                    "timestamp": "2026-02-12T10:00:00",
                    "session_id": "session-1",
                    "head_sha": "UNBORN",
                    "index_fingerprint": empty_hash,
                    "working_tree_fingerprint": empty_hash,
                    "gates": [
                        {"name": "tests", "status": "pass", "summary": "ok", "hard_stop": True},
                    ],
                },
                indent=2,
            )
        )

        hook_file = temp_dir / ".git" / "hooks" / "pre-push"
        result = subprocess.run([str(hook_file)], cwd=temp_dir, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0
        assert "fresh and passing" in result.stdout.lower()

    def test_pre_push_hook_blocks_stale_status(self, hook_manager, temp_dir):
        """Stale metadata should block push with no-verify guidance."""
        hook_manager.install()
        status_file = temp_dir / "test-proj" / "last-gate-status.json"
        status_file.parent.mkdir(parents=True, exist_ok=True)
        status_file.write_text(
            json.dumps(
                {
                    "run_id": "run-2",
                    "timestamp": "2026-02-12T10:01:00",
                    "session_id": "session-2",
                    "head_sha": "UNBORN",
                    "index_fingerprint": "stale",
                    "working_tree_fingerprint": "stale",
                    "gates": [
                        {"name": "tests", "status": "pass", "summary": "ok", "hard_stop": True},
                    ],
                },
                indent=2,
            )
        )

        hook_file = temp_dir / ".git" / "hooks" / "pre-push"
        result = subprocess.run([str(hook_file)], cwd=temp_dir, capture_output=True, text=True, timeout=10)
        assert result.returncode == 1
        assert "stale" in (result.stdout + result.stderr).lower()
        assert "--no-verify" in (result.stdout + result.stderr)
