# Claudetini Documentation

> Last updated: 2026-02-17

Claudetini is a Tauri desktop dashboard for Claude Code projects. It eliminates session amnesia and enforces development best practices by reading Claude Code's existing data artifacts (`~/.claude/`) to give developers persistent project awareness.

**Tech Stack:** Tauri 2 (Rust) + React 19 + TypeScript + Vite 7 + Tailwind CSS 3.4 + Python FastAPI sidecar + Zustand 5

---

## Table of Contents

### Core Documentation

| Document | Description |
|----------|-------------|
| [Architecture](ARCHITECTURE.md) | System architecture, component boundaries, and communication patterns |
| [API Reference](API.md) | Python FastAPI sidecar endpoint reference |
| [Core Modules](CORE-MODULES.md) | Python business logic modules in `src/core/` |
| [Data Flows](DATA-FLOWS.md) | Data flow diagrams and pipeline descriptions |
| [Design System](DESIGN-SYSTEM.md) | Color tokens, typography, spacing, and UI primitives |
| [State Management](STATE-MANAGEMENT.md) | Zustand stores, domain managers, and persistence |
| [Feature Catalog](FEATURES.md) | Complete feature inventory and capability matrix |
| [Frontend Architecture](FRONTEND.md) | React app structure, component catalog, hooks, and API client |

### View Documentation

Per-view documentation lives in [`views/`](views/):

| View | Description |
|------|-------------|
| [Overview](views/overview.md) | Main dashboard with project hero, milestone card, and live feed |
| [Roadmap](views/roadmap.md) | Milestone list, item actions, and suggestion cards |
| [Git](views/git.md) | Git status, staging, commit, and push operations |
| [Quality Gates](views/gates.md) | Gate definitions, execution, and results display |
| [Dispatch](views/dispatch.md) | Claude Code CLI dispatch with streaming output |
| [Parallel Execution](views/parallel-execution.md) | Multi-agent parallel task execution and branch merging |
| [Overlays](views/overlays.md) | Pre-flight, session report, and milestone plan review overlays |
| [Settings](views/settings.md) | User preferences, hooks, and provider configuration |
| [Logs](views/logs.md) | Log entry viewer with filtering |
| [Timeline](views/timeline.md) | Session timeline with commit correlation |
| [Scorecard](views/scorecard.md) | Project readiness scorecard with scoring rings |
| [Bootstrap](views/bootstrap.md) | Multi-step project setup wizard |
| [Project Picker](views/project-picker.md) | Project list, registration, and selection |
| [Reconciliation](views/reconciliation.md) | Post-session roadmap reconciliation workflow |

### Demo Projects

| Document | Description |
|----------|-------------|
| [Recipe CLI Demo](views/recipe-cli-demo.md) | Beginner demo (recipe-cli) |
| [Devlog Demo](views/devlog-demo.md) | Intermediate demo (devlog) |

### Testing

| Document | Description |
|----------|-------------|
| [Test Fixtures](test-fixtures.md) | Test fixture projects |

---

## Quick Start

```bash
# Run the full Tauri desktop app (frontend + backend)
cd app && npm run tauri:dev

# Run just the Python FastAPI sidecar (port 9876)
cd app && npm run backend

# Run just the React dev server
cd app && npm run dev

# Run Python tests
pytest

# Linting and type checking
ruff check src/
mypy src/
```

---

## Architecture Summary

```
+----------------------------------------------------------+
|                    Tauri 2 Desktop Shell                  |
|  +----------------------------------------------------+  |
|  |              React 19 + Vite 7 Frontend            |  |
|  |                                                    |  |
|  |   +-----------+  +---------+  +----------------+   |  |
|  |   | AppRouter |->| TabBar  |->| Dashboard Tabs |   |  |
|  |   +-----------+  +---------+  +----------------+   |  |
|  |        |                           |               |  |
|  |   +-----------+            +---------------+       |  |
|  |   | Screens:  |            | Overlays:     |       |  |
|  |   | Picker    |            | Dispatch      |       |  |
|  |   | Scorecard |            | Parallel Exec |       |  |
|  |   | Bootstrap |            | PreFlight     |       |  |
|  |   +-----------+            | Reconciliation|       |  |
|  |        |                   +---------------+       |  |
|  |   +--------------------------------------------+   |  |
|  |   |        Zustand Domain Managers             |   |  |
|  |   | projectManager | dispatchManager | git ... |   |  |
|  |   +--------------------------------------------+   |  |
|  +----------------------------------------------------+  |
|        | HTTP REST + SSE (port 9876)                     |
|  +----------------------------------------------------+  |
|  |           Python FastAPI Sidecar                   |  |
|  |                                                    |  |
|  |   +------------+  +------------+  +------------+   |  |
|  |   | src/core/  |  | src/agents/|  | Endpoints  |   |  |
|  |   | roadmap    |  | dispatcher |  | /api/...   |   |  |
|  |   | timeline   |  | gates      |  |            |   |  |
|  |   | health     |  | executor   |  |            |   |  |
|  |   | git_utils  |  |            |  |            |   |  |
|  |   +------------+  +------------+  +------------+   |  |
|  +----------------------------------------------------+  |
|        | Reads (read-only)                               |
|  +----------------------------------------------------+  |
|  |   ~/.claude/ (session logs, todos, settings)       |  |
|  +----------------------------------------------------+  |
+----------------------------------------------------------+
```

**Data flow:** The React frontend communicates with the Python sidecar over HTTP REST and SSE on port 9876. The sidecar reads Claude Code data from `~/.claude/` (read-only) and stores runtime data at `~/.claudetini/`. Zustand domain managers handle client-side state with localStorage persistence where needed.
