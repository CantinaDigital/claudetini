"""Audit log for dispatch policy overrides."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from ..utils import parse_iso
from .runtime import project_runtime_dir

OverrideType = Literal["gate", "budget", "prompt_secret"]


@dataclass(frozen=True)
class DispatchOverrideEvent:
    """Single override event for dispatch policy enforcement."""

    event_id: str
    timestamp: datetime
    override_type: OverrideType
    reason: str
    session_id: str | None
    metadata: dict

    @classmethod
    def from_dict(cls, data: dict) -> DispatchOverrideEvent:
        return cls(
            event_id=str(data.get("event_id") or f"override-{uuid.uuid4().hex[:10]}"),
            timestamp=parse_iso(data.get("timestamp")) or datetime.now(),
            override_type=str(data.get("override_type", "gate")),  # type: ignore[arg-type]
            reason=str(data.get("reason", "")),
            session_id=data.get("session_id"),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "override_type": self.override_type,
            "reason": self.reason,
            "session_id": self.session_id,
            "metadata": self.metadata,
        }


class DispatchAuditStore:
    """Project-scoped append-only audit log for override events."""

    def __init__(self, project_id: str, base_dir: Path | None = None):
        self.project_dir = project_runtime_dir(project_id, base_dir=base_dir)
        self.path = self.project_dir / "dispatch-audit.jsonl"

    def log_override(
        self,
        override_type: OverrideType,
        reason: str,
        session_id: str | None,
        metadata: dict | None = None,
    ) -> DispatchOverrideEvent:
        event = DispatchOverrideEvent(
            event_id=f"override-{uuid.uuid4().hex[:12]}",
            timestamp=datetime.now(),
            override_type=override_type,
            reason=reason.strip(),
            session_id=session_id,
            metadata=metadata or {},
        )
        self._append(event)
        return event

    def recent(self, limit: int = 200) -> list[DispatchOverrideEvent]:
        if not self.path.exists():
            return []
        events: list[DispatchOverrideEvent] = []
        try:
            with open(self.path) as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        events.append(DispatchOverrideEvent.from_dict(json.loads(line)))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
        return events[-limit:]

    def _append(self, event: DispatchOverrideEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.path, "a") as handle:
                handle.write(json.dumps(event.to_dict()) + "\n")
        except OSError:
            return

