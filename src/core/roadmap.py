"""Roadmap parsing and progress tracking."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .plan_models import PlanItemStatus, PlanSource
from .plan_scanner import ProjectPlanScanner


@dataclass
class AgentGroup:
    """Agent group annotation from ### headings in a milestone."""

    name: str
    task_indices: list[int]


@dataclass
class RoadmapItem:
    """A single item in a roadmap milestone."""

    text: str
    completed: bool = False
    line_number: int = 0
    source: str | None = None
    conflict: bool = False

    @property
    def done(self) -> bool:
        """Alias for completed for UI compatibility."""
        return self.completed

    @classmethod
    def from_line(cls, line: str, line_number: int = 0) -> Optional["RoadmapItem"]:
        """Parse a roadmap item from a markdown line.

        Supports:
        - [x] Completed item
        - [ ] Pending item
        - [X] Completed item (uppercase)
        """
        # Match checkbox pattern: - [x] or - [ ]
        match = re.match(r"^\s*[-*]\s*\[([ xX])\]\s*(.+)$", line)
        if not match:
            return None

        checkbox, text = match.groups()
        completed = checkbox.lower() == "x"
        return cls(text=text.strip(), completed=completed, line_number=line_number)

    def to_markdown(self) -> str:
        """Convert item back to markdown format."""
        checkbox = "[x]" if self.completed else "[ ]"
        return f"- {checkbox} {self.text}"

    @property
    def source_badge(self) -> str:
        """Compact source label for UI badges."""
        badges = {
            "roadmap_file": "ROADMAP",
            "phase_file": "PHASE",
            "planning_dir": "PLANNING",
            "claude_tasks": "CLAUDE",
            "embedded": "EMBEDDED",
            "heuristic": "HEURISTIC",
        }
        return badges.get(self.source or "", (self.source or "ROADMAP").upper())


@dataclass
class Milestone:
    """A milestone containing multiple roadmap items."""

    name: str
    items: list[RoadmapItem] = field(default_factory=list)
    line_number: int = 0

    @property
    def title(self) -> str:
        """Alias for name for UI compatibility."""
        return self.name

    @property
    def total_items(self) -> int:
        """Total number of items in this milestone."""
        return len(self.items)

    @property
    def completed_items(self) -> int:
        """Number of completed items."""
        return sum(1 for item in self.items if item.completed)

    @property
    def progress_percent(self) -> float:
        """Progress as a percentage (0-100)."""
        if self.total_items == 0:
            return 0.0
        return (self.completed_items / self.total_items) * 100

    @property
    def is_complete(self) -> bool:
        """Whether all items in this milestone are complete."""
        return self.total_items > 0 and self.completed_items == self.total_items

    @property
    def is_in_progress(self) -> bool:
        """Whether this milestone has some but not all items complete."""
        return 0 < self.completed_items < self.total_items

    @property
    def is_not_started(self) -> bool:
        """Whether this milestone has no completed items."""
        return self.completed_items == 0


