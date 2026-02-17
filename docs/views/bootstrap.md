# Bootstrap View

> Multi-step project scaffolding wizard that generates essential Claude Code artifacts through a guided, cost-aware process with real-time SSE progress streaming.

Last updated: 2026-02-17

---

## 1. Purpose

The Bootstrap View scaffolds a project for Claude Code by generating missing artifacts identified by the Scorecard. It uses the Claude CLI to analyze the project and create files like `CLAUDE.md`, `ROADMAP.md`, `.gitignore`, and `docs/ARCHITECTURE.md`. The process is orchestrated by the `BootstrapEngine` on the backend and displayed in the frontend through two components: `BootstrapWizard` (cost estimation, confirmation, result handling) and `BootstrapProgressView` (real-time SSE progress streaming).

---

## 2. When It Appears

The Bootstrap View appears in the screen state machine when the user clicks "Bootstrap N Items" from the Scorecard View. This typically happens when:

- The readiness score is low (multiple failed checks)
- Critical issues exist (missing `CLAUDE.md`, `ROADMAP.md`, or `Git Repository`)
- The user explicitly selects failed items for remediation

```
scorecard --> bootstrap --> dashboard   (bootstrap completes successfully)
scorecard --> bootstrap --> scorecard   (bootstrap fails, user retries or cancels)
```

The screen state is tracked in `projectManager` as `currentScreen: "bootstrap"`.

**Source:** `app/src/managers/projectManager.ts` (line 6)

---

## 3. Cost Estimation

Before any work begins, the Bootstrap Wizard fetches a cost estimate from the backend. This gives users transparency about token usage and estimated USD cost.

### Estimate Request

```
POST /api/bootstrap/estimate
Body: { "project_path": "/path/to/project" }
```

### Estimate Response

```typescript
interface CostEstimate {
  total_tokens: number;    // Total estimated tokens across all steps
  input_tokens: number;    // 60% of total (input portion)
  output_tokens: number;   // 40% of total (output portion)
  cost_usd: number;        // Estimated cost in USD
  steps: number;           // Number of steps to execute
}
```

### Cost Calculation (Backend)

The engine sums `estimated_tokens` from each active generator and computes cost using Claude Sonnet 4.5 pricing:

```python
input_tokens = total_tokens * 0.6
output_tokens = total_tokens * 0.4
cost_usd = (input_tokens * 3 / 1_000_000) + (output_tokens * 15 / 1_000_000)
```

Per-generator token estimates:

| Generator | Estimated Tokens |
|-----------|-----------------|
| Analyze Project | 30,000 |
| Generate Roadmap | 80,000 |
| Generate CLAUDE.md | 60,000 |
| Generate .gitignore | 20,000 |
| Generate Architecture Docs | 70,000 |
| **Total (all steps)** | **260,000** |

**Source:** `src/agents/bootstrap_engine.py` (lines 523-546)

### UI Presentation

The estimate screen displays:
- **What will be created** -- a checklist of four artifacts (ROADMAP.md, CLAUDE.md, .gitignore, ARCHITECTURE.md)
- **Estimated Cost** -- total steps, estimated tokens, and estimated USD cost prominently displayed
- A disclaimer: "Actual cost may vary based on project complexity"

---

## 4. Wizard Screen Flow

The `BootstrapWizard` component manages a four-screen state machine:

```typescript
type WizardScreen = 'estimate' | 'confirm' | 'progress' | 'result';
```

### Screen Transitions

```
estimate ---[Start Bootstrap]--> progress ---[complete/success]--> (onComplete -> dashboard)
    |                                |
    |                                +---[complete/fail]---------> result (error display)
    |
    +---[Cancel]-------------------> (onCancel -> scorecard)
```

In practice, the `confirm` screen is currently merged into `estimate` (the start button is on the estimate screen). The `result` screen is used only for failure display.

### Component Props

