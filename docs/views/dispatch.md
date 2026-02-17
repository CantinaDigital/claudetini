# Task Dispatch System

> Last updated: 2026-02-17

## Purpose

The Task Dispatch system is Claudetini's mechanism for executing Claude Code tasks from the desktop dashboard. It follows an **SSE-first architecture with polling fallback**: every dispatch attempt first opens a Server-Sent Events stream for real-time output, and only falls back to HTTP polling if the SSE connection fails or drops before completion. The system also handles token/credit limit detection and offers automatic fallback to alternative providers (Codex, Gemini).

All dispatch state lives in a single Zustand store (`dispatchManager`) that every dispatch component subscribes to via selectors.

---

## Components

### Component Map

| Component | File | Role |
|-----------|------|------|
| `DispatchOverlay` | `components/dispatch/DispatchOverlay.tsx` | Full-screen modal showing real-time progress, output, and errors |
| `StreamingOutput` | `components/dispatch/StreamingOutput.tsx` | SSE output renderer with auto-scroll and line counting |
| `DispatchSummary` | `components/dispatch/DispatchSummary.tsx` | Post-dispatch results overlay (files changed, line stats, actions) |
| `DispatchMinimized` | `components/dispatch/DispatchMinimized.tsx` | Bottom-right pill indicator when overlay is hidden |
| `FallbackModal` | `components/dispatch/FallbackModal.tsx` | Alternative-provider dispatch modal (Codex/Gemini) |

---

## Dispatch Phase State Machine

The dispatch lifecycle is driven by a `DispatchPhase` type stored in `dispatchManager.phase`:

```
                          +---> streaming --+---> completing ---> idle (success)
                          |                 |
idle ---> starting ---+---+                 +---> failed
                      |                     |
                      +---> polling --------+---> token_limit ---> (FallbackModal)
                                            |
                                            +---> cancelled
```

### Phase Definitions

| Phase | Description | UI State |
|-------|-------------|----------|
| `idle` | No dispatch in progress. | No overlay visible. |
| `starting` | Dispatch initiated; backend connectivity verified, guard against double-dispatch applied. Timer started. | Overlay appears with spinner and "Queueing dispatch job..." status. |
| `streaming` | SSE EventSource opened. Real-time output lines arriving via `onmessage`. | Overlay shows `StreamingOutput` component with live cursor. Header reads "Streaming Claude Code...". |
| `polling` | SSE failed or was unavailable. HTTP polling loop active (1s interval, 45-minute timeout). | Overlay shows "Live Output" section tailing the output file. Header reads "Running Claude Code...". |
| `completing` | Transitional state as the dispatch result is processed. | Brief; immediately transitions to `idle` or `failed`. |
| `failed` | Dispatch ended with an error. | Overlay shows error details, output tail, log file path, and action buttons (Retry / Try Codex-Gemini / Close). |
| `token_limit` | Claude Code hit a usage or token limit. | Overlay closes; `FallbackModal` opens with the original prompt pre-loaded. |
| `cancelled` | User cancelled the dispatch. | All state reset; overlay closes; toast notification. |

### Phase Transitions

1. **idle -> starting**: `execute()` is called. State is initialized, timer starts, `showOverlay` set to `true`.
2. **starting -> streaming**: `attemptStreaming()` opens an EventSource. `isStreaming` becomes `true`.
3. **streaming -> idle**: SSE receives a `complete` event with `status: "success"`. `completeDispatch()` cleans up.
4. **streaming -> failed**: SSE receives a `complete` event with `status: "failed"`, or `errorDetail` is set.
5. **streaming -> token_limit**: SSE receives `complete` with `status: "token_limit"`. `triggerFallback()` opens the FallbackModal.
6. **streaming -> polling**: SSE connection drops (onerror) without a `complete` event. The existing `sseJobId` is reused for polling.
7. **starting -> polling**: `attemptStreaming()` throws. A new dispatch job is created via `api.dispatchStart()`.
8. **polling -> idle**: Poll returns `done: true` with `result.success === true`.
9. **polling -> failed**: Poll returns `done: true` with `result.success === false`.
10. **polling -> token_limit**: Poll result indicates token/credit limit reached.
11. **any active -> cancelled**: User clicks Cancel; `cancel()` closes EventSource, calls backend cancel API, invokes `cancelDispatch()`.

