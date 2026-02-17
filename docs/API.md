# REST API Reference

> Last updated: 2026-02-17

The Claudetini Python sidecar exposes a REST API on `http://127.0.0.1:9876`. All endpoints return JSON unless noted otherwise (SSE endpoints return `text/event-stream`).

## Base URL

```
http://127.0.0.1:9876
```

## Health Check

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Returns `{"status": "ok"}` when the sidecar is ready |
| `GET` | `/` | Returns API name, version, and docs URL |

---

## Projects (`/api/project`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/list` | List all registered projects |
| `POST` | `/register` | Register a new project by path |
| `GET` | `/{project_id}` | Get detailed project info |
| `GET` | `/health/{project_id}` | Get project health report |

### `GET /api/project/list`

Returns all registered projects (lightweight response).

**Response:** `ProjectResponse[]`
```json
[
  {
    "id": "abc123",
    "name": "my-project",
    "path": "/Users/me/my-project",
    "branch": "main",
    "uncommitted": 3,
    "lastSession": "2h ago",
    "lastOpened": "Today",
    "lastOpenedTimestamp": "2026-02-17T10:00:00Z",
    "costWeek": "$2.40",
    "totalSessions": 15,
    "readmeSummary": "A web application for..."
  }
]
```

### `POST /api/project/register`

Register a new project directory.

**Request Body:**
```json
{ "path": "/Users/me/my-project" }
```

**Response:** `ProjectResponse` (same shape as list item)

### `GET /api/project/{project_id}`

Get detailed project information including git state, sessions, and usage.

**Response:** `ProjectResponse`

### `GET /api/project/health/{project_id}`

Run health checks across 8 categories.

**Response:** `HealthResponse`
```json
{
  "items": [
    { "name": "Security", "status": "pass", "detail": "No secrets detected" },
    { "name": "Roadmap", "status": "warn", "detail": "ROADMAP.md not found" }
  ],
  "score": 75
}
```

**Health Check Categories:** Security, Roadmap, README, CLAUDE.md, .gitignore, Tests, Quality Gates, CI/CD

---

## Roadmap (`/api/roadmap`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/{project_id}` | Get parsed roadmap with milestone progress |
| `POST` | `/{project_id}/toggle-item` | Toggle a single item done/incomplete |
| `POST` | `/{project_id}/batch-toggle` | Batch toggle multiple items |

### `GET /api/roadmap/{project_id}`

**Response:** `RoadmapResponse`
```json
{
  "milestones": [
    {
      "id": 0,
      "title": "Core Features",
      "items": [
        { "text": "Add login", "done": true, "source": null, "conflict": null },
        { "text": "Add signup", "done": false, "source": null, "conflict": null }
      ],
      "completed": 1,
      "total": 2,
      "progress": 50.0
    }
  ],
  "totalItems": 2,
  "completedItems": 1,
  "progress": 50.0
}
```

### `POST /api/roadmap/{project_id}/toggle-item`

**Request Body:**
```json
{ "item_text": "Add login" }
```

**Response:** `ToggleItemResponse`
```json
{ "success": true, "item_text": "Add login", "new_state": false }
```

### `POST /api/roadmap/{project_id}/batch-toggle`

**Request Body:**
```json
{ "item_texts": ["Add login", "Add signup"], "mark_done": true }
```

---

## Timeline (`/api/timeline`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/{project_id}?limit=50` | Get session timeline entries |

### `GET /api/timeline/{project_id}`

**Query Parameters:**
- `limit` (int, 1-500, default 50)

**Response:** `TimelineResponse`
```json
{
  "entries": [
    {
      "sessionId": "sess_abc",
      "date": "2026-02-17T10:00:00Z",
      "durationMinutes": 15,
      "summary": "Implemented auth module",
      "provider": "claude",
      "branch": "main",
      "commits": [
        { "sha": "abc1234", "message": "feat: add auth", "timestamp": "..." }
      ],
      "filesChanged": 5,
      "tokenUsage": { "input": 5000, "output": 3000, "total": 8000, "model": "claude-3-5-sonnet" },
      "testResults": { "passed": true, "total": 10, "passedCount": 10 },
      "gateStatuses": { "lint": "pass", "tests": "pass" },
      "costEstimate": 0.024
    }
  ],
  "total": 15
}
```

---

## Quality Gates (`/api/gates`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/{project_id}` | Get latest gate results |
| `POST` | `/{project_id}/run` | Run all quality gates |

### `GET /api/gates/{project_id}`

