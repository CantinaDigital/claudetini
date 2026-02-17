# Overlay Components

> Last updated: 2026-02-17

## Overview

Claudetini uses overlay components for workflows that require full user attention before or after a dispatch operation. These overlays sit above the main dashboard UI at high z-index levels and typically require explicit user action to dismiss.

| Component | File | Purpose | z-index |
|-----------|------|---------|---------|
| `PreFlightInterstitial` | `components/overlays/PreFlightInterstitial.tsx` | Pre-dispatch validation checks | `z-[100]` |
| `SessionReportOverlay` | `components/overlays/SessionReportOverlay.tsx` | Post-session detailed report | `z-[100]` |
| `MilestonePlanReview` | `components/overlays/MilestonePlanReview.tsx` | Milestone plan review and execution | `z-[9999]` |

---

## PreFlightInterstitial

**File**: `app/src/components/overlays/PreFlightInterstitial.tsx`

A pre-dispatch validation overlay that verifies project state before allowing a Claude Code dispatch to proceed. Displays a checklist of automated checks with pass/warn/fail status, optionally showing pre-session hooks that will run.

### Props

```typescript
interface PreFlightInterstitialProps {
  checks: PreFlightCheck[];       // Array of validation check results
  hooks?: PreSessionHook[];       // Optional pre-session hooks to display
  prompt?: string;                // The dispatch prompt (shown in context section)
  mode?: string;                  // Dispatch mode (shown as badge if non-standard)
  onClose: () => void;            // Cancel/close the interstitial
  onDispatch: () => void;         // Proceed with dispatch
}
```

### Exported Types

```typescript
interface PreFlightCheck {
  name: string;         // Check label (e.g., "Uncommitted changes")
  status: Status;       // "pass" | "warn" | "fail"
  detail: string;       // Descriptive detail text
}

interface PreSessionHook {
  cmd: string;          // Shell command to run
  enabled: boolean;     // Whether this hook is active
}

interface PreFlightInputs {
  uncommittedCount: number;
  branch?: string | null;
  dependenciesFresh?: boolean | null;
  previousSessionStatus?: "pass" | "warn" | "fail" | null;
  editorConflict?: boolean | null;
}
```

### Exported Helper: `generatePreFlightChecks()`

A pure function that generates the standard set of 5 pre-flight checks from project state inputs. Always returns all 5 checks -- unavailable data is shown as "warn" with explanatory detail rather than being omitted.

| # | Check Name | Pass Condition | Warn Condition |
|---|------------|----------------|----------------|
| 1 | Uncommitted changes | Always passes (informational) | N/A -- shows file count or "Clean" |
| 2 | Branch status | Branch name is available and non-empty | Branch unavailable |
| 3 | Dependencies fresh | `dependenciesFresh === true` | `false` or `null` |
| 4 | Previous session | `previousSessionStatus === "pass"` | Status is "warn" or `null` |
| 5 | Editor conflicts | `editorConflict === false` | `true` or `null` |

Note: Check #1 ("Uncommitted changes") always returns `"pass"` regardless of count -- it is purely informational.

### State

No local state. All state is derived from props.

### Visual Sections

1. **Header**: "Pre-Flight Checks" title with subtitle "Verifying project state before dispatch...".

2. **Dispatch Context** (conditional): Shown when `prompt` is provided. Displays the dispatch command (truncated to 120 characters) and a mode badge if the mode is non-standard (e.g., "BLITZ", "WITH REVIEW").

3. **Checks list**: Each check is rendered as a row with:
   - `StatusDot` component (green/amber/red)
   - Check name
   - Detail text in monospace (color-coded by status)
   - Background color: transparent (pass), amber-muted (warn), red-muted (fail)
   - Loading state: Shows "Running checks..." when `checks.length === 0`

4. **Pre-Session Hooks** (conditional): Shown when enabled hooks exist. Lists each hook command with an arrow prefix (`-> cmd`).

5. **Action buttons**:
   - "Cancel" button (always available)
   - "Dispatch" / "Dispatch Anyway" / "Blocked" / "Checking..." (context-dependent)

### Dispatch Button Logic

| Condition | Button Text | Enabled |
|-----------|------------|---------|
| `checks.length === 0` (loading) | "Checking..." | No (disabled, reduced opacity) |
| Any check has `status === "fail"` | "Blocked" | No (disabled, reduced opacity) |
| All checks pass | "Dispatch" | Yes |
| Some checks warn, none fail | "Dispatch Anyway" | Yes |