---

## SSE Streaming vs HTTP Polling Fallback

### SSE Streaming (Primary)

The SSE path provides real-time, line-by-line output from Claude Code:

1. **Initiation**: `api.streamStart(projectPath, { prompt })` creates the job and returns a `StreamStartResult` with `job_id` and `stream_url`.
2. **Connection**: An `EventSource` is opened to `{API_BASE_URL}/api/dispatch/stream/{job_id}`.
3. **Events received**:
   - `start` -- Stream connected acknowledgment. Progress bumped to 10%.
   - `status` -- Status text updates (e.g., "processing"). Progress may increase.
   - `output` -- A single line of Claude Code output. Appended to `streamOutputLines` (capped at 1000 lines). The last 24 lines are mirrored into `outputTail`.
   - `error` -- Error detail text stored in `errorDetail`.
   - `complete` -- Terminal event carrying a `StreamCompletionStatus`: `"success"`, `"failed"`, `"cancelled"`, or `"token_limit"`. Triggers `handleStreamCompletion()`.
4. **Cleanup**: On completion or error, `closeEventSource()` closes the EventSource. The elapsed timer is cleared.

### HTTP Polling (Fallback)

If SSE fails, the system seamlessly falls back to polling:

1. **Job reuse**: If SSE had already obtained a `sseJobId` before failing, that job ID is reused for polling (no duplicate job creation).
2. **New job**: If SSE failed before getting a job ID, `api.dispatchStart()` creates a new job.
3. **Poll loop**: `pollDispatchJob()` calls `api.getDispatchStatus(jobId)` every 1 second, up to 45 minutes (2700 iterations).
4. **Output tailing**: During polling, the system also calls `api.readDispatchOutput(sessionId)` to tail the log file for live CLI output, tracking `lastTailLineCount` to detect new lines.
5. **Progress heuristic**: Progress is estimated from elapsed time (`12 + elapsed * 2`, capped at 94%) plus status-based bumps (queued = 8%, running = 30%).
6. **Completion**: When `status.done` is `true`, the result payload is inspected for success, failure, or token limit.

---

## DispatchOverlay

**File**: `app/src/components/dispatch/DispatchOverlay.tsx`

Full-screen overlay that appears whenever a dispatch is running or has failed. It is the primary dispatch UI.

### Props

```typescript
interface DispatchOverlayProps {
  onRetry: () => void;  // Called when user clicks "Retry dispatch"
}
```

### State (from dispatchManager)

| Selector | Type | Purpose |
|----------|------|---------|
| `isDispatching` | `boolean` | Whether a dispatch is actively running |
| `isStreaming` | `boolean` | Whether SSE streaming is active |
| `streamOutputLines` | `string[]` | Lines received via SSE |
| `dispatchFailed` | `boolean` | Whether the last dispatch failed |
| `showOverlay` | `boolean` | Whether the overlay should render |
| `progressPct` | `number` | Progress bar percentage (3-100) |
| `elapsedSeconds` | `number` | Seconds since dispatch started |
| `jobId` | `string \| null` | Backend job identifier |
| `promptPreview` | `string` | Whitespace-normalized prompt text |
| `statusText` | `string` | Current status message |
| `errorDetail` | `string \| null` | Error message on failure |
| `outputTail` | `string \| null` | Last N lines of output (polling mode) |
| `logFile` | `string \| null` | Path to the dispatch log file |
| `lastContext` | `DispatchContext \| null` | The prompt/mode/source of the last dispatch |

### Local State

| State | Type | Purpose |
|-------|------|---------|
| `isCancelling` | `boolean` | Disables Cancel button during async cancel |