**Response:** `GateReportResponse`
```json
{
  "gates": [
    {
      "name": "lint",
      "status": "pass",
      "message": "No lint errors",
      "detail": "ruff check passed",
      "findings": [],
      "durationSeconds": 1.2,
      "hardStop": false,
      "costEstimate": 0
    },
    {
      "name": "secrets",
      "status": "warn",
      "message": "1 potential secret found",
      "findings": [
        { "severity": "warn", "description": "Possible API key", "file": "config.py", "line": 42 }
      ],
      "durationSeconds": 0.8,
      "hardStop": true,
      "costEstimate": 0
    }
  ],
  "runId": "run_xyz",
  "timestamp": "2026-02-17T10:00:00Z",
  "trigger": "manual",
  "overallStatus": "warn",
  "changedFiles": ["src/auth.py"]
}
```

**Gate Types:** `command` (runs shell command), `agent` (dispatches to Claude CLI), `secrets` (scans for secrets)

**Gate Statuses:** `pass`, `warn`, `fail`, `skipped`, `error`

---

## Git (`/api/git`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/{project_id}/status` | Get full git status |
| `GET` | `/{project_id}/commits?limit=30` | Get recent commits |
| `GET` | `/{project_id}/stashes` | List stash entries |
| `POST` | `/{project_id}/push` | Push to remote |
| `POST` | `/{project_id}/commit` | Stage all and commit |
| `POST` | `/{project_id}/stage` | Stage specific files |
| `POST` | `/{project_id}/stage-all` | Stage all files |
| `POST` | `/{project_id}/unstage` | Unstage specific files |
| `POST` | `/{project_id}/unstage-all` | Unstage all files |
| `POST` | `/{project_id}/commit-staged` | Commit only staged files |
| `POST` | `/{project_id}/discard` | Discard changes to a file |
| `DELETE` | `/{project_id}/untracked` | Delete an untracked file |
| `POST` | `/{project_id}/stash/pop` | Pop latest stash |
| `POST` | `/{project_id}/stash/drop` | Drop a stash entry |
| `GET` | `/{project_id}/generate-message` | Generate commit message (heuristic, fast) |
| `GET` | `/{project_id}/generate-message-ai` | Generate commit message via Claude Code |
| `POST` | `/{project_id}/quick-commit` | Stage all + generate message + commit |

### `GET /api/git/{project_id}/status`

**Response:** `GitStatusResponse`
```json
{
  "branch": "main",
  "unpushed": [
    { "hash": "abc123", "msg": "feat: add auth", "branch": "main", "date": "2026-02-17", "time": "10:00" }
  ],
  "staged": [
    { "file": "src/auth.py", "status": "modified", "additions": 30, "deletions": 5 }
  ],
  "uncommitted": [
    { "file": "src/config.py", "status": "modified", "additions": 10, "deletions": 2 }
  ],
  "untracked": [
    { "file": "src/new_file.py" }
  ],
  "stashed": [
    { "index": 0, "message": "WIP: auth changes", "branch": "main", "date": "2026-02-16" }
  ],
  "submoduleIssues": []
}
```

### `GET /api/git/{project_id}/generate-message`

Heuristic commit message generation (fast, free).

**Response:** `GenerateMessageResponse`
```json
{
  "message": "feat: add authentication module",
  "files": ["src/auth.py", "src/config.py"],
  "summary": "2 files changed, 40 additions, 7 deletions"
}
```

### `GET /api/git/{project_id}/generate-message-ai`

AI-powered commit message via Claude Code CLI.

**Query Parameters:**
- `model` (string, default: `claude-haiku-4-5-20251001`)

**Response:** `AIGenerateMessageResponse`
```json
{
  "message": "feat(auth): implement JWT-based login with session management",
  "files": ["src/auth.py", "src/config.py"],
  "summary": "2 files changed",
  "ai_generated": true,
  "model": "claude-haiku-4-5-20251001",
  "error": null
}
```

### `POST /api/git/{project_id}/quick-commit`

One-click: stage all files, generate heuristic message, and commit.

**Response:** `QuickCommitResponse`
```json
{
  "success": true,
  "message": "Quick commit successful",
  "commit_message": "feat: add auth module",
  "hash": "abc1234",
  "files_committed": ["src/auth.py"]
}
```

---

