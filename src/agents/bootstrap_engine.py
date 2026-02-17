"""Core bootstrap engine for creating Claude Code project artifacts.

This module provides the orchestration layer for bootstrapping projects.
It's designed to be used by both CLI and GUI interfaces.

Architecture:
- ArtifactGenerator: Abstract base for each artifact type
- BootstrapEngine: Orchestrates generators with partial-failure resilience
- BootstrapStep: Adapter built from generators for progress/cost APIs
- StepResult: Per-step outcome record for granular reporting
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol

from .dispatcher import DispatchResult, dispatch_task


class BootstrapStepType(Enum):
    """Types of bootstrap steps."""

    ANALYZE = "analyze"
    ROADMAP = "roadmap"
    CLAUDE_MD = "claude_md"
    GITIGNORE = "gitignore"
    ARCHITECTURE = "architecture"


@dataclass
class BootstrapStep:
    """A single step in the bootstrap process."""

    step_type: BootstrapStepType
    name: str
    description: str
    output_path: Path
    prompt_template: str
    weight: float = 1.0  # Relative weight for progress calculation
    skip_if_exists: bool = False  # Skip if output file already exists
    required: bool = True  # Whether this step is required for success


@dataclass
class StepResult:
    """Outcome of a single bootstrap step."""

    step_type: str
    name: str
    status: str  # "success", "failed", "skipped"
    required: bool
    error: str | None = None


@dataclass
class BootstrapResult:
    """Result of a bootstrap operation."""

    success: bool
    artifacts: dict[str, Path] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    steps_completed: int = 0
    steps_total: int = 0
    analysis_summary: str | None = None
    step_results: list[StepResult] = field(default_factory=list)


class ProgressCallback(Protocol):
    """Protocol for reporting bootstrap progress."""

    def __call__(
        self,
        step_type: BootstrapStepType,
        progress: float,
        message: str,
        step_index: int,
        total_steps: int,
    ) -> None:
        """Report progress.

        Args:
            step_type: Current step type
            progress: Overall progress percentage (0-100)
            message: Human-readable progress message
            step_index: Current step number (1-indexed)
            total_steps: Total number of steps
        """
        ...


# ---------------------------------------------------------------------------
# ArtifactGenerator abstraction (Task 4.1)
# ---------------------------------------------------------------------------


class ArtifactGenerator(ABC):
    """Base class for bootstrap artifact generators.

    Each generator knows how to produce one artifact type. The engine
    iterates over generators, calling ``generate()`` on each.
    """

    @property
    @abstractmethod
    def step_type(self) -> BootstrapStepType:
        """The step type this generator produces."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name shown in progress updates."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Progress message displayed while this step runs."""

    @property
    @abstractmethod
    def template_name(self) -> str:
        """Filename (without .txt) in bootstrap_prompts/."""

    @property
    @abstractmethod
    def required(self) -> bool:
        """If True, failure marks the overall bootstrap as failed."""

    @property
    def weight(self) -> float:
        """Relative weight for progress bar calculation."""
        return 1.0

    @property
    def skip_if_exists(self) -> bool:
        """If True, skip when the output file already exists."""
        return False

    @property
    def estimated_tokens(self) -> int:
        """Rough token estimate for cost calculation."""
        return 50_000

    @abstractmethod
    def output_path(self, project_path: Path) -> Path:
        """Return the output file path for this artifact."""

    def build_prompt(
        self,
        template: str,
        output: Path,
        analysis_context: str | None = None,
    ) -> str:
        """Assemble the full prompt sent to Claude CLI."""
        prompt = template
        if self.step_type != BootstrapStepType.ANALYZE and analysis_context:
            prompt = f"## Project Analysis\n\n{analysis_context}\n\n---\n\n{prompt}"
        prompt += f"\n\n**Output File**: Create the file at `{output}`"
        return prompt


class AnalyzeGenerator(ArtifactGenerator):
    step_type = BootstrapStepType.ANALYZE
    name = "Analyze Project"
    description = "Analyzing project structure and technologies"
    template_name = "analyze_codebase"
    required = True
    weight = 0.5
    estimated_tokens = 30_000

    def output_path(self, project_path: Path) -> Path:
        return project_path / ".bootstrap_analysis.md"


class RoadmapGenerator(ArtifactGenerator):
    step_type = BootstrapStepType.ROADMAP
    name = "Generate Roadmap"
    description = "Generating milestone-based roadmap"
    template_name = "generate_roadmap"
    required = True
    weight = 2.0
    estimated_tokens = 80_000

    def output_path(self, project_path: Path) -> Path:
        return project_path / ".claude" / "planning" / "ROADMAP.md"


class ClaudeMdGenerator(ArtifactGenerator):
    step_type = BootstrapStepType.CLAUDE_MD
    name = "Generate CLAUDE.md"
    description = "Creating project instructions for Claude Code"
    template_name = "generate_claude_md"
    required = True
    weight = 2.0
    estimated_tokens = 60_000

    def output_path(self, project_path: Path) -> Path:
        return project_path / "CLAUDE.md"


class GitignoreGenerator(ArtifactGenerator):
    step_type = BootstrapStepType.GITIGNORE
    name = "Generate .gitignore"
    description = "Creating .gitignore with best practices"
    template_name = "generate_gitignore"
    required = False
    weight = 0.5
    skip_if_exists = True
    estimated_tokens = 20_000

    def output_path(self, project_path: Path) -> Path:
        return project_path / ".gitignore"


class ArchitectureGenerator(ArtifactGenerator):
    step_type = BootstrapStepType.ARCHITECTURE
    name = "Generate Architecture Docs"
    description = "Documenting system architecture"
    template_name = "generate_architecture"
    required = False
    weight = 1.5
    estimated_tokens = 70_000

    def output_path(self, project_path: Path) -> Path:
        return project_path / "docs" / "ARCHITECTURE.md"


# Default generator ordering
DEFAULT_GENERATORS: list[type[ArtifactGenerator]] = [
    AnalyzeGenerator,
    RoadmapGenerator,
    ClaudeMdGenerator,
    GitignoreGenerator,
    ArchitectureGenerator,
]


class BootstrapEngine:
    """Core engine for bootstrapping Claude Code projects."""

    def __init__(
        self,
        project_path: Path,
        progress_callback: ProgressCallback | None = None,
        cli_path: str = "claude",
        timeout_per_step: int = 600,
        generators: list[ArtifactGenerator] | None = None,
    ):
        """Initialize bootstrap engine.

        Args:
            project_path: Path to project to bootstrap
            progress_callback: Optional callback for progress updates
            cli_path: Path to Claude CLI executable
            timeout_per_step: Timeout in seconds for each bootstrap step
            generators: Optional custom list of generators (defaults to all)
        """
        self.project_path = project_path.resolve()
        self.progress_callback = progress_callback or self._default_progress
        self.cli_path = cli_path
        self.timeout_per_step = timeout_per_step
        self._generators = generators if generators is not None else [g() for g in DEFAULT_GENERATORS]

        # Validate project path
        if not self.project_path.exists():
            raise ValueError(f"Project path does not exist: {self.project_path}")

        # Load prompt templates
        self.prompts_dir = Path(__file__).parent / "bootstrap_prompts"
        if not self.prompts_dir.exists():
            raise RuntimeError(f"Prompt templates directory not found: {self.prompts_dir}")

    def _default_progress(
        self,
        step_type: BootstrapStepType,
        progress: float,
        message: str,
        step_index: int,
        total_steps: int,
    ) -> None:
        """Default progress callback that prints to stdout."""
        print(f"[{step_index}/{total_steps}] {progress:.1f}% - {message}")

    def _load_prompt_template(self, template_name: str) -> str:
        """Load a prompt template from the prompts directory."""
        template_path = self.prompts_dir / f"{template_name}.txt"
        if not template_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {template_path}")
        return template_path.read_text(encoding="utf-8")

    def _select_generators(
        self,
        skip_git: bool = False,
        skip_architecture: bool = False,
    ) -> list[ArtifactGenerator]:
        """Filter generators based on skip flags."""
        active: list[ArtifactGenerator] = []
        for gen in self._generators:
            if skip_git and gen.step_type == BootstrapStepType.GITIGNORE:
                continue
            if skip_architecture and gen.step_type == BootstrapStepType.ARCHITECTURE:
                continue
            active.append(gen)
        return active

    def _build_steps(
        self,
        skip_git: bool = False,
        skip_architecture: bool = False,
    ) -> list[BootstrapStep]:
        """Build the list of bootstrap steps from generators."""
        generators = self._select_generators(skip_git=skip_git, skip_architecture=skip_architecture)
        steps: list[BootstrapStep] = []
        for gen in generators:
            steps.append(
                BootstrapStep(
                    step_type=gen.step_type,
                    name=gen.name,
                    description=gen.description,
                    output_path=gen.output_path(self.project_path),
                    prompt_template=self._load_prompt_template(gen.template_name),
                    weight=gen.weight,
                    skip_if_exists=gen.skip_if_exists,
                    required=gen.required,
                )
            )
        return steps

    def bootstrap(
        self,
        skip_git: bool = False,
        skip_architecture: bool = False,
        dry_run: bool = False,
    ) -> BootstrapResult:
        """Execute the full bootstrap process.

        Runs every generator in order.  Required-step failures mark
        ``result.success = False`` but do **not** abort remaining steps
        (partial-failure resilience, Task 4.11).  Optional-step failures
        are recorded as warnings.  Progress always reaches 100%.

        Args:
            skip_git: Skip .gitignore generation
            skip_architecture: Skip architecture documentation
            dry_run: Preview steps without executing

        Returns:
            BootstrapResult with artifacts, per-step results, and status
        """
        start_time = time.time()
        generators = self._select_generators(skip_git=skip_git, skip_architecture=skip_architecture)
        total_steps = len(generators)

        result = BootstrapResult(success=True, steps_total=total_steps, steps_completed=0)

        # Calculate total weight for progress calculation
        total_weight = sum(gen.weight for gen in generators)
        completed_weight = 0.0

        analysis_summary: str | None = None
        analysis_failed = False

        for idx, gen in enumerate(generators, start=1):
            out_path = gen.output_path(self.project_path)

            # Check if we should skip this step
            if gen.skip_if_exists and out_path.exists():
                self.progress_callback(
                    gen.step_type,
                    (completed_weight / total_weight) * 100,
                    f"Skipping {gen.name} (already exists)",
                    idx,
                    total_steps,
                )
                result.warnings.append(f"Skipped {gen.name} (file already exists)")
                result.step_results.append(
                    StepResult(
                        step_type=gen.step_type.value,
                        name=gen.name,
                        status="skipped",
                        required=gen.required,
                    )
                )
                completed_weight += gen.weight
                result.steps_completed += 1
                continue

            # Report step start
            progress = (completed_weight / total_weight) * 100
            self.progress_callback(gen.step_type, progress, gen.description, idx, total_steps)

            if dry_run:
                result.artifacts[gen.step_type.value] = out_path
                result.step_results.append(
                    StepResult(
                        step_type=gen.step_type.value,
                        name=gen.name,
                        status="success",
                        required=gen.required,
                    )
                )
                completed_weight += gen.weight
                result.steps_completed += 1
                continue

            # Warn if analysis failed and this step normally uses analysis context
            effective_analysis = analysis_summary
            if analysis_failed and gen.step_type != BootstrapStepType.ANALYZE:
                result.warnings.append(
                    f"{gen.name}: running without analysis context (analysis step failed)"
                )
                effective_analysis = None

            # Execute step
            error_msg: str | None = None
            try:
                dispatch_result = self._execute_generator(gen, out_path, effective_analysis)

                if dispatch_result.success:
                    result.artifacts[gen.step_type.value] = out_path
                    result.steps_completed += 1

                    # Capture analysis summary for later steps
                    if gen.step_type == BootstrapStepType.ANALYZE:
                        analysis_summary = dispatch_result.output

                    # Verify output file was created (except for analysis)
                    if gen.step_type != BootstrapStepType.ANALYZE and not out_path.exists():
                        error_msg = f"{gen.name} failed: Output file not created at {out_path}"
                    else:
                        # Step succeeded — record and move on
                        result.step_results.append(
                            StepResult(
                                step_type=gen.step_type.value,
                                name=gen.name,
                                status="success",
                                required=gen.required,
                            )
                        )
                        completed_weight += gen.weight
                        continue
                else:
                    error_msg = f"{gen.name} failed: {dispatch_result.error_message}"

            except Exception as exc:
                error_msg = f"{gen.name} failed with exception: {exc}"

            # --- Handle failure (required or optional) ---
            result.errors.append(error_msg)
            result.step_results.append(
                StepResult(
                    step_type=gen.step_type.value,
                    name=gen.name,
                    status="failed",
                    required=gen.required,
                    error=error_msg,
                )
            )

            if gen.step_type == BootstrapStepType.ANALYZE:
                analysis_failed = True

            if gen.required:
                result.success = False
            else:
                result.warnings.append(f"Optional step failed: {gen.name}")

            completed_weight += gen.weight

        # Progress always reaches 100% (Task 4.11)
        self.progress_callback(
            BootstrapStepType.ANALYZE,
            100.0,
            "Bootstrap complete!" if result.success else "Bootstrap completed with errors",
            total_steps,
            total_steps,
        )

        result.duration_seconds = time.time() - start_time
        result.analysis_summary = analysis_summary
        return result

    def _execute_generator(
        self,
        gen: ArtifactGenerator,
        out_path: Path,
        analysis_context: str | None = None,
    ) -> DispatchResult:
        """Execute a single generator via Claude CLI dispatch."""
        out_path.parent.mkdir(parents=True, exist_ok=True)

        template = self._load_prompt_template(gen.template_name)
        prompt = gen.build_prompt(template, out_path, analysis_context)

        return dispatch_task(
            prompt=prompt,
            working_dir=self.project_path,
            cli_path=self.cli_path,
            timeout_seconds=self.timeout_per_step,
        )

    # Keep legacy _execute_step for any external callers
    def _execute_step(self, step: BootstrapStep, analysis_context: str | None = None) -> DispatchResult:
        """Execute a single bootstrap step (legacy adapter)."""
        step.output_path.parent.mkdir(parents=True, exist_ok=True)

        prompt = step.prompt_template
        if step.step_type != BootstrapStepType.ANALYZE and analysis_context:
            prompt = f"## Project Analysis\n\n{analysis_context}\n\n---\n\n{prompt}"
        prompt += f"\n\n**Output File**: Create the file at `{step.output_path}`"

        return dispatch_task(
            prompt=prompt,
            working_dir=self.project_path,
            cli_path=self.cli_path,
            timeout_seconds=self.timeout_per_step,
        )

    def estimate_cost(self) -> dict[str, float]:
        """Estimate the cost of running bootstrap.

        Returns:
            Dict with estimated tokens and cost in USD
        """
        generators = self._select_generators()
        total_tokens = sum(gen.estimated_tokens for gen in generators)

        # Claude Sonnet 4.5 pricing (as of 2026-02)
        # Input: $3 per 1M tokens, Output: $15 per 1M tokens
        # Assume 60/40 split input/output
        input_tokens = total_tokens * 0.6
        output_tokens = total_tokens * 0.4

        cost_usd = (input_tokens * 3 / 1_000_000) + (output_tokens * 15 / 1_000_000)

        return {
            "total_tokens": total_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
            "steps": len(generators),
        }


# Convenience function for simple bootstrap
def bootstrap_project(
    project_path: Path,
    skip_git: bool = False,
    skip_architecture: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> BootstrapResult:
    """Convenience function to bootstrap a project.

    Args:
        project_path: Path to project
        skip_git: Skip .gitignore
        skip_architecture: Skip architecture docs
        progress_callback: Optional progress callback

    Returns:
        BootstrapResult
    """
    engine = BootstrapEngine(project_path, progress_callback)
    return engine.bootstrap(skip_git=skip_git, skip_architecture=skip_architecture)
