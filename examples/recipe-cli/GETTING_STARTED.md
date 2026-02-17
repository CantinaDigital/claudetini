# Getting Started with Recipe CLI + Claudetini

Welcome! This guide will walk you through setting up your very first development
project using Git, GitHub, and Claudetini. By the end, you will have a
working command-line tool, version control, and a professional project structure
--- all while watching your Claudetini readiness score climb from about 10
all the way to 90+.

No prior experience with Git or the command line is required. Every step is
explained in plain language with the exact commands to run.

---

## Table of Contents

1. [What You Will Build](#1-what-you-will-build)
2. [Prerequisites](#2-prerequisites)
3. [Check if Git is Installed](#3-check-if-git-is-installed)
4. [Install Git (if needed)](#4-install-git-if-needed)
5. [Configure Git](#5-configure-git)
6. [Create a GitHub Account](#6-create-a-github-account)
7. [Create a Repository on GitHub](#7-create-a-repository-on-github)
8. [Open the Project in Your Terminal](#8-open-the-project-in-your-terminal)
9. [Initialize Git Locally](#9-initialize-git-locally)
10. [See Your Score Jump in Claudetini](#10-see-your-score-jump-in-claudetini)
11. [Connect Your Local Repo to GitHub](#11-connect-your-local-repo-to-github)
12. [Your First Commit](#12-your-first-commit)
13. [Push to GitHub](#13-push-to-github)
14. [Check Claudetini Again](#14-check-claudetini-again)
15. [Run Bootstrap](#15-run-bootstrap)
16. [Commit the Bootstrapped Files](#16-commit-the-bootstrapped-files)
17. [Add Tests and a LICENSE](#17-add-tests-and-a-license)
18. [Final Score Check](#18-final-score-check)
19. [Readiness Score Progression Summary](#19-readiness-score-progression-summary)
20. [What is Next](#20-what-is-next)
21. [Troubleshooting](#21-troubleshooting)

---

## 1. What You Will Build

Recipe CLI is a simple Python command-line tool that searches recipes by
ingredient. For example:

```
python -m recipe_cli search chicken
```

It will print a table of chicken recipes with prep time, servings, and
difficulty. That is the whole app. It is deliberately small so you can focus
on learning the development workflow rather than getting lost in application
logic.

Along the way, you will learn:

- How to use Git to track changes to your code
- How to push code to GitHub so it is backed up and shareable
- How Claudetini scores your project's "readiness" and helps you improve it
- How Bootstrap generates professional project files automatically

### What is Claudetini?

Claudetini is a desktop dashboard for Claude Code projects. It scans your
project and gives you a readiness score based on best practices: Do you have
version control? Documentation? Tests? Are there exposed secrets? It helps you
build good habits from day one.

---

## 2. Prerequisites

Before you begin, make sure you have:

- **Python 3.9 or newer** installed on your computer
- **Claudetini** installed and running
- A **text editor** (VS Code, Sublime Text, or any editor you like)
- A **terminal** (Terminal on macOS, Command Prompt or PowerShell on Windows,
  or any terminal on Linux)

To check your Python version, open a terminal and run:

```bash
python --version
```

or:

```bash
python3 --version
```

You should see something like `Python 3.11.5` or similar. Any version 3.9 or
above will work.

If you do not have Python installed, visit https://python.org/downloads/ and
follow the instructions for your operating system.

---

## 3. Check if Git is Installed

Git is a version control system. It tracks every change you make to your code,
so you can go back in time, collaborate with others, and never lose your work.

Let us check if you already have it. Open your terminal and type:

```bash
git --version
```

If Git is installed, you will see something like:

```
git version 2.42.0
```

The exact version number does not matter as long as it is 2.x or newer. If you
see this, skip ahead to [Section 5: Configure Git](#5-configure-git).

If you see an error like `command not found` or `git is not recognized`, you
need to install Git. Continue to the next section.

---

## 4. Install Git (if needed)

### macOS

You have two options:

**Option A: Xcode Command Line Tools (easiest)**

Run this in your terminal:

```bash
xcode-select --install
```

A dialog box will pop up asking you to install the tools. Click "Install" and
wait for it to finish (it may take a few minutes). This installs Git along with
other useful developer tools.

**Option B: Homebrew**

If you use Homebrew (a package manager for macOS), run:

```bash
brew install git
```

If you do not have Homebrew, you can install it first by visiting
https://brew.sh/ and running the install command shown on that page.

### Linux

**Ubuntu / Debian:**

```bash
sudo apt update
sudo apt install git
```

**Fedora / RHEL / CentOS:**

```bash
sudo dnf install git
```

**Arch Linux:**

```bash
sudo pacman -S git
```

### Windows

Visit https://git-scm.com/download/win and download the installer. Run it and
accept the default settings. The installer includes "Git Bash," a terminal that
makes Git commands work the same way as on macOS and Linux.

After installation, close and reopen your terminal, then verify:

```bash
git --version
```

You should now see a version number. If you still get an error, restart your
computer and try again.

---

## 5. Configure Git

Before you can use Git, you need to tell it who you are. This information is
attached to every change you make, so your teammates (or future you) know who
wrote what.

Run these two commands, replacing the placeholder values with your actual name
and email:

```bash
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

For example:

```bash
git config --global user.name "Maria Garcia"
git config --global user.email "maria.garcia@gmail.com"
```

### What do these commands do?

- `git config` changes Git's settings
- `--global` means this applies to all projects on your computer (not just one)
- `user.name` is the name that appears next to your changes
- `user.email` is the email associated with your changes

Use the same email you will use for your GitHub account (next section). This
makes everything line up nicely.

### Verify your configuration

```bash
git config --global --list
```

You should see your name and email in the output:

```
user.name=Maria Garcia
user.email=maria.garcia@gmail.com
```

### Optional: Set your default editor

Git sometimes opens a text editor (for example, when you write commit
messages). By default, it uses Vim, which can be confusing for beginners. You
can change it to something friendlier:

**VS Code:**
```bash
git config --global core.editor "code --wait"
```

**Nano (simple terminal editor):**
```bash
git config --global core.editor "nano"
```

**Sublime Text:**
```bash
git config --global core.editor "subl -n -w"
```

This is optional. If you skip it, you can always write commit messages directly
on the command line (which is what we will do in this guide).

---

## 6. Create a GitHub Account

GitHub is a website that hosts Git repositories (projects) in the cloud. It is
the most popular platform for sharing and collaborating on code. Think of Git
as the tool on your computer, and GitHub as the online backup and sharing
service.

**Alternatives:** GitHub is not the only option. GitLab (https://gitlab.com)
and Bitbucket (https://bitbucket.org) do the same thing. We use GitHub in this
guide because it is the most widely used, but everything you learn here applies
to the others too.

### Create your account

1. Go to https://github.com/signup
2. Enter your email address
3. Create a password
4. Choose a username (this will be part of your profile URL, like
   `github.com/your-username`)
5. Complete the verification steps
6. Choose the free plan (it has everything you need)

That is it. You now have a GitHub account.

### A quick tour of GitHub

Once you are logged in, you will see your dashboard. The key things to know:

- **Repositories** are projects. Each project gets its own repository.
- **Commits** are snapshots of your code at a point in time.
- **Branches** are parallel versions of your code (we will stick to `main`
  for now).
- The **green "New" button** in the top-left creates a new repository.

---

## 7. Create a Repository on GitHub

Now let us create a home for your recipe-cli project on GitHub.

1. Click the green **"New"** button on your GitHub dashboard (or go directly
   to https://github.com/new)

2. Fill in the details:
   - **Repository name:** `recipe-cli`
   - **Description:** "A command-line tool that searches recipes by ingredient"
     (optional but nice to have)
   - **Visibility:** Public (so anyone can see it --- this is fine for a
     learning project)
   - **Initialize this repository:** Do NOT check any of the boxes (no README,
     no .gitignore, no license). We already have files locally, and we will
     push them up.

3. Click **"Create repository"**

GitHub will show you a page with setup instructions. Keep this page open ---
you will need the repository URL in a few minutes. It will look something like:

```
https://github.com/YOUR_USERNAME/recipe-cli.git
```

---

## 8. Open the Project in Your Terminal

Navigate to the recipe-cli folder in your terminal. If you are following the
Claudetini examples, the project is at:

```bash
cd /path/to/claudetini/examples/recipe-cli
```

Replace `/path/to/claudetini` with wherever you have Claudetini on your
computer.

### Verify you are in the right place

```bash
ls
```

You should see files like:

```
GETTING_STARTED.md  README.md  recipe_cli/  requirements.txt  setup.py  .env
```

If you see these files, you are in the right place. If not, double-check the
path.

### Register in Claudetini (first scan)

Open Claudetini and register this project:

1. Click "Add Project" in the sidebar
2. Navigate to the `recipe-cli` folder
3. Click "Register"

Claudetini will scan the project and show your initial readiness score.

**Expected score: approximately 10/100**

Why so low? Because:

- No Git repository (no version control)
- No CLAUDE.md (no project instructions)
- No ROADMAP.md (no task tracking)
- No .gitignore (build artifacts will clutter things up)
- No tests (no quality assurance)
- Exposed secrets in `.env` and `api.py` (security risk)
- Minimal README (missing sections like installation, contributing)

Do not worry! That is exactly the point. We are going to fix all of these
things step by step.

---

## 9. Initialize Git Locally

This is the big moment. You are about to turn a plain folder of files into a
Git repository.

Make sure you are in the `recipe-cli` folder, then run:

```bash
git init
```

You should see:

```
Initialized empty Git repository in /path/to/recipe-cli/.git/
```

### What just happened?

Git created a hidden folder called `.git/` inside your project. This folder
is where Git stores the entire history of your project --- every change, every
snapshot, every branch. You never need to touch this folder directly. Git
manages it for you.

### Verify it worked

```bash
git status
```

You should see something like:

```
On branch main
No commits yet
Untracked files:
  (use "git add <file>..." to include in what will be committed)
        .env
        GETTING_STARTED.md
        README.md
        recipe_cli/
        requirements.txt
        setup.py
```

"Untracked files" means Git can see these files but is not tracking them yet.
We will fix that soon.

---

## 10. See Your Score Jump in Claudetini

Go back to Claudetini and re-scan the project:

1. Open the project in Claudetini
2. Click "Re-scan" or "Refresh" on the Readiness tab

**Expected score: approximately 25/100**

The git check now passes! Claudetini detects that you have initialized a
Git repository. You will also see the Git tab light up with information about
your repository (though there is no commit history yet).

The score is still low because you are missing documentation, tests, and have
security issues. But you have made real progress. Every step forward counts.

### What Claudetini is checking

Here is a peek at what the readiness scanner looks for:

| Check              | Status | Points |
|--------------------|--------|--------|
| Git initialized    | PASS   | +15    |
| Has commits        | FAIL   | --     |
| Has .gitignore     | FAIL   | --     |
| Has README         | PASS   | +5     |
| README has sections | FAIL  | --     |
| Has CLAUDE.md      | FAIL   | --     |
| Has ROADMAP.md     | FAIL   | --     |
| Has tests          | FAIL   | --     |
| No exposed secrets | FAIL   | --     |
| Has LICENSE        | FAIL   | --     |

Do not memorize this table. Claudetini shows you exactly what is passing
and failing in the Readiness tab.

---

## 11. Connect Your Local Repo to GitHub

Now we need to connect your local Git repository to the one you created on
GitHub. In Git terminology, the GitHub copy is called a "remote."

Run this command, replacing `YOUR_USERNAME` with your actual GitHub username:

```bash
git remote add origin https://github.com/YOUR_USERNAME/recipe-cli.git
```

### What does this command do?

- `git remote add` tells Git to add a new remote connection
- `origin` is the name of the remote (this is a convention --- almost everyone
  calls the primary remote "origin")
- The URL is where your GitHub repository lives

### Verify the remote was added

```bash
git remote -v
```

You should see:

```
origin  https://github.com/YOUR_USERNAME/recipe-cli.git (fetch)
origin  https://github.com/YOUR_USERNAME/recipe-cli.git (push)
```

"Fetch" means pulling changes down from GitHub. "Push" means sending changes
up to GitHub. Both point to the same URL.

### A note about SSH vs HTTPS

The URL above uses HTTPS, which works with your GitHub username and password
(or a personal access token). If you are comfortable with SSH keys, you can
use the SSH URL instead:

```
git@github.com:YOUR_USERNAME/recipe-cli.git
```

For beginners, HTTPS is simpler. You can switch to SSH later if you want.

---

## 12. Your First Commit

A commit is a snapshot of your project at a specific point in time. Think of
it like saving a game --- you can always come back to this exact state later.

Making a commit is a two-step process:

### Step 1: Stage your files

Staging means telling Git which files you want to include in the next commit.
This gives you control --- you do not have to commit everything at once.

```bash
git add .
```

The `.` means "add everything in the current directory." For your first commit,
this is fine. Later, you might want to be more selective.

### Verify what is staged

```bash
git status
```

You should now see your files listed under "Changes to be committed" in green:

```
On branch main
No commits yet
Changes to be committed:
  (use "git rm --cached <file>..." to unstage)
        new file:   .env
        new file:   GETTING_STARTED.md
        new file:   README.md
        new file:   recipe_cli/__init__.py
        new file:   recipe_cli/__main__.py
        new file:   recipe_cli/api.py
        new file:   recipe_cli/display.py
        new file:   recipe_cli/main.py
        new file:   recipe_cli/search.py
        new file:   requirements.txt
        new file:   setup.py
```

Notice that `.env` is in there. In a real project, you would NOT commit your
`.env` file because it contains secrets. We are leaving it in deliberately so
Claudetini can detect it and warn you. You will fix this when you run
Bootstrap (which generates a proper `.gitignore`).

### Step 2: Create the commit

```bash
git commit -m "Initial project setup"
```

The `-m` flag lets you write your commit message directly on the command line.
The message should briefly describe what changed. "Initial project setup" is
perfect for a first commit.

You should see output like:

```
[main (root-commit) abc1234] Initial project setup
 11 files changed, 350 insertions(+)
 create mode 100644 .env
 create mode 100644 GETTING_STARTED.md
 create mode 100644 README.md
 create mode 100644 recipe_cli/__init__.py
 create mode 100644 recipe_cli/__main__.py
 create mode 100644 recipe_cli/api.py
 create mode 100644 recipe_cli/display.py
 create mode 100644 recipe_cli/main.py
 create mode 100644 recipe_cli/search.py
 create mode 100644 requirements.txt
 create mode 100644 setup.py
```

Congratulations! You just made your first Git commit.

### Understanding the staging area

Why does Git have a staging area? Why not just commit everything?

Imagine you fixed a bug AND added a new feature in the same coding session.
With the staging area, you can commit the bug fix first, then commit the new
feature separately. This makes your history clean and easy to understand.

```
Working Directory  -->  Staging Area  -->  Repository
   (your files)        (git add)         (git commit)
```

For now, just remember: `git add` picks what to include, `git commit` saves
the snapshot.

---

## 13. Push to GitHub

Your commit exists on your computer, but GitHub does not know about it yet.
Let us fix that.

```bash
git push -u origin main
```

### What does this command do?

- `git push` sends your commits to a remote
- `-u` (or `--set-upstream`) tells Git to remember that your local `main`
  branch should track the remote `main` branch. You only need `-u` the first
  time. After that, you can just run `git push`.
- `origin` is the name of the remote (GitHub)
- `main` is the branch you are pushing

### Authentication

The first time you push, Git will ask for your GitHub credentials.

**If using HTTPS:** GitHub no longer accepts passwords for Git operations. You
need a Personal Access Token:

1. Go to https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Give it a name like "recipe-cli"
4. Check the "repo" scope
5. Click "Generate token"
6. Copy the token and use it as your password when Git asks

**Tip:** To avoid entering your token every time, you can use a credential
helper:

```bash
# macOS (uses Keychain)
git config --global credential.helper osxkeychain

# Linux (caches for 1 hour)
git config --global credential.helper 'cache --timeout=3600'

# Windows (uses Windows Credential Manager)
git config --global credential.helper manager-core
```

### Verify on GitHub

After pushing, visit your repository on GitHub:

```
https://github.com/YOUR_USERNAME/recipe-cli
```

You should see all your files there! Click around, look at the code, read the
README. GitHub renders Markdown files (like README.md) automatically.

---

## 14. Check Claudetini Again

Go back to Claudetini and re-scan:

1. Open the project in Claudetini
2. Click "Re-scan" on the Readiness tab

**Expected score: approximately 25-30/100**

The score has not changed much because we mainly just set up Git and pushed.
The big gains come next.

But look at the **Git tab** --- it now shows:

- Your commit history (one commit so far)
- Branch information (you are on `main`)
- Remote information (connected to GitHub)

This is the power of Claudetini: it reads your Git data and presents it in
a clear, visual dashboard.

---

## 15. Run Bootstrap

This is where things get exciting. Claudetini's Bootstrap feature
automatically generates professional project files based on your codebase.

### What Bootstrap creates

Bootstrap scans your code and generates:

- **CLAUDE.md** --- Project instructions for Claude Code (and for
  Claudetini to read)
- **ROADMAP.md** --- A task list with milestones, pre-populated based on what
  your project needs
- **.gitignore** --- Tells Git which files to ignore (like `.env`, `__pycache__`,
  `.pyc` files)

### Run Bootstrap

In Claudetini:

1. Open the project
2. Go to the "Bootstrap" tab (or click "Bootstrap" in the Readiness tab
   suggestions)
3. Click "Run Bootstrap"
4. Wait for it to complete (usually takes 10-30 seconds)

### What happened?

Check your project folder. You should see new files:

```bash
ls -la
```

New files:

```
.gitignore       <-- Tells Git to ignore .env, __pycache__, etc.
CLAUDE.md        <-- Project instructions and conventions
.claude/planning/ROADMAP.md  <-- Task tracking with milestones
```

### Explore the generated files

**Take a moment to read them.** Open each file in your editor:

- `.gitignore` should include entries like `.env`, `__pycache__/`, `*.pyc`,
  `.DS_Store`, etc.
- `CLAUDE.md` should describe your project structure, tech stack, and
  conventions
- `ROADMAP.md` should have milestones with tasks like "Add unit tests,"
  "Add LICENSE file," "Improve README," etc.

### Re-scan in Claudetini

After Bootstrap finishes, Claudetini automatically re-scans. Check the
Readiness tab:

**Expected score: approximately 70/100**

That is a massive jump! Here is what changed:

| Check                | Before  | After   |
|----------------------|---------|---------|
| Git initialized      | PASS    | PASS    |
| Has commits          | PASS    | PASS    |
| Has .gitignore       | FAIL    | PASS    |
| Has README           | PASS    | PASS    |
| README has sections  | FAIL    | WARN    |
| Has CLAUDE.md        | FAIL    | PASS    |
| Has ROADMAP.md       | FAIL    | PASS    |
| Has tests            | FAIL    | FAIL    |
| No exposed secrets   | FAIL    | WARN    |
| Has LICENSE          | FAIL    | FAIL    |

The `.gitignore` now tells Git to ignore `.env`, so the secrets check improves
(though `api.py` still has hardcoded keys). The documentation checks now pass.
Only tests and LICENSE remain.

---

## 16. Commit the Bootstrapped Files

Let us commit the files that Bootstrap generated.

### Check what changed

```bash
git status
```

You should see new files (`.gitignore`, `CLAUDE.md`, and files under
`.claude/`).

### Stage and commit

```bash
git add .gitignore CLAUDE.md .claude/
git commit -m "Add Bootstrap-generated project files"
```

### Push to GitHub

```bash
git push
```

Notice you do not need `-u origin main` this time --- Git remembers from your
first push.

### Using Claudetini's Git tab

You can also do this from Claudetini's Git tab:

1. Open the Git tab
2. You will see the unstaged files
3. Stage them by selecting the checkboxes
4. Write a commit message: "Add Bootstrap-generated project files"
5. Click "Commit"
6. Click "Push"

Either way works. The command line and Claudetini's Git tab do the same
thing.

---

## 17. Add Tests and a LICENSE

To push your score above 90, you need tests and a LICENSE file.

### Add a simple test

Create a file called `tests/test_search.py`:

```bash
mkdir tests
```

Then create `tests/test_search.py` with this content:

```python
"""Tests for the recipe search module."""

from recipe_cli.search import find_recipes


def test_find_recipes_returns_matches():
    """Test that searching for chicken returns chicken recipes."""
    results = find_recipes("chicken")
    assert len(results) > 0
    for recipe in results:
        ingredient_names = " ".join(recipe["ingredients"])
        assert "chicken" in ingredient_names.lower()


def test_find_recipes_max_results():
    """Test that max_results limits the output."""
    results = find_recipes("chicken", max_results=2)
    assert len(results) <= 2


def test_find_recipes_no_match():
    """Test that searching for a nonexistent ingredient returns empty."""
    results = find_recipes("xylophone")
    assert len(results) == 0


def test_find_recipes_case_insensitive():
    """Test that search is case-insensitive."""
    upper = find_recipes("CHICKEN")
    lower = find_recipes("chicken")
    assert len(upper) == len(lower)
```

### Run the tests

First, install test dependencies:

```bash
pip install pytest
```

Then run:

```bash
pytest tests/ -v
```

You should see all tests pass:

```
tests/test_search.py::test_find_recipes_returns_matches PASSED
tests/test_search.py::test_find_recipes_max_results PASSED
tests/test_search.py::test_find_recipes_no_match PASSED
tests/test_search.py::test_find_recipes_case_insensitive PASSED
```

### Add a LICENSE

For an open-source project, you need a license. The MIT License is the most
popular choice --- it lets anyone use your code with minimal restrictions.

Create a file called `LICENSE` in your project root with the MIT License text
(you can copy it from https://opensource.org/licenses/MIT), replacing the year
and your name.

### Commit tests and LICENSE

```bash
git add tests/ LICENSE
git commit -m "Add unit tests and MIT LICENSE"
git push
```

---

## 18. Final Score Check

Re-scan in Claudetini one more time.

**Expected score: approximately 90+/100**

Your project now has:

- Version control (Git)
- Remote backup (GitHub)
- Documentation (README, CLAUDE.md, ROADMAP.md)
- Build artifacts ignored (.gitignore)
- Unit tests (pytest)
- A license (MIT)

The only remaining deductions are likely:

- Hardcoded secrets in `api.py` (the `AKIAIOSFODNN7EXAMPLE` key)
- README could have more sections (installation, contributing, etc.)

These are real issues that Claudetini correctly identifies. In a production
project, you would fix them. For this demo, they serve as examples of what the
scanner catches.

---

## 19. Readiness Score Progression Summary

Here is the journey you just completed:

```
Score: ~10/100   Starting point (raw project, no git, no docs)
       |
       | git init
       v
Score: ~25/100   Git initialized, basic README exists
       |
       | Bootstrap (CLAUDE.md, ROADMAP.md, .gitignore)
       v
Score: ~70/100   Documentation and project structure in place
       |
       | Add tests + LICENSE
       v
Score: ~90/100   Professional project with tests, docs, and license
```

Every step made a measurable difference. Claudetini gives you a clear path
from "just some files in a folder" to "professional, well-structured project."

---

## 20. What is Next

You have completed the beginner tutorial! Here are your options for continuing:

### Try the app

If you have not already, install the dependencies and run the CLI:

```bash
pip install -r requirements.txt
python -m recipe_cli search chicken
python -m recipe_cli search tomato --max 3
python -m recipe_cli search garlic --format json
```

### Fix the remaining issues

Claudetini told you about hardcoded secrets in `api.py`. Try fixing them:

1. Replace the hardcoded `API_KEY` with `os.environ.get("API_KEY")`
2. Remove the fallback to the hardcoded value
3. Create a `.env.example` file (without real keys) so others know what
   environment variables are needed
4. Re-scan and watch your score improve

### Explore Claudetini's tabs

- **Readiness Tab** --- You have been using this. Explore the individual
  scanner results (secrets, plans, dependencies).
- **Git Tab** --- View your commit history, branches, and diffs.
- **Intelligence Tab** --- See TODO/FIXME comments, code patterns, and
  technical debt detected in your code.
- **Timeline Tab** --- If you use Claude Code, this shows your session
  history.

### Move to the intermediate project

The **devlog** example project (`examples/devlog/`) is a more complex
application that demonstrates:

- Multi-file Python architecture
- Database integration
- API development with FastAPI
- Using Claudetini's Intelligence tab to track technical debt
- Branch-based development workflows

When you are comfortable with the basics covered here, the devlog project is
the natural next step.

---

## 21. Troubleshooting

### "git is not recognized" or "command not found"

Git is not installed. Go back to [Section 4](#4-install-git-if-needed).

### "fatal: not a git repository"

You are not in the right directory, or you forgot to run `git init`. Make sure
you are in the `recipe-cli` folder and run `git init`.

### "remote origin already exists"

You already added the remote. If you need to change it:

```bash
git remote set-url origin https://github.com/YOUR_USERNAME/recipe-cli.git
```

### "failed to push some refs"

This usually means the remote has changes you do not have locally. If this is
a fresh repository, try:

```bash
git push -u origin main --force
```

Only use `--force` if you are sure there is nothing on the remote you want to
keep.

### "Support for password authentication was removed"

GitHub requires a Personal Access Token instead of your password. See the
authentication section in [Step 13](#13-push-to-github).

### "Permission denied (publickey)"

If you are using SSH instead of HTTPS, your SSH key is not set up. The
easiest fix is to switch to HTTPS:

```bash
git remote set-url origin https://github.com/YOUR_USERNAME/recipe-cli.git
```

### "ModuleNotFoundError: No module named 'click'"

You need to install the project dependencies:

```bash
pip install -r requirements.txt
```

### "ModuleNotFoundError: No module named 'recipe_cli'"

Make sure you are running the command from the `recipe-cli` directory (the
folder that contains the `recipe_cli/` package folder):

```bash
cd /path/to/recipe-cli
python -m recipe_cli search chicken
```

### Claudetini does not detect my project

Make sure you registered the project in Claudetini by clicking "Add Project"
and selecting the `recipe-cli` folder. Then click "Re-scan."

### My score did not change after Bootstrap

Try manually clicking "Re-scan" or "Refresh" in the Readiness tab. If that
does not work, close and reopen the project in Claudetini.

---

## Quick Reference

Here are the Git commands you learned in this guide:

| Command                                    | What It Does                          |
|--------------------------------------------|---------------------------------------|
| `git --version`                            | Check if Git is installed             |
| `git config --global user.name "Name"`     | Set your name for commits             |
| `git config --global user.email "email"`   | Set your email for commits            |
| `git init`                                 | Create a new Git repository           |
| `git status`                               | See what files have changed           |
| `git add .`                                | Stage all changed files               |
| `git add filename`                         | Stage a specific file                 |
| `git commit -m "message"`                  | Save a snapshot with a message        |
| `git remote add origin URL`                | Connect to a remote repository        |
| `git push -u origin main`                  | Push to remote (first time)           |
| `git push`                                 | Push to remote (subsequent times)     |
| `git log --oneline`                        | See commit history (short format)     |

---

## Glossary

- **Repository (repo):** A project tracked by Git. Contains all files and
  their complete history.
- **Commit:** A snapshot of your project at a point in time. Like a save point
  in a video game.
- **Staging area:** A holding area where you prepare files before committing.
  Also called the "index."
- **Remote:** A copy of your repository on another computer (like GitHub).
- **Push:** Send your local commits to a remote.
- **Pull:** Get commits from a remote to your local machine.
- **Branch:** A parallel version of your code. The default branch is called
  `main`.
- **Clone:** Download a complete copy of a repository from a remote.
- **.gitignore:** A file that tells Git which files to ignore (not track).
- **Merge:** Combine changes from one branch into another.

---

You did it! You went from zero to a professional project setup. Your code is
version-controlled, backed up on GitHub, documented, tested, and scored by
Claudetini. That is a real development workflow.

Happy coding!
