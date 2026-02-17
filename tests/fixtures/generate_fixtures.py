"""Generate test project fixtures for E2E testing.

Creates 10 test projects with varying states to validate all app functionality.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "projects"


def run_git(cwd: Path, *args) -> bool:
    """Run a git command in the given directory."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def create_fixture(name: str, setup_fn) -> Path:
    """Create a fixture directory and run setup function."""
    fixture_path = FIXTURES_DIR / name
    if fixture_path.exists():
        shutil.rmtree(fixture_path)
    fixture_path.mkdir(parents=True)
    setup_fn(fixture_path)
    print(f"✓ Created: {name}")
    return fixture_path


# =============================================================================
# FIXTURE 1: Empty Project
# =============================================================================
def setup_empty_project(path: Path) -> None:
    """Fresh project with only git init, no roadmap, no CLAUDE.md."""
    run_git(path, "init")
    run_git(path, "config", "user.email", "test@test.com")
    run_git(path, "config", "user.name", "Test User")

    # Just a basic file
    (path / "README.md").write_text("# Empty Project\n\nThis is a fresh project.\n")
    run_git(path, "add", ".")
    run_git(path, "commit", "-m", "Initial commit")


# =============================================================================
# FIXTURE 2: Single Roadmap (Clean)
# =============================================================================
def setup_single_roadmap(path: Path) -> None:
    """Clean project with one ROADMAP.md - ideal state."""
    run_git(path, "init")
    run_git(path, "config", "user.email", "test@test.com")
    run_git(path, "config", "user.name", "Test User")

    (path / "README.md").write_text("# Single Roadmap Project\n")
    (path / "CLAUDE.md").write_text("# Project Guide\n\nFollow standard conventions.\n")

    (path / "ROADMAP.md").write_text("""# Project Roadmap

## Milestone 1: Foundation
- [x] Project setup
- [x] Basic structure
- [ ] Core functionality
- [ ] Error handling

## Milestone 2: Features
- [ ] Feature A
- [ ] Feature B
- [ ] Feature C

## Milestone 3: Polish
- [ ] Documentation
- [ ] Testing
- [ ] Release prep
""")

    run_git(path, "add", ".")
    run_git(path, "commit", "-m", "Initial project setup")


# =============================================================================
# FIXTURE 3: Multiple Planning Sources (Needs Consolidation)
# =============================================================================
def setup_multiple_sources(path: Path) -> None:
    """Project with multiple conflicting planning files."""
    run_git(path, "init")
    run_git(path, "config", "user.email", "test@test.com")
    run_git(path, "config", "user.name", "Test User")

    (path / "README.md").write_text("# Multi-Source Project\n")

    # Main roadmap
    (path / "ROADMAP.md").write_text("""# Roadmap

## Phase 1
- [x] Setup project
- [ ] Implement core
- [ ] Add tests
""")

    # Duplicate in .planning
    (path / ".planning").mkdir()
    (path / ".planning" / "ROADMAP.md").write_text("""# Master Roadmap

## Phase 1: Setup
- [x] Setup project
- [x] Configure tooling
- [ ] Implement core

## Phase 2: Development
- [ ] Feature X
- [ ] Feature Y
""")

    # Phase file
    (path / "PHASE-1-PLAN.md").write_text("""# Phase 1 Plan

## Tasks
- [x] Setup project
- [ ] Implement core logic
- [ ] Write unit tests
- [ ] Integration tests
""")

    # Embedded in CLAUDE.md
    (path / "CLAUDE.md").write_text("""# Project Guide

## Current Status
<!-- claudetini:managed -->
## What's Done
- [x] Project setup

## What's In Progress
- [ ] Core implementation
<!-- /claudetini:managed -->
""")

    run_git(path, "add", ".")
    run_git(path, "commit", "-m", "Project with multiple planning sources")


# =============================================================================
# FIXTURE 4: Completed Project (100%)
# =============================================================================
def setup_completed_project(path: Path) -> None:
    """Project with all roadmap items completed."""
    run_git(path, "init")
    run_git(path, "config", "user.email", "test@test.com")
    run_git(path, "config", "user.name", "Test User")

    (path / "README.md").write_text("# Completed Project\n\nAll tasks done!\n")
    (path / "CLAUDE.md").write_text("# Project Guide\n")

    (path / "ROADMAP.md").write_text("""# Project Roadmap

## Milestone 1: Setup
- [x] Initialize repository
- [x] Configure dependencies
- [x] Set up CI/CD

## Milestone 2: Core
- [x] Implement main logic
- [x] Add error handling
- [x] Write tests

## Milestone 3: Release
- [x] Documentation
- [x] Version bump
- [x] Deploy
""")

    run_git(path, "add", ".")
    run_git(path, "commit", "-m", "Completed project")


