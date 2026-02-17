# State Management

> Last updated: 2026-02-17

Comprehensive reference for the Claudetini frontend state architecture: Zustand stores, API client, caching, cross-store interactions, and TypeScript interfaces.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Store Catalog](#2-store-catalog)
   - [projectManager](#21-projectmanager)
   - [dispatchManager](#22-dispatchmanager)
   - [gitManager](#23-gitmanager)
   - [reconciliationManager](#24-reconciliationmanager)
   - [parallelManager](#25-parallelmanager)
   - [settingsStore](#26-settingsstore)
3. [API Client Architecture](#3-api-client-architecture)
4. [Data Caching Strategy](#4-data-caching-strategy)
5. [Cross-Store Interactions](#5-cross-store-interactions)
6. [TypeScript Interface Catalog](#6-typescript-interface-catalog)

---

## 1. Architecture Overview

Claudetini uses a **Domain Manager** pattern built on Zustand 5. Rather than a single monolithic store, state is divided into five domain-specific Zustand stores (called "managers") plus one settings store, each of which owns the complete lifecycle of its domain: reactive state, API calls, long-running polling, timer management, and cleanup.

```
app/src/
  managers/
    index.ts                  # Barrel exports for all managers
    projectManager.ts         # Project selection, readiness, bootstrap
    dispatchManager.ts        # Claude Code dispatch lifecycle
    gitManager.ts             # Git status, staging, commits, push
    reconciliationManager.ts  # Roadmap reconciliation analysis
    parallelManager.ts        # Multi-agent parallel execution
  stores/
    settingsStore.ts          # User preferences (localStorage-persisted)
  hooks/
    useDataCache.ts           # In-memory TTL cache for API responses
  api/
    backend.ts                # HTTP client to Python sidecar
  types/
    index.ts                  # All TypeScript interfaces
```

### Design Principles

- **One domain, one store.** Each manager encapsulates a single concern. No store directly mutates another store's state.
- **Module-scoped side effects.** Timers (`setInterval`), EventSource connections, and polling loops live as module-level variables outside reactive state, with explicit `cleanup()` methods.
- **Thin components.** Components subscribe to store slices with `useManagerName((s) => s.field)` selectors and call store actions. Business logic stays in managers.
- **Cross-store orchestration in App.tsx.** The root `App` component wires together cross-domain flows (e.g., dispatch completion triggers reconciliation check) via `useEffect` hooks that observe multiple stores.

### Store Access Pattern

```tsx
// Component subscribes to a slice (re-renders only when that field changes)
const phase = useDispatchManager((s) => s.phase);
const execute = useDispatchManager((s) => s.execute);

// External store access (outside React render, e.g., in another store)
const maxParallel = useSettingsStore.getState().maxParallelAgents;
```

---

## 2. Store Catalog

### 2.1 projectManager

**File:** `app/src/managers/projectManager.ts`
**Hook:** `useProjectManager`
**Purpose:** Application-level screen state machine and project selection.

#### State Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `currentScreen` | `"picker" \| "scorecard" \| "bootstrap" \| "dashboard"` | `"picker"` | Active application screen. Controls which top-level view is rendered. |
| `currentProject` | `Project \| null` | `null` | The currently selected project. Set after the user picks a project and readiness check passes. |
| `projects` | `Project[]` | `[]` | All registered projects returned by the backend. |
| `readinessScore` | `number \| null` | `null` | Numeric readiness score (0-100) from the most recent scan. |
| `readinessReport` | `ReadinessReport \| null` | `null` | Full readiness report with individual check results. |
| `bootstrapSessionId` | `string \| null` | `null` | Session ID of an in-progress bootstrap dispatch. |
| `bootstrapInProgress` | `boolean` | `false` | Whether the bootstrap process is currently running. |
| `isLoading` | `boolean` | `false` | Loading indicator for async operations (project list, readiness scan). |
| `error` | `string \| null` | `null` | Most recent error message. |

#### Actions

| Action | Signature | Behavior |
|--------|-----------|----------|
| `setScreen` | `(screen: AppScreen) => void` | Directly sets the active application screen. |
| `loadProjects` | `() => Promise<void>` | Calls `api.listProjects()`, populates `projects`. Sets `isLoading` during fetch. |
| `scanReadiness` | `(projectPath: string) => Promise<void>` | Calls `api.scanReadiness()`, populates `readinessScore` and `readinessReport`. |
| `startBootstrap` | `(projectPath: string) => Promise<void>` | Calls `api.startBootstrap()`, stores `bootstrapSessionId`. |
| `completeBootstrap` | `() => void` | Clears bootstrap state and transitions screen to `"dashboard"`. |

#### Persistence

None. All state is ephemeral and reset on app reload.

#### Polling/Refresh

None. Data is fetched on-demand via explicit action calls.

#### Consuming Components

- `AppRouter.tsx` -- screen routing
- `App.tsx` -- reads `currentProject.path` as `activeProjectPath`
- `ScorecardView.tsx` -- readiness display
- `OverviewTab.tsx` -- project context

---

### 2.2 dispatchManager

**File:** `app/src/managers/dispatchManager.ts`
**Hook:** `useDispatchManager`
**Purpose:** Full lifecycle management of Claude Code dispatch jobs: SSE streaming, polling fallback, fallback providers, dispatch queue, and milestone plan mode.

#### State Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `phase` | `DispatchPhase` | `"idle"` | Current phase: `"idle"`, `"starting"`, `"streaming"`, `"polling"`, `"completing"`, `"failed"`, `"token_limit"`, `"cancelled"`. |
| `jobId` | `string \| null` | `null` | Backend job ID for the active dispatch. |
| `startedAt` | `number \| null` | `null` | `Date.now()` timestamp when dispatch started. |
| `elapsedSeconds` | `number` | `0` | Seconds since dispatch started. Updated by a 1-second `setInterval`. |
| `progressPct` | `number` | `0` | Synthetic progress bar value (0-100). Advances based on phase transitions and elapsed time. |
| `statusText` | `string` | `""` | Human-readable status message shown in the overlay. |
| `context` | `DispatchContext \| null` | `null` | Pending dispatch context (set before pre-flight, cleared on execute). |
| `lastContext` | `DispatchContext \| null` | `null` | Context of the most recently executed dispatch. Used for retry. |
| `promptPreview` | `string` | `""` | Collapsed single-line version of the prompt for display. |
| `streamOutputLines` | `string[]` | `[]` | Accumulated SSE output lines (capped at last 1000). |
| `streamSequence` | `number` | `0` | Highest SSE sequence number received. |
| `outputTail` | `string \| null` | `null` | Last ~24 lines of output (from SSE or polling tail). Shown in the overlay. |
| `logFile` | `string \| null` | `null` | Path to the dispatch log file on the backend. |
| `errorDetail` | `string \| null` | `null` | Error message when dispatch fails. |
| `showOverlay` | `boolean` | `false` | Whether the full-screen DispatchOverlay is visible. |
| `fallbackPhase` | `FallbackPhase` | `"idle"` | Fallback provider phase: `"idle"`, `"queued"`, `"running"`, `"complete"`, `"failed"`. |
| `fallbackPrompt` | `string \| null` | `null` | Prompt prepared for fallback execution. |
| `fallbackOutput` | `string \| null` | `null` | Output from fallback provider execution. |
| `fallbackError` | `string \| null` | `null` | Error from fallback provider. |
| `fallbackErrorCode` | `string \| null` | `null` | Machine-readable error code from fallback. |
| `fallbackJobId` | `string \| null` | `null` | Backend job ID for the fallback dispatch. |
| `fallbackStatusText` | `string` | `""` | Human-readable fallback status message. |
| `fallbackProvider` | `"codex" \| "gemini" \| null` | `null` | Which fallback provider is currently running. |
| `queue` | `QueuedDispatch[]` | `[]` | FIFO queue of pending dispatch jobs. |
| `milestonePlanPhase` | `MilestonePlanPhase` | `"idle"` | Sub-state machine for milestone planning: `"idle"`, `"planning"`, `"reviewing"`, `"executing"`, `"complete"`, `"failed"`. |
| `milestonePlanContext` | `MilestonePlanContext \| null` | `null` | Milestone metadata for plan mode (ID, title, remaining items, combined prompt). |
| `milestonePlanOutput` | `string \| null` | `null` | Raw output from the planning dispatch, shown in the plan review overlay. |
| `isDispatching` | `boolean` | `false` | Derived: `true` when any dispatch is actively running. |
| `dispatchFailed` | `boolean` | `false` | Derived: `true` when the last dispatch ended in failure. |
| `isStreaming` | `boolean` | `false` | Derived: `true` when connected via SSE. |
| `showFallbackModal` | `boolean` | `false` | Derived: `true` when the fallback provider chooser should be displayed. |
| `isFallbackRunning` | `boolean` | `false` | Derived: `true` when a fallback provider dispatch is in progress. |

#### Actions

| Action | Signature | Behavior |
|--------|-----------|----------|
| `setContext` | `(context: DispatchContext \| null) => void` | Sets the pending dispatch context (before pre-flight). |
| `removeFromQueue` | `(id: string) => void` | Removes a queued dispatch by ID. |
| `dispatchNext` | `(projectPath: string) => void` | Dequeues and executes the next queued dispatch. No-op if already dispatching or queue is empty. |
| `execute` | `(context: DispatchContext, projectPath: string) => Promise<void>` | Main dispatch entry point. Attempts SSE streaming first; falls back to polling on failure. Handles success, failure, and token-limit outcomes. Guards against double-dispatch. |
| `cancel` | `() => Promise<void>` | Cancels the active dispatch (SSE or polled). Calls backend cancel API, then cleans up local state. |
| `retry` | `(projectPath: string) => void` | Re-executes using `lastContext`. |
| `runFallback` | `(provider, projectPath, cliPath?) => Promise<void>` | Runs a fallback dispatch via Codex or Gemini CLI. Polls fallback job status at 1-second intervals. |
| `closeFallback` | `() => void` | Closes the fallback modal (blocked while fallback is running). |
| `closeOverlay` | `() => void` | Closes the dispatch overlay. If dispatching, hides overlay without resetting state. |
| `reset` | `() => void` | Full state reset to idle. Clears timer and EventSource. |
| `cleanup` | `() => void` | Clears timer and EventSource without resetting state. Called on component unmount. |
| `startMilestonePlan` | `(context: MilestonePlanContext) => void` | Enters milestone planning mode. |
| `completePlanPhase` | `(planOutput: string) => void` | Transitions milestone plan from `"planning"` to `"reviewing"` with the plan output. |
| `executeMilestone` | `(mode, projectPath, userNotes?) => void` | Builds an execution prompt from plan output and dispatches it. |
| `resetMilestonePlan` | `() => void` | Resets milestone plan state to idle. |

#### Module-Level Resources

- **`timerInterval`**: 1-second `setInterval` that increments `elapsedSeconds` and advances `progressPct`.
- **`eventSource`**: `EventSource` instance for SSE streaming from `/api/dispatch/stream/{jobId}`.
- **`projectPathRef`**: Cached project path for use in module-scoped helpers.
- **`sseJobId`**: Tracks the job ID received during SSE stream start, enabling polling to reconnect to the same job if SSE fails.
- **`lastTailLineCount`**: Tracks output line count to show only new lines during polling.

#### Persistence

None. All state is ephemeral.

#### Polling/Refresh

- **Dispatch polling**: 1-second interval via `pollDispatchJob()`. Calls `api.getDispatchStatus()` and `api.readDispatchOutput()`. Maximum 45-minute timeout (2,700 polls).
- **Fallback polling**: 1-second interval inside `runFallback()`. Calls `api.getDispatchFallbackStatus()`. Maximum 45-minute timeout.
- **SSE streaming**: `EventSource` connected to `/api/dispatch/stream/{jobId}`. Processes `start`, `status`, `output`, `error`, and `complete` event types.

#### Consuming Components

- `App.tsx` -- orchestrates dispatch lifecycle, pre-flight, summary, milestone plan
- `DispatchOverlay.tsx` -- full-screen dispatch progress display
- `DispatchMinimized.tsx` -- minimized dispatch indicator
- `StreamingOutput.tsx` -- live SSE output viewer
- `MilestonePlanReview.tsx` -- milestone plan review overlay
- `OverviewTab.tsx` -- dispatch trigger from overview
- `RoadmapTab.tsx` -- dispatch trigger from roadmap items
- `LiveFeed.tsx` -- dispatch status indicator

---

### 2.3 gitManager

**File:** `app/src/managers/gitManager.ts`
**Hook:** `useGitManager`
**Purpose:** Git working tree state, staging area management, commits, push, and stash operations.

#### State Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `status` | `GitStatus \| null` | `null` | Full git status: branch, staged files, uncommitted files, untracked files, stashes, unpushed commits, submodule issues. |
| `commits` | `Commit[]` | `[]` | Recent commit history (default 30 commits). |
| `loading` | `boolean` | `false` | Whether a refresh is in progress. |
| `error` | `string \| null` | `null` | Most recent error message. |
| `commitMessage` | `string` | `""` | Current commit message being composed. |
| `isCommitting` | `boolean` | `false` | Whether a commit is in progress. |
| `isGeneratingMessage` | `boolean` | `false` | Whether an AI commit message is being generated. |

#### Actions

| Action | Signature | Behavior |
|--------|-----------|----------|
| `refresh` | `(projectId: string) => Promise<void>` | Fetches `gitStatus` and `commits` in parallel via `Promise.all`. |
| `stageFiles` | `(projectId: string, files: string[]) => Promise<void>` | Stages specific files, then auto-refreshes. |
| `stageAll` | `(projectId: string) => Promise<void>` | Stages all files, then auto-refreshes. |
| `unstageFiles` | `(projectId: string, files: string[]) => Promise<void>` | Unstages specific files, then auto-refreshes. |
| `unstageAll` | `(projectId: string) => Promise<void>` | Unstages all files, then auto-refreshes. |
| `setCommitMessage` | `(msg: string) => void` | Sets the commit message. |
| `generateMessage` | `(projectId: string) => Promise<void>` | Generates a rule-based commit message via `api.generateCommitMessage()`. |
| `generateMessageAI` | `(projectId: string) => Promise<void>` | Generates an AI-powered commit message via `api.generateCommitMessageAI()`. |
| `commit` | `(projectId: string) => Promise<boolean>` | Commits staged files with the current message. Returns `true` on success. Auto-refreshes. |
| `push` | `(projectId: string) => Promise<boolean>` | Pushes to remote. Returns `true` on success. Auto-refreshes. |
| `stashPop` | `(projectId: string) => Promise<void>` | Pops the top stash, then auto-refreshes. |
| `stashDrop` | `(projectId: string, stashId?: string) => Promise<void>` | Drops a stash entry, then auto-refreshes. |
| `discardFile` | `(projectId: string, file: string) => Promise<void>` | Discards changes to a single file (`git checkout`), then auto-refreshes. |
| `deleteUntracked` | `(projectId: string, file: string) => Promise<void>` | Deletes an untracked file, then auto-refreshes. |

#### Persistence

None. All state is ephemeral and re-fetched on demand.

#### Polling/Refresh

No automatic polling. The `refresh()` action is called explicitly by consuming components (e.g., when the Git tab becomes active or after a mutating operation).

#### Consuming Components

Currently consumed through the barrel export at `managers/index.ts`. The `GitTab` component manages its own git data fetching via `useDataCache` and direct `api` calls rather than exclusively through this manager. The gitManager provides the canonical commit workflow used by components that need staging + commit functionality.

---

### 2.4 reconciliationManager

**File:** `app/src/managers/reconciliationManager.ts`
**Hook:** `useReconciliationManager`
**Purpose:** Detects code changes that may correspond to completed roadmap items and presents suggestions for batch-marking items as done.

#### State Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `footerState` | `ReconciliationFooterState` | `"hidden"` | Footer bar state: `"hidden"`, `"changes_detected"`, `"analyzing"`, `"report_ready"`, `"no_matches"`, `"baseline_created"`. |
| `report` | `ReconciliationReport \| null` | `null` | Full reconciliation report with suggestions, file changes, and commit analysis. |
| `jobId` | `string \| null` | `null` | Backend job ID for the in-progress analysis. |
| `showModal` | `boolean` | `false` | Whether the reconciliation review modal is visible. |
| `checkedItems` | `Set<string>` | `new Set()` | Set of suggestion `item_text` strings the user has checked for acceptance. |

#### Actions

| Action | Signature | Behavior |
|--------|-----------|----------|
| `check` | `(projectId, { enabled }) => Promise<void>` | Quick-checks whether any code changes exist since last snapshot. Sets `footerState` to `"changes_detected"` or `"hidden"`. Respects the `enabled` flag (from settings). |
| `analyze` | `(projectId, { confidenceThreshold }) => Promise<void>` | Starts a full reconciliation analysis job. Transitions to `"analyzing"` and begins polling. |
| `verifyProgress` | `(projectId, { confidenceThreshold }) => Promise<void>` | Starts a progress verification job (rule-based). Polls and auto-opens modal on results. |
| `verifyProgressAI` | `(projectId, { confidenceThreshold }) => Promise<void>` | Starts an AI-powered progress verification. Same polling/modal behavior as `verifyProgress`. |
| `apply` | `(projectId, acceptedItems, dismissedItems) => Promise<void>` | Applies accepted suggestions (marks items done) and dismisses rejected ones. Refreshes roadmap cache afterward. |
| `undo` | `(projectId) => Promise<number>` | Undoes the last reconciliation application. Returns the number of items reverted. |
| `dismiss` | `() => void` | Resets footer state, clears report and job, stops polling. |
| `openModal` | `() => void` | Shows the reconciliation review modal. |
| `closeModal` | `() => void` | Hides the reconciliation review modal. |
| `toggleCheckedItem` | `(text: string) => void` | Toggles a single suggestion's checked state. |
| `toggleAllHighConfidence` | `() => void` | Toggles all suggestions with confidence >= 0.9 on or off. |
| `setFooterState` | `(state) => void` | Directly sets the footer state. |
| `cleanup` | `() => void` | Increments poll generation (invalidating stale callbacks) and clears polling interval. |

#### Module-Level Resources

- **`pollInterval`**: 2-second `setInterval` for polling job status.
- **`pollGeneration`**: Monotonically increasing counter. Each new poll increments it; stale poll callbacks check the counter before applying state updates, preventing race conditions.

#### Persistence

None. All state is ephemeral.

#### Polling/Refresh

- **Reconciliation status polling**: 2-second interval via `pollReconciliationStatus()` or `pollVerificationStatus()`. Calls `api.getReconciliationJobStatus()`. On completion, fetches the full report via `api.getReconciliationResult()`.
- **Stale poll guard**: Each poll loop captures its generation number. If a newer poll starts (incrementing `pollGeneration`), the old loop detects the mismatch and stops updating state.

#### Consuming Components

- `App.tsx` -- triggers `check()` on backend connect and after dispatch completion
- `OverviewTab.tsx` -- displays reconciliation status
- `ReconciliationFooter.tsx` -- footer bar with action buttons
- `ReconciliationModal.tsx` -- full review modal for accepting/dismissing suggestions

---

### 2.5 parallelManager

**File:** `app/src/managers/parallelManager.ts`
**Hook:** `useParallelManager`
**Purpose:** Orchestrates multi-agent parallel execution of milestone tasks: git cleanliness check, AI planning, plan review/replan, parallel agent execution, branch merging, verification, and finalization.

#### State Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `phase` | `ParallelPhase` | `"idle"` | Lifecycle phase: `"idle"`, `"git_check"`, `"planning"`, `"plan_review"`, `"replanning"`, `"executing"`, `"merging"`, `"verifying"`, `"finalizing"`, `"complete"`, `"failed"`, `"cancelled"`. |
| `milestoneTitle` | `string \| null` | `null` | Title of the milestone being executed. |
| `tasks` | `MilestoneItem[]` | `[]` | Remaining (undone) items from the milestone. |
| `error` | `string \| null` | `null` | Error message for the current phase. |
| `planJobId` | `string \| null` | `null` | Backend job ID for the planning agent. |
| `planOutputFile` | `string \| null` | `null` | Path to the planning agent's output file. |
| `planOutputTail` | `string \| null` | `null` | Tail of planning agent output (streamed during planning). |
| `plan` | `ExecutionPlan \| null` | `null` | AI-generated execution plan with phases, agent assignments, and success criteria. |
| `userFeedback` | `string` | `""` | User feedback for requesting a replan. |
| `isDirty` | `boolean` | `false` | Whether the git working tree has uncommitted changes. |
| `dirtyFiles` | `string[]` | `[]` | List of dirty file paths when `isDirty` is true. |
| `commitMessage` | `string` | `""` | Commit message for the pre-execution commit. |
| `isGeneratingMessage` | `boolean` | `false` | Whether an AI commit message is being generated. |
| `isCommitting` | `boolean` | `false` | Whether a commit is in progress. |
| `commitError` | `string \| null` | `null` | Error from the pre-execution commit. |
| `batchId` | `string \| null` | `null` | Backend batch ID for the execution run. |
| `agents` | `AgentSlotStatus[]` | `[]` | Per-agent status: task index, text, status, output tail, error, cost, group/phase IDs. |
| `mergeResults` | `MergeResultStatus[]` | `[]` | Per-branch merge results: success, conflicts, resolution method. |
| `currentPhaseId` | `number` | `0` | Currently executing phase ID from the plan. |
| `currentPhaseName` | `string` | `""` | Human-readable name of the current execution phase. |
| `verification` | `VerificationResult \| null` | `null` | Post-execution verification: overall pass, per-criterion results. |
| `verificationOutputTail` | `string \| null` | `null` | Tail of verification agent output. |
| `finalizeMessage` | `string \| null` | `null` | Summary message from the finalization step. |
| `totalCost` | `number` | `0` | Accumulated cost estimate across all agents. |
| `showOverlay` | `boolean` | `false` | Whether the parallel execution overlay is visible. |

#### Actions

| Action | Signature | Behavior |
|--------|-----------|----------|
| `startPlanning` | `(milestone, projectPath) => Promise<void>` | Entry point. Checks git cleanliness first. If dirty, shows commit UI. If clean, starts planning agent. |
| `approvePlan` | `(projectPath) => Promise<void>` | Executes the approved plan. Reads `maxParallelAgents` from settingsStore. Starts execution polling. |
| `replan` | `(projectPath) => Promise<void>` | Sends user feedback and current plan to the backend for a revised plan. Reads `lightModel` from settingsStore. |
| `cancel` | `() => Promise<void>` | Cancels the active planning or execution job. Best-effort backend cancel. |
| `closeOverlay` | `(projectPath?) => void` | Stops polling, clears persisted state, releases HMR lock, resets all state. |
| `reset` | `() => void` | Full state reset to initial values. |
| `cleanup` | `() => void` | Stops polling interval without resetting state. |
| `setCommitMessage` | `(msg: string) => void` | Sets the pre-execution commit message. |
| `generateCommitMessage` | `(projectPath) => Promise<void>` | Generates an AI commit message using `lightModel` from settingsStore. |
| `commitAndProceed` | `(projectPath) => Promise<void>` | Stages all, commits, re-checks git. If clean, auto-proceeds to planning. |
| `setUserFeedback` | `(feedback: string) => void` | Sets the replan feedback text. |

#### Module-Level Resources

- **`_pollInterval`**: 2-second `setInterval` used for both plan polling and execution polling.
- **`STORAGE_KEY`**: `"cantina:parallel-execution"` -- localStorage key for HMR/reload survival.

#### Persistence

**localStorage** (`cantina:parallel-execution`):
- Persists `{ batchId, phase, milestoneTitle }` during active execution.
- On module load, `_tryResumeExecution()` checks for persisted state and resumes execution polling if a non-terminal phase is found.
- Cleared when execution reaches a terminal phase (`complete`, `failed`, `cancelled`) or when the overlay is closed.

This allows the parallel execution overlay to survive Vite HMR reloads and full page refreshes during long-running multi-agent executions.

#### Polling/Refresh

- **Plan polling**: 2-second interval via `_startPlanPolling()`. Calls `api.parallelPlanStatus()`. Stops when plan status is `"complete"` or `"failed"`.
- **Execution polling**: 2-second interval via `_startExecutionPolling()`. Calls `api.parallelExecuteStatus()`. Updates agent statuses, merge results, verification, and cost. Stops on terminal phases.

#### Consuming Components

- `App.tsx` -- cleanup on unmount, `startPlanning` trigger from milestone actions
- `RoadmapTab.tsx` -- parallel execution trigger button
- `ParallelExecutionOverlay.tsx` -- full-screen multi-agent execution display

---

### 2.6 settingsStore

**File:** `app/src/stores/settingsStore.ts`
**Hook:** `useSettingsStore`
**Purpose:** User preferences and configuration. Fully persisted to localStorage.

#### State Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `codexPath` | `string` | `"codex"` | CLI path for OpenAI Codex. |
| `geminiPath` | `string` | `"gemini"` | CLI path for Google Gemini. |
| `preferredFallback` | `"codex" \| "gemini"` | `"codex"` | Which fallback provider to suggest first when Claude hits limits. |
| `usageMode` | `"subscription" \| "api"` | `"subscription"` | How Claude Code usage is billed. |
| `claudeRemainingPct` | `number` | `100` | Estimated remaining Claude usage percentage. |
| `fallbackThresholdPct` | `number` | `10` | Threshold below which fallback is suggested. |
| `preSessionHooks` | `HookCommand[]` | `[]` | Shell commands to run before each dispatch session. |
| `reconciliationEnabled` | `boolean` | `true` | Whether automatic reconciliation checking is active. |
| `reconciliationConfidenceThreshold` | `number` | `50` | Minimum confidence (30-90) for reconciliation suggestions. |
| `autoDispatchEnabled` | `boolean` | `false` | Whether auto-dispatch from queue is enabled. |
| `lightModel` | `string` | `"claude-haiku-4-5-20251001"` | Model used for lightweight tasks (commit messages, planning summaries). |
| `taskRouting` | `Record<string, string>` | `{ Coding: "Claude", Tests: "Claude", Documentation: "Gemini", ... }` | Per-task-type provider routing preferences. |
| `preflightChecks` | `Record<string, boolean>` | `{ "Uncommitted changes": true, ... }` | Toggle map for pre-flight check items. |
| `schedulingToggles` | `Record<string, boolean>` | `{ "Do-Not-Disturb mode": false, ... }` | Toggle map for scheduling features. |
| `branchStrategyToggles` | `{ autoCreateBranches, autoPR, autoMerge }` | all `false` | Branch automation toggles. |
| `postSessionHooks` | `HookCommand[]` | `[]` | Shell commands to run after each dispatch session. |
| `preMergeHooks` | `HookCommand[]` | `[]` | Shell commands to run before merge. |
| `postMergeHooks` | `HookCommand[]` | `[]` | Shell commands to run after merge. |
| `prePushHookEnabled` | `boolean` | `false` | Whether the pre-push hook is active. |
| `maxParallelAgents` | `number` | `3` | Maximum concurrent agents for parallel execution (1-8). |

#### Actions

| Action | Signature | Behavior |
|--------|-----------|----------|
| `setLightModel` | `(model: string) => void` | Updates `lightModel` and persists. |
| `setPreferredFallback` | `(provider) => void` | Updates `preferredFallback` and persists. |
| `addPreSessionHook` | `(cmd: string) => void` | Appends a new pre-session hook (enabled by default). |
| `updatePreSessionHook` | `(index, patch) => void` | Updates a pre-session hook's `cmd` or `enabled` status. |
| `removePreSessionHook` | `(index) => void` | Removes a pre-session hook by index. |
| `setAutoDispatch` | `(enabled) => void` | Toggles auto-dispatch. |
| `setTaskRouting` | `(task, provider) => void` | Sets routing for a specific task type. |
| `setPreflightCheck` | `(name, enabled) => void` | Toggles a preflight check. |
| `setSchedulingToggle` | `(name, enabled) => void` | Toggles a scheduling feature. |
| `setBranchStrategyToggle` | `(key, value) => void` | Toggles a branch automation feature. |
| `addHookToGroup` | `(group, cmd) => void` | Adds a hook to any hook group (post-session, pre-merge, post-merge). |
| `toggleHookInGroup` | `(group, index) => void` | Toggles a hook's enabled state within a group. |
| `removeHookFromGroup` | `(group, index) => void` | Removes a hook from a group. |
| `setPrePushHookEnabled` | `(enabled) => void` | Toggles pre-push hook. |
| `setMaxParallelAgents` | `(count) => void` | Sets max parallel agents (clamped 1-8). |

#### Persistence

**Full localStorage persistence** under key `"claudetini.fallback.settings.v1"`:
- All state fields are persisted on every mutation via `updateAndPersist()` or inline `persistSettings()` calls.
- On store creation, `loadSettings()` reads from localStorage with defensive parsing: each field is validated, type-checked, and falls back to defaults on any parse error.
- Hook arrays are sanitized via `_parseHookArray()`, which filters out malformed entries.
- Numeric fields are clamped to valid ranges (`_clampPct` for 0-100, `_clampRange` for custom bounds).

#### Polling/Refresh

None. Settings are purely user-driven.

#### Consuming Components

- `App.tsx` -- reads `preSessionHooks`, `preferredFallback`, `reconciliationEnabled`
- `SettingsTab.tsx` -- full settings UI
- `OverviewTab.tsx` -- reads various settings for dispatch advice
- `GatesTab.tsx` -- reads settings for gate display
- `GitTab.tsx` -- reads settings for commit workflow
- `ReconciliationFooter.tsx` -- reads `reconciliationEnabled`, `reconciliationConfidenceThreshold`
- `LiveFeed.tsx` -- reads `lightModel` for display
- `parallelManager.ts` -- reads `maxParallelAgents`, `lightModel` via `getState()`

---

## 3. API Client Architecture

**File:** `app/src/api/backend.ts`

The API client is a module-scoped HTTP client that communicates with the Python FastAPI sidecar on `http://127.0.0.1:9876`. It provides typed wrapper functions for every backend endpoint.

### 3.1 GET Deduplication

Concurrent GET requests to the same URL are deduplicated using an in-flight promise map:

```
_inflightGets: Map<string, Promise<unknown>>
```

When `fetchApi()` receives a GET request:
1. Checks `_inflightGets` for an existing promise for that URL.
2. If found, returns the existing promise (all callers share one network request).
3. If not found, creates the fetch promise, stores it in the map, and adds a `.finally()` handler to remove it when the request completes.

This prevents duplicate requests when multiple components mount simultaneously and each calls the same API endpoint (e.g., `getGitStatus`).

POST, DELETE, and other mutation requests are never deduplicated.

### 3.2 Timing Instrumentation

Every request records its timing via `_recordTiming()`:

```typescript
{ endpoint: string; method: string; ms: number; ok: boolean }
```

Timings are accumulated in `_apiTimings[]` and flushed to the console as a grouped table after **2 seconds of quiet** (no new requests). The flush includes:
- Sorted table (slowest first) with tier labels: `instant` (<50ms), `fast` (<200ms), `medium` (<1s), `slow` (>1s).
- Warning for any calls exceeding 500ms.

This enables performance monitoring during development without adding noise to every individual request.

### 3.3 Timeout Handling

Each request can specify a custom `timeoutMs` via the options parameter:
- Default timeout: **120 seconds** (2 minutes).
- Uses `AbortController` with `setTimeout` to enforce the deadline.
- On timeout, throws a descriptive error: `"Request timed out while calling {endpoint}."`.

Notable custom timeouts:
| Endpoint | Timeout | Rationale |
|----------|---------|-----------|
| `getLiveSessions` | 5s | Quick poll, should be fast |
| `quickCheckChanges` | 8s | Quick check, bounded |
| `getReconciliationResult` | 10s | May process large reports |
| `getDispatchFallbackStatus` | 15s | Polling interval tolerance |
| `testProvider` | 15s | CLI version check may be slow |
| `detectProviders` | 2s | Fast local detection |
| `getBranchStrategy` | 2s | Fast local detection |
| `getContextFiles` | 2s | Fast local detection |
| `getBudget` | 2s | Fast local detection |
| `getGateHistory` | 5s | May scan history files |
| `generateContextFile` | 60s | AI generation is slow |
| `dispatchFallback` | 930s (15.5m) | Long-running CLI execution |

### 3.4 Error Handling Patterns

The client uses a layered error handling approach:

1. **Network errors**: Caught in `_doFetch()`, wrapped with endpoint context: `"Network request failed for {endpoint}: {message}"`.
2. **Timeout errors**: Detected via `AbortError` name or `controller.signal.aborted`, wrapped with: `"Request timed out while calling {endpoint}."`.
3. **HTTP errors**: Non-2xx responses are caught, body text is read, and thrown as: `"API error ({status}): {body}"`.
4. **Backend disconnected**: `fetchApi()` checks `backendConnected` flag before every request and throws `"Backend not connected"` if false.

### 3.5 SSE Streaming Infrastructure

The dispatch manager creates `EventSource` connections directly (not through the api client) to:
```
${API_BASE_URL}/api/dispatch/stream/${jobId}
```

Events follow the `StreamEvent` interface with types: `start`, `output`, `status`, `complete`, `error`. The SSE connection is managed via module-scoped `eventSource` variable in `dispatchManager.ts`.

### 3.6 Endpoint Count by Domain

The `api` object exports **78 endpoint methods** organized into 16 domains:

| Domain | Count | Methods |
|--------|-------|---------|
| **Projects** | 4 | `listProjects`, `getProject`, `registerProject`, `getProjectHealth` |
| **Readiness & Bootstrap** | 3 | `scanReadiness`, `startBootstrap`, `estimateBootstrapCost` |
| **Timeline** | 1 | `getTimeline` |
| **Git** | 16 | `getGitStatus`, `getCommits`, `getStashes`, `pushToRemote`, `commitAll`, `stashPop`, `stashDrop`, `generateCommitMessage`, `generateCommitMessageAI`, `quickCommit`, `stageFiles`, `stageAll`, `unstageFiles`, `unstageAll`, `commitStaged`, `discardFile`, `deleteUntracked` |
| **Roadmap** | 3 | `getRoadmap`, `toggleRoadmapItem`, `batchToggleRoadmapItems` |
| **Quality Gates** | 2 | `getGateResults`, `runGates` |
| **Dispatch** | 12 | `dispatchStart`, `getDispatchStatus`, `cancelDispatch`, `readDispatchOutput`, `enrichPrompt`, `generateTaskPrompt`, `getDispatchSummary`, `dispatchFallback`, `dispatchFallbackStart`, `getDispatchFallbackStatus`, `cancelDispatchFallback`, `dispatchAdvice`, `getDispatchUsage` |
| **Streaming Dispatch** | 3 | `streamStart`, `getStreamStatus`, `cancelStream` |
| **Logs** | 1 | `getLogs` |
| **Live Sessions** | 1 | `getLiveSessions` |
| **Reconciliation** | 8 | `quickCheckChanges`, `startReconciliationAnalysis`, `startProgressVerification`, `startAIProgressVerification`, `getReconciliationJobStatus`, `getReconciliationResult`, `applyReconciliation`, `getCommitDiff`, `undoReconciliation` |
| **Providers** | 2 | `detectProviders`, `testProvider` |
| **Branch Strategy** | 1 | `getBranchStrategy` |
| **Context Files** | 2 | `getContextFiles`, `generateContextFile` |
| **Budget & Usage** | 1 | `getBudget` |
| **Gate History** | 1 | `getGateHistory` |
| **Settings Actions** | 3 | `resetGates`, `clearHistory`, `removeProject` |
| **Parallel Execution** | 8 | `parallelGitCheck`, `parallelPlan`, `parallelPlanStatus`, `parallelReplan`, `parallelExecute`, `parallelExecuteStatus`, `parallelCancel`, `parallelReleaseHmrLock` |

### 3.7 Connection Management

- `initBackend()`: Polls `/health` up to 5 times (300ms apart) until the backend reports `{ status: "ok" }`. Sets `backendConnected = true` on success.
- `stopBackend()`: Sets `backendConnected = false` (no-op for the actual process in dev mode).
- `isBackendConnected()`: Returns the current connection flag. Checked by managers before making API calls.

---

## 4. Data Caching Strategy

**File:** `app/src/hooks/useDataCache.ts`

An in-memory, key-prefix-based TTL cache used by components that fetch data outside of Zustand stores (e.g., `OverviewTab` and `GitTab`).

### TTL Tiers

| Key Prefix | TTL | Rationale |
|------------|-----|-----------|
| `sessions:` | 5 min (300s) | Past sessions are immutable once ended. |
| `timeline:` | 2 min (120s) | Timeline only changes when a new session starts or ends. |
| `advice:` | 5 min (300s) | AI-generated dispatch advice is expensive to compute. |
| `commits:` | 30 sec | Commits change only when new code is committed. |
| `git:` | 15 sec | Working tree can change frequently (editor saves, etc.). |
| *(default)* | 60 sec | Everything else. |

### API

| Function | Signature | Description |
|----------|-----------|-------------|
| `getCached<T>` | `(key: string) => T \| null` | Returns cached data if within TTL, or `null` if expired/missing. Deletes expired entries on read. |
| `setCache<T>` | `(key: string, data: T) => void` | Stores data with a current timestamp. |
| `invalidateCache` | `(keyPrefix?: string) => void` | Clears all entries matching the prefix, or all entries if no prefix is given. |

### Usage Pattern

```tsx
// In a component's data-fetching logic:
const cached = getCached<GitStatus>(`git:${projectPath}`);
if (cached) {
  setStatus(cached);
} else {
  const fresh = await api.getGitStatus(projectPath);
  setCache(`git:${projectPath}`, fresh);
  setStatus(fresh);
}

// After a mutation:
invalidateCache("git:");
```

### Relationship to Zustand Stores

The `useDataCache` layer is complementary to Zustand stores, not a replacement. Zustand managers hold canonical state for their domains. `useDataCache` is used by components that need to cache API responses that don't belong to any single manager (e.g., the Overview tab fetches roadmap, timeline, health, and git data in parallel and caches each independently).

---

## 5. Cross-Store Interactions

While stores do not directly mutate each other, several cross-store data flows are orchestrated in `App.tsx` and within individual managers.

### 5.1 Dispatch Completion Triggers Reconciliation Check

**Flow:** `dispatchManager` -> `App.tsx` useEffect -> `reconciliationManager.check()`

When `isDispatching` transitions from `true` to `false` and `dispatchFailed` is `false`, `App.tsx` fires a `useEffect` that:
1. Fetches a dispatch summary via `api.getDispatchSummary()`.
2. If the dispatch came from a milestone plan, batch-marks all milestone items as done.
3. If the dispatch was for a single roadmap item, auto-marks that item as done via `api.toggleRoadmapItem()`.
4. Calls `reconciliationManager.check()` to detect any additional completed items.

### 5.2 Parallel Manager Reads Settings Store

**Flow:** `parallelManager` -> `useSettingsStore.getState()`

The parallel manager reads from the settings store at execution time (not reactively):
- `maxParallelAgents` -- when calling `api.parallelExecute()` in `approvePlan()`.
- `lightModel` -- when calling `api.parallelPlan()`, `api.parallelReplan()`, and `api.generateCommitMessageAI()`.

This is a one-way read using `getState()`, not a subscription.

### 5.3 Dispatch Manager Reads Settings Store

**Flow:** `App.tsx` -> `useSettingsStore` selectors + `useDispatchManager` actions

`App.tsx` reads `preSessionHooks` and `preferredFallback` from settings and passes them to dispatch-related UI (pre-flight interstitial, fallback modal). The dispatch manager itself does not import the settings store; the orchestration happens in the component layer.

### 5.4 Reconciliation Settings Gate

**Flow:** `useSettingsStore.reconciliationEnabled` -> `App.tsx` -> `reconciliationManager.check()`

The `enabled` flag from the settings store is passed to `reconciliationManager.check()` as a parameter. If disabled, the check short-circuits and sets `footerState` to `"hidden"`.

### 5.5 Dispatch Guards Parallel Execution

**Flow:** `App.tsx` -> `useDispatchManager.getState().isDispatching` -> gate `parallelManager.startPlanning()`

Before starting parallel execution, `App.tsx` checks whether a dispatch is already in progress and shows a warning toast if so. This prevents concurrent dispatch and parallel execution.

### Interaction Diagram

```
                    App.tsx (orchestration layer)
                   /    |    \        \          \
                  /     |     \        \          \
   projectManager  dispatchManager  gitManager  reconciliationManager  parallelManager
                        |                              ^                    |
                        |  (dispatch completes)        |                    |
                        +---> check() ----------------+                    |
                                                                           |
                        settingsStore <-------- getState() ----------------+
                             ^
                             |
                        (all components read preferences)
```

---

## 6. TypeScript Interface Catalog

**File:** `app/src/types/index.ts`

All shared interfaces are defined in a single types module, organized by domain.

### Project Domain

| Interface | Key Fields | Used By |
|-----------|------------|---------|
| `Project` | `id`, `name`, `path`, `branch`, `uncommitted`, `lastSession`, `costWeek`, `totalSessions` | projectManager, OverviewTab |
| `HealthReport` | `items: HealthItem[]`, `score: number` | OverviewTab, api |
| `HealthItem` | `name`, `status: "pass" \| "warn" \| "fail"`, `detail` | OverviewTab |
| `ReadinessReport` | `score`, `is_ready`, `checks: ReadinessCheck[]`, `critical_issues`, `warnings` | projectManager |
| `ReadinessCheck` | `name`, `category`, `passed`, `severity`, `weight`, `message`, `remediation?`, `can_auto_generate?` | ScorecardView |

### Roadmap Domain

| Interface | Key Fields | Used By |
|-----------|------------|---------|
| `Roadmap` | `milestones: Milestone[]`, `totalItems`, `completedItems`, `progress` | RoadmapTab, OverviewTab |
| `Milestone` | `id`, `phase`, `title`, `sprint`, `items: MilestoneItem[]` | RoadmapTab, parallelManager |
| `MilestoneItem` | `text`, `done`, `prompt?`, `context?` | RoadmapTab, dispatchManager, parallelManager |
| `MilestonePlanContext` | `milestoneId`, `milestoneTitle`, `remainingItems`, `combinedPrompt` | dispatchManager |

### Timeline Domain

| Interface | Key Fields | Used By |
|-----------|------------|---------|
| `TimelineResponse` | `entries: TimelineEntry[]`, `total` | OverviewTab, GitTab |
| `TimelineEntry` | `sessionId`, `date`, `durationMinutes`, `summary`, `provider?`, `commits`, `filesChanged`, `gateStatuses`, `tokenUsage?`, `testResults?` | OverviewTab, App.tsx |
| `Session` | `id`, `date`, `time`, `duration`, `summary`, `commits`, `filesChanged`, `provider` | GitTab |
| `CommitInfo` | `sha`, `message`, `timestamp` | TimelineEntry |
| `TokenUsageSnapshot` | `inputTokens`, `outputTokens`, `model` | TimelineEntry |

### Git Domain

| Interface | Key Fields | Used By |
|-----------|------------|---------|
| `GitStatus` | `branch`, `unpushed`, `staged`, `uncommitted`, `untracked`, `stashed`, `submodule_issues` | gitManager, GitTab |
| `Commit` | `hash`, `msg`, `branch`, `date`, `time`, `merge?` | gitManager, GitTab |
| `UnpushedCommit` | `hash`, `msg`, `time` | GitTab |
| `UncommittedFile` | `file`, `status`, `lines` | GitTab |
| `UntrackedFile` | `file` | GitTab |
| `Stash` | `id`, `msg`, `time` | GitTab, gitManager |

### Quality Gates Domain

| Interface | Key Fields | Used By |
|-----------|------------|---------|
| `GateReport` | `gates: Gate[]`, `runId`, `timestamp`, `overallStatus`, `changedFiles` | GatesTab |
| `Gate` | `name`, `status`, `message`, `findings: GateFinding[]`, `durationSeconds`, `hardStop`, `costEstimate` | GatesTab |
| `GateFinding` | `severity`, `description`, `file?`, `line?` | GatesTab |
| `GateHistoryPoint` | `timestamp`, `status`, `score` | SettingsTab |

### Dispatch Domain

| Interface | Key Fields | Used By |
|-----------|------------|---------|
| `DispatchResult` | `success`, `sessionId?`, `error?`, `output?`, `provider?`, `token_limit_reached?` | dispatchManager |
| `DispatchStartResult` | `job_id`, `status`, `phase`, `message` | dispatchManager |
| `DispatchJobStatus` | `job_id`, `status`, `phase`, `done`, `result?`, `error_detail?`, `output_tail?`, `log_file?` | dispatchManager |
| `DispatchAdvice` | `estimated_tokens`, `estimated_cost?`, `should_suggest_fallback`, `suggested_provider?`, `reason` | OverviewTab |
| `DispatchUsageSummary` | `providers`, `total_tokens`, `total_cost_usd`, `total_events` | OverviewTab |
| `QueuedDispatch` | `id`, `prompt`, `mode`, `source`, `itemRef?`, `queuedAt` | dispatchManager |
| `DispatchContext` (exported from manager) | `prompt`, `mode`, `source`, `itemRef?` | dispatchManager, App.tsx |

### Streaming Domain

| Interface | Key Fields | Used By |
|-----------|------------|---------|
| `StreamEvent` | `type: StreamEventType`, `data`, `sequence`, `timestamp`, `job_id` | dispatchManager |
| `StreamStartResult` | `job_id`, `stream_url`, `status`, `message` | dispatchManager |
| `StreamJobStatus` | `job_id`, `is_running`, `is_cancelled`, `has_result`, `result` | dispatchManager |
| `StreamCancelResult` | `success`, `message` | dispatchManager |

### Live Session Domain

| Interface | Key Fields | Used By |
|-----------|------------|---------|
| `LiveSession` | `active`, `sessionId?`, `provider`, `pid?`, `tokensUsed`, `filesModified` | LiveFeed |
| `Exchange` | `time`, `type: "user" \| "assistant"`, `summary`, `files?` | LiveFeed |
| `LiveSessionResponse` | `active`, `session?`, `sessions?`, `exchanges` | LiveFeed |

### Reconciliation Domain

| Interface | Key Fields | Used By |
|-----------|------------|---------|
| `QuickCheckResponse` | `has_changes`, `commits_count`, `files_modified`, `uncommitted_count` | reconciliationManager |
| `ReconciliationReport` | `report_id`, `suggestions: RoadmapSuggestion[]`, `files_changed`, `commits_added`, `ai_metadata?` | reconciliationManager |
| `RoadmapSuggestion` | `item_text`, `milestone_name`, `confidence`, `reasoning[]`, `matched_files[]`, `matched_commits[]` | ReconciliationModal |
| `ApplyReconciliationRequest` | `report_id`, `accepted_items[]`, `dismissed_items[]` | reconciliationManager |
| `ApplyReconciliationResponse` | `success`, `items_completed`, `items_dismissed` | reconciliationManager |
| `ReconciliationFooterState` | Union type: `"hidden" \| "changes_detected" \| "analyzing" \| "report_ready" \| "no_matches" \| "baseline_created"` | reconciliationManager |

### Parallel Execution Domain

| Interface | Key Fields | Used By |
|-----------|------------|---------|
| `ExecutionPlan` | `summary`, `phases: ExecutionPhase[]`, `success_criteria[]`, `estimated_total_agents`, `warnings[]` | parallelManager |
| `ExecutionPhase` | `phase_id`, `name`, `description`, `parallel`, `agents: AgentAssignment[]` | parallelManager |
| `AgentAssignment` | `agent_id`, `theme`, `task_indices[]`, `rationale` | ParallelExecutionOverlay |
| `AgentSlotStatus` | `task_index`, `task_text`, `status`, `output_tail`, `error`, `cost_estimate`, `group_id`, `phase_id` | parallelManager |
| `MergeResultStatus` | `branch`, `success`, `conflict_files[]`, `resolution_method`, `message` | parallelManager |
| `VerificationResult` | `overall_pass`, `criteria_results: CriterionResult[]`, `summary` | parallelManager |
| `CriterionResult` | `criterion`, `passed`, `evidence`, `notes` | ParallelExecutionOverlay |
| `ParallelBatchStatus` | `batch_id`, `phase`, `current_phase_id`, `agents[]`, `merge_results[]`, `verification`, `total_cost`, `error` | parallelManager |
| `ParallelPhase` | Union type: 12 phases from `"idle"` to `"cancelled"` | parallelManager |

### Settings Domain

| Interface | Key Fields | Used By |
|-----------|------------|---------|
| `ProviderInfo` | `name`, `version`, `status`, `installed` | SettingsTab |
| `BranchStrategyInfo` | `detected`, `description`, `evidence` | SettingsTab |
| `ContextFileInfo` | `file`, `status`, `detail`, `icon` | SettingsTab |
| `BudgetInfo` | `monthly`, `spent`, `weeklySpent`, `perSession` | SettingsTab |
| `HookCommand` (exported from store) | `cmd`, `enabled` | settingsStore, SettingsTab |

### Utility Types

| Type | Definition | Used By |
|------|------------|---------|
| `Status` | `"pass" \| "warn" \| "fail"` | Throughout |
| `MilestonePlanPhase` | `"idle" \| "planning" \| "reviewing" \| "executing" \| "complete" \| "failed"` | dispatchManager |
| `StreamEventType` | `"start" \| "output" \| "status" \| "complete" \| "error"` | dispatchManager |
| `StreamCompletionStatus` | `"success" \| "failed" \| "cancelled" \| "token_limit"` | dispatchManager |
