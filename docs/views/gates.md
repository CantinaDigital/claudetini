# Quality Gates Tab

Last updated: 2026-02-17

---

## 1. Purpose and Role in the App

The Quality Gates tab is Claudetini's automated code-quality enforcement layer. It sits between development work and deployment, running a configurable set of checks -- secrets scanning, linting, tests, type checking, security review, and documentation coverage -- against the active project. Results are displayed as a compact gate-card list with pass/warn/fail status, trend sparklines, and expandable finding details.

Quality gates serve three interconnected purposes:

- **Pre-dispatch validation.** Gates can be configured as hard stops that block Claude Code dispatch when they fail, preventing new AI work from compounding existing quality problems.
- **Pre-push enforcement.** An optional Git pre-push hook checks gate results before allowing `git push`, ensuring that only code passing all hard-stop gates reaches the remote.
- **Continuous quality visibility.** Historical trend data and per-gate sparklines give developers an at-a-glance view of code quality trajectory over time.

### Source Files

| Layer | File |
|-------|------|
| Frontend component | `app/src/components/gates/GatesTab.tsx` |
| Backend API routes | `app/python-sidecar/sidecar/api/routes/gates.py` |
| Gate orchestrator | `src/agents/gates.py` (`QualityGateRunner`) |
| Gate executor | `src/agents/executor.py` (`GateExecutor`) |
| Result persistence | `src/core/gate_results.py` (`GateResultStore`) |
| Trend computation | `src/core/gate_trends.py` (`GateTrendStore`) |
| Pre-push hook | `src/agents/hooks.py` (`GitPrePushHookManager`) |
| TypeScript types | `app/src/types/index.ts` (see `Gate`, `GateReport`, `GateFinding`) |
| API client | `app/src/api/backend.ts` (see `getGateResults`, `runGates`, `getGateHistory`) |
| Settings store | `app/src/stores/settingsStore.ts` (see `prePushHookEnabled`) |

---

## 2. Gate Types

Every gate has a `gate_type` field that determines how it is executed. The three types are `command`, `secrets`, and `agent`.

### 2.1 Command Gates

Command gates run a shell command (via `subprocess` with `shell=True`) inside the project directory and interpret the exit code:

- **Exit 0** = pass. The executor extracts a summary from stdout (e.g., test counts, "Clean" for lint).
- **Non-zero exit** = fail. Stderr (or stdout) is captured as the finding description and packaged into a `GateFinding` with a suggested-fix prompt.
- **Timeout** = error. The gate is marked `error` with a summary noting the timeout duration.

Environment variables `NO_COLOR=1`, `TERM=dumb`, and `FORCE_COLOR=0` are injected to suppress ANSI escape sequences. Any remaining ANSI codes are stripped by `_strip_ansi()`.

Default command gates:

| Gate | Default command | Hard stop |
|------|----------------|-----------|
| `tests` | `pytest --tb=short -q` | Yes |
| `lint` | `ruff check .` | Yes |
| `typecheck` | Auto-detected (e.g., `npx tsc --noEmit`, `mypy .`) | Yes |

### 2.2 Secrets Gate

The secrets gate is a dedicated type that uses `SecretsScanner` (from `src/core/secrets_scanner.py`) rather than a shell command. Key characteristics:

- **Always runs first** in every gate execution cycle.
- **Cannot be disabled.** If removed from config, the runner re-adds it automatically.
- **Hard stop by default.** If critical or high-severity secrets are found, the gate fails and the entire run short-circuits -- no other gates execute.
- Findings are capped at 40 items per run.
- Each finding includes a `suggested_fix_prompt` advising the developer to move sensitive values into environment variables.

Status determination:
- `pass` -- no secrets detected.
- `warn` -- secrets found but none are critical/high severity.
- `fail` -- critical or high-severity secrets detected.

### 2.3 Agent Gates

