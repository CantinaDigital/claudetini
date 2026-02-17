"""Reporting and export services."""

from datetime import datetime, timezone, timedelta
from collections import defaultdict

from devlog.models import TimeEntry
from devlog import database
from devlog.utils.formatting import format_duration, format_date


class ReportService:
    """Service for generating reports and exports."""

    def weekly_summary(self, week_offset: int = 0) -> dict:
        """Generate a weekly summary of time entries.

        Args:
            week_offset: 0 for current week, -1 for last week, etc.
        """
        now = datetime.now(timezone.utc)
        week_start = now - timedelta(days=now.weekday() + (week_offset * -7))
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)

        entries = database.list_entries(limit=1000)
        week_entries = [
            e for e in entries
            if week_start <= e.created_at < week_end
        ]

        # Aggregate by project
        by_project: dict[str, int] = defaultdict(int)
        by_tag: dict[str, int] = defaultdict(int)

        for entry in week_entries:
            by_project[entry.project_id] += entry.duration_minutes
            for tag in entry.tags:
                by_tag[tag] += entry.duration_minutes

        total_minutes = sum(e.duration_minutes for e in week_entries)

        return {
            "week_start": format_date(week_start),
            "week_end": format_date(week_end),
            "total_entries": len(week_entries),
            "total_duration": format_duration(total_minutes),
            "total_minutes": total_minutes,
            "by_project": dict(by_project),
            "by_tag": dict(by_tag),
        }

    def filter_by_tag(self, tag: str) -> list[TimeEntry]:
        """Filter time entries by tag."""
        entries = database.list_entries(limit=1000)
        return [e for e in entries if tag in e.tags]

    def generate_csv(self, entries: list[TimeEntry] | None = None) -> str:
        """Export time entries as CSV format.

        This is a preview feature — not yet tracked in the roadmap.
        """
        if entries is None:
            entries = database.list_entries(limit=1000)

        lines = ["id,project_id,description,duration_minutes,tags,created_at"]
        for entry in entries:
            tags_str = ";".join(entry.tags)
            lines.append(
                f"{entry.id},{entry.project_id},\"{entry.description}\","
                f"{entry.duration_minutes},{tags_str},{entry.created_at.isoformat()}"
            )

        return "\n".join(lines)
