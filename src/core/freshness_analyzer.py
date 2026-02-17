"""Code freshness analyzer and migration pattern tracker.

Analyzes git history to determine how recently files were modified, identifies
stale or abandoned code, and detects partial migrations between old and new
coding patterns (e.g., class vs functional React components).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

FreshnessCategory = Literal["fresh", "aging", "stale", "abandoned"]

# Thresholds in days for freshness categories
FRESH_THRESHOLD = 30
AGING_THRESHOLD = 90
STALE_THRESHOLD = 365

# Minimum percentage of both old and new style to flag a partial migration
MIGRATION_THRESHOLD = 0.20

# File extensions to scan for migration patterns
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb", ".php",
    ".cs", ".rs", ".swift", ".kt", ".scala",
}

SKIP_DIRECTORIES = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".tox", ".nox", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", ".eggs", "*.egg-info", ".coverage",
}


@dataclass
class FileFreshness:
    """Freshness information for a single file."""

    file_path: str
    last_modified: datetime | None
    days_since_modified: int
    commit_count: int
    category: FreshnessCategory
    last_author: str | None = None


@dataclass
class AgeDistribution:
    """Count of files in each freshness bucket."""

    fresh: int = 0
    aging: int = 0
    stale: int = 0
    abandoned: int = 0

    @property
    def total(self) -> int:
        return self.fresh + self.aging + self.stale + self.abandoned


@dataclass
class DeprecatedPatternMatch:
    """A single occurrence of a deprecated/old-style code pattern."""

    file_path: str
    line_number: int
    pattern_name: str
    matched_text: str
    replacement: str


@dataclass
class FreshnessReport:
    """Complete freshness analysis results."""

    files: list[FileFreshness] = field(default_factory=list)
    age_distribution: AgeDistribution = field(default_factory=AgeDistribution)
    stale_files: list[str] = field(default_factory=list)
    abandoned_files: list[str] = field(default_factory=list)
    single_commit_files: list[str] = field(default_factory=list)
    freshness_score: int = 100
    partial_migrations: list[dict] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def has_stale_code(self) -> bool:
        return len(self.stale_files) > 0 or len(self.abandoned_files) > 0


# Migration pattern pairs: (pattern_name, old_regex, new_regex, old_desc, new_desc, applicable_extensions)
MIGRATION_PATTERNS: list[tuple[str, str, str, str, str, set[str]]] = [
    (
        "React class vs functional components",
        r"\bclass\s+\w+\s+extends\s+(?:React\.)?(?:Component|PureComponent)\b",
        r"\bfunction\s+\w+\s*\([^)]*\)\s*\{[\s\S]*?return\s*[\s\S]*?<|const\s+\w+\s*[:=]\s*(?:React\.)?(?:FC|FunctionComponent|memo)\b|^\s*(?:export\s+)?(?:default\s+)?function\s+\w+.*\)\s*(?::\s*\w+)?\s*\{",
        "class components",
        "functional components",
        {".jsx", ".tsx", ".js", ".ts"},
    ),
    (
        "JavaScript var vs let/const",
        r"\bvar\s+\w+",
        r"\b(?:let|const)\s+\w+",
        "var declarations",
        "let/const declarations",
        {".js", ".jsx", ".ts", ".tsx"},
    ),
    (
        "Python %-formatting vs f-strings",
        r"""['"][^'"]*%[sdfreoaxXcbBn][^'"]*['"]\s*%\s*""",
        r"""\bf['"]""",
        "%-formatting",
        "f-strings",
        {".py"},
    ),
    (
        "JavaScript require vs import",
        r"\brequire\s*\(\s*['\"]",
        r"^\s*import\s+.*\s+from\s+['\"]",
        "require()",
        "ES import",
        {".js", ".jsx", ".ts", ".tsx"},
    ),
]


def _categorize(days: int) -> FreshnessCategory:
    """Categorize a file based on days since last modification."""
    if days < FRESH_THRESHOLD:
        return "fresh"
    elif days < AGING_THRESHOLD:
        return "aging"
    elif days < STALE_THRESHOLD:
        return "stale"
    else:
        return "abandoned"


