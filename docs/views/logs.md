# Logs View

> Last updated: 2026-02-17

## Purpose

The Logs tab provides an audit trail and operational log viewer for Claudetini. It displays a chronological feed of log entries from all subsystems -- dispatches, quality gates, security scans, and general operations -- with severity-based filtering and actionable "Fix" buttons for gate-related failures.

**Source file:** `app/src/components/logs/LogsTab.tsx`
**Tab index:** 4 (the "Logs" entry in the `TABS` array in `App.tsx`)

## Component Interface

```typescript
interface LogsTabProps {
  projectPath?: string | null;
  isActive?: boolean;
  onFix?: (gateName: string, finding: string) => void;
  onShowConfirm?: (config: {
    title: string;
    message: string;
    confirmLabel: string;
    danger?: boolean;
    onConfirm: () => void;
  } | null) => void;
}
```

- `onFix` -- callback invoked when the user clicks a "Fix" button on an actionable log entry; receives the gate name and the finding message
- `onShowConfirm` -- callback for showing a confirmation dialog (used by the "Clear" action)

## Data Model

Each log entry conforms to the `LogEntry` interface:

```typescript
interface LogEntry {
  time: string;                              // Timestamp string (e.g., "14:32:05")
  level: "info" | "pass" | "warn" | "fail";  // Severity level
  src: string;                               // Source identifier (e.g., "dispatch", "gate:lint", "secrets")
  msg: string;                               // Human-readable message
}
```

## Log Levels

The component defines four severity levels plus an "all" filter:

| Level | Text Color | Background | Description |
|-------|-----------|------------|-------------|
| `info` | `text-mc-text-3` (dim) | none | Informational messages, rendered at 70% opacity |
| `pass` | `text-mc-green` | `bg-mc-green-muted` | Successful operations (gates passed, dispatches completed) |
| `warn` | `text-mc-amber` | `bg-mc-amber-muted` | Warnings (non-blocking issues, degraded performance) |
| `fail` | `text-mc-red` | `bg-mc-red-muted` | Failures (gate failures, dispatch errors, security findings) |

## Log Sources

The `src` field identifies which subsystem generated the log entry. Common sources include:

| Source Pattern | Origin |
|---------------|--------|
| `dispatch` | Claude Code dispatch operations |
| `gate:<name>` | Quality gate results (e.g., `gate:lint`, `gate:typecheck`, `gate:test`) |
| `secrets` | Security/secrets scanner findings |
| `reconciliation` | Multi-provider reconciliation results |
| `system` | Internal Claudetini operations |

Gate-sourced entries are recognized by the `gate:` prefix and may be actionable.

## UI Structure

### Filter Bar

A horizontal bar at the top with:

1. **Level filter buttons** -- five pill buttons (`all`, `info`, `pass`, `warn`, `fail`), styled as monospace uppercase text. The active filter gets a highlighted background (`bg-mc-surface-3`, `text-mc-text-0`); inactive filters are transparent with dim text.
2. **Entry count** -- monospace display of the filtered entry count
3. **Clear button** -- triggers a confirmation dialog (via `onShowConfirm`) before wiping all log entries from local state

Filtering is applied client-side: `filter === "all" ? logs : logs.filter((l) => l.level === filter)`.

### Log Container

A rounded container (`bg-mc-surface-1`, monospace `text-[11.5px]`) displaying filtered entries as rows. Each row contains:

| Column | Width | Content |
|--------|-------|---------|
| Time | 88px fixed | Timestamp in dim text, 60% opacity |
| Level | 36px fixed | Level badge -- bold, uppercase, 9.5px, colored by severity |
| Source | 100px fixed | Source identifier in dim text, 60% opacity |
| Message | flex-1 | Log message text; info-level entries rendered at 70% opacity |
| Action | shrink-0 | "Fix" button (only for actionable entries) |

Rows are separated by bottom borders. Background color varies by level (warn/fail entries get their muted background color applied to the entire row).

### Actionable Entries

A log entry is considered actionable when:

```typescript
const isActionable = (l: LogEntry) =>
  (l.level === "fail" || l.level === "warn") && l.src.startsWith("gate");
```

Actionable entries display a "Fix" button with a play icon. The button color matches the severity:
- `fail` -- red background (`bg-mc-red`)
- `warn` -- amber background (`bg-mc-amber`)

Clicking "Fix" extracts the gate name from the source field (strips `gate:` prefix, capitalizes first letter) and invokes `onFix(gateName, log.msg)`. This integrates with the dispatch system to automatically fix gate findings.

### Empty State

When no entries match the current filter: "No log entries found" centered in the container.

## API Integration

Logs are fetched from a single endpoint:

```
GET /api/logs/{projectId}?limit=100
```

Response shape:

```typescript
{ entries: LogEntry[]; total_count: number }
```

The default limit is 100 entries. The `total_count` field indicates how many entries exist server-side (for potential pagination).

## Data Loading Strategy

- Logs are fetched when the tab becomes active (`isActive === true`) or when it has been loaded at least once (`hasLoaded.current`)
- The `hasLoaded` ref resets when `projectPath` changes
- A loading spinner ("Loading logs...") is shown only on the first load; subsequent refreshes update silently
- On fetch failure, an error banner appears at the top of the tab with the error message, and the log list is cleared

## Clear Logs Behavior

The "Clear" button has two code paths:

1. **With `onShowConfirm`** -- Shows a confirmation dialog: "This will remove all log entries. This cannot be undone." with a danger-styled "Clear All" button. On confirm, clears the local `logs` state.
2. **Without `onShowConfirm`** -- Clears logs immediately without confirmation.

Note: clearing logs only affects the local component state (`setLogs([])`). It does not call a backend endpoint to delete persisted logs.

## Dispatch Audit Trail

The logs view serves as the primary audit trail for dispatch operations. When the dispatch system runs with safety overrides (e.g., bypassing a pre-flight check, forcing a dispatch despite warnings), those decisions are logged as `warn` or `info` entries with the `dispatch` source. This provides traceability for:

- Which pre-flight checks were bypassed
- When fallback providers were activated
- Whether safety gates were overridden
- Dispatch start/end times and outcomes

## Edge Cases

1. **No project selected** -- Shows "Select a project to view logs." placeholder
2. **Backend disconnected** -- `isBackendConnected()` check prevents API calls; logs array is emptied
3. **API failure** -- Error banner displayed; log list cleared; user can retry by switching tabs
4. **Large log sets** -- The default limit of 100 entries prevents memory issues; the server-side `total_count` enables future pagination
5. **Rapid filter switching** -- Filtering is local and synchronous, so there is no debounce needed
6. **Missing onFix callback** -- If `onFix` is not provided, clicking "Fix" falls through to a `console.log` as a development fallback
