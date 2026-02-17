"""
Reconciliation API routes for smart roadmap progress tracking.
"""

import asyncio
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

# Import core modules
try:
    from src.core.project import Project
    from src.core.reconciliation import (
        FileChange,
        ProjectStateSnapshot,
        ReconciliationEngine,
        ReconciliationReport,
        RoadmapSuggestion,
    )
    from src.core.roadmap import Roadmap

    CORE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Core modules not available: {e}")
    CORE_AVAILABLE = False


# Pydantic response models
class QuickCheckResponse(BaseModel):
    has_changes: bool
    commits_count: int
    files_modified: int
    uncommitted_count: int


class AnalysisJobResponse(BaseModel):
    job_id: str
    status: Literal["started"]


class JobStatusResponse(BaseModel):
    status: Literal["running", "complete", "failed"]
    progress: int  # 0-100
    error: str | None = None


class FileChangeResponse(BaseModel):
    path: str
    change_type: Literal["added", "modified", "deleted"]
    loc_delta: int
    is_substantial: bool


class SuggestionResponse(BaseModel):
    item_text: str
    milestone_name: str
    confidence: float
    reasoning: list[str]
    matched_files: list[str]
    matched_commits: list[str]
    session_id: str | None = None


class ReconciliationReportResponse(BaseModel):
    report_id: str
    timestamp: str
    old_snapshot_id: str
    new_snapshot_id: str
    commits_added: int
    files_changed: list[FileChangeResponse]
    dependencies_changed: bool
    suggestions: list[SuggestionResponse]
    already_completed_externally: list[str]
    ai_metadata: dict | None = None


class ApplyReconciliationRequest(BaseModel):
    report_id: str
    accepted_items: list[str]
    dismissed_items: list[str]


class ApplyReconciliationResponse(BaseModel):
    success: bool
    items_completed: int
    items_dismissed: int


class AnalyzeRequest(BaseModel):
    min_confidence: float = 0.5  # Default 50%


class SnapshotResponse(BaseModel):
    snapshot_id: str
    timestamp: str
    git_head_sha: str | None
    git_branch: str | None
    completed_items: int
    total_items: int


# In-memory job storage (in production, use Redis)
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _get_project_path(project_id: str) -> Path | None:
    """Get project path from ID."""
    path = Path(project_id)
    if path.exists():
        return path
    if CORE_AVAILABLE:
        try:
            from src.core.project import ProjectRegistry
            registry = ProjectRegistry()
            for project in registry.list_projects():
                if str(project.path) == project_id or project.name == project_id:
                    return project.path
        except Exception:
            pass
    return None


def _update_job_status(job_id: str, status: str, progress: int = 0, result: dict | None = None, error: str | None = None):
    """Update job status in the jobs dict."""
    with _jobs_lock:
        if job_id not in _jobs:
            _jobs[job_id] = {}
        _jobs[job_id]["status"] = status
        _jobs[job_id]["progress"] = progress
        if result is not None:
            _jobs[job_id]["result"] = result
        if error is not None:
            _jobs[job_id]["error"] = error


