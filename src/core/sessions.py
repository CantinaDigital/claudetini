"""Session log and memory parsing."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class SessionSummary:
    """Parsed session summary from Claude Code's session memory."""

    session_id: str
    summary_text: str
    accomplishments: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    timestamp: datetime | None = None
    duration_minutes: int | None = None

    @classmethod
    def from_summary_file(cls, path: Path, session_id: str) -> "SessionSummary":
        """Parse a session summary from a summary.md file."""
        content = path.read_text()

        # Extract accomplishments (lines starting with - or *)
        accomplishments = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith(("-", "*")) and len(line) > 2:
                accomplishments.append(line[1:].strip())

        return cls(
            session_id=session_id,
            summary_text=content,
            accomplishments=accomplishments,
        )


@dataclass
class SessionLogEntry:
    """A single entry from a JSONL session log."""

    type: str  # e.g., "human", "assistant", "tool_use", "tool_result"
    content: str
    timestamp: datetime | None = None
    tool_name: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Session:
    """A parsed Claude Code session."""

    session_id: str
    project_hash: str
    log_path: Path
    memory_path: Path | None = None
    summary: SessionSummary | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None

    @property
    def duration_minutes(self) -> int | None:
        """Calculate session duration in minutes."""
        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
            return int(delta.total_seconds() / 60)
        return None


class SessionParser:
    """Parser for Claude Code session logs and memory."""

    def __init__(self, claude_dir: Path | None = None):
        self.claude_dir = claude_dir or Path.home() / ".claude"
        self.projects_dir = self.claude_dir / "projects"

    def find_sessions(self, project_hash: str) -> list[Session]:
        """Find all sessions for a project."""
        project_dir = self.projects_dir / project_hash
        if not project_dir.exists():
            return []

        sessions = []

        # Look for JSONL log files
        for log_file in project_dir.glob("*.jsonl"):
            session_id = log_file.stem

            # Check for corresponding session memory
            memory_dir = project_dir / session_id / "session-memory"
            summary_path = memory_dir / "summary.md"

            session = Session(
                session_id=session_id,
                project_hash=project_hash,
                log_path=log_file,
                memory_path=summary_path if summary_path.exists() else None,
            )

            # Parse summary if available
            if session.memory_path:
                try:
                    session.summary = SessionSummary.from_summary_file(
                        session.memory_path, session_id
                    )
                except Exception:
                    pass  # Summary parsing failed, continue without it

            # Try to get timestamps from log file
            timestamps = self._extract_timestamps(log_file)
            if timestamps:
                session.start_time = timestamps[0]
                session.end_time = timestamps[-1] if len(timestamps) > 1 else timestamps[0]

            sessions.append(session)

        # Sort by start time (most recent first)
        sessions.sort(key=lambda s: s.start_time or datetime.min, reverse=True)
        return sessions

    def _extract_timestamps(self, log_path: Path) -> list[datetime]:
        """Extract timestamps from a JSONL log file."""
        timestamps = []

        try:
            with open(log_path) as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if "timestamp" in entry:
                            ts = entry["timestamp"]
                            if isinstance(ts, str):
                                # Try to parse ISO format
                                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                                timestamps.append(dt)
                    except (json.JSONDecodeError, ValueError):
                        continue
        except Exception:
            pass

        return timestamps

    def parse_log_entries(self, log_path: Path, limit: int = 100) -> list[SessionLogEntry]:
        """Parse entries from a JSONL session log.

        Args:
            log_path: Path to the JSONL file
            limit: Maximum number of entries to parse (from end of file)
        """
        entries = []

        try:
            with open(log_path) as f:
                lines = f.readlines()
                # Take last N lines
                for line in lines[-limit:]:
                    try:
                        data = json.loads(line)
                        entry = SessionLogEntry(
                            type=data.get("type", "unknown"),
                            content=data.get("content", ""),
                            tool_name=data.get("tool_name"),
                            metadata=data,
                        )
                        if "timestamp" in data:
                            try:
                                entry.timestamp = datetime.fromisoformat(
                                    data["timestamp"].replace("Z", "+00:00")
                                )
                            except ValueError:
                                pass
                        entries.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass

        return entries

    def get_latest_session(self, project_hash: str) -> Session | None:
        """Get the most recent session for a project."""
        sessions = self.find_sessions(project_hash)
        return sessions[0] if sessions else None

    def get_session_count(self, project_hash: str) -> int:
        """Get the total number of sessions for a project."""
        return len(self.find_sessions(project_hash))