## Dispatch (`/api/dispatch`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/` | Synchronous dispatch (blocking) |
| `POST` | `/start` | Start async dispatch (returns job_id) |
| `GET` | `/status/{job_id}` | Poll dispatch job status |
| `POST` | `/cancel/{job_id}` | Cancel a running dispatch |
| `GET` | `/output/{session_id}` | Read dispatch output file |
| `POST` | `/enrich-prompt` | Enrich task prompt with project context |
| `POST` | `/generate-task-prompt` | AI-generate a task prompt from a title |
| `POST` | `/summary` | Get dispatch summary (files changed, errors) |
| `POST` | `/advice` | Pre-dispatch cost/budget advice |
| `GET` | `/usage/{project_id}?days=7` | Provider usage totals |
| `POST` | `/fallback` | Synchronous fallback dispatch (Codex/Gemini) |
| `POST` | `/fallback/start` | Start async fallback dispatch |
| `GET` | `/fallback/status/{job_id}` | Poll fallback dispatch status |
| `POST` | `/fallback/cancel/{job_id}` | Cancel fallback dispatch |

### `POST /api/dispatch/start`

Start an async Claude Code dispatch.

**Request Body:**
```json
{
  "project_path": "/Users/me/my-project",
  "prompt": "Implement user authentication",
  "mode": "task",
  "roadmap_item": "Add login",
  "model": null,
  "agents_json": null
}
```

**Response:** `DispatchStartResponse`
```json
{ "job_id": "job_abc", "status": "queued", "phase": "queued", "message": "Dispatch queued" }
```

### `GET /api/dispatch/status/{job_id}`

**Response:** `DispatchStatusResponse`
```json
{
  "job_id": "job_abc",
  "status": "running",
  "phase": "running",
  "message": "Dispatch in progress",
  "created_at": "...",
  "started_at": "...",
  "finished_at": null,
  "done": false,
  "result": null,
  "error_detail": null,
  "output_tail": "Creating auth module...",
  "log_file": "/path/to/dispatch.log"
}
```

**Dispatch Phases:** `queued` -> `running` -> `succeeded` / `failed` / `cancelled`

### `POST /api/dispatch/enrich-prompt`

Enrich a task prompt with project context (roadmap state, git diff, conventions).

**Request Body:**
```json
{
  "project_path": "/Users/me/my-project",
  "task_text": "Add login",
  "custom_prompt": null
}
```

**Response:** `EnrichPromptResponse`
```json
{ "enriched_prompt": "...", "context_summary": "..." }
```

### `POST /api/dispatch/summary`

Get a summary of what a dispatch accomplished.

**Request Body:**
```json
{
  "session_id": "sess_abc",
  "project_path": "/Users/me/my-project",
  "log_file": "/path/to/dispatch.log"
}
```

**Response:** `DispatchSummaryResponse`
```json
{
  "success": true,
  "files_changed": [
    { "path": "src/auth.py", "additions": 50, "deletions": 0, "change_type": "new" }
  ],
  "total_added": 50,
  "total_removed": 0,
  "summary_message": "Created 1 new file",
  "has_errors": false
}
```

---

## Streaming Dispatch (`/api/dispatch/stream`)

SSE-based real-time dispatch output streaming.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/start` | Start SSE streaming dispatch |
| `GET` | `/{job_id}` | SSE event stream (EventSource) |
| `GET` | `/{job_id}/status` | Poll stream job status (fallback) |
| `POST` | `/{job_id}/cancel` | Cancel streaming dispatch |

### SSE Event Format

```json
{
  "type": "start | output | status | error | complete",
  "data": "string",
  "sequence": 42,
  "timestamp": "2026-02-17T10:00:00Z",
  "job_id": "stream_abc"
}
```

---

## Live Sessions (`/api/live-sessions`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/{project_id}` | Get active Claude Code sessions |

### `GET /api/live-sessions/{project_id}`

**Response:** `LiveSessionResponse`
```json
{
  "active": true,
  "sessions": [
    {
      "session_id": "sess_abc",
      "provider": "claude",
      "pid": 12345,
      "started_at": "...",
      "elapsed": 120,
      "estimated_cost": 0.05,
      "tokens_used": 8000,
      "files_modified": ["src/auth.py"]
    }
  ],
  "exchanges": [
    { "time": "10:01", "type": "user", "summary": "Add authentication", "files": [] },
    { "time": "10:02", "type": "assistant", "summary": "Created auth module...", "files": ["src/auth.py"] }
  ]
}
```

---

## Reconciliation (`/api/project/{project_id}/reconcile`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/quick-check` | Fast change detection (<100ms) |
| `POST` | `/analyze` | Start full reconciliation analysis |
| `POST` | `/verify` | Heuristic progress verification |
| `POST` | `/verify-ai` | AI-powered progress verification |
| `GET` | `/status/{job_id}` | Poll analysis job status |
| `GET` | `/result/{job_id}` | Get analysis results |
| `POST` | `/apply` | Apply reconciliation suggestions |
| `POST` | `/undo` | Undo last reconciliation |
| `GET` | `/diff/{commit_sha}` | Get diff for a specific commit |