def _run_reconciliation_analysis(project_path: Path, project_id: str, job_id: str, min_confidence: float = 0.5):
    """Background task to run full reconciliation analysis."""
    try:
        _update_job_status(job_id, "running", progress=0)

        # Initialize engine
        engine = ReconciliationEngine(project_path, project_id)

        # Get latest snapshot
        _update_job_status(job_id, "running", progress=10)
        old_snapshot = engine.snapshot_store.get_latest_snapshot()

        # Create new snapshot
        _update_job_status(job_id, "running", progress=20)
        new_snapshot = engine.create_snapshot("reconciliation")

        if not old_snapshot:
            # First snapshot - no comparison possible
            _update_job_status(
                job_id,
                "complete",
                progress=100,
                result={
                    "report_id": "",
                    "timestamp": datetime.now().isoformat(),
                    "old_snapshot_id": "",
                    "new_snapshot_id": new_snapshot.snapshot_id,
                    "commits_added": 0,
                    "files_changed": [],
                    "dependencies_changed": False,
                    "suggestions": [],
                    "already_completed_externally": [],
                },
            )
            return

        # Detect changes
        _update_job_status(job_id, "running", progress=40)
        file_changes, commit_shas = engine.detect_changes(old_snapshot, new_snapshot)

        # Load roadmap
        _update_job_status(job_id, "running", progress=60)
        project = Project.from_path(project_path)
        roadmap_path = project.get_roadmap_path()

        if not roadmap_path or not roadmap_path.exists():
            # No roadmap - can't generate suggestions
            _update_job_status(
                job_id,
                "complete",
                progress=100,
                result={
                    "report_id": "",
                    "timestamp": datetime.now().isoformat(),
                    "old_snapshot_id": old_snapshot.snapshot_id,
                    "new_snapshot_id": new_snapshot.snapshot_id,
                    "commits_added": len(commit_shas),
                    "files_changed": [
                        {
                            "path": fc.path,
                            "change_type": fc.change_type,
                            "loc_delta": fc.loc_delta,
                            "is_substantial": fc.is_substantial,
                        }
                        for fc in file_changes
                    ],
                    "dependencies_changed": old_snapshot.dependency_fingerprint != new_snapshot.dependency_fingerprint,
                    "suggestions": [],
                    "already_completed_externally": [],
                },
            )
            return

        roadmap = Roadmap.parse(roadmap_path)

        # Generate suggestions
        _update_job_status(job_id, "running", progress=80)
        suggestions = engine.generate_suggestions(roadmap, file_changes, commit_shas)

        # Filter by confidence threshold from settings
        filtered_suggestions = [s for s in suggestions if s.confidence >= min_confidence]

        # Detect external completions
        external_completions = engine.detect_external_completions(old_snapshot, new_snapshot)

        # Create report
        report_id = str(uuid.uuid4())
        report = ReconciliationReport(
            report_id=report_id,
            timestamp=datetime.now(),
            old_snapshot_id=old_snapshot.snapshot_id,
            new_snapshot_id=new_snapshot.snapshot_id,
            commits_added=len(commit_shas),
            files_changed=file_changes,
            dependencies_changed=old_snapshot.dependency_fingerprint != new_snapshot.dependency_fingerprint,
            suggestions=filtered_suggestions,
            already_completed_externally=external_completions,
        )

        # Save report
        engine.reconciliation_store.save_report(report)

        # Convert to response dict
        result = {
            "report_id": report.report_id,
            "timestamp": report.timestamp.isoformat(),
            "old_snapshot_id": report.old_snapshot_id,
            "new_snapshot_id": report.new_snapshot_id,
            "commits_added": report.commits_added,
            "files_changed": [
                {
                    "path": fc.path,
                    "change_type": fc.change_type,
                    "loc_delta": fc.loc_delta,
                    "is_substantial": fc.is_substantial,
                }
                for fc in report.files_changed
            ],
            "dependencies_changed": report.dependencies_changed,
            "suggestions": [
                {
                    "item_text": s.item_text,
                    "milestone_name": s.milestone_name,
                    "confidence": s.confidence,
                    "reasoning": s.reasoning,
                    "matched_files": s.matched_files,
                    "matched_commits": s.matched_commits,
                    "session_id": s.session_id,
                }
                for s in report.suggestions
            ],
            "already_completed_externally": report.already_completed_externally,
        }

        _update_job_status(job_id, "complete", progress=100, result=result)

    except Exception as e:
        logger.exception(f"Reconciliation analysis failed for job {job_id}")
        _update_job_status(job_id, "failed", progress=0, error=str(e))


@router.get("/{project_id:path}/reconcile/quick-check")
async def quick_check(project_id: str) -> QuickCheckResponse:
    """Fast check (<100ms) for changes since last snapshot."""
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Core modules not loaded")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        engine = ReconciliationEngine(project_path, project_id)
        result = engine.quick_check_for_changes()
        return QuickCheckResponse(**result)
    except Exception as e:
        logger.exception("Quick check failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id:path}/reconcile/analyze")
async def start_analysis(
    project_id: str, background_tasks: BackgroundTasks, request: AnalyzeRequest = AnalyzeRequest()
) -> AnalysisJobResponse:
    """Start background reconciliation analysis (30-60 seconds)."""
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Core modules not loaded")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate and clamp min_confidence
    min_confidence = max(0.3, min(0.9, request.min_confidence))

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Start background task
    background_tasks.add_task(_run_reconciliation_analysis, project_path, project_id, job_id, min_confidence)

    return AnalysisJobResponse(job_id=job_id, status="started")


