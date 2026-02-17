"""Tests for the AI-orchestrated parallel execution engine."""

import asyncio
import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.parallel_orchestrator import (
    AgentSlot,
    MergeResult,
    ParallelBatchStatus,
    ParallelOrchestrator,
)
from src.agents.planning_agent import (
    AgentAssignment,
    CriterionResult,
    ExecutionPlan,
    ExecutionPhase,
    VerificationResult,
)
from src.core.worktree_manager import WorktreeManager


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
        {"text": "Add utility functions to src/core/utils.py", "prompt": "Add helper functions"},
        {"text": "Create tests/test_helpers.py", "prompt": "Write tests"},
        {"text": "Update src/components/Header.tsx", "prompt": "Fix header layout"},
    ]


@pytest.fixture
def sequential_plan():
    """ExecutionPlan with a single sequential phase."""
    return ExecutionPlan(
        summary="Sequential plan",
        phases=[
            ExecutionPhase(
                phase_id=0,
                name="All Tasks",
                description="Run everything sequentially",
                parallel=False,
                agents=[
                    AgentAssignment(
                        agent_id=0,
                        theme="All",
                        task_indices=[0, 1, 2],
                        rationale="Single agent",
                        agent_prompt="Do all three tasks",
                    ),
                ],
            ),
        ],
        success_criteria=["Tests pass"],
        estimated_total_agents=1,
        warnings=[],
    )


@pytest.fixture
def parallel_plan():
    """ExecutionPlan with a parallel phase."""
    return ExecutionPlan(
        summary="Parallel plan",
        phases=[
            ExecutionPhase(
                phase_id=0,
                name="Parallel Work",
                description="Run tasks in parallel",
                parallel=True,
                agents=[
                    AgentAssignment(
                        agent_id=0,
                        theme="Backend",
                        task_indices=[0],
                        rationale="Core module",
                        agent_prompt="Create utils.py",
                    ),
                    AgentAssignment(
                        agent_id=1,
                        theme="Tests",
                        task_indices=[1],
                        rationale="Test module",
                        agent_prompt="Create test file",
                    ),
                    AgentAssignment(
                        agent_id=2,
                        theme="Frontend",
                        task_indices=[2],
                        rationale="UI component",
                        agent_prompt="Fix header",
                    ),
                ],
            ),
        ],
        success_criteria=["All pass"],
        estimated_total_agents=3,
        warnings=[],
    )


@pytest.fixture
def mixed_plan():
    """ExecutionPlan with both sequential and parallel phases."""
    return ExecutionPlan(
        summary="Mixed plan",
        phases=[
            ExecutionPhase(
                phase_id=0,
                name="Foundation",
                description="Sequential foundation",
                parallel=False,
                agents=[
                    AgentAssignment(
                        agent_id=0,
                        theme="Backend",
                        task_indices=[0],
                        rationale="Core first",
                        agent_prompt="Create utils.py",
                    ),
                ],
            ),
            ExecutionPhase(
                phase_id=1,
                name="Parallel Work",
                description="Tests and frontend in parallel",
                parallel=True,
                agents=[
                    AgentAssignment(
                        agent_id=1,
                        theme="Tests",
                        task_indices=[1],
                        rationale="Tests",
                        agent_prompt="Write tests",
                    ),
                    AgentAssignment(
                        agent_id=2,
                        theme="Frontend",
                        task_indices=[2],
                        rationale="UI",
                        agent_prompt="Fix header",
                    ),
                ],
            ),
        ],
        success_criteria=["Tests pass", "Build succeeds"],
        estimated_total_agents=3,
        warnings=["Watch dependencies"],
    )


@pytest.fixture
def mock_verification():
    """Mock verification and finalize dependencies for tests that complete successfully."""
    mock_vr = VerificationResult(
        overall_pass=True,
        criteria_results=[],
        summary="All criteria passed",
    )
    with patch(
        "src.agents.planning_agent.PlanningAgent.verify_completion",
        return_value=mock_vr,
    ), patch(
        "src.agents.dispatcher.get_dispatch_output_path",
        return_value=("test-session", Path("/tmp/test-verify.log")),
    ):
        yield mock_vr


