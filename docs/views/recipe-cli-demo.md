# Recipe CLI Demo Project

> Beginner "Fix My Project" learning experience that walks new developers through Git, GitHub, and Claudetini by transforming a broken project (score ~10) into a professional one (score 90+).

Last updated: 2026-02-17

---

## 1. Purpose

The recipe-cli demo is the entry-level onboarding project for Claudetini. It provides a deliberately flawed Python CLI application that a new user progressively fixes while learning fundamental development practices. The project starts with no version control, no documentation, no tests, and an exposed secret -- scoring approximately 10/100 on Claudetini's readiness scorecard.

The core value proposition is "Fix My Project": rather than reading about what Claudetini does, the user experiences every major feature by working through a real project that needs real remediation. Each fix produces a visible, measurable score improvement, giving immediate feedback and a sense of progression.

This demo is one of two curated examples (the other being `devlog`, an intermediate project). The recipe-cli demo is intentionally small (~8 files, ~400 lines) so that beginners can focus on workflow rather than application complexity.

---

## 2. Target Audience

The recipe-cli demo is designed for users who are:

- **New to Git** -- have never run `git init`, do not know what staging or commits are
- **New to GitHub** -- have never pushed code to a remote repository
- **New to Claude Code** -- have not used Claude Code or Claudetini before
- **Comfortable with a terminal** -- can open a terminal and run commands, but may not know many commands yet
- **Have Python installed** -- Python 3.9+ is the only hard prerequisite

No prior experience with version control, CI/CD, project scaffolding, or security scanning is assumed. The `GETTING_STARTED.md` walkthrough explains every concept from first principles, including what Git is, what a commit is, and what the staging area does.

---

## 3. Project Structure

The recipe-cli project lives at `examples/recipe-cli/` in the Claudetini repository. It contains 11 files across 2 directories:

```
examples/recipe-cli/
├── .env                        # Intentional secret: exposed API key (security scanner demo)
├── GETTING_STARTED.md          # 21-section guided walkthrough (1134 lines)
├── README.md                   # Deliberately minimal README (10 lines)
├── requirements.txt            # Python dependencies: requests, click
├── setup.py                    # setuptools packaging configuration
└── recipe_cli/                 # Python package
    ├── __init__.py             # Package marker with __version__ = "0.1.0"
    ├── __main__.py             # Enables `python -m recipe_cli` execution
    ├── main.py                 # Click CLI entry point (search command)
    ├── search.py               # Local recipe database and search logic
    ├── api.py                  # Intentional secret: hardcoded AKIA key
    └── display.py              # Table and JSON output formatting
```

### File-by-File Purpose