```typescript
interface BootstrapWizardProps {
  projectPath: string;       // Absolute path to the project
  onComplete: () => void;    // Called on successful bootstrap (navigate to dashboard)
  onCancel: () => void;      // Called on cancel (navigate back to scorecard)
}
```

---

## 5. Bootstrap Steps

The `BootstrapEngine` executes five generators in a fixed order. Each generator is an `ArtifactGenerator` subclass.

### Step 1: Analyze Project

| Property | Value |
|----------|-------|
| Step type | `ANALYZE` |
| Output | `.bootstrap_analysis.md` (temporary) |
| Required | Yes |
| Weight | 0.5 |

Scans the project structure, technologies, and patterns. The analysis output is passed as context to all subsequent generators. If this step fails, subsequent steps run without analysis context and a warning is recorded.

### Step 2: Generate ROADMAP.md

| Property | Value |
|----------|-------|
| Step type | `ROADMAP` |
| Output | `.claude/planning/ROADMAP.md` |
| Required | Yes |
| Weight | 2.0 |

Creates a milestone-based development plan with checkbox-format tasks. Uses the analysis context to understand the project and generate relevant milestones.

### Step 3: Generate CLAUDE.md

| Property | Value |
|----------|-------|
| Step type | `CLAUDE_MD` |
| Output | `CLAUDE.md` (project root) |
| Required | Yes |
| Weight | 2.0 |

Creates the project instruction file that Claude Code reads on every session. Includes architecture overview, code conventions, commands, and project-specific guidance.

### Step 4: Generate .gitignore

| Property | Value |
|----------|-------|
| Step type | `GITIGNORE` |
| Output | `.gitignore` |
| Required | No |
| Weight | 0.5 |
| Skip if exists | Yes |

Creates a `.gitignore` tailored to the project's detected technologies. Automatically skipped if a `.gitignore` already exists.

### Step 5: Generate Architecture Docs

| Property | Value |
|----------|-------|
| Step type | `ARCHITECTURE` |
| Output | `docs/ARCHITECTURE.md` |
| Required | No |
| Weight | 1.5 |

Documents the system architecture, component relationships, and data flow. This step is optional and can be skipped by the user.

### Execution Model

Each step dispatches a prompt to the Claude CLI via `dispatch_task()`. The engine uses **partial-failure resilience**: required-step failures mark the overall result as failed but do not abort remaining steps. Optional-step failures are recorded as warnings. Progress always reaches 100%.

**Source:** `src/agents/bootstrap_engine.py` (lines 333-485)

---

## 6. SSE Progress Streaming

The Bootstrap Wizard uses Server-Sent Events (SSE) for real-time progress updates during execution.

### Architecture

```
Frontend (EventSource)  <---SSE---  Backend (/api/bootstrap/stream/{session_id})
                                          |
                                    asyncio poll loop (0.5s)
                                          |
                                    _active_sessions dict
                                          |
                                    _run_bootstrap_async (background task)
                                          |
                                    BootstrapEngine.bootstrap()
                                          |
                                    progress_callback -> session["messages"]
```

### Starting the Stream

1. Frontend calls `POST /api/bootstrap/start` with `project_path` and skip options.
2. Backend generates a UUID `session_id`, stores session state in `_active_sessions`, and launches `_run_bootstrap_async` as a background `asyncio.create_task`.
3. Backend returns `{ session_id, stream_url }`.
4. Frontend creates an `EventSource` connected to `GET /api/bootstrap/stream/{session_id}`.

### SSE Message Types

```typescript
interface BootstrapProgress {
  type: 'progress' | 'complete' | 'error';
  progress?: number;    // 0-100 percentage
  message?: string;     // Current step description
  step?: string;        // e.g., "2/5"
  step_type?: string;   // e.g., "roadmap"
  status?: string;      // Final status: "completed" | "failed"
  result?: any;         // Final result object (on complete)
  error?: string;       // Error message (on error/failure)
}
```

### Event Handling

