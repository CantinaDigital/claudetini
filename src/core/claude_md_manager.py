"""Living CLAUDE.md management."""

import re
from dataclasses import dataclass
from datetime import datetime

from .project import Project
from .roadmap import RoadmapParser

START_MARKER = "<!-- claudetini:managed -->"
END_MARKER = "<!-- /claudetini:managed -->"


@dataclass
class ClaudeMdStatus:
    """Status for CLAUDE.md health integration."""

    exists: bool
    managed: bool
    stale: bool
    last_updated: datetime | None = None


class ClaudeMdManager:
    """Manage CLAUDE.md managed sections while preserving user content."""

    def __init__(self, project: Project):
        self.project = project
        self.path = project.path / "CLAUDE.md"

    def update_managed_section(
        self,
        active_branch: str,
        known_issues: list[str] | None = None,
        health_score: int | None = None,
        health_issues: list[str] | None = None,
    ) -> None:
        """Create or refresh managed status block."""
        known_issues = known_issues or []
        health_issues = health_issues or []
        roadmap = RoadmapParser.parse(self.project.path)

        done = []
        in_progress = []
        if roadmap:
            for milestone in roadmap.milestones:
                for item in milestone.items:
                    line = item.text
                    if item.completed:
                        done.append(line)
                    else:
                        in_progress.append(line)

        managed = self._render_managed_block(
            active_branch=active_branch,
            done_items=done[:8],
            in_progress_items=in_progress[:8],
            known_issues=known_issues[:8],
            health_score=health_score,
            health_issues=health_issues[:8],
        )

        if self.path.exists():
            content = self.path.read_text()
        else:
            content = "# CLAUDE.md\n\n"

        # Handle both new and legacy markers for backwards compatibility
        if START_MARKER in content and END_MARKER in content:
            pattern = re.compile(
                re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER),
                re.DOTALL,
            )
            updated = pattern.sub(managed, content)
        elif "<!-- claudetini:managed -->" in content and "<!-- /claudetini:managed -->" in content:
            # Migrate from legacy markers to new markers
            pattern = re.compile(
                r"<!-- claudetini:managed -->.*?<!-- /claudetini:managed -->",
                re.DOTALL,
            )
            updated = pattern.sub(managed, content)
        else:
            updated = content.rstrip() + "\n\n" + managed + "\n"

        self.path.write_text(updated)

    def status(self) -> ClaudeMdStatus:
        """Get CLAUDE.md status."""
        if not self.path.exists():
            return ClaudeMdStatus(exists=False, managed=False, stale=True)
        content = self.path.read_text()
        # Check for both new and legacy markers for backwards compatibility
        managed = (START_MARKER in content and END_MARKER in content) or (
            "<!-- claudetini:managed -->" in content and "<!-- /claudetini:managed -->" in content
        )
        try:
            updated = datetime.fromtimestamp(self.path.stat().st_mtime)
        except OSError:
            updated = None
        stale = True
        if updated:
            stale = (datetime.now() - updated).days > 7
        return ClaudeMdStatus(exists=True, managed=managed, stale=stale, last_updated=updated)

    def _render_managed_block(
        self,
        active_branch: str,
        done_items: list[str],
        in_progress_items: list[str],
        known_issues: list[str],
        health_score: int | None,
        health_issues: list[str],
    ) -> str:
        done_lines = "\n".join(f"- [x] {item}" for item in done_items) or "- [x] No completed items detected yet"
        progress_lines = "\n".join(f"- [ ] {item}" for item in in_progress_items) or "- [ ] No active items detected"
        issue_lines = "\n".join(f"- {item}" for item in known_issues) or "- None detected"
        health_label = "unknown"
        if health_score is not None:
            health_label = f"{health_score}/100"
        health_lines = "\n".join(f"- {item}" for item in health_issues) or "- No active health warnings"

        return "\n".join(
            [
                START_MARKER,
                "## Current Status",
                f"- Active branch: {active_branch}",
                f"- Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                "",
                "## What's Done",
                done_lines,
                "",
                "## What's In Progress",
                progress_lines,
                "",
                "## Health Snapshot",
                f"- Overall score: {health_label}",
                health_lines,
                "",
                "## Known Issues",
                issue_lines,
                END_MARKER,
            ]
        )
