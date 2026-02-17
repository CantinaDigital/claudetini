"""Tests for the AI-driven planning agent."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.agents.planning_agent import (
    AgentAssignment,
    CriterionResult,
    ExecutionPlan,
    ExecutionPhase,
    PlanningAgent,
    VerificationResult,
)


@pytest.fixture
def git_repo(tmp_path):
    """Create a real git repository with an initial commit."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path, capture_output=True,
    )
    readme = tmp_path / "README.md"
    readme.write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path, capture_output=True,
    )
    return tmp_path


@pytest.fixture
def sample_tasks():
    """Sample task list for testing."""
    return [
        {"text": "Add utility functions", "prompt": "Create src/core/utils.py"},
        {"text": "Write unit tests", "prompt": "Create tests/test_utils.py"},
        {"text": "Update documentation", "prompt": "Update README.md"},
    ]


@pytest.fixture
def sample_plan():
    """Pre-built ExecutionPlan for testing."""
    return ExecutionPlan(
        summary="Test plan with 2 phases",
        phases=[
            ExecutionPhase(
                phase_id=0,
                name="Foundation",
                description="Core utilities first",
                parallel=False,
                agents=[
                    AgentAssignment(
                        agent_id=0,
                        theme="Backend Core",
                        task_indices=[0],
                        rationale="Core module needed first",
                        agent_prompt="Create src/core/utils.py with helper functions",
                    ),
                ],
            ),
            ExecutionPhase(
                phase_id=1,
                name="Parallel Work",
                description="Tests and docs in parallel",
                parallel=True,
                agents=[
                    AgentAssignment(
                        agent_id=1,
                        theme="Tests",
                        task_indices=[1],
                        rationale="Tests for core module",
                        agent_prompt="Write tests for utils.py",
                    ),
                    AgentAssignment(
                        agent_id=2,
                        theme="Documentation",
                        task_indices=[2],
                        rationale="Update docs",
                        agent_prompt="Update README with new utilities",
                    ),
                ],
            ),
        ],
        success_criteria=["Tests pass", "README updated"],
        estimated_total_agents=3,
        warnings=[],
        raw_output="test output",
    )


class TestExtractJson:
    """Tests for _extract_json static method."""

    def test_clean_json(self):
        """Extract JSON from clean JSON string."""
        data = {"summary": "test", "phases": []}
        result = PlanningAgent._extract_json(json.dumps(data))
        assert result == data

    def test_json_in_text(self):
        """Extract JSON from mixed text output."""
        text = 'Here is the plan:\n\n{"summary": "test", "phases": []}\n\nDone!'
        result = PlanningAgent._extract_json(text)
        assert result["summary"] == "test"

    def test_json_in_code_fence(self):
        """Extract JSON from markdown code fence."""
        text = '```json\n{"summary": "test", "phases": []}\n```'
        result = PlanningAgent._extract_json(text)
        assert result["summary"] == "test"

    def test_json_in_code_fence_no_lang(self):
        """Extract JSON from code fence without language specifier."""
        text = '```\n{"summary": "test", "phases": []}\n```'
        result = PlanningAgent._extract_json(text)
        assert result["summary"] == "test"

    def test_nested_json(self):
        """Extract nested JSON with braces inside strings."""
        data = {
            "summary": "Plan with {braces}",
            "phases": [{"name": "test", "agents": []}],
        }
        text = f"Output:\n{json.dumps(data)}\nDone"
        result = PlanningAgent._extract_json(text)
        assert result["summary"] == "Plan with {braces}"

    def test_no_json_raises(self):
        """Raises ValueError when no JSON found."""
        with pytest.raises(ValueError, match="No JSON object found"):
            PlanningAgent._extract_json("No JSON here")

    def test_malformed_json_raises(self):
        """Raises error on malformed JSON."""
        with pytest.raises((json.JSONDecodeError, ValueError)):
            PlanningAgent._extract_json('{"incomplete": ')


