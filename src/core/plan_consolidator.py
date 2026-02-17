"""Plan consolidation - merge multiple planning sources into single source of truth."""

from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .plan_models import PlanItem, PlanItemStatus, PlanSource
from .plan_scanner import ProjectPlanScanner


@dataclass
class DetectedSource:
    """A detected planning source file."""

    path: Path
    source_type: PlanSource
    item_count: int
    completed_count: int
    can_delete: bool = True  # Some files like CLAUDE.md shouldn't be deleted, just cleaned

    @property
    def display_name(self) -> str:
        """Short display name for UI."""
        return self.path.name

    @property
    def relative_path(self) -> str:
        """Path relative to project root."""
        return str(self.path)

    @property
    def percent_complete(self) -> int:
        """Completion percentage."""
        if self.item_count == 0:
            return 0
        return int(self.completed_count / self.item_count * 100)


@dataclass
class ConsolidatedItem:
    """A deduplicated, merged planning item."""

    content: str
    done: bool
    milestone: str | None
    sources: list[Path] = field(default_factory=list)  # Which files had this item

    @property
    def content_hash(self) -> str:
        """Hash for deduplication."""
        # Normalize content for comparison
        normalized = re.sub(r'\s+', ' ', self.content.lower().strip())
        return hashlib.md5(normalized.encode()).hexdigest()[:12]


@dataclass
class ConsolidationResult:
    """Result of a consolidation operation."""

    success: bool
    consolidated_path: Path | None
    items_consolidated: int
    duplicates_removed: int
    files_archived: list[Path]
    files_deleted: list[Path]
    error: str | None = None


