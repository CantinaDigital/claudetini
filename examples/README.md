# Claudetini Demo Projects

Two curated demo projects that let you see every Claudetini feature in action — no existing project required.

## Quick Start

```bash
# From the repo root
bash examples/setup_demos.sh
```

Then open Claudetini and register either project.

---

## The Two Projects

### 1. `recipe-cli` — Beginner: "Fix My Project"

A simple Python CLI that searches recipes by ingredient. ~8 files, ~400 lines.

**Start here if you're new to Git and Claude Code.** This project has no git repo, no documentation, and a hardcoded API key. The included `GETTING_STARTED.md` walks you through setting up git, connecting to GitHub, and watching your Claudetini readiness score climb from ~10 to 90+.

**What you'll see:**
- Readiness Scorecard starting at ~10/100 (everything red)
- Secrets Scanner catching a hardcoded `AKIA...` key and exposed `.env` file
- Bootstrap Wizard generating CLAUDE.md, ROADMAP.md, and .gitignore
- Git Tab learning experience (staged vs unstaged vs untracked)
- Score climbing as you fix each issue

**Register it:** Open Claudetini → Add Path → select `examples/recipe-cli/`

---

### 2. `devlog` — Intermediate: "Full Dashboard Experience"

A Python FastAPI app for tracking developer work logs. ~20 files, ~1200 lines.

**Start here if you already know Git** and want to see the full Claudetini dashboard in action. This project is properly set up with a roadmap at ~55% progress, quality gates with mixed results, and real git state.

**What you'll see:**
- Overview Tab with progress ring, milestone cards, and validation list
- Roadmap Tab with 4 milestones at 100% / 75% / 25% / 0%
- Git Tab with unpushed commits, uncommitted files, and a stash entry
- Quality Gates with mixed pass/warn/fail results
- Readiness Scorecard at ~85/100
- Reconciliation Engine matching commits to roadmap items

**Register it:** Open Claudetini → Add Path → select `examples/devlog/`

---

## What the Setup Script Does

- **recipe-cli:** Verifies files are in place. Does NOT init git — that's your job (the walkthrough guides you).
- **devlog:** Initializes a git repo with ~15 realistic commits, creates dirty working state (uncommitted changes, untracked file, stash entry).

**What it does NOT do:**
- Modify `~/.claude/` (Claudetini's read-only policy)
- Auto-register projects (you do this in the app)
- Install Python dependencies (you manage your own venv)

---

## Suggested Order

1. Start with **recipe-cli** if you're new to Git/GitHub/Claude Code
2. Follow the `GETTING_STARTED.md` walkthrough end-to-end
3. Then switch to **devlog** to explore the full dashboard
4. Try dispatching tasks, running quality gates, and viewing the roadmap
