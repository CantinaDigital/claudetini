#!/usr/bin/env bash
#
# Setup script for Claudetini demo projects.
#
# - recipe-cli: Verifies files are in place. Does NOT init git (that's the user's journey).
# - devlog: Initializes git with ~15 realistic commits, creates dirty working state.
#
# Usage: bash examples/setup_demos.sh
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECIPE_DIR="$SCRIPT_DIR/recipe-cli"
DEVLOG_DIR="$SCRIPT_DIR/devlog"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color
BOLD='\033[1m'

echo ""
echo -e "${BOLD}Claudetini Demo Projects Setup${NC}"
echo "=================================="
echo ""

# --- Verify recipe-cli ---

echo -e "${BLUE}[1/2] Checking recipe-cli (beginner project)...${NC}"

RECIPE_OK=true
for f in README.md requirements.txt .env setup.py GETTING_STARTED.md; do
    if [[ ! -f "$RECIPE_DIR/$f" ]]; then
        echo -e "  ${RED}MISSING${NC} $f"
        RECIPE_OK=false
    fi
done

for f in __init__.py main.py search.py api.py display.py __main__.py; do
    if [[ ! -f "$RECIPE_DIR/recipe_cli/$f" ]]; then
        echo -e "  ${RED}MISSING${NC} recipe_cli/$f"
        RECIPE_OK=false
    fi
done

if [[ "$RECIPE_OK" == true ]]; then
    echo -e "  ${GREEN}All files present.${NC}"
    echo -e "  ${YELLOW}Git NOT initialized (intentional — follow GETTING_STARTED.md).${NC}"
else
    echo -e "  ${RED}Some files are missing. Re-clone the repository.${NC}"
fi

echo ""

# --- Set up devlog ---

echo -e "${BLUE}[2/2] Setting up devlog (intermediate project)...${NC}"

# Verify files exist first
DEVLOG_OK=true
for f in CLAUDE.md README.md LICENSE pyproject.toml .env.example .gitignore config.example.py; do
    if [[ ! -f "$DEVLOG_DIR/$f" ]]; then
        echo -e "  ${RED}MISSING${NC} $f"
        DEVLOG_OK=false
    fi
done

if [[ ! -f "$DEVLOG_DIR/.claude/planning/ROADMAP.md" ]]; then
    echo -e "  ${RED}MISSING${NC} .claude/planning/ROADMAP.md"
    DEVLOG_OK=false
fi

if [[ ! -f "$DEVLOG_DIR/docs/ARCHITECTURE.md" ]]; then
    echo -e "  ${RED}MISSING${NC} docs/ARCHITECTURE.md"
    DEVLOG_OK=false
fi

if [[ ! -f "$DEVLOG_DIR/.github/workflows/ci.yml" ]]; then
    echo -e "  ${RED}MISSING${NC} .github/workflows/ci.yml"
    DEVLOG_OK=false
fi

if [[ "$DEVLOG_OK" != true ]]; then
    echo -e "  ${RED}Some files are missing. Re-clone the repository.${NC}"
    exit 1
fi

# Clean up any existing git state in devlog
if [[ -d "$DEVLOG_DIR/.git" ]]; then
    echo "  Removing existing git state..."
    rm -rf "$DEVLOG_DIR/.git"
fi

echo "  Initializing git repository..."
cd "$DEVLOG_DIR"
git init -q
git checkout -q -b main 2>/dev/null || true

# Configure local git user for demo commits (won't affect global config)
git config user.name "Demo Developer"
git config user.email "dev@example.com"

# --- Create realistic commit history ---
# Commits match roadmap item descriptions for reconciliation engine testing.
# Dates are spread over ~3 weeks to show timeline variety.

BASE_DATE="2025-12-01T09:00:00"

commit_at() {
    local date="$1"
    local msg="$2"
    shift 2
    GIT_AUTHOR_DATE="$date" GIT_COMMITTER_DATE="$date" git commit -q -m "$msg" "$@"
}

# Commit 1: Initial project setup
git add pyproject.toml LICENSE .gitignore .env.example
commit_at "2025-12-01T09:00:00" "Initial project setup"

# Commit 2: Create SQLite database schema
git add devlog/__init__.py devlog/database.py
commit_at "2025-12-01T14:30:00" "Create SQLite database schema with migrations"

# Commit 3: Implement TimeEntry model
git add devlog/models.py
commit_at "2025-12-02T10:00:00" "Implement TimeEntry and Project models"

# Commit 4: Add CRUD operations for time entries
git add devlog/utils/__init__.py devlog/utils/formatting.py devlog/utils/validation.py
commit_at "2025-12-03T11:00:00" "Add CRUD operations for time entries"

# Commit 5: Add CRUD operations for projects
git add devlog/services/__init__.py devlog/services/entries.py devlog/services/projects.py
commit_at "2025-12-04T09:30:00" "Add CRUD operations for projects"

# Commit 6: Write migration script (completes Milestone 1)
git add config.example.py
commit_at "2025-12-05T16:00:00" "Write migration script for database setup"