class PlanConsolidator:
    """Consolidates multiple planning sources into a single source of truth."""

    # Files that should have sections removed rather than being deleted
    CLEAN_ONLY_FILES = {"CLAUDE.md", "README.md"}

    # The canonical location for consolidated roadmap
    CONSOLIDATED_DIR = ".claude/planning"
    CONSOLIDATED_FILE = "ROADMAP.md"

    def __init__(self, project_path: Path):
        self.project_path = project_path.resolve()
        self._scanner = ProjectPlanScanner(project_path)

    def detect_sources(self) -> list[DetectedSource]:
        """Detect all planning sources in the project."""
        plan = self._scanner.scan()

        # Group items by source file
        items_by_file: dict[Path, list[PlanItem]] = {}
        for item in plan.items:
            if item.source_file:
                if item.source_file not in items_by_file:
                    items_by_file[item.source_file] = []
                items_by_file[item.source_file].append(item)

        sources = []
        for file_path, items in items_by_file.items():
            # Determine source type
            source_type = items[0].source if items else PlanSource.HEURISTIC

            # Check if file can be deleted or just cleaned
            can_delete = file_path.name not in self.CLEAN_ONLY_FILES

            completed = sum(1 for item in items if item.status == PlanItemStatus.DONE)

            sources.append(DetectedSource(
                path=file_path,
                source_type=source_type,
                item_count=len(items),
                completed_count=completed,
                can_delete=can_delete,
            ))

        # Sort by item count descending
        sources.sort(key=lambda s: s.item_count, reverse=True)
        return sources

    def needs_consolidation(self) -> bool:
        """Check if project has multiple planning sources that should be consolidated."""
        sources = self.detect_sources()
        # Need consolidation if more than one source with items
        return len([s for s in sources if s.item_count > 0]) > 1

    def consolidate(
        self,
        archive: bool = True,
        delete_after: bool = False,
    ) -> ConsolidationResult:
        """
        Consolidate all planning sources into single file.

        Args:
            archive: If True, copy old files to .claude/planning/archive/ before removal
            delete_after: If True, delete source files (except CLEAN_ONLY_FILES)

        Returns:
            ConsolidationResult with details of the operation
        """
        try:
            sources = self.detect_sources()
            if not sources:
                return ConsolidationResult(
                    success=True,
                    consolidated_path=None,
                    items_consolidated=0,
                    duplicates_removed=0,
                    files_archived=[],
                    files_deleted=[],
                )

            # Merge and deduplicate items
            merged_items = self._merge_items(sources)
            duplicates_removed = self._count_total_items(sources) - len(merged_items)

            # Create consolidated directory
            consolidated_dir = self.project_path / self.CONSOLIDATED_DIR
            consolidated_dir.mkdir(parents=True, exist_ok=True)

            # Write consolidated roadmap
            consolidated_path = consolidated_dir / self.CONSOLIDATED_FILE
            self._write_consolidated_roadmap(consolidated_path, merged_items)

            # Archive old files if requested
            files_archived = []
            if archive:
                archive_dir = consolidated_dir / "archive" / datetime.now().strftime("%Y%m%d_%H%M%S")
                archive_dir.mkdir(parents=True, exist_ok=True)

                for source in sources:
                    if source.path != consolidated_path and source.path.exists():
                        archive_path = archive_dir / source.path.name
                        # Handle name collisions
                        if archive_path.exists():
                            stem = archive_path.stem
                            suffix = archive_path.suffix
                            archive_path = archive_dir / f"{stem}_{source.source_type.value}{suffix}"
                        shutil.copy2(source.path, archive_path)
                        files_archived.append(archive_path)

            # Delete or clean source files
            files_deleted = []
            if delete_after:
                for source in sources:
                    if source.path == consolidated_path:
                        continue

                    if source.can_delete and source.path.exists():
                        source.path.unlink()
                        files_deleted.append(source.path)
                    elif not source.can_delete:
                        # Clean embedded sections from files like CLAUDE.md
                        self._clean_embedded_section(source.path)

            return ConsolidationResult(
                success=True,
                consolidated_path=consolidated_path,
                items_consolidated=len(merged_items),
                duplicates_removed=duplicates_removed,
                files_archived=files_archived,
                files_deleted=files_deleted,
            )

        except Exception as e:
            return ConsolidationResult(
                success=False,
                consolidated_path=None,
                items_consolidated=0,
                duplicates_removed=0,
                files_archived=[],
                files_deleted=[],
                error=str(e),
            )

    def _merge_items(self, sources: list[DetectedSource]) -> list[ConsolidatedItem]:
        """Merge items from all sources, deduplicating by content."""
        plan = self._scanner.scan()

        # Group by content hash for deduplication
        items_by_hash: dict[str, ConsolidatedItem] = {}

        for item in plan.items:
            # Create consolidated item
            consolidated = ConsolidatedItem(
                content=item.content,
                done=item.status == PlanItemStatus.DONE,
                milestone=item.milestone,
                sources=[item.source_file] if item.source_file else [],
            )

            content_hash = consolidated.content_hash

            if content_hash in items_by_hash:
                # Merge with existing - if ANY source has it done, mark done
                existing = items_by_hash[content_hash]
                existing.done = existing.done or consolidated.done
                if item.source_file and item.source_file not in existing.sources:
                    existing.sources.append(item.source_file)
            else:
                items_by_hash[content_hash] = consolidated

        return list(items_by_hash.values())

    def _count_total_items(self, sources: list[DetectedSource]) -> int:
        """Count total items across all sources (before deduplication)."""
        return sum(s.item_count for s in sources)

    def _write_consolidated_roadmap(
        self,
        path: Path,
        items: list[ConsolidatedItem],
    ) -> None:
        """Write consolidated roadmap in standard format."""
        # Group items by milestone
        items_by_milestone: dict[str, list[ConsolidatedItem]] = {}
        no_milestone: list[ConsolidatedItem] = []

        for item in items:
            if item.milestone:
                if item.milestone not in items_by_milestone:
                    items_by_milestone[item.milestone] = []
                items_by_milestone[item.milestone].append(item)
            else:
                no_milestone.append(item)

        # Build markdown content
        lines = [
            "# Project Roadmap",
            "",
            f"_Consolidated on {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
            "",
        ]

        # Write milestones
        milestone_num = 1
        for milestone, milestone_items in items_by_milestone.items():
            # Clean up milestone name
            milestone_name = milestone
            if not milestone_name.lower().startswith("milestone"):
                milestone_name = f"Milestone {milestone_num}: {milestone}"
                milestone_num += 1

            lines.append(f"## {milestone_name}")
            lines.append("")

            for item in milestone_items:
                checkbox = "[x]" if item.done else "[ ]"
                lines.append(f"- {checkbox} {item.content}")

            lines.append("")

        # Write items without milestone
        if no_milestone:
            lines.append("## Uncategorized")
            lines.append("")
            for item in no_milestone:
                checkbox = "[x]" if item.done else "[ ]"
                lines.append(f"- {checkbox} {item.content}")
            lines.append("")

        # Write summary
        total = len(items)
        done = sum(1 for item in items if item.done)
        lines.extend([
            "---",
            "",
            f"**Progress:** {done}/{total} items ({int(done/total*100) if total > 0 else 0}% complete)",
            "",
        ])

        path.write_text("\n".join(lines))

    def _clean_embedded_section(self, path: Path) -> None:
        """Remove embedded planning sections from a file like CLAUDE.md."""
        if not path.exists():
            return

        content = path.read_text()

        # Remove claudetini:managed sections
        pattern = r'<!-- claudetini:managed -->.*?<!-- /claudetini:managed -->'
        cleaned = re.sub(pattern, '', content, flags=re.DOTALL)

        # Remove ## What's Done / ## What's In Progress sections if they exist standalone
        patterns_to_remove = [
            r'\n## What\'s Done\n.*?(?=\n## |\n---|\Z)',
            r'\n## What\'s In Progress\n.*?(?=\n## |\n---|\Z)',
        ]

        for pattern in patterns_to_remove:
            cleaned = re.sub(pattern, '\n', cleaned, flags=re.DOTALL)

        # Clean up multiple blank lines
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

        if cleaned != content:
            path.write_text(cleaned)
