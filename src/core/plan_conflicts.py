"""Conflict detection and resolution for unified project plans."""

from collections import defaultdict

from .plan_models import (
    ConflictResolution,
    ConflictSource,
    PlanItem,
    PlanItemConflict,
    PlanItemStatus,
    PlanSource,
)


def detect_conflicts(items: list[PlanItem]) -> list[PlanItemConflict]:
    """Detect conflicts for items with differing statuses across sources."""
    by_id: dict[str, list[PlanItem]] = defaultdict(list)
    for item in items:
        by_id[item.id].append(item)

    conflicts: list[PlanItemConflict] = []
    for item_id, variants in by_id.items():
        statuses = {item.status for item in variants}
        if len(statuses) <= 1:
            continue

        conflict_sources = [
            ConflictSource(
                source=item.source,
                status=item.status,
                source_file=item.source_file,
                source_mtime=_source_mtime(item),
            )
            for item in variants
        ]
        resolution, resolved_status = _resolve_conflict(conflict_sources)
        conflicts.append(
            PlanItemConflict(
                item_id=item_id,
                sources=conflict_sources,
                resolution=resolution,
                resolved_status=resolved_status,
            )
        )

    return conflicts


def merge_items(items: list[PlanItem], conflicts: list[PlanItemConflict]) -> list[PlanItem]:
    """Merge plan items by id, applying conflict resolutions where needed."""
    by_id: dict[str, list[PlanItem]] = defaultdict(list)
    for item in items:
        by_id[item.id].append(item)

    conflict_by_id = {conflict.item_id: conflict for conflict in conflicts}
    merged: list[PlanItem] = []

    for item_id, variants in by_id.items():
        selected = _select_preferred_variant(variants)
        conflict = conflict_by_id.get(item_id)
        if conflict:
            selected.status = conflict.resolved_status
            selected.conflicts.append(conflict)
        merged.append(selected)

    return merged


def _resolve_conflict(
    sources: list[ConflictSource],
) -> tuple[ConflictResolution, PlanItemStatus]:
    """Resolve a conflict using Phase 2 resolution rules."""
    roadmap_done = any(
        source.source == PlanSource.ROADMAP_FILE and source.status == PlanItemStatus.DONE
        for source in sources
    )
    if roadmap_done:
        return ConflictResolution.ROADMAP_WINS, PlanItemStatus.DONE

    tasks_in_progress = any(
        source.source == PlanSource.CLAUDE_TASKS_API and source.status == PlanItemStatus.IN_PROGRESS
        for source in sources
    )
    if tasks_in_progress:
        return ConflictResolution.TASKS_API_WINS, PlanItemStatus.IN_PROGRESS

    most_recent = _most_recent_status(sources)
    if most_recent is not None:
        return ConflictResolution.MOST_RECENT_WINS, most_recent

    # Fall back to manual resolution while preserving deterministic behavior.
    return ConflictResolution.MANUAL, sources[0].status


def _most_recent_status(sources: list[ConflictSource]) -> PlanItemStatus | None:
    latest = None
    for source in sources:
        if source.source_mtime is None:
            continue
        if latest is None or source.source_mtime > latest.source_mtime:
            latest = source
    return latest.status if latest else None


def _source_mtime(item: PlanItem):
    if item.source_file is None:
        return None
    try:
        return item.source_file.stat().st_mtime_ns
    except OSError:
        return None


def _select_preferred_variant(variants: list[PlanItem]) -> PlanItem:
    """Select the highest-quality variant for display metadata."""
    # Prefer explicit roadmap text, then phase files, then planning dirs,
    # then tasks API, then global Claude plans, then embedded, then heuristic.
    priority = {
        PlanSource.ROADMAP_FILE: 7,
        PlanSource.PHASE_FILE: 6,
        PlanSource.PLANNING_DIR: 5,
        PlanSource.CLAUDE_TASKS_API: 4,
        PlanSource.CLAUDE_PLANS: 3,
        PlanSource.EMBEDDED_SECTION: 2,
        PlanSource.HEURISTIC: 1,
    }
    variants.sort(key=lambda item: priority.get(item.source, 0), reverse=True)
    return variants[0]