class FreshnessAnalyzer:
    """Analyzes code freshness using git history and detects partial migrations."""

    def __init__(self, project_path: Path):
        self.project_path = project_path.resolve()

    def analyze(self) -> FreshnessReport:
        """Analyze file freshness across the project.

        Uses a single git log command to efficiently build per-file metadata,
        then categorizes files and detects partial code migrations.

        Returns a FreshnessReport with freshness data and migration analysis.
        """
        now = datetime.now(UTC)
        file_map = self._build_file_map()
        report = FreshnessReport()

        for rel_path, info in sorted(file_map.items()):
            last_modified = info["last_modified"]
            commit_count = info["commit_count"]
            last_author = info["last_author"]

            if last_modified:
                delta = now - last_modified
                days = delta.days
            else:
                days = 0

            category = _categorize(days)

            freshness = FileFreshness(
                file_path=rel_path,
                last_modified=last_modified,
                days_since_modified=days,
                commit_count=commit_count,
                category=category,
                last_author=last_author,
            )
            report.files.append(freshness)

            # Update distribution
            if category == "fresh":
                report.age_distribution.fresh += 1
            elif category == "aging":
                report.age_distribution.aging += 1
            elif category == "stale":
                report.age_distribution.stale += 1
                report.stale_files.append(rel_path)
            elif category == "abandoned":
                report.age_distribution.abandoned += 1
                report.abandoned_files.append(rel_path)

            if commit_count == 1:
                report.single_commit_files.append(rel_path)

        # Calculate freshness score: 100 - (stale * 2) - (abandoned * 5)
        stale_penalty = len(report.stale_files) * 2
        abandoned_penalty = len(report.abandoned_files) * 5
        report.freshness_score = max(0, 100 - stale_penalty - abandoned_penalty)

        # Detect partial migrations
        report.partial_migrations = self._detect_migrations()

        return report

    def _build_file_map(self) -> dict[str, dict]:
        """Build per-file metadata from a single git log command.

        Uses `git log --all --format=... --name-only` to extract last commit date,
        commit count, and last author for every file in O(1) git calls.
        """
        file_map: dict[str, dict] = {}

        try:
            result = subprocess.run(
                [
                    "git", "log", "--all",
                    "--format=%H|%aI|%an",
                    "--name-only",
                ],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return file_map

        if result.returncode != 0:
            return file_map

        current_date: datetime | None = None
        current_author: str | None = None

        for line in result.stdout.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Check if this is a commit header line (hash|date|author)
            if "|" in line:
                parts = line.split("|", 2)
                if len(parts) == 3:
                    _sha, date_str, author = parts
                    try:
                        current_date = datetime.fromisoformat(date_str)
                        # Ensure timezone-aware for comparison
                        if current_date.tzinfo is None:
                            current_date = current_date.replace(tzinfo=UTC)
                        current_author = author
                    except ValueError:
                        current_date = None
                        current_author = None
                    continue

            # This is a filename line
            file_path = line
            if file_path not in file_map:
                file_map[file_path] = {
                    "last_modified": current_date,
                    "last_author": current_author,
                    "commit_count": 1,
                }
            else:
                file_map[file_path]["commit_count"] += 1
                # Keep the most recent date (git log outputs newest first)
                # so the first occurrence is already the most recent

        return file_map

    def _detect_migrations(self) -> list[dict]:
        """Detect partial code migrations where old and new patterns coexist.

        For each pattern pair, counts files using old vs new style.
        If both exceed the MIGRATION_THRESHOLD (20%), flags as partial migration.
        """
        migrations: list[dict] = []

        compiled_patterns = [
            (
                name,
                re.compile(old_pat, re.MULTILINE),
                re.compile(new_pat, re.MULTILINE),
                old_desc,
                new_desc,
                exts,
            )
            for name, old_pat, new_pat, old_desc, new_desc, exts in MIGRATION_PATTERNS
        ]

        for name, old_re, new_re, _old_desc, _new_desc, exts in compiled_patterns:
            old_files: list[str] = []
            new_files: list[str] = []
            total_applicable = 0

            for file_path in self._get_code_files(exts):
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except (OSError, PermissionError):
                    continue

                rel_path = str(file_path.relative_to(self.project_path))
                total_applicable += 1

                has_old = bool(old_re.search(content))
                has_new = bool(new_re.search(content))

                if has_old:
                    old_files.append(rel_path)
                if has_new:
                    new_files.append(rel_path)

            if total_applicable == 0:
                continue

            old_ratio = len(old_files) / total_applicable
            new_ratio = len(new_files) / total_applicable

            if old_ratio > MIGRATION_THRESHOLD and new_ratio > MIGRATION_THRESHOLD:
                migrations.append({
                    "pattern_name": name,
                    "old_count": len(old_files),
                    "new_count": len(new_files),
                    "files_with_old": old_files,
                    "files_with_new": new_files,
                })

        return migrations

    def _get_code_files(self, extensions: set[str]) -> list[Path]:
        """Get code files matching the given extensions."""
        files = []
        for item in self.project_path.rglob("*"):
            if any(skip in item.parts for skip in SKIP_DIRECTORIES):
                continue
            if item.is_file() and item.suffix.lower() in extensions:
                files.append(item)
        return files
