# Contributing to Claudetini

Thanks for checking out the project. Whether you're here to build, review, or just poke around — welcome.

## Launch Bounties ($160)

I'm putting up my own money to kick off the community. Two prizes, two weeks from launch.

### Best Pull Request ($60)

Add a feature, fix a bug, or improve the UI. The contribution that adds the most value wins.

- Code must run and pass existing tests
- PR must be mergeable against `main`
- Community votes (thumbs-up on the PR) factor into the decision

### Best Code Review ($100)

This is the bigger prize on purpose. Good reviews make everyone's code better.

- Leave constructive, technical feedback on other people's PRs
- Catch bugs, suggest improvements, flag security issues
- Community votes (thumbs-up on review comments) factor into the decision

### How Voting Works

- **For PRs:** Browse [Pull Requests](https://github.com/cantina-digital/claudetini/pulls) and add a thumbs-up reaction to the ones you want to see merged.
- **For Reviews:** Add a thumbs-up reaction to helpful review comments.

Winners are chosen by a combination of community votes and technical merit. Broken or malicious code is disqualified regardless of votes.

**Winners announced in the Discussions tab approximately 2 weeks after launch.**

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Rust (latest stable, for Tauri)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview) installed

### Setup

```bash
# Clone
git clone https://github.com/cantina-digital/claudetini.git
cd claudetini

# Python dependencies
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"

# Run the app (installs frontend dependencies automatically)
cd app
npm run tauri:dev
```

First Tauri build takes 2-3 minutes. After that, hot reload is fast.

If you don't have Rust/Tauri and just want to work on the frontend or backend:

```bash
cd app

# Terminal 1: backend
npm run backend

# Terminal 2: frontend
npm run dev
```

Then open http://localhost:5173.

---

## Making a Contribution

1. **Find something to work on.** Check [Issues](https://github.com/cantina-digital/claudetini/issues) for bugs and feature requests, or open your own.
2. **Create a branch:** `git checkout -b feature/your-feature`
3. **Make your changes.**
4. **Test:**
   ```bash
   # Python tests
   pytest

   # Lint
   ruff check src/

   # Type check
   mypy src/
   ```
5. **Open a PR** against `main` with a clear description of what changed and why.

---

## Project Structure

```
claudetini/
├── src/core/              # Python business logic (30+ modules)
├── src/agents/            # Claude Code integration (bootstrap, dispatch, gates)
├── tests/                 # Pytest suite
└── app/     # Desktop application
    ├── src/               # React 19 + TypeScript + Tailwind CSS frontend
    ├── src-tauri/         # Tauri 2 Rust shell (minimal)
    └── python-sidecar/    # FastAPI backend (port 9876)
```

### Where to Look

| I want to... | Look here |
|--------------|-----------|
| Fix a UI bug | `app/src/components/` |
| Add a backend endpoint | `app/python-sidecar/sidecar/api/routes/` |
| Change core logic (scoring, parsing, git) | `src/core/` |
| Modify the bootstrap engine | `src/agents/bootstrap_engine.py` |
| Add or fix quality gates | `src/agents/gates.py` |
| Change the dispatch system | `src/agents/dispatcher.py` |
| Write tests | `tests/` |

---

## Code Style

### Python (`src/`, `python-sidecar/`)

- PEP 8 via `ruff`
- Type hints on all function signatures
- `pathlib.Path` over `os.path`
- Dataclasses or Pydantic models for structured data

### TypeScript/React (`app/src/`)

- Functional components only
- Tailwind CSS with `mc-*` design tokens (dark theme)
- Zustand for global state, `useState` for local UI state
- No `any` — use `unknown` if the type is genuinely unknown

### Naming

- `snake_case` for Python
- `camelCase` for TypeScript functions/variables
- `PascalCase` for components, classes, types, interfaces
- `SCREAMING_SNAKE_CASE` for constants

---

## Good First Contributions

Not sure where to start? Here are some ideas:

- **Improve error messages** — Find a place where a failure gives unhelpful feedback and make it clearer
- **Add a missing test** — Pick a core module and add test coverage
- **UI polish** — Spacing, alignment, hover states, loading states
- **Documentation** — Spot something wrong or unclear in the docs? Fix it
- **Accessibility** — Keyboard navigation, screen reader support, contrast

---

## Questions?

Open an issue or start a discussion. No question is too basic.
