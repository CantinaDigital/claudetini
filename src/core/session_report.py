"""Post-session report generation."""

import fcntl
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .cost_tracker import TokenUsage
from .diff_summary import DiffSummary, DiffSummaryBuilder
from .runtime import project_runtime_dir
from .timeline import TimelineEntry

logger = logging.getLogger(__name__)


@dataclass
class SessionReport:
    """Human-readable session report."""

    session_id: str
    generated_at: datetime
    duration_minutes: int
    commits_count: int
    files_changed: int
    total_additions: int
    total_deletions: int
    test_summary: str
    token_usage: TokenUsage | None = None
    cost_estimate: float | None = None
    key_changes: list[str] = field(default_factory=list)


class SessionReportBuilder:
    """Generate report cards from timeline entries and git refs."""

    def __init__(self, project_path: Path):
        self.project_path = project_path.resolve()

    def build(
        self,
        entry: TimelineEntry,
        from_ref: str | None = None,
        to_ref: str = "HEAD",
    ) -> SessionReport:
        """Build a report for a timeline entry."""
        diff = DiffSummary()
        if from_ref:
            diff = DiffSummaryBuilder(self.project_path).build(from_ref=from_ref, to_ref=to_ref)

        test_summary = "Not run"
        if entry.test_results:
            if entry.test_results.total is not None and entry.test_results.passed_count is not None:
                test_summary = f"{entry.test_results.passed_count}/{entry.test_results.total} passing"
            else:
                test_summary = "Passing" if entry.test_results.passed else "Failing"

        key_changes = [f"NEW {item.path}" for item in diff.files_new[:5]]
        key_changes.extend(f"MOD {item.path}" for item in diff.files_modified[:5 - len(key_changes)])

        return SessionReport(
            session_id=entry.session_id,
            generated_at=datetime.now(),
            duration_minutes=entry.duration_minutes,
            commits_count=len(entry.commits),
            files_changed=diff.total_files or entry.files_changed,
            total_additions=diff.total_additions,
            total_deletions=diff.total_deletions,
            test_summary=test_summary,
            token_usage=entry.token_usage,
            cost_estimate=entry.cost_estimate,
            key_changes=key_changes,
        )


class SessionReportStore:
    """Persist session reports to project storage with concurrent-safe file access."""

    def __init__(self, project_id: str, base_dir: Path | None = None):
        self.project_dir = project_runtime_dir(project_id, base_dir=base_dir)
        self.path = self.project_dir / "session-reports.json"

    def save(self, report: SessionReport) -> None:
        """Save a session report with file locking for concurrent safety."""
        try:
            with open(self.path, "a+") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.seek(0)
                    content = f.read()
                    reports = json.loads(content) if content.strip() else []
                    if not isinstance(reports, list):
                        reports = []

                    reports.append(
                        {
                            "session_id": report.session_id,
                            "generated_at": report.generated_at.isoformat(),
                            "duration_minutes": report.duration_minutes,
                            "commits_count": report.commits_count,
                            "files_changed": report.files_changed,
                            "total_additions": report.total_additions,
                            "total_deletions": report.total_deletions,
                            "test_summary": report.test_summary,
                            "token_usage": (
                                {
                                    "input_tokens": report.token_usage.input_tokens,
                                    "output_tokens": report.token_usage.output_tokens,
                                    "model": report.token_usage.model,
                                }
                                if report.token_usage
                                else None
                            ),
                            "cost_estimate": report.cost_estimate,
                            "key_changes": report.key_changes,
                        }
                    )
                    reports = reports[-500:]

                    f.seek(0)
                    f.truncate()
                    f.write(json.dumps(reports, indent=2))
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError as e:
            logger.warning("Failed to save session report: %s", e)

    def load_all_raw(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            with open(self.path) as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    data = json.loads(f.read())
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load session reports: %s", e)
            return []
        return data if isinstance(data, list) else []