### Visual Sections

1. **Header**: Spinner (running) or error icon (failed) with dynamic title:
   - "Streaming Claude Code..." (SSE active)
   - "Running Claude Code..." (polling)
   - "Dispatch Failed" (error state)

2. **Status text**: Below header; shows `statusText` or a default message.

3. **Progress bar**: Animated width transition. Blue (`bg-mc-accent`) when running, red (`bg-mc-red`) when failed. Minimum width of 3%.

4. **Elapsed time + Job ID**: Formatted as `M:SS`. Job ID shown when available.

5. **Prompt preview**: Scrollable box showing the normalized prompt text.

6. **Streaming output** (SSE mode): Renders `StreamingOutput` component with `maxHeight={200}` when `isStreaming && streamOutputLines.length > 0`.

7. **Live output** (polling mode): Monospace output area showing the last 20 lines of `outputTail`, with diff-aware syntax coloring (green for additions, red for removals, cyan for hunk headers).

8. **Error details** (failed state): Red-bordered box with `errorDetail`. If `outputTail` contains diff content, rendered via `DiffBlock`; otherwise as plain text. Log file path shown below.

9. **Action buttons**:
   - **Running**: "Cancel" (triggers `cancelAction()` with loading state) and "Hide" (sets `showOverlay: false`).
   - **Failed**: "Retry dispatch" (`onRetry`), "Try Codex/Gemini" (`handleTryFallback` -- closes overlay, opens FallbackModal), "Close" (`closeOverlay`).

### Interactions

- **Cancel**: Calls `cancel()` on the dispatch manager. Disables button during the async operation.
- **Hide**: Sets `showOverlay: false` without cancelling. Dispatch continues in background; `DispatchMinimized` becomes visible.
- **Try Codex/Gemini**: Closes the overlay and transitions state to show the `FallbackModal` with the original prompt, output, and error detail pre-loaded.
- **Retry**: Delegates to parent via `onRetry` prop.

### Visibility Logic

Returns `null` if `!showOverlay` or if `!isDispatching && !dispatchFailed`.

---

## StreamingOutput

**File**: `app/src/components/dispatch/StreamingOutput.tsx`

Dedicated real-time output display for SSE streaming. Features auto-scroll with scroll-lock detection.

### Props

```typescript
interface StreamingOutputProps {
  maxHeight?: number;         // Default: 200 (px)
  showLineNumbers?: boolean;  // Default: false
}
```

### State (from dispatchManager)

| Selector | Type | Purpose |
|----------|------|---------|
| `streamOutputLines` | `string[]` | All lines received from SSE |
| `isStreaming` | `boolean` | Whether the stream is active (controls live indicator and cursor) |

### Local State

| State | Type | Purpose |
|-------|------|---------|
| `autoScroll` | `boolean` | Whether the container auto-scrolls to bottom on new lines |
| `userScrolled` | `boolean` | Whether the user has manually scrolled away from bottom |

### Auto-Scroll Behavior

- **Default**: Auto-scroll is ON. New lines cause the container to scroll to bottom.
- **User scrolls up**: If the user scrolls more than 30px from the bottom, auto-scroll disables.
- **User scrolls back to bottom**: Auto-scroll re-enables automatically.
- **Toggle button**: Header bar includes an "Auto-scroll ON/OFF" button for manual override.

### Visual Sections

1. **Header bar**: Background surface with:
   - Green pulsing dot when `isStreaming`
   - "Live Output" label with line count
   - Auto-scroll toggle button (accent when ON, muted when OFF)

2. **Output container**: Monospace text at 10px, line-by-line rendering of `streamOutputLines`. Optional line numbers. Blinking cursor appended when streaming.

3. **Empty state**: Returns `null` when `streamOutputLines.length === 0`.

### Custom Animations

Defines two CSS keyframes via an inline `<style>` tag:
- `cc-pulse`: Opacity oscillation (1 -> 0.4 -> 1)
- `cc-blink`: Step-function blink (1 -> 0 -> 1)

