"""
SSE Streaming Dispatch API routes - Real-time Claude Code output streaming.

Provides Server-Sent Events (SSE) endpoints for streaming Claude CLI output
with sub-100ms latency from CLI output to UI display.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

# Import core modules
try:
    from src.agents.async_dispatcher import (
        AsyncDispatchJob,
        get_async_dispatch_output_path,
    )
    from src.core.provider_telemetry import usage_snapshot
    from src.core.provider_usage import ProviderUsageStore
    from src.core.project import ProjectRegistry
    from src.core.runtime import project_id_for_path
    from src.core.cost_tracker import CostTracker, TokenUsage

    CORE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Core modules not available for streaming: {e}")
    CORE_AVAILABLE = False


# In-memory job storage for active streaming jobs
_stream_jobs: dict[str, AsyncDispatchJob] = {}
_stream_jobs_lock = asyncio.Lock()
_MAX_STREAM_JOBS = 50


class StreamStartRequest(BaseModel):
    """Request to start a streaming dispatch job."""

    prompt: str
    project_id: str


class StreamStartResponse(BaseModel):
    """Response with job info for connecting to stream."""

    job_id: str
    stream_url: str
    status: Literal["starting", "running"]
    message: str


class StreamCancelResponse(BaseModel):
    """Response from cancelling a stream job."""

    success: bool
    message: str


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


async def _cleanup_old_jobs() -> None:
    """Remove completed jobs that are older than 5 minutes."""
    async with _stream_jobs_lock:
        now = datetime.now()
        to_remove = []
        for job_id, job in _stream_jobs.items():
            if not job.is_running:
                # Job is done, check age
                if hasattr(job, "_finished_at") and job._finished_at:
                    age = (now - job._finished_at).total_seconds()
                    if age > 300:  # 5 minutes
                        to_remove.append(job_id)
        for job_id in to_remove:
            del _stream_jobs[job_id]


async def _format_sse_event(
    event_type: str,
    data: str,
    sequence: int,
    job_id: str,
) -> str:
    """Format an SSE event string."""
    event_data = {
        "type": event_type,
        "data": data,
        "sequence": sequence,
        "timestamp": datetime.utcnow().isoformat(),
        "job_id": job_id,
    }
    return f"data: {json.dumps(event_data)}\n\n"


async def _stream_events(job: AsyncDispatchJob) -> AsyncGenerator[str, None]:
    """Generate SSE events from a dispatch job."""
    try:
        async for event_type, data, sequence in job.events():
            yield await _format_sse_event(event_type, data, sequence, job.job_id)
    except asyncio.CancelledError:
        yield await _format_sse_event("complete", "cancelled", 999999, job.job_id)
        raise


@router.post("/start")
async def stream_start(request: StreamStartRequest) -> StreamStartResponse:
    """Start a new streaming dispatch job.

    Returns a job_id and stream_url that the client can use to connect
    to the SSE stream endpoint.
    """
    if not CORE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Core modules not loaded - cannot start streaming dispatch",
        )

    project_path = _get_project_path(request.project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    # Generate job ID and output file
    job_id = f"stream-{uuid.uuid4().hex[:12]}"

    try:
        _session_id, output_file = get_async_dispatch_output_path(project_path, job_id)
    except Exception as exc:
        logger.warning(f"Failed to create output path: {exc}")
        output_file = None

    # Create and start the job
    job = AsyncDispatchJob(
        job_id=job_id,
        prompt=request.prompt,
        working_dir=project_path,
        cli_path="claude",
        timeout_seconds=900,
    )

    async with _stream_jobs_lock:
        # Cleanup old jobs first
        await _cleanup_old_jobs()

        if len(_stream_jobs) >= _MAX_STREAM_JOBS:
            raise HTTPException(
                status_code=503,
                detail="Too many active streaming jobs",
            )

        _stream_jobs[job_id] = job

    # Start the job
    job.start(output_file=output_file)

    return StreamStartResponse(
        job_id=job_id,
        stream_url=f"/api/dispatch/stream/{job_id}",
        status="starting",
        message="Dispatch job started. Connect to stream_url for real-time output.",
    )


@router.get("/{job_id}")
async def stream_events(job_id: str) -> StreamingResponse:
    """SSE endpoint for streaming dispatch output.

    Connect to this endpoint with EventSource to receive real-time
    Claude CLI output as Server-Sent Events.

    Event format:
    ```
    data: {"type":"output","data":"line of output","sequence":1,"timestamp":"...","job_id":"..."}

    data: {"type":"status","data":"Processing...","sequence":2,...}

    data: {"type":"complete","data":"success","sequence":99,...}
    ```

    Event types:
    - start: Initial connection established
    - output: A line of CLI output
    - status: Status update message
    - error: An error occurred
    - complete: Job finished (data is "success", "failed", "cancelled", or "token_limit")
    """
    async with _stream_jobs_lock:
        job = _stream_jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Streaming job not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        # Send initial start event
        yield await _format_sse_event("start", "Connected to dispatch stream", 0, job_id)

        # Stream events from the job
        async for event in _stream_events(job):
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("/{job_id}/cancel")
async def stream_cancel(job_id: str) -> StreamCancelResponse:
    """Cancel a running streaming dispatch job."""
    await _cleanup_old_jobs()
    async with _stream_jobs_lock:
        job = _stream_jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Streaming job not found")

    if not job.is_running:
        return StreamCancelResponse(
            success=False,
            message="Job is not running or already completed",
        )

    cancelled = job.cancel()

    if cancelled:
        return StreamCancelResponse(
            success=True,
            message="Job cancellation requested",
        )
    else:
        return StreamCancelResponse(
            success=False,
            message="Failed to cancel job",
        )


@router.get("/{job_id}/status")
async def stream_status(job_id: str) -> dict:
    """Get current status of a streaming job.

    Useful for checking job state without connecting to the stream.
    """
    await _cleanup_old_jobs()
    async with _stream_jobs_lock:
        job = _stream_jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Streaming job not found")

    result = job.get_result()

    return {
        "job_id": job_id,
        "is_running": job.is_running,
        "is_cancelled": job.is_cancelled,
        "has_result": result is not None,
        "result": {
            "success": result.success,
            "token_limit_reached": result.token_limit_reached,
            "cancelled": result.cancelled,
            "error_message": result.error_message,
        }
        if result
        else None,
    }


def _record_stream_usage(
    project_path: Path,
    prompt: str,
    provider: str,
    output: str | None,
    session_id: str | None,
    token_limit_reached: bool = False,
) -> None:
    """Record usage telemetry for a completed stream job."""
    if not CORE_AVAILABLE:
        return

    try:
        project_runtime_id = project_id_for_path(project_path)
        usage_store = ProviderUsageStore(project_runtime_id)
        snapshot = usage_snapshot(provider=provider, prompt=prompt, output=output)
        usage_store.record(
            snapshot=snapshot,
            source="stream_dispatch",
            session_id=session_id,
            metadata={
                "token_limit_reached": token_limit_reached,
                "streaming": True,
            },
        )

        # Keep Claude API cost history compatible with existing budget logic
        if provider == "claude":
            model = snapshot.model or "claude-3-5-sonnet-latest"
            cost_tracker = CostTracker(project_runtime_id)
            cost_tracker.record_usage(
                TokenUsage(
                    input_tokens=snapshot.input_tokens,
                    output_tokens=snapshot.output_tokens,
                    model=model,
                ),
                source="stream_dispatch",
                session_id=session_id,
            )
    except Exception as exc:
        logger.warning(f"Failed to record stream usage: {exc}")
