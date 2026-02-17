"""Time entry business logic."""

from datetime import datetime, timezone

from devlog.models import TimeEntryCreate, TimeEntry
from devlog import database


class EntryService:
    """Service for managing time entries."""

    def create(self, data: TimeEntryCreate) -> TimeEntry:
        """Create a new time entry."""
        # FIXME: Validate that project_id exists before creating entry
        entry = TimeEntry(
            project_id=data.project_id,
            description=data.description,
            duration_minutes=data.duration_minutes,
            tags=data.tags,
        )
        return database.create_entry(entry)

    def get(self, entry_id: str) -> TimeEntry | None:
        """Get a time entry by ID."""
        return database.get_entry(entry_id)

    def list_all(self, limit: int = 100) -> list[TimeEntry]:
        """List all time entries."""
        return database.list_entries(limit=limit)

    def update(self, entry_id: str, data: TimeEntryCreate) -> TimeEntry | None:
        """Update an existing time entry."""
        return database.update_entry(
            entry_id,
            description=data.description,
            duration_minutes=data.duration_minutes,
            tags=data.tags,
        )

    def delete(self, entry_id: str) -> bool:
        """Delete a time entry."""
        return database.delete_entry(entry_id)

    def get_total_duration(self, project_id: str) -> int:
        """Calculate total duration for a project in minutes."""
        entries = self.list_all()
        total = 0
        for entry in entries:
            if entry.project_id == project_id:
                total += entry.duration_minutes
        return total