---

## DispatchSummary

**File**: `app/src/components/dispatch/DispatchSummary.tsx`

Post-dispatch results overlay showing what changed, with actions to review, commit, or mark complete.

### Props

```typescript
interface DispatchSummaryProps {
  success: boolean;                 // Whether dispatch succeeded
  filesChanged: FileChange[];       // Array of changed files with stats
  totalAdded: number;               // Total lines added across all files
  totalRemoved: number;             // Total lines removed across all files
  summaryMessage: string | null;    // AI-generated summary (rendered as Markdown)
  hasErrors: boolean;               // Whether errors occurred during execution
  onReviewChanges: () => void;      // Opens diff review
  onMarkComplete: () => void;       // Marks the roadmap task as done
  onCommit: () => void;             // Commits the changes
  onClose: () => void;              // Closes the overlay
  outputTail?: string | null;       // Raw CLI output (shown when hasErrors)
}

interface FileChange {
  file: string;
  lines_added: number;
  lines_removed: number;
  status: string;
}
```

### Local State

| State | Type | Purpose |
|-------|------|---------|
| `showOutput` | `boolean` | Toggles visibility of error output section |

### Visual Sections

1. **Header**: Icon based on outcome:
   - Checkmark for success
   - Warning icon for "completed with errors"
   - Info icon for "task ended" (neither success nor errors)
   - Title + `summaryMessage` rendered via `InlineMarkdown`

2. **Error output** (conditional): Collapsible section shown only when `hasErrors && outputTail`. Toggle button labeled "Claude Code Output (errors)". Content rendered as `DiffBlock` if it looks like a diff, otherwise as a `<pre>` block.

3. **Stats bar**: Three columns -- Files Changed (count), Lines Added (green), Lines Removed (red). Only shown when files were changed.

4. **File list**: Scrollable monospace list of changed files with per-file `+added` / `-removed` counts.

5. **No changes message**: Centered text when `filesChanged.length === 0`.

6. **Actions** (two rows when files changed):
   - Row 1: "Review Changes" (primary) + "Mark Task Complete" (only if `success`)
   - Row 2: "Commit Changes" + "Close"
   - When no files changed: single "Close" button

### Interactions

- **Backdrop click**: Calls `onClose`.
- **Inner panel click**: Stops propagation to prevent backdrop close.
- **Review Changes**: Delegates to parent for diff viewing.
- **Mark Task Complete**: Marks the corresponding roadmap item as done.
- **Commit Changes**: Triggers a git commit workflow.

---

## DispatchMinimized

**File**: `app/src/components/dispatch/DispatchMinimized.tsx`

Minimal bottom-right indicator visible when a dispatch is running but the overlay has been hidden.

### Props

None. Entirely driven by `dispatchManager` state.

### State (from dispatchManager)

| Selector | Type | Purpose |
|----------|------|---------|
| `isDispatching` | `boolean` | Whether a dispatch is running |
| `showOverlay` | `boolean` | Whether the full overlay is shown |
| `elapsedSeconds` | `number` | Running timer |

### Visibility Logic

Returns `null` unless `isDispatching && !showOverlay`. This means it only appears when the user has clicked "Hide" on the DispatchOverlay.

### Visual

Fixed-position pill in the bottom-right corner (`z-[9997]`). Displays:
- "Claude dispatch running (M:SS)"
- "Show" button that sets `showOverlay: true` to restore the full overlay.

---

## FallbackModal

**File**: `app/src/components/dispatch/FallbackModal.tsx`

Modal for running a task via an alternative AI provider (Codex or Gemini) when Claude Code hits a token or credit limit.

### Props