Key behavior: **Warnings do not block dispatch.** Only `"fail"` status prevents proceeding. The "Dispatch Anyway" label makes the user aware they are proceeding despite warnings.

### Interactions

- **Backdrop click**: Calls `onClose`.
- **Inner panel click**: Stops propagation.
- **Cancel**: Calls `onClose`.
- **Dispatch / Dispatch Anyway**: Calls `onDispatch`. The play icon (`Icons.play`) is shown before the text.

### Edge Cases

- **All data unavailable**: If no project state data is available, all 5 checks will show as "warn" with "unavailable" detail text. The user can still proceed with "Dispatch Anyway".
- **Empty checks array**: Treated as a loading state. The button shows "Checking..." and is disabled.
- **Long prompts**: Truncated to 120 characters with "..." suffix in the dispatch context section.

---

## SessionReportOverlay

**File**: `app/src/components/overlays/SessionReportOverlay.tsx`

A slide-in side panel displaying a comprehensive post-session report with summary, gate results, test results, file changes, roadmap matches, and action buttons.

### Props

```typescript
interface SessionReportOverlayProps {
  report: SessionReport;          // Full session report data
  onClose: () => void;            // Close the panel
  onApprove?: () => void;         // Approve the session and continue
  onRetry?: () => void;           // Retry with additional context
  onRevert?: () => void;          // Revert the session's changes
}
```

### SessionReport Type

```typescript
interface SessionReport {
  sessionId: string;
  duration: string;
  cost?: string | null;
  tokens?: { input: number; output: number } | null;
  provider?: string | null;
  branch?: string | null;
  summary: string;
  files: {
    path: string;
    status: "A" | "M" | "D";       // Added, Modified, Deleted
    lines: string;                   // e.g., "+12 -3"
  }[];
  tests?: {
    passed: number;
    failed: number;
    coverage?: number;
    newTests?: number;
  } | null;
  gates: Record<string, Status>;     // Gate name -> pass/warn/fail
  roadmapMatches?: string[];         // Matched roadmap items
}
```

### State

No local state. All content is derived from the `report` prop.

### Visual Sections

1. **Header**: Session ID (truncated to 8 characters for display), close button (X icon).
   - Detail line: `duration . cost . tokens . provider` joined by centered dots.
   - Cost, tokens, and provider show "unavailable" text when null.

2. **Summary**: Diff-aware rendering of `report.summary`:
   - If the summary contains diff content (detected by `looksLikeDiff()`), it is rendered via `DiffBlock`.
   - Otherwise, parsed as lightweight Markdown:
     - `### headings` rendered as uppercase, bold, small section headers
     - Numbered list items (`1. ...`) rendered with left padding
     - Bullet items (`- ` or `* `) rendered with left padding
     - Regular text rendered as `InlineMarkdown` (supports bold, code, links)
     - Empty lines rendered as `<br>`

3. **Gate Results**: Horizontal flex-wrapped list of gate badges. Each badge shows a `StatusDot` (5px) and the gate name (capitalized). If no gates were captured, shows a fallback message.

4. **Tests** (conditional): Shown when `report.tests` is provided. Wrapped in a `Section` component with "Tests" label. Displays:
   - Passed count (green)
   - Failed count (red if > 0, muted otherwise)
   - Coverage percentage (if available)
   - New tests count (accent color, if available)

5. **Changed Files**: Wrapped in a `Section` component with file count in the label. Each file row shows:
   - Status badge: **A** (green), **M** (amber), **D** (red) with matching background tint
   - File path in monospace
   - Line change summary (e.g., "+12 -3")
   - Rows separated by bottom borders
   - Empty state message when no files captured

6. **Roadmap Match** (conditional): Green-bordered box shown when `roadmapMatches.length > 0`. Displays "Roadmap Match Detected" header and lists each matched item with a checkmark prefix.

7. **Action buttons**: Fixed to bottom of the panel via `mt-auto`:
   - "Approve & Continue" (primary, with check icon)
   - "Retry with Context" (with retry icon)
   - "Revert" (danger-styled)

### Layout

Unlike other overlays that center a modal, `SessionReportOverlay` uses a **slide-in side panel** design:
- The backdrop (`fixed inset-0`) uses `flex justify-end` to position the panel on the right.
- The panel is 520px wide, full height, with `animate-slide-in` entrance animation.
- Content scrolls vertically with `overflow-y-auto`.

### Interactions