Agent gates use built-in heuristic analyzers (or optionally the Claude CLI) to perform higher-level code review. Unlike command gates, they do not simply run a shell command and check the exit code; they analyze project files and produce structured findings.

Default agent gates:

| Gate | What it does | Hard stop |
|------|-------------|-----------|
| `security` | Runs `SecretsScanner` in full-tree mode (not staged-only) and reports credential patterns | Yes |
| `documentation` | Scans changed `.py` files for public functions/classes missing docstrings | No |
| `test_coverage` | Checks whether changed source files have matching test files (`test_*.py` / `*_test.py`) | No (disabled by default) |

When the gate config has `command: "claude"` and the `claude` CLI is on `$PATH`, the executor invokes it as a subprocess with `--output-format json`, parses the structured output, and extracts token usage for cost tracking. This path is optional and only activates when explicitly configured.

The `documentation` gate uses a `fail_threshold` (default 3): if the number of missing docstrings is below the threshold, the gate warns; at or above, it fails.

---

## 3. UI Structure

The `GatesTab` component (`GatesTab.tsx`) renders the following layout from top to bottom:

### 3.1 Header Bar

A horizontal bar with:

- **Left side:** Last run timestamp (relative, e.g., "5m ago"), file count ("12 files"), and total cost estimate in monospace (`$0.00` or `N/A`).
- **Right side:** Two buttons:
  - **Configure** -- navigates to the Settings tab (calls `onNavigateToSettings` prop).
  - **Run All** (primary, purple) -- triggers `api.runGates(projectPath)`. Disabled and shows "Running..." while a run is in progress.

### 3.2 Error Banner

If the backend returns an error, a red-bordered alert box appears below the header showing the error message.

### 3.3 Gate Cards List

An accessible `role="list"` container holding one card per gate. Each card is a rounded surface (`bg-mc-surface-1`) with a conditional border color:

| Gate status | Border |
|-------------|--------|
| `fail` | `border-mc-red-border` |
| `warn` | `border-mc-amber-border` |
| `pass` / other | `border-mc-border-0` |
| Focused (keyboard) | `border-mc-accent-border` |

Each card row contains (left to right):

1. **Icon** -- an emoji looked up from `GATE_ICONS` by gate name (e.g., `tests` -> test tube, `secrets` -> lock with key, `lint` -> sparkles, `typecheck` -> ruler).
2. **Gate name** -- capitalized, semibold, 13.5px.
3. **Severity tag** -- rendered via `<SeverityTag status={...} />`.
4. **Detail message** -- monospace, muted text, rendered through `<InlineMarkdown>` for inline formatting.
5. **Sparkline** -- a `<Sparkline>` component showing the last 10 historical scores, colored green/amber/red based on current status.
6. **Relative timestamp** -- e.g., "3m ago".
7. **Chevron** -- only shown when the gate has a finding; toggles expansion.

### 3.4 Expanded Finding Panel

Clicking a card with a finding (or pressing Enter/Space when focused) reveals an expandable panel containing:

- A `<pre>` block with the finding text (monospace, word-wrapped).
- A **Fix** button (danger-styled for `fail`, primary for `warn`). Clicking it calls `onFix(gateName, finding)` if provided, or logs to console.
- The panel background is `bg-mc-red-muted` for failures and `bg-mc-amber-muted` for warnings.

### 3.5 Git Pre-Push Hook Toggle

Below the gate list, a separate card shows:

- **Title:** "Git Pre-Push Hook"
- **Subtitle:** "Block push when gates fail"
- **Toggle:** Bound to `prePushHookEnabled` in the Zustand settings store. Toggling it calls `setPrePushHookEnabled(!prePushHook)`.

### 3.6 Keyboard Navigation

The gate list supports full keyboard navigation via `handleGateKeyDown`:

- **Arrow Down / Arrow Up** -- move focus between gate cards.
- **Enter / Space** -- expand or collapse the focused gate's finding panel.
- Focus is tracked via `focusedGateIndex` state and ref-based `focus()` calls.

