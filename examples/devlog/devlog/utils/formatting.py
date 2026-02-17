"""Time and date formatting utilities."""

from datetime import datetime


def format_duration(minutes: int) -> str:
    hours = minutes // 60
    remaining = minutes % 60

    if hours > 0 and remaining > 0:
        return f"{hours}h {remaining}m"
    elif hours > 0:
        return f"{hours}h"
    else:
        return f"{remaining}m"


def format_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def format_datetime(dt: datetime) -> str:
    """Format a datetime as a human-readable string."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def minutes_to_hours(minutes: int) -> float:
    return round(minutes / 60, 2)


def seconds_to_display(seconds: int) -> str:
    """Convert seconds to a human-readable duration string."""
    if seconds >= 3600:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m"
    elif seconds >= 60:
        return f"{seconds // 60}m"
    else:
        return f"{seconds}s"


def truncate_text(text: str, max_length: int = 100) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def get_week_number(dt: datetime) -> int:
    """Get ISO week number for a datetime."""
    return dt.isocalendar()[1]


def days_until_end_of_week(dt: datetime) -> int:
    return 7 - dt.weekday() - 1


def format_percentage(value: float) -> str:
    """Format a value as a percentage string."""
    return f"{value:.1f}%"
