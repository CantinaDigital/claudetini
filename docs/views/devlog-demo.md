# Devlog Demo Project

> Last updated: 2026-02-17

The devlog demo is the **intermediate** demo project shipped with Claudetini. It provides a fully configured FastAPI + SQLite developer time-tracking application with a realistic git history, a partially complete roadmap, and intentional dirty working state. Its purpose is to exercise every major Claudetini feature in a single, self-contained project that requires no external dependencies beyond Python.

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Target Audience](#2-target-audience)
3. [Project Structure](#3-project-structure)
4. [Architecture](#4-architecture)
5. [Git State Setup](#5-git-state-setup)
6. [Roadmap State](#6-roadmap-state)
7. [Claudetini Features Demonstrated](#7-claudetini-features-demonstrated)
8. [Setup Instructions](#8-setup-instructions)
9. [Commit-to-Roadmap Alignment](#9-commit-to-roadmap-alignment)
10. [Quality Gate Behavior](#10-quality-gate-behavior)
11. [Expected User Experience](#11-expected-user-experience)

---

## 1. Purpose

The devlog demo serves as the **"Full Dashboard Experience"** project. Unlike the beginner `recipe-cli` demo (which starts broken and guides the user through fixing it), devlog is already properly configured with:

- A `CLAUDE.md` project guide with managed status section
- A `.claude/planning/ROADMAP.md` at roughly 55% completion
- A git repository with 15 realistic commits spread over three weeks
- A deliberate mix of staged, unstaged, untracked, and stashed changes
- A complete test suite with 6 test modules
- CI workflow, architecture docs, and licensing

This lets users immediately explore every Claudetini dashboard tab, run quality gates, test reconciliation, view the timeline, and dispatch tasks -- without spending time on project setup.

**Source directory:** `examples/devlog/`

---

## 2. Target Audience

The devlog demo is aimed at developers who are already comfortable with:

- Git fundamentals (branches, staging, commits, stashing)
- Python project structure (packages, pyproject.toml, virtual environments)
- REST API concepts (endpoints, HTTP methods, request/response)
- Command-line tools

These users do not need a guided walkthrough. They want to open Claudetini and immediately see what a fully populated dashboard looks like, then explore features at their own pace.

---

## 3. Project Structure

```
examples/devlog/
|-- CLAUDE.md                           # Project guide with managed status section
|-- README.md                           # Project README with installation and usage
|-- LICENSE                             # MIT license
|-- pyproject.toml                      # Python project metadata and dependencies
|-- .env.example                        # Environment variable template
|-- .gitignore                          # Standard Python/IDE/DB ignores
|-- config.example.py                   # Example configuration file
|
|-- .claude/
|   `-- planning/
|       `-- ROADMAP.md                  # 4-milestone roadmap (~55% complete)
|
|-- .github/
|   `-- workflows/
|       `-- ci.yml                      # GitHub Actions CI (Python 3.11 + 3.12)
|
|-- docs/
|   `-- ARCHITECTURE.md                 # Layered architecture documentation
|
|-- devlog/                             # Main application package
|   |-- __init__.py                     # Package init, version = "0.1.0"
|   |-- app.py                          # FastAPI application setup, lifespan, CORS, error handler
|   |-- models.py                       # Pydantic models (API) + dataclasses (internal)
|   |-- database.py                     # SQLite connection, migrations, CRUD operations
|   |
|   |-- routes/
|   |   |-- __init__.py                 # Route module init
|   |   |-- entries.py                  # Time entry CRUD endpoints (/api/v1/entries)
|   |   `-- projects.py                 # Project CRUD endpoints (/api/v1/projects)
|   |
|   |-- services/
|   |   |-- __init__.py                 # Service module init
|   |   |-- entries.py                  # Entry business logic (EntryService)
|   |   |-- projects.py                # Project business logic (ProjectService)
|   |   `-- reports.py                  # Weekly summary, tag filtering, CSV export (ReportService)
|   |
|   `-- utils/
|       |-- __init__.py                 # Utils module init
|       |-- formatting.py              # Duration/date/time formatting helpers
|       |-- validation.py              # Input validation, sanitization
|       `-- cache.py                   # [UNTRACKED] File-based cache utility
|
`-- tests/                              # Test suite (6 modules)
    |-- __init__.py                     # Test package init
    |-- conftest.py                     # Shared fixtures (temp DB, sample data)
    |-- test_models.py                  # Pydantic + dataclass model tests (12 tests)
    |-- test_database.py               # Database CRUD operation tests (12 tests)
    |-- test_entries_routes.py         # Entry endpoint integration tests (5 tests)
    |-- test_projects_routes.py        # Project endpoint integration tests (4 tests)
    |-- test_entries_service.py        # Entry service logic tests (5 tests)
    `-- test_reports.py                # Report service tests (6 tests)
```

**Total:** ~30 files, ~1200 lines of Python code, 6 test modules with ~44 test cases.

### Key Files for Claudetini

| File | Claudetini Reads It For |
|------|---------------------------|
| `CLAUDE.md` | Project metadata, managed status section, conventions |
| `.claude/planning/ROADMAP.md` | Milestone tracking, progress calculation, task items |
| `.gitignore` | Readiness scoring (presence check) |
| `pyproject.toml` | Dependency detection, project name |
| `tests/` | Test presence check for quality gates |
| `.github/workflows/ci.yml` | CI presence check for readiness scoring |

---

## 4. Architecture

DevLog follows a three-layer architecture with clear separation of concerns:

```
HTTP Request --> Route --> Service --> Database
                                        |
HTTP Response <-- Route <-- Service <-- Result
```

### Layer 1: Routes (HTTP)

- `routes/entries.py` -- CRUD endpoints for time entries under `/api/v1/entries`
- `routes/projects.py` -- CRUD endpoints for projects under `/api/v1/projects`
- Routes handle HTTP serialization via Pydantic and delegate business logic to services

### Layer 2: Services (Business Logic)

- `services/entries.py` -- `EntryService` with create, get, list, update, delete, and duration calculation
- `services/projects.py` -- `ProjectService` with create, get, list, delete
- `services/reports.py` -- `ReportService` with weekly summary aggregation, tag filtering, and CSV export

### Layer 3: Database (Data Access)

- `database.py` -- Module-level SQLite connection singleton, WAL mode, migration runner, all CRUD functions
- `models.py` -- Pydantic models for API boundaries (`TimeEntryCreate`, `TimeEntryResponse`, `ProjectCreate`, `ProjectResponse`) and dataclasses for internal use (`TimeEntry`, `Project`)

### Database Schema

**time_entries table:**

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT | UUID primary key |
| project_id | TEXT | FK to projects |
| description | TEXT | What was done |
| duration_minutes | INTEGER | Time spent |
| tags | TEXT | Comma-separated |
| created_at | TEXT | ISO timestamp |
| updated_at | TEXT | ISO timestamp |

**projects table:**

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT | UUID primary key |
| name | TEXT | Project name |
| description | TEXT | Project description |
| color | TEXT | Hex color for UI |
| created_at | TEXT | ISO timestamp |

### Design Decisions

- **SQLite over PostgreSQL:** Single-user tool, no server to manage.
- **No ORM:** Direct SQL keeps the data layer transparent and debuggable.
- **Pydantic for API, dataclasses for internals:** Clear boundary between external and internal data structures.
- **Service layer:** Keeps routes thin and business logic testable.

### Dependencies

From `pyproject.toml`:

**Runtime:**
- `fastapi>=0.109.0`
- `uvicorn>=0.27.0`
- `pydantic>=2.5.0`
- `python-dateutil>=2.8.0`
- `httpx>=0.25.0`

**Dev (optional):**
- `pytest>=7.4.0`, `pytest-asyncio>=0.21.0`
- `ruff>=0.1.0`, `mypy>=1.7.0`
- `coverage>=7.3.0`, `sentry-sdk>=1.39.0`

---

## 5. Git State Setup

The setup script (`examples/setup_demos.sh`) creates a self-contained git repository inside `examples/devlog/` with a carefully crafted history and dirty working state. If a `.git` directory already exists, the script removes it and starts fresh.

### The 15 Commits

All commits use the author "Demo Developer" (`dev@example.com`) with dates spread across December 1-17, 2025, to produce a realistic three-week timeline.

| # | Date | Commit Message | Files Added | Roadmap Item |
|---|------|---------------|-------------|--------------|
| 1 | Dec 01 09:00 | Initial project setup | pyproject.toml, LICENSE, .gitignore, .env.example | -- |
| 2 | Dec 01 14:30 | Create SQLite database schema with migrations | devlog/__init__.py, devlog/database.py | M1: Create SQLite database schema |
| 3 | Dec 02 10:00 | Implement TimeEntry and Project models | devlog/models.py | M1: Implement TimeEntry model, Implement Project model |
| 4 | Dec 03 11:00 | Add CRUD operations for time entries | devlog/utils/__init__.py, devlog/utils/formatting.py, devlog/utils/validation.py | M1: Add CRUD operations for time entries |
| 5 | Dec 04 09:30 | Add CRUD operations for projects | devlog/services/__init__.py, devlog/services/entries.py, devlog/services/projects.py | M1: Add CRUD operations for projects |
| 6 | Dec 05 16:00 | Write migration script for database setup | config.example.py | M1: Write migration script |
| 7 | Dec 08 09:00 | Set up FastAPI app structure | devlog/app.py, devlog/routes/__init__.py | M2: Set up FastAPI app structure |
| 8 | Dec 08 14:00 | Create time entry endpoints (CRUD) | devlog/routes/entries.py | M2: Create time entry endpoints (CRUD) |
| 9 | Dec 09 10:30 | Create project endpoints (CRUD) | devlog/routes/projects.py | M2: Create project endpoints (CRUD) |
| 10 | Dec 10 11:00 | Add input validation with Pydantic models | devlog/services/reports.py | M2: Add input validation with Pydantic |
| 11 | Dec 11 09:00 | Add error handling middleware and CLAUDE.md | CLAUDE.md | M2: Add error handling middleware |
| 12 | Dec 12 14:00 | Write API integration tests | tests/ (all test files) | M2: Write API integration tests |
| 13 | Dec 15 10:00 | Add README, architecture docs, CI workflow, and roadmap | README.md, docs/, .github/, .claude/ | -- (infrastructure) |
| 14 | Dec 16 11:30 | Add weekly summary aggregation | (empty commit) | M3: Weekly summary aggregation |
| 15 | Dec 17 15:00 | Add tag-based filtering for time entries | (empty commit) | M3: Tag-based filtering |

Commits 14 and 15 are `--allow-empty` because the implementation code was already committed in earlier commits (e.g., `reports.py` was added in commit 10). This mirrors a realistic scenario where logic is added ahead of the formal roadmap checkpoint.

### Dirty Working State

After the 15 commits, the script creates four types of uncommitted state:

| Type | File | Content |
|------|------|---------|
| **Stash** | `devlog/services/monthly.py` | WIP monthly summary stub. Created, staged, stashed with message "WIP: monthly summary aggregation (Milestone 3)", then deleted from working tree. |
| **Staged** | `devlog/utils/formatting.py` | Appended `format_percentage()` function. Added to index. |
| **Unstaged (modified)** | `devlog/utils/validation.py` | Appended `validate_project_name()` function. Not staged. |
| **Untracked** | `devlog/utils/cache.py` | New file: file-based cache utility with `get_cached()`, `set_cached()`, and `_hash_key()` functions using `/tmp/devlog_cache`. |

This combination ensures Claudetini's Git tab shows all four categories of working state, and quality gates have mixed file states to evaluate.

### Intentional Code Issues

The codebase includes deliberate issues that trigger Claudetini quality checks:

| Issue | Location | Description |
|-------|----------|-------------|
| Naive datetime | `database.py` line 84 | `datetime.now()` without timezone in migration logging |
| Naive datetime | `database.py` line 157 | `datetime.now()` in `create_project()` |
| Undocumented env vars | `validation.py` lines 11-12 | `DEVLOG_LOG_LEVEL` and `DEVLOG_SECRET_KEY` not in `.env.example` |
| Default secret key | `validation.py` line 12 | `SECRET_KEY = "dev-secret-key-change-me"` |
| Hardcoded cache path | `database.py` line 16 | `CACHE_DIR = "/tmp/devlog_cache"` |
| MD5 usage | `cache.py` line 47 | `hashlib.md5()` for key hashing |
| Missing FIXME | `services/entries.py` line 14 | `FIXME: Validate that project_id exists before creating entry` |
| Missing TODO | `routes/entries.py` line 12 | `TODO: Add pagination query parameters to list endpoint` |
| Empty Sentry DSN | `app.py` line 24 | `sentry_sdk.init(dsn="")` -- initializes with empty DSN |

---

## 6. Roadmap State

The roadmap at `.claude/planning/ROADMAP.md` contains **4 milestones with 26 total items** at approximately **54% completion** (14/26 items checked).

### Milestone 1 -- Core Data Layer (100% complete, 6/6)

All items checked. Covers database schema, models, CRUD operations, and migrations.

- [x] Create SQLite database schema
- [x] Implement TimeEntry model
- [x] Implement Project model
- [x] Add CRUD operations for time entries
- [x] Add CRUD operations for projects
- [x] Write migration script

### Milestone 2 -- API Layer (75% complete, 6/8)

Six of eight items checked. Remaining: pagination and rate limiting.

- [x] Set up FastAPI app structure
- [x] Create time entry endpoints (CRUD)
- [x] Create project endpoints (CRUD)
- [ ] Add pagination to list endpoints
- [x] Add input validation with Pydantic
- [x] Add error handling middleware
- [ ] Add rate limiting
- [x] Write API integration tests

### Milestone 3 -- Reporting & Export (25% complete, 2/7)

Two of seven items checked (weekly summary and tag filtering). Five remaining.

- [x] Weekly summary aggregation
- [ ] Monthly summary aggregation
- [ ] Markdown export for weekly reports
- [ ] CSV export for time entries
- [x] Tag-based filtering
- [ ] Date range queries with timezone support
- [ ] Project-level time totals

### Milestone 4 -- Polish & Deploy (0% complete, 0/6)

Entirely pending. Covers CLI, config file, Docker, docs, benchmarks, and user guide.

- [ ] Add CLI interface with Click
- [ ] Configuration file support (.devlog.toml)
- [ ] Docker Compose setup
- [ ] API documentation with OpenAPI
- [ ] Performance benchmarks
- [ ] User guide in docs/

### CLAUDE.md Managed Section

The managed section in `CLAUDE.md` reflects the roadmap state:

```
Overall: 14/26 items (54%)
Active: Milestone 2 (75%), Milestone 3 (25%)
Next: Remaining Milestone 2/3 items, then Milestone 4
```

This managed section is what Claudetini reads and updates automatically when reconciliation runs.

---

## 7. Claudetini Features Demonstrated

The devlog demo is designed to exercise every major Claudetini feature:

### Overview Tab
- **Progress ring** showing ~54% completion
- **Milestone card** displaying Milestone 2 as the active milestone with 2 remaining tasks
- **Quality issues** derived from readiness checks (secrets, TODOs/FIXMEs)
- **Validation list** combining health checks and quality gate results
- **Dispatch controls** for sending tasks to Claude Code

### Roadmap Tab
- **Four milestones** at 100% / 75% / 25% / 0%
- **Task-level detail** with checkbox toggle
- **Active milestone highlighting** (Milestone 2)
- **Dispatch-from-roadmap** capability for pending items

### Git Tab
- **15 unpushed commits** (no remote configured, so all commits show as local-only)
- **1 staged file** (`devlog/utils/formatting.py` with `format_percentage()`)
- **1 unstaged modified file** (`devlog/utils/validation.py` with `validate_project_name()`)
- **1 untracked file** (`devlog/utils/cache.py`)
- **1 stash entry** ("WIP: monthly summary aggregation (Milestone 3)")
- **Commit timeline** spanning Dec 1-17, 2025

### Quality Gates
- Mixed **pass/warn/fail** results from code analysis
- Readiness checks evaluating project structure, documentation, and code quality
- See [Section 10](#10-quality-gate-behavior) for detailed gate behavior

### Reconciliation Engine
- Commit messages that semantically match roadmap items (see [Section 9](#9-commit-to-roadmap-alignment))
- Both heuristic and AI-powered progress verification
- Automatic detection of completed items based on git history

### Timeline
- Three weeks of commit activity (Dec 1-17, 2025) for timeline visualization
- Natural clustering: week 1 (setup), week 2 (API), week 3 (docs + reports)

### Readiness Scorecard
- Expected score of approximately **85/100**
- Passes: CLAUDE.md present, ROADMAP.md present, .gitignore present, tests present, CI present, README present
- Warns/Fails: Undocumented env vars, default secret key, potential code issues

### Dispatch
- Task dispatch from the Overview tab's milestone card or Ask Input
- Pre-flight flow showing prompt preview and mode selection
- Queue management for multiple pending tasks

---

## 8. Setup Instructions

### Prerequisites

- Git installed and available on PATH
- Bash shell (macOS/Linux native; WSL or Git Bash on Windows)
- The Claudetini repository cloned locally

### Running Setup

From the repository root:

```bash
bash examples/setup_demos.sh
```

This script:

1. **Verifies** that all required devlog files exist in the repository
2. **Removes** any existing `.git` directory inside `examples/devlog/`
3. **Initializes** a fresh git repository on a `main` branch
4. **Configures** a local git user (`Demo Developer <dev@example.com>`)
5. **Creates 15 commits** with realistic dates, messages, and file groupings
6. **Creates a stash entry** with WIP monthly summary code
7. **Stages** a change to `formatting.py` (new `format_percentage()` function)
8. **Modifies** `validation.py` without staging (new `validate_project_name()` function)
9. **Creates** an untracked `cache.py` file

The script also sets up the `recipe-cli` beginner demo in the same run.

### What the Script Does NOT Do

- Modify `~/.claude/` (Claudetini's read-only data source policy)
- Auto-register the project in Claudetini (you do this manually)
- Install Python dependencies (manage your own virtual environment)
- Create a remote repository or push anywhere

### Registering in Claudetini

After running the setup script:

1. Start Claudetini: `cd app && npm run tauri:dev`
2. Click **Add Path** in the Project Picker
3. Select the `examples/devlog/` directory
4. The dashboard loads immediately with the full project state

### Re-running Setup

The script is idempotent. Running it again will destroy and recreate the git repository from scratch, restoring the exact same 15-commit history and dirty state. Any changes you made inside `examples/devlog/.git/` will be lost.

---

## 9. Commit-to-Roadmap Alignment

The commit messages in the setup script are intentionally crafted to closely match roadmap item descriptions. This enables Claudetini's **reconciliation engine** to automatically match git history to roadmap progress.

### Mapping Table

| Commit Message | Matched Roadmap Item | Milestone |
|---------------|---------------------|-----------|
| "Create SQLite database schema with migrations" | "Create SQLite database schema" | M1 |
| "Implement TimeEntry and Project models" | "Implement TimeEntry model" + "Implement Project model" | M1 |
| "Add CRUD operations for time entries" | "Add CRUD operations for time entries" | M1 |
| "Add CRUD operations for projects" | "Add CRUD operations for projects" | M1 |
| "Write migration script for database setup" | "Write migration script" | M1 |
| "Set up FastAPI app structure" | "Set up FastAPI app structure" | M2 |
| "Create time entry endpoints (CRUD)" | "Create time entry endpoints (CRUD)" | M2 |
| "Create project endpoints (CRUD)" | "Create project endpoints (CRUD)" | M2 |
| "Add input validation with Pydantic models" | "Add input validation with Pydantic" | M2 |
| "Add error handling middleware and CLAUDE.md" | "Add error handling middleware" | M2 |
| "Write API integration tests" | "Write API integration tests" | M2 |
| "Add weekly summary aggregation" | "Weekly summary aggregation" | M3 |
| "Add tag-based filtering for time entries" | "Tag-based filtering" | M3 |

### What This Means for Reconciliation

- **Heuristic matching** uses substring and keyword overlap to link commits to items. The close textual similarity between commit messages and roadmap item descriptions produces high-confidence matches.
- **AI-based matching** can additionally identify that commit 3 ("Implement TimeEntry and Project models") covers two separate roadmap items.
- Commits 1 and 13 ("Initial project setup" and "Add README, architecture docs...") are infrastructure commits that do not match any roadmap item. These appear as unmatched commits in the reconciliation view.
- The reconciliation engine should confirm that all 14 checked items in the roadmap have corresponding commits, validating the 54% progress figure.

---

## 10. Quality Gate Behavior

Claudetini runs several quality gates against the devlog project. Below is the expected behavior for each category.

### Readiness Checks (Scorecard)

| Check | Expected Result | Reason |
|-------|----------------|--------|
| CLAUDE.md present | PASS | File exists at project root |
| ROADMAP.md present | PASS | File exists at `.claude/planning/ROADMAP.md` |
| .gitignore present | PASS | File exists at project root |
| README.md present | PASS | File exists at project root |
| Tests present | PASS | `tests/` directory with 6 test modules |
| CI configured | PASS | `.github/workflows/ci.yml` exists |
| Git initialized | PASS | Repository with 15 commits |
| Env config audit | WARN | `DEVLOG_LOG_LEVEL` and `DEVLOG_SECRET_KEY` in `validation.py` are not documented in `.env.example` |
| Secrets scan | WARN | Default secret key `"dev-secret-key-change-me"` in `validation.py` |

### Code Quality Gates

| Gate | Expected Result | Reason |
|------|----------------|--------|
| Lint (Ruff) | PASS/WARN | Code follows PEP 8; minor issues possible depending on ruff version |
| Type check (mypy) | WARN | Some functions lack full type annotations; naive datetime usage |
| TODO/FIXME scan | WARN | `FIXME` in `services/entries.py`, `TODO` in `routes/entries.py` and `app.py` |
| Test presence | PASS | 6 test modules covering models, database, routes, services, reports |

### Security-Related Checks

| Check | Expected Result | Reason |
|-------|----------------|--------|
| Hardcoded secrets | WARN | `SECRET_KEY = "dev-secret-key-change-me"` in `validation.py` |
| .env exposure | PASS | `.env` is in `.gitignore`; only `.env.example` is committed |
| API key scan | PASS | No hardcoded API keys (unlike the `recipe-cli` demo) |

### Uncommitted Changes Gate

| Check | Expected Result | Reason |
|-------|----------------|--------|
| Working tree clean | FAIL | 1 staged + 1 modified + 1 untracked file |

### Overall Expected Score

Approximately **85/100** on the readiness scorecard. The project has strong structural hygiene (CLAUDE.md, ROADMAP, tests, CI, README, .gitignore all present) but loses points for the undocumented env vars, default secret key, and uncommitted working state.

---

## 11. Expected User Experience

This section walks through what a user will see when they register the devlog project and explore each Claudetini tab.

### Project Picker

After registering `examples/devlog/`, the project picker shows:

- **Project name:** devlog
- **Branch:** main
- **Readiness score:** ~85 (green ring)
- **Progress:** ~54% (14/26 items)
- **Last commit:** "Add tag-based filtering for time entries" (Dec 17, 2025)

### Overview Tab

The landing view after selecting the project:

- **Progress Hero** displays a progress ring at ~54%, project name "devlog", 14/26 items complete across 4 milestones, with the README summary ("A developer time-tracking API built with FastAPI and SQLite").
- **Branch Bar** shows `main` branch with "3 uncommitted" indicator (staged + modified + untracked). No remote configured, so no push/pull indicators.
- **Milestone Card** highlights **Milestone 2 -- API Layer** as the active milestone (first milestone with incomplete items). The two remaining tasks ("Add pagination to list endpoints" and "Add rate limiting") are listed with dispatch controls. The first pending task is highlighted as "Up next".
- **Quality Issues** section shows warnings for the undocumented env vars and the default secret key.
- **Validation List** shows a mix of pass (ROADMAP, CLAUDE.md, tests, CI) and warn (secrets, TODOs) indicators.
- **Recent Sessions** will be empty (no Claude Code sessions have been run against this demo project yet).

### Roadmap Tab

Displays all four milestones in a vertical list:

- **Milestone 1 -- Core Data Layer:** Full green progress bar, 6/6 items, all checked. Collapsed by default since it is complete.
- **Milestone 2 -- API Layer:** 75% progress bar, 6/8 items. Two unchecked items ("Add pagination to list endpoints", "Add rate limiting") are visible and dispatchable. This is the active milestone.
- **Milestone 3 -- Reporting & Export:** 25% progress bar, 2/7 items. Five unchecked items visible, including "Monthly summary aggregation" (which has a corresponding stash entry).
- **Milestone 4 -- Polish & Deploy:** Empty progress bar, 0/6 items. All items unchecked.

Users can click any unchecked item to expand it, view or edit the dispatch prompt, and send it to Claude Code.

### Git Tab

Shows a rich view of the repository state:

- **Commit History:** 15 commits in reverse chronological order, from "Add tag-based filtering" (Dec 17) back to "Initial project setup" (Dec 1). All commits are local-only (no remote).
- **Staged Changes:** `devlog/utils/formatting.py` -- the appended `format_percentage()` function.
- **Unstaged Changes:** `devlog/utils/validation.py` -- the appended `validate_project_name()` function.
- **Untracked Files:** `devlog/utils/cache.py` -- the new cache utility file.
- **Stash:** One entry: "WIP: monthly summary aggregation (Milestone 3)".

This demonstrates every category of git working state that Claudetini can display and manage.

### Quality Gates Tab

Displays gate results grouped by category:

- **Passed gates** appear with green checkmarks (ROADMAP presence, test presence, CI, .gitignore, CLAUDE.md, README).
- **Warning gates** appear with yellow indicators (env config audit, default secret key, TODO/FIXME items).
- **Failed gates** appear with red indicators (uncommitted changes in working tree).

Users can click any gate to see its details, including file locations and suggested fixes.

### Logs Tab

Initially empty since no Claude Code sessions have been run. After dispatching a task from the Overview or Roadmap tab, session logs will appear here with:

- Exchange history (user prompts and assistant responses)
- Token counts and cost
- Modified files
- Duration

### Settings Tab

Default settings apply. Users can configure:

- Dispatch mode (standard, with-review, full-pipeline, blitz)
- Usage mode (subscription vs. API)
- Preferred fallback provider
- Auto-dispatch toggle
- Reconciliation confidence threshold

### Timeline

Displays the three-week commit history as a visual timeline:

- **Week 1 (Dec 1-5):** Foundation work -- project setup, database, models, CRUD (6 commits)
- **Week 2 (Dec 8-12):** API layer -- FastAPI, routes, validation, tests (6 commits)
- **Week 3 (Dec 15-17):** Documentation and reporting (3 commits)

The natural clustering provides a realistic development cadence that resembles actual project work.

### Reconciliation

Users can trigger reconciliation from the Overview tab's "Verify Progress" or "AI Verify Progress" buttons:

- **Heuristic verification** scans the 15 commit messages against the 26 roadmap items and produces high-confidence matches for the 14 completed items.
- **AI verification** provides deeper analysis, identifying multi-item commits (e.g., commit 3 covering both TimeEntry and Project models).
- The reconciliation modal shows matched items with confidence scores, unmatched commits, and any discrepancies between the roadmap's checked state and what the git history supports.
- The reconciliation footer appears at the bottom of the dashboard when matches are found, offering to update the roadmap.

### Dispatch

Users can dispatch tasks to Claude Code from multiple surfaces:

- **Ask Input** on the Overview tab -- type a free-form task description
- **Milestone card "Start"/"Run" buttons** -- dispatch a specific roadmap task
- **Roadmap tab item expansion** -- dispatch with an AI-generated or custom prompt
- **Quality issue "Fix" buttons** -- dispatch a fix for a detected issue

The pre-flight interstitial shows the prompt, selected mode, and estimated cost before confirming.

---

## Appendix: Notable Code Patterns

### Pydantic + Dataclass Separation

The `models.py` file demonstrates a deliberate dual-model pattern:

```python
# API boundary (Pydantic)
class TimeEntryCreate(BaseModel):
    project_id: str
    description: str = Field(..., min_length=1, max_length=500)
    duration_minutes: int = Field(..., gt=0, le=1440)
    tags: list[str] = Field(default_factory=list)

# Internal representation (dataclass)
@dataclass
class TimeEntry:
    id: str = field(default_factory=lambda: str(uuid4()))
    project_id: str = ""
    description: str = ""
    duration_minutes: int = 0
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

### Test Fixtures

The `conftest.py` provides an auto-use `test_db` fixture that creates a temporary SQLite database for each test, ensuring test isolation:

```python
@pytest.fixture(autouse=True)
def test_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    database.init_db(db_path)
    yield db_path
    database.close_db()
```

### FastAPI Lifespan

The `app.py` uses the modern async context manager lifespan pattern:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
    close_db()
```