class TestAgentSlot:
    """Tests for AgentSlot dataclass."""

    def test_defaults(self):
        slot = AgentSlot(
            task_index=0,
            task_text="Do something",
            prompt="prompt",
        )
        assert slot.status == "pending"
        assert slot.worktree_path is None
        assert slot.output_file is None
        assert slot.started_at is None
        assert slot.error is None
        assert slot.cost_estimate == 0.0
        assert slot.group_id == 0
        assert slot.phase_id == 0

    def test_with_group_phase(self):
        slot = AgentSlot(
            task_index=1,
            task_text="Task",
            prompt="prompt",
            group_id=2,
            phase_id=1,
        )
        assert slot.group_id == 2
        assert slot.phase_id == 1


class TestMergeResult:
    """Tests for MergeResult dataclass."""

    def test_clean_merge(self):
        mr = MergeResult(branch="test-branch", success=True, message="Merged")
        assert mr.conflict_files == []
        assert mr.resolution_method == "clean"

    def test_conflict_merge(self):
        mr = MergeResult(
            branch="test-branch",
            success=False,
            conflict_files=["file.py"],
            resolution_method="conflict",
            message="Merge conflict",
        )
        assert not mr.success
        assert len(mr.conflict_files) == 1


class TestParallelBatchStatus:
    """Tests for ParallelBatchStatus dataclass."""

    def test_defaults(self):
        status = ParallelBatchStatus(batch_id="test-batch")
        assert status.phase == "idle"
        assert status.current_phase_id == 0
        assert status.current_phase_name == ""
        assert status.agents == []
        assert status.merge_results == []
        assert status.verification is None
        assert status.plan_summary == ""
        assert status.total_cost == 0.0
        assert status.error is None