**Snapshot Endpoints** (mounted on `/api/project/{project_id}`, not under `/reconcile`):

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/snapshot` | Create a reconciliation snapshot |
| `GET` | `/snapshots` | List all snapshots for the project |

### `GET /api/project/{project_id}/reconcile/quick-check`

Fast check for whether the project has changes since last snapshot.

**Response:** `QuickCheckResponse`
```json
{
  "has_changes": true,
  "commits_count": 5,
  "files_modified": 12,
  "uncommitted_count": 2
}
```

### `POST /api/project/{project_id}/reconcile/analyze`

Start background analysis matching code changes to roadmap items.

**Request Body:**
```json
{ "min_confidence": 0.5 }
```

**Response:**
```json
{ "job_id": "recon_abc", "status": "started" }
```

### `GET /api/project/{project_id}/reconcile/result/{job_id}`

**Response:** `ReconciliationReportResponse`
```json
{
  "report_id": "rpt_123",
  "timestamp": "...",
  "commits_added": 5,
  "files_changed": [
    { "path": "src/auth.py", "change_type": "modified", "loc_delta": 42, "is_substantial": true }
  ],
  "suggestions": [
    {
      "item_text": "Implement login",
      "milestone_name": "Core Features",
      "confidence": 0.85,
      "reasoning": ["File src/auth.py contains login logic", "Commit message references auth"],
      "matched_files": ["src/auth.py"],
      "matched_commits": ["abc1234"]
    }
  ],
  "already_completed_externally": ["Add README"]
}
```

### `POST /api/project/{project_id}/reconcile/apply`

Apply selected reconciliation suggestions (mark roadmap items as done).

**Request Body:**
```json
{
  "report_id": "rpt_123",
  "accepted_items": ["Implement login"],
  "dismissed_items": ["Add README"]
}
```

**Response:**
```json
{ "success": true, "items_completed": 1, "items_dismissed": 1 }
```

---

## Readiness (`/api/readiness`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/scan` | Full readiness scan |
| `GET` | `/score/{project_path}` | Just the score (lightweight) |

### `POST /api/readiness/scan`

**Request Body:**
```json
{ "project_path": "/Users/me/my-project" }
```

**Response:** `ReadinessReportResponse`
```json
{
  "score": 75,
  "is_ready": true,
  "checks": [
    {
      "name": "Git Repository",
      "category": "Foundation",
      "passed": true,
      "severity": "critical",
      "weight": 15,
      "message": "Git repository initialized",
      "remediation": null,
      "can_auto_generate": false
    },
    {
      "name": "CLAUDE.md",
      "category": "AI Readiness",
      "passed": false,
      "severity": "important",
      "weight": 10,
      "message": "No CLAUDE.md found",
      "remediation": "Create CLAUDE.md with project conventions",
      "can_auto_generate": true
    }
  ],
  "critical_issues": [],
  "warnings": ["No CLAUDE.md found"]
}
```

---

## Bootstrap (`/api/bootstrap`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/estimate` | Estimate bootstrap cost |
| `POST` | `/start` | Start bootstrap wizard |
| `GET` | `/stream/{session_id}` | SSE progress stream |
| `GET` | `/status/{session_id}` | Get bootstrap status |
| `GET` | `/result/{session_id}` | Get bootstrap result |
| `DELETE` | `/session/{session_id}` | Cleanup session |

### `POST /api/bootstrap/estimate`

**Request Body:**
```json
{ "project_path": "/Users/me/my-project" }
```

**Response:**
```json
{ "estimated_tokens": 15000, "estimated_cost_usd": 0.05, "steps": 4 }
```

### `POST /api/bootstrap/start`

**Request Body:**
```json
{
  "project_path": "/Users/me/my-project",
  "skip_steps": [],
  "dry_run": false
}
```

**Response:**
```json
{ "session_id": "boot_abc", "status": "started" }
```

### `GET /api/bootstrap/status/{session_id}`

**Response:** `BootstrapStatusResponse`
```json
{
  "session_id": "boot_abc",
  "status": "running",
  "progress": 50.0,
  "current_step": "Generating CLAUDE.md",
  "step_index": 1,
  "total_steps": 4
}
```

### `GET /api/bootstrap/result/{session_id}`

