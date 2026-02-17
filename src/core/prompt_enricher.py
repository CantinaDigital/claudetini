"""Context-aware prompt enrichment for task dispatch."""

import re
from dataclasses import dataclass
from pathlib import Path

from .git_utils import GitUtils
from .project import Project


@dataclass
class EnrichedPrompt:
    """Enriched prompt with context."""
    prompt: str
    context_added: list[str]  # List of context types added: "conventions", "files", "structure", etc.


class PromptEnricher:
    """Enriches task prompts with project context."""

    def __init__(self, project_path: Path):
        self.project = Project.from_path(project_path)
        self.git = GitUtils(project_path)

    def enrich_task_prompt(
        self,
        task_text: str,
        custom_prompt: str | None = None
    ) -> EnrichedPrompt:
        """Build a context-rich prompt for a roadmap task.

        Args:
            task_text: The task description from roadmap
            custom_prompt: Optional custom prompt (if set in roadmap item)

        Returns:
            EnrichedPrompt with added context
        """
        # Strip markdown numbering (e.g. "**1.4** Display...") from the task text for a clean description
        clean_task = re.sub(r'^\*\*[\d.]+\*\*\s*', '', task_text).strip()

        if custom_prompt:
            prompt_parts = [custom_prompt]
        else:
            prompt_parts = [f"Implement: {clean_task}"]

        context_added = []

        # 1. Add code conventions from CLAUDE.md
        conventions = self._extract_conventions()
        if conventions:
            prompt_parts.append(f"\n## Code Conventions\n{conventions}")
            context_added.append("conventions")

        # 2. Add relevant file hints
        file_hints = self._find_relevant_files(task_text)
        if file_hints:
            prompt_parts.append(
                "\n## Relevant Files\nThese files are likely relevant — read them before making changes:\n"
                + "\n".join(f"- `{f}`" for f in file_hints)
            )
            context_added.append("file_hints")

        # 3. Add component structure guidance
        structure = self._infer_component_structure(task_text)
        if structure:
            prompt_parts.append(f"\n## Implementation Guidance\n{structure}")
            context_added.append("structure")

        # 4. Add acceptance criteria
        criteria = self._generate_acceptance_criteria(clean_task)
        prompt_parts.append(f"\n## Acceptance Criteria\n{criteria}")
        context_added.append("acceptance_criteria")

        # 5. Add recent changes context
        recent_files = self._get_recent_changes()
        if recent_files:
            prompt_parts.append(
                "\n## Recently Modified Files\nThese were changed recently and may be relevant:\n"
                + "\n".join(f"- `{f}`" for f in recent_files)
            )
            context_added.append("recent_changes")

        return EnrichedPrompt(
            prompt="\n".join(prompt_parts),
            context_added=context_added
        )

    def _extract_conventions(self) -> str | None:
        """Extract code conventions section from CLAUDE.md."""
        claude_md = self.project.path / "CLAUDE.md"
        if not claude_md.exists():
            return None

        try:
            content = claude_md.read_text(encoding="utf-8")
            # Find "Code Conventions" or "Conventions" section
            match = re.search(
                r'## (?:Code )?Conventions?\s*\n(.*?)(?=\n##|\Z)',
                content,
                re.DOTALL | re.IGNORECASE
            )
            if match:
                conventions = match.group(1).strip()
                # Limit to 600 chars to avoid bloating prompt
                return conventions[:600] + ("..." if len(conventions) > 600 else "")
        except Exception:
            pass

        return None

    def _find_relevant_files(self, task_text: str) -> list[str]:
        """Find files relevant to the task based on keywords."""
        keywords = self._extract_keywords(task_text)
        if not keywords:
            return []

        relevant = set()
        for keyword in keywords:
            # Search for files with keyword in name
            try:
                matches = list(self.project.path.glob(f"**/*{keyword}*"))
                # Filter out common noise (node_modules, .git, etc.)
                matches = [
                    m for m in matches
                    if not any(
                        part.startswith('.')
                        or part in ('node_modules', 'dist', 'build', '__pycache__')
                        for part in m.parts
                    )
                ]
                for match in matches[:3]:  # Top 3 per keyword
                    try:
                        rel_path = match.relative_to(self.project.path)
                        relevant.add(str(rel_path))
                    except ValueError:
                        continue
            except Exception:
                continue

        return sorted(relevant)[:10]  # Max 10 files

    def _infer_component_structure(self, task_text: str) -> str | None:
        """Infer what component structure is needed based on task."""
        task_lower = task_text.lower()

        # UI-related task
        ui_keywords = ["display", "show", "view", "component", "page", "ui", "button", "form",
                        "navigation", "keyboard", "select", "picker", "list", "card", "tab"]
        if any(kw in task_lower for kw in ui_keywords):
            return (
                "Frontend component task.\n"
                "- Components live in `app/src/components/`\n"
                "- Use inline styles with design tokens from `styles/tokens.ts`\n"
                "- State: local `useState` for UI, Zustand store for shared state\n"
                "- Follow existing component patterns in the same directory"
            )

        # API-related task
        api_keywords = ["api", "endpoint", "route", "fetch", "request", "backend"]
        if any(kw in task_lower for kw in api_keywords):
            return (
                "API/backend task.\n"
                "- Backend routes: `python-sidecar/sidecar/api/routes/`\n"
                "- Models: Pydantic BaseModel for request/response\n"
                "- Frontend client: `app/src/api/backend.ts`\n"
                "- Wire both sides: add endpoint + add client method + call from component"
            )

        # Core logic task
        core_keywords = ["parser", "scanner", "analyzer", "engine", "core", "utils"]
        if any(kw in task_lower for kw in core_keywords):
            return (
                "Core logic task.\n"
                "- Module location: `src/core/`\n"
                "- Use type hints and dataclasses\n"
                "- Add tests in `tests/`\n"
                "- Use `pathlib.Path` for file operations"
            )

        return None

    def _generate_acceptance_criteria(self, task_text: str) -> str:
        """Generate acceptance criteria for the task."""
        task_lower = task_text.lower()
        criteria = [f"- {task_text} works as described"]

        if any(kw in task_lower for kw in ["display", "show", "render", "ui", "component", "button", "view"]):
            criteria.append("- UI renders correctly with no visual regressions")
        if any(kw in task_lower for kw in ["api", "endpoint", "fetch", "request"]):
            criteria.append("- API endpoint returns correct data and handles errors")
        if any(kw in task_lower for kw in ["keyboard", "navigate", "shortcut", "key"]):
            criteria.append("- Keyboard interactions work as specified")
        if any(kw in task_lower for kw in ["test", "coverage"]):
            criteria.append("- Tests pass and cover the new functionality")

        criteria.append("- Code follows project conventions (CLAUDE.md)")
        criteria.append("- No debug code or console.log statements left behind")
        return "\n".join(criteria)

    def _get_recent_changes(self) -> list[str]:
        """Get recently modified files from git."""
        try:
            # Get files modified in last 3 commits
            result = self.git.run_git_command(
                ["log", "--name-only", "--pretty=format:", "-3"]
            )
            if result.success and result.stdout:
                files = [
                    line.strip()
                    for line in result.stdout.strip().split('\n')
                    if line.strip()
                ]
                # Deduplicate and limit
                return list(dict.fromkeys(files))[:5]
        except Exception:
            pass

        return []

    def _extract_keywords(self, task_text: str) -> list[str]:
        """Extract relevant keywords from task text."""
        # Remove markdown and common words
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at",
            "to", "for", "of", "with", "from", "by", "as", "is", "are"
        }

        # Extract words
        words = re.findall(r'\b[a-zA-Z_-]+\b', task_text.lower())

        # Filter and return top 5 meaningful keywords
        keywords = [
            w for w in words
            if w not in stop_words and len(w) > 3
        ]

        return keywords[:5]
