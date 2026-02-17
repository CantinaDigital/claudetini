"""
Roadmap API routes
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Import core modules
try:
    from src.core.roadmap import RoadmapParser, Roadmap
    from src.core.project import Project, ProjectRegistry
    CORE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Core modules not available: {e}")
    CORE_AVAILABLE = False


class MilestoneItemResponse(BaseModel):
    text: str
    done: bool
    source: Optional[str] = None
    conflict: bool = False


class MilestoneResponse(BaseModel):
    id: int
    title: str
    items: list[MilestoneItemResponse]
    completed: int
    total: int
    progress: float


class RoadmapResponse(BaseModel):
    milestones: list[MilestoneResponse]
    totalItems: int
    completedItems: int
    progress: int
    title: Optional[str] = None


class ToggleItemRequest(BaseModel):
    """Request to toggle an item's done status."""
    item_text: str


class ToggleItemResponse(BaseModel):
    """Response after toggling an item."""
    success: bool
    message: str
    new_status: bool


class BatchToggleRequest(BaseModel):
    """Request to batch-toggle multiple items."""
    item_texts: list[str]
    mark_done: bool = True


class BatchToggleResponse(BaseModel):
    """Response after batch-toggling items."""
    success: bool
    toggled_count: int
    not_found: list[str]


def _get_project_path(project_id: str) -> Path | None:
    """Get project path from ID."""
    path = Path(project_id)
    if path.exists():
        return path
    if CORE_AVAILABLE:
        registry = ProjectRegistry.load_or_create()
        for project in registry.list_projects():
            if str(project.path) == project_id or project.name == project_id:
                return project.path
    return None


@router.get("/{project_id:path}")
def get_roadmap(project_id: str) -> RoadmapResponse:
    """Get project roadmap"""
    if not CORE_AVAILABLE:
        # Core modules not available - return empty data
        return RoadmapResponse(
            milestones=[],
            totalItems=0,
            completedItems=0,
            progress=0,
            title=None,
        )

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    roadmap = RoadmapParser.parse(project_path)

    if not roadmap:
        raise HTTPException(status_code=404, detail="No roadmap found")

    milestones = []
    for i, milestone in enumerate(roadmap.milestones):
        items = [
            MilestoneItemResponse(
                text=item.text,
                done=item.completed,
                source=getattr(item, 'source', None),
                conflict=getattr(item, 'conflict', False),
            )
            for item in milestone.items
        ]
        milestones.append(
            MilestoneResponse(
                id=i + 1,
                title=milestone.name,
                items=items,
                completed=milestone.completed_items,
                total=milestone.total_items,
                progress=milestone.progress_percent,
            )
        )

    return RoadmapResponse(
        milestones=milestones,
        totalItems=roadmap.total_items,
        completedItems=roadmap.completed_items,
        progress=int(roadmap.progress_percent),
        title=roadmap.title,
    )


@router.post("/{project_id:path}/toggle-item")
def toggle_roadmap_item(project_id: str, request: ToggleItemRequest) -> ToggleItemResponse:
    """Toggle the done status of a roadmap item by its text."""
    if not CORE_AVAILABLE:
        return ToggleItemResponse(
            success=False,
            message="Core modules not available",
            new_status=False
        )

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        roadmap = RoadmapParser.parse(project_path)
        if not roadmap:
            raise HTTPException(status_code=404, detail="No roadmap found")

        # Toggle the item
        found = roadmap.toggle_item_by_text(request.item_text)
        if not found:
            return ToggleItemResponse(
                success=False,
                message=f"Item not found: {request.item_text}",
                new_status=False
            )

        # Save the updated roadmap
        roadmap.save()

        # Find the item to get its new status
        for milestone in roadmap.milestones:
            for item in milestone.items:
                if item.text == request.item_text:
                    return ToggleItemResponse(
                        success=True,
                        message=f"Item {'completed' if item.completed else 'reopened'}",
                        new_status=item.completed
                    )

        # Shouldn't reach here, but just in case
        return ToggleItemResponse(
            success=True,
            message="Item toggled",
            new_status=False
        )

    except Exception as e:
        logger.error(f"Failed to toggle roadmap item: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id:path}/batch-toggle")
def batch_toggle_roadmap_items(
    project_id: str, request: BatchToggleRequest
) -> BatchToggleResponse:
    """Batch-toggle multiple roadmap items in a single parse/save cycle."""
    if not CORE_AVAILABLE:
        return BatchToggleResponse(
            success=False, toggled_count=0, not_found=request.item_texts
        )

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        roadmap = RoadmapParser.parse(project_path)
        if not roadmap:
            raise HTTPException(status_code=404, detail="No roadmap found")

        toggled = 0
        not_found: list[str] = []

        for item_text in request.item_texts:
            # Find the item and set its status
            found = False
            for milestone in roadmap.milestones:
                for item in milestone.items:
                    if item.text == item_text:
                        found = True
                        if request.mark_done and not item.completed:
                            item.completed = True
                            toggled += 1
                        elif not request.mark_done and item.completed:
                            item.completed = False
                            toggled += 1
                        break
                if found:
                    break
            if not found:
                not_found.append(item_text)

        # Save once after all changes
        if toggled > 0:
            roadmap.save()

        return BatchToggleResponse(
            success=True,
            toggled_count=toggled,
            not_found=not_found,
        )

    except Exception as e:
        logger.error(f"Failed to batch-toggle roadmap items: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