@router.get("/{project_id:path}/reconcile/status/{job_id}")
async def get_job_status(project_id: str, job_id: str) -> JobStatusResponse:
    """Get status of a background reconciliation job."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        status=job.get("status", "running"), progress=job.get("progress", 0), error=job.get("error")
    )


@router.get("/{project_id:path}/reconcile/result/{job_id}")
async def get_job_result(project_id: str, job_id: str) -> ReconciliationReportResponse:
    """Get result of a completed reconciliation job."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("status") != "complete":
        raise HTTPException(status_code=400, detail=f"Job not complete (status: {job.get('status')})")

    result = job.get("result")
    if not result:
        raise HTTPException(status_code=500, detail="Job completed but no result available")

    return ReconciliationReportResponse(**result)


@router.post("/{project_id:path}/reconcile/apply")
async def apply_reconciliation(project_id: str, request: ApplyReconciliationRequest) -> ApplyReconciliationResponse:
    """Apply accepted reconciliation suggestions to roadmap."""
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Core modules not loaded")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        engine = ReconciliationEngine(project_path, project_id)

        # Get roadmap path
        project = Project.from_path(project_path)
        roadmap_path = project.get_roadmap_path()

        if not roadmap_path or not roadmap_path.exists():
            raise HTTPException(status_code=404, detail="Roadmap not found")

        # Apply accepted items
        items_completed = engine.apply_suggestions(roadmap_path, request.accepted_items)

        # Record dismissals
        for item_text in request.dismissed_items:
            engine.reconciliation_store.add_dismissal(request.report_id, item_text)

        # Log for history/undo
        engine.reconciliation_store.log_action(
            "applied",
            {
                "report_id": request.report_id,
                "accepted_items": request.accepted_items,
                "dismissed_items": request.dismissed_items,
                "items_completed": items_completed,
            },
        )

        return ApplyReconciliationResponse(
            success=True, items_completed=items_completed, items_dismissed=len(request.dismissed_items)
        )

    except Exception as e:
        logger.exception("Failed to apply reconciliation")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id:path}/reconcile/undo")
async def undo_reconciliation(project_id: str) -> dict[str, Any]:
    """Undo the last applied reconciliation."""
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Core modules not loaded")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        engine = ReconciliationEngine(project_path, project_id)

        # Read audit log to find last applied action
        if not engine.reconciliation_store.audit_log.exists():
            raise HTTPException(status_code=404, detail="No reconciliation history found")

        import json

        # Read last "applied" action
        last_applied = None
        with open(engine.reconciliation_store.audit_log, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("action") == "applied":
                        last_applied = entry
                except json.JSONDecodeError:
                    continue

        if not last_applied:
            raise HTTPException(status_code=404, detail="No applied reconciliation to undo")

        # Get the items that were marked complete
        accepted_items = last_applied["details"]["accepted_items"]

        # Get roadmap and revert
        project = Project.from_path(project_path)
        roadmap_path = project.get_roadmap_path()

        if not roadmap_path or not roadmap_path.exists():
            raise HTTPException(status_code=404, detail="Roadmap not found")

        roadmap = Roadmap.parse(roadmap_path)
        reverted_count = 0

        for item_text in accepted_items:
            for milestone in roadmap.milestones:
                for item in milestone.items:
                    if item.text == item_text and item.completed:
                        item.completed = False
                        reverted_count += 1

        roadmap.save()

        # Log undo action
        engine.reconciliation_store.log_action(
            "undone", {"report_id": last_applied["details"]["report_id"], "items_reverted": reverted_count}
        )

        return {"success": True, "items_reverted": reverted_count}

    except Exception as e:
        logger.exception("Failed to undo reconciliation")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id:path}/snapshot")
async def create_snapshot(project_id: str) -> SnapshotResponse:
    """Manually create a project state snapshot."""
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Core modules not loaded")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        engine = ReconciliationEngine(project_path, project_id)
        snapshot = engine.create_snapshot("manual")

        return SnapshotResponse(
            snapshot_id=snapshot.snapshot_id,
            timestamp=snapshot.timestamp.isoformat(),
            git_head_sha=snapshot.git_head_sha,
            git_branch=snapshot.git_branch,
            completed_items=len(snapshot.completed_items),
            total_items=snapshot.total_items,
        )
    except Exception as e:
        logger.exception("Failed to create snapshot")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id:path}/snapshots")
