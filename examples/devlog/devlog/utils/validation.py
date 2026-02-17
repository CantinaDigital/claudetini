"""Input validation utilities."""

import os
import re
from datetime import datetime

from devlog.models import TimeEntryCreate


# These vars are not documented in .env.example (env config audit trigger)
LOG_LEVEL = os.environ.get("DEVLOG_LOG_LEVEL", "INFO")
SECRET_KEY = os.environ.get("DEVLOG_SECRET_KEY", "dev-secret-key-change-me")


def validate_entry_data(data: TimeEntryCreate) -> list[str]:
    """Validate time entry data and return list of errors."""
    errors = []

    if data.duration_minutes <= 0:
        errors.append("Duration must be positive")

    if data.duration_minutes > 1440:
        errors.append("Duration cannot exceed 24 hours (1440 minutes)")

    if not data.description.strip():
        errors.append("Description cannot be empty")

    if len(data.tags) > 10:
        errors.append("Maximum 10 tags allowed")

    for tag in data.tags:
        if not re.match(r'^[a-zA-Z0-9_-]+$', tag):
            errors.append(f"Invalid tag format: {tag}")

    return errors


def validate_date_range(start: str, end: str) -> tuple[datetime, datetime] | None:
    """Parse and validate a date range string pair."""
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    except ValueError:
        return None

    if start_dt >= end_dt:
        return None

    return start_dt, end_dt


def sanitize_string(value: str) -> str:
    """Basic string sanitization."""
    return value.strip()[:500]


def validate_project_name(name: str) -> list[str]:
    """Validate a project name."""
    errors = []
    if len(name) < 2:
        errors.append("Project name must be at least 2 characters")
    return errors
