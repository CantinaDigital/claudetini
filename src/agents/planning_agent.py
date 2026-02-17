"""AI-driven execution planner for parallel milestone execution.

Dispatches Claude Code to analyze tasks with full project context,
generates phased execution plans with themed agents, and verifies
completion against success criteria.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Data Models ──


@dataclass
class AgentAssignment:
    """A themed batch of tasks assigned to a single agent."""

    agent_id: int
    theme: str
    task_indices: list[int]
    rationale: str
    agent_prompt: str  # Detailed implementation prompt for the agent


@dataclass
class ExecutionPhase:
    """A phase in the execution plan."""

    phase_id: int
    name: str
    description: str
    parallel: bool  # Can agents in this phase run simultaneously?
    agents: list[AgentAssignment]


@dataclass
class ExecutionPlan:
    """Complete AI-generated execution plan."""

    summary: str
    phases: list[ExecutionPhase]
    success_criteria: list[str]
    estimated_total_agents: int
    warnings: list[str]
    raw_output: str = ""  # Full planning agent output for display


@dataclass
class CriterionResult:
    """Result of checking a single success criterion."""

    criterion: str
    passed: bool
    evidence: str
    notes: str


@dataclass
class VerificationResult:
    """Result of verifying plan completion."""

    overall_pass: bool
    criteria_results: list[CriterionResult]
    summary: str
    raw_output: str = ""


# ── Planning Agent ──


class PlanningAgent:
    """AI-driven execution planner that leverages full project context."""

    def __init__(self, project_path: Path):
        self.project_path = project_path.resolve()

    def create_plan(
        self,
        tasks: list[dict],
        milestone_title: str = "",
        model: str | None = None,
        output_file: Path | None = None,
        previous_plan: ExecutionPlan | None = None,
        user_feedback: str | None = None,
    ) -> ExecutionPlan:
        """Dispatch planning agent with full project context, parse JSON plan.

        Args:
            tasks: List of task dicts with 'text' and optional 'prompt'.
            milestone_title: Title of the milestone being planned.
            model: Claude model to use (defaults to None = CLI default).
            output_file: Pre-generated output file for live monitoring.
            previous_plan: Previous plan for re-planning with feedback.
            user_feedback: User feedback for re-planning.

        Returns:
            ExecutionPlan with phases, agents, and success criteria.
        """
        from .dispatcher import dispatch_task, get_dispatch_output_path

        prompt = self._build_planning_prompt(
            tasks, milestone_title, previous_plan, user_feedback
        )

        if output_file is None:
            _session_id, output_file = get_dispatch_output_path(self.project_path)

        result = dispatch_task(
            prompt=prompt,
            working_dir=self.project_path,
            output_file=output_file,
            model=model,
            timeout_seconds=600,
        )

        raw_output = result.output or ""

        if not result.success:
            logger.error("Planning agent failed: %s", result.error_message)
            return ExecutionPlan(
                summary=f"Planning failed: {result.error_message}",
                phases=[],
                success_criteria=[],
                estimated_total_agents=0,
                warnings=[result.error_message or "Unknown error"],
                raw_output=raw_output,
            )

        # Parse JSON from output
        parse_error: Exception | None = None
        try:
            plan_dict = self._extract_json(raw_output)
            return self._parse_plan(plan_dict, raw_output)
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            parse_error = exc

        # Fallback: check if the agent wrote a file instead of stdout
        plan_dict = self._try_read_agent_file(raw_output)
        if plan_dict is not None:
            try:
                return self._parse_plan(plan_dict, raw_output)
            except (ValueError, KeyError) as inner_exc:
                parse_error = inner_exc

        logger.error("Failed to parse planning agent output: %s", parse_error)
        return ExecutionPlan(
            summary=f"Failed to parse plan: {parse_error}",
            phases=[],
            success_criteria=[],
            estimated_total_agents=0,
            warnings=[f"JSON parsing failed: {parse_error}"],
            raw_output=raw_output,
        )

    def verify_completion(
        self,
        tasks: list[dict],
        plan: ExecutionPlan,
        model: str | None = None,
        output_file: Path | None = None,
        agent_statuses: list[dict] | None = None,
    ) -> VerificationResult:
        """Dispatch verification agent that reviews code against success criteria.

        Args:
            tasks: Original task list.
            plan: The executed plan with success criteria.
            model: Claude model to use.
            output_file: Pre-generated output file for live monitoring.
            agent_statuses: List of dicts with agent execution outcomes
                (task_text, status, error, group_id, phase_id).

        Returns:
            VerificationResult with per-criterion pass/fail.
        """
        from .dispatcher import dispatch_task, get_dispatch_output_path

        if output_file is None:
            _session_id, output_file = get_dispatch_output_path(self.project_path)

        # Step 1: Run quality gates if available
        gate_results = self._run_quality_gates()

        # Step 2: Dispatch verification agent
        criteria_text = "\n".join(
            f"{i + 1}. {c}" for i, c in enumerate(plan.success_criteria)
        )
        gate_summary = ""
        if gate_results:
            gate_lines = []
            for gr in gate_results.get("results", []):
                gate_lines.append(f"- {gr.get('name', '?')}: {gr.get('status', '?')} — {gr.get('message', '')}")
            if gate_lines:
                gate_summary = "\n## Quality Gate Results\n" + "\n".join(gate_lines)

        agent_status_section = ""
        if agent_statuses:
            status_lines = []
            failed_count = 0
            for a in agent_statuses:
                s = a.get("status", "unknown")
                label = f"Agent {a.get('group_id', '?')} (phase {a.get('phase_id', '?')}): {s}"
                if a.get("error"):
                    label += f" — {a['error']}"
                    failed_count += 1
                status_lines.append(f"- {label} | task: {a.get('task_text', '?')}")
            agent_status_section = (
                "\n## Agent Execution Results (FACTUAL — use these for completion criteria)\n"
                + "\n".join(status_lines)
                + f"\n\nTotal agents: {len(agent_statuses)}, "
                + f"succeeded: {sum(1 for a in agent_statuses if a.get('status') == 'succeeded')}, "
                + f"failed: {failed_count}"
                + "\n\nIMPORTANT: For any criterion about 'all tasks completed without errors', "
                + "use the agent execution results above as the source of truth, NOT file existence."
            )

        verify_prompt = f"""You are verifying whether a milestone's implementation meets its success criteria.

