"""Tests for smart scheduling, conflict detection, and dispatch queue."""

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.scheduling import (
    DispatchScheduler,
    QueuedDispatch,
    SchedulingConfig,
)


def _init_repo(path):
    """Initialize a git repository for testing."""
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-B", "main"], cwd=path, check=True, capture_output=True)
    # Create initial commit so git log works
    (path / "README.md").write_text("# Test")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=path,
        check=True,
        capture_output=True,
        env={"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@test.com",
             "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@test.com"},
    )


@pytest.fixture
def scheduler(temp_dir):
    """Create a DispatchScheduler for testing."""
    _init_repo(temp_dir)
    return DispatchScheduler(temp_dir, "test-proj", base_dir=temp_dir)


class TestSchedulingConfig:
    """Test SchedulingConfig dataclass."""

    def test_config_defaults(self):
        """Test default config values."""
        config = SchedulingConfig()

        assert config.detect_active_editing is True
        assert config.editing_cooldown_seconds == 30
        assert config.detect_manual_commits is True
        assert config.commit_cooldown_seconds == 300
        assert config.dnd_enabled is False
        assert config.auto_dispatch_on_clear is True

    def test_config_from_dict(self):
        """Test config deserialization."""
        data = {
            "detect_active_editing": False,
            "editing_cooldown_seconds": 60,
            "dnd_enabled": True,
        }

        config = SchedulingConfig.from_dict(data)

        assert config.detect_active_editing is False
        assert config.editing_cooldown_seconds == 60
        assert config.dnd_enabled is True

    def test_config_to_dict(self):
        """Test config serialization."""
        config = SchedulingConfig(dnd_enabled=True, editing_cooldown_seconds=45)

        data = config.to_dict()

        assert data["dnd_enabled"] is True
        assert data["editing_cooldown_seconds"] == 45


class TestQueuedDispatch:
    """Test QueuedDispatch dataclass."""

    def test_dispatch_from_dict(self):
        """Test dispatch deserialization."""
        data = {
            "dispatch_id": "abc123",
            "prompt": "Fix the bug",
            "roadmap_item": "Task 1",
            "queued_at": "2026-02-12T10:00:00",
            "reason": "dnd",
            "auto_dispatch": True,
        }

        dispatch = QueuedDispatch.from_dict(data)

        assert dispatch.dispatch_id == "abc123"
        assert dispatch.prompt == "Fix the bug"
        assert dispatch.reason == "dnd"

    def test_dispatch_to_dict(self):
        """Test dispatch serialization."""
        dispatch = QueuedDispatch(
            dispatch_id="xyz789",
            prompt="Add tests",
            roadmap_item="",
            queued_at=datetime(2026, 2, 12, 10, 0, 0),
            reason="active_editing",
            auto_dispatch=False,
        )

        data = dispatch.to_dict()

        assert data["dispatch_id"] == "xyz789"
        assert data["prompt"] == "Add tests"
        assert data["reason"] == "active_editing"
        assert data["auto_dispatch"] is False


class TestSchedulerConfigPersistence:
    """Test config persistence."""

    def test_load_config_default(self, scheduler):
        """Test loading default config."""
        config = scheduler.load_config()

        assert isinstance(config, SchedulingConfig)
        assert config.dnd_enabled is False

    def test_save_and_load_config(self, scheduler):
        """Test saving and loading config."""
        config = SchedulingConfig(dnd_enabled=True, editing_cooldown_seconds=60)
        scheduler.save_config(config)

        loaded = scheduler.load_config()

        assert loaded.dnd_enabled is True
        assert loaded.editing_cooldown_seconds == 60

    def test_load_config_handles_corruption(self, scheduler):
        """Test loading handles corrupt config file."""
        scheduler.config_file.write_text("not valid json")

        config = scheduler.load_config()

        # Should return defaults
        assert isinstance(config, SchedulingConfig)


class TestQueueManagement:
    """Test dispatch queue management."""

    def test_enqueue_creates_dispatch(self, scheduler):
        """Test enqueue creates a dispatch item."""
        item = scheduler.enqueue(
            prompt="Implement feature",
            reason="dnd",
            roadmap_item="Phase 1, Item 3",
        )

        assert item.dispatch_id
        assert item.prompt == "Implement feature"
        assert item.reason == "dnd"

    def test_load_queue_empty(self, scheduler):
        """Test loading empty queue."""
        queue = scheduler.load_queue()

        assert queue == []

    def test_load_queue_after_enqueue(self, scheduler):
        """Test loading queue after enqueue."""
        scheduler.enqueue(prompt="Task 1", reason="dnd")
        scheduler.enqueue(prompt="Task 2", reason="active_editing")

        queue = scheduler.load_queue()

        assert len(queue) == 2
        assert queue[0].prompt == "Task 1"
        assert queue[1].prompt == "Task 2"

    def test_remove_dispatch(self, scheduler):
        """Test removing dispatch from queue."""
        item = scheduler.enqueue(prompt="To remove", reason="dnd")

        result = scheduler.remove(item.dispatch_id)

        assert result is True
        assert scheduler.load_queue() == []

    def test_remove_nonexistent_dispatch(self, scheduler):
        """Test removing nonexistent dispatch."""
        result = scheduler.remove("nonexistent-id")

        assert result is False

    def test_pop_next(self, scheduler):
        """Test popping next dispatch."""
        scheduler.enqueue(prompt="First", reason="dnd")
        scheduler.enqueue(prompt="Second", reason="dnd")

        item = scheduler.pop_next()

        assert item.prompt == "First"
        assert len(scheduler.load_queue()) == 1

    def test_pop_next_empty_queue(self, scheduler):
        """Test popping from empty queue."""
        item = scheduler.pop_next()

        assert item is None

    def test_queue_limit_enforced(self, scheduler):
        """Test queue respects size limit."""
        for i in range(350):
            scheduler.enqueue(prompt=f"Task {i}", reason="dnd")

        queue = scheduler.load_queue()

        # Should be limited to 300
        assert len(queue) <= 300