```typescript
interface FallbackModalProps {
  prompt: string;                           // The original task prompt
  preferredProvider: FallbackProvider;       // User's preferred fallback ("codex" | "gemini")
  isRunning: boolean;                       // Whether a fallback dispatch is active
  runningProvider: FallbackProvider | null;  // Which provider is currently running
  output?: string | null;                   // Output from the fallback run
  error?: string | null;                    // Error message from fallback
  errorCode?: string | null;               // Error code (e.g., "execution_failed")
  statusText?: string | null;              // Status updates during fallback
  phase?: string | null;                   // Fallback phase label
  onRun: (provider: FallbackProvider) => void;  // Start fallback with chosen provider
  onClose: () => void;                     // Close the modal
}

type FallbackProvider = "codex" | "gemini";
```

### Visual Sections

1. **Header**:
   - Running state: Spinner + "Running via CODEX/GEMINI..." (cyan text)
   - Idle state: "Claude Code token limit reached"
   - Subtitle: "This may take a few minutes" (running) or "Run this task with an alternative?" (idle)
   - Status line with phase indicator when running
   - Prompt preview in monospace box

2. **Provider buttons**:
   - "Run via Codex" -- primary-styled when `preferredProvider === "codex"`
   - "Run via Gemini" -- primary-styled when `preferredProvider === "gemini"`
   - Both disabled during execution; active button shows "Running..."
   - "Close" button (disabled during execution)

3. **Error display** (conditional): Red-bordered box with `errorCode: error` format.

4. **Output display** (conditional): Scrollable monospace `<pre>` block showing fallback output.

### Interactions

- **Backdrop click**: Calls `onClose` only when not running.
- **Run via Codex/Gemini**: Calls `onRun(provider)`. The dispatch manager's `runFallback()` builds a specialized prompt wrapper and polls the fallback job.
- **Close**: Only available when not running. Calls `closeFallback()` on the manager.

### Fallback Prompt Construction

The `buildFallbackPrompt()` function wraps the original prompt with provider-specific instructions:
- Do not ask clarifying questions
- Do not wait for confirmation
- Keep unrelated dirty files untouched
- Modify only files needed
- Run relevant gates and report pass/fail

---

## Token Limit Detection and Recovery

The dispatch system detects token/credit limits through two paths:

### SSE Path
When the stream completes with `status: "token_limit"`, `handleStreamCompletion()` calls `triggerFallback()`.

### Polling Path
After polling completes, the result is inspected for:
1. `result.token_limit_reached === true`
2. Error text containing:
   - "you've exceeded your usage limit"
   - "your claude.ai usage limit"
   - "please wait until your limit resets"

### Recovery Flow

```
Token limit detected
  -> triggerFallback(prompt, output, error)
  -> showFallbackModal: true
  -> FallbackModal renders with original prompt
  -> User selects Codex or Gemini
  -> runFallback(provider, projectPath)
  -> api.dispatchFallbackStart({provider, prompt, projectPath})
  -> Poll api.getDispatchFallbackStatus(jobId) every 1s
  -> Complete or fail
```

### Fallback Phase Machine

```
idle -> queued -> running -> complete
                          -> failed
```

The fallback has its own separate state slice (`fallbackPhase`, `fallbackPrompt`, `fallbackOutput`, `fallbackError`, etc.) that is independent of the main dispatch phase.

---

## State Management (dispatchManager)

**File**: `app/src/managers/dispatchManager.ts`

A Zustand store created with `create<DispatchManagerState>()` that serves as the single source of truth for all dispatch-related state.

### State Shape

```typescript
interface DispatchManagerState {
  // Phase state machine
  phase: DispatchPhase;
  jobId: string | null;
  startedAt: number | null;
  elapsedSeconds: number;
  progressPct: number;
  statusText: string;
  context: DispatchContext | null;       // Current pending context
  lastContext: DispatchContext | null;    // Last executed context (for retry)
  promptPreview: string;
  streamOutputLines: string[];           // SSE output lines (max 1000)
  streamSequence: number;               // SSE sequence counter
  outputTail: string | null;            // Last ~24 lines of output
  logFile: string | null;               // Path to dispatch log
  errorDetail: string | null;
  showOverlay: boolean;

  // Fallback state
  fallbackPhase: FallbackPhase;
  fallbackPrompt: string | null;
  fallbackOutput: string | null;
  fallbackError: string | null;
  fallbackErrorCode: string | null;
  fallbackJobId: string | null;
  fallbackStatusText: string;
  fallbackProvider: "codex" | "gemini" | null;

  // Queue
  queue: QueuedDispatch[];

  // Milestone Plan Mode
  milestonePlanPhase: MilestonePlanPhase;
  milestonePlanContext: MilestonePlanContext | null;
  milestonePlanOutput: string | null;

  // Derived booleans
  isDispatching: boolean;
  dispatchFailed: boolean;
  isStreaming: boolean;
  showFallbackModal: boolean;
  isFallbackRunning: boolean;
}
```

