"""
Live Sessions API routes

Detects and returns information about actively running Claude Code sessions.
Supports multiple simultaneous sessions.
"""

import json
import logging
import hashlib
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

# Claude Code data directory
CLAUDE_HOME = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_HOME / "projects"

# Activity timeout: how recently a session file must have been modified
# to be considered "active". 120s is generous enough to survive long
# thinking pauses, context window operations, and slow tool calls.
ACTIVITY_TIMEOUT_SECONDS = 120


class Exchange(BaseModel):
    """A single conversation exchange in a live session."""
    time: str
    type: str  # "user" or "assistant"
    summary: str
    files: list[str] = []
    lines: Optional[str] = None


class LiveSession(BaseModel):
    """Information about an active Claude Code session."""
    active: bool
    session_id: Optional[str] = None
    provider: str = "claude"
    pid: Optional[int] = None
    started_at: Optional[str] = None
    elapsed: Optional[str] = None
    estimated_cost: Optional[str] = None
    tokens_used: int = 0
    files_modified: list[str] = []
    lines_added: int = 0
    lines_removed: int = 0


class LiveSessionResponse(BaseModel):
    """Response for live session endpoint."""
    active: bool
    sessions: list[LiveSession] = []
    exchanges: list[Exchange] = []
    # Backward compat: single session shortcut
    session: Optional[LiveSession] = None


def _get_project_hash(project_path: str) -> str:
    """Generate hash for project path (matches Claude Code's hashing)."""
    # Claude Code uses a simple hash of the project path
    return hashlib.md5(project_path.encode()).hexdigest()[:8]


def _find_project_dir(project_path: str) -> Optional[Path]:
    """Find the Claude Code project directory for a given project path."""
    if not PROJECTS_DIR.exists():
        return None

    # Normalize: strip trailing slashes, ensure consistent format
    normalized = project_path.rstrip("/").rstrip("\\")
    sanitized = normalized.replace("/", "-").replace("\\", "-").lstrip("-")
    # Claude Code names directories like "-Users-username-project"
    expected_name = "-" + sanitized

    try:
        # Try exact match first (most reliable)
        exact = PROJECTS_DIR / expected_name
        if exact.is_dir():
            return exact

        # Fallback: find the best substring match (shortest name wins to avoid
        # matching child directories like "project-app" when looking for "project")
        best: Optional[Path] = None
        for project_dir in PROJECTS_DIR.iterdir():
            if not project_dir.is_dir():
                continue
            if sanitized in project_dir.name:
                if best is None or len(project_dir.name) < len(best.name):
                    best = project_dir
        return best
    except OSError as exc:
        logger.warning("Failed to scan Claude project directories: %s", exc)
        return None


def _parse_jsonl_entry(line: str) -> Optional[dict]:
    """Parse a JSONL entry."""
    try:
        return json.loads(line.strip())
    except (json.JSONDecodeError, ValueError):
        return None


def _format_elapsed(start_time: datetime) -> str:
    """Format elapsed time since start."""
    elapsed = datetime.now(timezone.utc) - start_time
    total_seconds = int(elapsed.total_seconds())

    if total_seconds < 60:
        return f"{total_seconds}s"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}m {seconds}s"
    else:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours}h {minutes}m"


def _is_session_active(session_file: Path) -> bool:
    """
    Check if a session file is actively being written to.
    A session is considered active if:
    1. The file was modified within ACTIVITY_TIMEOUT_SECONDS
    2. No summary.md exists for this session (session hasn't ended)
    """
    if not session_file.exists():
        return False

    # Check if file was recently modified
    mtime = session_file.stat().st_mtime
    if time.time() - mtime > ACTIVITY_TIMEOUT_SECONDS:
        return False

    # Check if summary.md exists (indicates session ended)
    session_id = session_file.stem
    session_dir = session_file.parent / session_id
    summary_file = session_dir / "session-memory" / "summary.md"

    if summary_file.exists():
        # Grace period: if summary was written very recently (< 10s), the
        # session may still be wrapping up
        summary_age = time.time() - summary_file.stat().st_mtime
        if summary_age < 10:
            return True
        return False

    return True


def _detect_claude_pids() -> list[int]:
    """Detect running Claude Code CLI processes."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "claude"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return [int(pid) for pid in result.stdout.strip().split("\n") if pid.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    return []


def _read_tail_lines(session_file: Path, max_lines: int, max_bytes: int) -> list[str]:
    """Read recent lines from a potentially large JSONL file without loading it all."""
    try:
        with open(session_file, "rb") as f:
            f.seek(0, 2)
            file_size = f.tell()
            if file_size <= 0:
                return []
            read_size = min(file_size, max_bytes)
            f.seek(file_size - read_size)
            blob = f.read(read_size)
    except (IOError, OSError) as exc:
        logger.warning("Failed to read session tail: %s", exc)
        return []

    text = blob.decode("utf-8", errors="ignore")
    lines = text.splitlines()
    return lines[-max_lines:]


def _is_user_prompt(entry: dict) -> bool:
    """Return True if this JSONL entry is an actual user-typed prompt (not a tool_result)."""
    if entry.get("type") != "user":
        return False
    message = entry.get("message", {})
    content = message.get("content", "") if isinstance(message, dict) else message
    # Plain string = real user prompt
    if isinstance(content, str):
        return bool(content.strip())
    # List content: real prompt only if it contains non-tool_result blocks
    if isinstance(content, list):
        return any(
            isinstance(b, dict) and b.get("type") != "tool_result"
            for b in content
        )
    return False


def _get_user_text(entry: dict) -> str:
    """Extract the user's typed text from a user entry."""
    message = entry.get("message", {})
    content = message.get("content", "") if isinstance(message, dict) else str(message)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return " ".join(parts).strip()
    return str(content).strip()


