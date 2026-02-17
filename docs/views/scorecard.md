# Scorecard View

> Project readiness assessment that determines whether a project can proceed directly to the dashboard or needs bootstrapping first.

Last updated: 2026-02-17

---

## 1. Purpose

The Scorecard View evaluates a project's readiness for Claude Code development. It runs 12 automated checks across categories like version control, documentation, planning, security, and testing, then produces a weighted score from 0 to 100. Based on this score the user is routed either to the main dashboard (high readiness) or to the Bootstrap Wizard (low readiness / critical issues).

---

## 2. When It Appears

The Scorecard appears in the **screen state machine** managed by `projectManager` after a project is selected from the Project Picker. The flow is:

```
picker --> scorecard --> dashboard   (score >= 80, no failures)
picker --> scorecard --> bootstrap   (failed checks selected for bootstrap)
picker --> scorecard --> dashboard   (user clicks "Back to Dashboard" to skip)
```

The screen state is tracked as `AppScreen` which has four values: `"picker" | "scorecard" | "bootstrap" | "dashboard"`.

**Source:** `app/src/managers/projectManager.ts` (line 6)

---

## 3. ReadinessRing Component

The `ReadinessRing` is a circular SVG progress indicator that renders the readiness score at the center of the Scorecard's "Score Card" panel.

**File:** `app/src/components/scorecard/ReadinessRing.tsx`

### Props

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `score` | `number` | -- | Score value from 0 to 100 |
| `size` | `number` | `120` | Pixel diameter of the ring |

### Color Thresholds

The ring color changes based on the score:

| Score Range | Color | Token |
|-------------|-------|-------|
| >= 85 | Green | `t.green` (`#34d399`) |
| >= 60 | Amber | `t.amber` (`#fbbf24`) |
| < 60 | Red | `t.red` (`#f87171`) |

### Rendering