class TestParallelOrchestrator:
    """Tests for ParallelOrchestrator."""

    def test_init(self, git_repo):
        orch = ParallelOrchestrator(git_repo)
        assert orch.project_path == git_repo.resolve()

    def test_generate_batch_id(self):
        """Batch IDs have expected format."""
        bid = ParallelOrchestrator.generate_batch_id()
        assert bid.startswith("par-")
        assert len(bid) > 20

    def test_generate_batch_id_unique(self):
        """Each generated batch ID is unique."""
        ids = {ParallelOrchestrator.generate_batch_id() for _ in range(10)}
        assert len(ids) == 10

    def test_get_status_unknown_batch(self, git_repo):
        """get_status returns None for unknown batch."""
        orch = ParallelOrchestrator(git_repo)
        assert orch.get_status("nonexistent") is None

    def test_cancel_batch_unknown(self, git_repo):
        """cancel_batch returns False for unknown batch."""
        orch = ParallelOrchestrator(git_repo)
        assert orch.cancel_batch("nonexistent") is False

    def test_cancel_batch_known(self, git_repo):
        """cancel_batch sets the cancel flag."""
        orch = ParallelOrchestrator(git_repo)
        batch_id = "test-cancel"
        orch._batches[batch_id] = ParallelBatchStatus(batch_id=batch_id)
        assert orch.cancel_batch(batch_id) is True
        assert orch._cancel_flags[batch_id] is True

    @pytest.mark.asyncio
    async def test_execute_plan_dirty_tree(self, git_repo, sample_tasks, sequential_plan):
        """execute_plan refuses to run on a dirty working tree (tracked modifications)."""
        # Modify a tracked file to make the tree dirty
        (git_repo / "README.md").write_text("# Modified content\n")

        orch = ParallelOrchestrator(git_repo)
        batch_id = orch.generate_batch_id()
        status = await orch.execute_plan(batch_id, sample_tasks, sequential_plan)

        assert status.phase == "failed"
        assert "uncommitted change" in status.error

    @pytest.mark.asyncio
    async def test_execute_plan_sequential(self, git_repo, sample_tasks, sequential_plan, mock_verification):
        """execute_plan handles a sequential plan."""
        orch = ParallelOrchestrator(git_repo)
        batch_id = orch.generate_batch_id()

        with patch(
            "src.agents.parallel_orchestrator.ParallelOrchestrator._run_single_dispatch",
            new_callable=AsyncMock,
        ) as mock_dispatch:
            async def fake_dispatch(slots, prompt, wt_path, bid):
                for slot in slots:
                    slot.status = "succeeded"
                    slot.started_at = datetime.now()
                    slot.finished_at = datetime.now()

            mock_dispatch.side_effect = fake_dispatch
            status = await orch.execute_plan(batch_id, sample_tasks, sequential_plan)

        assert status.batch_id == batch_id
        assert len(status.agents) == 3
        assert status.started_at is not None
        assert status.finished_at is not None

    @pytest.mark.asyncio
    async def test_execute_plan_parallel(self, git_repo, sample_tasks, parallel_plan, mock_verification):
        """execute_plan handles a parallel plan with multiple agents."""
        orch = ParallelOrchestrator(git_repo)
        batch_id = orch.generate_batch_id()

        with patch(
            "src.agents.parallel_orchestrator.ParallelOrchestrator._run_single_dispatch",
            new_callable=AsyncMock,
        ) as mock_dispatch:
            async def fake_dispatch(slots, prompt, wt_path, bid):
                # Simulate writing and committing in worktree
                new_file = wt_path / f"agent_output_{slots[0].task_index}.txt"
                new_file.write_text(f"Output from task {slots[0].task_index}")
                subprocess.run(["git", "add", "."], cwd=wt_path, capture_output=True)
                subprocess.run(
                    ["git", "commit", "-m", f"Agent {slots[0].group_id}"],
                    cwd=wt_path, capture_output=True,
                )
                for slot in slots:
                    slot.status = "succeeded"
                    slot.started_at = datetime.now()
                    slot.finished_at = datetime.now()

            mock_dispatch.side_effect = fake_dispatch
            status = await orch.execute_plan(batch_id, sample_tasks, parallel_plan)

        assert status.batch_id == batch_id
        assert len(status.agents) == 3
        # Should have merge results (one per agent in the parallel phase)
        assert len(status.merge_results) > 0

    @pytest.mark.asyncio
    async def test_execute_plan_mixed(self, git_repo, sample_tasks, mixed_plan, mock_verification):
        """execute_plan handles a mixed sequential + parallel plan."""
        orch = ParallelOrchestrator(git_repo)
        batch_id = orch.generate_batch_id()

        with patch(
            "src.agents.parallel_orchestrator.ParallelOrchestrator._run_single_dispatch",
            new_callable=AsyncMock,
        ) as mock_dispatch:
            async def fake_dispatch(slots, prompt, wt_path, bid):
                new_file = wt_path / f"output_{slots[0].task_index}.txt"
                new_file.write_text(f"Output from task {slots[0].task_index}")
                subprocess.run(["git", "add", "."], cwd=wt_path, capture_output=True)
                subprocess.run(
                    ["git", "commit", "-m", f"Task {slots[0].task_index}"],
                    cwd=wt_path, capture_output=True,
                )
                for slot in slots:
                    slot.status = "succeeded"
                    slot.started_at = datetime.now()
                    slot.finished_at = datetime.now()

            mock_dispatch.side_effect = fake_dispatch
            status = await orch.execute_plan(batch_id, sample_tasks, mixed_plan)

        assert status.batch_id == batch_id
        assert len(status.agents) == 3
        assert status.plan_summary == "Mixed plan"

    @pytest.mark.asyncio
    async def test_execute_plan_cancelled(self, git_repo, sample_tasks, parallel_plan):
        """execute_plan respects cancellation flag."""
        orch = ParallelOrchestrator(git_repo)
        batch_id = orch.generate_batch_id()

        with patch(
            "src.agents.parallel_orchestrator.ParallelOrchestrator._run_single_dispatch",
            new_callable=AsyncMock,
        ) as mock_dispatch:
            async def cancelling_dispatch(slots, prompt, wt_path, bid):
                # Cancel during first dispatch
                orch._cancel_flags[batch_id] = True
                for slot in slots:
                    slot.status = "cancelled"

            mock_dispatch.side_effect = cancelling_dispatch
            status = await orch.execute_plan(batch_id, sample_tasks, parallel_plan)

        assert status.phase == "cancelled"

    @pytest.mark.asyncio
    async def test_execute_plan_cleanup_on_failure(self, git_repo, sample_tasks, sequential_plan):
        """Worktrees are cleaned up even if execution fails."""
        orch = ParallelOrchestrator(git_repo)
        batch_id = orch.generate_batch_id()

        with patch(
            "src.agents.parallel_orchestrator.ParallelOrchestrator._run_single_dispatch",
            new_callable=AsyncMock,
            side_effect=RuntimeError("agent crashed"),
        ):
            status = await orch.execute_plan(batch_id, sample_tasks, sequential_plan)

        assert status.finished_at is not None
        worktree_dir = git_repo / ".cantina-worktrees"
        if worktree_dir.exists():
            remaining = list(worktree_dir.iterdir())
            assert len(remaining) == 0

    @pytest.mark.asyncio
    async def test_execute_plan_get_status(self, git_repo, sample_tasks, sequential_plan, mock_verification):
        """get_status returns the batch status during/after execution."""
        orch = ParallelOrchestrator(git_repo)
        batch_id = orch.generate_batch_id()

        with patch(
            "src.agents.parallel_orchestrator.ParallelOrchestrator._run_single_dispatch",
            new_callable=AsyncMock,
        ) as mock_dispatch:
            async def fake_dispatch(slots, prompt, wt_path, bid):
                for slot in slots:
                    slot.status = "succeeded"
                    slot.started_at = datetime.now()
                    slot.finished_at = datetime.now()

            mock_dispatch.side_effect = fake_dispatch
            await orch.execute_plan(batch_id, sample_tasks, sequential_plan)

        status = orch.get_status(batch_id)
        assert status is not None
        assert status.batch_id == batch_id

    def test_build_agent_slots(self, git_repo, sample_tasks, mixed_plan):
        """_build_agent_slots creates slots for all tasks in the plan."""
        orch = ParallelOrchestrator(git_repo)
        slots = orch._build_agent_slots(sample_tasks, mixed_plan)

        assert len(slots) == 3
        # Check group_id and phase_id assignments
        idx_to_slot = {s.task_index: s for s in slots}
        assert idx_to_slot[0].group_id == 0
        assert idx_to_slot[0].phase_id == 0
        assert idx_to_slot[1].group_id == 1
        assert idx_to_slot[1].phase_id == 1
        assert idx_to_slot[2].group_id == 2
        assert idx_to_slot[2].phase_id == 1

    def test_build_agent_slots_deduplication(self, git_repo, sample_tasks):
        """_build_agent_slots doesn't create duplicate slots for the same task."""
        plan = ExecutionPlan(
            summary="Dup test",
            phases=[
                ExecutionPhase(
                    phase_id=0,
                    name="P1",
                    description="",
                    parallel=False,
                    agents=[
                        AgentAssignment(
                            agent_id=0,
                            theme="A",
                            task_indices=[0, 1],
                            rationale="",
                            agent_prompt="",
                        ),
                        AgentAssignment(
                            agent_id=1,
                            theme="B",
                            task_indices=[1, 2],  # task 1 appears twice
                            rationale="",
                            agent_prompt="",
                        ),
                    ],
                ),
            ],
            success_criteria=[],
            estimated_total_agents=2,
            warnings=[],
        )
        orch = ParallelOrchestrator(git_repo)
        slots = orch._build_agent_slots(sample_tasks, plan)
        task_indices = [s.task_index for s in slots]
        assert len(set(task_indices)) == len(task_indices)  # No duplicates

    @pytest.mark.asyncio
    async def test_execute_plan_finalize_commits(self, git_repo, sample_tasks, sequential_plan, mock_verification):
        """Finalize phase stages leftover files, commits, and marks roadmap items complete."""
        # Create an untracked file — won't block execution (clean check ignores untracked)
        (git_repo / "leftover.txt").write_text("leftover from agent")

        # Create a roadmap with matching task items
        roadmap_dir = git_repo / ".claude" / "planning"
        roadmap_dir.mkdir(parents=True)
        roadmap_file = roadmap_dir / "ROADMAP.md"
        roadmap_file.write_text(
            "# Roadmap\n\n## Milestone 1: Test\n"
            "- [ ] Add utility functions to src/core/utils.py\n"
            "- [ ] Create tests/test_helpers.py\n"
            "- [ ] Update src/components/Header.tsx\n"
        )

        orch = ParallelOrchestrator(git_repo)
        batch_id = orch.generate_batch_id()

        with patch(
            "src.agents.parallel_orchestrator.ParallelOrchestrator._run_single_dispatch",
            new_callable=AsyncMock,
        ) as mock_dispatch:
            async def fake_dispatch(slots, prompt, wt_path, bid):
                for slot in slots:
                    slot.status = "succeeded"
                    slot.started_at = datetime.now()
                    slot.finished_at = datetime.now()

            mock_dispatch.side_effect = fake_dispatch
            status = await orch.execute_plan(batch_id, sample_tasks, sequential_plan)

        assert status.phase == "complete"
        assert status.finalize_message is not None
        assert "committed as" in status.finalize_message.lower()
        assert "marked 3 item(s) complete" in status.finalize_message.lower()

        # Verify the file was actually committed
        wm = WorktreeManager(git_repo)
        assert wm.is_working_tree_clean()
        # Check git log for the finalize commit
        log_out, _ = wm._run_git("log", "--oneline", "-1")
        assert "feat(parallel)" in log_out

        # Verify roadmap items were marked complete
        content = roadmap_file.read_text()
        assert "- [x] Add utility functions" in content
        assert "- [x] Create tests/test_helpers.py" in content
        assert "- [x] Update src/components/Header.tsx" in content

    @pytest.mark.asyncio
    async def test_execute_plan_skip_finalize_on_cancel(self, git_repo, sample_tasks, parallel_plan):
        """Cancelled batches skip verification and finalizing."""
        orch = ParallelOrchestrator(git_repo)
        batch_id = orch.generate_batch_id()

        with patch(
            "src.agents.parallel_orchestrator.ParallelOrchestrator._run_single_dispatch",
            new_callable=AsyncMock,
        ) as mock_dispatch:
            async def cancelling_dispatch(slots, prompt, wt_path, bid):
                orch._cancel_flags[batch_id] = True
                for slot in slots:
                    slot.status = "cancelled"

            mock_dispatch.side_effect = cancelling_dispatch
            status = await orch.execute_plan(batch_id, sample_tasks, parallel_plan)

        assert status.phase == "cancelled"
        assert status.verification is None
        assert status.finalize_message is None