| File | Lines | Purpose |
|------|-------|---------|
| `.env` | 4 | Contains `API_KEY=sk-fake-key-for-demo-purposes-do-not-use`. Exists to trigger the secrets scanner. |
| `GETTING_STARTED.md` | 1134 | Complete walkthrough from zero to 90+ score. See [Section 8](#8-the-getting_startedmd-walkthrough-structure). |
| `README.md` | 10 | Intentionally bare: just a title and two usage examples. Claudetini flags it as missing sections. |
| `requirements.txt` | 2 | Declares `requests>=2.31.0` and `click>=8.1.0`. |
| `setup.py` | 19 | Standard setuptools config with `console_scripts` entry point for `recipe-cli`. Requires Python >=3.9. |
| `__init__.py` | 3 | Package init, exports `__version__ = "0.1.0"`. |
| `__main__.py` | 5 | Imports and calls `cli()` from `main.py`, enabling `python -m recipe_cli`. |
| `main.py` | 42 | Click CLI group with a `search` command. Accepts `ingredient`, `--max`, and `--format` options. |
| `search.py` | 135 | Contains 15 hardcoded recipes and the `find_recipes()` function. Has `TODO` and `FIXME` comments. |
| `api.py` | 48 | Unused API client with a hardcoded `AKIAIOSFODNN7EXAMPLE` key. Exists to trigger the secrets scanner. |
| `display.py` | 64 | Formats search results as either a text table or JSON. |

### What Is Deliberately Missing

The following are absent by design, so that Claudetini's scorecard flags them:

- **No `.git/` directory** -- no version control initialized
- **No `.gitignore`** -- no ignore rules, so `.env` would be committed
- **No `CLAUDE.md`** -- no project instructions for Claude Code
- **No `.claude/planning/ROADMAP.md`** -- no task tracking
- **No `tests/` directory** -- no unit tests
- **No `LICENSE` file** -- no open-source license

---

## 4. The Intentional .env Secret

The recipe-cli project contains two deliberately planted secrets that demonstrate Claudetini's security scanning capability:

### Secret 1: `.env` file

```
API_KEY=sk-fake-key-for-demo-purposes-do-not-use
API_BASE_URL=http://api.example.com/v2
DEBUG=true
```

The `.env` file itself is a security concern because it is not excluded by a `.gitignore` (which does not yet exist). Without a `.gitignore`, `git add .` will stage the `.env` file and its secrets will be committed to version history.

### Secret 2: Hardcoded key in `api.py`

```python
API_KEY = "AKIAIOSFODNN7EXAMPLE"
```

This uses the `AKIA` prefix pattern characteristic of AWS access keys. Claudetini's secrets scanner pattern-matches this as a potential credential leak. The key is fake but follows the real AWS key format to ensure the scanner triggers on realistic patterns.

### The Learning Moment

When the user registers the project in Claudetini, the readiness scorecard shows a failing "No exposed secrets" check. The walkthrough explains:

1. **Before Bootstrap:** Both the `.env` file and the `api.py` hardcoded key are flagged.
2. **After Bootstrap:** The generated `.gitignore` excludes `.env`, so that exposure drops to a warning. However, `api.py` still contains the hardcoded key, which the scanner correctly continues to flag.
3. **Optional fix (Section 20):** The walkthrough suggests replacing the hardcoded key with `os.environ.get("API_KEY")` and creating a `.env.example` file without real values.

This progression teaches that secrets management is not a one-time fix but a practice: exclude secret files from version control, never hardcode credentials, and use environment variables.

---

## 5. Learning Journey -- Score Progression

The recipe-cli walkthrough produces four distinct score plateaus:

```
Score: ~10/100    Starting point
     |
     |  git init
     v
Score: ~25/100    Git initialized, basic README detected
     |
     |  Bootstrap (generates CLAUDE.md, ROADMAP.md, .gitignore)
     v
Score: ~70/100    Documentation and project structure in place
     |
     |  Add tests/ directory + LICENSE file
     v
Score: ~90/100    Professional project with tests, docs, and license
```

### Score Breakdown by Phase

**Phase 1: Raw project (~10/100)**

| Check | Status |
|-------|--------|
| Git initialized | FAIL |
| Has commits | FAIL |
| Has .gitignore | FAIL |
| Has README | PASS (+5) |
| README has sections | FAIL |
| Has CLAUDE.md | FAIL |
| Has ROADMAP.md | FAIL |
| Has tests | FAIL |
| No exposed secrets | FAIL |
| Has LICENSE | FAIL |

**Phase 2: After `git init` (~25/100)**

Git initialized flips to PASS (+15). Everything else remains the same.

**Phase 3: After Bootstrap (~70/100)**

| Check | Change |
|-------|--------|
| Has .gitignore | FAIL -> PASS |
| Has CLAUDE.md | FAIL -> PASS |
| Has ROADMAP.md | FAIL -> PASS |
| No exposed secrets | FAIL -> WARN (`.env` now ignored, but `api.py` still has hardcoded key) |
| README has sections | FAIL -> WARN |

**Phase 4: After tests + LICENSE (~90/100)**

| Check | Change |
|-------|--------|
| Has tests | FAIL -> PASS |
| Has LICENSE | FAIL -> PASS |

The remaining deductions (preventing a perfect 100) are the hardcoded `AKIAIOSFODNN7EXAMPLE` key in `api.py` and the minimal README. These are left as optional exercises.

---

## 6. Claudetini Features Demonstrated

The recipe-cli demo exercises five major Claudetini features:

### 6.1 Readiness Scorecard

The primary feature on display. The user sees the scorecard at four different points in the walkthrough, watching individual checks flip from red (FAIL) to yellow (WARN) to green (PASS). The scorecard teaches users:

- What a "ready" project looks like
- Which checks matter and why
- How to interpret the overall score versus individual results

### 6.2 Secrets Scanner

Triggered by two intentional secrets (`.env` file and hardcoded `AKIA` key in `api.py`). Demonstrates:

- Pattern-based secret detection (AWS key format)
- `.env` file detection as a security risk
- How `.gitignore` mitigates `.env` exposure
- That hardcoded secrets in source files remain flagged even after `.gitignore` is added

### 6.3 Bootstrap Wizard

The user runs Bootstrap from Claudetini to generate:

- `CLAUDE.md` -- project instructions for Claude Code
- `.claude/planning/ROADMAP.md` -- milestone-based task tracking
- `.gitignore` -- technology-appropriate ignore patterns

The Bootstrap demonstration shows cost estimation, real-time SSE progress streaming, and the resulting artifact generation. This is the single largest score jump in the walkthrough (from ~25 to ~70).

### 6.4 Git Tab

After `git init` and the first commit, the Git tab shows:

- Commit history
- Branch information
- Remote connection status (after connecting to GitHub)
- Staged vs. unstaged vs. untracked files (the walkthrough explicitly discusses all three states)

The walkthrough also demonstrates using the Git tab as an alternative to command-line `git add` and `git commit`.

### 6.5 Project Registration

The very first Claudetini interaction is registering the project via "Add Project" in the sidebar. This demonstrates the project picker and initial scan flow.

---

## 7. Setup Instructions

### Prerequisites

- Python 3.9 or newer
- Claudetini installed and running
- A text editor
- A terminal

### Running the Setup Script

From the Claudetini repository root:

```bash
bash examples/setup_demos.sh
```

**What the script does for recipe-cli:**

1. Verifies all expected files are present (checks each file in the root and `recipe_cli/` package)
2. Reports any missing files
3. Explicitly does NOT initialize Git (this is the user's job, guided by `GETTING_STARTED.md`)

**What the script does NOT do:**

- Modify `~/.claude/` (Claudetini's read-only policy)
- Auto-register projects in Claudetini (the user does this manually)
- Install Python dependencies (the user manages their own virtual environment)
- Create a Git repository (intentionally left for the walkthrough)

### Manual Verification

If you prefer to skip the setup script, verify the project is intact:

```bash
ls examples/recipe-cli/
# Should show: .env  GETTING_STARTED.md  README.md  recipe_cli/  requirements.txt  setup.py

ls examples/recipe-cli/recipe_cli/
# Should show: __init__.py  __main__.py  api.py  display.py  main.py  search.py
```

### Registering in Claudetini

1. Open Claudetini
2. Click "Add Project" in the sidebar
3. Navigate to `examples/recipe-cli/`
4. Click "Register"

The initial scan will produce a readiness score of approximately 10/100.

---

## 8. The GETTING_STARTED.md Walkthrough Structure

The walkthrough is a 1134-line, 21-section guided document that takes a complete beginner from zero to a professional project setup. Below is a summary of each section:

### Section 1: What You Will Build

Introduces Recipe CLI as a simple ingredient search tool. Sets expectations: the app is deliberately small so the focus is on workflow, not application logic. Lists learning outcomes (Git, GitHub, Claudetini, Bootstrap).

### Section 2: Prerequisites

Lists requirements: Python 3.9+, Claudetini, a text editor, and a terminal. Includes commands to verify the Python version and a link to python.org for installation.

### Section 3: Check if Git is Installed

Explains what Git is (version control system) and how to check if it is already installed via `git --version`.

### Section 4: Install Git (if needed)

Platform-specific installation instructions for macOS (Xcode Command Line Tools or Homebrew), Linux (apt, dnf, pacman), and Windows (git-scm.com installer). Includes post-install verification.

### Section 5: Configure Git

Walks through `git config --global user.name` and `user.email`. Explains each flag. Includes optional editor configuration (VS Code, Nano, Sublime Text).

### Section 6: Create a GitHub Account

Explains what GitHub is and how it relates to Git. Step-by-step GitHub signup. Mentions GitLab and Bitbucket as alternatives. Quick tour of repositories, commits, and branches.

### Section 7: Create a Repository on GitHub

Step-by-step guide to creating an empty GitHub repository named `recipe-cli`. Emphasizes not checking any initialization boxes (no README, no .gitignore, no license) since files already exist locally.

### Section 8: Open the Project in Your Terminal

Navigate to the `recipe-cli` directory. Verify correct location with `ls`. First Claudetini interaction: register the project and observe the initial ~10/100 score. Lists all the reasons the score is low.

### Section 9: Initialize Git Locally

Run `git init`. Explains what the `.git/` hidden directory is. Verify with `git status` -- shows all files as "untracked."

### Section 10: See Your Score Jump in Claudetini

Re-scan after `git init`. Score jumps to ~25/100. Includes a table of all readiness checks with current pass/fail status. Explains what Claudetini is checking.

### Section 11: Connect Your Local Repo to GitHub

Run `git remote add origin <URL>`. Explains what "origin" means, what a remote is, and the difference between fetch and push. Covers HTTPS vs. SSH URL formats.

### Section 12: Your First Commit

Two-step process: `git add .` then `git commit -m "Initial project setup"`. Extensive explanation of the staging area concept with a diagram (Working Directory -> Staging Area -> Repository). Notes that `.env` is being committed intentionally for demo purposes.

### Section 13: Push to GitHub

Run `git push -u origin main`. Explains each flag. Covers GitHub authentication (Personal Access Tokens replacing passwords). Includes credential helper setup for macOS, Linux, and Windows. Verify on GitHub.

### Section 14: Check Claudetini Again

Re-scan shows ~25-30/100. Score has not changed much because the big gains come from documentation, not just Git setup. Highlights the Git tab now showing commit history and remote info.

### Section 15: Run Bootstrap

The walkthrough's pivotal moment. Explains what Bootstrap creates (CLAUDE.md, ROADMAP.md, .gitignore). Step-by-step guide to running Bootstrap from Claudetini. Post-Bootstrap file inspection. Score jumps to ~70/100 with a before/after comparison table.

### Section 16: Commit the Bootstrapped Files

Stage and commit the Bootstrap-generated files (`git add .gitignore CLAUDE.md .claude/`). Push to GitHub. Also demonstrates using Claudetini's Git tab as an alternative to CLI commands.

### Section 17: Add Tests and a LICENSE

Create `tests/test_search.py` with four test functions (match, max results, no match, case insensitive). Install pytest. Run tests. Create a MIT LICENSE file. Commit and push both.

### Section 18: Final Score Check

Re-scan shows ~90+/100. Lists what the project now has (Git, GitHub, README, CLAUDE.md, ROADMAP.md, .gitignore, tests, LICENSE). Notes remaining deductions (hardcoded secret in `api.py`, minimal README sections).

### Section 19: Readiness Score Progression Summary

ASCII art summary of the four score plateaus (~10 -> ~25 -> ~70 -> ~90+) with the action that caused each jump.

### Section 20: What is Next

Suggests three paths forward:
1. Run the CLI app (`python -m recipe_cli search chicken`)
2. Fix remaining issues (replace hardcoded API key with environment variable, create `.env.example`)
3. Explore Claudetini tabs (Readiness, Git, Intelligence, Timeline)
4. Move to the intermediate `devlog` demo project

### Section 21: Troubleshooting

Covers eight common problems: Git not found, not a git repository, remote already exists, push failures, password authentication removed, SSH permission denied, missing Python modules, Claudetini not detecting the project, and score not updating.

The document ends with a **Quick Reference** table of all Git commands used and a **Glossary** defining repository, commit, staging area, remote, push, pull, branch, clone, .gitignore, and merge.

---

## 9. How the Recipe CLI Code Works

The application is a Python CLI that searches a local recipe database by ingredient. It uses the Click library for command-line interface construction and has three functional modules: search, API (unused), and display.

### Entry Point

**`main.py`** defines a Click command group with a single `search` command:

```python
@cli.command()
@click.argument("ingredient")
@click.option("--max", "-m", "max_results", default=10)
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]), default="table")
def search(ingredient, max_results, output_format):
```

The user runs:

```
python -m recipe_cli search chicken
python -m recipe_cli search "bell pepper" --max 5
python -m recipe_cli search garlic --format json
```

The `__main__.py` module enables `python -m recipe_cli` by importing and calling the `cli()` function.

### Search Module

**`search.py`** contains a hardcoded list of 15 recipes, each a dictionary with `name`, `ingredients` (list of strings), `prep_time` (minutes), `servings` (integer), and `difficulty` (easy/medium/hard).

The 15 recipes cover a range of cuisines:
- Classic Chicken Parmesan, Chicken Stir Fry, Chicken Tikka Masala, BBQ Chicken Pizza
- Tomato Basil Soup, Beef Tacos, Pasta Carbonara, Caesar Salad
- Vegetable Curry, Grilled Salmon, Mushroom Risotto
- Shrimp Scampi, Black Bean Soup, Greek Salad, Banana Pancakes

The `find_recipes()` function performs a case-insensitive substring match against each recipe's ingredient list:

```python
def find_recipes(ingredient: str, max_results: int = 10) -> list[dict]:
    matches = []
    for recipe in RECIPES:
        for recipe_ingredient in recipe["ingredients"]:
            if ingredient.lower() in recipe_ingredient.lower():
                matches.append(recipe)
                break
    return matches[:max_results]
```

Notable details:
- Search is case-insensitive (despite the `FIXME` comment claiming otherwise -- the code already normalizes with `.lower()`)
- The `timeout = 30` variable on line 125 is unused dead code
- The `TODO` comment about replacing hardcoded recipes with an API call is intentional -- it gives Claudetini's intelligence scanner something to detect

### API Module (Unused)

**`api.py`** defines `search_api()` and `get_recipe_details()` functions that call a fake API endpoint (`http://api.example.com/v2/recipes`). These functions are never called by the main application. The module exists solely to:

1. Plant the `AKIAIOSFODNN7EXAMPLE` hardcoded secret for the security scanner
2. Include a `FIXME` comment for the intelligence scanner
3. Demonstrate what an API client module looks like

The `get_api_key()` function shows a common anti-pattern: falling back to a hardcoded key when the environment variable is not set:

```python
def get_api_key() -> str:
    return os.environ.get("API_KEY", API_KEY)  # Falls back to hardcoded AKIA key
```

### Display Module

**`display.py`** formats search results in two modes:

- **Table mode** (default): Fixed-width columns showing Name (35 chars), Time, Serves, and Difficulty. Uses string formatting with alignment operators (`:<35`, `:>6`, etc.).
- **JSON mode**: Pretty-printed JSON via `json.dumps(recipes, indent=2)`.

Example table output:

```
Name                                  Time  Serves Difficulty
-----------------------------------------------------------
Classic Chicken Parmesan              45min       4 medium
Chicken Stir Fry                      25min       2 easy
```

### Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `click` | >=8.1.0 | CLI framework (commands, arguments, options) |
| `requests` | >=2.31.0 | HTTP client (used only in the unused `api.py`) |

---

## 10. Expected Outcomes After Completing the Walkthrough

After completing all 21 sections of the `GETTING_STARTED.md` walkthrough, the user will have:

### Artifacts Created

| Artifact | Origin | Location |
|----------|--------|----------|
| Git repository | User (Section 9) | `examples/recipe-cli/.git/` |
| GitHub remote | User (Sections 7, 11, 13) | `github.com/<username>/recipe-cli` |
| Initial commit | User (Section 12) | Git history |
| CLAUDE.md | Bootstrap (Section 15) | `examples/recipe-cli/CLAUDE.md` |
| ROADMAP.md | Bootstrap (Section 15) | `examples/recipe-cli/.claude/planning/ROADMAP.md` |
| .gitignore | Bootstrap (Section 15) | `examples/recipe-cli/.gitignore` |
| Bootstrap commit | User (Section 16) | Git history |
| Test suite | User (Section 17) | `examples/recipe-cli/tests/test_search.py` |
| LICENSE | User (Section 17) | `examples/recipe-cli/LICENSE` |
| Tests + LICENSE commit | User (Section 17) | Git history |

### Skills Learned

- **Git fundamentals:** `init`, `add`, `status`, `commit`, `remote add`, `push`, `log`
- **Staging area concept:** Understanding the three-stage workflow (working directory, staging area, repository)
- **GitHub basics:** Creating a repository, pushing code, viewing code on GitHub, Personal Access Tokens
- **Claudetini usage:** Registering projects, reading the readiness scorecard, running Bootstrap, using the Git tab
- **Project best practices:** Why you need a `.gitignore`, how secrets leak through version control, the purpose of CLAUDE.md and ROADMAP.md, why tests and licenses matter

### Claudetini Readiness Score

Final score of approximately 90/100, with the remaining deductions from:

- Hardcoded `AKIAIOSFODNN7EXAMPLE` in `api.py` (security scanner)
- Minimal README missing common sections like installation, contributing, and changelog

### Recommended Next Steps

1. **Fix remaining issues** -- Replace the hardcoded API key with `os.environ.get()`, create `.env.example`, expand README sections
2. **Explore other Claudetini tabs** -- Intelligence tab (TODO/FIXME detection), Timeline tab (Claude Code session history)
3. **Move to the devlog demo** -- The intermediate project at `examples/devlog/` demonstrates the full dashboard with roadmap progress, quality gates, reconciliation, and multi-milestone tracking

---

## 11. Key Source Files

| File | Purpose |
|------|---------|
| `examples/recipe-cli/GETTING_STARTED.md` | Complete 21-section beginner walkthrough |
| `examples/recipe-cli/README.md` | Minimal project README (intentionally bare) |
| `examples/recipe-cli/.env` | Intentional secret for security scanner demo |
| `examples/recipe-cli/recipe_cli/main.py` | Click CLI entry point |
| `examples/recipe-cli/recipe_cli/search.py` | Recipe database and search logic |
| `examples/recipe-cli/recipe_cli/api.py` | Unused API client with hardcoded AKIA key |
| `examples/recipe-cli/recipe_cli/display.py` | Table and JSON output formatting |
| `examples/recipe-cli/setup.py` | Package configuration |
| `examples/recipe-cli/requirements.txt` | Python dependencies |
| `examples/setup_demos.sh` | Setup script for both demo projects |
| `examples/README.md` | Overview of both demo projects |