@dataclass
class Roadmap:
    """A project roadmap with milestones."""

    path: Path
    milestones: list[Milestone] = field(default_factory=list)
    title: str | None = None

    @property
    def total_items(self) -> int:
        """Total items across all milestones."""
        return sum(m.total_items for m in self.milestones)

    @property
    def completed_items(self) -> int:
        """Completed items across all milestones."""
        return sum(m.completed_items for m in self.milestones)

    @property
    def progress_percent(self) -> float:
        """Overall progress as a percentage."""
        if self.total_items == 0:
            return 0.0
        return (self.completed_items / self.total_items) * 100

    @classmethod
    def parse(cls, path: Path) -> "Roadmap":
        """Parse a roadmap from a markdown file."""
        if not path.exists():
            raise FileNotFoundError(f"Roadmap file not found: {path}")

        content = path.read_text()
        return cls.parse_content(content, path)

    @classmethod
    def parse_content(cls, content: str, path: Path) -> "Roadmap":
        """Parse roadmap content from a string."""
        lines = content.split("\n")
        roadmap = cls(path=path)

        current_milestone: Milestone | None = None

        for line_num, line in enumerate(lines, start=1):
            # Check for title (# heading)
            if line.startswith("# ") and roadmap.title is None:
                roadmap.title = line[2:].strip()
                continue

            # Check for milestone (## heading)
            milestone_match = re.match(r"^##\s+(.+)$", line)
            if milestone_match:
                # Save previous milestone if exists
                if current_milestone:
                    roadmap.milestones.append(current_milestone)

                milestone_name = milestone_match.group(1).strip()
                current_milestone = Milestone(name=milestone_name, line_number=line_num)
                continue

            # Check for roadmap item
            if current_milestone:
                item = RoadmapItem.from_line(line, line_number=line_num)
                if item:
                    current_milestone.items.append(item)

        # Don't forget the last milestone
        if current_milestone:
            roadmap.milestones.append(current_milestone)

        return roadmap

    def mark_item_complete(self, milestone_index: int, item_index: int) -> None:
        """Mark a specific item as complete."""
        if 0 <= milestone_index < len(self.milestones):
            milestone = self.milestones[milestone_index]
            if 0 <= item_index < len(milestone.items):
                milestone.items[item_index].completed = True

    def mark_item_incomplete(self, milestone_index: int, item_index: int) -> None:
        """Mark a specific item as incomplete."""
        if 0 <= milestone_index < len(self.milestones):
            milestone = self.milestones[milestone_index]
            if 0 <= item_index < len(milestone.items):
                milestone.items[item_index].completed = False

    def save(self) -> None:
        """Save the roadmap back to its file."""
        content = self.to_markdown()
        self.path.write_text(content)

    def toggle_item_by_text(self, item_text: str) -> bool:
        """Toggle completion status of an item by its text.

        Returns True if item was found and toggled, False otherwise.
        """
        for milestone in self.milestones:
            for item in milestone.items:
                if item.text == item_text:
                    item.completed = not item.completed
                    return True
        return False

    def find_item_by_text(self, item_text: str) -> tuple[int, int] | None:
        """Find milestone and item indices for an item by text.

        Returns (milestone_index, item_index) or None if not found.
        """
        for m_idx, milestone in enumerate(self.milestones):
            for i_idx, item in enumerate(milestone.items):
                if item.text == item_text:
                    return (m_idx, i_idx)
        return None

    def to_markdown(self) -> str:
        """Convert the roadmap back to markdown format."""
        lines = []

        if self.title:
            lines.append(f"# {self.title}")
            lines.append("")

        for milestone in self.milestones:
            lines.append(f"## {milestone.name}")
            for item in milestone.items:
                lines.append(item.to_markdown())
            lines.append("")

        return "\n".join(lines)

    def find_next_incomplete(self) -> tuple[int, int, RoadmapItem] | None:
        """Find the next incomplete item in the roadmap.

        Returns tuple of (milestone_index, item_index, item) or None.
        """
        for m_idx, milestone in enumerate(self.milestones):
            for i_idx, item in enumerate(milestone.items):
                if not item.completed:
                    return (m_idx, i_idx, item)
        return None

    def find_items_matching(self, text: str) -> list[tuple[int, int, RoadmapItem]]:
        """Find roadmap items matching the given text (case-insensitive).

        Returns list of (milestone_index, item_index, item) tuples.
        """
        text_lower = text.lower()
        matches = []

        for m_idx, milestone in enumerate(self.milestones):
            for i_idx, item in enumerate(milestone.items):
                if text_lower in item.text.lower():
                    matches.append((m_idx, i_idx, item))

        return matches

    def get_item_by_text(self, item_text: str) -> RoadmapItem | None:
        """Get a roadmap item by its exact text.

        Args:
            item_text: The exact text of the item

        Returns:
            The RoadmapItem if found, None otherwise
        """
        for milestone in self.milestones:
            for item in milestone.items:
                if item.text == item_text:
                    return item
        return None

    def bulk_mark_complete(self, item_texts: list[str]) -> int:
        """Mark multiple items as complete by their text.

        Args:
            item_texts: List of item texts to mark complete

        Returns:
            Number of items successfully marked complete
        """
        completed_count = 0

        for item_text in item_texts:
            for milestone in self.milestones:
                for item in milestone.items:
                    if item.text == item_text and not item.completed:
                        item.completed = True
                        completed_count += 1
                        break

        return completed_count


    def extract_agent_groups(self, milestone_name: str) -> list[AgentGroup]:
        """Extract ### agent group headings and their task indices from a milestone.

        Parses the raw ROADMAP markdown for ### headings within the target
        milestone's ## section. Each ### heading groups the - [ ] items beneath it.

        Args:
            milestone_name: Name of the milestone to extract groups from.

        Returns:
            List of AgentGroup with name and task indices (0-based into
            the milestone's incomplete items list).
        """
        try:
            content = self.path.read_text(encoding="utf-8")
        except OSError:
            return []

        lines = content.split("\n")

        # Find the target milestone section
        in_milestone = False
        groups: list[AgentGroup] = []
        current_group_name: str | None = None
        current_group_indices: list[int] = []
        item_index = 0  # Index into incomplete items only

        for line in lines:
            # Check for milestone heading
            milestone_match = re.match(r"^##\s+(.+)$", line)
            if milestone_match:
                if in_milestone:
                    # We've hit the next milestone, stop
                    break
                if milestone_match.group(1).strip() == milestone_name:
                    in_milestone = True
                continue

            if not in_milestone:
                continue

            # Check for agent group heading (###)
            group_match = re.match(r"^###\s+(.+)$", line)
            if group_match:
                # Flush previous group
                if current_group_name and current_group_indices:
                    groups.append(AgentGroup(
                        name=current_group_name,
                        task_indices=current_group_indices,
                    ))
                current_group_name = group_match.group(1).strip()
                current_group_indices = []
                continue

            # Check for incomplete checkbox item
            item_match = re.match(r"^\s*[-*]\s*\[[ ]\]\s+.+$", line)
            if item_match and current_group_name is not None:
                current_group_indices.append(item_index)

            # Count all incomplete items (to match task index ordering)
            if re.match(r"^\s*[-*]\s*\[[ ]\]\s+.+$", line):
                item_index += 1

        # Flush last group
        if current_group_name and current_group_indices:
            groups.append(AgentGroup(
                name=current_group_name,
                task_indices=current_group_indices,
            ))

        return groups


class RoadmapParser:
    """Static helper for parsing roadmaps from project paths."""

    @staticmethod
    def parse(project_path: Path) -> Roadmap | None:
        """Parse roadmap from a project directory.

        Phase 2 behavior: scan all planning artifacts and convert to legacy Roadmap.
        """
        try:
            scanner = ProjectPlanScanner(project_path)
            plan = scanner.scan()

            if not plan.items:
                return None

            roadmap_path = project_path / "ROADMAP.md"
            for source_path in plan.sources_found.get(PlanSource.ROADMAP_FILE, []):
                roadmap_path = source_path
                break

            roadmap = Roadmap(path=roadmap_path, title="Unified Project Plan")
            conflict_ids = {conflict.item_id for conflict in plan.conflicts}

            for milestone in plan.milestones:
                items = [
                    RoadmapItem(
                        text=item.content,
                        completed=item.status == PlanItemStatus.DONE,
                        line_number=item.source_line or 0,
                        source=item.source.value,
                        conflict=item.id in conflict_ids,
                    )
                    for item in milestone.items
                ]
                roadmap.milestones.append(
                    Milestone(
                        name=milestone.name,
                        items=items,
                    )
                )
            return roadmap
        except Exception:
            return None