class TestParsePlan:
    """Tests for _parse_plan static method."""

    def test_full_plan(self):
        """Parse a complete plan dictionary."""
        plan_dict = {
            "summary": "3 agents across 2 phases",
            "phases": [
                {
                    "phase_id": 0,
                    "name": "Phase 1",
                    "description": "Foundation",
                    "parallel": False,
                    "agents": [
                        {
                            "agent_id": 0,
                            "theme": "Backend",
                            "task_indices": [0, 1],
                            "rationale": "Core modules",
                            "agent_prompt": "Build the backend",
                        }
                    ],
                }
            ],
            "success_criteria": ["Tests pass"],
            "estimated_total_agents": 1,
            "warnings": ["Watch out"],
        }
        plan = PlanningAgent._parse_plan(plan_dict, "raw")
        assert plan.summary == "3 agents across 2 phases"
        assert len(plan.phases) == 1
        assert plan.phases[0].name == "Phase 1"
        assert not plan.phases[0].parallel
        assert len(plan.phases[0].agents) == 1
        assert plan.phases[0].agents[0].task_indices == [0, 1]
        assert plan.success_criteria == ["Tests pass"]
        assert plan.warnings == ["Watch out"]
        assert plan.raw_output == "raw"

    def test_missing_fields_defaults(self):
        """Missing fields use sensible defaults."""
        plan_dict = {"phases": [{"agents": [{}]}]}
        plan = PlanningAgent._parse_plan(plan_dict, "")
        assert plan.summary == ""
        assert plan.estimated_total_agents == 0
        assert plan.phases[0].phase_id == 0
        assert plan.phases[0].parallel is False

    def test_empty_phases(self):
        """Plan with empty phases list."""
        plan_dict = {"summary": "empty", "phases": []}
        plan = PlanningAgent._parse_plan(plan_dict, "")
        assert len(plan.phases) == 0


class TestPlanToDict:
    """Tests for _plan_to_dict static method."""

    def test_roundtrip(self, sample_plan):
        """Plan survives dict conversion roundtrip."""
        d = PlanningAgent._plan_to_dict(sample_plan)
        assert d["summary"] == sample_plan.summary
        assert len(d["phases"]) == 2
        assert d["phases"][0]["agents"][0]["agent_prompt"] == "Create src/core/utils.py with helper functions"
        assert d["success_criteria"] == ["Tests pass", "README updated"]


class TestParseVerification:
    """Tests for _parse_verification static method."""

    def test_full_verification(self):
        """Parse a complete verification result."""
        vr_dict = {
            "overall_pass": True,
            "criteria_results": [
                {
                    "criterion": "Tests pass",
                    "passed": True,
                    "evidence": "pytest exits 0",
                    "notes": "",
                },
                {
                    "criterion": "README updated",
                    "passed": False,
                    "evidence": "README.md unchanged",
                    "notes": "Needs manual update",
                },
            ],
            "summary": "1 of 2 passed",
        }
        vr = PlanningAgent._parse_verification(vr_dict, "raw")
        assert vr.overall_pass is True
        assert len(vr.criteria_results) == 2
        assert vr.criteria_results[0].passed is True
        assert vr.criteria_results[1].passed is False
        assert vr.summary == "1 of 2 passed"


class TestPromptConstruction:
    """Tests for prompt building."""

    def test_build_planning_prompt_initial(self, git_repo, sample_tasks):
        """Initial planning prompt includes tasks and project context."""
        agent = PlanningAgent(git_repo)
        prompt = agent._build_planning_prompt(
            sample_tasks, "Milestone 13", None, None
        )
        assert "Milestone: Milestone 13" in prompt
        assert "Add utility functions" in prompt
        assert "Write unit tests" in prompt
        assert "DETAILED IMPLEMENTATION PROMPTS" in prompt

    def test_build_planning_prompt_with_claude_md(self, git_repo, sample_tasks):
        """Planning prompt includes CLAUDE.md content when present."""
        (git_repo / "CLAUDE.md").write_text("# My Project\nUse Python 3.11+\n")
        agent = PlanningAgent(git_repo)
        prompt = agent._build_planning_prompt(sample_tasks, "", None, None)
        assert "My Project" in prompt

    def test_build_replanning_prompt(self, git_repo, sample_tasks, sample_plan):
        """Re-planning prompt includes previous plan and feedback."""
        agent = PlanningAgent(git_repo)
        prompt = agent._build_planning_prompt(
            sample_tasks, "Milestone 13", sample_plan, "Group tasks differently"
        )
        assert "Previous Plan" in prompt
        assert "User Feedback" in prompt
        assert "Group tasks differently" in prompt

    def test_build_planning_prompt_with_custom_prompts(self, git_repo):
        """Tasks with custom prompts are included."""
        tasks = [
            {"text": "Task A", "prompt": "Custom prompt for A"},
            {"text": "Task B"},
        ]
        agent = PlanningAgent(git_repo)
        prompt = agent._build_planning_prompt(tasks, "", None, None)
        assert "Custom prompt: Custom prompt for A" in prompt
        assert "Custom prompt: None" in prompt