# =============================================================================
# FIXTURE 5: Partial Progress (Mixed State)
# =============================================================================
def setup_partial_progress(path: Path) -> None:
    """Project with some milestones complete, some in progress."""
    run_git(path, "init")
    run_git(path, "config", "user.email", "test@test.com")
    run_git(path, "config", "user.name", "Test User")

    (path / "README.md").write_text("# Partial Progress Project\n")
    (path / "CLAUDE.md").write_text("# Project Guide\n")

    # Create some source files
    (path / "src").mkdir()
    (path / "src" / "__init__.py").write_text("")
    (path / "src" / "main.py").write_text("def main():\n    print('Hello')\n")

    (path / "ROADMAP.md").write_text("""# Project Roadmap

## Milestone 1: Foundation (Complete)
- [x] Project structure
- [x] Dependencies
- [x] Basic config

## Milestone 2: Core Features (In Progress)
- [x] User authentication
- [x] Database setup
- [ ] API endpoints
- [ ] Background jobs

## Milestone 3: Advanced Features
- [ ] Caching layer
- [ ] Rate limiting
- [ ] Analytics

## Milestone 4: Polish
- [ ] Performance optimization
- [ ] Security audit
- [ ] Documentation
""")

    run_git(path, "add", ".")
    run_git(path, "commit", "-m", "Partial progress")


# =============================================================================
# FIXTURE 6: No Git Repo
# =============================================================================
def setup_no_git(path: Path) -> None:
    """Project without git initialization."""
    (path / "README.md").write_text("# No Git Project\n\nNot a git repository.\n")
    (path / "ROADMAP.md").write_text("""# Roadmap

## Phase 1
- [ ] Initialize git
- [ ] Set up project
""")


# =============================================================================
# FIXTURE 7: Dirty Git State
# =============================================================================
def setup_dirty_git(path: Path) -> None:
    """Project with uncommitted changes and untracked files."""
    run_git(path, "init")
    run_git(path, "config", "user.email", "test@test.com")
    run_git(path, "config", "user.name", "Test User")

    (path / "README.md").write_text("# Dirty Git Project\n")
    (path / "ROADMAP.md").write_text("""# Roadmap

## Tasks
- [x] Initial setup
- [ ] Clean up
""")

    run_git(path, "add", ".")
    run_git(path, "commit", "-m", "Initial commit")

    # Now make it dirty
    (path / "README.md").write_text("# Dirty Git Project\n\nModified but not committed.\n")
    (path / "untracked.txt").write_text("This file is untracked\n")
    (path / "src").mkdir()
    (path / "src" / "new_file.py").write_text("# New untracked file\n")


# =============================================================================
# FIXTURE 8: Quality Gate Failures
# =============================================================================
def setup_quality_failures(path: Path) -> None:
    """Project with code that would fail quality gates."""
    run_git(path, "init")
    run_git(path, "config", "user.email", "test@test.com")
    run_git(path, "config", "user.name", "Test User")

    (path / "README.md").write_text("# Quality Failures Project\n")
    (path / "CLAUDE.md").write_text("# Project Guide\n")

    (path / "ROADMAP.md").write_text("""# Roadmap

## Tasks
- [x] Setup
- [ ] Fix lint errors
- [ ] Fix type errors
- [ ] Add tests
""")

    # Python file with issues
    (path / "src").mkdir()
    (path / "src" / "__init__.py").write_text("")
    (path / "src" / "bad_code.py").write_text('''"""Module with quality issues."""

import os, sys, json  # Multiple imports on one line
import unused_module  # Unused import

def badly_formatted_function(x,y,z):  # No spaces after commas
    """Missing type hints."""
    if x==1:  # No spaces around operator
        return y+z
    else:
        return None  # Inconsistent return

class badlyNamedClass:  # Should be PascalCase
    def __init__(self):
        self.x = 1

    def method_without_docstring(self):
        pass

# TODO: This is a fixme that should be addressed
SECRET_KEY = "hardcoded-secret-12345"  # Security issue
''')

    # Test file that would fail
    (path / "tests").mkdir()
    (path / "tests" / "__init__.py").write_text("")
    (path / "tests" / "test_main.py").write_text('''"""Tests that fail."""

def test_failing():
    assert 1 == 2, "This test always fails"

def test_another_failure():
    raise Exception("Intentional failure")
''')

    run_git(path, "add", ".")
    run_git(path, "commit", "-m", "Code with quality issues")


