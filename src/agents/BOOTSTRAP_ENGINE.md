# Bootstrap Engine - Technical Documentation

**Phase 1, Week 3-4: Core Bootstrap Engine** ✅

## Overview

The Bootstrap Engine is the core orchestration layer that automates the creation of perfect Claude Code project setups. It's designed to be used by both CLI and GUI interfaces.

## Architecture

```
bootstrap_engine.py
├── BootstrapEngine       # Core orchestration
├── BootstrapStep         # Individual step definition
├── BootstrapResult       # Execution results
└── ProgressCallback      # UI progress interface

bootstrap_prompts/
├── analyze_codebase.txt       # Step 1: Project analysis
├── generate_roadmap.txt       # Step 2: ROADMAP.md
├── generate_claude_md.txt     # Step 3: CLAUDE.md
├── generate_gitignore.txt     # Step 4: .gitignore
└── generate_architecture.txt  # Step 5: ARCHITECTURE.md

bootstrap_cli.py          # CLI wrapper (testing/validation)
dispatcher.py             # Added dispatch_bootstrap() method
```

## Key Features

### 1. Modular Architecture

Each bootstrap step is independent and reusable:

```python
from src.agents.bootstrap_engine import BootstrapEngine, BootstrapStepType

# Initialize engine
engine = BootstrapEngine(
    project_path=Path("/my/project"),
    progress_callback=my_progress_handler,  # Optional
)

# Run full bootstrap
result = engine.bootstrap(
    skip_git=False,
    skip_architecture=False,
    dry_run=False,
)

# Check results
if result.success:
    print(f"Created {len(result.artifacts)} artifacts")
    for artifact_type, path in result.artifacts.items():
        print(f"  {artifact_type}: {path}")
else:
    print(f"Failed with {len(result.errors)} errors")
```

### 2. Progress Tracking

Real-time progress callbacks for UI integration:

```python
def my_progress_callback(step_type, progress, message, step_index, total_steps):
    """Called after each step with progress updates."""
    print(f"[{step_index}/{total_steps}] {progress:.1f}% - {message}")

engine = BootstrapEngine(
    project_path=project_path,
    progress_callback=my_progress_callback,
)
```

The GUI will use this for real-time progress bars and status updates.

### 3. Cost Estimation

Before running bootstrap, estimate the cost:

```python
engine = BootstrapEngine(project_path=Path("/my/project"))
estimate = engine.estimate_cost()

print(f"Steps: {estimate['steps']}")
print(f"Tokens: ~{estimate['total_tokens']:,}")
print(f"Cost: ${estimate['cost_usd']:.2f}")
```

Example output:
```
Steps: 5
Tokens: ~260,000
Cost: $1.25
```

### 4. Prompt Templates

All prompts are externalized to `.txt` files for easy editing and iteration:

- **analyze_codebase.txt**: Analyze project type, tech stack, current state
- **generate_roadmap.txt**: Create milestone-based roadmap
- **generate_claude_md.txt**: Generate project instructions
- **generate_gitignore.txt**: Create language-specific .gitignore
- **generate_architecture.txt**: Document system architecture

This makes it easy to:
- Improve prompts without touching code
- Version control prompt changes
- A/B test different prompting strategies
- Share prompts with community

### 5. Graceful Error Handling

Bootstrap continues even if optional steps fail:

```python
result = engine.bootstrap()

# Check what succeeded
print(f"Completed: {result.steps_completed}/{result.steps_total}")

# Handle errors
for error in result.errors:
    print(f"Error: {error}")

# Handle warnings
for warning in result.warnings:
    print(f"Warning: {warning}")
```

## Bootstrap Steps

### Step 1: Analyze Project (Weight: 0.5)

- **Purpose**: Understand project type, tech stack, current state
- **Output**: Temporary analysis file (not committed)
- **Used by**: All subsequent steps for context

### Step 2: Generate ROADMAP.md (Weight: 2.0)

- **Output**: `.claude/planning/ROADMAP.md`
- **Format**: GitHub-flavored markdown with checkboxes
- **Content**: 3-6 milestones with actionable tasks
- **Required**: Yes

### Step 3: Generate CLAUDE.md (Weight: 2.0)

- **Output**: `CLAUDE.md` (project root)
- **Format**: Comprehensive project guide
- **Content**: Overview, architecture, conventions, commands
- **Required**: Yes

### Step 4: Generate .gitignore (Weight: 0.5)

- **Output**: `.gitignore` (project root)
- **Format**: Language-specific ignore patterns
- **Skip if**: File already exists
- **Required**: No (optional)

### Step 5: Generate ARCHITECTURE.md (Weight: 1.5)