| Event Type | Frontend Action |
|------------|----------------|
| `progress` | Update progress bar, message, step indicator; append to activity log |
| `complete` + `status: "completed"` | Set progress to 100%, call `onComplete(true, result)`, close EventSource |
| `complete` + `status: "failed"` | Set status to failed, display error, call `onComplete(false)`, close EventSource |
| `error` | Set status to failed, display error, call `onComplete(false)`, close EventSource |
| EventSource `onerror` | Set status to failed with "Connection lost" message, close EventSource |

---

## 7. BootstrapProgressView Component

**File:** `app/src/components/bootstrap/BootstrapProgressView.tsx`

### Props

```typescript
interface BootstrapProgressViewProps {
  sessionId: string;                                    // Bootstrap session UUID
  onComplete: (success: boolean, result?: any) => void; // Completion callback
  onCancel?: () => void;                                // Optional cancel callback
}
```

### Visual Layout

```
+------------------------------------------+
|         Bootstrapping Project             |
|  "Setting up your project for Claude..."  |
+------------------------------------------+
|                                           |
|          [Circular Progress Ring]          |
|               67%                         |
|              3/5                           |
|                                           |
|    "Creating project instructions..."     |
|                                           |
+------------------------------------------+
|  Activity Log                             |
|  [2/5] Generating milestone-based roadmap |
|  [3/5] Creating project instructions...   |
|                                           |
+------------------------------------------+
|              [Cancel]                     |
+------------------------------------------+
```

### Progress Ring

