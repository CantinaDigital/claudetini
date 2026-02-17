"""Bootstrap API endpoints with real-time progress via SSE."""

import asyncio
import uuid
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.agents.bootstrap_engine import (
    BootstrapEngine,
    BootstrapResult,
    BootstrapStepType,
    StepResult,
)

router = APIRouter(prefix="/bootstrap", tags=["bootstrap"])

# In-memory storage for bootstrap sessions
_active_sessions: dict[str, dict] = {}


class BootstrapStartRequest(BaseModel):
    """Request to start bootstrap process."""

    project_path: str
    skip_git: bool = False
    skip_architecture: bool = False
    dry_run: bool = False


class BootstrapEstimateRequest(BaseModel):
    """Request to estimate bootstrap cost."""

    project_path: str


class BootstrapStatusResponse(BaseModel):
    """Bootstrap status response."""

    session_id: str
    status: str  # 'running', 'completed', 'failed'
    progress: float  # 0-100
    current_step: str
    step_index: int
    total_steps: int
    error: str | None = None


class StepResultResponse(BaseModel):
    """Per-step outcome in the bootstrap result."""

    step_type: str
    name: str
    status: str  # "success", "failed", "skipped"
    required: bool
    error: str | None = None


class BootstrapResultResponse(BaseModel):
    """Bootstrap result response."""

    success: bool
    artifacts: dict[str, str]
    errors: list[str]
    warnings: list[str]
    duration_seconds: float
    steps_completed: int
    steps_total: int
    step_results: list[StepResultResponse] = []


@router.post("/estimate")
async def estimate_cost(request: BootstrapEstimateRequest) -> dict:
    """Estimate the cost of bootstrapping a project.

    Returns estimated tokens and USD cost.
    """
    project_path = Path(request.project_path).resolve()

    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"Project path does not exist: {project_path}")

    try:
        engine = BootstrapEngine(project_path)
        estimate = engine.estimate_cost()
        return estimate

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Cost estimation failed: {exc}")


@router.post("/start")
async def start_bootstrap(request: BootstrapStartRequest) -> dict:
    """Start a bootstrap process and return session ID.

    Use /bootstrap/stream/{session_id} to monitor progress.
    """
    project_path = Path(request.project_path).resolve()

    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"Project path does not exist: {project_path}")

    # Generate session ID
    session_id = str(uuid.uuid4())

    # Initialize session state
    _active_sessions[session_id] = {
        "status": "pending",
        "progress": 0.0,
        "current_step": "Initializing",
        "step_index": 0,
        "total_steps": 5,
        "messages": [],
        "result": None,
        "error": None,
    }

    # Start bootstrap in background
    asyncio.create_task(
        _run_bootstrap_async(
            session_id=session_id,
            project_path=project_path,
            skip_git=request.skip_git,
            skip_architecture=request.skip_architecture,
            dry_run=request.dry_run,
        )
    )

    return {
        "session_id": session_id,
        "stream_url": f"/api/bootstrap/stream/{session_id}",
    }


@router.get("/stream/{session_id}")
async def stream_progress(session_id: str):
    """Stream bootstrap progress via Server-Sent Events (SSE).

    Clients should connect to this endpoint to receive real-time updates.
    """
    if session_id not in _active_sessions:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events for bootstrap progress."""
        last_message_count = 0

        while True:
            session = _active_sessions.get(session_id)
            if not session:
                break

            # Send any new messages
            messages = session["messages"]
            if len(messages) > last_message_count:
                for msg in messages[last_message_count:]:
                    yield f"data: {msg}\n\n"
                last_message_count = len(messages)

            # Check if complete
            if session["status"] in ("completed", "failed"):
                # Send final status
                final_data = {
                    "type": "complete",
                    "status": session["status"],
                    "result": session.get("result"),
                    "error": session.get("error"),
                }
                import json

                yield f"data: {json.dumps(final_data)}\n\n"
                break

            # Wait a bit before checking again
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/status/{session_id}", response_model=BootstrapStatusResponse)
async def get_status(session_id: str) -> BootstrapStatusResponse:
    """Get current status of a bootstrap session."""
    if session_id not in _active_sessions:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    session = _active_sessions[session_id]

    return BootstrapStatusResponse(
        session_id=session_id,
        status=session["status"],
        progress=session["progress"],
        current_step=session["current_step"],
        step_index=session["step_index"],
        total_steps=session["total_steps"],
        error=session.get("error"),
    )


@router.get("/result/{session_id}", response_model=BootstrapResultResponse)
async def get_result(session_id: str) -> BootstrapResultResponse:
    """Get the final result of a completed bootstrap session."""
    if session_id not in _active_sessions:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    session = _active_sessions[session_id]

    if session["status"] not in ("completed", "failed"):
        raise HTTPException(status_code=400, detail="Bootstrap not yet complete")

    result: BootstrapResult = session.get("result")
    if not result:
        raise HTTPException(status_code=500, detail="Result not available")

    return BootstrapResultResponse(
        success=result.success,
        artifacts={k: str(v) for k, v in result.artifacts.items()},
        errors=result.errors,
        warnings=result.warnings,
        duration_seconds=result.duration_seconds,
        steps_completed=result.steps_completed,
        steps_total=result.steps_total,
        step_results=[
            StepResultResponse(
                step_type=sr.step_type,
                name=sr.name,
                status=sr.status,
                required=sr.required,
                error=sr.error,
            )
            for sr in result.step_results
        ],
    )


@router.delete("/session/{session_id}")
async def cleanup_session(session_id: str) -> dict:
    """Clean up a bootstrap session from memory."""
    if session_id in _active_sessions:
        del _active_sessions[session_id]
        return {"status": "deleted"}

    raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")


async def _run_bootstrap_async(
    session_id: str,
    project_path: Path,
    skip_git: bool,
    skip_architecture: bool,
    dry_run: bool,
) -> None:
    """Run bootstrap in background and update session state."""
    import json

    session = _active_sessions[session_id]
    session["status"] = "running"

    def progress_callback(
        step_type: BootstrapStepType,
        progress: float,
        message: str,
        step_index: int,
        total_steps: int,
    ) -> None:
        """Update session state with progress."""
        session["progress"] = progress
        session["current_step"] = message
        session["step_index"] = step_index
        session["total_steps"] = total_steps

        # Add progress message to stream
        progress_data = {
            "type": "progress",
            "progress": progress,
            "message": message,
            "step": f"{step_index}/{total_steps}",
            "step_type": step_type.value,
        }
        session["messages"].append(json.dumps(progress_data))

    try:
        # Create engine with progress callback
        engine = BootstrapEngine(
            project_path=project_path,
            progress_callback=progress_callback,
        )

        # Run bootstrap (this is synchronous but we're in an async task)
        result = await asyncio.to_thread(
            engine.bootstrap,
            skip_git=skip_git,
            skip_architecture=skip_architecture,
            dry_run=dry_run,
        )

        # Update session with result
        session["status"] = "completed" if result.success else "failed"
        session["result"] = result
        session["progress"] = 100.0

        if not result.success:
            session["error"] = "; ".join(result.errors)

    except Exception as exc:
        session["status"] = "failed"
        session["error"] = str(exc)
        session["progress"] = 0.0

        error_data = {
            "type": "error",
            "error": str(exc),
        }
        session["messages"].append(json.dumps(error_data))
