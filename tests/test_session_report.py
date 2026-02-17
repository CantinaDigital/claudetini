"""Tests for session report generation."""

from datetime import datetime

from src.core.session_report import SessionReportBuilder
from src.core.timeline import TimelineEntry


def test_session_report_builder_basic(temp_dir):
    entry = TimelineEntry(
        session_id="s1",
        date=datetime.now(),
        duration_minutes=12,
        summary="Did work",
    )
    report = SessionReportBuilder(temp_dir).build(entry)
    assert report.session_id == "s1"
    assert report.duration_minutes == 12