def _summarize_turn(assistant_entries: list[dict]) -> tuple[str, list[str]]:
    """Collapse all assistant entries in a turn into one summary + file list.

    Returns (summary_text, files_modified).
    """
    text_parts: list[str] = []
    files: list[str] = []
    tool_counts: dict[str, int] = {}  # tool_name -> count

    for entry in assistant_entries:
        message = entry.get("message", {})
        if not isinstance(message, dict):
            continue
        content = message.get("content", "")

        if isinstance(content, str) and content.strip():
            text_parts.append(content.strip())
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "")
                if btype == "text":
                    t = block.get("text", "").strip()
                    if t:
                        text_parts.append(t)
                elif btype == "tool_use":
                    name = block.get("name", "unknown")
                    tool_counts[name] = tool_counts.get(name, 0) + 1
                    inp = block.get("input", {})
                    if isinstance(inp, dict):
                        fp = inp.get("file_path", "")
                        if fp and fp not in files:
                            files.append(fp)

    # Build summary: prefer Claude's own text, fall back to tool summary
    full_text = " ".join(text_parts)
    if full_text:
        # Take the last meaningful text (usually the final response to the user)
        # Skip very short fragments (< 20 chars) that are just transitions
        meaningful = [t for t in text_parts if len(t) >= 20]
        summary_source = meaningful[-1] if meaningful else text_parts[-1]
        summary = summary_source[:200] + "..." if len(summary_source) > 200 else summary_source
    elif tool_counts:
        # No text at all — summarize what tools did
        parts = []
        edits = tool_counts.get("Edit", 0) + tool_counts.get("Write", 0)
        reads = tool_counts.get("Read", 0) + tool_counts.get("Glob", 0) + tool_counts.get("Grep", 0)
        runs = tool_counts.get("Bash", 0)
        tasks = tool_counts.get("Task", 0)
        if edits:
            parts.append(f"edited {edits} file{'s' if edits > 1 else ''}")
        if reads:
            parts.append(f"read {reads} file{'s' if reads > 1 else ''}")
        if runs:
            parts.append(f"ran {runs} command{'s' if runs > 1 else ''}")
        if tasks:
            parts.append(f"spawned {tasks} agent{'s' if tasks > 1 else ''}")
        summary = ", ".join(parts).capitalize() if parts else "Working..."
    else:
        summary = "Working..."

    return summary, files


def _extract_exchanges(session_file: Path, max_turns: int = 10) -> list[Exchange]:
    """Extract recent conversation turns from a session JSONL file.

    Groups JSONL entries into turns (user prompt + assistant response) instead
    of showing every individual tool call. Returns at most max_turns * 2 exchanges
    (one user + one assistant per turn).
    """
    lines = _read_tail_lines(session_file, max_lines=500, max_bytes=1_000_000)
    if not lines:
        return []

    # Parse all entries
    entries: list[dict] = []
    for line in lines:
        entry = _parse_jsonl_entry(line)
        if entry:
            entries.append(entry)

    if not entries:
        return []

    # Group into turns: a turn starts at each real user prompt
    turns: list[dict] = []  # each: {user_entry, assistant_entries[]}
    current_turn: Optional[dict] = None

    for entry in entries:
        if _is_user_prompt(entry):
            # Start a new turn
            if current_turn is not None:
                turns.append(current_turn)
            current_turn = {"user": entry, "assistants": []}
        elif entry.get("type") == "assistant" and current_turn is not None:
            current_turn["assistants"].append(entry)

    # Don't forget the last turn (may be in progress)
    if current_turn is not None:
        turns.append(current_turn)

    # Take only the most recent turns
    recent_turns = turns[-max_turns:]

    # Convert turns to Exchange pairs
    exchanges: list[Exchange] = []
    for turn in recent_turns:
        user_entry = turn["user"]
        user_text = _get_user_text(user_entry)
        if not user_text:
            continue

        user_summary = user_text[:200] + "..." if len(user_text) > 200 else user_text
        exchanges.append(Exchange(
            time=user_entry.get("timestamp", ""),
            type="user",
            summary=user_summary,
        ))

        # Summarize the assistant's full response for this turn
        if turn["assistants"]:
            summary, files = _summarize_turn(turn["assistants"])
            last_ts = turn["assistants"][-1].get("timestamp", user_entry.get("timestamp", ""))
            exchanges.append(Exchange(
                time=last_ts,
                type="assistant",
                summary=summary,
                files=files,
            ))

    return exchanges