# Commit 7: Set up FastAPI app structure
git add devlog/app.py devlog/routes/__init__.py
commit_at "2025-12-08T09:00:00" "Set up FastAPI app structure"

# Commit 8: Create time entry endpoints (CRUD)
git add devlog/routes/entries.py
commit_at "2025-12-08T14:00:00" "Create time entry endpoints (CRUD)"

# Commit 9: Create project endpoints (CRUD)
git add devlog/routes/projects.py
commit_at "2025-12-09T10:30:00" "Create project endpoints (CRUD)"

# Commit 10: Add input validation with Pydantic
git add devlog/services/reports.py
commit_at "2025-12-10T11:00:00" "Add input validation with Pydantic models"

# Commit 11: Add error handling middleware and CLAUDE.md
git add CLAUDE.md
commit_at "2025-12-11T09:00:00" "Add error handling middleware and CLAUDE.md"

# Commit 12: Write API integration tests
git add tests/
commit_at "2025-12-12T14:00:00" "Write API integration tests"

# Commit 13: Add project docs
git add README.md docs/ .github/ .claude/
commit_at "2025-12-15T10:00:00" "Add README, architecture docs, CI workflow, and roadmap"

# Commit 14: Weekly summary aggregation (empty — logic was in reports.py already)
commit_at "2025-12-16T11:30:00" "Add weekly summary aggregation" --allow-empty

# Commit 15: Tag-based filtering
commit_at "2025-12-17T15:00:00" "Add tag-based filtering for time entries" --allow-empty

# --- Create dirty working state ---

echo "  Creating dirty working state..."

# Create stash entry FIRST (before other dirty state, since stash captures all changes)
echo "# WIP: Monthly summary" > devlog/services/monthly.py
echo "" >> devlog/services/monthly.py
echo "# TODO: Implement monthly aggregation" >> devlog/services/monthly.py
git add devlog/services/monthly.py
git stash push -q -m "WIP: monthly summary aggregation (Milestone 3)"
rm -f devlog/services/monthly.py

# Uncommitted change 1: Modify formatting.py (staged)
echo "" >> devlog/utils/formatting.py
echo "" >> devlog/utils/formatting.py
echo "def format_percentage(value: float) -> str:" >> devlog/utils/formatting.py
echo '    """Format a value as a percentage string."""' >> devlog/utils/formatting.py
echo '    return f"{value:.1f}%"' >> devlog/utils/formatting.py
git add devlog/utils/formatting.py

# Uncommitted change 2: Modify validation.py (unstaged)
echo "" >> devlog/utils/validation.py
echo "" >> devlog/utils/validation.py
echo "def validate_project_name(name: str) -> list[str]:" >> devlog/utils/validation.py
echo '    """Validate a project name."""' >> devlog/utils/validation.py
echo "    errors = []" >> devlog/utils/validation.py
echo "    if len(name) < 2:" >> devlog/utils/validation.py
echo '        errors.append("Project name must be at least 2 characters")' >> devlog/utils/validation.py
echo "    return errors" >> devlog/utils/validation.py

# Untracked file
cat > devlog/utils/cache.py << 'PYEOF'
"""Simple file-based cache for report results."""

import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta

CACHE_DIR = Path("/tmp/devlog_cache")
CACHE_TTL = timedelta(hours=1)


def get_cached(key: str) -> dict | None:
    """Get a value from the cache."""
    cache_file = CACHE_DIR / f"{_hash_key(key)}.json"
    if not cache_file.exists():
        return None

    data = json.loads(cache_file.read_text())
    cached_at = datetime.fromisoformat(data["cached_at"])

    if datetime.now() - cached_at > CACHE_TTL:
        cache_file.unlink()
        return None

    return data["value"]


def set_cached(key: str, value: dict) -> None:
    """Set a value in the cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{_hash_key(key)}.json"
    cache_file.write_text(json.dumps({
        "cached_at": datetime.now().isoformat(),
        "value": value,
    }))


def _hash_key(key: str) -> str:
    return hashlib.md5(key.encode()).hexdigest()
PYEOF

echo -e "  ${GREEN}Git repository initialized with 15 commits.${NC}"
echo -e "  ${GREEN}Dirty state: 1 staged + 1 modified + 1 untracked + 1 stash.${NC}"

# --- Print instructions ---

echo ""
echo -e "${BOLD}Setup Complete!${NC}"
echo ""
echo -e "${BOLD}Next steps:${NC}"
echo ""
echo -e "  1. Start Claudetini:"
echo -e "     ${BLUE}cd app && npm run tauri:dev${NC}"
echo ""
echo -e "  2. Register the demo projects:"
echo -e "     • Click ${BOLD}Add Path${NC} and select ${BLUE}examples/recipe-cli/${NC}"
echo -e "     • Click ${BOLD}Add Path${NC} and select ${BLUE}examples/devlog/${NC}"
echo ""
echo -e "  ${YELLOW}Start with recipe-cli if you're new to Git and Claude Code.${NC}"
echo -e "  Follow the ${BOLD}GETTING_STARTED.md${NC} walkthrough for a guided experience."
echo ""
echo -e "  ${GREEN}Start with devlog to explore the full dashboard immediately.${NC}"
echo ""