- **Backdrop click**: Calls `onClose`.
- **Panel click**: Stops propagation.
- **Close button (X)**: Calls `onClose`.
- **Approve & Continue**: Calls `onApprove`. Signals acceptance of the session's changes.
- **Retry with Context**: Calls `onRetry`. Intended to re-dispatch with additional context from the session.
- **Revert**: Calls `onRevert`. Danger-styled to indicate destructive action (reverting changes).

### Edge Cases

- **Long session IDs**: UUIDs are truncated to the first 8 characters in the header.
- **Missing cost/tokens/provider**: Displayed as "[field] unavailable" in the detail line.
- **No gate results**: Shows "No gate results were captured for this session." message.
- **No file changes**: Shows "File-level changes were not captured for this session." within the Changed Files section.
- **Diff content in summary**: Automatically detected and rendered with `DiffBlock` instead of Markdown parsing.
- **Optional action callbacks**: `onApprove`, `onRetry`, and `onRevert` are all optional props. Buttons still render but will be no-ops if the callback is undefined.

---

## MilestonePlanReview

**File**: `app/src/components/overlays/MilestonePlanReview.tsx`

A two-phase overlay for milestone execution: first showing live planning output from Claude Code, then transitioning to a review interface where the user can modify the plan approach, add notes, and select an execution mode.

### Props

```typescript
interface MilestonePlanReviewProps {
  milestoneTitle: string;                           // Name of the milestone being planned
  remainingItems: MilestoneItem[];                  // Tasks to be implemented
  planOutput: string;                               // Completed plan text (empty during planning)
  isPlanning: boolean;                              // Whether the planning dispatch is still running
  onExecute: (mode: string, userNotes?: string) => void;  // Start execution with chosen mode + notes
  onCancel: () => void;                             // Cancel planning or dismiss review
}
```

### State (from dispatchManager)

| Selector | Type | Purpose |
|----------|------|---------|
| `isDispatching` | `boolean` | Whether the planning dispatch is active |
| `isStreaming` | `boolean` | Whether SSE streaming is active |
| `streamOutputLines` | `string[]` | SSE output lines |
| `outputTail` | `string \| null` | Polling output tail |
| `statusText` | `string` | Current status message |
| `elapsedSeconds` | `number` | Timer |
| `progressPct` | `number` | Progress percentage |
| `cancelAction` | `() => Promise<void>` | Cancel function reference |
| `dispatchFailed` | `boolean` | Whether planning failed |
| `errorDetail` | `string \| null` | Error message |

### Local State

| State | Type | Default | Purpose |
|-------|------|---------|---------|
| `selectedMode` | `string` | `"standard"` | Chosen execution mode |
| `userNotes` | `string` | `""` | User's additional context/notes |
| `isCancelling` | `boolean` | `false` | Cancel button loading state |
| `autoScroll` | `boolean` | `true` | Auto-scroll for live output |

### Execution Modes

```typescript
const MODES = [
  { key: "standard", label: "Standard", desc: "Default execution mode" },
  { key: "blitz", label: "Blitz", desc: "Fast, minimal verification" },
  { key: "with-review", label: "With Review", desc: "Agent-based with review" },
];
```

### Two-Phase UI

The overlay operates in two distinct phases controlled by the `isPlanning` prop:

#### Phase 1: Planning

When `isPlanning === true`, the overlay shows a live terminal view of Claude Code generating the implementation plan.

**Visual sections during planning:**

1. **Header**: Spinner + "Planning Milestone..." with milestone title, task count, and elapsed time.

2. **Progress bar**: 3px-tall bar below the header. Blue when running, red if `dispatchFailed`.

3. **Tasks list**: Compact flex-wrapped display of all remaining items with empty checkbox icons. Always visible in both phases.

4. **Live output terminal**:
   - Header bar with green pulsing dot, "Claude Code Output" label, line count, and status text.
   - Output area: Renders `liveLines` (prefers `streamOutputLines` over `outputTail`). Minimum height of 200px, max 380px. Auto-scroll behavior (disables when user scrolls up, re-enables at bottom).
   - Blinking cursor when SSE streaming is active.

5. **Error state**: Red-bordered box with `errorDetail` shown below the terminal when `dispatchFailed`.

6. **Footer**: "Cancel" button (red-styled, with loading state) + status text ("Claude Code is analyzing the codebase..." / "Planning failed. Cancel and retry.").

#### Phase 2: Reviewing

