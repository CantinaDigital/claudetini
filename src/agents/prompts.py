"""Prompt templates for Claude Code dispatch and sub-agents."""

import re
from dataclasses import dataclass
from pathlib import Path

from ..core.runtime import project_runtime_dir


@dataclass
class FailureContext:
    """Context about a previous failed attempt."""

    error_message: str
    error_type: str = "unknown"  # "test_failure", "lint_error", "runtime_error", etc.
    attempted_solutions: list[str] | None = None
    files_affected: list[str] | None = None
    gate_failures: list[str] | None = None


@dataclass
class PromptContext:
    """Context for building prompts."""

    project_name: str
    project_path: Path
    session_summary: str | None = None
    roadmap_status: str | None = None
    claude_md_content: str | None = None
    files_in_scope: list[str] | None = None
    last_failure: FailureContext | None = None
    git_diff_summary: str | None = None


class PromptBuilder:
    """Builder for Claude Code prompts."""

    # Base template for all prompts
    BASE_TEMPLATE = """You are working on {project_name}.

{context_section}

Task: {task}

{requirements_section}"""

    # Requirements that are always included
    DEFAULT_REQUIREMENTS = [
        "Follow existing code patterns and conventions",
        "Write tests for new functionality",
        "Update documentation if adding public APIs",
    ]

    def __init__(self, context: PromptContext):
        self.context = context

    def build_task_prompt(
        self,
        task: str,
        additional_context: str | None = None,
        additional_requirements: list[str] | None = None,
        include_session_summary: bool = True,
        include_roadmap: bool = True,
        include_claude_md: bool = False,
    ) -> str:
        """Build a complete prompt for a task."""
        context_parts = []

        if additional_context:
            context_parts.append(additional_context)

        if include_session_summary and self.context.session_summary:
            context_parts.append(f"Context from last session:\n{self.context.session_summary}")

        if include_roadmap and self.context.roadmap_status:
            context_parts.append(f"Current roadmap status:\n{self.context.roadmap_status}")

        if include_claude_md and self.context.claude_md_content:
            # Only include relevant sections, not the whole file
            conventions = self._extract_conventions(self.context.claude_md_content)
            if conventions:
                context_parts.append(f"Project conventions:\n{conventions}")

        context_section = "\n\n".join(context_parts) if context_parts else ""

        # Build requirements
        requirements = list(self.DEFAULT_REQUIREMENTS)
        if additional_requirements:
            requirements.extend(additional_requirements)

        requirements_section = "Requirements:\n" + "\n".join(f"- {r}" for r in requirements)

        return self.BASE_TEMPLATE.format(
            project_name=self.context.project_name,
            context_section=context_section,
            task=task,
            requirements_section=requirements_section,
        )

    def build_roadmap_item_prompt(
        self,
        item_text: str,
        milestone_name: str,
    ) -> str:
        """Build a prompt for working on a roadmap item."""
        additional_context = f"This is part of milestone: {milestone_name}"

        return self.build_task_prompt(
            task=f"Implement: {item_text}",
            additional_context=additional_context,
            include_roadmap=True,
        )

    def build_todo_prompt(
        self,
        todo_content: str,
        priority: str,
    ) -> str:
        """Build a prompt for completing a todo item."""
        additional_context = f"This was a {priority}-priority todo from a previous session."

        return self.build_task_prompt(
            task=todo_content,
            additional_context=additional_context,
        )

    def build_recovery_prompt(
        self,
        task: str,
        failure: FailureContext,
    ) -> str:
        """Build a prompt that includes context about why a previous attempt failed.

        This is critical for solving session amnesia - Claude needs to know
        what went wrong so it doesn't repeat the same mistakes.
        """
        # Build failure context section
        failure_parts = [
            "## Previous Attempt Failed",
            "",
            f"**Error Type:** {failure.error_type}",
            "**Error Message:**",
            "```",
            failure.error_message[:1500],  # Limit error length
            "```",
        ]

        if failure.attempted_solutions:
            failure_parts.append("")
            failure_parts.append("**Already Tried (don't repeat these):**")
            for solution in failure.attempted_solutions:
                failure_parts.append(f"- {solution}")

        if failure.files_affected:
            failure_parts.append("")
            failure_parts.append("**Files Affected:**")
            for f in failure.files_affected[:10]:
                failure_parts.append(f"- {f}")

        if failure.gate_failures:
            failure_parts.append("")
            failure_parts.append("**Quality Gates That Failed:**")
            for gate in failure.gate_failures:
                failure_parts.append(f"- {gate}")

        failure_context = "\n".join(failure_parts)

        # Build the task with recovery instructions
        recovery_task = f"""{task}

**Recovery Instructions:**
1. First analyze why the previous attempt failed
2. Do NOT repeat the same approaches that already failed
3. Fix the root cause, not just the symptoms
4. Run tests/lint before completing to verify the fix"""

        return self.build_task_prompt(
            task=recovery_task,
            additional_context=failure_context,
            additional_requirements=[
                "Address the specific error from the previous attempt",
                "Verify the fix doesn't introduce new issues",
            ],
        )

    def build_prompt_with_diff(
        self,
        task: str,
        diff_summary: str | None = None,
    ) -> str:
        """Build a prompt that includes git diff context.

        This helps Claude understand what has changed recently
        and focus on the relevant files.
        """
        diff_context = None

        # Use provided diff or context's diff
        diff = diff_summary or self.context.git_diff_summary

        if diff:
            diff_context = f"""## Recent Changes (git diff)

{diff[:2000]}

Focus on these recently changed files when working on the task."""

        return self.build_task_prompt(
            task=task,
            additional_context=diff_context,
        )

    def build_review_prompt(
        self,
        files: list[str],
        review_type: str = "general",
    ) -> str:
        """Build a prompt for code review."""
        files_str = "\n".join(f"- {f}" for f in files)

        if review_type == "security":
            task = f"""Review the following files for security vulnerabilities:

{files_str}

Look for:
- Exposed secrets or credentials
- SQL injection vulnerabilities
- XSS vulnerabilities
- Insecure dependencies
- Other OWASP Top 10 issues

Report findings as a structured list with severity levels."""

        elif review_type == "documentation":
            task = f"""Review the following files for documentation completeness:

{files_str}

Flag any:
- Functions or classes missing docstrings
- Outdated or incorrect documentation
- Missing type hints
- Complex logic without explanatory comments"""

        else:
            task = f"""Review the following files:

{files_str}

Check for:
- Code quality issues
- Potential bugs
- Performance concerns
- Adherence to project conventions"""

        return self.build_task_prompt(
            task=task,
            include_claude_md=True,
        )

    def _extract_conventions(self, claude_md: str) -> str:
        """Extract coding conventions from CLAUDE.md content."""
        # Look for sections about conventions, style, etc.
        lines = claude_md.split("\n")
        in_conventions = False
        conventions_lines = []

        keywords = ["convention", "style", "pattern", "guideline", "rule"]

        for line in lines:
            lower_line = line.lower()

            # Start capturing at relevant headers
            if line.startswith("#") and any(k in lower_line for k in keywords):
                in_conventions = True
                conventions_lines.append(line)
                continue

            # Stop at next major header
            if in_conventions and line.startswith("# "):
                break

            if in_conventions:
                conventions_lines.append(line)

        result = "\n".join(conventions_lines).strip()
        # Limit length
        if len(result) > 500:
            result = result[:500] + "..."

        return result


