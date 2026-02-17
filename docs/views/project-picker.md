# Project Picker View

> Last updated: 2026-02-17

## Purpose

The Project Picker is the initial screen of Claudetini, rendered when the app launches (or whenever the user navigates back to the picker). It allows users to browse registered projects, inspect key metadata at a glance, register new project directories, and open a project to enter the main dashboard. It is the entry point of the application's screen state machine: `picker -> scorecard -> bootstrap -> dashboard`.

**Source files:**

| File | Role |
|------|------|
| `app/src/components/project/ProjectPickerView.tsx` | Main view component |
| `app/src/managers/projectManager.ts` | Zustand state machine for screen routing and project list |
| `app/src/AppRouter.tsx` | Screen router that mounts `ProjectPickerView` |

---

## Layout

The view is a full-screen two-panel layout:

```
+-----------------------------+------------------------------------------+
|  LEFT PANEL (440px)         |  RIGHT PANEL (flex-1)                    |
|                             |                                          |
|  "Select Project" header    |  Project Detail header                   |
|  Search bar + Refresh btn   |  Stats grid (2x2)                       |
|  Scrollable project cards   |  Readiness preview ring + health pills   |
|  Register path form         |  README summary                          |
|                             |  Recent Activity (from timeline API)     |
|                             |  "Open Project" button (pinned bottom)   |
+-----------------------------+------------------------------------------+
```

### Left Panel -- Project List

1. **Header** -- Title "Select Project" with subtitle "Pick a registered workspace or add a new path."
2. **Backend warning banner** -- Shown when `backendConnected` is `false`, warns the user the sidecar is not running.
3. **Search bar** -- Filters the project list in real time. Searches across `name`, `path`, `branch`, `lastSession`, and `readmeSummary`. The query is normalized (trimmed, lowercased) before matching.
4. **Refresh button** -- Calls `onRefresh()` to reload the project list from the backend.
5. **Project cards** -- One card per registered project (see section below).
6. **Register path form** -- Text input + "Add Path" button at the bottom of the panel.

### Right Panel -- Project Detail

Displayed when a project is selected (otherwise shows a centered placeholder). Contains:

1. **Project header** -- Project name (large, bold) and filesystem path.
2. **Stats grid** -- Four metric tiles in a 2x2 grid:
   - Branch (with git branch icon)
   - Weekly Usage (accented)
   - Last Session
   - Total Sessions
3. **Readiness preview** -- `ReadinessRing` component (56px) showing the health score, plus colored health-check pills (pass/warn/fail) from the `HealthReport`.
4. **README summary** -- The project's `readmeSummary` field, or "No README summary available." as fallback.
5. **Recent Activity** -- Up to 3 recent timeline entries fetched via `api.getTimeline(projectId, 3)`. Each row shows an index number, summary text, and date.
6. **Open Project button** -- Primary action, pinned to the bottom right. Triggers `onOpenProject`.

---

## Project Card

Each card in the left-panel list renders:

| Element | Source | Detail |
|---------|--------|--------|
| Folder icon | `Icons.folder` | Accented when card is selected |
| Project name | `project.name` | Bold, `text-sm` |
| Status tag | `project.uncommitted` | "Clean" (green) when 0, "N changes" (amber) otherwise |
| Path | `project.path` | Monospace, truncated with ellipsis |
| Branch | `project.branch` | With branch icon |
| Mini readiness bar | `healthMap[project.id]?.score` | 32px progress bar + numeric score |
| Last opened | `project.lastOpened` | e.g. "Opened 2h ago" or "Never opened" |

**Interactions:**
- **Click** -- Selects the project (highlights the card and loads its detail in the right panel).
- **Double-click** -- Opens the project directly (equivalent to selecting + clicking "Open Project").

Cards are sorted by `lastOpenedTimestamp` descending (most recently opened first), with a fallback alphabetical sort by name.

---

## Project Data Shape

```typescript
interface Project {
  id: string;               // Unique project identifier (hash)
  name: string;             // Project directory name
  path: string;             // Absolute filesystem path
  branch: string;           // Current git branch
  uncommitted: number;      // Count of uncommitted changes
  lastSession: string | null;
  lastOpened: string | null; // Human-readable relative time
  lastOpenedTimestamp: string | null;
  costWeek: string;         // Weekly API usage cost
  totalSessions: number;
  readmeSummary?: string | null;
}
```

---

## Project Registration Flow

1. User types a local filesystem path into the registration input (e.g., `/Users/dev/my-project`).
2. User clicks "Add Path" or presses Enter.
3. The form validates that the input is not empty. If empty, displays inline error: "Enter a local filesystem path."
4. `AppRouter.handleRegisterProject(path)` is called:
   a. Calls `api.registerProject(path)` -- a POST to `/api/project/register`.
   b. The backend validates the path, detects the Claude Code project hash from `~/.claude/projects/`, and creates the project record.
   c. On success, calls `loadProjects()` to refresh the full list.
   d. Auto-selects the newly registered project in the picker.