async def list_snapshots(project_id: str) -> list[SnapshotResponse]:
    """List recent snapshots for a project."""
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Core modules not loaded")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        engine = ReconciliationEngine(project_path, project_id)
        snapshots = engine.snapshot_store.list_snapshots()

        return [
            SnapshotResponse(
                snapshot_id=s.snapshot_id,
                timestamp=s.timestamp.isoformat(),
                git_head_sha=s.git_head_sha,
                git_branch=s.git_branch,
                completed_items=len(s.completed_items),
                total_items=s.total_items,
            )
            for s in snapshots
        ]
    except Exception as e:
        logger.exception("Failed to list snapshots")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id:path}/reconcile/diff/{commit_sha}")
async def get_commit_diff(project_id: str, commit_sha: str) -> dict[str, str]:
    """Get the diff content for a specific commit."""
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Core modules not loaded")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        from src.core.git_utils import GitRepo

        repo = GitRepo(project_path)

        # Get diff from parent to this commit
        output, code = repo._run_git("show", "--format=", commit_sha)

        if code != 0:
            raise HTTPException(status_code=404, detail="Commit not found or diff unavailable")

        return {"commit_sha": commit_sha, "diff": output}

    except Exception as e:
        logger.exception("Failed to get commit diff")
        raise HTTPException(status_code=500, detail=str(e))


def _run_verification_analysis(project_path: Path, project_id: str, job_id: str, min_confidence: float = 0.5):
    """Background task to verify all roadmap items against current codebase."""
    try:
        _update_job_status(job_id, "running", progress=0)

        # Initialize engine
        engine = ReconciliationEngine(project_path, project_id)

        # Load roadmap
        _update_job_status(job_id, "running", progress=20)
        project = Project.from_path(project_path)
        roadmap_path = project.get_roadmap_path()

        if not roadmap_path or not roadmap_path.exists():
            # No roadmap - nothing to verify
            _update_job_status(
                job_id,
                "complete",
                progress=100,
                result={
                    "report_id": str(uuid.uuid4()),
                    "timestamp": datetime.now().isoformat(),
                    "old_snapshot_id": "",
                    "new_snapshot_id": "",
                    "commits_added": 0,
                    "files_changed": [],
                    "dependencies_changed": False,
                    "suggestions": [],
                    "already_completed_externally": [],
                },
            )
            return

        roadmap = Roadmap.parse(roadmap_path)

        # Run verification — pass min_confidence so the engine doesn't pre-filter above it
        _update_job_status(job_id, "running", progress=50)
        suggestions = engine.verify_all_items(roadmap, min_confidence=min_confidence)

        # Already filtered at min_confidence by the engine
        _update_job_status(job_id, "running", progress=80)
        filtered_suggestions = suggestions

        # Create report-like result
        report_id = str(uuid.uuid4())
        result = {
            "report_id": report_id,
            "timestamp": datetime.now().isoformat(),
            "old_snapshot_id": "verification",
            "new_snapshot_id": "current",
            "commits_added": 0,  # Not applicable for verification
            "files_changed": [],  # Not applicable for verification
            "dependencies_changed": False,
            "suggestions": [
                {
                    "item_text": s.item_text,
                    "milestone_name": s.milestone_name,
                    "confidence": s.confidence,
                    "reasoning": s.reasoning,
                    "matched_files": s.matched_files,
                    "matched_commits": s.matched_commits,
                    "session_id": s.session_id,
                }
                for s in filtered_suggestions
            ],
            "already_completed_externally": [],
        }

        _update_job_status(job_id, "complete", progress=100, result=result)

    except Exception as e:
        logger.exception(f"Verification analysis failed for job {job_id}")
        _update_job_status(job_id, "failed", progress=0, error=str(e))