def _extract_session_stats(session_file: Path) -> dict:
    """Extract statistics from session JSONL."""
    stats = {
        "tokens_used": 0,
        "files_modified": set(),
        "lines_added": 0,
        "lines_removed": 0,
        "started_at": None,
        "estimated_cost": None,
    }

    lines = _read_tail_lines(session_file, max_lines=4000, max_bytes=2_000_000)
    for line in lines:
        entry = _parse_jsonl_entry(line)
        if not entry:
            continue

        # Get start time from first parsed entry in the sampled window.
        if stats["started_at"] is None:
            timestamp = entry.get("timestamp")
            if timestamp:
                stats["started_at"] = timestamp

        # Extract token usage
        usage = entry.get("usage", {})
        if usage:
            stats["tokens_used"] += usage.get("input_tokens", 0)
            stats["tokens_used"] += usage.get("output_tokens", 0)

        # Extract file modifications from tool use
        entry_type = entry.get("type", "")
        if entry_type == "assistant":
            message = entry.get("message", {})
            content = message.get("content", []) if isinstance(message, dict) else []

            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_name = block.get("name", "")
                        tool_input = block.get("input", {})

                        if tool_name in ("Write", "Edit"):
                            file_path = tool_input.get("file_path", "")
                            if file_path:
                                stats["files_modified"].add(file_path)

    # Convert set to list
    stats["files_modified"] = list(stats["files_modified"])

    # Estimate cost (rough approximation: $0.015 per 1K tokens)
    if stats["tokens_used"] > 0:
        cost = (stats["tokens_used"] / 1000) * 0.015
        stats["estimated_cost"] = f"${cost:.3f}"

    return stats


def _build_session(session_file: Path, claude_pids: list[int]) -> tuple[LiveSession, list[Exchange]]:
    """Build a LiveSession + exchanges from a JSONL file."""
    session_id = session_file.stem
    stats = _extract_session_stats(session_file)
    exchanges = _extract_exchanges(session_file)

    # Calculate elapsed time
    elapsed = None
    if stats["started_at"]:
        try:
            start_time = datetime.fromisoformat(
                stats["started_at"].replace("Z", "+00:00")
            )
            elapsed = _format_elapsed(start_time)
        except (ValueError, TypeError):
            pass

    # Try to find a matching PID (best effort — associate if only one)
    pid = claude_pids[0] if len(claude_pids) == 1 else None

    session = LiveSession(
        active=True,
        session_id=session_id,
        provider="claude",
        pid=pid,
        started_at=stats["started_at"],
        elapsed=elapsed,
        estimated_cost=stats["estimated_cost"],
        tokens_used=stats["tokens_used"],
        files_modified=stats["files_modified"],
        lines_added=stats["lines_added"],
        lines_removed=stats["lines_removed"],
    )
    return session, exchanges


@router.get("/{project_id:path}")
def get_live_sessions(project_id: str) -> LiveSessionResponse:
    """
    Get information about active Claude Code sessions for a project.

    Returns all active sessions with recent exchanges.
    The `session` field contains the most recent active session (backward compat).
    The `sessions` field contains all active sessions.
    """
    try:
        # Find project directory
        project_dir = _find_project_dir(project_id)
        if not project_dir:
            return LiveSessionResponse(active=False)

        # Detect running Claude processes for PID info
        claude_pids = _detect_claude_pids()

        # Find ALL active session files (not just the first one)
        def _mtime(path: Path) -> float:
            try:
                return path.stat().st_mtime
            except OSError:
                return 0.0

        jsonl_files = sorted(project_dir.glob("*.jsonl"), key=_mtime, reverse=True)
        active_files: list[Path] = []
        for jsonl_file in jsonl_files[:30]:
            if _is_session_active(jsonl_file):
                active_files.append(jsonl_file)

        if not active_files:
            return LiveSessionResponse(active=False)

        # Build session objects for each active file
        all_sessions: list[LiveSession] = []
        # Exchanges from the most recently modified session (primary)
        primary_exchanges: list[Exchange] = []

        for i, af in enumerate(active_files):
            try:
                session, exchanges = _build_session(af, claude_pids)
                all_sessions.append(session)
                if i == 0:
                    primary_exchanges = exchanges
            except Exception as exc:
                logger.warning(
                    "Failed to parse session %s: %s", af.stem, exc
                )
                continue

        if not all_sessions:
            return LiveSessionResponse(active=False)

        return LiveSessionResponse(
            active=True,
            session=all_sessions[0],  # backward compat
            sessions=all_sessions,
            exchanges=primary_exchanges,
        )
    except Exception as exc:
        logger.warning("Live session lookup failed for %s: %s", project_id, exc)
        return LiveSessionResponse(active=False)