## Success Criteria
{criteria_text}
{gate_summary}
{agent_status_section}

## Instructions
Check each criterion by examining the codebase. For each criterion:
1. Look for the expected files, code, or behavior
2. Determine if it passes or fails
3. Provide evidence (file paths, command output references, etc.)
4. For criteria about task completion or errors, cross-reference the Agent Execution Results above

Output ONLY valid JSON:
{{
  "overall_pass": true/false,
  "criteria_results": [
    {{
      "criterion": "The criterion text",
      "passed": true/false,
      "evidence": "What you found",
      "notes": "Any additional context"
    }}
  ],
  "summary": "Brief overall assessment"
}}"""

        result = dispatch_task(
            prompt=verify_prompt,
            working_dir=self.project_path,
            output_file=output_file,
            model=model,
            timeout_seconds=600,
        )

        raw_output = result.output or ""

        if not result.success:
            return VerificationResult(
                overall_pass=False,
                criteria_results=[],
                summary=f"Verification agent failed: {result.error_message}",
                raw_output=raw_output,
            )

        try:
            vr_dict = self._extract_json(raw_output)
            return self._parse_verification(vr_dict, raw_output)
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            return VerificationResult(
                overall_pass=False,
                criteria_results=[],
                summary=f"Failed to parse verification output: {exc}",
                raw_output=raw_output,
            )

    def _build_planning_prompt(
        self,
        tasks: list[dict],
        milestone_title: str,
        previous_plan: ExecutionPlan | None,
        user_feedback: str | None,
    ) -> str:
        """Assemble the richest possible context for the planning agent."""
        ctx = self._get_project_context()

        # Format tasks with their custom prompts
        task_lines = []
        for i, task in enumerate(tasks):
            text = task.get("text", "")
            prompt = task.get("prompt", "")
            line = f"{i + 1}. {text}"
            if prompt and prompt != text:
                line += f"\n     Custom prompt: {prompt}"
            else:
                line += "\n     Custom prompt: None"
            task_lines.append(line)
        tasks_text = "\n".join(task_lines)

        # Check for pre-defined agent groups in the ROADMAP
        agent_groups = self._get_agent_groups(milestone_title)
        agent_group_section = ""
        grouping_rule = "- Target 2-5 agents total, never one agent per task"
        if agent_groups:
            agent_group_section = self._format_agent_groups(agent_groups)
            grouping_rule = "- Use the pre-defined agent groups above — do NOT re-group or split tasks differently"

        if previous_plan and user_feedback:
            # Re-planning prompt
            prev_json = json.dumps(self._plan_to_dict(previous_plan), indent=2)
            return f"""You are an expert software architect revising a parallel execution plan.