class TestConflictDetection:
    """Test conflict detection."""

    def test_should_queue_dnd(self, scheduler):
        """Test DND triggers queueing."""
        scheduler.set_dnd(True)

        reason = scheduler.should_queue()

        assert reason == "dnd"

    def test_should_queue_no_conflicts(self, scheduler):
        """Test no queueing without conflicts."""
        # Disable conflict detection since our fixture creates recent files and commits
        config = SchedulingConfig(detect_manual_commits=False, detect_active_editing=False)
        scheduler.save_config(config)

        reason = scheduler.should_queue()

        assert reason is None

    def test_detect_active_editing(self, scheduler, temp_dir):
        """Test detecting recently modified files."""
        # Create a recently modified file
        test_file = temp_dir / "src" / "app.py"
        test_file.parent.mkdir(exist_ok=True)
        test_file.write_text("print('hello')")

        conflicts = scheduler.detect_active_editing(["src/app.py"])

        # File was just created, should be detected
        assert "src/app.py" in conflicts

    def test_detect_active_editing_old_file(self, scheduler, temp_dir):
        """Test old files not detected as active editing."""
        # Create file and wait for cooldown
        test_file = temp_dir / "old.py"
        test_file.write_text("print('old')")

        # Mock time to make file appear old
        with patch("time.time", return_value=time.time() + 60):
            conflicts = scheduler.detect_active_editing(["old.py"])

        assert conflicts == []

    def test_detect_active_editing_disabled(self, scheduler, temp_dir):
        """Test active editing detection can be disabled."""
        config = SchedulingConfig(detect_active_editing=False)
        scheduler.save_config(config)

        test_file = temp_dir / "new.py"
        test_file.write_text("print('new')")

        conflicts = scheduler.detect_active_editing(["new.py"])

        assert conflicts == []

    def test_detect_recent_manual_commit(self, scheduler, temp_dir):
        """Test detecting recent manual commit."""
        # Make a new commit
        (temp_dir / "new.py").write_text("print('new')")
        subprocess.run(["git", "add", "."], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "New commit"],
            cwd=temp_dir,
            check=True,
            capture_output=True,
            env={"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@test.com",
                 "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@test.com"},
        )

        has_recent = scheduler.has_recent_manual_commit()

        assert has_recent is True

    def test_detect_recent_manual_commit_disabled(self, scheduler):
        """Test manual commit detection can be disabled."""
        config = SchedulingConfig(detect_manual_commits=False)
        scheduler.save_config(config)

        has_recent = scheduler.has_recent_manual_commit()

        assert has_recent is False


class TestDndMode:
    """Test Do Not Disturb mode."""

    def test_set_dnd_enabled(self, scheduler):
        """Test enabling DND mode."""
        scheduler.set_dnd(True)

        config = scheduler.load_config()
        assert config.dnd_enabled is True

    def test_set_dnd_disabled(self, scheduler):
        """Test disabling DND mode."""
        scheduler.set_dnd(True)
        scheduler.set_dnd(False)

        config = scheduler.load_config()
        assert config.dnd_enabled is False


class TestAutoDispatch:
    """Test auto-dispatch functionality."""

    def test_next_dispatchable_returns_item(self, scheduler):
        """Test next_dispatchable returns item when conditions clear."""
        # Disable conflict detection since our fixture creates recent files and commits
        config = SchedulingConfig(
            detect_manual_commits=False,
            detect_active_editing=False,
            auto_dispatch_on_clear=True,
        )
        scheduler.save_config(config)

        scheduler.enqueue(prompt="Ready", reason="dnd", auto_dispatch=True)

        item = scheduler.next_dispatchable()

        assert item is not None
        assert item.prompt == "Ready"

    def test_next_dispatchable_respects_dnd(self, scheduler):
        """Test next_dispatchable respects DND."""
        scheduler.enqueue(prompt="Ready", reason="dnd", auto_dispatch=True)
        scheduler.set_dnd(True)

        item = scheduler.next_dispatchable()

        assert item is None

    def test_next_dispatchable_skips_manual(self, scheduler):
        """Test next_dispatchable skips non-auto items."""
        # Disable conflict detection since our fixture creates recent files and commits
        config = SchedulingConfig(
            detect_manual_commits=False,
            detect_active_editing=False,
            auto_dispatch_on_clear=True,
        )
        scheduler.save_config(config)

        scheduler.enqueue(prompt="Manual", reason="dnd", auto_dispatch=False)
        scheduler.enqueue(prompt="Auto", reason="dnd", auto_dispatch=True)

        item = scheduler.next_dispatchable()

        assert item is not None
        assert item.prompt == "Auto"

    def test_next_dispatchable_disabled(self, scheduler):
        """Test next_dispatchable when auto-dispatch disabled."""
        config = SchedulingConfig(auto_dispatch_on_clear=False)
        scheduler.save_config(config)
        scheduler.enqueue(prompt="Ready", reason="dnd", auto_dispatch=True)

        item = scheduler.next_dispatchable()

        assert item is None

    def test_next_dispatchable_empty_queue(self, scheduler):
        """Test next_dispatchable with empty queue."""
        item = scheduler.next_dispatchable()

        assert item is None
