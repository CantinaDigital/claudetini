"""Smart scheduling, conflict detection, and dispatch queue."""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..utils import parse_iso
from .runtime import project_runtime_dir


@dataclass
class SchedulingConfig:
    """Per-project scheduling controls."""

    detect_active_editing: bool = True
    editing_cooldown_seconds: int = 30
    detect_manual_commits: bool = True
    commit_cooldown_seconds: int = 300
    dnd_enabled: bool = False
    auto_dispatch_on_clear: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> SchedulingConfig:
        return cls(
            detect_active_editing=bool(data.get("detect_active_editing", True)),
            editing_cooldown_seconds=int(data.get("editing_cooldown_seconds", 30) or 30),
            detect_manual_commits=bool(data.get("detect_manual_commits", True)),
            commit_cooldown_seconds=int(data.get("commit_cooldown_seconds", 300) or 300),
            dnd_enabled=bool(data.get("dnd_enabled", False)),
            auto_dispatch_on_clear=bool(data.get("auto_dispatch_on_clear", True)),
        )

    def to_dict(self) -> dict:
        return {
            "detect_active_editing": self.detect_active_editing,
            "editing_cooldown_seconds": self.editing_cooldown_seconds,
            "detect_manual_commits": self.detect_manual_commits,
            "commit_cooldown_seconds": self.commit_cooldown_seconds,
            "dnd_enabled": self.dnd_enabled,
            "auto_dispatch_on_clear": self.auto_dispatch_on_clear,
        }


@dataclass
class QueuedDispatch:
    """Deferred dispatch item."""

    dispatch_id: str
    prompt: str
    roadmap_item: str
    queued_at: datetime
    reason: str
    auto_dispatch: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> QueuedDispatch:
        return cls(
            dispatch_id=data.get("dispatch_id") or uuid.uuid4().hex[:10],
            prompt=data.get("prompt", ""),
            roadmap_item=data.get("roadmap_item", ""),
            queued_at=parse_iso(data.get("queued_at")) or datetime.now(),
            reason=data.get("reason", "unknown"),
            auto_dispatch=bool(data.get("auto_dispatch", True)),
        )

    def to_dict(self) -> dict:
        return {
            "dispatch_id": self.dispatch_id,
            "prompt": self.prompt,
            "roadmap_item": self.roadmap_item,
            "queued_at": self.queued_at.isoformat(),
            "reason": self.reason,
            "auto_dispatch": self.auto_dispatch,
        }


class DispatchScheduler:
    """Scheduling coordinator with queue persistence."""

    def __init__(self, project_path: Path, project_id: str, base_dir: Path | None = None):
        self.project_path = project_path.resolve()
        self.project_id = project_id
        self.project_dir = project_runtime_dir(project_id, base_dir=base_dir)
        self.config_file = self.project_dir / "scheduling.json"
        self.queue_file = self.project_dir / "dispatch-queue.json"

    def load_config(self) -> SchedulingConfig:
        if not self.config_file.exists():
            return SchedulingConfig()
        try:
            data = json.loads(self.config_file.read_text())
        except (json.JSONDecodeError, OSError):
            return SchedulingConfig()
        if not isinstance(data, dict):
            return SchedulingConfig()
        return SchedulingConfig.from_dict(data)

    def save_config(self, config: SchedulingConfig) -> None:
        self.config_file.write_text(json.dumps(config.to_dict(), indent=2))

    def detect_active_editing(self, scope_files: list[str]) -> list[str]:
        """Return files edited inside the active-editing cooldown window."""
        config = self.load_config()
        if not config.detect_active_editing:
            return []

        now = time.time()
        conflicts: list[str] = []
        for rel_path in scope_files:
            target = self.project_path / rel_path
            if not target.exists():
                continue
            try:
                age = now - target.stat().st_mtime
            except OSError:
                continue
            if age < config.editing_cooldown_seconds:
                conflicts.append(rel_path)
        return conflicts

    def has_recent_manual_commit(self) -> bool:
        config = self.load_config()
        if not config.detect_manual_commits:
            return False

        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct"],
            cwd=self.project_path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False

        try:
            latest_commit_ts = int(result.stdout.strip())
        except ValueError:
            return False

        return (time.time() - latest_commit_ts) < config.commit_cooldown_seconds

    def should_queue(self, scope_files: list[str] | None = None) -> str | None:
        config = self.load_config()
        if config.dnd_enabled:
            return "dnd"

        files = scope_files or self._repo_changed_files()
        if files and self.detect_active_editing(files):
            return "active_editing"

        if self.has_recent_manual_commit():
            return "recent_manual_commit"

        return None

    def enqueue(
        self,
        prompt: str,
        reason: str,
        roadmap_item: str = "",
        auto_dispatch: bool = True,
    ) -> QueuedDispatch:
        queue = self.load_queue()
        item = QueuedDispatch(
            dispatch_id=uuid.uuid4().hex[:10],
            prompt=prompt,
            roadmap_item=roadmap_item,
            queued_at=datetime.now(),
            reason=reason,
            auto_dispatch=auto_dispatch,
        )
        queue.append(item)
        self._save_queue(queue)
        return item

    def load_queue(self) -> list[QueuedDispatch]:
        if not self.queue_file.exists():
            return []
        try:
            raw = json.loads(self.queue_file.read_text())
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(raw, list):
            return []
        return [QueuedDispatch.from_dict(item) for item in raw]

    def remove(self, dispatch_id: str) -> bool:
        queue = self.load_queue()
        remaining = [item for item in queue if item.dispatch_id != dispatch_id]
        changed = len(remaining) != len(queue)
        if changed:
            self._save_queue(remaining)
        return changed

    def pop_next(self) -> QueuedDispatch | None:
        queue = self.load_queue()
        if not queue:
            return None
        item = queue.pop(0)
        self._save_queue(queue)
        return item

    def next_dispatchable(self) -> QueuedDispatch | None:
        config = self.load_config()
        if not config.auto_dispatch_on_clear:
            return None

        queue = self.load_queue()
        if not queue:
            return None

        reason = self.should_queue()
        if reason:
            return None

        for item in queue:
            if item.auto_dispatch:
                return item
        return None

    def set_dnd(self, enabled: bool) -> None:
        config = self.load_config()
        config.dnd_enabled = enabled
        self.save_config(config)

    def _save_queue(self, queue: list[QueuedDispatch]) -> None:
        payload = [item.to_dict() for item in queue]
        self.queue_file.write_text(json.dumps(payload[-300:], indent=2))

    def _repo_changed_files(self) -> list[str]:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self.project_path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []

        files: list[str] = []
        for line in result.stdout.splitlines():
            if len(line) < 4:
                continue
            rel_path = line[3:].strip()
            if rel_path:
                files.append(rel_path)
        return files


