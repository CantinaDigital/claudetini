"""Tests for retry prompt composition."""

from datetime import datetime

from src.core.retry import RetryComposer
from src.core.timeline import TimelineEntry


def test_retry_compose():
    entry = TimelineEntry(
        session_id="s1",
        date=datetime.now(),
        duration_minutes=10,
        summary="partial work",
        files_changed=3,
    )
    prompt = RetryComposer.compose_followup_prompt("Implement auth", entry)
    assert "Implement auth" in prompt
    assert "Do NOT redo work" in prompt


def test_retry_offer_for_incomplete():
    entry = TimelineEntry(
        session_id="s1",
        date=datetime.now(),
        duration_minutes=5,
        summary="incomplete",
        files_changed=1,
    )
    assert RetryComposer.should_offer_retry(entry, marked_incomplete=True) is True