### 3.7 Empty and Loading States

- **Loading:** "Loading quality gates..." centered text.
- **No project selected:** "Select a project to view quality gates."
- **No results:** A muted card reading "No quality gate results are available yet."

---

## 4. Auto-Detection of Gates from Project Structure

`QualityGateRunner._auto_detect_commands()` inspects the project directory to determine appropriate shell commands for command gates. Detection is file-based and language-aware:

### Python projects (`pyproject.toml`)

| Config content contains | Gate | Command |
|------------------------|------|---------|
| `pytest` | tests | `pytest --tb=short -q` |
| `ruff` | lint | `ruff check .` |
| `mypy` | typecheck | `mypy .` |

### Node.js projects (`package.json`)

| Condition | Gate | Command |
|-----------|------|---------|
| `scripts.test` contains "vitest" | tests | `npx vitest run` |
| `scripts.test` exists (other) | tests | `npm test` |
| `scripts.lint` exists | lint | `npm run lint` |
| No lint script but eslint in deps | lint | `npx eslint .` |
| `scripts.typecheck` exists | typecheck | `npm run typecheck` |
| No typecheck script but `tsconfig.json` exists | typecheck | `npx tsc --noEmit` |

### Makefile projects

| Target exists | Gate | Command |
|--------------|------|---------|
| `test:` | tests | `make test` |
| `lint:` | lint | `make lint` |
| `typecheck:` | typecheck | `make typecheck` |

### Rust projects (`Cargo.toml`)

| Gate | Command |
|------|---------|
| tests | `cargo test` |
| lint | `cargo clippy -- -D warnings` |

### Go projects (`go.mod`)

| Gate | Command |
|------|---------|
| tests | `go test ./...` |
| lint | `golangci-lint run` |

Detection is evaluated in the order listed above. Later entries can overwrite earlier ones (e.g., a project with both `pyproject.toml` and `Makefile` will use Makefile targets if present). The `typecheck` gate is only enabled when a command is detected; otherwise it remains configured but disabled.

---

## 5. Gate Configuration and Customization

### 5.1 Configuration Storage

Gate configuration is stored at `~/.claudetini/projects/<hash>/gates.json`. The JSON structure:

```json
{
  "gates": {
    "secrets": {
      "enabled": true,
      "type": "secrets",
      "hard_stop": true,
      "command": null,
      "agent_prompt": null,
      "auto_detect": false,
      "timeout": 300,
      "min_coverage": null,
      "severity_threshold": null,
      "fail_threshold": 3
    },
    "tests": {
      "enabled": true,
      "type": "command",
      "hard_stop": true,
      "command": "pytest --tb=short -q",
      "timeout": 300
    }
  },
  "triggers": {
    "on_session_end": true,
    "on_demand": true,
    "pre_push": false
  },
  "git_hook_installed": false
}
```

### 5.2 GateConfig Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | (required) | Gate identifier, used as key in config |
| `gate_type` | `"command"` / `"agent"` / `"secrets"` | (required) | Determines execution strategy |
| `enabled` | bool | `true` | Whether the gate runs |
| `hard_stop` | bool | `false` | Whether failure blocks dispatch/push |
| `command` | string or null | null | Shell command for command gates |
| `agent_prompt` | string or null | null | Prompt template for agent gates using Claude CLI |
| `auto_detect` | bool | `true` | Whether to auto-detect commands from project structure |
| `timeout` | int | 300 | Maximum execution time in seconds |
| `min_coverage` | int or null | null | Minimum coverage percentage (reserved) |
| `severity_threshold` | string or null | null | Minimum severity to trigger failure (e.g., `"high"`) |
| `fail_threshold` | int | 3 | Number of findings before a gate fails vs. warns |

### 5.3 Custom Gates

Users can add custom gates by editing `gates.json` directly. Any gate name not in the auto-detected defaults is preserved across config reloads. Custom gates must specify at least `type` and `command` (for command gates) or will be skipped.

