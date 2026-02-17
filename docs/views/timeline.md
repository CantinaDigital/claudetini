# Timeline View

> Last updated: 2026-02-17

## Purpose

The Timeline tab provides historical session intelligence for a Claudetini project. It presents a chronological record of Claude Code sessions alongside the git commit history, allowing developers to correlate AI-assisted development activity with concrete repository changes. The view also surfaces real-time git status for quick working tree management.

**Source file:** `app/src/components/timeline/TimelineTab.tsx`
**Active tab status:** The `TimelineTab` component exists but is **not currently in the active TABS array** in `App.tsx`. The active tabs are `["Overview", "Roadmap", "Git", "Quality Gates", "Logs", "Settings"]`. The "Git" tab at index 2 uses the newer `GitTab` component (`app/src/components/git/GitTab.tsx`), which is an evolved version of this component. The `TimelineTab` remains in the codebase as the original implementation.

## Component Interface

```typescript
interface TimelineTabProps {
  projectPath?: string | null;
  onReport?: (sessionId: string) => void;
  onShowConfirm?: (config: {
    title: string;
    message: string;
    confirmLabel: string;
    danger?: boolean;
    onConfirm: () => void;
  } | null) => void;
}
```

- `onReport` -- callback invoked when the user clicks "View full report" on a selected session, opening the `SessionReportOverlay`
- `onShowConfirm` -- callback for showing a confirmation dialog (used by the stash drop action)

## Data Models

### TimelineEntry (from backend)

```typescript
interface TimelineEntry {
  sessionId: string;
  date: string;                              // ISO date string
  durationMinutes: number;
  summary: string;
  provider?: "claude" | "codex" | "gemini" | string;
  branch?: string | null;
  promptUsed?: string;                       // Original user prompt
  commits: CommitInfo[];
  filesChanged: number;
  todosCreated: number;
  todosCompleted: number;
  roadmapItemsCompleted: string[];
  costEstimate?: number;                     // Dollar amount
  gateStatuses: Record<string, string>;      // Gate name -> status
  tokenUsage?: TokenUsageSnapshot | null;
  testResults?: SessionTestResult | null;
}

interface TokenUsageSnapshot {
  inputTokens: number;
  outputTokens: number;
  model: string;
}

interface SessionTestResult {
  passed: boolean;
  total?: number | null;
  passedCount?: number | null;
  raw?: string | null;
}
```

### ExtendedSession (local mapping)

The component maps `TimelineEntry` objects into `ExtendedSession` objects for display:

```typescript
interface ExtendedSession extends Session {
  sessionId?: string;
  startTime?: Date;
  endTime?: Date;
  promptUsed?: string;
}

interface Session {
  id: number;
  date: string;          // Formatted: "Feb 17"
  time: string;          // Formatted: "2:30 PM"
  duration: string;      // Formatted: "1h 23m" or "45m"
  summary: string;
  commits: number;
  filesChanged: number;
  linesAdded: number;
  linesRemoved: number;
  branch: string;
  provider: string;
  cost?: string;         // Formatted: "$1.23"
  tokens?: number;       // Total token count
  tests?: { passed: number; failed: number; coverage: number };
  dispatchMode?: string;
}
```

### GitStatus

```typescript
interface GitStatus {
  branch: string;
  unpushed: UnpushedCommit[];
  staged: UncommittedFile[];
  uncommitted: UncommittedFile[];
  untracked: UntrackedFile[];
  stashed: Stash[];
  submodule_issues: SubmoduleIssue[];
}
```

## UI Structure

The view is organized into two main regions: a git status strip at the top and a session-commit grid below.

### Git Status Strip (3-column grid)

Three side-by-side `Section` panels showing real-time git state:

#### Unpushed Commits

- Lists commits that exist locally but have not been pushed to the remote
- Each entry shows: short hash (cyan, monospace), commit message, and timestamp
- **Push All** button calls `api.pushToRemote(projectPath)` and refreshes git status

#### Working Tree

- Combines `uncommitted` and `untracked` files into a single list
- Each file shows a status badge with color coding:

| Status | Badge | Color |
|--------|-------|-------|
| Modified | M | Amber |
| Added | A | Green |
| Deleted | D | Red |
| Untracked | U | Green |

- Line change counts shown where available
- **Commit All** button generates an automatic commit message (format: `{prefix}: {files}`) and calls `api.commitAll(projectPath, message)`. Prefix is "update" for single file, "chore" for multiple files.

#### Stash

- Lists stashed changes with message and timestamp
- Two action buttons:
  - **Pop** -- calls `api.stashPop(projectPath)` to restore stashed changes
  - **Drop** -- shows a confirmation dialog ("This will permanently delete the stashed changes. This cannot be undone.") before calling `api.stashDrop(projectPath)`

### Session-Commit Grid (2-column layout)

#### Sessions Panel (left)

A scrollable list of Claude Code sessions, ordered chronologically. Each session card contains:

**Header row:**
- Session number (`#1`, `#2`, etc.) -- highlighted in accent color when selected
- Date (monospace, dim)
- Branch tag -- color-coded using a deterministic hash function:
  - `main`/`master` branches always get orange (`#f97316`)
  - Other branches get a stable color from a palette of 7 colors based on branch name hash
  - `feature/` prefix is stripped from display
- Dispatch mode tag (shown only for non-standard modes: "Review", "Pipeline")

**Summary:** The session summary text, or "No summary available" as fallback.