- **Output**: `docs/ARCHITECTURE.md`
- **Format**: High-level design documentation
- **Content**: System design, components, data flow, decisions
- **Required**: No (optional)

**Total Weight**: 6.5 (used for progress calculation)

## Integration Points

### CLI Usage (Testing)

```bash
# Basic bootstrap
python -m src.agents.bootstrap_cli /path/to/project

# Estimate cost first
python -m src.agents.bootstrap_cli /path/to/project --estimate-cost

# Dry run
python -m src.agents.bootstrap_cli /path/to/project --dry-run

# Skip optional steps
python -m src.agents.bootstrap_cli /path/to/project --skip-architecture

# Verbose output
python -m src.agents.bootstrap_cli /path/to/project -v
```

### GUI Usage (Future)

```python
# In the GUI's bootstrap view component
from src.agents.bootstrap_engine import BootstrapEngine, BootstrapStepType

class BootstrapView:
    def start_bootstrap(self):
        engine = BootstrapEngine(
            project_path=self.selected_project_path,
            progress_callback=self.update_progress_bar,
        )

        # Run in background thread to avoid blocking UI
        threading.Thread(
            target=self.run_bootstrap_async,
            args=(engine,),
        ).start()

    def update_progress_bar(self, step_type, progress, message, step_index, total_steps):
        # Update UI components
        self.progress_bar.set_value(progress)
        self.status_label.set_text(message)
        self.step_indicator.set_text(f"Step {step_index} of {total_steps}")

    def run_bootstrap_async(self, engine):
        result = engine.bootstrap()
        # Update UI on completion
        self.show_completion_screen(result)
```

## Testing Checklist

Before considering bootstrap engine "validated", test on:

- [ ] **Python project** (Django/FastAPI/Flask)
- [ ] **JavaScript project** (React/Vue/Node.js)
- [ ] **Rust project** (CLI/web server)
- [ ] **Empty directory** (new project)
- [ ] **Monorepo** (multiple sub-projects)

**Success criteria per test**:
- [ ] All files created successfully
- [ ] ROADMAP.md has project-specific milestones
- [ ] CLAUDE.md has actual code examples from project
- [ ] .gitignore has correct language patterns
- [ ] ARCHITECTURE.md describes actual system design
- [ ] Completes in < 10 minutes
- [ ] No unhandled exceptions

## Cost & Performance

**Typical bootstrap run**:
- **Duration**: 3-8 minutes
- **Tokens**: 50k-100k (varies by project complexity)
- **Cost**: $0.15-$0.30 per project

**Breakdown by step**:
```
Analyze:        30k tokens   ~$0.04
ROADMAP:        80k tokens   ~$0.10
CLAUDE.md:      60k tokens   ~$0.08
.gitignore:     20k tokens   ~$0.03
ARCHITECTURE:   70k tokens   ~$0.09
---
Total:         ~260k tokens  ~$0.34
```

## Future Enhancements

Planned improvements (not in current scope):

1. **Resume from failure**: Save progress, resume from last successful step
2. **Custom templates**: Allow users to provide their own prompt templates
3. **Multi-language support**: Generate artifacts in different languages
4. **Incremental updates**: Update existing ROADMAP.md rather than regenerating
5. **Quality validation**: Check artifact quality before marking step complete

## API Reference

### BootstrapEngine

```python
class BootstrapEngine:
    def __init__(
        self,
        project_path: Path,
        progress_callback: ProgressCallback | None = None,
        cli_path: str = "claude",
        timeout_per_step: int = 600,
    )

    def bootstrap(
        self,
        skip_git: bool = False,
        skip_architecture: bool = False,
        dry_run: bool = False,
    ) -> BootstrapResult

    def estimate_cost(self) -> dict[str, float]
```

### BootstrapResult

```python
@dataclass
class BootstrapResult:
    success: bool                           # Overall success
    artifacts: dict[str, Path]              # Created files by type
    errors: list[str]                       # Critical errors
    warnings: list[str]                     # Non-critical warnings
    duration_seconds: float                 # Total execution time
    steps_completed: int                    # How many steps succeeded
    steps_total: int                        # Total steps attempted
    analysis_summary: str | None            # Project analysis output
```

### ProgressCallback

```python
class ProgressCallback(Protocol):
    def __call__(
        self,
        step_type: BootstrapStepType,      # Current step
        progress: float,                    # 0-100
        message: str,                       # Human-readable status
        step_index: int,                    # Current step (1-indexed)
        total_steps: int,                   # Total steps
    ) -> None
```

---

**Status**: ✅ Complete and ready for testing
**Created**: 2026-02-14
**Phase**: 1 Week 3-4
**Next**: Week 5-6 - Readiness Scorecard Engine