### 5.4 Config Loading Behavior

On `load_config()`:

1. If no `gates.json` exists, the runner generates a default config from auto-detection and saves it.
2. If the file is corrupt or unreadable, defaults are regenerated.
3. Existing config is merged with auto-detected defaults -- existing user overrides are preserved, but new auto-detected gates are added.
4. Backward compatibility handles an older list-form config format (array of gate objects instead of a dictionary).

---

## 6. Gate Execution Flow

### 6.1 Execution Order

The `run_all_gates()` method in `QualityGateRunner` orchestrates the following sequence:

```
1. Secrets gate (always first, cannot be skipped)
   |
   |-- If secrets fail + hard_stop: STOP. Return report immediately.
   |
2. Command gates (run in parallel via ThreadPoolExecutor)
   |-- Up to 4 concurrent workers
   |-- Results sorted back into original config order
   |
3. Agent gates (run sequentially, one at a time)
   |-- security -> documentation -> test_coverage -> custom agents
   |-- Cost tracked per gate
```

### 6.2 Command Gates: Parallel Execution

`GateExecutor.run_command_gates()` uses a `ThreadPoolExecutor` with `max_workers=min(4, len(gates))`. Each gate runs its shell command independently. After all futures complete, results are sorted back into the original configuration order for consistent display.

### 6.3 Agent Gates: Sequential Execution

`GateExecutor.run_agent_gates()` iterates over agent configs one at a time. This is intentional:

- Agent gates may invoke the Claude CLI, which is resource-intensive.
- Sequential execution avoids concurrent API calls that could hit rate limits.
- Each agent's cost is recorded to the `CostTracker` immediately after completion.

### 6.4 Disabled Gates

Gates with `enabled: false` are not executed. Instead, a `GateResult` with `status: "skipped"` and `message: "Gate disabled"` is added to the report.

### 6.5 Trigger Types

Gate runs can be triggered by:

| Trigger | Value | Source |
|---------|-------|--------|
| Manual | `"manual"` | User clicks "Run All" in the UI |
| API | `"api"` | Called via the `/api/gates/{id}/run` POST endpoint |
| Session end | `"on_session_end"` | (configured in triggers, not yet wired) |
| Pre-push | `"pre_push"` | Git pre-push hook |

---

## 7. Results Display

### 7.1 Status Values

Every gate produces one of five statuses:

| Status | Meaning | Visual treatment |
|--------|---------|-----------------|
| `pass` | Gate passed all checks | Green severity tag, green sparkline |
| `warn` | Issues found but below failure threshold | Amber severity tag, amber sparkline, amber border |
| `fail` | Gate failed; blocking if hard-stop | Red severity tag, red sparkline, red border |
| `skipped` | Gate is disabled | Rendered but no findings |
| `error` | Gate execution itself failed (timeout, crash) | Red styling |

### 7.2 Findings

Each gate can produce a list of `GateFinding` objects with:

- `severity` -- e.g., "critical", "high", "medium", "low"
- `description` -- human-readable explanation
- `file` -- optional file path
- `line` -- optional line number
- `suggested_fix_prompt` -- a prompt that can be dispatched to Claude Code to auto-fix the issue

The frontend shows the first finding's description in the expandable panel. The "Fix" button is intended to dispatch the `suggested_fix_prompt` to the Claude Code agent.

### 7.3 Duration

Each gate records `duration_seconds` -- the wall-clock time from start to subprocess completion (or scanner completion for secrets). This is stored in the report but not prominently displayed in the current UI (the relative timestamp shown is the run timestamp, not per-gate duration).

### 7.4 Cost Estimate

Agent gates that invoke the Claude CLI extract token usage from the JSON response and compute a cost estimate via `estimate_cost()`. The total cost across all gates is summed and displayed in the header bar (e.g., `$0.03`). Command and secrets gates have a cost estimate of `$0.00`.

### 7.5 Metric Extraction

