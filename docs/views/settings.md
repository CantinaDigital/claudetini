# Settings View

> Last updated: 2026-02-17

## Purpose

The Settings tab provides user configuration for the Claudetini application on a per-project basis. It exposes provider management, task routing, branch strategy automation, token budgets, pre-flight checks, scheduling controls, session hooks, context file management, and destructive project actions. All user-facing toggles and preferences are persisted client-side in localStorage via the `settingsStore` (Zustand).

**Source file:** `app/src/components/settings/SettingsTab.tsx`
**Store file:** `app/src/stores/settingsStore.ts`
**Tab index:** 5 (the "Settings" entry in the `TABS` array in `App.tsx`)

## Component Interface

```typescript
interface SettingsTabProps {
  projectPath?: string | null;
  isActive?: boolean;
  backendConnected: boolean;
  onShowConfirm?: (config: {
    title: string;
    message: string;
    confirmLabel: string;
    danger?: boolean;
    onConfirm: () => void;
  } | null) => void;
}
```

The `onShowConfirm` callback is used by danger-zone actions to show a confirmation modal before executing destructive operations.

## UI Sections

The tab renders nine distinct sections in a vertical stack:

### 1. Available Providers

Displays detected AI providers (Claude Code, Codex CLI, Gemini CLI) with:
- Color-coded dot per provider
- Name, version string, and authentication status tag
- Status tag colors: green for "authenticated", red for "error", amber for "not configured"
- **Test/Setup button** per provider, which calls `api.testProvider(providerName)` and refreshes the provider list on success

Data is fetched from `api.detectProviders(projectPath)` on mount. Falls back to `FALLBACK_PROVIDERS` when the backend is unavailable:

```typescript
const FALLBACK_PROVIDERS: ProviderInfo[] = [
  { name: "Claude Code", version: "unknown", status: "not configured", color: "#8b7cf6", installed: false },
  { name: "Codex CLI",   version: "unknown", status: "not configured", color: "#34d399", installed: false },
  { name: "Gemini CLI",  version: "unknown", status: "not configured", color: "#60a5fa", installed: false },
];
```

### 2. Task Type to Provider Routing

A table mapping task categories to provider assignments. Each row has a task name, a dropdown select (`Claude` / `Codex` / `Gemini`), and optionally a lock icon.

**Default routing:**

| Task | Default Provider | Locked |
|------|-----------------|--------|
| Coding | Claude | No |
| Tests | Claude | No |
| Documentation | Gemini | No |
| Refactoring | Claude | No |
| CI/CD | Codex | No |
| Security Review | Claude | Yes |
| Quality Gates | Claude | Yes |

Locked tasks (defined in `LOCKED_TASKS`) cannot have their provider changed. The lock is enforced in the UI by disabling the `<Select>` component and showing a lock icon.

Persisted in `settingsStore.taskRouting` (a `Record<string, string>`).

### 3. Branch Strategy

Displays the detected branch strategy (fetched from `api.getBranchStrategy(projectPath)`) with three automation toggles:

| Toggle Key | Label | Description | Default |
|------------|-------|-------------|---------|
| `autoCreateBranches` | Auto-create feature branches | Creates `feature/cp-<slug>` before dispatch | `false` |
| `autoPR` | Auto-PR on completion | `gh pr create` when item completed | `false` |
| `autoMerge` | Auto-merge after gates pass | Merge PR when all gates pass | `false` |

The detected strategy is shown as a cyan tag (e.g., "Detected: trunk-based") with supporting evidence text.

Persisted in `settingsStore.branchStrategyToggles`.

### 4. Token Budget

A 4-column stat grid displaying:
- **Monthly** -- soft budget limit (`$X.XX`)
- **Month Spent** -- amount spent this month with percentage
- **Week Spent** -- rolling weekly cost
- **Per-Session** -- hard stop per session

Below the grid is a progress bar showing the budget consumption percentage, with a warning marker at 80%.

Data is fetched from `api.getBudget(projectPath)`. Falls back to all zeros.

### 5. Light Model

A dropdown to select the model used for lightweight tasks (commit message generation, summaries). Options:
- `claude-haiku-4-5-20251001` -- Claude Haiku 4.5 (Recommended, default)
- `claude-sonnet-4-5-20250929` -- Claude Sonnet 4.5
- `claude-opus-4-6` -- Claude Opus 4.6

Persisted in `settingsStore.lightModel`.

### 6. Pre-Flight Checks

Toggle list of checks that run before dispatching Claude Code:

| Check | Description | Default | Locked |
|-------|-------------|---------|--------|
| Uncommitted changes | Warn if working tree dirty | `true` | No |
| Branch behind remote | Check origin freshness | `true` | No |
| Stale dependencies | Check lockfile freshness | `false` | No |
| Previous session incomplete | Warn on non-zero exit | `true` | No |
| Editor conflict detection | Files modified < 30s ago | `false` | No |
| Disk space (Blitz) | Block if < 2GB per worktree | `true` | Yes |