## Previous Plan
{prev_json}

## User Feedback
{user_feedback}

## Project Context
{ctx.get('conventions', '(not available)')[:6000]}

## Project File Structure
{ctx.get('file_tree', '(not available)')[:4000]}
{agent_group_section}

## Instructions
First, briefly describe what changes you're making to the plan based on the user's feedback.
Then output the revised JSON plan in the same format as the previous plan.
Keep the same level of detail in agent_prompt fields."""

        return f"""You are an expert software architect planning the parallel execution of a milestone's tasks.
You have deep understanding of the project's architecture, conventions, and codebase.

## Project Conventions (from CLAUDE.md)
{ctx.get('conventions', '(not available)')[:12000]}

## Roadmap Context
{ctx.get('roadmap_status', '(not available)')[:2000]}

## Project File Structure
{ctx.get('file_tree', '(not available)')[:8000]}

## Recently Modified Files
{ctx.get('recent_changes', '(not available)')[:2000]}

## Milestone: {milestone_title}
## Tasks to Execute
{tasks_text}
{agent_group_section}

## Your Job

IMPORTANT: First, write a brief analysis section describing:
- What themes/categories you see in the tasks
- Which tasks have dependencies on each other
- How you plan to group them into agents
- Any potential file conflicts between parallel agents

Then, output the execution plan as a JSON block.

