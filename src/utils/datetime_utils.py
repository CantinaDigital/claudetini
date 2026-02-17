"""Shared datetime utilities."""

from __future__ import annotations

from datetime import datetime


def parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO 8601 datetime string, returning None on invalid input.

    Handles common variations:
    - Standard ISO format: 2026-02-12T10:30:00
    - With timezone Z suffix: 2026-02-12T10:30:00Z
    - With timezone offset: 2026-02-12T10:30:00+00:00

    Returns a naive datetime (tzinfo stripped) for consistent comparison.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None
