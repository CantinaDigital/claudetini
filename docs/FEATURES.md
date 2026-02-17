# Feature Catalog

> Last updated: 2026-02-17

Comprehensive catalog of all Claudetini features organized by functional area.

## Table of Contents

1. [Project Management](#1-project-management)
2. [Overview Dashboard](#2-overview-dashboard)
3. [Roadmap Management](#3-roadmap-management)
4. [Task Dispatch](#4-task-dispatch)
5. [Parallel Execution](#5-parallel-execution)
6. [Quality Gates](#6-quality-gates)
7. [Git Operations](#7-git-operations)
8. [Reconciliation](#8-reconciliation)
9. [Session Intelligence](#9-session-intelligence)
10. [Bootstrap & Readiness](#10-bootstrap--readiness)
11. [Provider Management](#11-provider-management)
12. [Settings & Configuration](#12-settings--configuration)
13. [Logging & Audit](#13-logging--audit)

---

## 1. Project Management

### Project Picker
- Browse all registered Claude Code projects in a card-based view
- Each card shows: project name, branch, session count, last activity, README summary
- Register new projects by entering a directory path
- Auto-detects Claude Code project hash from `~/.claude/projects/`

### Project Registration
- Validates directory exists and contains a git repo
- Auto-discovers Claude Code session data
- Computes stable project ID from path hash

### Multi-Project Support
- Switch between projects from the project picker
- Each project maintains independent state (gates, snapshots, dispatch history)
- Runtime data stored per-project at `~/.claudetini/projects/<hash>/`

---

## 2. Overview Dashboard

### Project Hero
- Project name and current git branch
- Uncommitted file count with status indicator
- Total sessions count and weekly cost estimate
- Last session timestamp with relative time display
- Health score (0-100) with color-coded indicator

### Active Milestone Card
- Shows the current active milestone from the roadmap
- Per-item progress with completion checkboxes
- Phase and sprint labels
- Click-to-dispatch: launch a task for any roadmap item
- Batch mode: select multiple items for sequential dispatch

### Live Session Feed
- Real-time detection of active Claude Code sessions
- Shows user/assistant exchanges as they happen
- Displays: elapsed time, estimated cost, tokens used, files modified
- Polls every 5 seconds when the Overview tab is active

### Recent Sessions
- History of past Claude Code sessions
- Per-session: duration, summary, commits, files changed, cost
- Provider badge (Claude, Codex, Gemini)
- Click to view session report overlay

### Quality Issues Panel
- Surfaces current quality warnings from the latest gate run
- Color-coded severity (pass/warn/fail)
- Quick link to Quality Gates tab for details

### Git Status Bar
- Compact horizontal bar showing current git state
- Uncommitted changes count, unpushed commits, branch behind remote

---

## 3. Roadmap Management

### Roadmap Viewer
- Renders all milestones from `.claude/planning/ROADMAP.md`
- Expandable milestones with per-item detail
- Progress bar per milestone showing completion percentage
- Overall progress indicator (total items completed / total)

### Item Actions
- **Toggle completion** — Click checkbox to mark item done/undone (writes to ROADMAP.md)
- **Launch dispatch** — Click play button to dispatch task for a specific item
- **View prompt** — Items with embedded prompts show the task description
- **Batch toggle** — Select multiple items and mark done/undone at once

### Milestone Plan Mode
- Select a milestone to create a combined dispatch plan
- Review combined prompt before execution
- Execute all items in sequence with a single dispatch

### Parallel Execution Launch
- Click "Run Parallel" on any milestone to enter parallel mode
- AI planning agent decomposes tasks into phases and agents
- Review and approve the execution plan before starting
- See full details in [Parallel Execution](#5-parallel-execution)

---

## 4. Task Dispatch

### Dispatch Methods
- **Ask Input** — Free-text prompt from the Overview tab
- **Roadmap Item** — Click play on a specific roadmap item
- **Milestone Batch** — Execute all items in a milestone sequentially
- **Parallel Execution** — Multi-agent parallel execution of milestone items

### Pre-Flight Checks
Before every dispatch, the system runs pre-flight checks:
1. **Uncommitted changes** — Warns if there are unstaged/uncommitted files
2. **Unpushed commits** — Warns if commits haven't been pushed
3. **Gate failures** — Warns if quality gates are failing
4. **Budget check** — Warns if approaching budget limits

Users can proceed despite warnings or must resolve hard stops.

### Dispatch Execution Flow
1. SSE streaming attempted first for real-time output
2. Automatic fallback to HTTP polling if SSE fails
3. Real-time CLI output display in the Dispatch Overlay
4. Elapsed time counter and progress estimation
5. Cancel button to abort running dispatches

### Post-Dispatch Actions
- **Dispatch Summary** — Shows files changed, lines added/removed
- **Auto-mark roadmap item** — If dispatched from a roadmap item, auto-marks it complete on success
- **Session Report** — View detailed session report with commits, cost, test results
- **Reconciliation trigger** — Automatically checks for code-to-roadmap matches

### Prompt Enrichment
- Task prompts are enriched with project context before dispatch
- Includes: roadmap state, recent session memory, git diff, conventions from CLAUDE.md
- AI-generated task prompts from item titles (uses Claude Code CLI)

### Token Limit Detection
- Detects when Claude Code hits token limits
- Surfaces clear error with option to use fallback provider

---

## 5. Parallel Execution

### AI-Orchestrated Planning
- AI planning agent analyzes roadmap tasks and project structure
- Decomposes tasks into execution phases (sequential and parallel)
- Assigns themed agents to related tasks
- Generates success criteria for verification

### Plan Review
- Visual display of proposed execution plan
- Phase breakdown with agent assignments and rationale
- Success criteria listing
- Estimated total agents and warnings
- **Approve** to execute or provide **feedback** for re-planning

### Multi-Phase Execution
- Git worktrees created for each parallel agent (isolated execution)
- Multiple agents run concurrently within a phase
- Phases execute sequentially (phase N completes before phase N+1 starts)
- Real-time status cards for each agent: running, complete, error

### Branch Merging
- After each phase, worktree branches are merged back to main
- Conflict detection with resolution attempts
- Merge results displayed with per-branch status

### Automated Verification
- Claude Code verifies success criteria against the codebase
- Per-criterion pass/fail with evidence and notes
- Overall pass/fail determination

### Finalization
- Roadmap items auto-marked complete
- Total cost summary across all agents
- Full execution timeline

### HMR Resilience
- Execution state persisted to localStorage
- Auto-resumes polling after Vite HMR reloads or page refresh

---

## 6. Quality Gates

### Gate Types
- **Command gates** — Execute shell commands (lint, test, type-check, etc.)
- **Secrets gates** — Scan for accidentally committed secrets
- **Agent gates** — Dispatch to Claude Code for code analysis

### Auto-Detection
- Gates automatically detected from project structure:
  - Python: ruff, mypy, pytest
  - JavaScript/TypeScript: eslint, tsc, jest, vitest
  - Go: go vet, go test
  - Rust: cargo check, cargo test

### Gate Results
- Per-gate status: pass, warn, fail, skipped, error
- Findings list with severity, description, file, and line number
- Duration tracking per gate
- Cost estimate for agent gates
- Hard stop flag — blocks dispatch when failing

### Gate Trends
- Sparkline charts showing gate health over time
- Historical data points with timestamp and score
- Visual trend identification

### Gate Configuration
- Configurable per-project at `~/.claudetini/projects/<hash>/gates.json`
- Enable/disable individual gates
- Custom commands and thresholds
- Fail threshold (number of findings before gate fails vs. warns)

### Gate Reset
- Reset gate configuration back to auto-detected defaults

---

## 7. Git Operations

### Status View
- **Staged files** — Files in the staging area with status and line changes
- **Uncommitted files** — Modified files not yet staged
- **Untracked files** — New files not tracked by git
- **Unpushed commits** — Commits ahead of remote
- **Stashes** — Saved stash entries
- **Submodule issues** — Detected submodule problems

### Staging Area Management
- Stage individual files or all files
- Unstage individual files or all files
- Visual diff indicator per file (lines added/removed)

### Commit Message Generation
- **Heuristic (fast)** — Analyzes diff to generate conventional commit messages
- **AI-generated** — Uses Claude Code CLI for high-quality commit messages
- Editable message field before committing
- Supports conventional commit format (feat:, fix:, refactor:, etc.)

### One-Click Operations
- **Quick Commit** — Stage all + generate message + commit in one step
- **Push** — Push to remote with status feedback
- **Stash Pop/Drop** — Manage stash entries
- **Discard** — Discard changes to individual files
- **Delete Untracked** — Remove new untracked files

---

## 8. Reconciliation

### Change Detection
- Fast quick-check (<100ms) detects whether the project has changed since last snapshot
- Tracks: new commits, modified files, uncommitted changes
- Footer indicator shows "Changes Detected" state

### Analysis Engine
Three verification modes:

1. **Heuristic Analysis** — File path matching, commit message analysis, keyword extraction (fast, free)
2. **Progress Verification** — Enhanced heuristic with confidence scoring
3. **AI-Powered Verification** — Uses Claude Code for high-accuracy matching (slower, costs tokens)

### Confidence Scoring
- Each suggestion includes a confidence score (0-1)
- Configurable minimum confidence threshold (default: 50%)
- Higher thresholds = fewer but more accurate suggestions

### Suggestion Review
- Modal dialog showing all matched suggestions
- Per-suggestion: item text, milestone, confidence, reasoning, matched files/commits
- Checkbox interface to accept or dismiss each suggestion

### Apply & Undo
- Apply accepted suggestions: marks items as `[x]` in ROADMAP.md
- Dismissed suggestions are recorded but not applied
- Undo last reconciliation to revert changes
- Creates new snapshot after apply

### Auto-Trigger
- Automatically checks for changes after dispatch completes
- Reconciliation footer appears when changes are detected
- User controls when to run full analysis

---

## 9. Session Intelligence

### Timeline View
- Chronological list of all Claude Code sessions
- Per-session details:
  - Duration and timestamp
  - Summary of work done
  - Provider used (Claude, Codex, Gemini)
  - Branch worked on
  - Git commits correlated to session time window
  - Files changed count
  - Todos created/completed
  - Roadmap items completed
  - Token usage and cost estimate
  - Test results (if tests were run)
  - Gate statuses at time of session

### Session Reports
- Detailed post-session overlay with full session data
- Commit list with messages
- File change summary
- Cost breakdown

### Multi-Provider Timeline
- Sessions from Codex and Gemini dispatches included in timeline
- Provider-specific badges and color coding
- Unified view across all AI providers

---

## 10. Bootstrap & Readiness

### Readiness Scorecard
- 12-check assessment of project readiness for AI-assisted development
- Visual ring indicator with percentage score
- Checks categorized by severity: Critical, Important, Nice to Have
- Per-check: name, status, message, remediation hint
- Some checks offer auto-generation capability

### Bootstrap Wizard
- Multi-step automated project setup using Claude Code CLI
- Cost estimation before starting (tokens and USD)
- Steps:
  1. Analyze project structure and purpose
  2. Generate CLAUDE.md with project conventions
  3. Generate ROADMAP.md with development milestones
  4. Generate architecture documentation (optional)
- SSE progress streaming with step-by-step updates
- Result summary with generated artifacts
- Skip options for individual steps

---

## 11. Provider Management

### Provider Detection
- Auto-detects installed AI providers: Claude Code, Codex, Gemini
- Shows version, authentication status, and health
- Provider test button to verify connectivity

### Provider Fallback
- Pre-dispatch advice recommends fallback when:
  - Claude usage is approaching limits
  - Usage exceeds configurable threshold
  - Token limit already reached
- Fallback modal allows selecting alternative provider (Codex/Gemini)
- Full dispatch support for fallback providers

### Usage Tracking
- Per-provider usage aggregation over configurable time windows
- Tracks: tokens, effort units, cost (USD), event count
- Dashboard display of weekly spending

### Budget Management
- Token budget limits (monthly, weekly, per-session)
- Budget evaluation before dispatch with warnings
- Remaining budget percentage calculation
- Blitz session cost estimation

---

## 12. Settings & Configuration

### Provider Settings
- Preferred fallback provider (Codex or Gemini)
- Usage mode (subscription or API)
- Claude remaining usage percentage
- Fallback suggestion threshold

### Reconciliation Settings
- Enable/disable auto-reconciliation
- Confidence threshold slider (0-100%)

### Hook Configuration
- Pre-session hooks: shell commands run before dispatch
- Post-session hooks: shell commands run after dispatch
- Pre-merge hooks: shell commands run before parallel merge
- Post-merge hooks: shell commands run after parallel merge

### Parallel Execution Settings
- Maximum parallel agents (1-8, default 3)
- Planning model selection (default: Claude Haiku)

### Branch Strategy
- Auto-detected branching strategy display
- Shows: strategy name, description, evidence

### Context Files
- List project context files (CLAUDE.md, .cursorrules, etc.)
- Status indicator per file (present, missing, warning)
- Auto-generate missing context files

### Settings Actions
- Reset quality gates to defaults
- Clear project history
- Remove project from registry

---

## 13. Logging & Audit

### Log Viewer
- Chronological log entries with severity levels: info, pass, warn, fail
- Source attribution per entry (dispatch, gates, secrets, etc.)
- Configurable entry limit

### Dispatch Audit Trail
- Append-only audit log for safety overrides
- Tracks: gate overrides, budget overrides, prompt-secret overrides
- Timestamps and event details

### API Performance Monitoring
- All API calls timed and logged to browser DevTools console
- Grouped summary with per-endpoint timing
- Slow call warnings (>500ms)
- Tier classification: instant (<50ms), fast (<200ms), medium (<1s), slow (>1s)