The progress view renders its own circular SVG progress indicator (separate from the Scorecard's `ReadinessRing`):

- 180x180px SVG with an 80px radius
- 8px stroke width
- Stroke color changes based on status:

| Status | Color |
|--------|-------|
| `running` | `#8b7cf6` (accent/purple) |
| `completed` | `#34d399` (green) |
| `failed` | `#f87171` (red) |

The center shows the percentage and current step indicator (e.g., "3/5").

### Activity Log

A scrollable monospace log panel accumulates messages from SSE events. Each entry shows the step number and message:

```
[1/5] Analyzing project structure and technologies
[2/5] Generating milestone-based roadmap
[3/5] Creating project instructions for Claude Code
```

Maximum height is 192px (max-h-48) with overflow scroll.

### Status-Dependent Actions

| Status | Buttons Shown |
|--------|---------------|
| `running` | Cancel (outline/secondary) |
| `completed` | "Continue to Dashboard" (green) |
| `failed` | "Try Again" (red) + "Cancel" (secondary) |

On completion, a green checkmark icon appears. On failure, an error panel with a red border displays the error message.

---

## 8. Skip Options

The estimate screen provides two skip toggles before starting:

### skipGit (Skip .gitignore)

```typescript
skipOptions.skipGit: boolean  // Default: false
```

When enabled, the `.gitignore` generator is excluded from the bootstrap run. Useful when the project already has a `.gitignore` (the generator also has `skip_if_exists: true` as a safety net).

### skipArchitecture (Skip Architecture Docs)

```typescript
skipOptions.skipArchitecture: boolean  // Default: false
```

When enabled, the `docs/ARCHITECTURE.md` generator is excluded. Since architecture documentation is an optional step (`required: false`), this lets users reduce cost and time.

### Backend Implementation

The skip flags are passed through the API to `BootstrapEngine._select_generators()`:

```python
def _select_generators(self, skip_git=False, skip_architecture=False):
    active = []
    for gen in self._generators:
        if skip_git and gen.step_type == BootstrapStepType.GITIGNORE:
            continue
        if skip_architecture and gen.step_type == BootstrapStepType.ARCHITECTURE:
            continue
        active.append(gen)
    return active
```

Additionally, the `GitignoreGenerator` has `skip_if_exists = True`, meaning even without the explicit skip flag it will be skipped if `.gitignore` already exists.

---

## 9. Transition After Completion

### Successful Bootstrap

When the bootstrap completes successfully (`status === "completed"`):

1. `BootstrapProgressView` calls `onComplete(true, result)`.
2. `BootstrapWizard.handleBootstrapComplete(true)` calls the parent `onComplete()`.
3. The parent sets `currentScreen: "dashboard"` via `projectManager.completeBootstrap()`.
4. The `completeBootstrap` action also clears bootstrap state:
   ```typescript
   completeBootstrap: () => {
     set({
       bootstrapInProgress: false,
       bootstrapSessionId: null,
       currentScreen: "dashboard",
     });
   }
   ```

### Failed Bootstrap

When the bootstrap fails:

1. `BootstrapProgressView` calls `onComplete(false)`.
2. `BootstrapWizard.handleBootstrapComplete(false)` sets `screen` to `'result'`.
3. The user sees the error state with "Try Again" and "Cancel" buttons.
4. "Cancel" calls `onCancel` which typically returns to the Scorecard for a re-scan.

---

## 10. Backend Session Management

Bootstrap sessions are managed in-memory on the Python sidecar.

### Session Lifecycle

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/bootstrap/estimate` | POST | Calculate cost estimate before starting |
| `/api/bootstrap/start` | POST | Create session, launch background task, return `session_id` |
| `/api/bootstrap/stream/{session_id}` | GET (SSE) | Stream real-time progress events |
| `/api/bootstrap/status/{session_id}` | GET | Poll current status (alternative to SSE) |
| `/api/bootstrap/result/{session_id}` | GET | Retrieve final result with per-step details |
| `/api/bootstrap/session/{session_id}` | DELETE | Clean up session from memory |

### Session State

```python
_active_sessions[session_id] = {
    "status": "pending" | "running" | "completed" | "failed",
    "progress": 0.0,          # 0-100
    "current_step": str,       # Human-readable step name
    "step_index": int,         # Current step number
    "total_steps": 5,          # Total steps
    "messages": list[str],     # JSON-encoded SSE messages
    "result": BootstrapResult, # Final result (on completion)
    "error": str | None,       # Error message (on failure)
}
```

### Progress Callback

The `BootstrapEngine` receives a `progress_callback` function that the API route wires to the session state. Each callback invocation appends a JSON progress message to `session["messages"]`, which the SSE generator polls every 500ms.

**Source:** `app/python-sidecar/sidecar/api/routes/bootstrap.py`

---

## 11. Generated Artifacts Summary

After a successful bootstrap, the following artifacts exist in the project:

| Artifact | Path | Purpose |
|----------|------|---------|
| Analysis | `.bootstrap_analysis.md` | Temporary analysis summary (used internally) |
| Roadmap | `.claude/planning/ROADMAP.md` | Milestone-based development plan with checkboxes |
| Project Instructions | `CLAUDE.md` | Session instructions for Claude Code |
| Git Ignore | `.gitignore` | Technology-appropriate ignore patterns |
| Architecture | `docs/ARCHITECTURE.md` | System design documentation |

The `BootstrapResult` tracks which artifacts were created:

```python
@dataclass
class BootstrapResult:
    success: bool
    artifacts: dict[str, Path]     # step_type -> output path
    errors: list[str]
    warnings: list[str]
    duration_seconds: float
    steps_completed: int
    steps_total: int
    step_results: list[StepResult] # Per-step status (success/failed/skipped)
```

---

## 12. Key Source Files

| File | Purpose |
|------|---------|
| `app/src/components/bootstrap/BootstrapWizard.tsx` | Wizard orchestrator (estimate, confirm, progress, result) |
| `app/src/components/bootstrap/BootstrapProgressView.tsx` | SSE-connected real-time progress display |
| `app/src/managers/projectManager.ts` | Zustand store with bootstrap state |
| `app/src/api/backend.ts` (lines 267-291) | Frontend API calls for readiness and bootstrap |
| `app/python-sidecar/sidecar/api/routes/bootstrap.py` | Backend SSE streaming and session management |
| `src/agents/bootstrap_engine.py` | Core engine with generators and partial-failure resilience |
