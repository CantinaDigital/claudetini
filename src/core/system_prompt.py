"""System prompt generation for append-system-prompt dispatch."""

import os
from dataclasses import dataclass
from pathlib import Path

from .git_utils import GitUtils
from .project import Project
from .roadmap import RoadmapParser
from .runtime import project_id_for_project, project_runtime_dir
from .sessions import SessionParser


@dataclass
class SystemPromptContext:
    """Context used to render project system prompt."""

    project_name: str
    active_milestone: str
    current_focus_item: str
    conventions: str
    last_session_summary: str
    known_issues: list[str]
    blitz_mode: bool = False
    worktree_root: str | None = None
    git_diff_summary: str | None = None  # Auto-injected git context


class SystemPromptBuilder:
    """Build and persist system prompt files for dispatcher usage."""

    def __init__(
        self,
        project: Project,
        base_dir: Path | None = None,
        blitz_mode: bool | None = None,
    ):
        self.project = project
        self.project_id = project_id_for_project(project)
        if blitz_mode is None:
            env_flag = os.environ.get("CLAUDETINI_BLITZ", "").lower()
            blitz_mode = env_flag in {"1", "true", "yes", "on"}
            if ".worktrees" in str(project.path):
                blitz_mode = True
        self.blitz_mode = blitz_mode
        if base_dir is None:
            configured_home = os.environ.get("CLAUDETINI_HOME")
            if configured_home:
                base_dir = Path(configured_home) / "projects"
        elif base_dir.name != "projects":
            base_dir = base_dir / "projects"
        self.output_dir = project_runtime_dir(self.project_id, base_dir=base_dir)
        self.output_path = self.output_dir / ".system-prompt.md"

    def build_and_write(self) -> Path:
        """Generate and persist the system prompt file."""
        context = self._collect_context()
        self.output_path.write_text(self._render(context))
        return self.output_path

    def _collect_context(self) -> SystemPromptContext:
        roadmap = RoadmapParser.parse(self.project.path)
        active_milestone = "Backlog"
        focus_item = "Select the highest-priority incomplete roadmap item."
        if roadmap:
            for milestone in roadmap.milestones:
                if any(not item.completed for item in milestone.items):
                    active_milestone = milestone.name
                    for item in milestone.items:
                        if not item.completed:
                            focus_item = item.text
                            break
                    break

        claude_md = self.project.path / "CLAUDE.md"
        conventions = ""
        if claude_md.exists():
            conventions = self._extract_conventions(claude_md.read_text())

        summary = "No recent session summary."
        if self.project.claude_hash:
            session = SessionParser().get_latest_session(self.project.claude_hash)
            if session and session.summary and session.summary.summary_text.strip():
                summary = session.summary.summary_text.strip().splitlines()[0]

        # Get git diff context if there are uncommitted changes
        git_diff_summary = None
        try:
            git_utils = GitUtils(self.project.path)
            git_diff_summary = git_utils.get_diff_summary(max_lines=30)
        except Exception:
            pass  # Git context is optional

        return SystemPromptContext(
            project_name=self.project.name,
            active_milestone=active_milestone,
            current_focus_item=focus_item,
            conventions=conventions,
            last_session_summary=summary,
            known_issues=[],
            blitz_mode=bool(self.blitz_mode),
            worktree_root=str(self.project.path),
            git_diff_summary=git_diff_summary,
        )

    @staticmethod
    def _extract_conventions(content: str) -> str:
        lines = content.splitlines()
        relevant = []
        include = False
        for line in lines:
            lower = line.lower()
            if line.startswith("#") and any(key in lower for key in ("convention", "style", "rule", "test")):
                include = True
                relevant.append(line)
                continue
            if include and line.startswith("# "):
                break
            if include:
                relevant.append(line)
        text = "\n".join(relevant).strip()
        return text[:1200] if text else "Follow project conventions in CLAUDE.md."

    @staticmethod
    def _render(context: SystemPromptContext) -> str:
        known_issues = "\n".join(f"- {issue}" for issue in context.known_issues) or "- None"
        lines = [
            "## Project Context",
            f"You are working on {context.project_name}.",
            f"Current sprint/milestone: {context.active_milestone}",
            f"Current focus item: {context.current_focus_item}",
            "",
            "## Conventions",
            context.conventions,
            "",
            "## Recent Context",
            f"Last session: {context.last_session_summary}",
            "",
            "## Known Issues",
            known_issues,
        ]

        # Add git diff context if available
        if context.git_diff_summary:
            lines.extend(
                [
                    "",
                    "## Uncommitted Changes",
                    "Focus on these recently modified files when working on the task:",
                    "",
                    context.git_diff_summary,
                ]
            )

        if context.blitz_mode:
            lines.extend(
                [
                    "",
                    "## Blitz Mode Constraints",
                    f"- Operate only inside this worktree: {context.worktree_root}",
                    "- Do not modify sibling worktrees or parent repository roots.",
                    "- Avoid destructive git history operations.",
                ]
            )
        return "\n".join(lines)