# =============================================================================
# FIXTURE 9: Large Roadmap
# =============================================================================
def setup_large_roadmap(path: Path) -> None:
    """Project with many milestones and items."""
    run_git(path, "init")
    run_git(path, "config", "user.email", "test@test.com")
    run_git(path, "config", "user.name", "Test User")

    (path / "README.md").write_text("# Large Roadmap Project\n")
    (path / "CLAUDE.md").write_text("# Project Guide\n")

    # Generate large roadmap
    lines = ["# Project Roadmap\n"]
    total_done = 0
    total_items = 0

    for milestone in range(1, 11):  # 10 milestones
        lines.append(f"\n## Milestone {milestone}: Phase {milestone}")
        for item in range(1, 16):  # 15 items per milestone
            total_items += 1
            # Make ~60% done
            if milestone < 7 or (milestone == 7 and item < 8):
                lines.append(f"- [x] Task {milestone}.{item}: Implementation detail")
                total_done += 1
            else:
                lines.append(f"- [ ] Task {milestone}.{item}: Implementation detail")

    lines.append(f"\n---\n**Progress:** {total_done}/{total_items} ({int(total_done/total_items*100)}%)\n")

    (path / "ROADMAP.md").write_text("\n".join(lines))

    run_git(path, "add", ".")
    run_git(path, "commit", "-m", "Large roadmap project")


# =============================================================================
# FIXTURE 10: Consolidated (Already Clean)
# =============================================================================
def setup_already_consolidated(path: Path) -> None:
    """Project that has already been consolidated - single source of truth."""
    run_git(path, "init")
    run_git(path, "config", "user.email", "test@test.com")
    run_git(path, "config", "user.name", "Test User")

    (path / "README.md").write_text("# Consolidated Project\n")
    (path / "CLAUDE.md").write_text("# Project Guide\n\nSingle source of truth in .claude/planning/\n")

    # Create consolidated roadmap location
    (path / ".claude" / "planning").mkdir(parents=True)
    (path / ".claude" / "planning" / "ROADMAP.md").write_text("""# Project Roadmap

_Consolidated on 2024-01-15 10:30_

## Milestone 1: Foundation
- [x] Project setup
- [x] Dependencies configured
- [x] Basic structure

## Milestone 2: Core Features
- [x] User authentication
- [x] Database integration
- [ ] API endpoints
- [ ] Background processing

## Milestone 3: Polish
- [ ] Documentation
- [ ] Testing
- [ ] Deployment

---

**Progress:** 5/10 items (50% complete)
""")

    # Archive directory to show consolidation happened
    (path / ".claude" / "planning" / "archive" / "20240115_103000").mkdir(parents=True)
    (path / ".claude" / "planning" / "archive" / "20240115_103000" / "ROADMAP.md").write_text(
        "# Old Roadmap\n\nThis was the original roadmap before consolidation.\n"
    )

    run_git(path, "add", ".")
    run_git(path, "commit", "-m", "Consolidated project")


# =============================================================================
# MAIN GENERATOR
# =============================================================================
FIXTURES = [
    ("01_empty_project", setup_empty_project),
    ("02_single_roadmap", setup_single_roadmap),
    ("03_multiple_sources", setup_multiple_sources),
    ("04_completed_project", setup_completed_project),
    ("05_partial_progress", setup_partial_progress),
    ("06_no_git", setup_no_git),
    ("07_dirty_git", setup_dirty_git),
    ("08_quality_failures", setup_quality_failures),
    ("09_large_roadmap", setup_large_roadmap),
    ("10_already_consolidated", setup_already_consolidated),
]


def generate_all() -> None:
    """Generate all test fixtures."""
    print("Generating test fixtures...")
    print("=" * 50)

    if FIXTURES_DIR.exists():
        shutil.rmtree(FIXTURES_DIR)
    FIXTURES_DIR.mkdir(parents=True)

    for name, setup_fn in FIXTURES:
        try:
            create_fixture(name, setup_fn)
        except Exception as e:
            print(f"✗ Failed: {name} - {e}")

    print("=" * 50)
    print(f"Generated {len(FIXTURES)} test fixtures in {FIXTURES_DIR}")

    # Create manifest
    manifest = {
        "fixtures": [
            {
                "name": name,
                "path": str(FIXTURES_DIR / name),
                "description": setup_fn.__doc__,
            }
            for name, setup_fn in FIXTURES
        ]
    }
    (FIXTURES_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print("Created manifest.json")


if __name__ == "__main__":
    generate_all()