### DispatchContext

```typescript
interface DispatchContext {
  prompt: string;
  mode: string;       // "standard" | "with-review" | "full-pipeline" | "blitz"
  source: "overview" | "roadmap" | "ask" | "task" | "queue" | "fix" | "gates" | "logs" | "timeline";
  itemRef?: { text: string; prompt?: string };  // Roadmap item reference for auto-marking
}
```

### Actions

| Action | Signature | Description |
|--------|-----------|-------------|
| `execute` | `(context, projectPath) => Promise<void>` | Main entry point. Guards against double-dispatch, tries SSE then polling, handles all outcomes. |
| `cancel` | `() => Promise<void>` | Cancels active dispatch. Closes EventSource, calls backend cancel API, resets state. |
| `retry` | `(projectPath) => void` | Re-executes the `lastContext`. |
| `runFallback` | `(provider, projectPath, cliPath?) => Promise<void>` | Runs the fallback dispatch via Codex or Gemini CLI. |
| `closeFallback` | `() => void` | Closes the FallbackModal (blocked if fallback is running). |
| `closeOverlay` | `() => void` | Hides the overlay. If dispatching, just hides; if not, resets error state. |
| `reset` | `() => void` | Full state reset. Clears timer and EventSource. |
| `cleanup` | `() => void` | Clears timer and EventSource without resetting state. |
| `setContext` | `(context) => void` | Sets the pending dispatch context. |
| `removeFromQueue` | `(id) => void` | Removes a queued dispatch by ID. |
| `dispatchNext` | `(projectPath) => void` | Dequeues and executes the next item. |
| `startMilestonePlan` | `(context) => void` | Enters milestone planning mode. |
| `completePlanPhase` | `(planOutput) => void` | Transitions from planning to reviewing. |
| `executeMilestone` | `(mode, projectPath, userNotes?) => void` | Builds execution prompt from plan output and executes. |
| `resetMilestonePlan` | `() => void` | Resets milestone plan state to idle. |

### Module-Level Resources

These live outside the Zustand store to avoid reactivity overhead:

| Resource | Type | Purpose |
|----------|------|---------|
| `timerInterval` | `ReturnType<typeof setInterval>` | 1-second elapsed timer |
| `eventSource` | `EventSource` | Active SSE connection |
| `projectPathRef` | `string` | Cached project path for post-dispatch operations |
| `sseJobId` | `string` | Job ID from SSE stream start (reused for polling fallback) |
| `lastTailLineCount` | `number` | Tracks output tailing position during polling |

### Internal Helper Functions

| Function | Description |
|----------|-------------|
| `startTimer()` | Starts the 1-second interval that updates `elapsedSeconds` and `progressPct`. |
| `completeDispatch()` | Clears timer/EventSource, resets to idle with `progressPct: 100`. |
| `failDispatch(error, output?, logFile?)` | Clears timer/EventSource, sets `dispatchFailed: true`, keeps overlay open. |
| `cancelDispatch()` | Clears timer/EventSource, resets all state, hides overlay. |
| `triggerFallback(prompt, output, error)` | Clears timer/EventSource, opens FallbackModal with pre-loaded data. |
| `pollDispatchJob(jobId)` | Polling loop with output tailing. Returns the final status when `done: true`. |
| `attemptStreaming(prompt, projectPath)` | Opens SSE EventSource, handles events, returns `true` on completion. |
| `handleStreamEvent(event, onComplete)` | Dispatches SSE events to state updates. |
| `handleStreamCompletion(status)` | Processes `StreamCompletionStatus` into success/failure/token-limit/cancel. |

