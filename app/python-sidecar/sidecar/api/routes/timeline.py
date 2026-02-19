"""
Timeline API routes
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
from datetime import datetime
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Import core modules
try:
    from src.core.timeline import TimelineBuilder, TimelineEntry
    from src.core.project import Project, ProjectRegistry
    CORE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Core modules not available: {e}")
    CORE_AVAILABLE = False

from ..ttl_cache import get as cache_get, put as cache_put


class CommitInfoResponse(BaseModel):
    """Git commit metadata for timeline entries."""

    sha: str
    message: str
    timestamp: str


class TokenUsageResponse(BaseModel):
    """Token usage metrics for a session."""

    inputTokens: int
    outputTokens: int
    model: str


class TestResultResponse(BaseModel):
    """Test execution results for a session."""

    passed: bool
    total: int | None = None
    passedCount: int | None = None
    raw: str | None = None


class TimelineEntryResponse(BaseModel):
    """A single session entry in the project timeline."""

    sessionId: str
    date: str
    durationMinutes: int
    summary: str
    provider: str = "claude"
    branch: Optional[str] = None
    promptUsed: Optional[str] = None  # What the user asked
    commits: list[CommitInfoResponse]
    filesChanged: int
    todosCreated: int
    todosCompleted: int
    roadmapItemsCompleted: list[str]
    costEstimate: Optional[float] = None
    gateStatuses: dict[str, str]
    tokenUsage: TokenUsageResponse | None = None
    testResults: TestResultResponse | None = None


class TimelineResponse(BaseModel):
    """Complete timeline response with session entries."""

    entries: list[TimelineEntryResponse]
    total: int


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
def get_timeline(project_id: str, limit: int = Query(50, ge=1, le=500)) -> TimelineResponse:
    """Get project timeline with sessions and commits"""
    if not CORE_AVAILABLE:
        # Core modules not available - raise HTTP error instead of silent failure
        raise HTTPException(
            status_code=500,
            detail="Timeline unavailable: Core modules failed to import. Check sidecar logs for details."
        )

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    cache_key = f"timeline:{project_path}:{limit}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        project = Project.from_path(project_path)
        builder = TimelineBuilder(project)
        entries = builder.build(limit=limit)
    except Exception as e:
        logger.error(f"Failed to build timeline for {project_path}: {e}", exc_info=True)
        # Return HTTP error instead of silently returning empty data
        raise HTTPException(
            status_code=500,
            detail=f"Failed to build timeline: {str(e)}"
        )

    response_entries = []
    for entry in entries:
        response_entries.append(
            TimelineEntryResponse(
                sessionId=entry.session_id,
                date=entry.date.isoformat(),
                durationMinutes=entry.duration_minutes,
                summary=entry.summary,
                provider=entry.provider,
                branch=entry.branch,
                promptUsed=entry.prompt_used,  # What the user asked
                commits=[
                    CommitInfoResponse(
                        sha=c.sha[:7],
                        message=c.message,
                        timestamp=c.timestamp.isoformat(),
                    )
                    for c in entry.commits
                ],
                filesChanged=entry.files_changed,
                todosCreated=entry.todos_created,
                todosCompleted=entry.todos_completed,
                roadmapItemsCompleted=entry.roadmap_items_completed,
                costEstimate=entry.cost_estimate,
                gateStatuses=entry.gate_statuses,
                tokenUsage=(
                    TokenUsageResponse(
                        inputTokens=entry.token_usage.input_tokens,
                        outputTokens=entry.token_usage.output_tokens,
                        model=entry.token_usage.model,
                    )
                    if entry.token_usage
                    else None
                ),
                testResults=(
                    TestResultResponse(
                        passed=entry.test_results.passed,
                        total=entry.test_results.total,
                        passedCount=entry.test_results.passed_count,
                        raw=entry.test_results.raw,
                    )
                    if entry.test_results
                    else None
                ),
            )
        )

    result = TimelineResponse(
        entries=response_entries,
        total=len(response_entries),
    )
    cache_put(cache_key, result, ttl=10)
    return result
