"""Retry-with-context composition for incomplete sessions."""

from dataclasses import dataclass, field
from datetime import datetime

from .timeline import TimelineEntry


@dataclass
class RetryAttempt:
    """A single retry attempt."""

    session_id: str
    retry_number: int
    prompt_delta: str
    outcome: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class RetryChain:
    """Retry chain rooted at an original session."""

    original_session_id: str
    retries: list[RetryAttempt] = field(default_factory=list)


class RetryComposer:
    """Compose follow-up prompts for retries."""

    @staticmethod
    def should_offer_retry(
        entry: TimelineEntry,
        marked_incomplete: bool = False,
    ) -> bool:
        """Determine whether retry UI should be shown."""
        if marked_incomplete:
            return True
        if entry.test_results and not entry.test_results.passed:
            return True
        if entry.roadmap_items_completed:
            return False
        return entry.duration_minutes > 0 and entry.files_changed > 0

    @staticmethod
    def compose_followup_prompt(
        roadmap_item: str,
        entry: TimelineEntry,
        what_went_wrong: str | None = None,
    ) -> str:
        """Build the retry prompt from prior session outputs."""
        commits = (
            "\n".join(f"- {commit.sha[:7]} {commit.message}" for commit in entry.commits)
            or "- No commits detected"
        )
        files_summary = f"{entry.files_changed} file(s) changed"

        test_failure = ""
        if entry.test_results and not entry.test_results.passed:
            test_failure = entry.test_results.raw or "Tests failed in previous attempt."

        problem = what_went_wrong or test_failure or "Session ended before completion."

        return "\n".join(
            [
                f'The previous attempt at "{roadmap_item}" produced partial results.',
                "",
                "What was done:",
                commits,
                "",
                "What went wrong:",
                problem,
                "",
                "Files that were changed:",
                files_summary,
                "",
                "Please continue from where the last session left off. Focus on:",
                f"- Complete remaining work for: {roadmap_item}",
                "- Validate with tests before finishing.",
                "",
                "Do NOT redo work that's already complete.",
            ]
        )