Create an execution plan that:
1. Groups tasks by THEME (backend core, frontend UI, API/config, tests, etc.)
2. Determines execution ORDER — which tasks must complete before others can start
3. Assigns tasks to AGENTS — each agent gets a themed batch to run sequentially
4. Writes DETAILED IMPLEMENTATION PROMPTS for each agent — not just the raw task text, but rich prompts with:
   - Specific files to create/modify (based on the project structure above)
   - Code patterns to follow (from conventions)
   - What other agents are doing in parallel (so they don't conflict)
   - Clear completion criteria per task
5. Defines SUCCESS CRITERIA — concrete, verifiable checks for the milestone

After your analysis, output the plan as JSON:

```json
{{
  "summary": "Brief strategy description",
  "phases": [
    {{
      "phase_id": 0,
      "name": "Phase name",
      "description": "Why this phase exists",
      "parallel": true,
      "agents": [
        {{
          "agent_id": 0,
          "theme": "Agent theme name",
          "task_indices": [0, 2, 5],
          "rationale": "Why these tasks belong together",
          "agent_prompt": "DETAILED implementation prompt for this agent..."
        }}
      ]
    }}
  ],
  "success_criteria": [
    "All new Python modules have corresponding test files",
    "Frontend builds without TypeScript errors"
  ],
  "estimated_total_agents": 3,
  "warnings": ["Any dependency risks or concerns"]
}}
```

CRITICAL OUTPUT RULES:
- You MUST output the JSON plan directly to stdout — do NOT write files to disk
- Do NOT create any .md, .json, or other files — your ONLY output is text to stdout
- The JSON block MUST appear in your stdout output wrapped in ```json ... ``` fences
- Even for large plans with many tasks, output everything to stdout
- All IDs (agent_id, phase_id) MUST be plain integers (0, 1, 2, ...) — NOT strings like "1A"

Planning rules:
{grouping_rule}
- Group by theme and semantic dependency, not just file names
- agent_prompt MUST be detailed enough for an agent to work independently
- Success criteria MUST be concrete (runnable commands, checkable file existence, etc.)
- If a task depends on another task's output, they must be in sequential phases
- task_indices are 0-based indices into the task list above

## Cross-file dependency rules (IMPORTANT)
When tasks create new files that must be registered/imported elsewhere, the agent_prompt MUST include
the registration step. Common patterns in this project:
- New Python route file in `sidecar/api/routes/` → MUST also add import + `app.include_router(...)` in `server.py`
- New React component → MUST also add it to any parent component or route that renders it
- New Python module in `src/core/` → MUST also update `__init__.py` if one exists
- New test file → should import from the module it tests
Do NOT assume a separate agent will wire things up — each agent must complete the full integration for its files."""

    def _get_project_context(self) -> dict:
        """Gather all project context for the planning agent."""
        ctx: dict[str, str] = {}

        # Read CLAUDE.md
        claude_md = self.project_path / "CLAUDE.md"
        if claude_md.exists():
            try:
                ctx["conventions"] = claude_md.read_text(encoding="utf-8")[:12000]
            except OSError:
                ctx["conventions"] = "(failed to read CLAUDE.md)"
        else:
            ctx["conventions"] = "(no CLAUDE.md found)"

        # Read ROADMAP.md status
        roadmap_md = self.project_path / ".claude" / "planning" / "ROADMAP.md"
        if roadmap_md.exists():
            try:
                content = roadmap_md.read_text(encoding="utf-8")
                # Extract just the status/progress sections
                ctx["roadmap_status"] = content[:2000]
            except OSError:
                ctx["roadmap_status"] = "(failed to read ROADMAP.md)"
        else:
            ctx["roadmap_status"] = "(no ROADMAP.md found)"

        # Get project file tree
        ctx["file_tree"] = self._get_project_tree()

        # Get recent changes
        ctx["recent_changes"] = self._get_recent_changes()

        return ctx

    def _get_project_tree(self, max_chars: int = 8000) -> str:
        """Get truncated git ls-files output."""
        try:
            result = subprocess.run(
                ["git", "ls-files"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return "(git ls-files failed)"
            output = result.stdout.strip()
            if len(output) > max_chars:
                return output[:max_chars] + "\n... (truncated)"
            return output
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return "(git not available)"

    def _get_recent_changes(self, count: int = 5) -> str:
        """Get recent commit log with changed files."""
        try:
            result = subprocess.run(
                ["git", "log", "--name-only", f"-{count}", "--oneline"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return "(git log failed)"
            return result.stdout.strip()[:2000]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return "(git not available)"

    def _get_agent_groups(self, milestone_title: str) -> list:
        """Extract pre-defined agent groups from ROADMAP ### headings."""
        try:
            from ..core.roadmap import Roadmap

            roadmap_path = self.project_path / ".claude" / "planning" / "ROADMAP.md"
            if not roadmap_path.exists():
                return []
            roadmap = Roadmap.parse(roadmap_path)
            return roadmap.extract_agent_groups(milestone_title)
        except Exception as exc:
            logger.debug("Failed to extract agent groups: %s", exc)
            return []

    @staticmethod
    def _format_agent_groups(agent_groups: list) -> str:
        """Format agent groups as a planning constraint section."""
        lines = [
            "",
            "## Pre-defined Agent Groups (MUST follow)",
            "The milestone author has pre-defined agent groupings. You MUST use these exact groupings.",
            "Do NOT re-group or split tasks differently.",
            "",
        ]
        for i, group in enumerate(agent_groups):
            indices_str = ", ".join(str(idx) for idx in group.task_indices)
            lines.append(f"**Group {i + 1}: {group.name}** — task_indices: [{indices_str}]")
        lines.append("")
        lines.append("Determine the execution order (which groups can run in parallel vs sequential)")
        lines.append("and write detailed agent_prompt for each group. Do NOT change the task-to-group assignments.")
        return "\n".join(lines)

    def _run_quality_gates(self) -> dict | None:
        """Run quality gates and return results dict."""
        try:
            from .gates import QualityGateRunner

            runner = QualityGateRunner(self.project_path)
            runner.load_config()
            report = runner.run_all_gates(session_id=None)
            return {
                "results": [
                    {
                        "name": r.name,
                        "status": r.status,
                        "message": r.message,
                        "duration_seconds": r.duration_seconds,
                    }
                    for r in report.results
                ],
            }
        except (ImportError, Exception) as exc:
            logger.debug("Quality gates not available: %s", exc)
            return None

    def _try_read_agent_file(self, raw_output: str) -> dict | None:
        """Fallback: if the agent wrote a file instead of stdout, try to read it.

        Some models write plan files to disk for large plans. Look for file paths
        in the output and try to extract JSON from them.
        """
        # Look for file paths the agent mentioned writing
        file_refs = re.findall(
            r'(?:saved|written|created|output).*?[`"\']?(/[^\s`"\']+\.(?:json|md))[`"\']?',
            raw_output, re.IGNORECASE,
        )
        # Also check common patterns
        for pattern in ["EXECUTION-PLAN*.md", "EXECUTION-PLAN*.json", "plan*.json"]:
            import glob as glob_mod
            matches = glob_mod.glob(str(self.project_path / pattern))
            file_refs.extend(matches)

        for path_str in file_refs:
            try:
                path = Path(path_str)
                if not path.exists():
                    continue
                content = path.read_text(encoding="utf-8")
                result = self._extract_json(content)
                # Clean up the file the agent created
                try:
                    path.unlink()
                except OSError:
                    pass
                logger.info("Recovered plan from agent-written file: %s", path)
                return result
            except (ValueError, json.JSONDecodeError, OSError):
                continue
        return None

    @staticmethod
    def _extract_json(output: str) -> dict:
        """Extract JSON object from mixed text output using brace counting.

        Finds the first top-level { ... } block in the output and parses it.
        Handles cases where Claude wraps JSON in markdown code fences.
        """
        # First try: look for ```json ... ``` blocks
        json_block = re.search(r"```(?:json)?\s*\n({.*?})\s*\n```", output, re.DOTALL)
        if json_block:
            return json.loads(json_block.group(1))

        # Second try: find the first { and count braces to find the matching }
        start = output.find("{")
        if start == -1:
            raise ValueError("No JSON object found in output")

        depth = 0
        in_string = False
        escape_next = False

        for i in range(start, len(output)):
            ch = output[i]

            if escape_next:
                escape_next = False
                continue

            if ch == "\\":
                escape_next = True
                continue

            if ch == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(output[start : i + 1])

        raise ValueError("No complete JSON object found in output")

    @staticmethod
    def _parse_plan(plan_dict: dict, raw_output: str) -> ExecutionPlan:
        """Parse and validate a plan dictionary into an ExecutionPlan."""
        phases = []
        for phase_data in plan_dict.get("phases", []):
            agents = []
            for idx, agent_data in enumerate(phase_data.get("agents", [])):
                # Coerce agent_id to int — AI sometimes returns "1A", "2B", etc.
                raw_id = agent_data.get("agent_id", idx)
                try:
                    agent_id = int(raw_id)
                except (ValueError, TypeError):
                    agent_id = idx
                agents.append(
                    AgentAssignment(
                        agent_id=agent_id,
                        theme=agent_data.get("theme", ""),
                        task_indices=agent_data.get("task_indices", []),
                        rationale=agent_data.get("rationale", ""),
                        agent_prompt=agent_data.get("agent_prompt", ""),
                    )
                )
            raw_phase_id = phase_data.get("phase_id", len(phases))
            try:
                phase_id = int(raw_phase_id)
            except (ValueError, TypeError):
                phase_id = len(phases)
            phases.append(
                ExecutionPhase(
                    phase_id=phase_id,
                    name=phase_data.get("name", ""),
                    description=phase_data.get("description", ""),
                    parallel=phase_data.get("parallel", False),
                    agents=agents,
                )
            )

        return ExecutionPlan(
            summary=plan_dict.get("summary", ""),
            phases=phases,
            success_criteria=plan_dict.get("success_criteria", []),
            estimated_total_agents=plan_dict.get("estimated_total_agents", 0),
            warnings=plan_dict.get("warnings", []),
            raw_output=raw_output,
        )

    @staticmethod
    def _parse_verification(vr_dict: dict, raw_output: str) -> VerificationResult:
        """Parse verification result dictionary."""
        criteria_results = []
        for cr_data in vr_dict.get("criteria_results", []):
            criteria_results.append(
                CriterionResult(
                    criterion=cr_data.get("criterion", ""),
                    passed=cr_data.get("passed", False),
                    evidence=cr_data.get("evidence", ""),
                    notes=cr_data.get("notes", ""),
                )
            )

        return VerificationResult(
            overall_pass=vr_dict.get("overall_pass", False),
            criteria_results=criteria_results,
            summary=vr_dict.get("summary", ""),
            raw_output=raw_output,
        )

    @staticmethod
    def _plan_to_dict(plan: ExecutionPlan) -> dict:
        """Convert ExecutionPlan back to a dict for re-planning."""
        return {
            "summary": plan.summary,
            "phases": [
                {
                    "phase_id": phase.phase_id,
                    "name": phase.name,
                    "description": phase.description,
                    "parallel": phase.parallel,
                    "agents": [
                        {
                            "agent_id": a.agent_id,
                            "theme": a.theme,
                            "task_indices": a.task_indices,
                            "rationale": a.rationale,
                            "agent_prompt": a.agent_prompt,
                        }
                        for a in phase.agents
                    ],
                }
                for phase in plan.phases
            ],
            "success_criteria": plan.success_criteria,
            "estimated_total_agents": plan.estimated_total_agents,
            "warnings": plan.warnings,
        }