- Two SVG `<circle>` elements: a background track (surface-3 color) and a foreground arc.
- The foreground arc length is controlled by `strokeDashoffset = circumference * (1 - score / 100)`.
- A subtle glow effect is applied via `drop-shadow(0 0 8px ${color}40)`.
- The score number and "Readiness Score" label are absolutely positioned in the center.
- Stroke width adapts: 4px for small rings (size <= 60), 6px otherwise.
- The entire ring rotates -90 degrees so the arc starts from the top (12 o'clock).
- The arc animates into place with a 600ms CSS transition (`transition-all duration-[600ms]`).

The `scoreColor` function is exported for reuse elsewhere.

---

## 4. The 12 Readiness Checks

Each check is defined in `src/core/readiness.py` and produces a `ReadinessCheck` dataclass. Checks are executed sequentially by `ReadinessScanner.scan()`.

| # | Check Name | Category | Severity | Weight | What It Checks |
|---|-----------|----------|----------|--------|---------------|
| 1 | Git Repository | `version_control` | CRITICAL | 0.15 | `git init` has been run |
| 2 | README | `documentation` | IMPORTANT | 0.10 | README.md/rst/txt exists |
| 3 | ROADMAP.md | `planning` | CRITICAL | 0.20 | `.claude/planning/ROADMAP.md` exists |
| 4 | CLAUDE.md | `documentation` | CRITICAL | 0.20 | Root `CLAUDE.md` exists |
| 5 | .gitignore | `version_control` | IMPORTANT | 0.08 | `.gitignore` exists and is non-empty |
| 6 | Dependencies | `project_structure` | IMPORTANT | 0.10 | `package.json`, `pyproject.toml`, etc. |
| 7 | License | `legal` | NICE_TO_HAVE | 0.03 | `LICENSE` / `COPYING` file exists |
| 8 | Architecture Docs | `documentation` | NICE_TO_HAVE | 0.05 | `docs/ARCHITECTURE.md` or similar |
| 9 | Test Infrastructure | `testing` | IMPORTANT | 0.07 | `tests/` dir or test files found |
| 10 | CI/CD | `automation` | NICE_TO_HAVE | 0.02 | `.github/workflows`, `.gitlab-ci.yml`, etc. |
| 11 | Secret Protection | `security` | CRITICAL | 0.10 | `.env` files are gitignored |
| 12 | Git Status | `version_control` | NICE_TO_HAVE | 0.00 | Working directory is clean (informational) |

**Source:** `src/core/readiness.py` (lines 89-411)

### Severity Levels

Severity maps to tiers in the UI:

| Severity | Tier Label | Visual Treatment |
|----------|------------|-----------------|
| `critical` | Essential | Red border, failures highlighted prominently |
| `important` | Recommended | Amber border |
| `nice_to_have` | Optional | Default border (border-1) |

### ReadinessCheck Fields

```typescript
interface ReadinessCheck {
  name: string;           // Human-readable check name
  category: string;       // Category key (e.g., "version_control")
  passed: boolean;        // Pass/fail result
  severity: string;       // "critical" | "important" | "nice_to_have"
  weight: number;         // Contribution to overall score (0-1)
  message: string;        // Human-readable result message
  remediation?: string;   // How to fix if failed
  why?: string;           // Why this check matters
  can_auto_generate?: boolean;  // Whether bootstrap can create this
  details?: Record<string, unknown>;
}
```

---

## 5. Score Calculation

### Backend Calculation (Python)

The backend computes a weighted score:

```python
total_weight = sum(check.weight for check in checks)           # Sum of all weights
earned_weight = sum(check.weight for check in checks if check.passed)
score = (earned_weight / total_weight) * 100
```

All 12 check weights sum to 1.10. A project that passes all checks scores 100. A project that fails only the two CRITICAL items `ROADMAP.md` (0.20) and `CLAUDE.md` (0.20) would score approximately `(0.70 / 1.10) * 100 = 63.6`.

### Frontend Progressive Score

During the staggered reveal animation, the frontend computes a **progressive score** that only penalizes checks that have been visually revealed:

```typescript
const computedScore = Math.max(0, Math.round(
  100 - revealedFail.reduce((s, c) =>
    s + (c.severity === "nice_to_have" ? 5 : 15), 0)
));
```

This simplified frontend formula deducts:
- **15 points** per revealed failure with severity `critical` or `important`
- **5 points** per revealed failure with severity `nice_to_have`

The progressive score starts at 100 and decreases as failures are revealed.

### Dismiss Support

Users can dismiss individual failed checks. Dismissed checks are excluded from both the active check list and the score computation. A "restore all" action brings them back.

---

## 6. Progressive Reveal Animation

Checks are not displayed all at once. The Scorecard uses a staggered reveal:

1. On scan completion, checks appear one at a time every **120ms** (`REVEAL_STAGGER_MS`).
2. Unrevealed checks show a "grading..." skeleton placeholder.
3. Revealed checks fade in with a 0.3s animation (`fadeIn 0.3s ease forwards`).
4. Once all checks are revealed (`allRevealed`), the final score appears after a 300ms pause.
5. The action bar (buttons) appears only after `showFinalScore` is true.

This creates the perception of a real-time grading process.

---

## 7. Auto-Generation Capability

Each `ReadinessCheck` has a `can_auto_generate` field. When a check fails and has `can_auto_generate: true`, it means the Bootstrap Wizard can create the missing artifact. In the current implementation, the Git Repository check explicitly sets `can_auto_generate=True`.

Failed checks are pre-selected for bootstrap via checkboxes. Users can toggle individual checks on/off before launching the Bootstrap Wizard.

### Selective Bootstrap

The Scorecard maintains a `bootstrapSel` set of check names selected for remediation:

- On scan completion, all failed check names are automatically added to `bootstrapSel`.
- Users click checkboxes to toggle individual failed items.
- The "Bootstrap N Items" button dynamically shows the count of selected items.
- Unchecked failed items appear at 50% opacity.

---

## 8. Transition Logic

The action bar at the bottom of the Scorecard adapts based on the final state:

### High Score, No Failures (score >= 80, failed.length === 0)

- **Primary action:** "Continue to Dashboard" button (calls `onSkip`)
- A green success message appears: "Project is ready for Claude Code!"

### Failures Present

- **Primary action:** "Bootstrap N Items" button (calls `onBootstrap`)
- **Secondary actions:** "Re-scan" and "Back to Dashboard" (skip)
- The "Needs Attention" callout shows the count of failed items and how many are selected for bootstrap.

### Backend Readiness Threshold

The Python `ReadinessReport.is_ready` property uses a different threshold:

```python
@property
def is_ready(self) -> bool:
    return self.score >= 70.0 and len(self.critical_issues) == 0
```

A project is considered "ready" on the backend when score >= 70 and there are zero critical issues.

---

## 9. State Management

### projectManager Store

The Scorecard integrates with the `useProjectManager` Zustand store defined in `app/src/managers/projectManager.ts`.

```typescript
interface ProjectManagerState {
  currentScreen: "picker" | "scorecard" | "bootstrap" | "dashboard";
  currentProject: Project | null;
  readinessScore: number | null;
  readinessReport: ReadinessReport | null;
  bootstrapSessionId: string | null;
  bootstrapInProgress: boolean;
  isLoading: boolean;
  error: string | null;

  setScreen: (screen: AppScreen) => void;
  scanReadiness: (projectPath: string) => Promise<void>;
  startBootstrap: (projectPath: string) => Promise<void>;
  completeBootstrap: () => void;
}
```

### Data Flow

1. `ScorecardView` receives `projectPath` as a prop and calls `api.scanReadiness(projectPath)` on mount.
2. The scan response is stored locally as `report` state and also written to the global store:
   ```typescript
   useProjectManager.setState({
     readinessScore: data.score,
     readinessReport: data,
   });
   ```
3. This allows other views (e.g., the Overview tab in the dashboard) to access the readiness data.

### API Endpoint

```
POST /api/readiness/scan
Body: { "project_path": "/path/to/project" }
Response: ReadinessReport
```

**Source:** `app/src/api/backend.ts` (line 267)

---

## 10. UI Layout

### Structure

```
+------------------------------------------+
|  <- Back to Dashboard                     |
|  Project Readiness                        |
|  "Checking if your project is ready..."   |
+------------------------------------------+
|           [ReadinessRing: 85]             |
|         10 of 12 checks passed            |
+------------------------------------------+
|  [!] 2 items need attention               |
|       2 selected for bootstrap            |
+------------------------------------------+
|  Essential (red border)                   |
|    [x] ROADMAP.md      [Planning]         |
|    [x] CLAUDE.md       [Documentation]    |
+------------------------------------------+
|  Recommended (amber border)               |
|    [ok] README          [Documentation]   |
|    [ok] Dependencies    [Project Struct.]  |
+------------------------------------------+
|  Passing Checks (collapsed)               |
|    [ok] Git Repository  ...               |
+------------------------------------------+
|  1 dismissed  [restore all]               |
+------------------------------------------+
|  [Bootstrap 2 Items]  [Re-scan]  [Skip]  |
+------------------------------------------+
```

### Tier Display

- **Tiers with failures** are expanded and bordered with the tier's color.
- **Tiers where all checks pass** are collapsed into a compact "Passing Checks" strip, shown only after all checks are revealed.
- Each check row shows: checkbox/green-circle, name, category tag, message, optional `why`, optional `remediation` hint, and a dismiss button.

### Category Labels

Check categories are mapped to human-readable names:

| Key | Label |
|-----|-------|
| `version_control` | Version Control |
| `documentation` | Documentation |
| `planning` | Planning |
| `project_structure` | Project Structure |
| `legal` | Legal |
| `testing` | Testing |
| `automation` | Automation |
| `security` | Security |

---

## 11. Error Handling

If the readiness scan fails entirely (API error), the Scorecard shows a centered error screen with:

- "Failed to scan project" heading
- The error message detail
- "Try Again" primary button
- "Back to Dashboard" secondary button (if `onBack` is provided)

---

## 12. Component Props

```typescript
interface ScorecardViewProps {
  projectPath: string;      // Absolute path to the project
  onBootstrap: () => void;  // Navigate to Bootstrap Wizard
  onSkip: () => void;       // Skip to dashboard
  onBack?: () => void;      // Optional back navigation
  onRefresh?: () => void;   // Optional refresh callback
}
```

---

## 13. Key Source Files

| File | Purpose |
|------|---------|
| `app/src/components/scorecard/ScorecardView.tsx` | Main scorecard view component |
| `app/src/components/scorecard/ReadinessRing.tsx` | Circular progress ring |
| `app/src/managers/projectManager.ts` | Zustand store with screen state machine |
| `app/src/types/index.ts` (lines 578-600) | `ReadinessCheck` and `ReadinessReport` types |
| `app/src/api/backend.ts` (line 267) | `scanReadiness` API call |
| `src/core/readiness.py` | Backend scanner with 12 checks and weighted scoring |
