"""Unified project plan models for Phase 2."""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class PlanItemStatus(Enum):
    """Status for unified plan items."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


class PlanSource(Enum):
    """Source of a plan item."""

    ROADMAP_FILE = "roadmap_file"      # Tier 1: Explicit files (ROADMAP.md, TODO.md)
    PHASE_FILE = "phase_file"          # Tier 2: Numbered files (phase1.md, sprint-2.md)
    PLANNING_DIR = "planning_dir"      # Tier 3: Planning directories
    CLAUDE_TASKS_API = "claude_tasks"  # Tier 4a: Claude Code todos JSON
    CLAUDE_PLANS = "claude_plans"      # Tier 4b: ~/.claude/plans/ global plans
    EMBEDDED_SECTION = "embedded"      # Tier 5: Embedded sections in README/CLAUDE.md
    HEURISTIC = "heuristic"            # Tier 6: Heuristic fallback


class ConflictResolution(Enum):
    """Resolution strategy for conflicting plan item states."""

    ROADMAP_WINS = "roadmap_wins"
    TASKS_API_WINS = "tasks_api_wins"
    MOST_RECENT_WINS = "most_recent"
    MANUAL = "manual"


@dataclass
class ConflictSource:
    """A source participating in a planning conflict."""

    source: PlanSource
    status: PlanItemStatus
    source_file: Path | None = None
    source_mtime: float | None = None


@dataclass
class PlanItemConflict:
    """Conflict between statuses for the same logical plan item."""

    item_id: str
    sources: list[ConflictSource]
    resolution: ConflictResolution
    resolved_status: PlanItemStatus


@dataclass
class PlanItem:
    """A single item found by the unified project plan scanner."""

    id: str
    content: str
    status: PlanItemStatus
    source: PlanSource
    source_file: Path | None = None
    source_line: int | None = None
    milestone: str | None = None
    priority: int = 3
    tags: list[str] = field(default_factory=list)
    conflicts: list[PlanItemConflict] = field(default_factory=list)


@dataclass
class PlanMilestone:
    """A milestone grouping unified plan items."""

    name: str
    items: list[PlanItem] = field(default_factory=list)


@dataclass
class UnifiedProjectPlan:
    """Canonical plan view aggregated from multiple planning sources."""

    items: list[PlanItem]
    milestones: list[PlanMilestone]
    sources_found: dict[PlanSource, list[Path]]
    scan_timestamp: datetime = field(default_factory=datetime.now)
    conflicts: list[PlanItemConflict] = field(default_factory=list)

    @property
    def progress_percent(self) -> float:
        """Overall completion percent."""
        if not self.items:
            return 0.0
        done = sum(1 for item in self.items if item.status == PlanItemStatus.DONE)
        return (done / len(self.items)) * 100

    @property
    def has_conflicts(self) -> bool:
        """Whether active conflicts exist."""
        return bool(self.conflicts)

    @property
    def active_conflicts(self) -> list[PlanItemConflict]:
        """Active conflicts list."""
        return self.conflicts

    def next_items(self, limit: int = 5) -> list[PlanItem]:
        """Return next pending or in-progress items."""
        candidates = [
            item
            for item in self.items
            if item.status in (PlanItemStatus.PENDING, PlanItemStatus.IN_PROGRESS)
        ]
        candidates.sort(
            key=lambda item: (item.status != PlanItemStatus.IN_PROGRESS, -item.priority, item.content)
        )
        return candidates[:limit]


def make_plan_item_id(content: str) -> str:
    """Create a stable item id from normalized content."""
    normalized = " ".join(content.lower().split())
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