**Stats row (monospace, dim):**
- Commit count
- Lines added (green) / removed (red)
- Cost estimate (accent color, e.g., "$1.23")
- Token count (e.g., "45.2k tok")
- Test results: shows failed count in red, or coverage percentage in green

**Report link:** When a session is selected and `onReport` is provided, a "View full report" link appears, triggering the session report overlay.

Clicking a session card selects it, which:
1. Highlights the session with an accent left border and muted accent background
2. Cross-highlights associated commits in the commits panel

#### Commits Panel (right)

A list of the 50 most recent git commits. Each commit row shows:
- Branch color dot (7px) -- same deterministic color algorithm as sessions
- Short hash (monospace, colored by branch)
- Commit message (truncated with ellipsis)
- Date (monospace, right-aligned)

**Cross-highlighting:** When a session is selected, commits associated with that session are highlighted with an accent muted background and a glowing branch dot. The mapping is built from `TimelineEntry.commits` by matching short SHAs.

Merge commits are rendered at 50% opacity with italic text.

## Multi-Provider Support

The timeline natively supports sessions from different AI providers:

- **Claude** (`provider: "claude"`) -- default
- **Codex** (`provider: "codex"`)
- **Gemini** (`provider: "gemini"`)
- Custom providers (any string value)

The provider field comes from `TimelineEntry.provider` and is stored on the mapped session object. This enables the timeline to show a unified history across all AI-assisted development, regardless of which provider was used for each session.

## Session Report Overlay Integration

When a session is selected, the "View full report" link invokes `onReport(sessionId)`. In the parent `App.tsx`, this opens the `SessionReportOverlay` component, which provides a detailed breakdown of:
- Full session summary and prompt used
- Commit details with diffs
- Gate statuses and test results
- Token usage breakdown
- Cost analysis

The overlay is a separate modal component; the `TimelineTab` only triggers it via the callback.

## API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/git/{projectId}/status` | GET | Fetch current git status (unpushed, working tree, stash) |
| `/api/git/{projectId}/commits?limit=50` | GET | Fetch recent commits |
| `/api/timeline/{projectId}?limit=50` | GET | Fetch session timeline entries |
| `/api/git/{projectId}/push` | POST | Push all unpushed commits |
| `/api/git/{projectId}/commit-all` | POST | Commit all working tree changes |
| `/api/git/{projectId}/stash-pop` | POST | Pop the latest stash |
| `/api/git/{projectId}/stash-drop` | POST | Drop the latest stash |

## Data Loading Strategy

1. On mount (or when `projectPath` changes), `fetchData()` is called via a `useEffect`
2. Git status is fetched first via `fetchGitStatus()`
3. Commits are fetched (up to 50) and mapped into the local `commits` state
4. Timeline entries are fetched and mapped into `ExtendedSession` objects:
   - Duration is formatted as `Xh Ym` or `Xm`
   - Branch is resolved by cross-referencing commit data with the branch lookup map
   - Cost is formatted as `$X.XX`
   - Token count is computed as `inputTokens + outputTokens`
5. The first session is auto-selected
6. Loading state is shown only during the initial fetch

Data loading timing is logged to the console: `[TimelineTab] loaded in Xms`.

## Branch Color Algorithm

Branches are assigned stable colors using a deterministic hash:

```typescript
const generateBranchColor = (branch: string): string => {
  const normalized = branch.trim().toLowerCase();
  if (!normalized || normalized === "unknown") return t.text3;  // dim gray
  if (normalized === "main" || normalized === "master") return "#f97316";  // orange
  const colors = [t.cyan, t.accent, t.green, t.amber, "#f97316", "#22c55e", "#60a5fa"];
  let hash = 0;
  for (let i = 0; i < normalized.length; i++) {
    hash = normalized.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
};
```

This ensures the same branch always gets the same color across sessions and commits, providing visual consistency.

## Git Actions

The timeline includes four git actions, all guarded by `projectPath` and `isBackendConnected()`:

| Action | Loading Key | Behavior |
|--------|-------------|----------|
| Push All | `"push"` | Pushes to remote; refreshes git status |
| Commit All | `"commit"` | Auto-generates message; commits; refreshes status and commits list |
| Stash Pop | `"stash-pop"` | Restores stash; refreshes git status |
| Stash Drop | `"stash-drop"` | Requires confirmation; drops stash; refreshes git status |

Action errors are displayed in a dismissible red banner at the top of the view. Only one action can be in-flight at a time (tracked by `actionLoading` state).

## Edge Cases

1. **No project selected** -- Shows "Select a project to view timeline data." placeholder
2. **Backend disconnected** -- All state arrays are cleared; loading completes immediately
3. **No sessions found** -- Sessions panel shows: "No sessions found. Start a Claude Code session in this project to see activity."
4. **No commits found** -- Commits panel shows: "No commits found in this repository."
5. **Failed API calls** -- Each API call is wrapped in its own try/catch, so a timeline fetch failure does not prevent commits from loading (and vice versa); warnings are logged to console
6. **Branch resolution fallback** -- If a session's commits cannot be matched to any known branch, it falls back to `entry.branch` from the timeline data, then to `"unknown"`
7. **Missing cost/token data** -- Cost and token stats are conditionally rendered; they simply do not appear if the data is not available
8. **Stash drop without confirm callback** -- If `onShowConfirm` is not provided, the drop executes immediately without confirmation
9. **Merge commits** -- Rendered at reduced opacity (50%) with italic text to visually de-emphasize them in the commit list
