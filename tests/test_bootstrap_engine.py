"""Tests for bootstrap engine ArtifactGenerator abstraction and partial-failure handling."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.agents.bootstrap_engine import (
    AnalyzeGenerator,
    ArchitectureGenerator,
    ArtifactGenerator,
    BootstrapEngine,
    BootstrapResult,
    BootstrapStep,
    BootstrapStepType,
    ClaudeMdGenerator,
    DEFAULT_GENERATORS,
    GitignoreGenerator,
    RoadmapGenerator,
    StepResult,
)
from src.agents.dispatcher import DispatchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(
    project_path: Path,
    generators: list[ArtifactGenerator] | None = None,
) -> BootstrapEngine:
    """Create an engine with the prompts_dir mocked to exist."""
    with patch.object(Path, "exists", return_value=True):
        engine = BootstrapEngine(
            project_path=project_path,
            generators=generators,
        )
    # Point prompts_dir at the real templates so _load_prompt_template works
    engine.prompts_dir = Path(__file__).resolve().parent.parent / "src" / "agents" / "bootstrap_prompts"
    return engine


def _ok_dispatch(**overrides) -> DispatchResult:
    defaults = dict(success=True, output="analysis output")
    defaults.update(overrides)
    return DispatchResult(**defaults)


def _fail_dispatch(msg: str = "boom") -> DispatchResult:
    return DispatchResult(success=False, error_message=msg)


# ---------------------------------------------------------------------------
# Task 4.1 – ArtifactGenerator abstraction
# ---------------------------------------------------------------------------


class TestArtifactGeneratorProperties:
    """Generators expose correct metadata used by _build_steps."""

    def test_analyze_generator_metadata(self):
        gen = AnalyzeGenerator()
        assert gen.step_type == BootstrapStepType.ANALYZE
        assert gen.required is True
        assert gen.weight == 0.5
        assert gen.skip_if_exists is False

    def test_roadmap_generator_metadata(self):
        gen = RoadmapGenerator()
        assert gen.step_type == BootstrapStepType.ROADMAP
        assert gen.required is True
        assert gen.weight == 2.0

    def test_claude_md_generator_metadata(self):
        gen = ClaudeMdGenerator()
        assert gen.step_type == BootstrapStepType.CLAUDE_MD
        assert gen.required is True

    def test_gitignore_generator_metadata(self):
        gen = GitignoreGenerator()
        assert gen.step_type == BootstrapStepType.GITIGNORE
        assert gen.required is False
        assert gen.skip_if_exists is True

    def test_architecture_generator_metadata(self):
        gen = ArchitectureGenerator()
        assert gen.step_type == BootstrapStepType.ARCHITECTURE
        assert gen.required is False

    def test_output_paths(self, temp_dir):
        project = temp_dir / "proj"
        project.mkdir()

        assert AnalyzeGenerator().output_path(project) == project / ".bootstrap_analysis.md"
        assert RoadmapGenerator().output_path(project) == project / ".claude" / "planning" / "ROADMAP.md"
        assert ClaudeMdGenerator().output_path(project) == project / "CLAUDE.md"
        assert GitignoreGenerator().output_path(project) == project / ".gitignore"
        assert ArchitectureGenerator().output_path(project) == project / "docs" / "ARCHITECTURE.md"

    def test_default_generators_order(self):
        assert len(DEFAULT_GENERATORS) == 5
        assert DEFAULT_GENERATORS[0] is AnalyzeGenerator
        assert DEFAULT_GENERATORS[-1] is ArchitectureGenerator


class TestBuildPrompt:
    """ArtifactGenerator.build_prompt assembles prompts correctly."""

    def test_analysis_step_omits_analysis_context(self):
        gen = AnalyzeGenerator()
        prompt = gen.build_prompt("template body", Path("/out.md"), analysis_context="should be ignored")
        assert "Project Analysis" not in prompt
        assert "template body" in prompt
        assert "/out.md" in prompt

    def test_non_analysis_step_includes_context(self):
        gen = RoadmapGenerator()
        prompt = gen.build_prompt("template body", Path("/out.md"), analysis_context="ctx here")
        assert "## Project Analysis" in prompt
        assert "ctx here" in prompt
        assert "template body" in prompt

    def test_non_analysis_step_without_context(self):
        gen = RoadmapGenerator()
        prompt = gen.build_prompt("template body", Path("/out.md"), analysis_context=None)
        assert "Project Analysis" not in prompt


class TestBuildStepsFromGenerators:
    """_build_steps constructs BootstrapStep objects from generators."""

    def test_build_steps_returns_all_steps(self, temp_dir):
        project = temp_dir / "proj"
        project.mkdir()
        engine = _make_engine(project)
        steps = engine._build_steps()
        assert len(steps) == 5
        assert all(isinstance(s, BootstrapStep) for s in steps)

    def test_skip_git_removes_gitignore(self, temp_dir):
        project = temp_dir / "proj"
        project.mkdir()
        engine = _make_engine(project)
        steps = engine._build_steps(skip_git=True)
        types = [s.step_type for s in steps]
        assert BootstrapStepType.GITIGNORE not in types
        assert len(steps) == 4

    def test_skip_architecture_removes_arch(self, temp_dir):
        project = temp_dir / "proj"
        project.mkdir()
        engine = _make_engine(project)
        steps = engine._build_steps(skip_architecture=True)
        types = [s.step_type for s in steps]
        assert BootstrapStepType.ARCHITECTURE not in types
        assert len(steps) == 4

    def test_custom_generators(self, temp_dir):
        project = temp_dir / "proj"
        project.mkdir()
        engine = _make_engine(project, generators=[AnalyzeGenerator(), RoadmapGenerator()])
        steps = engine._build_steps()
        assert len(steps) == 2
        assert steps[0].step_type == BootstrapStepType.ANALYZE
        assert steps[1].step_type == BootstrapStepType.ROADMAP


class TestEstimateCost:
    """estimate_cost uses generator metadata."""

    def test_estimate_returns_expected_keys(self, temp_dir):
        project = temp_dir / "proj"
        project.mkdir()
        engine = _make_engine(project)
        est = engine.estimate_cost()
        assert "total_tokens" in est
        assert "cost_usd" in est
        assert "steps" in est
        assert est["steps"] == 5

    def test_skip_flags_reduce_cost(self, temp_dir):
        project = temp_dir / "proj"
        project.mkdir()
        engine = _make_engine(project)
        full = engine.estimate_cost()

        engine_skip = _make_engine(project)
        # Simulate skip by removing generators
        engine_skip._generators = [g for g in engine_skip._generators if g.step_type not in (BootstrapStepType.GITIGNORE, BootstrapStepType.ARCHITECTURE)]
        reduced = engine_skip.estimate_cost()
        assert reduced["total_tokens"] < full["total_tokens"]


# ---------------------------------------------------------------------------
# Task 4.11 – Partial failure handling
# ---------------------------------------------------------------------------


class TestBootstrapRequiredFailureMarksOverallFailure:
    """result.success=False when any required step fails."""

    @patch("src.agents.bootstrap_engine.dispatch_task")
    def test_required_failure_marks_overall_failure(self, mock_dispatch, temp_dir):
        project = temp_dir / "proj"
        project.mkdir()

        # Analyze succeeds, Roadmap fails (required)
        mock_dispatch.side_effect = [
            _ok_dispatch(),           # analyze
            _fail_dispatch("roadmap error"),  # roadmap (required)
            _ok_dispatch(),           # claude_md
            _ok_dispatch(),           # gitignore
            _ok_dispatch(),           # architecture
        ]

        engine = _make_engine(project)
        result = engine.bootstrap()

        assert result.success is False
        assert any("roadmap error" in e for e in result.errors)


class TestBootstrapOptionalFailureStillSucceeds:
    """Gitignore fails → result.success=True + warning."""

    @patch("src.agents.bootstrap_engine.dispatch_task")
    def test_optional_failure_still_succeeds(self, mock_dispatch, temp_dir):
        project = temp_dir / "proj"
        project.mkdir()

        def side_effect_fn(prompt, working_dir, cli_path, timeout_seconds):
            if "gitignore" in prompt.lower():
                return _fail_dispatch("gitignore error")
            # For non-analysis steps, create the output file so verification passes
            if "ROADMAP" in prompt:
                out = project / ".claude" / "planning" / "ROADMAP.md"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text("# Roadmap")
            elif "CLAUDE.md" in prompt:
                (project / "CLAUDE.md").write_text("# Claude")
            elif "ARCHITECTURE" in prompt:
                out = project / "docs" / "ARCHITECTURE.md"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text("# Arch")
            return _ok_dispatch()

        mock_dispatch.side_effect = side_effect_fn

        # Use only required generators + gitignore (skip architecture to simplify)
        engine = _make_engine(project)
        result = engine.bootstrap(skip_architecture=True)

        assert result.success is True
        assert any("Optional step failed" in w for w in result.warnings)
        assert any("gitignore" in w.lower() for w in result.warnings)


class TestBootstrapAnalysisFailureWarnsLaterSteps:
    """Analysis fails → later steps run, warning emitted."""

    @patch("src.agents.bootstrap_engine.dispatch_task")
    def test_analysis_failure_warns_later_steps(self, mock_dispatch, temp_dir):
        project = temp_dir / "proj"
        project.mkdir()

        call_count = 0

        def side_effect_fn(prompt, working_dir, cli_path, timeout_seconds):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call is analyze — fail it
                return _fail_dispatch("analysis failed")
            # Create output files for remaining steps
            if "ROADMAP" in prompt:
                out = project / ".claude" / "planning" / "ROADMAP.md"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text("# Roadmap")
            elif "CLAUDE.md" in prompt:
                (project / "CLAUDE.md").write_text("# Claude")
            return _ok_dispatch()

        mock_dispatch.side_effect = side_effect_fn

        # Only required steps
        engine = _make_engine(
            project,
            generators=[AnalyzeGenerator(), RoadmapGenerator(), ClaudeMdGenerator()],
        )
        result = engine.bootstrap()

        # Analysis is required, so overall fails
        assert result.success is False
        # But later steps still ran
        assert call_count == 3
        # Warnings about missing analysis context
        assert any("without analysis context" in w for w in result.warnings)


class TestBootstrapStepResultsTracked:
    """result.step_results has per-step entries."""

    @patch("src.agents.bootstrap_engine.dispatch_task")
    def test_step_results_tracked(self, mock_dispatch, temp_dir):
        project = temp_dir / "proj"
        project.mkdir()

        def side_effect_fn(prompt, working_dir, cli_path, timeout_seconds):
            if "gitignore" in prompt.lower():
                return _fail_dispatch("gitignore error")
            if "ROADMAP" in prompt:
                out = project / ".claude" / "planning" / "ROADMAP.md"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text("# Roadmap")
            elif "CLAUDE.md" in prompt:
                (project / "CLAUDE.md").write_text("# Claude")
            return _ok_dispatch()

        mock_dispatch.side_effect = side_effect_fn

        engine = _make_engine(
            project,
            generators=[AnalyzeGenerator(), RoadmapGenerator(), ClaudeMdGenerator(), GitignoreGenerator()],
        )
        result = engine.bootstrap()

        assert len(result.step_results) == 4

        # Check individual statuses
        by_type = {sr.step_type: sr for sr in result.step_results}
        assert by_type["analyze"].status == "success"
        assert by_type["roadmap"].status == "success"
        assert by_type["claude_md"].status == "success"
        assert by_type["gitignore"].status == "failed"
        assert by_type["gitignore"].error is not None
        assert by_type["gitignore"].required is False

    @patch("src.agents.bootstrap_engine.dispatch_task")
    def test_skipped_steps_tracked(self, mock_dispatch, temp_dir):
        project = temp_dir / "proj"
        project.mkdir()
        # Create .gitignore so it gets skipped
        (project / ".gitignore").write_text("*.pyc")

        mock_dispatch.return_value = _ok_dispatch()

        engine = _make_engine(
            project,
            generators=[GitignoreGenerator()],
        )
        result = engine.bootstrap()

        assert len(result.step_results) == 1
        assert result.step_results[0].status == "skipped"
        assert result.step_results[0].step_type == "gitignore"


class TestBootstrapProgressReaches100OnPartialFailure:
    """Progress always reaches 100%."""

    @patch("src.agents.bootstrap_engine.dispatch_task")
    def test_progress_reaches_100_on_partial_failure(self, mock_dispatch, temp_dir):
        project = temp_dir / "proj"
        project.mkdir()

        progress_values: list[float] = []

        def capture_progress(step_type, progress, message, step_index, total_steps):
            progress_values.append(progress)

        # First (required) step fails
        mock_dispatch.return_value = _fail_dispatch("required failure")

        engine = _make_engine(
            project,
            generators=[AnalyzeGenerator(), RoadmapGenerator()],
        )
        engine.progress_callback = capture_progress
        result = engine.bootstrap()

        assert result.success is False
        # Final progress callback must be 100%
        assert progress_values[-1] == 100.0

    @patch("src.agents.bootstrap_engine.dispatch_task")
    def test_progress_reaches_100_on_success(self, mock_dispatch, temp_dir):
        project = temp_dir / "proj"
        project.mkdir()

        progress_values: list[float] = []

        def capture_progress(step_type, progress, message, step_index, total_steps):
            progress_values.append(progress)

        def side_effect_fn(prompt, working_dir, cli_path, timeout_seconds):
            if "ROADMAP" in prompt:
                out = project / ".claude" / "planning" / "ROADMAP.md"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text("# Roadmap")
            return _ok_dispatch()

        mock_dispatch.side_effect = side_effect_fn

        engine = _make_engine(
            project,
            generators=[AnalyzeGenerator(), RoadmapGenerator()],
        )
        engine.progress_callback = capture_progress
        result = engine.bootstrap()

        assert result.success is True
        assert progress_values[-1] == 100.0


class TestBootstrapAllStepsRunAfterRequiredFailure:
    """Remaining steps continue after a required step fails (Task 4.11)."""

    @patch("src.agents.bootstrap_engine.dispatch_task")
    def test_all_generators_invoked_despite_failure(self, mock_dispatch, temp_dir):
        project = temp_dir / "proj"
        project.mkdir()

        invoked_prompts: list[str] = []

        def side_effect_fn(prompt, working_dir, cli_path, timeout_seconds):
            invoked_prompts.append(prompt[:50])
            if "roadmap" in prompt.lower() or "ROADMAP" in prompt:
                return _fail_dispatch("roadmap failed")
            if "CLAUDE.md" in prompt:
                (project / "CLAUDE.md").write_text("# Claude")
            return _ok_dispatch()

        mock_dispatch.side_effect = side_effect_fn

        engine = _make_engine(
            project,
            generators=[AnalyzeGenerator(), RoadmapGenerator(), ClaudeMdGenerator()],
        )
        result = engine.bootstrap()

        # All 3 generators were invoked (no early abort)
        assert len(invoked_prompts) == 3
        assert result.success is False


class TestDryRun:
    """Dry run produces step_results without dispatching."""

    def test_dry_run_populates_step_results(self, temp_dir):
        project = temp_dir / "proj"
        project.mkdir()

        engine = _make_engine(
            project,
            generators=[AnalyzeGenerator(), RoadmapGenerator()],
        )
        result = engine.bootstrap(dry_run=True)

        assert result.success is True
        assert len(result.step_results) == 2
        assert all(sr.status == "success" for sr in result.step_results)
        assert result.steps_completed == 2


class TestExceptionHandling:
    """Exceptions during dispatch are captured as failures."""

    @patch("src.agents.bootstrap_engine.dispatch_task")
    def test_exception_in_optional_step_is_warning(self, mock_dispatch, temp_dir):
        project = temp_dir / "proj"
        project.mkdir()

        def side_effect_fn(prompt, working_dir, cli_path, timeout_seconds):
            if "gitignore" in prompt.lower():
                raise RuntimeError("unexpected crash")
            return _ok_dispatch()

        mock_dispatch.side_effect = side_effect_fn

        engine = _make_engine(
            project,
            generators=[AnalyzeGenerator(), GitignoreGenerator()],
        )
        result = engine.bootstrap()

        assert result.success is True  # Gitignore is optional
        assert any("exception" in e for e in result.errors)
        assert any("Optional step failed" in w for w in result.warnings)
        gitignore_sr = [sr for sr in result.step_results if sr.step_type == "gitignore"][0]
        assert gitignore_sr.status == "failed"

    @patch("src.agents.bootstrap_engine.dispatch_task")
    def test_exception_in_required_step_fails(self, mock_dispatch, temp_dir):
        project = temp_dir / "proj"
        project.mkdir()

        mock_dispatch.side_effect = RuntimeError("cli exploded")

        engine = _make_engine(
            project,
            generators=[AnalyzeGenerator()],
        )
        result = engine.bootstrap()

        assert result.success is False
        assert len(result.step_results) == 1
        assert result.step_results[0].status == "failed"
