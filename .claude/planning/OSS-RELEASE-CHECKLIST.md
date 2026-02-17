# Open Source Release Checklist

> Run through this checklist after the final milestone is complete and before making the repo public.
> Items marked with `[!!]` are blockers. Everything else is strongly recommended.

---

## 1. Secrets & Sanitization

- [ ] `[!!]` Run `git log --all -p | grep -iE "(sk-|ghp_|ghs_|AKIA|password\s*=|token\s*=|secret\s*=)"` — confirm zero real credentials in history
- [ ] `[!!]` Verify no `.env` files are tracked: `git ls-files | grep -i '\.env'`
- [ ] `[!!]` Confirm `.gitignore` excludes: `.env`, `.env.local`, `.claudetini/`, `__pycache__/`, `node_modules/`, `target/`, `.venv/`
- [ ] `[!!]` Search for hardcoded local paths: `grep -r "/Users/" src/ app/src/ --include="*.py" --include="*.ts" --include="*.tsx"` — must be zero results (all paths should use `Path.home()` or env vars)
- [ ] Verify `examples/recipe-cli/.env` contains only the fake demo key (`sk-fake-key-for-demo-purposes-do-not-use`)
- [ ] Verify `examples/devlog/.env.example` is a template with no real values
- [ ] Check that `.claudetini/` runtime data directory is not committed (it's in `.gitignore`)
- [ ] Search for TODO/FIXME/HACK comments that expose internal context: `grep -rn "TODO\|FIXME\|HACK\|XXX" src/ app/src/` — review each one

---

## 2. SECURITY.md

- [ ] `[!!]` Replace the GitHub template boilerplate with real content. Current file at `/SECURITY.md` has placeholder version table (5.1.x, 5.0.x, 4.0.x) that makes no sense for this project.
- [ ] Specify supported versions (currently v0.2.0 alpha)
- [ ] Add reporting instructions (email or GitHub Security Advisories)
- [ ] Set response time expectations (e.g., "We aim to respond within 72 hours")
- [ ] Note that Claudetini is read-only for `~/.claude/` data (relevant security context)

---

## 3. Documentation Review

### README.md
- [ ] Verify all links work: GitHub repo URL, CONTRIBUTING.md, LICENSE, examples/README.md
- [ ] Confirm badges render correctly (Python, Node, License, Status)
- [ ] Test installation instructions on a clean machine or fresh clone
- [ ] Verify `npm run tauri:dev` command works from the documented path
- [ ] Confirm demo setup script works: `bash examples/setup_demos.sh`
- [ ] Review FAQ — are answers still accurate?

### CLAUDE.md (root)
- [ ] Verify `<!-- claudetini:managed -->` section is up to date
- [ ] Confirm architecture diagram matches current directory structure
- [ ] Verify all listed commands work (`pytest`, `ruff check src/`, `mypy src/`, etc.)
- [ ] Check that data source paths (`~/.claude/projects/`, `~/.claude/todos/`) are still accurate

### app/CLAUDE.md
- [ ] Verify frontend conventions match the actual codebase
- [ ] Check that component naming patterns are accurate
- [ ] Confirm state management description matches current Zustand usage

### CONTRIBUTING.md
- [ ] Confirm bounty amounts and rules are what you want to publish
- [ ] Verify the "Getting Started" setup steps work
- [ ] Check that "Where to Look" table matches current directory structure
- [ ] Review "Good First Contributions" — are they still valid entry points?

### docs/
- [ ] `docs/README.md` — hub links point to real files
- [ ] `docs/ARCHITECTURE.md` — matches current system design
- [ ] `docs/API.md` — all documented endpoints exist and return what's described
- [ ] `docs/CORE-MODULES.md` — module list matches what's in `src/core/`
- [ ] `docs/FEATURES.md` — no features listed that don't actually work
- [ ] `docs/FRONTEND.md` — component inventory is current
- [ ] `docs/STATE-MANAGEMENT.md` — Zustand stores match reality
- [ ] `docs/DESIGN-SYSTEM.md` — design tokens are accurate
- [ ] `docs/DATA-FLOWS.md` — data flow diagrams are current
- [ ] `docs/views/*.md` — spot-check 3-4 view docs for accuracy
- [ ] `docs/test-fixtures.md` — fixture descriptions match actual fixtures

### Other docs
- [ ] `TESTING_GUIDE.md` — instructions work, referenced test commands succeed
- [ ] `RUN_INSTRUCTIONS.md` — setup flow works on a clean environment
- [ ] `examples/README.md` — demo descriptions match actual demo content

---

## 4. Dependency Cleanup

- [ ] `[!!]` **Remove PyQt6 from `pyproject.toml`** — this is a Tauri/React app, PyQt6 appears to be a leftover from an earlier iteration. Also remove `pytest-qt` from dev deps if no longer used.
- [ ] Run `pip install -e ".[dev]"` cleanly with no errors
- [ ] Run `cd app && npm install` cleanly with no errors
- [ ] Check for unused Python dependencies: review `requirements.txt` vs actual imports
- [ ] Check for unused npm dependencies: `cd app && npx depcheck`
- [ ] Verify all dependency versions in READMEs and CLAUDE.md match `pyproject.toml` / `package.json`
- [ ] Confirm `app/python-sidecar/pyproject.toml` dependencies are complete (no missing imports at runtime)

---

## 5. Version Alignment

Current state (inconsistent):
- Root `pyproject.toml`: `0.2.0`
- Sidecar `pyproject.toml`: `1.0.0`
- App `package.json`: `0.1.0`
- Tauri `tauri.conf.json`: `1.0.0`

- [ ] `[!!]` Align all version numbers to a single release version (recommend `0.1.0` for initial open-source release since this is alpha)
- [ ] Update `pyproject.toml` version
- [ ] Update `app/python-sidecar/pyproject.toml` version
- [ ] Update `app/package.json` version
- [ ] Update `app/src-tauri/tauri.conf.json` version
- [ ] Update any version references in docs

---

## 6. Package Metadata

### pyproject.toml (root)
- [ ] `name` is correct: `claudetini`
- [ ] `description` is clear and concise
- [ ] `license` is MIT
- [ ] `authors` — decide if you want individual names or just "Cantina Digital"
- [ ] `classifiers` — review for accuracy (currently lists Alpha, macOS, Python 3.11/3.12)
- [ ] `project.urls` — verify GitHub links will be live when repo goes public
- [ ] `project.scripts` — verify `claudetini` and `claudetini` entry points work

### app/package.json
- [ ] Decide on `"private": true` — keep if not publishing to npm (likely correct for a desktop app)
- [ ] Add `"description"`, `"license"`, `"repository"` fields if missing
- [ ] Verify `"name"` won't conflict with existing npm packages

### Cargo.toml
- [ ] Verify `description`, `authors`, `edition` are correct
- [ ] Add `license = "MIT"` if missing
- [ ] Add `repository` URL if missing

---

## 7. Planning Directory Cleanup

- [ ] Review `.claude/planning/DISPATCH-UX-ISSUES.md` — archive or delete if resolved
- [ ] Review `.claude/planning/DISPATCH-UX-PLAN.md` — archive or delete if resolved
- [ ] Review `.claude/planning/archive/` — confirm these are fine to ship (they're historical planning docs; harmless but potentially confusing for newcomers)
- [ ] ROADMAP.md — make sure completed milestones don't contain internal-only context or embarrassing notes
- [ ] Decide: should `.claude/planning/` be in `.gitignore`? It's useful for transparency but also internal. If keeping it, add a brief comment at the top of ROADMAP.md explaining what it is.

---

## 8. Code Quality Gate

- [ ] `[!!]` `pytest` — all tests pass
- [ ] `[!!]` `ruff check src/` — no lint errors
- [ ] `mypy src/` — type check passes (or document known exclusions)
- [ ] `cd app && npm run build` — frontend builds without errors
- [ ] No `console.log` debug statements left in production code (search: `grep -rn "console.log" app/src/ --include="*.ts" --include="*.tsx"`)
- [ ] No Python `print()` debug statements (search: `grep -rn "^[^#]*print(" src/ --include="*.py"` — review each hit)
- [ ] No `breakpoint()` or `pdb` left in code

---

## 9. Git Hygiene

- [ ] `[!!]` Clean working tree — all changes committed or intentionally unstaged
- [ ] Review the current uncommitted changes (see git status at top of this session) — commit what belongs, discard what doesn't
- [ ] Deleted files (color_utils.py, text_table.py, smoke_test.py, etc.) — confirm these deletions are intentional and tests still pass without them
- [ ] No merge conflict markers in any file: `grep -rn "<<<<<<" src/ app/src/ docs/`
- [ ] `.gitmodules` — verify the test fixture submodule (`tests/fixtures/projects/07_dirty_git`) is intentional and documented
- [ ] Confirm `main` branch is the correct default branch
- [ ] Review recent commit messages — are they clean and professional? (no "WIP", "asdf", "fix fix fix")

---

## 10. Missing Files to Create

### CODE_OF_CONDUCT.md
- [ ] Create using [Contributor Covenant](https://www.contributor-covenant.org/) (standard for OSS)
- [ ] Add enforcement contact info

### CHANGELOG.md
- [ ] Create with initial release notes
- [ ] Document what's in v0.1.0 (or whatever the release version is)
- [ ] Follow [Keep a Changelog](https://keepachangelog.com/) format

### GitHub Issue Templates (optional but recommended)
- [ ] `.github/ISSUE_TEMPLATE/bug_report.md` — structured bug report form
- [ ] `.github/ISSUE_TEMPLATE/feature_request.md` — feature request form
- [ ] Review existing `.github/ISSUE_TEMPLATE/bounties.md` — still accurate?

---

## 11. CI/CD (Recommended Before Launch)

- [ ] `.github/workflows/python-tests.yml` — run `pytest` on push/PR
- [ ] `.github/workflows/python-lint.yml` — run `ruff check` and `mypy` on push/PR
- [ ] `.github/workflows/frontend-build.yml` — run `npm run build` on push/PR
- [ ] Set branch protection on `main`: require CI to pass before merge
- [ ] Test the workflows on a branch before going live

---

## 12. User Experience (First Impressions)

- [ ] Clone the repo to a fresh directory and follow README setup exactly — does it work?
- [ ] Run `bash examples/setup_demos.sh` — do the demos set up correctly?
- [ ] Start the app with `npm run tauri:dev` — does it launch and show the project picker?
- [ ] Register a demo project — does the scorecard load?
- [ ] Navigate all tabs — do they render without errors?
- [ ] Check browser console for JS errors during normal use
- [ ] Check Python sidecar logs for tracebacks during normal use
- [ ] Verify the app works without Claude Code installed (should degrade gracefully, not crash)

---

## 13. Legal & Licensing

- [ ] `LICENSE` file is MIT and dated correctly (2026)
- [ ] Verify no third-party code was copied without attribution
- [ ] Verify no GPL-licensed dependencies that would conflict with MIT
- [ ] Check that Tauri (MIT/Apache-2.0), React (MIT), FastAPI (MIT) licenses are compatible
- [ ] If using any icons/assets, verify their licenses allow open-source distribution

---

## 14. GitHub Repository Settings (Post-Push)

- [ ] Repository description matches README tagline
- [ ] Topics/tags added: `claude-code`, `developer-tools`, `tauri`, `react`, `python`, `fastapi`, `desktop-app`
- [ ] Website field set (if applicable)
- [ ] "Releases" section has initial release with tag
- [ ] Discussions tab enabled (for community Q&A and bounty announcements)
- [ ] Branch protection rules on `main`
- [ ] Issue labels created: `bug`, `enhancement`, `good first issue`, `bounty`, `documentation`

---

## 15. Launch Day Actions

- [ ] Create GitHub Release with tag (e.g., `v0.1.0-alpha`)
- [ ] Write release notes summarizing what's included
- [ ] Post bounty announcement in Discussions tab
- [ ] Verify all README links work on the live GitHub page
- [ ] Verify the repo renders well on GitHub (README, badges, file tree)
- [ ] Star the repo from the org account to seed visibility

---

## Quick Reference: Blocker Items

These must be resolved before going public:

1. **SECURITY.md** — replace GitHub template with real content
2. **Secrets scan** — confirm zero real credentials in git history
3. **No .env tracked** — verify none are committed
4. **Remove PyQt6** — dead dependency confuses contributors
5. **Version alignment** — pick one version, apply everywhere
6. **Tests pass** — `pytest` green
7. **Lint clean** — `ruff check src/` clean
8. **Clean git state** — all changes committed intentionally
