"""Unified 6-tier project plan scanner for Phase 2."""

import hashlib
import json
import logging
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .plan_conflicts import detect_conflicts, merge_items
from .plan_models import (
    PlanItem,
    PlanItemStatus,
    PlanMilestone,
    PlanSource,
    UnifiedProjectPlan,
    make_plan_item_id,
)

logger = logging.getLogger(__name__)

# Minimum relevance score for content-based plan matching
PLAN_RELEVANCE_THRESHOLD = 0.25

CHECKBOX_PATTERN = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s*(.+)$")
HEADER_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class ProjectPlanScanner:
    """Scan all known planning surfaces and return a unified plan."""

    EXPLICIT_FILES = {
        "ROADMAP.md",
        "roadmap.md",
        "TODO.md",
        "PLAN.md",
        "TASKS.md",
        "BACKLOG.md",
    }
    NUMBERED_PATTERNS = [
        re.compile(r"^phase[-_ ]?\d+.*\.md$", re.IGNORECASE),
        re.compile(r"^sprint[-_ ]?\d+.*\.md$", re.IGNORECASE),
        re.compile(r"^milestone[-_ ].*\.md$", re.IGNORECASE),
        re.compile(r"^epic[-_ ].*\.md$", re.IGNORECASE),
    ]
    PLANNING_DIRS = [
        Path("tasks"),
        Path("plans"),
        Path(".planning"),
        Path(".claude/plans"),
        Path("docs/roadmap"),
    ]
    EMBEDDED_KEYWORDS = ("roadmap", "todo", "tasks", "what's next", "next steps", "plan")
    HEURISTIC_KEYWORDS = ("roadmap", "todo", "backlog", "milestone", "sprint", "phase", "plan")

    def __init__(self, project_path: Path, claude_dir: Path | None = None):
        self.project_path = project_path.resolve()
        self.claude_dir = claude_dir or (Path.home() / ".claude")

    def scan(self) -> UnifiedProjectPlan:
        """Run all six tiers and return a unified project plan.

        If a consolidated roadmap exists at .claude/planning/ROADMAP.md,
        ONLY that file is scanned (single source of truth).
        """
        # Check for consolidated roadmap first (single source of truth)
        consolidated_path = self.project_path / ".claude" / "planning" / "ROADMAP.md"
        if consolidated_path.exists():
            return self._scan_consolidated_only(consolidated_path)

        all_items: list[PlanItem] = []
        sources_found: dict[PlanSource, set[Path]] = defaultdict(set)
        seen_files: set[Path] = set()

        tier_items, tier_sources = self._scan_tier_explicit_files()
        self._accumulate(all_items, sources_found, seen_files, tier_items, tier_sources)

        tier_items, tier_sources = self._scan_tier_numbered_files(excluded=seen_files)
        self._accumulate(all_items, sources_found, seen_files, tier_items, tier_sources)

        tier_items, tier_sources = self._scan_tier_planning_dirs()
        self._accumulate(all_items, sources_found, seen_files, tier_items, tier_sources)

        tier_items, tier_sources = self._scan_tier_claude_tasks()
        self._accumulate(all_items, sources_found, seen_files, tier_items, tier_sources)

        tier_items, tier_sources = self._scan_tier_global_claude_plans()
        self._accumulate(all_items, sources_found, seen_files, tier_items, tier_sources)

        tier_items, tier_sources = self._scan_tier_embedded_sections()
        self._accumulate(all_items, sources_found, seen_files, tier_items, tier_sources)

        tier_items, tier_sources = self._scan_tier_heuristic_fallback(excluded=seen_files)
        self._accumulate(all_items, sources_found, seen_files, tier_items, tier_sources)

        conflicts = detect_conflicts(all_items)
        merged_items = merge_items(all_items, conflicts)
        milestones = self._build_milestones(merged_items)

        return UnifiedProjectPlan(
            items=merged_items,
            milestones=milestones,
            sources_found={source: sorted(paths) for source, paths in sources_found.items()},
            scan_timestamp=datetime.now(),
            conflicts=conflicts,
        )

    def _scan_consolidated_only(self, consolidated_path: Path) -> UnifiedProjectPlan:
        """Scan only the consolidated roadmap (single source of truth).

        This is used when .claude/planning/ROADMAP.md exists, indicating
        that plan consolidation has been performed.
        """
        items = self._parse_markdown_file(consolidated_path, PlanSource.ROADMAP_FILE)
        milestones = self._build_milestones(items)

        return UnifiedProjectPlan(
            items=items,
            milestones=milestones,
            sources_found={PlanSource.ROADMAP_FILE: [consolidated_path]},
            scan_timestamp=datetime.now(),
            conflicts=[],  # No conflicts possible with single source
        )

    def _scan_tier_explicit_files(self) -> tuple[list[PlanItem], dict[PlanSource, set[Path]]]:
        items: list[PlanItem] = []
        sources: dict[PlanSource, set[Path]] = defaultdict(set)

        for candidate in sorted(self.EXPLICIT_FILES):
            for path in (self.project_path / candidate, self.project_path / "docs" / candidate):
                if not path.exists() or not path.is_file():
                    continue
                parsed = self._parse_markdown_file(path, PlanSource.ROADMAP_FILE)
                items.extend(parsed)
                if parsed:
                    sources[PlanSource.ROADMAP_FILE].add(path)

        return items, sources

    def _scan_tier_numbered_files(
        self,
        excluded: set[Path],
    ) -> tuple[list[PlanItem], dict[PlanSource, set[Path]]]:
        items: list[PlanItem] = []
        sources: dict[PlanSource, set[Path]] = defaultdict(set)

        for path in self.project_path.rglob("*.md"):
            if path in excluded or not path.is_file():
                continue
            if not any(pattern.match(path.name) for pattern in self.NUMBERED_PATTERNS):
                continue
            parsed = self._parse_markdown_file(path, PlanSource.PHASE_FILE)
            items.extend(parsed)
            if parsed:
                sources[PlanSource.PHASE_FILE].add(path)

        return items, sources

    def _scan_tier_planning_dirs(self) -> tuple[list[PlanItem], dict[PlanSource, set[Path]]]:
        items: list[PlanItem] = []
        sources: dict[PlanSource, set[Path]] = defaultdict(set)

        for rel_dir in self.PLANNING_DIRS:
            planning_dir = self.project_path / rel_dir
            if not planning_dir.exists() or not planning_dir.is_dir():
                continue

            for path in planning_dir.rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in {".md", ".markdown"}:
                    continue
                parsed = self._parse_markdown_file(path, PlanSource.PLANNING_DIR)
                items.extend(parsed)
                if parsed:
                    sources[PlanSource.PLANNING_DIR].add(path)

        return items, sources

    def _scan_tier_claude_tasks(self) -> tuple[list[PlanItem], dict[PlanSource, set[Path]]]:
        items: list[PlanItem] = []
        sources: dict[PlanSource, set[Path]] = defaultdict(set)

        project_hash = hashlib.md5(str(self.project_path).encode("utf-8")).hexdigest()[:16]
        project_claude_dir = self.claude_dir / "projects" / project_hash

        if not project_claude_dir.exists():
            return items, sources

        # Project-local tasks file.
        project_todos = project_claude_dir / "todos.json"
        if project_todos.exists():
            parsed = self._parse_todo_file(project_todos)
            items.extend(parsed)
            if parsed:
                sources[PlanSource.CLAUDE_TASKS_API].add(project_todos)

        # Session-scoped todo files under ~/.claude/todos.
        todos_dir = self.claude_dir / "todos"
        session_ids = {path.stem for path in project_claude_dir.glob("*.jsonl")}
        if todos_dir.exists() and session_ids:
            for todo_file in todos_dir.glob("*.json"):
                if not any(session_id in todo_file.name for session_id in session_ids):
                    continue
                parsed = self._parse_todo_file(todo_file)
                items.extend(parsed)
                if parsed:
                    sources[PlanSource.CLAUDE_TASKS_API].add(todo_file)

        return items, sources

    def _scan_tier_global_claude_plans(self) -> tuple[list[PlanItem], dict[PlanSource, set[Path]]]:
        """Tier 4b: Scan ~/.claude/plans/ for project-relevant plans.

        Uses a 3-layer correlation strategy:
        1. Session correlation via history.jsonl
        2. Content-based matching (file paths, project name, package names)
        3. Timestamp correlation as a boost factor
        """
        items: list[PlanItem] = []
        sources: dict[PlanSource, set[Path]] = defaultdict(set)

        plans_dir = self.claude_dir / "plans"
        if not plans_dir.exists() or not plans_dir.is_dir():
            return items, sources

        # Gather project signals for content matching
        project_signals = self._gather_project_signals()

        # Get session activity windows for timestamp correlation
        session_windows = self._get_session_time_windows()

        matched_plans: list[tuple[Path, float]] = []

        for plan_path in plans_dir.glob("*.md"):
            if not plan_path.is_file():
                continue

            try:
                content = plan_path.read_text()
            except OSError:
                continue

            score = 0.0

            # Layer 1: Check if plan was created during a project session
            # (via timestamp overlap with session windows)
            plan_mtime = plan_path.stat().st_mtime
            for start_ts, end_ts in session_windows:
                if start_ts <= plan_mtime <= end_ts:
                    score += 0.4  # Strong signal
                    break

            # Layer 2: Content-based matching
            content_lower = content.lower()

            # Project name match
            if project_signals["name"].lower() in content_lower:
                score += 0.3

            # File path matches
            path_matches = sum(
                1 for fp in project_signals["key_files"]
                if fp.lower() in content_lower
            )
            score += min(path_matches * 0.1, 0.3)  # Cap at 0.3

            # Package/module name matches
            pkg_matches = sum(
                1 for pkg in project_signals["packages"]
                if pkg.lower() in content_lower
            )
            score += min(pkg_matches * 0.15, 0.3)  # Cap at 0.3

            # Directory structure matches
            dir_matches = sum(
                1 for d in project_signals["directories"]
                if d.lower() in content_lower
            )
            score += min(dir_matches * 0.05, 0.15)  # Cap at 0.15

            if score >= PLAN_RELEVANCE_THRESHOLD:
                matched_plans.append((plan_path, score))

        # Sort by score descending, take top matches
        matched_plans.sort(key=lambda x: -x[1])

        for plan_path, _score in matched_plans[:5]:  # Limit to top 5 plans
            parsed = self._parse_markdown_file(plan_path, PlanSource.CLAUDE_PLANS)
            items.extend(parsed)
            if parsed:
                sources[PlanSource.CLAUDE_PLANS].add(plan_path)

        return items, sources

    def _gather_project_signals(self) -> dict:
        """Extract identifying signals from current project for plan matching."""
        signals = {
            "name": self.project_path.name,
            "key_files": [],
            "packages": [],
            "directories": [],
        }

        # Key source directories
        for d in ["src", "lib", "app", "components", "pages", "api"]:
            if (self.project_path / d).exists():
                signals["directories"].append(d)

        # Key source files (relative paths)
        patterns = ["src/**/*.py", "lib/**/*.ts", "app/**/*.tsx", "**/*.rs"]
        for pattern in patterns:
            for p in list(self.project_path.glob(pattern))[:15]:
                try:
                    rel = str(p.relative_to(self.project_path))
                    signals["key_files"].append(rel)
                except ValueError:
                    pass

        # Package name from pyproject.toml
        pyproject = self.project_path / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text()
                # Simple extraction - look for name = "..."
                match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
                if match:
                    signals["packages"].append(match.group(1))
            except OSError:
                pass

        # Package name from package.json
        pkg_json = self.project_path / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text())
                if "name" in data:
                    signals["packages"].append(data["name"])
            except (OSError, json.JSONDecodeError):
                pass

        # Cargo.toml package name
        cargo = self.project_path / "Cargo.toml"
        if cargo.exists():
            try:
                content = cargo.read_text()
                match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
                if match:
                    signals["packages"].append(match.group(1))
            except OSError:
                pass

        return signals

    def _get_session_time_windows(self) -> list[tuple[float, float]]:
        """Get time windows when sessions were active on this project."""
        windows = []
        project_dir = self._get_project_claude_dir()

        if not project_dir or not project_dir.exists():
            return windows

        # Session JSONL files have timestamps we can use
        for jsonl_path in project_dir.glob("*.jsonl"):
            try:
                stat = jsonl_path.stat()
                # Estimate session window from file times
                # ctime = creation, mtime = last modification
                start_ts = stat.st_birthtime if hasattr(stat, 'st_birthtime') else stat.st_ctime
                end_ts = stat.st_mtime
                # Add some buffer (plans might be created slightly after session ends)
                windows.append((start_ts - 300, end_ts + 600))
            except OSError:
                pass

        return windows

    def _get_project_sessions_from_history(self) -> set[str]:
        """Get session IDs that have worked on this project from history.jsonl."""
        sessions = set()
        history_path = self.claude_dir / "history.jsonl"

        if not history_path.exists():
            return sessions

        project_str = str(self.project_path)

        try:
            with open(history_path) as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("project") == project_str:
                            session_id = entry.get("sessionId")
                            if session_id:
                                sessions.add(session_id)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

        return sessions

    def _get_project_claude_dir(self) -> Path | None:
        """Get the Claude project directory for this project."""
        # Claude uses path with / replaced by -
        path_key = str(self.project_path).replace("/", "-")
        project_dir = self.claude_dir / "projects" / path_key

        if project_dir.exists():
            return project_dir

        # Fallback: try hash-based lookup (older Claude versions)
        project_hash = hashlib.md5(str(self.project_path).encode("utf-8")).hexdigest()[:16]
        hash_dir = self.claude_dir / "projects" / project_hash
        if hash_dir.exists():
            return hash_dir

        return None

    def _scan_tier_embedded_sections(self) -> tuple[list[PlanItem], dict[PlanSource, set[Path]]]:
        items: list[PlanItem] = []
        sources: dict[PlanSource, set[Path]] = defaultdict(set)

        candidates = [
            self.project_path / "README.md",
            self.project_path / "CLAUDE.md",
            self.project_path / "docs" / "README.md",
        ]

        for path in candidates:
            if not path.exists() or not path.is_file():
                continue
            parsed = self._parse_embedded_sections(path)
            items.extend(parsed)
            if parsed:
                sources[PlanSource.EMBEDDED_SECTION].add(path)

        return items, sources

    def _scan_tier_heuristic_fallback(
        self,
        excluded: set[Path],
    ) -> tuple[list[PlanItem], dict[PlanSource, set[Path]]]:
        items: list[PlanItem] = []
        sources: dict[PlanSource, set[Path]] = defaultdict(set)

        for path in self.project_path.rglob("*.md"):
            if path in excluded or not path.is_file():
                continue
            try:
                content = path.read_text()
            except OSError:
                continue

            checkbox_count = len(CHECKBOX_PATTERN.findall(content))
            if checkbox_count < 3:
                continue

            content_lower = content.lower()
            if not any(keyword in content_lower for keyword in self.HEURISTIC_KEYWORDS):
                continue

            parsed = self._parse_markdown_file(path, PlanSource.HEURISTIC)
            items.extend(parsed)
            if parsed:
                sources[PlanSource.HEURISTIC].add(path)

        return items, sources

    def _parse_markdown_file(self, path: Path, source: PlanSource) -> list[PlanItem]:
        try:
            lines = path.read_text().splitlines()
        except OSError:
            return []

        items: list[PlanItem] = []
        milestone: str | None = None
        for line_number, line in enumerate(lines, start=1):
            header_match = HEADER_PATTERN.match(line)
            if header_match:
                level = len(header_match.group(1))
                title = header_match.group(2).strip()
                # Only ## headings create milestones; ### and deeper are
                # sub-sections that keep items under the parent milestone.
                if level <= 2:
                    milestone = title
                continue

            checkbox_match = CHECKBOX_PATTERN.match(line)
            if not checkbox_match:
                continue
            marker, content = checkbox_match.groups()
            content = content.strip()
            items.append(
                PlanItem(
                    id=make_plan_item_id(content),
                    content=content,
                    status=self._status_from_checkbox(marker),
                    source=source,
                    source_file=path,
                    source_line=line_number,
                    milestone=milestone,
                    priority=self._priority_from_content(content),
                    tags=self._extract_tags(content),
                )
            )

        return items

    def _parse_embedded_sections(self, path: Path) -> list[PlanItem]:
        try:
            lines = path.read_text().splitlines()
        except OSError:
            return []

        items: list[PlanItem] = []
        active_section: str | None = None
        active_level = 0

        for line_number, line in enumerate(lines, start=1):
            header_match = HEADER_PATTERN.match(line)
            if header_match:
                level = len(header_match.group(1))
                title = header_match.group(2).strip()
                if any(keyword in title.lower() for keyword in self.EMBEDDED_KEYWORDS):
                    active_section = title
                    active_level = level
                elif active_section is not None and level <= active_level:
                    active_section = None
                continue

            if active_section is None:
                continue

            checkbox_match = CHECKBOX_PATTERN.match(line)
            if not checkbox_match:
                continue
            marker, content = checkbox_match.groups()
            content = content.strip()
            items.append(
                PlanItem(
                    id=make_plan_item_id(content),
                    content=content,
                    status=self._status_from_checkbox(marker),
                    source=PlanSource.EMBEDDED_SECTION,
                    source_file=path,
                    source_line=line_number,
                    milestone=active_section,
                    priority=self._priority_from_content(content),
                    tags=self._extract_tags(content),
                )
            )

        return items

    def _parse_todo_file(self, path: Path) -> list[PlanItem]:
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return []

        if isinstance(data, dict):
            raw_todos = data.get("todos", [])
        elif isinstance(data, list):
            raw_todos = data
        else:
            return []

        items: list[PlanItem] = []
        for todo in raw_todos:
            if not isinstance(todo, dict):
                continue

            content = (todo.get("content") or "").strip()
            if not content:
                continue

            status = self._status_from_todo(todo.get("status"))
            items.append(
                PlanItem(
                    id=make_plan_item_id(content),
                    content=content,
                    status=status,
                    source=PlanSource.CLAUDE_TASKS_API,
                    source_file=path,
                    source_line=None,
                    milestone=todo.get("milestone"),
                    priority=self._priority_from_todo(todo.get("priority")),
                    tags=self._extract_tags(content),
                )
            )

        return items

    def _build_milestones(self, items: list[PlanItem]) -> list[PlanMilestone]:
        grouped: dict[str, list[PlanItem]] = defaultdict(list)
        order: list[str] = []
        for item in items:
            milestone = item.milestone or "Backlog"
            if milestone not in grouped:
                order.append(milestone)
            grouped[milestone].append(item)

        return [PlanMilestone(name=name, items=grouped[name]) for name in order]

    @staticmethod
    def _status_from_checkbox(marker: str) -> PlanItemStatus:
        return PlanItemStatus.DONE if marker.lower() == "x" else PlanItemStatus.PENDING

    @staticmethod
    def _status_from_todo(value: str | None) -> PlanItemStatus:
        status = (value or "").lower()
        if status == "completed":
            return PlanItemStatus.DONE
        if status == "in_progress":
            return PlanItemStatus.IN_PROGRESS
        if status == "blocked":
            return PlanItemStatus.BLOCKED
        return PlanItemStatus.PENDING

    @staticmethod
    def _extract_tags(content: str) -> list[str]:
        return [f"#{tag}" for tag in re.findall(r"#([a-zA-Z0-9_-]+)", content)]

    @staticmethod
    def _priority_from_todo(value: str | None) -> int:
        priority = (value or "").lower()
        if priority == "high":
            return 5
        if priority == "low":
            return 2
        return 3

    @staticmethod
    def _priority_from_content(content: str) -> int:
        normalized = content.lower()
        if "[p1]" in normalized or "high priority" in normalized:
            return 5
        if "[p2]" in normalized:
            return 4
        if "[p3]" in normalized:
            return 3
        if "[p4]" in normalized:
            return 2
        if "[p5]" in normalized:
            return 1
        return 3

    @staticmethod
    def _accumulate(
        all_items: list[PlanItem],
        sources_found: dict[PlanSource, set[Path]],
        seen_files: set[Path],
        tier_items: list[PlanItem],
        tier_sources: dict[PlanSource, set[Path]],
    ) -> None:
        all_items.extend(tier_items)
        for source, paths in tier_sources.items():
            sources_found[source].update(paths)
            seen_files.update(paths)