# Pre-built prompts for common operations
class CommonPrompts:
    """Collection of common prompt templates."""

    @staticmethod
    def fix_failing_tests(test_output: str) -> str:
        """Prompt to fix failing tests."""
        return f"""Fix the failing tests shown below:

```
{test_output[:2000]}
```

Analyze the failures and implement the necessary fixes."""

    @staticmethod
    def add_tests_for_file(file_path: str) -> str:
        """Prompt to add tests for a file."""
        return f"""Add comprehensive tests for the code in {file_path}.

Include:
- Unit tests for all public functions
- Edge case coverage
- Integration tests if applicable"""

    @staticmethod
    def refactor_for_clarity(file_path: str) -> str:
        """Prompt to refactor code for clarity."""
        return f"""Refactor {file_path} to improve code clarity and maintainability.

Focus on:
- Extracting complex logic into well-named functions
- Improving variable and function names
- Reducing cognitive complexity
- Adding clarifying comments where needed

Do not change functionality."""

    @staticmethod
    def create_roadmap_from_codebase() -> str:
        """Prompt to analyze codebase and generate a roadmap."""
        return (
            "Analyze this codebase and generate a ROADMAP.md file. "
            "Include milestones with checkbox items using - [x] for complete and - [ ] for pending. "
            "Start with implemented features marked complete, then add logical next steps grouped by milestone."
        )


DEFAULT_AGENT_TEMPLATES: dict[str, str] = {
    "security_review.md": (
        "Security review for {{project_name}}.\n"
        "Changed files:\n{{changed_files}}\n\n"
        "Look for vulnerabilities, exposed secrets, unsafe input handling, and insecure patterns.\n"
        "Respond in JSON with fields: status, summary, findings[]."
    ),
    "doc_review.md": (
        "Documentation review for {{project_name}}.\n"
        "Changed files:\n{{changed_files}}\n\n"
        "Identify missing docstrings, outdated docs, and user-visible behavior needing docs updates.\n"
        "Respond in JSON with fields: status, summary, findings[]."
    ),
    "test_review.md": (
        "Test coverage review for {{project_name}}.\n"
        "Changed files:\n{{changed_files}}\n\n"
        "Identify untested behavior and suggest concrete tests to add.\n"
        "Respond in JSON with fields: status, summary, findings[]."
    ),
}


class PromptTemplateLoader:
    """Load and render project-local agent templates."""

    def __init__(self, project_id: str, base_dir: Path | None = None):
        self.project_dir = project_runtime_dir(project_id, base_dir=base_dir)
        self.prompts_dir = self.project_dir / "prompts"
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        self._seed_defaults()

    def list_templates(self) -> list[str]:
        """Return available template filenames."""
        templates = {path.name for path in self.prompts_dir.glob("*.md")}
        templates.update(DEFAULT_AGENT_TEMPLATES.keys())
        return sorted(templates)

    def load_template(self, template_name: str) -> str:
        """Load template text from project prompts directory or defaults."""
        candidate = self.prompts_dir / template_name
        if candidate.exists():
            try:
                return candidate.read_text()
            except OSError:
                pass
        return DEFAULT_AGENT_TEMPLATES.get(template_name, "")

    def render(self, template_name: str, variables: dict[str, str]) -> str:
        """Render a template using {{variable}} substitution."""
        content = self.load_template(template_name)
        if not content:
            return ""

        def replace_var(match: re.Match[str]) -> str:
            """Replace template variable with value from variables dict."""
            key = match.group(1).strip()
            return str(variables.get(key, ""))

        return re.sub(r"{{\s*([a-zA-Z0-9_]+)\s*}}", replace_var, content)

    def save_template(self, template_name: str, content: str) -> Path:
        """Persist a custom template."""
        target = self.prompts_dir / template_name
        target.write_text(content)
        return target

    def _seed_defaults(self) -> None:
        for name, content in DEFAULT_AGENT_TEMPLATES.items():
            path = self.prompts_dir / name
            if not path.exists():
                path.write_text(content)