For command gates, the executor attempts to extract meaningful metrics from stdout:

- **Tests:** Looks for a `N/M` pattern (e.g., "5/5 passing") and coverage percentage patterns (`XX% cov`).
- **Lint:** Counts error mentions to derive a quality score (100 minus error count).

These metrics feed into the trend system.

---

## 8. Gate Trends and Historical Data

### 8.1 How Trends Are Computed

After every gate run, `QualityGateRunner._persist()` saves the report and then calls `GateTrendStore.compute()`. This method:

1. Loads the last 200 historical reports from `~/.claudetini/projects/<hash>/gate-results/`.
2. For each gate in each report, records a `GateHistoryPoint` with date, status, and metric.
3. Keeps the most recent `limit` points (default 10) per gate.
4. Saves the aggregated trends to `gate-trends.json`.

### 8.2 Metric Mapping

When a gate does not produce a numeric metric, the status is mapped to a default:

| Status | Metric |
|--------|--------|
| pass | 3.0 |
| warn | 2.0 |
| skipped | 2.0 |
| fail | 1.0 |
| error | 1.0 |

### 8.3 Sparkline Rendering

The backend provides a `render_sparkline()` function that converts metric values to Unicode block characters (`▁▂▃▄▅▆▇█`), but the frontend renders its own `<Sparkline>` component using the numeric scores from the history API.

The frontend fetches trend data via `api.getGateHistory(projectPath)`, which returns `Record<string, GateHistoryPoint[]>`. Each point has a `score` (0-100). The component maps the last 10 points to a 0.0-1.0 range (`score / 100`) and passes them to the `<Sparkline>` component.

When no history is available, `generateTrend()` creates a flat array of 10 values: `1.0` for pass, `0.5` for warn, `0.0` for fail.

### 8.4 Persistence Files

| File | Location | Purpose |
|------|----------|---------|
| Individual reports | `gate-results/<timestamp>-<run_id>.json` | Full historical record |
| Latest report | `gate-results/latest.json` | Quick access for the UI |
| Last status | `last-gate-status.json` | Compact status for pre-push hook |
| Trends | `gate-trends.json` | Aggregated sparkline data |
| Failure todos | `gate-failure-todos.json` | Open/resolved finding tracking |

All paths are relative to `~/.claudetini/projects/<hash>/`.

---

## 9. Hard Stop Behavior

### 9.1 What Hard Stop Means

A gate with `hard_stop: true` blocks downstream actions when it fails:

- **Secrets gate failure with hard stop:** The entire gate run short-circuits immediately. No command or agent gates execute. The report is persisted and returned with only the secrets result.
- **Pre-push hook:** The `last-gate-status.json` file is checked by the Git hook script. It verifies that (a) the gate results are fresh (matching current HEAD, index fingerprint, and worktree fingerprint) and (b) no hard-stop gates are failing. If either check fails, `git push` is blocked with an explanatory message. The developer can bypass with `git push --no-verify`.
- **Dispatch blocking:** Hard-stop failures in the gate report can be used by the dispatch system to prevent new Claude Code sessions from starting (via the `hard_stop_failures` property on `GateReport`).

### 9.2 Default Hard-Stop Configuration

| Gate | Hard stop | Rationale |
|------|-----------|-----------|
| `secrets` | Yes | Credential leaks are critical and must block everything |
| `tests` | Yes | Failing tests indicate broken functionality |
| `lint` | Yes | Lint failures indicate code quality regression |
| `typecheck` | Yes | Type errors indicate correctness issues |
| `security` | Yes | Security findings above threshold are blocking |
| `documentation` | No | Missing docs are advisory, not blocking |
| `test_coverage` | No | Missing test files are advisory |

### 9.3 Pre-Push Hook Details

The pre-push hook is a managed section injected into `.git/hooks/pre-push`. It:

