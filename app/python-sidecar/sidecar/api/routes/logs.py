"""
Logs API route - aggregates dispatch logs, gate results, and audit events.
"""

import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

try:
    from src.agents.dispatcher import DispatchLogger
    from src.core.dispatch_audit import DispatchAuditStore
    from src.core.gate_results import GateResultStore
    from src.core.runtime import project_id_for_path
    from src.core.cost_tracker import estimate_cost, parse_usage_file

    CORE_AVAILABLE = True
except ImportError:
    CORE_AVAILABLE = False

router = APIRouter()


class LogEntry(BaseModel):
    """A single log entry from dispatch, gate, or audit sources."""

    time: str
    level: str  # info, pass, warn, fail
    src: str
    msg: str


class LogsResponse(BaseModel):
    """Paginated list of aggregated log entries for a project."""

    entries: list[LogEntry]
    total_count: int


def _parse_dt(value: str | None) -> datetime | None:
    """Parse ISO datetime, always returning naive (no tzinfo) for safe sorting."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _format_time(dt: datetime, today: datetime) -> str:
    """Format timestamp with date context for non-today entries."""
    if dt.date() == today.date():
        return dt.strftime("%H:%M:%S")
    return dt.strftime("%b %d %H:%M")


@router.get("/{project_id:path}")
def get_logs(project_id: str, limit: int = Query(100, ge=1, le=1000)) -> LogsResponse:
    """Get aggregated logs for a project."""
    if not CORE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Core modules not loaded - cannot retrieve logs",
        )

    # Collect (datetime, level, src, msg) tuples so we can sort by real datetime
    raw_entries: list[tuple[datetime, str, str, str]] = []
    now = datetime.now()

    # Resolve project_id to a hash if it's a path
    project_path = Path(project_id)
    if project_path.exists():
        pid = project_id_for_path(project_path)
    else:
        pid = project_id

    # Load dispatch records (higher limit to survive cross-project filtering)
    try:
        dispatch_logger = DispatchLogger()
        records = dispatch_logger.get_recent_dispatches(limit=100)

        for record in records:
            record_project_id = record.get("project_id")
            record_project_path = record.get("project_path")

            # Match by project_id or by path
            matches = (
                record_project_id == pid or
                (record_project_path and Path(record_project_path).exists() and
                 project_id_for_path(Path(record_project_path)) == pid) or
                record_project_path == project_id
            )

            if not matches:
                continue

            ts = _parse_dt(record.get("timestamp")) or now
            level = "pass" if record.get("success") else "fail"
            message = "Session dispatched"

            output_file = record.get("output_file")
            try:
                usage = parse_usage_file(Path(output_file)) if output_file else None
                if usage:
                    cost = estimate_cost(usage, usage.model)
                    message = (
                        f"Session {record.get('session_id', '')} ended — "
                        f"{usage.input_tokens:,} in / {usage.output_tokens:,} out · ${cost:.2f}"
                    )
                    level = "info"
            except Exception as e:
                logger.warning("Failed to parse dispatch log record: %s", e)

            if record.get("error"):
                message = f"Dispatch failed: {record['error']}"

            raw_entries.append((ts, level, "dispatcher", message))
    except Exception as e:
        logger.warning("Failed to load dispatch logs: %s", e)

    # Load gate results (historical, not just latest)
    try:
        gate_store = GateResultStore(pid)
        gate_reports = gate_store.load_history(limit=20)
        for gate_report in gate_reports:
            if not gate_report.timestamp:
                continue
            ts = gate_report.timestamp
            for gate in gate_report.gates:
                level = gate.status if gate.status in {"pass", "warn", "fail"} else "info"
                raw_entries.append((ts, level, f"gate:{gate.name[:8]}", gate.summary))
    except Exception as e:
        logger.warning("Failed to load gate results: %s", e)

    # Load audit events
    try:
        audit_store = DispatchAuditStore(pid)
        for event in audit_store.recent(limit=40):
            raw_entries.append((
                event.timestamp,
                "warn",
                f"audit:{event.override_type}",
                f"Override: {event.reason}",
            ))
    except Exception as e:
        logger.warning("Failed to load audit events: %s", e)

    # Sort by full datetime descending (correct cross-day ordering)
    raw_entries.sort(key=lambda e: e[0], reverse=True)

    # Convert to response entries with date-aware display times
    entries = [
        LogEntry(
            time=_format_time(dt, now),
            level=level,
            src=src,
            msg=msg,
        )
        for dt, level, src, msg in raw_entries[:limit]
    ]

    return LogsResponse(entries=entries, total_count=len(entries))