Locked checks show a "Required" tag and their toggle cannot be changed. The "Disk space (Blitz)" check is always enabled as a safety measure for parallel worktree operations.

Persisted in `settingsStore.preflightChecks` (a `Record<string, boolean>`).

### 7. Smart Scheduling

Toggle list for dispatch scheduling behavior:

| Toggle | Description | Default |
|--------|-------------|---------|
| Auto-dispatch queue on session end | Start next queued task when session finishes | `false` |
| Do-Not-Disturb mode | Pause all dispatches and queue | `false` |
| Active editor detection | Detect VS Code / Cursor writing to project files | `false` |
| Auto-resume queue | Dispatch queued items when DND lifts | `true` |
| Conflict prevention | Block dispatch if files modified < 30s ago | `false` |

The auto-dispatch toggle is stored separately as `settingsStore.autoDispatchEnabled`. The remaining four are stored in `settingsStore.schedulingToggles` (a `Record<string, boolean>`).

### 8. Session Hooks

Four hook groups, each supporting an arbitrary list of shell commands:

| Group | Store Key | Description |
|-------|-----------|-------------|
| Pre-Session | `preSessionHooks` | Run before dispatching Claude Code |
| Post-Session | `postSessionHooks` | Run after session completes |
| Pre-Merge (Blitz) | `preMergeHooks` | Run before merging blitz branches |
| Post-Merge (Blitz) | `postMergeHooks` | Run after blitz merge |

Each hook is a `HookCommand` object:

```typescript
interface HookCommand {
  cmd: string;      // Shell command string
  enabled: boolean;  // Toggle on/off without removing
}
```

**User interactions:**
- **Add Hook** -- opens an inline text input; Enter confirms, Escape cancels
- **Toggle** -- enables/disables the hook without removing it
- **Remove** -- deletes the hook from the list (x button)

All hook arrays are persisted in `settingsStore`. The `_parseHookArray()` function sanitizes stored data on load, filtering out malformed entries and trimming whitespace.

### 9. Context File Management

Lists context files detected in the project (e.g., `CLAUDE.md`, `.cursorrules`, `.clinerules`) with:
- File icon, filename, and status dot (pass/warn/missing)
- Detail text describing the file's state
- **Generate / Regenerate** button that calls `api.generateContextFile(projectPath, file)`

When no context files are detected, shows "No context files detected" (or a backend connection message when offline).

### 10. Danger Zone

A red-bordered section with three destructive actions, each requiring confirmation via `onShowConfirm`:

| Action | API Call | What It Does |
|--------|----------|--------------|
| **Reset Gates** | `api.resetGates(projectPath)` | Clears all quality gate results and trends |
| **Clear History** | `api.clearHistory(projectPath)` | Removes all session, commit, and log history |
| **Remove Project** | `api.removeProject(projectPath)` | Permanently deletes all project data from Claudetini (source code is not affected) |

All three show a confirmation dialog with danger styling before executing.

## Settings Store (`settingsStore`)

**Location:** `app/src/stores/settingsStore.ts`
**Persistence key:** `claudetini.fallback.settings.v1` (localStorage)
**Library:** Zustand `create<SettingsStore>`

### Stored Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `codexPath` | `string` | `"codex"` | Path to Codex CLI binary |
| `geminiPath` | `string` | `"gemini"` | Path to Gemini CLI binary |
| `preferredFallback` | `"codex" \| "gemini"` | `"codex"` | Which provider to fall back to |
| `usageMode` | `"subscription" \| "api"` | `"subscription"` | Billing mode |
| `claudeRemainingPct` | `number` (0-100) | `100` | Remaining Claude usage percentage |
| `fallbackThresholdPct` | `number` (0-100) | `10` | Trigger fallback below this threshold |
| `preSessionHooks` | `HookCommand[]` | `[]` | Pre-session shell commands |
| `reconciliationEnabled` | `boolean` | `true` | Enable conflict reconciliation |
| `reconciliationConfidenceThreshold` | `number` (30-90) | `50` | Minimum confidence to auto-accept |
| `autoDispatchEnabled` | `boolean` | `false` | Auto-dispatch on session end |
| `lightModel` | `string` | `"claude-haiku-4-5-20251001"` | Model for lightweight tasks |
| `taskRouting` | `Record<string, string>` | (see table above) | Task-to-provider mapping |
| `preflightChecks` | `Record<string, boolean>` | (see table above) | Pre-flight check toggles |
| `schedulingToggles` | `Record<string, boolean>` | (see table above) | Scheduling behavior toggles |
| `branchStrategyToggles` | `{ autoCreateBranches, autoPR, autoMerge }` | all `false` | Branch automation toggles |
| `postSessionHooks` | `HookCommand[]` | `[]` | Post-session shell commands |
| `preMergeHooks` | `HookCommand[]` | `[]` | Pre-merge shell commands |
| `postMergeHooks` | `HookCommand[]` | `[]` | Post-merge shell commands |
| `prePushHookEnabled` | `boolean` | `false` | Pre-push hook toggle |
| `maxParallelAgents` | `number` (1-8) | `3` | Max concurrent parallel agents |