class TestCommitWorktreeChanges:
    """Tests for _commit_worktree_changes — the fix that ensures agent work
    is committed to the worktree branch before the worktree is removed."""

    def test_commit_with_new_files(self, git_repo):
        """Files written in a worktree get committed."""
        wm = WorktreeManager(git_repo)
        info = wm.create_worktree("commit-test", 0)

        # Simulate agent writing files
        (info.path / "output.py").write_text("RESULT = 42\n")
        (info.path / "test_output.py").write_text("def test(): assert True\n")

        result = ParallelOrchestrator._commit_worktree_changes(info.path, "commit-test")
        assert result is True

        # Verify commit exists
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=info.path, capture_output=True, text=True,
        )
        assert "Agent work for batch commit-test" in log.stdout

        # Remove and merge — files should survive
        original_branch = wm.get_current_branch()
        wm.remove_worktree(info.path, force=True)
        success, _, _ = wm.merge_branch(info.branch, into=original_branch)
        assert success
        assert (git_repo / "output.py").exists()
        assert (git_repo / "test_output.py").exists()
        wm.delete_branch(info.branch)

    def test_commit_with_no_changes(self, git_repo):
        """Returns False when agent wrote nothing."""
        wm = WorktreeManager(git_repo)
        info = wm.create_worktree("empty-test", 0)

        # Don't write anything
        result = ParallelOrchestrator._commit_worktree_changes(info.path, "empty-test")
        assert result is False

        wm.remove_worktree(info.path, force=True)
        wm.delete_branch(info.branch)

    def test_commit_with_modified_files(self, git_repo):
        """Modified tracked files get committed."""
        wm = WorktreeManager(git_repo)
        info = wm.create_worktree("modify-test", 0)

        # Modify existing file
        (info.path / "README.md").write_text("# Modified by agent\n")

        result = ParallelOrchestrator._commit_worktree_changes(info.path, "modify-test")
        assert result is True

        original_branch = wm.get_current_branch()
        wm.remove_worktree(info.path, force=True)
        success, _, _ = wm.merge_branch(info.branch, into=original_branch)
        assert success
        assert (git_repo / "README.md").read_text() == "# Modified by agent\n"
        wm.delete_branch(info.branch)

    def test_commit_with_nested_dirs(self, git_repo):
        """New directories and nested files get committed."""
        wm = WorktreeManager(git_repo)
        info = wm.create_worktree("nested-test", 0)

        # Create nested structure
        components = info.path / "src" / "components"
        components.mkdir(parents=True)
        (components / "Widget.tsx").write_text("export function Widget() {}\n")
        tests = info.path / "tests"
        tests.mkdir()
        (tests / "test_widget.py").write_text("def test_widget(): pass\n")

        result = ParallelOrchestrator._commit_worktree_changes(info.path, "nested-test")
        assert result is True

        original_branch = wm.get_current_branch()
        wm.remove_worktree(info.path, force=True)
        success, _, _ = wm.merge_branch(info.branch, into=original_branch)
        assert success
        assert (git_repo / "src" / "components" / "Widget.tsx").exists()
        assert (git_repo / "tests" / "test_widget.py").exists()
        wm.delete_branch(info.branch)


