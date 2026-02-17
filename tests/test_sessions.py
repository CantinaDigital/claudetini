"""Tests for session parsing."""

import pytest
from pathlib import Path
from datetime import datetime
import json

from src.core.sessions import SessionParser, SessionSummary, Session


class TestSessionSummary:
    """Tests for SessionSummary class."""

    def test_from_summary_file(self, mock_claude_dir):
        """Test parsing a session summary file."""
        summary_path = (
            mock_claude_dir / "projects" / "abc123def456" /
            "session-001" / "session-memory" / "summary.md"
        )

        summary = SessionSummary.from_summary_file(summary_path, "session-001")

        assert summary.session_id == "session-001"
        assert len(summary.accomplishments) == 3
        assert "Implemented user authentication" in summary.accomplishments


class TestSessionParser:
    """Tests for SessionParser class."""

    def test_find_sessions(self, mock_claude_dir):
        """Test finding sessions for a project."""
        parser = SessionParser(claude_dir=mock_claude_dir)

        sessions = parser.find_sessions("abc123def456")

        assert len(sessions) == 1
        assert sessions[0].session_id == "session-001"

    def test_find_sessions_empty(self, mock_claude_dir):
        """Test finding sessions for a non-existent project."""
        parser = SessionParser(claude_dir=mock_claude_dir)

        sessions = parser.find_sessions("nonexistent")

        assert len(sessions) == 0

    def test_get_latest_session(self, mock_claude_dir):
        """Test getting the latest session."""
        parser = SessionParser(claude_dir=mock_claude_dir)

        session = parser.get_latest_session("abc123def456")

        assert session is not None
        assert session.session_id == "session-001"

    def test_get_session_count(self, mock_claude_dir):
        """Test counting sessions."""
        parser = SessionParser(claude_dir=mock_claude_dir)

        count = parser.get_session_count("abc123def456")

        assert count == 1

    def test_session_has_summary(self, mock_claude_dir):
        """Test that session summary is loaded."""
        parser = SessionParser(claude_dir=mock_claude_dir)

        session = parser.get_latest_session("abc123def456")

        assert session is not None
        assert session.summary is not None
        assert len(session.summary.accomplishments) > 0

    def test_parse_log_entries(self, mock_claude_dir):
        """Test parsing log entries."""
        parser = SessionParser(claude_dir=mock_claude_dir)
        log_path = mock_claude_dir / "projects" / "abc123def456" / "session-001.jsonl"

        entries = parser.parse_log_entries(log_path)

        assert len(entries) == 2
        assert entries[0].type == "human"
        assert entries[1].type == "assistant"


class TestSession:
    """Tests for Session class."""

    def test_duration_calculation(self):
        """Test session duration calculation."""
        session = Session(
            session_id="test",
            project_hash="abc",
            log_path=Path("/fake/path"),
            start_time=datetime(2024, 2, 10, 10, 0, 0),
            end_time=datetime(2024, 2, 10, 11, 30, 0),
        )

        assert session.duration_minutes == 90

    def test_duration_none_without_times(self):
        """Test duration is None when times not set."""
        session = Session(
            session_id="test",
            project_hash="abc",
            log_path=Path("/fake/path"),
        )

        assert session.duration_minutes is None