### Actions

| Action | Signature | Description |
|--------|-----------|-------------|
| `setLightModel` | `(model: string) => void` | Update light model selection |
| `setPreferredFallback` | `(provider: FallbackProvider) => void` | Set fallback provider |
| `addPreSessionHook` | `(cmd: string) => void` | Append a new pre-session hook |
| `updatePreSessionHook` | `(index: number, patch: Partial<HookCommand>) => void` | Update hook at index |
| `removePreSessionHook` | `(index: number) => void` | Remove hook at index |
| `setAutoDispatch` | `(enabled: boolean) => void` | Toggle auto-dispatch |
| `setTaskRouting` | `(task: string, provider: string) => void` | Set provider for a task type |
| `setPreflightCheck` | `(name: string, enabled: boolean) => void` | Toggle a preflight check |
| `setSchedulingToggle` | `(name: string, enabled: boolean) => void` | Toggle a scheduling option |
| `setBranchStrategyToggle` | `(key, value) => void` | Toggle a branch strategy option |
| `addHookToGroup` | `(group, cmd) => void` | Add hook to post-session/merge group |
| `toggleHookInGroup` | `(group, index) => void` | Toggle hook enabled state |
| `removeHookFromGroup` | `(group, index) => void` | Remove hook from group |
| `setPrePushHookEnabled` | `(enabled: boolean) => void` | Toggle pre-push hook |
| `setMaxParallelAgents` | `(count: number) => void` | Set max parallel agents (clamped 1-8) |

### Persistence Mechanism

1. On store creation, `loadSettings()` reads from `localStorage` under key `claudetini.fallback.settings.v1`
2. The raw JSON is parsed and each field is validated/sanitized individually:
   - Strings are trimmed and checked for non-empty
   - Numbers are clamped to valid ranges via `_clampPct()` and `_clampRange()`
   - Hook arrays are sanitized via `_parseHookArray()` (filters malformed entries)
   - Objects are spread over defaults so new fields are always present
3. On every mutation, `persistSettings(toStorable(state))` serializes the storable fields (excluding action functions) back to `localStorage`
4. If `localStorage` is unavailable (e.g., SSR context), persistence silently no-ops

## API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/settings/{projectId}/providers` | GET | Detect available AI providers |
| `/api/settings/{projectId}/branch-strategy` | GET | Detect branch strategy |
| `/api/settings/{projectId}/budget` | GET | Fetch token budget info |
| `/api/settings/{projectId}/context-files` | GET | List context files |
| `/api/settings/{projectId}/test-provider` | POST | Test provider connectivity |
| `/api/settings/{projectId}/generate-context` | POST | Generate/regenerate a context file |
| `/api/settings/{projectId}/reset-gates` | POST | Clear gate results |
| `/api/settings/{projectId}/clear-history` | POST | Clear session/log history |
| `/api/settings/{projectId}/remove-project` | DELETE | Remove project data |

All endpoints use `Promise.allSettled` on initial load so that one failing endpoint does not block the others.

## Data Loading Strategy

- Settings are fetched only when the tab becomes active (`isActive === true`) OR when the tab has been loaded at least once (`hasLoaded.current`)
- A `hasLoaded` ref prevents redundant loading spinners on repeat visits
- The ref is reset when `projectPath` changes, ensuring a fresh load for a new project
- API calls within `fetchSettings` use `.catch()` with fallback values to fast-fail instead of blocking on backend timeouts

## Edge Cases

1. **No project selected** -- API calls are skipped; the component renders with fallback/default data
2. **Backend disconnected** -- `isBackendConnected()` guard prevents API calls; context files section shows "Connect to backend to detect context files"
3. **Locked tasks** -- Security Review and Quality Gates are permanently routed to Claude; the dropdown is disabled and a lock icon is shown
4. **Locked preflight checks** -- Disk space (Blitz) cannot be disabled; the toggle is locked and a "Required" tag is shown
5. **Empty hook commands** -- Adding a hook with blank/whitespace-only input silently no-ops (the trim check catches it)
6. **localStorage unavailable** -- All defaults are used; persistence silently fails
7. **Corrupted localStorage** -- The `loadSettings()` catch block returns `DEFAULT_SETTINGS`, effectively resetting all preferences
8. **New fields added to store** -- The spread-over-defaults pattern (`{ ...DEFAULT_SETTINGS, ...parsed }`) ensures new fields get their defaults even for users with older stored data
9. **Danger zone without confirm callback** -- If `onShowConfirm` is not provided, the danger buttons no-op (early return guard)