class TestCreatePlan:
    """Tests for the create_plan method with mocked dispatch."""

    def test_successful_plan(self, git_repo, sample_tasks):
        """create_plan returns a parsed plan on success."""
        plan_json = json.dumps({
            "summary": "AI plan",
            "phases": [
                {
                    "phase_id": 0,
                    "name": "Phase 1",
                    "description": "Do stuff",
                    "parallel": True,
                    "agents": [
                        {
                            "agent_id": 0,
                            "theme": "Backend",
                            "task_indices": [0, 1, 2],
                            "rationale": "All related",
                            "agent_prompt": "Implement everything",
                        }
                    ],
                }
            ],
            "success_criteria": ["Tests pass"],
            "estimated_total_agents": 1,
            "warnings": [],
        })

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.output = f"Here is the plan:\n{plan_json}"
        mock_result.error_message = None

        with patch("src.agents.dispatcher.dispatch_task", return_value=mock_result), \
             patch("src.agents.dispatcher.get_dispatch_output_path", return_value=("sid", git_repo / "out.txt")):
            agent = PlanningAgent(git_repo)
            plan = agent.create_plan(sample_tasks, "Test Milestone")

        assert plan.summary == "AI plan"
        assert len(plan.phases) == 1
        assert plan.phases[0].agents[0].task_indices == [0, 1, 2]

    def test_failed_dispatch(self, git_repo, sample_tasks):
        """create_plan returns error plan when dispatch fails."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.output = ""
        mock_result.error_message = "CLI not found"

        with patch("src.agents.dispatcher.dispatch_task", return_value=mock_result), \
             patch("src.agents.dispatcher.get_dispatch_output_path", return_value=("sid", git_repo / "out.txt")):
            agent = PlanningAgent(git_repo)
            plan = agent.create_plan(sample_tasks)

        assert "failed" in plan.summary.lower() or "CLI not found" in plan.summary
        assert len(plan.phases) == 0
        assert len(plan.warnings) > 0

    def test_invalid_json_output(self, git_repo, sample_tasks):
        """create_plan handles invalid JSON in output."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.output = "This is not JSON at all"
        mock_result.error_message = None

        with patch("src.agents.dispatcher.dispatch_task", return_value=mock_result), \
             patch("src.agents.dispatcher.get_dispatch_output_path", return_value=("sid", git_repo / "out.txt")):
            agent = PlanningAgent(git_repo)
            plan = agent.create_plan(sample_tasks)

        assert len(plan.phases) == 0
        assert "parsing failed" in plan.warnings[0].lower() or "JSON" in plan.warnings[0]


class TestProjectContext:
    """Tests for project context gathering."""

    def test_get_project_tree(self, git_repo):
        """_get_project_tree returns git tracked files."""
        agent = PlanningAgent(git_repo)
        tree = agent._get_project_tree()
        assert "README.md" in tree

    def test_get_project_tree_truncation(self, git_repo):
        """_get_project_tree respects max_chars."""
        agent = PlanningAgent(git_repo)
        tree = agent._get_project_tree(max_chars=5)
        assert len(tree) <= 30  # 5 chars + "... (truncated)"

    def test_get_recent_changes(self, git_repo):
        """_get_recent_changes returns commit log."""
        agent = PlanningAgent(git_repo)
        changes = agent._get_recent_changes()
        assert "Initial commit" in changes

    def test_get_project_context_with_claude_md(self, git_repo):
        """_get_project_context reads CLAUDE.md when present."""
        (git_repo / "CLAUDE.md").write_text("# Project Guide\nUse Python")
        agent = PlanningAgent(git_repo)
        ctx = agent._get_project_context()
        assert "Project Guide" in ctx["conventions"]

    def test_get_project_context_no_claude_md(self, git_repo):
        """_get_project_context handles missing CLAUDE.md."""
        agent = PlanningAgent(git_repo)
        ctx = agent._get_project_context()
        assert "no CLAUDE.md" in ctx["conventions"]