1. Reads `last-gate-status.json` from the project's runtime directory.
2. Compares the stored `head_sha`, `index_fingerprint`, and `working_tree_fingerprint` against the current Git state.
3. If the stored state does not match the current state, the push is blocked with "Gate results are stale."
4. If any gate has `hard_stop: true` and `status: "fail"`, the push is blocked with the gate name and summary.
5. The hook is installed/removed via `GitPrePushHookManager.install()` / `.remove()`, which injects or extracts a clearly marked section between `# >>> claudetini pre-push >>>` and `# <<< claudetini pre-push <<<` markers.

---

## 10. Edge Cases

### 10.1 No Gates Configured

When `gates.json` does not exist:

- `QualityGateRunner.load_config()` generates a default configuration via `_default_config()` and `_auto_detect_commands()`, then writes it to disk.
- The UI shows "No quality gate results are available yet." until the first run completes.

When the project has no recognizable build system (no `pyproject.toml`, `package.json`, `Makefile`, `Cargo.toml`, or `go.mod`):

- The secrets gate is always present.
- Tests default to `pytest --tb=short -q` and lint to `ruff check .` -- these may fail if the tools are not installed, producing `error` status rather than `fail`.
- Typecheck remains disabled (no command detected).

### 10.2 Gate Execution Errors

Errors are distinguished from failures:

- **Timeout:** If a command gate exceeds its `timeout` (default 300s), `subprocess.TimeoutExpired` is caught and the gate is marked `status: "error"` with summary `"Timed out after {timeout}s"`.
- **Command not found / crash:** Any `Exception` from `subprocess.run()` is caught and produces `status: "error"` with the exception message as summary.
- **Secrets scanner crash:** `_run_secrets_gate` wraps the scanner in a try/except; any exception produces `status: "error"` with `"Secrets scan failed: {exc}"`.
- **Backend unreachable:** The frontend checks `isBackendConnected()` before making API calls. If disconnected, gates are cleared and the loading state is dismissed without an error banner.
- **Corrupt config file:** `load_config()` catches `json.JSONDecodeError` and `OSError`, regenerates defaults, and overwrites the corrupt file.

### 10.3 Long-Running Agent Gates

Agent gates can be slow, especially when invoking the Claude CLI:

- Each agent gate has a configurable `timeout` (default varies: 120s for security, 90s for documentation and test_coverage).
- When using the Claude CLI (`command: "claude"`), the subprocess timeout is taken from the gate config (default 180s).
- Agent gates run sequentially, so a single slow agent blocks subsequent agents but does not block the UI -- the frontend shows "Running..." on the button and waits for the entire `POST /run` response.
- The frontend API call uses the default 2-minute timeout (`120000ms`). If the total gate run exceeds this, the frontend will show a timeout error even though the backend may still be processing.

### 10.4 Stale Gate Results

Gate results become stale when the Git state changes after a run:

- The pre-push hook detects staleness by comparing SHA, index fingerprint, and worktree fingerprint.
- The UI does not currently display a staleness indicator -- it shows whatever the latest report contains.
- Re-running gates via "Run All" produces a fresh report tied to the current Git state.

### 10.5 No Project Selected

If `projectPath` is null or undefined, the component renders "Select a project to view quality gates." and makes no API calls.

### 10.6 Concurrent Gate Runs

The backend does not explicitly guard against concurrent gate runs for the same project. If the user clicks "Run All" twice rapidly, both runs will execute and the second will overwrite `latest.json`. The UI disables the "Run All" button during execution (`running` state) to prevent this at the UI level.

### 10.7 Failure Todo Lifecycle

The `GateResultStore._sync_failure_todos()` method maintains a feedback loop:

- New findings from a failing gate create `GateFailureTodo` entries (identified by a SHA-1 key of gate name + severity + file + line + description).
- If a previously-failing finding no longer appears in the latest report, its todo is marked `resolved_at`.
- If the same finding reappears, its `resolved_at` is cleared (re-opened).
- The todo file is capped at 1000 entries.