5. On failure, the error is stored in `projectManager.error` and displayed as an error banner in the left panel.

**Registration states:**
- `registering=false` -- Input is enabled, button reads "Add Path".
- `registering=true` -- Input is disabled, button reads "Adding...".

---

## Auto-Detection of Claude Code Project Hash

When a path is registered via `api.registerProject(path)`, the Python sidecar:

1. Resolves the absolute path of the given directory.
2. Looks up the Claude Code project hash in `~/.claude/projects/` by matching the directory path.
3. If a matching hash is found, the project is linked to Claude Code session data (JSONL logs, session memory, todos).
4. If no hash is found, the project is still registered but will have limited session data.

The project `id` field returned by the backend is the project hash or a generated identifier.

---

## Health Data Fetching

Health data is fetched lazily and cached to minimize backend calls:

1. **On mount** -- Cached health scores are loaded from `localStorage` key `claudetini.health-cache`.
2. **On selection** -- When a project card is selected, `api.getProjectHealth(projectId)` is called (once per project, tracked by `healthFetchedRef`).
3. **On response** -- The new score is merged into `healthMap` state and persisted to `localStorage`.
4. **Non-selected cards** -- Display cached scores from `localStorage`, which may be stale but avoid N+1 API calls.

---

## State Management (projectManager)

The `projectManager` Zustand store manages the app-level screen state machine and project list.

```typescript
type AppScreen = "picker" | "scorecard" | "bootstrap" | "dashboard";

interface ProjectManagerState {
  // Screen state machine
  currentScreen: AppScreen;
  currentProject: Project | null;
  projects: Project[];

  // Readiness state
  readinessScore: number | null;
  readinessReport: ReadinessReport | null;

  // Bootstrap state
  bootstrapSessionId: string | null;
  bootstrapInProgress: boolean;

  // Loading / error
  isLoading: boolean;
  error: string | null;

  // Actions
  setScreen: (screen: AppScreen) => void;
  loadProjects: () => Promise<void>;
  scanReadiness: (projectPath: string) => Promise<void>;
  startBootstrap: (projectPath: string) => Promise<void>;
  completeBootstrap: () => void;
}
```

**Screen transitions from Project Picker:**

```
picker ──onOpenProject──> dashboard
picker ──(scorecard route)──> scorecard ──> bootstrap ──> dashboard
```

In the current implementation, `handleOpenProject` in `AppRouter` sets `currentProject` and transitions directly to `"dashboard"`. The scorecard and bootstrap screens are accessible on-demand from the dashboard rather than as mandatory gates.

---

## Navigation Flow

```
 ┌─────────────────┐
 │  AppRouter       │
 │  (screen router) │
 └───────┬─────────┘
         │
         ├── picker ──────────> ProjectPickerView
         │                       │
         │                       ├── Select project (click)
         │                       │    -> updates currentProject
         │                       │
         │                       ├── Open project (double-click or "Open Project" button)
         │                       │    -> setScreen("dashboard")
         │                       │
         │                       └── Register path ("Add Path")
         │                            -> api.registerProject(path)
         │                            -> loadProjects()
         │                            -> auto-select new project
         │
         ├── scorecard ───────> ScorecardView
         ├── bootstrap ───────> BootstrapWizard
         └── dashboard ───────> App (main dashboard)
```

---

## Keyboard Navigation

The picker supports keyboard navigation when focus is not inside an input:

| Key | Action |
|-----|--------|
| `ArrowDown` | Select the next project in the filtered list |
| `ArrowUp` | Select the previous project in the filtered list |
| `Enter` | Open the currently selected project |

The event listener is registered on the `window` object and ignores events that originate from `<input>` or `<textarea>` elements.

---

## Edge Cases

### No projects registered
When `projects.length === 0` and no search query is active, the card list area displays: "No registered projects yet." as a dashed-border placeholder. The right panel shows: "Select a project to view details."

### No search results
When a search query is active but no projects match, displays: `No projects match "{query}"`.

### Backend not connected
- A warning banner appears: "Backend not connected. Start sidecar to manage projects."
- The search input and refresh button remain functional but refresh is disabled.
- The registration input and "Add Path" button are disabled.
- The "Open Project" button is disabled.
- Cached health data from `localStorage` may still render on project cards.

### Invalid paths
When `api.registerProject(path)` fails (e.g., path does not exist, not a git repo, permission denied), the error is captured and displayed as a red error banner in the left panel. The user can dismiss it by triggering another action.

### Empty path submission
If the user submits an empty or whitespace-only path, inline validation catches it immediately with: "Enter a local filesystem path." -- no API call is made.

### Health data unavailable
If the health API call fails, the cached value (if any) remains. If no cached value exists, the readiness bar shows 0% width and a dash ("--") instead of a numeric score. The health pills section shows "No health data available."

### Timeline data unavailable
If the timeline API call fails or returns empty, the "Recent Activity" section is simply omitted from the right panel (conditional rendering based on `recentSessions.length > 0`).
