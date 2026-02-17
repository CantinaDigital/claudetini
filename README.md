# Claudetini

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![Node](https://img.shields.io/badge/node-18+-green.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-alpha-orange.svg)

A desktop dashboard for Claude Code projects. Set up projects the right way, track what happened across sessions, and keep everything healthy — without memorizing terminal commands.

---

## What It Does

**If you're new to Claude Code:** Claudetini walks you through project setup. It generates your CLAUDE.md, roadmap, .gitignore, and architecture docs so you don't have to figure out what goes where.

**If you're already using Claude Code:** Claudetini gives you a persistent overview of everything Claude did across sessions — timeline, roadmap progress, git status, and quality checks — in one window that doesn't forget.

### Core Features

- **Bootstrap Wizard** — Guided project setup that analyzes your codebase and generates CLAUDE.md, ROADMAP.md, ARCHITECTURE.md, and .gitignore. Shows a cost estimate before running anything.
- **Readiness Scorecard** — 12-point assessment (0-100) covering git setup, documentation, test coverage, security, and dependency management. Shows exactly what's missing and how to fix it.
- **Visual Roadmap** — Parses your ROADMAP.md into interactive milestone cards with progress bars and task checkboxes. Reconciles with git state automatically.
- **Session Timeline** — Browse every Claude Code session, see what was done, and read session memory summaries. Live feed when sessions are active.
- **Quality Gates** — Automated checks for tests, linting (Ruff), type checking (MyPy), and security scanning. Run them before you push.
- **Git Integration** — Commit history, branch status, unpushed changes, and dirty state detection at a glance.
- **Dispatch Queue** — Run Claude Code tasks from the dashboard with live output streaming and post-task reconciliation.

---

## Use Cases

### "I just installed Claude Code and I have no idea what I'm doing"

You've got a side project — maybe a Python CLI tool or a React app — and you heard Claude Code can help you build it faster. But you open the terminal, type `claude`, and realize you don't know what a `CLAUDE.md` is, what a roadmap should look like, or how to give Claude context about your project.

**With Claudetini:**
1. Open the app and point it at your project folder
2. The **Readiness Scorecard** instantly tells you what's missing — no CLAUDE.md, no .gitignore, no roadmap, no tests
3. Click **Bootstrap** and Claudetini analyzes your codebase, then generates a CLAUDE.md (project instructions for Claude), a ROADMAP.md (your task plan), and a .gitignore — all tailored to your actual code
4. Now when you open Claude Code, it already knows your project's tech stack, conventions, and what to work on next

*You skip the "first 10 sessions of figuring out how to set things up" phase entirely.*

---

### "I use Claude Code daily but I keep losing context between sessions"

You're building a full-stack app. Monday's session added authentication. Tuesday's session refactored the database layer. Wednesday you come back and can't remember what state things are in — which tasks are done, what's left, whether Tuesday's session even committed cleanly.

**With Claudetini:**
1. Open the dashboard and check the **Session Timeline** — every session is listed with what was done, when, and the session memory summary
2. Glance at the **Visual Roadmap** — milestone progress bars show exactly where you are. 14 of 23 tasks done on Milestone 3, all green
3. The **Git Tab** shows your last commit was Tuesday at 11pm, you're on the right branch, and there are no unpushed changes
4. Pick up right where you left off — no archaeology required

*You stop wasting the first 10 minutes of every session figuring out what happened last time.*

---

### "I'm working on a team project and code quality keeps slipping"

You and two other developers are using Claude Code on the same repo. Sometimes Claude generates code that doesn't pass linting. Sometimes commits go up without tests. Nobody checks for hardcoded secrets until it's too late.

**With Claudetini:**
1. Before pushing, run **Quality Gates** — automated checks for linting (Ruff), type safety (MyPy), test coverage, and security scanning
2. The **Readiness Scorecard** flags that test coverage dropped below 70% and your .env file isn't in .gitignore
3. The **Secrets Scanner** catches an API key that got committed three sessions ago
4. Fix the issues, re-run gates, push clean code

*Quality problems get caught locally before they become PR review comments or production incidents.*

---

### "I juggle multiple Claude Code projects and need a command center"

You're a freelancer or a power user running 3-5 projects simultaneously. Each project has its own roadmap, its own Claude sessions, its own git state. Switching between them in the terminal means mental context-switching every time.

**With Claudetini:**
1. The **Project Picker** lists all your Claude Code projects with their health scores at a glance
2. Switch to Project B — the dashboard loads its roadmap (Milestone 2, 80% done), its session timeline, and its git status instantly
3. You notice Project B has 3 unpushed commits and a failing gate — fix that before jumping to Project C
4. The **Dispatch Queue** lets you kick off a Claude Code task on Project C while you review Project B's timeline

*One window replaces five terminal tabs and the mental overhead of tracking project state in your head.*

---

### "I want Claude Code to follow a structured development process, not just freestyle"

You've seen what Claude Code can do, but you've also seen it go off the rails — skipping tests, making unnecessary refactors, ignoring your architecture. You want guardrails without micromanaging every prompt.

**With Claudetini:**
1. **Bootstrap** generates a CLAUDE.md with your project's conventions, naming standards, and architecture rules — Claude reads this automatically every session
2. Your **ROADMAP.md** breaks work into milestones and tasks with clear scope — Claude knows what to work on and what's out of bounds
3. **Quality Gates** enforce your standards after every change — tests must pass, linting must be clean, no secrets in the codebase
4. The **Reconciliation Engine** cross-references your roadmap with actual git commits so tasks don't get marked "done" unless the code actually shipped

*You get a structured development workflow where Claude Code operates within defined guardrails, not a blank canvas where anything goes.*

---

### "I want to understand what Claude Code actually did in my codebase"

Claude Code ran for 45 minutes while you were in a meeting. It said it "completed the authentication system." But what does that actually mean? What files changed? Did it follow your patterns? Did it break anything?

**With Claudetini:**
1. Open the **Session Timeline** and click on that session — see the full summary of what Claude did, what files it touched, and what decisions it made
2. Check the **Git Tab** — see the exact commits, diffs, and branch state from that session
3. Run **Quality Gates** — instantly verify that tests still pass, linting is clean, and no security issues were introduced
4. Check the **Roadmap** — see which tasks Claude marked as complete and whether that matches what actually happened

*You get full visibility into AI-assisted development instead of trusting a one-line summary.*

---

## Demo Projects

Want to see Claudetini in action without setting up your own project first? Two curated demo projects are included in `examples/`:

| Project | Level | What You'll See |
|---------|-------|----------------|
| **recipe-cli** | Beginner | Readiness score starting at ~10/100, secrets scanner catching hardcoded keys, step-by-step git + GitHub walkthrough |
| **devlog** | Intermediate | Full dashboard with 4-milestone roadmap at ~55%, quality gates, git state with unpushed commits and stash |

```bash
# Set up the demos
bash examples/setup_demos.sh

# Then open Claudetini and register examples/recipe-cli/ or examples/devlog/
```

See [`examples/README.md`](examples/README.md) for details.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Node.js** | 18+ | For the React frontend |
| **Python** | 3.11+ | For the backend sidecar and core logic |
| **Rust** | latest stable | For the Tauri desktop shell |
| **Claude Code** | latest | [Install from Anthropic](https://docs.anthropic.com/en/docs/claude-code/overview) |

### System Requirements

- **macOS** (primary platform)
- **Linux** (supported)
- **Windows** (coming soon)

### Recommended

- Git installed and configured
- A Claude Code project already initialized (or let Bootstrap create one)

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/cantina-digital/claudetini.git
cd claudetini
```

### 2. Install Python dependencies

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

### 3. Install frontend dependencies

```bash
cd app
npm install
```

### 4. Install Tauri CLI (if not already installed)

```bash
cargo install tauri-cli
```

---

## Usage

### Full Desktop App (Recommended)

```bash
cd app
npm run tauri:dev
```

This starts the Python backend (port 9876), Vite dev server (port 1420), and the Tauri desktop window. First build takes 2-3 minutes for Rust compilation.

### Browser Mode (For Development)

**Terminal 1 — Backend:**
```bash
cd app
npm run backend
```

**Terminal 2 — Frontend:**
```bash
cd app
npm run dev
```

Open http://localhost:5173 in your browser.

### Backend Only

```bash
cd app
npm run backend
```

The FastAPI sidecar runs on http://127.0.0.1:9876. Useful for testing API endpoints directly.

### Bootstrap CLI (Headless)

```bash
# Bootstrap a project
python -m src.agents.bootstrap_cli ~/my-project

# See cost estimate first
python -m src.agents.bootstrap_cli ~/my-project --estimate-cost

# Dry run (no changes)
python -m src.agents.bootstrap_cli ~/my-project --dry-run
```

---

## How It Works

Claudetini reads your existing Claude Code data from `~/.claude/` — session logs, memory files, and todos. It never modifies those files.

```
You open Claudetini
    |
    v
Project Picker — select or add a project
    |
    v
Readiness Scan — 12-point health check runs automatically
    |
    v
Scorecard — see what's good, what's missing, what's critical
    |
    v
Bootstrap (optional) — generate missing docs with AI assistance
    |
    v
Dashboard — roadmap, timeline, git, gates, logs, all in one place
```

### Architecture

```
claudetini/
├── src/core/              # Python business logic (30+ modules)
│   ├── readiness.py       # 12-point scoring engine
│   ├── roadmap.py         # ROADMAP.md parser and tracker
│   ├── timeline.py        # Session timeline builder
│   ├── git_utils.py       # Git operations
│   ├── reconciliation.py  # Roadmap-git state sync
│   ├── secrets_scanner.py # Security scanning
│   └── ...
├── src/agents/            # Claude Code integration
│   ├── bootstrap_engine.py
│   ├── dispatcher.py
│   └── gates.py
├── app/     # Desktop application
│   ├── src/               # React 19 + TypeScript frontend
│   ├── src-tauri/         # Tauri 2 Rust shell
│   └── python-sidecar/    # FastAPI backend (port 9876)
└── tests/                 # Pytest suite
```

**Tech Stack:** Tauri 2 (Rust) | React 19 + TypeScript | Tailwind CSS | Python FastAPI | Zustand | Vite

---

## Available Commands

| Command | Description |
|---------|-------------|
| `npm run tauri:dev` | Full desktop app (backend + frontend + Tauri) |
| `npm run dev:all` | Backend + frontend without Tauri window |
| `npm run dev` | Frontend dev server only |
| `npm run backend` | Python FastAPI sidecar only |
| `npm run build` | Production build |
| `npm run kill-ports` | Kill stuck processes on dev ports |
| `pytest` | Run Python test suite |
| `ruff check src/` | Lint Python code |
| `mypy src/` | Type check Python code |

All frontend commands run from `app/`.

---

## Contributing

We're running a **Launch Bounty** to kick off the community:

- **$60 — Best Pull Request.** Feature, bug fix, or UI improvement. Most valuable contribution wins.
- **$100 — Best Code Review.** Constructive feedback on other people's PRs. Catch bugs, suggest improvements, improve code quality.

See [CONTRIBUTING.md](CONTRIBUTING.md) for full rules, how to vote, and how to participate.

### Quick Start for Contributors

```bash
git clone https://github.com/cantina-digital/claudetini.git
cd claudetini
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
cd app && npm install
npm run tauri:dev
```

---

## FAQ

### How is this different from the Claude Code dashboard in the Claude desktop app?

They solve different problems. The Claude desktop app's Claude Code section is an interface for running Claude Code conversations. Claudetini is a **project management layer** that sits on top of your Claude Code data:

- **Session persistence** — Claude Code sessions are ephemeral. Claudetini reads your session history and gives you a timeline of everything that happened across all sessions, even after they're gone.
- **Project health** — There's no built-in way to see if your project has proper docs, tests, git hygiene, and security practices. Claudetini scores this and tells you exactly what's missing.
- **Bootstrap automation** — If you don't know what a CLAUDE.md should contain or what a good roadmap looks like, Claudetini generates them for you based on your actual codebase.
- **Roadmap tracking** — Claude Code doesn't track progress across sessions. Claudetini parses your ROADMAP.md, shows milestone progress, and reconciles it with your git history.
- **Quality gates** — Automated pre-push checks for linting, type safety, tests, and security scanning, configured per-project.

Think of it this way: Claude Code is where you do the work. Claudetini is where you see the big picture.

### Do I need to know how to use the terminal?

For basic usage, no. The desktop app handles everything through the GUI — project selection, health scanning, bootstrapping, and dashboard browsing. You'll only need the terminal for installation and starting the app.

### Does this modify my Claude Code data?

No. Claudetini is strictly read-only for anything in `~/.claude/`. It reads session logs, memory files, and todos but never writes to them. The only files it creates are in your project directory (CLAUDE.md, ROADMAP.md, etc.) during bootstrap, and only when you explicitly ask it to.

### How much does the bootstrap cost?

The bootstrap wizard shows you a cost estimate before running. Typical projects cost $0.30-0.50 in Claude API usage. You can also do a dry run to see what would be generated without spending anything.

### Does it work with existing projects?

Yes. Point it at any directory and the readiness scanner will assess its current state. The bootstrap wizard only generates files that are missing — it won't overwrite existing CLAUDE.md or ROADMAP.md files.

### What data does Claudetini collect?

None. Everything runs locally on your machine. There are no analytics, no telemetry, and no network calls except to the Claude API during bootstrap (which runs through your own Claude Code installation).

### I found a bug / I have a feature idea

[Open an issue](https://github.com/cantina-digital/claudetini/issues) on GitHub. If you want to fix it yourself, check the [contributing guide](CONTRIBUTING.md) — there's bounty money on the table.

---

## Troubleshooting

### Backend not connecting

```bash
# Check if port 9876 is in use
lsof -i :9876

# Kill stuck processes
cd app && npm run kill-ports

# Restart backend
npm run backend
```

### Module not found errors

```bash
# Install Python dependencies
pip install -e ".[dev]"

# Install sidecar dependencies
cd app/python-sidecar && pip install -e .
```

### Tauri build fails

Make sure Rust is installed and up to date:
```bash
rustup update
```

On macOS, you may also need Xcode command line tools:
```bash
xcode-select --install
```

### Bootstrap hangs

- Verify Claude Code is installed: `claude --version`
- Verify Claude Code is authenticated: `claude --help`
- Try with a smaller test project first

---

## License

MIT. See [LICENSE](LICENSE) for details.