def _run_ai_verification_analysis(project_path: Path, project_id: str, job_id: str, min_confidence: float = 0.5):
    """Background task to verify roadmap items using AI-powered semantic analysis."""
    try:
        _update_job_status(job_id, "running", progress=0)

        # Initialize engine
        engine = ReconciliationEngine(project_path, project_id)

        # Load roadmap
        _update_job_status(job_id, "running", progress=10)
        project = Project.from_path(project_path)
        roadmap_path = project.get_roadmap_path()

        if not roadmap_path or not roadmap_path.exists():
            # No roadmap - nothing to verify
            _update_job_status(
                job_id,
                "complete",
                progress=100,
                result={
                    "report_id": str(uuid.uuid4()),
                    "timestamp": datetime.now().isoformat(),
                    "old_snapshot_id": "ai_verification",
                    "new_snapshot_id": "current",
                    "commits_added": 0,
                    "files_changed": [],
                    "dependencies_changed": False,
                    "suggestions": [],
                    "already_completed_externally": [],
                },
            )
            return

        roadmap = Roadmap.parse(roadmap_path)

        # Progress callback to update job status
        def progress_callback(current: int, total: int, item_text: str):
            progress = 10 + int((current / total) * 80)  # 10% to 90%
            _update_job_status(
                job_id,
                "running",
                progress=progress,
            )
            logger.info(f"AI analyzing item {current}/{total}: {item_text[:50]}...")

        # Run AI verification (async)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            suggestions, ai_metadata = loop.run_until_complete(
                engine.verify_all_items_ai(roadmap, progress_callback=progress_callback)
            )
        finally:
            loop.close()

        # If all AI calls failed and there were candidates, mark job as failed
        if ai_metadata["candidates_found"] > 0 and ai_metadata["ai_calls_succeeded"] == 0:
            _update_job_status(
                job_id, "failed", progress=100,
                error="AI verification failed — Claude Code CLI may not be available or authenticated. "
                      f"{ai_metadata['ai_calls_failed']} items could not be analyzed."
            )
            return

        # Filter by confidence threshold
        _update_job_status(job_id, "running", progress=95)
        filtered_suggestions = [s for s in suggestions if s.confidence >= min_confidence]

        # Create report
        report_id = str(uuid.uuid4())
        result = {
            "report_id": report_id,
            "timestamp": datetime.now().isoformat(),
            "old_snapshot_id": "ai_verification",
            "new_snapshot_id": "current",
            "commits_added": 0,
            "files_changed": [],
            "dependencies_changed": False,
            "suggestions": [
                {
                    "item_text": s.item_text,
                    "milestone_name": s.milestone_name,
                    "confidence": s.confidence,
                    "reasoning": s.reasoning,
                    "matched_files": s.matched_files,
                    "matched_commits": s.matched_commits,
                    "session_id": s.session_id,
                }
                for s in filtered_suggestions
            ],
            "already_completed_externally": [],
            "ai_metadata": ai_metadata,
        }

        _update_job_status(job_id, "complete", progress=100, result=result)

    except Exception as e:
        logger.exception(f"AI verification analysis failed for job {job_id}")
        _update_job_status(job_id, "failed", progress=0, error=str(e))


@router.post("/{project_id:path}/reconcile/verify")
async def start_verification(
    project_id: str, background_tasks: BackgroundTasks, request: AnalyzeRequest = AnalyzeRequest()
) -> AnalysisJobResponse:
    """Start background verification of all roadmap items against codebase.

    This scans the entire codebase (file existence, git history, content)
    to verify which uncompleted roadmap items appear to actually be done.

    Uses heuristic-based matching (fast, free).
    """
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Core modules not loaded")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate and clamp min_confidence
    min_confidence = max(0.3, min(0.9, request.min_confidence))

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Start background task
    background_tasks.add_task(_run_verification_analysis, project_path, project_id, job_id, min_confidence)

    return AnalysisJobResponse(job_id=job_id, status="started")


@router.post("/{project_id:path}/reconcile/verify-ai")
async def start_ai_verification(
    project_id: str, background_tasks: BackgroundTasks, request: AnalyzeRequest = AnalyzeRequest()
) -> AnalysisJobResponse:
    """Start AI-powered verification using Claude Code for semantic analysis.

    This uses Claude Code to actually read and understand your codebase to determine
    which roadmap items have been completed. Much more accurate than heuristics but
    slower and requires Claude Code API calls.

    Cost: ~$0.10-0.50 per verification depending on roadmap size
    Time: 2-5 minutes for typical projects
    """
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Core modules not loaded")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate and clamp min_confidence
    min_confidence = max(0.3, min(0.9, request.min_confidence))

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Start background task
    background_tasks.add_task(_run_ai_verification_analysis, project_path, project_id, job_id, min_confidence)

    return AnalysisJobResponse(job_id=job_id, status="started")