**Response:** `BootstrapResultResponse`
```json
{
  "success": true,
  "artifacts": {
    "claude_md": "Generated CLAUDE.md with project conventions",
    "roadmap": "Generated ROADMAP.md with 3 milestones"
  },
  "errors": [],
  "warnings": [],
  "duration_seconds": 45,
  "steps_completed": 4,
  "steps_total": 4
}
```

---

## Parallel Execution (`/api/parallel`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/git-check` | Check if working tree is clean |
| `POST` | `/cleanup-orphans` | Clean orphaned worktrees |
| `POST` | `/plan` | Start planning agent |
| `GET` | `/plan/status/{plan_job_id}` | Poll planning status |
| `POST` | `/plan/replan` | Re-plan with user feedback |
| `POST` | `/execute` | Start phased execution |
| `GET` | `/execute/status/{batch_id}` | Poll execution status |
| `POST` | `/cancel/{id}` | Cancel plan or execution |
| `POST` | `/release-hmr-lock` | Release Vite HMR lock |

### `POST /api/parallel/plan`

**Request Body:**
```json
{
  "project_path": "/Users/me/my-project",
  "tasks": [
    { "text": "Add user login", "done": false },
    { "text": "Add unit tests", "done": false }
  ],
  "milestone_title": "Core Features",
  "model": "claude-haiku-4-5-20251001"
}
```

**Response:**
```json
{ "plan_job_id": "plan_abc", "status": "planning" }
```

### `GET /api/parallel/plan/status/{plan_job_id}`

**Response:** `PlanStatusResponse`
```json
{
  "status": "complete",
  "output_tail": "Planning complete...",
  "plan": {
    "summary": "2 phases, 3 agents",
    "phases": [
      {
        "phase_id": 1,
        "name": "Foundation",
        "description": "Core auth logic",
        "parallel": true,
        "agents": [
          { "agent_id": 1, "theme": "Auth Backend", "task_indices": [0], "rationale": "..." },
          { "agent_id": 2, "theme": "Test Suite", "task_indices": [1], "rationale": "..." }
        ]
      }
    ],
    "success_criteria": ["All tests pass", "Login endpoint works"],
    "estimated_total_agents": 2,
    "warnings": []
  },
  "error": null
}
```

### `POST /api/parallel/execute`

Start phased execution of the approved plan.

**Request Body:**
```json
{
  "project_path": "/Users/me/my-project",
  "tasks": [...],
  "plan": { "phases": [...] },
  "max_parallel": 3
}
```

**Response:**
```json
{ "batch_id": "batch_abc", "status": "executing", "message": "Started" }
```

### `GET /api/parallel/execute/status/{batch_id}`

**Response:** `BatchStatusResponse`
```json
{
  "batch_id": "batch_abc",
  "phase": "executing",
  "current_phase_id": 1,
  "current_phase_name": "Foundation",
  "agents": [
    {
      "task_index": 0,
      "task_text": "Add user login",
      "status": "running",
      "output_tail": "Creating auth module...",
      "error": null,
      "cost_estimate": 0.30,
      "group_id": 1,
      "phase_id": 1
    }
  ],
  "merge_results": [],
  "verification": null,
  "verification_output_tail": null,
  "finalize_message": null,
  "plan_summary": "2 phases, 3 agents",
  "total_cost": 0.30,
  "started_at": "...",
  "finished_at": null,
  "error": null
}
```

**Phase Progression:** `executing` -> `merging` -> `verifying` -> `finalizing` -> `complete`

---

## Logs (`/api/logs`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/{project_id}?limit=100` | Get log entries |

### `GET /api/logs/{project_id}`

**Response:** `LogsResponse`
```json
{
  "entries": [
    { "time": "10:01:23", "level": "info", "src": "dispatch", "msg": "Starting task..." },
    { "time": "10:02:45", "level": "pass", "src": "gates", "msg": "All gates passed" },
    { "time": "10:03:00", "level": "warn", "src": "secrets", "msg": "Potential secret in config.py" }
  ],
  "total_count": 150
}
```

**Log Levels:** `info`, `pass`, `warn`, `fail`

---


## Error Handling

All endpoints return standard HTTP error codes:

| Code | Meaning |
|------|---------|
| `200` | Success |
| `400` | Bad request (missing/invalid parameters) |
| `404` | Resource not found (project, job, etc.) |
| `500` | Internal server error |

Error responses include detail messages:
```json
{ "detail": "Project not found: abc123" }
```

## CORS Configuration

The sidecar accepts requests from:
- `tauri://localhost`
- `http://localhost:5173` (Vite dev server)
- `http://localhost:1420` (Tauri dev)
- `http://127.0.0.1:*` (any localhost port)