### Dispatch Mode Flags

The `mode` field maps to CLI flags via `getDispatchFlags()`:

| Mode | CLI Flag |
|------|----------|
| `standard` | (none) |
| `with-review` | `--agents` |
| `full-pipeline` | `--agents --full-pipeline` |
| `blitz` | `--blitz` |

### Milestone Plan Integration

The dispatch system supports a two-phase milestone execution flow:

1. **Planning phase** (`milestonePlanPhase: "planning"`): A dispatch runs to generate an implementation plan. When it completes successfully, `completePlanPhase()` is called instead of the normal success path, transitioning to `"reviewing"`.

2. **Reviewing phase** (`milestonePlanPhase: "reviewing"`): The `MilestonePlanReview` component displays the plan output. The user can add notes and select an execution mode.

3. **Execution phase** (`milestonePlanPhase: "executing"`): `executeMilestone()` builds a comprehensive prompt including the plan output, task list, and user notes, then calls `execute()` for the actual implementation.

### Queue System

The dispatch manager includes a dispatch queue (`QueuedDispatch[]`):
- Items are added by various UI sources (ask, task, fix, queue)
- `dispatchNext(projectPath)` dequeues the first item and executes it
- Guards prevent execution when `isDispatching` is already `true`
- `removeFromQueue(id)` allows manual removal

---

## Data Flow Diagram

```
User Action (Dispatch button)
  |
  v
execute(context, projectPath)
  |
  +-- Guards: backend connected? not already dispatching?
  |
  +-- Set phase: "starting", show overlay, start timer
  |
  +-- attemptStreaming()
  |     |
  |     +-- api.streamStart() -> job_id
  |     +-- new EventSource(stream_url)
  |     |     |
  |     |     +-- onmessage: handleStreamEvent()
  |     |     |     +-- "output" -> append to streamOutputLines
  |     |     |     +-- "status" -> update statusText
  |     |     |     +-- "complete" -> handleStreamCompletion()
  |     |     |
  |     |     +-- onerror: close ES, reject -> fall to polling
  |     |
  |     +-- Returns true on success, throws on failure
  |
  +-- [If SSE fails] pollDispatchJob(jobId)
        |
        +-- Loop: api.getDispatchStatus(jobId) every 1s
        +-- Tail: api.readDispatchOutput(sessionId)
        +-- When done: check result.success / token_limit
        |
        +-- completeDispatch() | failDispatch() | triggerFallback()
```

---

## Edge Cases

1. **Double-dispatch guard**: `execute()` checks `isDispatching` and returns early with a console warning if already running.

2. **SSE to polling handoff**: If SSE obtained a `job_id` before failing, that ID is reused for polling to avoid creating a duplicate backend job.

3. **Polling timeout**: After 45 minutes (2700 polls at 1s each), the poll loop throws a timeout error.

4. **Fallback blocking**: The FallbackModal's close button is disabled while a fallback dispatch is running. `closeFallback()` also checks `isFallbackRunning`.

5. **Overlay hide vs cancel**: "Hide" only sets `showOverlay: false`; the dispatch continues. "Cancel" actually stops the backend job.

6. **Progress estimation**: Progress is heuristic-based -- time-driven (`12 + elapsed * 2`, capped at 94%) with status-based floor bumps. Never reaches 100% until `completeDispatch()`.

7. **Output line cap**: SSE `streamOutputLines` are capped at 1000 lines (`.slice(-1000)`). Polling output tail shows the last 24 lines.

8. **Milestone plan interception**: When `milestonePlanPhase === "planning"`, a successful dispatch does not follow the normal success path. Instead, `completePlanPhase()` captures the output and transitions to the review UI.