class TestVerificationGate:
    """Tests that verification results gate roadmap marking."""

    @pytest.mark.asyncio
    async def test_failed_verification_still_marks_roadmap(self, git_repo, sample_tasks, sequential_plan):
        """When verification fails, roadmap items are still marked [x] based on agent success.
        Verification is informational — it notes issues but doesn't block completion."""
        # Set up roadmap
        roadmap_dir = git_repo / ".claude" / "planning"
        roadmap_dir.mkdir(parents=True)
        roadmap_file = roadmap_dir / "ROADMAP.md"
        roadmap_file.write_text(
            "# Roadmap\n\n## Milestone 1: Test\n"
            "- [ ] Add utility functions to src/core/utils.py\n"
            "- [ ] Create tests/test_helpers.py\n"
            "- [ ] Update src/components/Header.tsx\n"
        )

        # Mock verification to FAIL
        mock_vr = VerificationResult(
            overall_pass=False,
            criteria_results=[
                CriterionResult(
                    criterion="ruff passes",
                    passed=False,
                    evidence="lint errors",
                    notes="",
                ),
            ],
            summary="Tests failed",
        )

        orch = ParallelOrchestrator(git_repo)
        batch_id = orch.generate_batch_id()

        with patch(
            "src.agents.parallel_orchestrator.ParallelOrchestrator._run_single_dispatch",
            new_callable=AsyncMock,
        ) as mock_dispatch, patch(
            "src.agents.planning_agent.PlanningAgent.verify_completion",
            return_value=mock_vr,
        ), patch(
            "src.agents.dispatcher.get_dispatch_output_path",
            return_value=("test-session", Path("/tmp/test-verify.log")),
        ):
            async def fake_dispatch(slots, prompt, wt_path, bid):
                for slot in slots:
                    slot.status = "succeeded"
                    slot.started_at = datetime.now()
                    slot.finished_at = datetime.now()

            mock_dispatch.side_effect = fake_dispatch
            status = await orch.execute_plan(batch_id, sample_tasks, sequential_plan)

        assert status.phase == "complete"
        # Items ARE marked complete (agents succeeded)
        content = roadmap_file.read_text()
        assert "- [x] Add utility functions" in content
        assert "- [x] Create tests/test_helpers.py" in content
        assert "- [x] Update src/components/Header.tsx" in content
        # Verification issues are noted informally
        assert "verification noted" in (status.finalize_message or "").lower()

    @pytest.mark.asyncio
    async def test_passed_verification_marks_roadmap(self, git_repo, sample_tasks, sequential_plan):
        """When verification passes, roadmap items get marked [x]."""
        roadmap_dir = git_repo / ".claude" / "planning"
        roadmap_dir.mkdir(parents=True)
        roadmap_file = roadmap_dir / "ROADMAP.md"
        roadmap_file.write_text(
            "# Roadmap\n\n## Milestone 1: Test\n"
            "- [ ] Add utility functions to src/core/utils.py\n"
            "- [ ] Create tests/test_helpers.py\n"
            "- [ ] Update src/components/Header.tsx\n"
        )

        mock_vr = VerificationResult(
            overall_pass=True,
            criteria_results=[],
            summary="All passed",
        )

        orch = ParallelOrchestrator(git_repo)
        batch_id = orch.generate_batch_id()

        with patch(
            "src.agents.parallel_orchestrator.ParallelOrchestrator._run_single_dispatch",
            new_callable=AsyncMock,
        ) as mock_dispatch, patch(
            "src.agents.planning_agent.PlanningAgent.verify_completion",
            return_value=mock_vr,
        ), patch(
            "src.agents.dispatcher.get_dispatch_output_path",
            return_value=("test-session", Path("/tmp/test-verify.log")),
        ):
            async def fake_dispatch(slots, prompt, wt_path, bid):
                for slot in slots:
                    slot.status = "succeeded"
                    slot.started_at = datetime.now()
                    slot.finished_at = datetime.now()

            mock_dispatch.side_effect = fake_dispatch
            status = await orch.execute_plan(batch_id, sample_tasks, sequential_plan)

        assert status.phase == "complete"
        content = roadmap_file.read_text()
        assert "- [x] Add utility functions" in content
        assert "- [x] Create tests/test_helpers.py" in content
        assert "- [x] Update src/components/Header.tsx" in content
        assert "marked 3 item(s) complete" in (status.finalize_message or "").lower()
