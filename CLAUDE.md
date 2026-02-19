# Claudetini Development Guide

> A desktop dashboard for Claude Code projects that eliminates session amnesia and enforces development best practices.

## Project Overview

Claudetini is a Tauri desktop application with a React frontend and Python FastAPI sidecar. It reads Claude Code's existing data artifacts (~/.claude/) to give developers persistent project awareness.

**Tech Stack:**
- **Desktop Shell:** Tauri 2 (Rust)
- **Frontend:** React 19 + TypeScript + Vite + Tailwind CSS
- **Backend:** Python 3.11+ FastAPI sidecar (port 9876)
- **State:** Zustand
- **Core Logic:** Python modules in `src/core/`

## Architecture

```
claudetini/                      # Monorepo root
├── src/core/                       # Shared Python business logic
│   ├── roadmap.py                  # Roadmap parsing, progress tracking
│   ├── timeline.py                 # Session timeline builder
│   ├── health.py                   # Project health checks
│   ├── git_utils.py                # Git operations
│   ├── plan_scanner.py             # 7-tier plan detection
│   ├── secrets_scanner.py          # Security scanning
│   └── ...                         # 30+ core modules
├── src/agents/                     # Claude Code integration
│   ├── dispatcher.py               # Claude Code CLI dispatch
│   ├── gates.py                    # Quality gate definitions
│   └── executor.py                 # Gate execution engine
├── tests/                          # Shared test suite
└── app/              # Tauri desktop application
    ├── src/                        # React frontend
    ├── src-tauri/                  # Tauri Rust shell
    └── python-sidecar/             # FastAPI backend
```

## Design Philosophy: Intelligence, Not Dashboards

A view that presents raw data is not intelligence. Intelligence means: "here's what matters, here's what's getting worse, here's where to focus." Build a dashboard, not a database browser.

## Code Conventions

### Python (src/core/, src/agents/, python-sidecar/)
- Follow PEP 8
- Use type hints for all function signatures
- Use `pathlib.Path` over `os.path` for file operations
- Prefer f-strings for string formatting
- Use dataclasses or Pydantic models for data structures

### TypeScript/React (app/src/)
- See `app/CLAUDE.md` for frontend conventions

### Naming
- snake_case for Python functions, variables, modules
- camelCase for TypeScript functions, variables
- PascalCase for classes and React components
- SCREAMING_SNAKE_CASE for constants

### Error Handling
- Raise specific exceptions, not generic `Exception`
- Always provide meaningful error messages
- Gracefully handle missing Claude Code data files

### Testing
- Tests live in `tests/` directory
- Use pytest for Python tests
- Aim for 70%+ coverage on core modules
- Mock external dependencies (file system, subprocess)

## Data Sources

Claudetini reads from these Claude Code locations:

| Data | Location | Format |
|------|----------|--------|
| Session logs | `~/.claude/projects/<hash>/<session>.jsonl` | JSONL |
| Session memory | `~/.claude/projects/<hash>/<session>/session-memory/summary.md` | Markdown |
| Todos | `~/.claude/todos/{session-id}-*.json` | JSON |
| Settings | `~/.claude/settings.json` | JSON |

**Important:** Claudetini is READ-ONLY for Claude Code data. Never modify files in `~/.claude/`.

## Runtime Data (Do Not Touch)

Claudetini stores per-project runtime data at `~/.claudetini/projects/<hash>/`. This includes:
- `dispatch-output/*.log` — Logs from Claude CLI dispatches
- `intelligence-cache.json` — Cached scan results
- `.system-prompt.md` — Generated system prompts
- `prompts/` — Project-specific prompt templates

**These are runtime artifacts, not source code.** Do not read, modify, or rely on them during development of the app itself. They are generated and managed by the running application for the projects it manages (beginner demo projects, user projects, etc.).

Similarly, example/demo projects in the repo (e.g., `tests/fixtures/projects/`) are test fixtures — not part of the application source.

## Planning & Progress Tracking

**Source of Truth:** `.claude/planning/ROADMAP.md`

1. All tasks tracked in ROADMAP.md with checkbox format
2. Mark items `[x]` when complete
3. Add new tasks under appropriate milestones
4. Keep managed section below in sync with ROADMAP state

**IMPORTANT:** Do NOT create stray planning documents (PLAN.md, TODO.md, etc.) anywhere in the repo. All planned features, implementation tasks, and future development work MUST be added to the master roadmap at `.claude/planning/ROADMAP.md`. Add new milestones or items to existing milestones as needed.

## Commands

```bash
# Run the Tauri app (frontend + backend)
cd app && npm run tauri:dev

# Run just the Python sidecar
cd app && npm run backend

# Run just the React dev server
cd app && npm run dev

# Run Python tests
pytest

# Run linting
ruff check src/

# Type checking
mypy src/
```

## Dependencies

**Python Core (pyproject.toml):**
- gitpython>=3.1.40
- watchdog>=3.0.0

**Python Sidecar (python-sidecar/pyproject.toml):**
- fastapi>=0.109.0
- uvicorn>=0.27.0
- pydantic>=2.5.0

**Frontend (package.json):**
- react@19, @tauri-apps/api@2, zustand@5, tailwindcss@3.4

<!-- claudetini:managed -->
## Current Status
- Active branch: main
- Last updated: 2026-02-19

## What's In Progress
- Roadmap audit complete — false completions corrected, 14 items pruned

## What's Next
- M10: Sidecar auto-start (10.4) and Python bundling (10.5) — blocks shipping
- M6: Switch Project (6.5) and screen persistence (6.6)
- M7: Project dropdown in dashboard (7.1, 7.2)
- M5: Fix bootstrap error recovery (5.5)
- M12: Polish dispatch success/failure UX (12.9)
- M11: Replace 163 inline styles (11.3), full-width layouts (11.4, 11.5)
- M8: Auto-discovery presentation (8.4), dedup (8.5)
- M10: Auto-update (10.6), release workflow (10.7)

## Progress
- Overall: 97/112 items (87%) — corrected from falsely reported 88%
<!-- /claudetini:managed -->