When `isPlanning === false`, the planning dispatch has completed and the user can review the output.

**Visual sections during review:**

1. **Header**: Green checkmark + "Plan Ready -- Review & Execute" with milestone title and task count.

2. **Tasks list**: Same as planning phase.

3. **Plan output**: `<pre>` block showing the complete plan text in monospace. Max height 300px, scrollable. Falls back to "(No plan output received)" when empty.

4. **User notes**: Textarea for optional context. Placeholder text: "Add context, answer questions from the plan, or adjust the approach...". Resizable vertically.

5. **Execution mode selector**: Three radio-style buttons in a horizontal row. Selected mode has accent border and background. Each button shows mode label and description.

6. **Footer**: "Cancel" button + "Execute (N tasks)" primary button with play icon. Execute calls `onExecute(selectedMode, userNotes.trim() || undefined)`.

### Live Output Logic

The `liveLines` variable selects the best available output source:
```typescript
const liveLines = isStreaming && streamOutputLines.length > 0
  ? streamOutputLines        // SSE lines (preferred)
  : outputTail
    ? outputTail.split("\n") // Polling tail (fallback)
    : [];                    // Empty (initial state)
```

### Auto-Scroll Behavior

Uses a `ref` on the output container and an `onScroll` handler:
- Checks if the user is within 30px of the bottom.
- Sets `autoScroll` to `true` when at bottom, `false` when scrolled up.
- A `useEffect` scrolls to bottom on new `liveLines` when `autoScroll` is enabled.

### Cancel Behavior

Cancel during planning phase:
1. Sets `isCancelling: true` (disables button).
2. Calls `cancelAction()` from dispatchManager (which closes EventSource, calls backend cancel API, resets state).
3. On completion (via `finally`), sets `isCancelling: false` and calls `onCancel()` to dismiss the overlay.

### Interactions

- **Backdrop**: The overlay does NOT close on backdrop click (no onClick handler on the backdrop div).
- **Inner panel click**: Stops propagation.
- **Cancel (planning)**: Async cancel with loading state, then dismisses.
- **Cancel (reviewing)**: Simple `onCancel()` call.
- **Execute**: Calls `onExecute(mode, notes)`. The parent is responsible for calling `executeMilestone()` on the dispatch manager.

### Edge Cases

- **Planning failure**: When `dispatchFailed` is true during planning, the error detail is shown and the footer displays "Planning failed. Cancel and retry." The user must cancel and try again -- there is no automatic retry.
- **Empty plan output**: The review phase shows "(No plan output received)" in the plan output section. The user can still proceed with execution.
- **Long task lists**: Tasks are rendered in a flex-wrapped layout with text truncation (`max-w-[280px]`, `text-ellipsis`, `whitespace-nowrap`).
- **SSE to polling transition**: The `liveLines` selector seamlessly switches from SSE lines to polling tail without visual disruption.
- **No backdrop dismiss**: Unlike other overlays, this component intentionally does not allow backdrop click to close, preventing accidental dismissal during planning.

---

## Common Patterns Across Overlays

### Backdrop Behavior

All overlays use a fixed full-screen backdrop (`fixed inset-0 bg-black/60`). Most support backdrop-click-to-close via an `onClick` on the backdrop that calls `onClose`, with `e.stopPropagation()` on the inner panel to prevent the inner content clicks from triggering close. Exception: `MilestonePlanReview` does not support backdrop dismiss.

### Animation

- `PreFlightInterstitial`: `animate-fade-in-fast`
- `SessionReportOverlay`: `animate-slide-in` (slides in from right)
- `MilestonePlanReview`: `animate-[fadeIn_0.2s_ease]`

### Z-Index Layering

```
z-[100]   — PreFlightInterstitial, SessionReportOverlay
z-[240]   — FallbackModal
z-[9997]  — DispatchMinimized
z-[9998]  — DispatchOverlay
z-[9999]  — MilestonePlanReview, DispatchSummary
```

The dispatch-related overlays use higher z-indexes to ensure they appear above validation and report overlays.

### Shared UI Components

All overlays use shared primitives from `components/ui/`:
- `Button` -- Consistent button styling with `primary`, `small`, and `danger` variants
- `StatusDot` -- Color-coded status indicator
- `Icons` -- SVG icon library (play, check, x, retry)
- `InlineMarkdown` -- Inline Markdown renderer for bold, code, links
- `DiffBlock` -- Diff-aware code block renderer
- `Section` -- Collapsible labeled section container
