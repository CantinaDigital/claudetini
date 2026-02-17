"""Tests for reporting service."""

import pytest

from devlog.services.reports import ReportService
from devlog.models import TimeEntry
from devlog import database


@pytest.fixture
def report_service():
    return ReportService()


class TestReportService:
    def test_weekly_summary_empty(self, report_service):
        summary = report_service.weekly_summary()
        assert summary["total_entries"] == 0
        assert summary["total_minutes"] == 0

    def test_weekly_summary_keys(self, report_service, sample_entries):
        summary = report_service.weekly_summary()
        assert "total_entries" in summary
        assert "total_minutes" in summary
        assert "by_project" in summary
        assert "by_tag" in summary
        assert "week_start" in summary
        assert "week_end" in summary

    def test_filter_by_tag(self, report_service, sample_entries):
        results = report_service.filter_by_tag("backend")
        backend_entries = [e for e in sample_entries if "backend" in e.tags]
        assert len(results) == len(backend_entries)

    def test_filter_by_nonexistent_tag(self, report_service, sample_entries):
        results = report_service.filter_by_tag("nonexistent")
        assert len(results) == 0

    def test_generate_csv(self, report_service, sample_entries):
        csv_output = report_service.generate_csv(sample_entries)
        lines = csv_output.strip().split("\n")
        # Header + data rows
        assert len(lines) == len(sample_entries) + 1
        assert lines[0].startswith("id,project_id")

    def test_generate_csv_empty(self, report_service):
        csv_output = report_service.generate_csv([])
        lines = csv_output.strip().split("\n")
        assert len(lines) == 1  # Just the header
