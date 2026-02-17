"""Prompt versioning and history storage."""

import fcntl
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .cost_tracker import DEFAULT_MODEL, TokenUsage
from .runtime import project_runtime_dir

logger = logging.getLogger(__name__)


@dataclass
class PromptVersion:
    """Single prompt version."""

    version: int
    prompt_text: str
    dispatched_at: datetime | None = None
    session_id: str | None = None
    outcome: str | None = None
    token_usage: TokenUsage | None = None
    notes: str | None = None


@dataclass
class PromptHistory:
    """Prompt version history for a roadmap item."""

    roadmap_item: str
    versions: list[PromptVersion] = field(default_factory=list)


class PromptHistoryStore:
    """Persist prompt history per project with concurrent-safe file access."""

    def __init__(self, project_id: str, base_dir: Path | None = None):
        self.project_dir = project_runtime_dir(project_id, base_dir=base_dir)
        self.path = self.project_dir / "prompt-history.json"

    def add_version(self, roadmap_item: str, prompt_text: str, notes: str | None = None) -> PromptVersion:
        """Create and store a new prompt version."""
        data = self._load_raw()
        versions = data.setdefault(roadmap_item, [])
        version_number = int(versions[-1]["version"]) + 1 if versions else 1
        record = {
            "version": version_number,
            "prompt_text": prompt_text,
            "dispatched_at": None,
            "session_id": None,
            "outcome": None,
            "token_usage": None,
            "notes": notes,
        }
        versions.append(record)
        self._save_raw(data)
        return PromptVersion(version=version_number, prompt_text=prompt_text, notes=notes)

    def mark_dispatched(
        self,
        roadmap_item: str,
        version: int,
        session_id: str | None = None,
    ) -> None:
        """Mark an existing prompt version as dispatched."""
        data = self._load_raw()
        for item in data.get(roadmap_item, []):
            if int(item.get("version", 0)) != version:
                continue
            item["dispatched_at"] = datetime.now().isoformat()
            item["session_id"] = session_id
            break
        self._save_raw(data)

    def mark_outcome(
        self,
        roadmap_item: str,
        version: int,
        outcome: str,
        usage: TokenUsage | None = None,
        notes: str | None = None,
    ) -> None:
        """Store outcome and optional usage for a version."""
        data = self._load_raw()
        for item in data.get(roadmap_item, []):
            if int(item.get("version", 0)) != version:
                continue
            item["outcome"] = outcome
            if usage:
                item["token_usage"] = {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "model": usage.model,
                }
            if notes:
                item["notes"] = notes
            break
        self._save_raw(data)

    def get_history(self, roadmap_item: str) -> PromptHistory:
        """Get prompt history for item."""
        data = self._load_raw().get(roadmap_item, [])
        versions = []
        for row in data:
            usage = None
            if row.get("token_usage"):
                usage = TokenUsage(
                    input_tokens=int(row["token_usage"].get("input_tokens", 0)),
                    output_tokens=int(row["token_usage"].get("output_tokens", 0)),
                    model=row["token_usage"].get("model", DEFAULT_MODEL),
                )
            versions.append(
                PromptVersion(
                    version=int(row["version"]),
                    prompt_text=row["prompt_text"],
                    dispatched_at=_parse_datetime(row.get("dispatched_at")),
                    session_id=row.get("session_id"),
                    outcome=row.get("outcome"),
                    token_usage=usage,
                    notes=row.get("notes"),
                )
            )
        return PromptHistory(roadmap_item=roadmap_item, versions=versions)

    def mark_outcome_for_session(
        self,
        session_id: str,
        outcome: str,
        usage: TokenUsage | None = None,
        notes: str | None = None,
    ) -> bool:
        """Mark outcome for the most recent prompt version tied to session_id."""
        data = self._load_raw()
        target_key: str | None = None
        target_version = -1

        for roadmap_item, entries in data.items():
            if not isinstance(entries, list):
                continue
            for item in entries:
                if item.get("session_id") != session_id:
                    continue
                version = int(item.get("version", 0) or 0)
                if version >= target_version:
                    target_key = str(roadmap_item)
                    target_version = version

        if not target_key or target_version < 1:
            return False

        self.mark_outcome(
            roadmap_item=target_key,
            version=target_version,
            outcome=outcome,
            usage=usage,
            notes=notes,
        )
        return True

    def _load_raw(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            with open(self.path) as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    data = json.loads(f.read())
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load prompt history: %s", e)
            return {}
        return data if isinstance(data, dict) else {}

    def _save_raw(self, data: dict) -> None:
        try:
            with open(self.path, "w") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.write(json.dumps(data, indent=2))
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError as e:
            logger.warning("Failed to save prompt history: %s", e)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
