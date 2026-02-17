"""
Dispatch API routes - Launch Claude Code sessions
"""

import json
import logging
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

router = APIRouter()
logger = logging.getLogger(__name__)

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_ANSI_OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")

# Regex to strip bold markdown numbering (e.g. "**1.2** Task text" -> "Task text")
_BOLD_NUMBERING_RE = re.compile(r"^\*\*[\d.]+\*\*\s*")

# Import core modules
try:
    from src.agents.codex_dispatcher import dispatch_task as dispatch_codex_task
    from src.agents.dispatcher import DispatchLogger, dispatch_task as dispatch_claude_task
    from src.agents.dispatcher import get_dispatch_output_path
    from src.agents.gates import QualityGateRunner
    from src.agents.gemini_dispatcher import dispatch_task as dispatch_gemini_task
    from src.core.cost_tracker import CostTracker, TokenUsage
    from src.core.project import ProjectRegistry
    from src.core.provider_telemetry import usage_snapshot
    from src.core.provider_usage import ProviderUsageStore
    from src.core.runtime import project_id_for_path, project_runtime_dir
    from src.core.token_budget import TokenBudgetManager

    CORE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Core modules not available: {e}")
    CORE_AVAILABLE = False


def _strip_ansi(value: str) -> str:
    """Strip ANSI control sequences from terminal output."""
    cleaned = _ANSI_OSC_RE.sub("", value)
    return _ANSI_ESCAPE_RE.sub("", cleaned)


def _parse_jsonl_line(line: str) -> str:
    """Extract human-readable text from a JSONL log line.

    Claude CLI outputs lines like {"level":"info","message":"Working on task..."}.
    Returns the message text, or the original line if not JSONL.
    """
    stripped = line.strip()
    if not stripped.startswith("{"):
        return line
    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict) and "message" in obj:
            return obj["message"]
        return line
    except (json.JSONDecodeError, ValueError):
        return line


def _read_log_file_tail(log_file: str | None, max_lines: int = 24, max_chars: int = 2400) -> str | None:
    """Read the tail of a log file for live output display.

    Only reads files within known safe directories (runtime dispatch-output
    and /tmp) to prevent path traversal.
    """
    if not log_file:
        return None
    try:
        path = Path(log_file).resolve()

        # Validate the resolved path is within allowed directories
        allowed_prefixes = (
            Path.home() / ".claude",
            Path.home() / ".claudetini",
            Path("/tmp"),
        )
        if not any(str(path).startswith(str(prefix.resolve())) for prefix in allowed_prefixes):
            logger.warning("Blocked read of log file outside allowed directories: %s", path)
            return None

        if not path.exists():
            return None
        content = path.read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            return None
        sanitized = _strip_ansi(content)
        lines = [
            _parse_jsonl_line(line)
            for line in sanitized.splitlines()
            if line.strip()
        ]
        if not lines:
            return None
        text = "\n".join(lines[-max_lines:])
        if len(text) > max_chars:
            text = text[-max_chars:]
        return text
    except Exception:
        return None


class DispatchRequest(BaseModel):
    """Request model for initiating a Claude dispatch job."""

    prompt: str = Field(..., min_length=1, max_length=50000)
    project_id: str = Field(..., min_length=1, max_length=2048)


class DispatchResponse(BaseModel):
    """Response model for completed dispatch job results."""

    success: bool
    sessionId: str | None = None
    error: str | None = None
    error_code: str | None = None
    output: str | None = None
    verification: dict[str, str] | None = None
    provider: str = "claude"
    token_limit_reached: bool = False


class DispatchStartResponse(BaseModel):
    """Response model when starting an async dispatch job."""

    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    phase: str
    message: str


class DispatchStatusResponse(BaseModel):
    """Response model for checking the status of a running dispatch job."""

    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    phase: str
    message: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    done: bool
    result: DispatchResponse | None = None
    error_detail: str | None = None
    output_tail: str | None = None
    log_file: str | None = None


class FallbackDispatchRequest(BaseModel):
    """Request model for dispatching to fallback providers (Codex/Gemini)."""

    provider: Literal["codex", "gemini"]
    prompt: str = Field(..., min_length=1, max_length=50000)
    project_path: str = Field(..., min_length=1, max_length=2048)
    cli_path: str | None = Field(None, max_length=2048)


class DispatchAdviceRequest(BaseModel):
    """Request model for getting dispatch advice based on usage and cost estimates."""

    prompt: str = Field(..., min_length=1, max_length=50000)
    project_path: str = Field(..., min_length=1, max_length=2048)
    preferred_fallback: Literal["codex", "gemini"] | None = None
    usage_mode: Literal["subscription", "api"] = "subscription"
    claude_remaining_pct: float | None = None
    fallback_threshold_pct: float = 10.0


class DispatchAdviceResponse(BaseModel):
    """Response model with cost estimates and fallback recommendations."""

    estimated_tokens: int
    estimated_cost: float | None = None
    estimated_effort_units: float
    usage_mode: Literal["subscription", "api"]
    telemetry_source: str = "heuristic"
    remaining_pct: float | None = None
    should_suggest_fallback: bool = False
    suggested_provider: Literal["codex", "gemini"] | None = None
    reason: str


class ProviderUsageTotalsResponse(BaseModel):
    """Usage totals for a single provider (Claude, Codex, or Gemini)."""

    tokens: int
    effort_units: float
    cost_usd: float
    events: int


class DispatchUsageSummaryResponse(BaseModel):
    """Aggregated usage summary across all providers for a project."""

    project_id: str
    days: int
    providers: dict[str, ProviderUsageTotalsResponse]
    total_tokens: int
    total_effort_units: float
    total_cost_usd: float
    total_events: int
    latest_event_at: str | None = None


_dispatch_jobs: dict[str, dict] = {}
_dispatch_jobs_lock = threading.Lock()
_MAX_DISPATCH_JOBS = 200

_fallback_jobs: dict[str, dict] = {}
_fallback_jobs_lock = threading.Lock()
_MAX_FALLBACK_JOBS = 200


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


def _resolve_fallback_request(
    request: FallbackDispatchRequest,
) -> tuple[Literal["codex", "gemini"], Path, str]:
    """Validate and normalize fallback dispatch request fields."""
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Core modules not loaded - cannot dispatch sessions")

    project_path = Path(request.project_path).expanduser().resolve()
    if not project_path.exists():
        raise HTTPException(status_code=404, detail="Project path not found")
    if not project_path.is_dir():
        raise HTTPException(status_code=400, detail="project_path must be a directory")

    provider = request.provider
    cli_path = request.cli_path or provider
    return provider, project_path, cli_path


@router.post("/start")
async def dispatch_start(request: DispatchRequest) -> DispatchStartResponse:
    """Start an asynchronous Claude dispatch job and return a job ID immediately."""
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Core modules not loaded - cannot dispatch sessions")

    project_path = _get_project_path(request.project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    job = _create_dispatch_job(prompt=request.prompt, project_path=project_path)
    worker = threading.Thread(
        target=_run_dispatch_job,
        kwargs={
            "job_id": job["job_id"],
            "prompt": request.prompt,
            "project_path": project_path,
        },
        daemon=True,
        name=f"dispatch-{job['job_id']}",
    )
    worker.start()

    return DispatchStartResponse(
        job_id=job["job_id"],
        status=job["status"],
        phase=job["phase"],
        message=job["message"],
    )


class CancelResponse(BaseModel):
    """Response model for job cancellation requests."""

    success: bool
    message: str


@router.post("/cancel/{job_id}")
async def dispatch_cancel(job_id: str) -> CancelResponse:
    """Cancel a running dispatch job."""
    job = _get_dispatch_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Dispatch job not found")

    if job.get("done"):
        return CancelResponse(success=False, message="Job already completed")

    # Mark job as cancelled
    _update_dispatch_job(
        job_id,
        status="failed",
        phase="cancelled",
        message="Dispatch cancelled by user.",
        finished_at=datetime.utcnow().isoformat(),
        done=True,
        cancelled=True,
        result=DispatchResponse(success=False, error="Cancelled by user").model_dump(),
        error_detail="Job was cancelled by user request.",
    )

    return CancelResponse(success=True, message="Job cancelled")


@router.get("/status/{job_id}")
async def dispatch_status(job_id: str) -> DispatchStatusResponse:
    """Get current status/result for a dispatch job.

    During execution, reads live output from the log file so callers can
    see Claude's progress in real-time.

    Also handles stream job IDs (prefix "stream-") by looking up the
    streaming job store — this supports the SSE-to-polling fallback path.
    """
    job = _get_dispatch_job(job_id)

    # Bridge: if not found in dispatch jobs and ID is a stream job, look up stream jobs
    if not job and job_id.startswith("stream-"):
        return await _bridge_stream_job_status(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Dispatch job not found")

    result_payload = job.get("result")
    result = DispatchResponse(**result_payload) if isinstance(result_payload, dict) else None

    # Read live output from log file during execution
    # After completion, use the stored output_tail from the job
    output_tail = job.get("output_tail")
    if not job.get("done") and job.get("log_file"):
        # Job is still running - read current output from log file
        live_tail = _read_log_file_tail(job.get("log_file"))
        if live_tail:
            output_tail = live_tail

    return DispatchStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        phase=job["phase"],
        message=job["message"],
        created_at=job["created_at"],
        started_at=job.get("started_at"),
        finished_at=job.get("finished_at"),
        done=bool(job.get("done")),
        result=result,
        error_detail=job.get("error_detail"),
        output_tail=output_tail,
        log_file=job.get("log_file"),
    )


async def _bridge_stream_job_status(job_id: str) -> DispatchStatusResponse:
    """Bridge a stream job into a DispatchStatusResponse for the polling fallback path.

    When SSE streaming starts but the EventSource connection drops, the client
    falls back to polling with the stream job ID. This function translates the
    stream job state into the expected polling response format.
    """
    from .dispatch_stream import _stream_jobs, _stream_jobs_lock

    async with _stream_jobs_lock:
        stream_job = _stream_jobs.get(job_id)

    if not stream_job:
        raise HTTPException(status_code=404, detail="Dispatch job not found")

    is_running = stream_job.is_running
    is_cancelled = stream_job.is_cancelled
    job_result = stream_job.get_result()

    # Read live output from the job's log file
    output_tail: str | None = None
    log_file: str | None = None
    if stream_job.output_file:
        log_file = str(stream_job.output_file)
        live_tail = _read_log_file_tail(log_file)
        if live_tail:
            output_tail = live_tail

    # Determine status/phase/message
    if is_running:
        status = "running"
        phase = "running"
        message = "Claude Code is processing your task."
        done = False
    elif is_cancelled:
        status = "failed"
        phase = "cancelled"
        message = "Job was cancelled."
        done = True
    elif job_result is not None:
        done = True
        if job_result.success:
            status = "succeeded"
            phase = "complete"
            message = "Claude Code completed successfully."
        elif job_result.token_limit_reached:
            status = "failed"
            phase = "failed"
            message = "Claude Code token limit reached."
        else:
            status = "failed"
            phase = "failed"
            message = job_result.error_message or "Claude Code did not complete successfully."
    else:
        # Not running, no result yet — transitional state
        status = "running"
        phase = "launching"
        message = "Launching Claude Code CLI..."
        done = False

    # Build a DispatchResponse from the stream result if available
    result: DispatchResponse | None = None
    error_detail: str | None = None
    if job_result is not None:
        result = DispatchResponse(
            success=job_result.success,
            error=job_result.error_message,
            output=job_result.output,
            token_limit_reached=job_result.token_limit_reached,
        )
        if not job_result.success and job_result.error_message:
            error_detail = job_result.error_message

        # If done, also try to get final output_tail from the result
        if not output_tail and job_result.output:
            sanitized = _strip_ansi(job_result.output)
            lines = [line.rstrip() for line in sanitized.splitlines() if line.strip()]
            if lines:
                output_tail = "\n".join(lines[-24:])

    return DispatchStatusResponse(
        job_id=job_id,
        status=status,
        phase=phase,
        message=message,
        created_at=datetime.utcnow().isoformat(),
        started_at=None,
        finished_at=datetime.utcnow().isoformat() if done else None,
        done=done,
        result=result,
        error_detail=error_detail,
        output_tail=output_tail,
        log_file=log_file,
    )


@router.post("")
async def dispatch(request: DispatchRequest) -> DispatchResponse:
    """Dispatch a Claude Code session"""
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Core modules not loaded - cannot dispatch sessions")

    project_path = _get_project_path(request.project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        # Dispatch uses subprocess execution and can run for several minutes.
        # Run it off the event loop so the rest of the API remains responsive.
        result = await run_in_threadpool(dispatch_claude_task, request.prompt, project_path)
        # Log dispatch event for the Logs tab (both success and failure)
        _log_dispatch_event(result, request.prompt, project_path)
        if result.success or result.token_limit_reached:
            _record_usage_event(
                project_path=project_path,
                prompt=request.prompt,
                provider=result.provider,
                output=result.output,
                session_id=result.session_id,
                source="dispatch",
                token_limit_reached=result.token_limit_reached,
            )
        return _dispatch_response_from_result(result)
    except Exception as e:
        logger.error(f"Dispatch failed: {e}")
        return DispatchResponse(
            success=False,
            error=str(e),
        )


@router.post("/fallback/start")
async def fallback_dispatch_start(request: FallbackDispatchRequest) -> DispatchStartResponse:
    """Start an asynchronous fallback dispatch job and return a job ID immediately."""
    provider, project_path, cli_path = _resolve_fallback_request(request)
    job = _create_fallback_job(
        prompt=request.prompt,
        project_path=project_path,
        provider=provider,
        cli_path=cli_path,
    )
    worker = threading.Thread(
        target=_run_fallback_job,
        kwargs={
            "job_id": job["job_id"],
            "prompt": request.prompt,
            "provider": provider,
            "project_path": project_path,
            "cli_path": cli_path,
        },
        daemon=True,
        name=f"fallback-{job['job_id']}",
    )
    worker.start()
    return DispatchStartResponse(
        job_id=job["job_id"],
        status=job["status"],
        phase=job["phase"],
        message=job["message"],
    )


@router.get("/fallback/status/{job_id}")
async def fallback_dispatch_status(job_id: str) -> DispatchStatusResponse:
    """Get current status/result for a fallback dispatch job."""
    job = _get_fallback_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Fallback dispatch job not found")

    result_payload = job.get("result")
    result = DispatchResponse(**result_payload) if isinstance(result_payload, dict) else None

    output_tail = job.get("output_tail")
    message = job["message"]
    if not job.get("done") and job.get("log_file"):
        live_tail = _read_log_file_tail(job.get("log_file"))
        if live_tail:
            output_tail = live_tail
            message = f"{job['provider'].capitalize()} is running..."
        else:
            started_at = job.get("started_at")
            if isinstance(started_at, str):
                try:
                    elapsed = (datetime.utcnow() - datetime.fromisoformat(started_at)).total_seconds()
                    if elapsed > 30:
                        message = "Running... waiting for CLI output."
                except ValueError:
                    pass

    return DispatchStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        phase=job["phase"],
        message=message,
        created_at=job["created_at"],
        started_at=job.get("started_at"),
        finished_at=job.get("finished_at"),
        done=bool(job.get("done")),
        result=result,
        error_detail=job.get("error_detail"),
        output_tail=output_tail,
        log_file=job.get("log_file"),
    )


@router.post("/fallback/cancel/{job_id}")
async def fallback_dispatch_cancel(job_id: str) -> CancelResponse:
    """Cancel a running fallback dispatch job."""
    job = _get_fallback_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Fallback dispatch job not found")
    if job.get("done"):
        return CancelResponse(success=False, message="Job already completed")

    cancel_event = job.get("cancel_event")
    if isinstance(cancel_event, threading.Event):
        cancel_event.set()

    _update_fallback_job(
        job_id,
        phase="cancelling",
        message="Cancellation requested...",
    )
    return CancelResponse(success=True, message="Cancellation requested")


@router.post("/fallback")
async def fallback_dispatch(request: FallbackDispatchRequest) -> DispatchResponse:
    """Legacy synchronous fallback dispatch endpoint."""
    provider, project_path, cli_path = _resolve_fallback_request(request)

    try:
        if provider == "codex":
            result = await run_in_threadpool(
                dispatch_codex_task,
                request.prompt,
                project_path,
                cli_path,
            )
        else:
            result = await run_in_threadpool(
                dispatch_gemini_task,
                request.prompt,
                project_path,
                cli_path,
            )

        # Log dispatch event for the Logs tab (both success and failure)
        _log_dispatch_event(result, request.prompt, project_path)

        verification: dict[str, str] | None = None
        if result.success:
            verified, verification, verification_error = _verify_fallback_gates(project_path, request.prompt)
            if not verified:
                code = "verification_failed"
                return _dispatch_response_from_result(
                    result,
                    error_override=verification_error or "Post-run gate verification failed.",
                    error_code=code,
                    success_override=False,
                    verification=verification,
                )
            _record_usage_event(
                project_path=project_path,
                prompt=request.prompt,
                provider=result.provider,
                output=result.output,
                session_id=result.session_id,
                source="fallback_dispatch",
            )
            return _dispatch_response_from_result(result, verification=verification)

        error_code = _classify_fallback_failure(
            provider=provider,
            error=result.error_message,
            output=result.output,
        )
        return _dispatch_response_from_result(result, error_code=error_code)
    except Exception as exc:
        logger.error("Fallback dispatch failed for %s: %s", provider, exc)
        raise HTTPException(status_code=503, detail=f"Fallback dispatch failed for {provider}: {exc}")


@router.post("/advice")
async def dispatch_advice(request: DispatchAdviceRequest) -> DispatchAdviceResponse:
    """Return pre-dispatch budget/risk advice for a prompt."""
    usage_mode = request.usage_mode
    snapshot = usage_snapshot("claude", request.prompt, output=None)

    if not CORE_AVAILABLE:
        return DispatchAdviceResponse(
            estimated_tokens=snapshot.total_tokens,
            estimated_cost=None,
            estimated_effort_units=snapshot.effort_units,
            usage_mode=usage_mode,
            telemetry_source=snapshot.telemetry_source,
            remaining_pct=None,
            should_suggest_fallback=False,
            reason="Core modules not loaded; using heuristic estimate only.",
        )

    project_path = Path(request.project_path).expanduser().resolve()
    if not project_path.exists():
        raise HTTPException(status_code=404, detail="Project path not found")
    if not project_path.is_dir():
        raise HTTPException(status_code=400, detail="project_path must be a directory")

    project_id = project_id_for_path(project_path)
    budget_manager = TokenBudgetManager(project_id=project_id)

    estimated_tokens = snapshot.total_tokens
    estimated_effort_units = snapshot.effort_units

    should_suggest_fallback = False
    remaining_pct: float | None
    estimated_cost: float | None

    if usage_mode == "subscription":
        estimated_cost = None
        remaining_pct = _clamp_percent(request.claude_remaining_pct)
        threshold_pct = _clamp_threshold(request.fallback_threshold_pct)
        if remaining_pct is not None and remaining_pct < threshold_pct:
            should_suggest_fallback = True
            reason = (
                f"Estimated {estimated_tokens} tokens ({estimated_effort_units:.2f} effort units). "
                f"Claude subscription remaining is {remaining_pct:.1f}% (< {threshold_pct:.1f}%)."
            )
        elif remaining_pct is not None:
            reason = (
                f"Estimated {estimated_tokens} tokens ({estimated_effort_units:.2f} effort units). "
                f"Claude subscription remaining is {remaining_pct:.1f}%."
            )
        else:
            reason = (
                f"Estimated {estimated_tokens} tokens ({estimated_effort_units:.2f} effort units). "
                "Set Claude remaining % in Settings for automatic fallback suggestions."
            )
    else:
        estimated_cost = budget_manager.estimate_dispatch_cost(request.prompt)
        remaining_pct = budget_manager.remaining_budget_percent(estimated_cost=estimated_cost)
        decision = budget_manager.evaluate_dispatch(estimated_cost=estimated_cost)
        reason = (
            f"Estimated {estimated_tokens} tokens, {estimated_effort_units:.2f} effort units, "
            f"and ${estimated_cost:.2f}."
        )

        if remaining_pct is None:
            reason = (
                f"Estimated {estimated_tokens} tokens, {estimated_effort_units:.2f} effort units, "
                f"and ${estimated_cost:.2f}. No API budget cap configured."
            )
        elif remaining_pct < 10.0:
            should_suggest_fallback = True
            reason = (
                f"Estimated {estimated_tokens} tokens, {estimated_effort_units:.2f} effort units, "
                f"and ${estimated_cost:.2f}. Projected Claude API budget remaining: {remaining_pct:.1f}%."
            )
        elif decision.exceeded:
            should_suggest_fallback = True
            reason = decision.message

    if should_suggest_fallback:
        suggested_provider = request.preferred_fallback or "codex"
    else:
        suggested_provider = None

    return DispatchAdviceResponse(
        estimated_tokens=estimated_tokens,
        estimated_cost=estimated_cost,
        estimated_effort_units=estimated_effort_units,
        usage_mode=usage_mode,
        telemetry_source=snapshot.telemetry_source,
        remaining_pct=remaining_pct,
        should_suggest_fallback=should_suggest_fallback,
        suggested_provider=suggested_provider,
        reason=reason,
    )


@router.get("/usage/{project_id:path}")
async def dispatch_usage_summary(project_id: str, days: int = Query(7, ge=1, le=365)) -> DispatchUsageSummaryResponse:
    """Return provider usage totals for a project over the selected window."""
    if not CORE_AVAILABLE:
        return DispatchUsageSummaryResponse(
            project_id=project_id,
            days=days,
            providers={},
            total_tokens=0,
            total_effort_units=0.0,
            total_cost_usd=0.0,
            total_events=0,
            latest_event_at=None,
        )

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    project_runtime_id = project_id_for_path(project_path)
    usage_store = ProviderUsageStore(project_runtime_id)
    totals = usage_store.totals(days=max(1, min(days, 365)))
    providers = {
        provider: ProviderUsageTotalsResponse(**values)
        for provider, values in totals.get("providers", {}).items()
    }
    all_totals = totals.get("all", {})
    latest_event = usage_store.latest_event_timestamp()

    return DispatchUsageSummaryResponse(
        project_id=str(project_path),
        days=max(1, min(days, 365)),
        providers=providers,
        total_tokens=int(all_totals.get("tokens", 0)),
        total_effort_units=float(all_totals.get("effort_units", 0.0)),
        total_cost_usd=float(all_totals.get("cost_usd", 0.0)),
        total_events=int(all_totals.get("events", 0)),
        latest_event_at=latest_event.isoformat() if latest_event else None,
    )


class DispatchOutputResponse(BaseModel):
    """Response for dispatch output file reading."""
    lines: list[str]
    exists: bool
    line_count: int


class EnrichPromptRequest(BaseModel):
    """Request for prompt enrichment."""
    task_text: str = Field(..., min_length=1, max_length=50000)
    custom_prompt: str | None = Field(None, max_length=50000)
    project_path: str = Field(..., min_length=1, max_length=2048)


class EnrichPromptResponse(BaseModel):
    """Response for enriched prompt."""
    enriched_prompt: str
    context_added: list[str]


class GenerateTaskPromptRequest(BaseModel):
    """Request for AI-generated task prompt."""
    task_text: str = Field(..., min_length=1, max_length=50000)
    project_path: str = Field(..., min_length=1, max_length=2048)


class GenerateTaskPromptResponse(BaseModel):
    """Response for AI-generated task prompt."""
    prompt: str
    ai_generated: bool
    error: str | None = None


class DispatchSummaryRequest(BaseModel):
    """Request for dispatch summary."""
    session_id: str = Field(..., min_length=1, max_length=2048)
    project_path: str = Field(..., min_length=1, max_length=2048)
    log_file: str | None = Field(None, max_length=2048)  # Direct path to dispatch output log


class FileChange(BaseModel):
    """File change information."""
    file: str
    lines_added: int
    lines_removed: int
    status: str  # "modified", "added", "deleted"


class DispatchSummaryResponse(BaseModel):
    """Response for dispatch summary."""
    success: bool
    files_changed: list[FileChange]
    total_added: int
    total_removed: int
    summary_message: str | None
    has_errors: bool


@router.get("/output/{session_id}")
async def read_dispatch_output(session_id: str) -> DispatchOutputResponse:
    """Read dispatch output file and return lines.

    Allows frontend to tail the output file that dispatcher.py writes to.
    Returns all lines each time (frontend tracks what it's already seen).
    """
    if not CORE_AVAILABLE:
        return DispatchOutputResponse(lines=[], exists=False, line_count=0)

    if ".." in session_id:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    try:
        # Clean session_id (remove .log extension if present)
        session_id_clean = session_id.replace(".log", "")

        # Try to get output file path
        # The session_id might be a full path or just an ID
        if "/" in session_id_clean:
            # Full path provided
            output_file = Path(session_id_clean)
        else:
            # Just an ID - need to find the file
            # Look in all dispatch jobs first
            for job_id, job in list(_dispatch_jobs.items()):
                log_file = job.get("log_file")
                if log_file and session_id_clean in log_file:
                    output_file = Path(log_file)
                    break
            else:
                # Not in dispatch jobs, try fallback jobs
                for job_id, job in list(_fallback_jobs.items()):
                    log_file = job.get("log_file")
                    if log_file and session_id_clean in log_file:
                        output_file = Path(log_file)
                        break
                else:
                    # Last resort: try to construct path
                    # This handles cases where the job is very old and pruned
                    return DispatchOutputResponse(lines=[], exists=False, line_count=0)

        if not output_file.exists():
            return DispatchOutputResponse(lines=[], exists=False, line_count=0)

        # Read all lines
        content = output_file.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()

        return DispatchOutputResponse(
            lines=lines,
            exists=True,
            line_count=len(lines)
        )
    except Exception as e:
        logger.error(f"Failed to read dispatch output for {session_id}: {e}")
        return DispatchOutputResponse(lines=[], exists=False, line_count=0)


@router.post("/enrich-prompt")
async def enrich_prompt(request: EnrichPromptRequest) -> EnrichPromptResponse:
    """Enrich a task prompt with project context."""
    if not CORE_AVAILABLE:
        # Fallback to basic prompt if core modules not available
        clean = _BOLD_NUMBERING_RE.sub('', request.task_text).strip()
        basic = request.custom_prompt or f"Implement: {clean}"
        return EnrichPromptResponse(
            enriched_prompt=basic,
            context_added=[]
        )

    try:
        from src.core.prompt_enricher import PromptEnricher

        project_path = Path(request.project_path).expanduser().resolve()
        if not project_path.exists():
            raise HTTPException(status_code=404, detail="Project path not found")

        enricher = PromptEnricher(project_path)
        result = enricher.enrich_task_prompt(
            task_text=request.task_text,
            custom_prompt=request.custom_prompt
        )

        return EnrichPromptResponse(
            enriched_prompt=result.prompt,
            context_added=result.context_added
        )
    except Exception as e:
        logger.error(f"Failed to enrich prompt: {e}")
        # Fallback to basic prompt on error
        clean = _BOLD_NUMBERING_RE.sub('', request.task_text).strip()
        basic = request.custom_prompt or f"Implement: {clean}"
        return EnrichPromptResponse(
            enriched_prompt=basic,
            context_added=[]
        )


@router.post("/generate-task-prompt")
async def generate_task_prompt(request: GenerateTaskPromptRequest) -> GenerateTaskPromptResponse:
    """Generate an implementation prompt for a roadmap task using Claude Code.

    Sends the task text and project context to Claude Code CLI, which analyzes
    the codebase and generates a detailed implementation prompt.
    """
    if not CORE_AVAILABLE:
        clean = _BOLD_NUMBERING_RE.sub('', request.task_text).strip()
        return GenerateTaskPromptResponse(
            prompt=f"Implement: {clean}",
            ai_generated=False,
            error="Core modules not available"
        )

    project_path = Path(request.project_path).expanduser().resolve()
    if not project_path.exists():
        raise HTTPException(status_code=404, detail="Project path not found")

    clean_task = _BOLD_NUMBERING_RE.sub('', request.task_text).strip()

    # Read CLAUDE.md for project context
    claude_md_content = ""
    claude_md = project_path / "CLAUDE.md"
    if claude_md.exists():
        try:
            raw = claude_md.read_text(encoding="utf-8")
            # Truncate to keep prompt manageable
            claude_md_content = raw[:3000] + ("..." if len(raw) > 3000 else "")
        except Exception:
            pass

    # Read ROADMAP.md for milestone context
    roadmap_context = ""
    roadmap_path = project_path / ".claude" / "planning" / "ROADMAP.md"
    if roadmap_path.exists():
        try:
            raw = roadmap_path.read_text(encoding="utf-8")
            # Just the first 2000 chars for context
            roadmap_context = raw[:2000] + ("..." if len(raw) > 2000 else "")
        except Exception:
            pass

    meta_prompt = f"""You are generating an implementation prompt for a developer task. Your job is to write a clear, actionable prompt that another Claude Code session will execute.

Task: {clean_task}

Project CLAUDE.md:
```
{claude_md_content}
```

Roadmap context:
```
{roadmap_context}
```

Write a detailed implementation prompt that:
1. States exactly what needs to be built or changed
2. Lists the specific files that likely need modification (based on the project structure in CLAUDE.md)
3. Describes the expected behavior
4. Notes any edge cases or gotchas based on the project conventions
5. Specifies acceptance criteria

Write the prompt as if you're instructing a developer. Be specific about file paths, component names, and patterns to follow. Do NOT include meta-commentary — just output the implementation prompt directly.

Keep it under 800 words. Start with a one-line summary of the task."""

    try:
        result = await run_in_threadpool(
            dispatch_claude_task,
            prompt=meta_prompt,
            working_dir=project_path,
        )

        if result.success and result.output:
            generated = result.output.strip()
            # Remove any markdown code fences if Claude wrapped its response
            if generated.startswith("```"):
                lines = generated.split("\n")
                lines = [l for l in lines if not l.startswith("```")]
                generated = "\n".join(lines).strip()

            return GenerateTaskPromptResponse(
                prompt=generated,
                ai_generated=True,
            )
        else:
            logger.error(f"Claude Code failed to generate task prompt: {result.error_message}")
            return GenerateTaskPromptResponse(
                prompt=f"Implement: {clean_task}",
                ai_generated=False,
                error=result.error_message or "Claude Code dispatch failed",
            )

    except Exception as e:
        logger.exception(f"Failed to generate AI task prompt: {e}")
        return GenerateTaskPromptResponse(
            prompt=f"Implement: {clean_task}",
            ai_generated=False,
            error=str(e),
        )


@router.post("/summary")
async def get_dispatch_summary(request: DispatchSummaryRequest) -> DispatchSummaryResponse:
    """Get summary of what a dispatch accomplished."""
    if not CORE_AVAILABLE:
        return DispatchSummaryResponse(
            success=False,
            files_changed=[],
            total_added=0,
            total_removed=0,
            summary_message=None,
            has_errors=True
        )

    try:
        from src.core.git_utils import GitUtils

        project_path = Path(request.project_path).expanduser().resolve()
        if not project_path.exists():
            raise HTTPException(status_code=404, detail="Project path not found")

        git = GitUtils(project_path)

        # Get uncommitted files with line change stats
        uncommitted = git.uncommitted_files_with_lines()

        files_changed = []
        total_added = 0
        total_removed = 0

        for file_info in uncommitted:
            added = 0
            removed = 0
            if file_info.get("lines"):
                # lines format is "+N -M"
                parts = file_info["lines"].split()
                for part in parts:
                    if part.startswith("+"):
                        added = int(part[1:])
                    elif part.startswith("-"):
                        removed = int(part[1:])

            files_changed.append(FileChange(
                file=file_info["path"],
                lines_added=added,
                lines_removed=removed,
                status=file_info.get("status", "M")
            ))

            total_added += added
            total_removed += removed

        # Read dispatch output to check for errors
        summary_message = None
        has_errors = False
        job_result_checked = False

        # Primary: check the actual dispatch job result (most reliable signal)
        for store, lock in [(_dispatch_jobs, _dispatch_jobs_lock), (_fallback_jobs, _fallback_jobs_lock)]:
            with lock:
                job = store.get(request.session_id)
                if job:
                    result_data = job.get("result")
                    if isinstance(result_data, dict):
                        has_errors = not result_data.get("success", True)
                        job_result_checked = True
                    break

        # Try to find the output file using multiple strategies
        output_file = None

        # Option 1: Direct log file path provided by frontend
        if request.log_file:
            candidate = Path(request.log_file)
            if candidate.exists():
                output_file = candidate

        # Option 2: Look up from active dispatch jobs by job_id
        if output_file is None:
            with _dispatch_jobs_lock:
                job = _dispatch_jobs.get(request.session_id)
                if job and job.get("log_file"):
                    candidate = Path(job["log_file"])
                    if candidate.exists():
                        output_file = candidate

        # Option 3: Try constructing from session_id (original behavior)
        if output_file is None:
            _, constructed = get_dispatch_output_path(project_path, request.session_id)
            if constructed.exists():
                output_file = constructed

        if output_file is not None and output_file.exists():
            output = output_file.read_text(encoding="utf-8", errors="ignore")

            # Fallback heuristic: only check last 5 lines for actual error patterns
            # (avoids false positives from code about error handling, test output, etc.)
            if not job_result_checked:
                lines_all = [l.strip() for l in output.splitlines() if l.strip()]
                tail = "\n".join(lines_all[-5:]).lower() if lines_all else ""
                error_patterns = ["error:", "fatal:", "traceback (most recent", "abort:"]
                has_errors = any(pat in tail for pat in error_patterns)

            # Try to extract Claude's final message (last non-empty line)
            lines = [l.strip() for l in output.splitlines() if l.strip()]
            if lines:
                summary_message = lines[-1][:200]  # Last line, truncated

        return DispatchSummaryResponse(
            success=len(files_changed) > 0,
            files_changed=files_changed,
            total_added=total_added,
            total_removed=total_removed,
            summary_message=summary_message,
            has_errors=has_errors
        )
    except Exception as e:
        logger.error(f"Failed to generate dispatch summary: {e}")
        return DispatchSummaryResponse(
            success=False,
            files_changed=[],
            total_added=0,
            total_removed=0,
            summary_message=None,
            has_errors=True
        )


def _create_dispatch_job(prompt: str, project_path: Path) -> dict:
    job_id = f"disp-{uuid.uuid4().hex[:12]}"

    # Generate output file path upfront so we can monitor it during execution
    log_file: str | None = None
    if CORE_AVAILABLE:
        try:
            _session_id, output_path = get_dispatch_output_path(project_path)
            log_file = str(output_path)
        except Exception as exc:
            logger.warning("Failed to generate dispatch output path: %s", exc)

    job = {
        "job_id": job_id,
        "status": "queued",
        "phase": "queued",
        "message": "Dispatch queued. Preparing Claude Code run...",
        "created_at": datetime.utcnow().isoformat(),
        "started_at": None,
        "finished_at": None,
        "done": False,
        "project_path": str(project_path),
        "prompt_preview": _prompt_preview(prompt),
        "result": None,
        "error_detail": None,
        "output_tail": None,
        "log_file": log_file,  # Store early so status endpoint can read during execution
    }
    with _dispatch_jobs_lock:
        _dispatch_jobs[job_id] = job
        _trim_dispatch_jobs_locked()
    return dict(job)


def _get_dispatch_job(job_id: str) -> dict | None:
    with _dispatch_jobs_lock:
        job = _dispatch_jobs.get(job_id)
        return dict(job) if job else None


def _update_dispatch_job(job_id: str, **updates) -> dict | None:
    with _dispatch_jobs_lock:
        job = _dispatch_jobs.get(job_id)
        if not job:
            return None
        job.update(updates)
        return dict(job)


def _trim_dispatch_jobs_locked() -> None:
    if len(_dispatch_jobs) <= _MAX_DISPATCH_JOBS:
        return
    completed = sorted(
        (
            (job_id, data)
            for job_id, data in _dispatch_jobs.items()
            if data.get("done")
        ),
        key=lambda item: item[1].get("finished_at") or item[1].get("created_at") or "",
    )
    while len(_dispatch_jobs) > _MAX_DISPATCH_JOBS and completed:
        job_id, _ = completed.pop(0)
        _dispatch_jobs.pop(job_id, None)


def _create_fallback_job(prompt: str, project_path: Path, provider: str, cli_path: str) -> dict:
    """Create and persist a fallback job record."""
    job_id = f"fb-{uuid.uuid4().hex[:12]}"
    session_id = f"dispatch-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    runtime_dir = project_runtime_dir(project_id_for_path(project_path))
    dispatch_output_dir = runtime_dir / "dispatch-output"
    dispatch_output_dir.mkdir(parents=True, exist_ok=True)
    log_file = dispatch_output_dir / f"{session_id}-{provider}.log"

    job = {
        "job_id": job_id,
        "status": "queued",
        "phase": "queued",
        "message": f"Fallback queued for {provider}.",
        "created_at": datetime.utcnow().isoformat(),
        "started_at": None,
        "finished_at": None,
        "done": False,
        "provider": provider,
        "cli_path": cli_path,
        "project_path": str(project_path),
        "prompt_preview": _prompt_preview(prompt),
        "result": None,
        "error_detail": None,
        "output_tail": None,
        "log_file": str(log_file),
        "session_id": session_id,
        "cancel_event": threading.Event(),
        "verification": None,
    }
    with _fallback_jobs_lock:
        _fallback_jobs[job_id] = job
        _trim_fallback_jobs_locked()
    return dict(job)


def _get_fallback_job(job_id: str) -> dict | None:
    with _fallback_jobs_lock:
        job = _fallback_jobs.get(job_id)
        return dict(job) if job else None


def _update_fallback_job(job_id: str, **updates) -> dict | None:
    with _fallback_jobs_lock:
        job = _fallback_jobs.get(job_id)
        if not job:
            return None
        job.update(updates)
        return dict(job)


def _trim_fallback_jobs_locked() -> None:
    if len(_fallback_jobs) <= _MAX_FALLBACK_JOBS:
        return
    completed = sorted(
        (
            (job_id, data)
            for job_id, data in _fallback_jobs.items()
            if data.get("done")
        ),
        key=lambda item: item[1].get("finished_at") or item[1].get("created_at") or "",
    )
    while len(_fallback_jobs) > _MAX_FALLBACK_JOBS and completed:
        job_id, _ = completed.pop(0)
        _fallback_jobs.pop(job_id, None)


def _run_fallback_job(
    job_id: str,
    prompt: str,
    provider: Literal["codex", "gemini"],
    project_path: Path,
    cli_path: str,
) -> None:
    """Run a fallback job in a background thread with live-log support."""
    job = _get_fallback_job(job_id)
    cancel_event = job.get("cancel_event") if job else None
    log_file = Path(job["log_file"]) if job and job.get("log_file") else None

    _update_fallback_job(
        job_id,
        status="running",
        phase="launching",
        message=f"Launching {provider} CLI...",
        started_at=datetime.utcnow().isoformat(),
    )

    try:
        _update_fallback_job(
            job_id,
            phase="running",
            message=f"{provider.capitalize()} is processing your task...",
        )
        if provider == "codex":
            result = dispatch_codex_task(
                prompt,
                project_path,
                cli_path=cli_path,
                output_file=log_file,
                cancel_event=cancel_event if isinstance(cancel_event, threading.Event) else None,
            )
        else:
            result = dispatch_gemini_task(
                prompt,
                project_path,
                cli_path=cli_path,
                output_file=log_file,
                cancel_event=cancel_event if isinstance(cancel_event, threading.Event) else None,
            )

        # Log dispatch event for the Logs tab (both success and failure)
        _log_dispatch_event(result, prompt, project_path)

        verification: dict[str, str] | None = None
        verification_error: str | None = None
        success = bool(result.success)
        error_code: str | None = None

        if success:
            _update_fallback_job(
                job_id,
                phase="verifying",
                message="Verifying lint/typecheck/documentation gates...",
            )
            verified, verification, verification_error = _verify_fallback_gates(project_path, prompt)
            if not verified:
                success = False
                error_code = "verification_failed"

        if success:
            _record_usage_event(
                project_path=project_path,
                prompt=prompt,
                provider=result.provider,
                output=result.output,
                session_id=result.session_id,
                source="fallback_dispatch",
            )

        if not success and error_code is None:
            error_code = _classify_fallback_failure(
                provider=provider,
                error=(verification_error or result.error_message),
                output=result.output,
            )

        response = _dispatch_response_from_result(
            result,
            success_override=success,
            error_override=verification_error,
            error_code=error_code,
            verification=verification,
        )
        message = "Fallback completed successfully." if success else (
            response.error or f"{provider.capitalize()} fallback failed."
        )

        _update_fallback_job(
            job_id,
            status="succeeded" if success else "failed",
            phase="complete" if success else "failed",
            message=message,
            finished_at=datetime.utcnow().isoformat(),
            done=True,
            result=response.model_dump(),
            error_detail=_build_fallback_error_detail(response, result.output, result.output_file),
            output_tail=_tail_text(result.output, max_lines=30, max_chars=3000),
            log_file=str(result.output_file) if result.output_file else (str(log_file) if log_file else None),
            verification=verification,
        )
    except Exception as exc:
        logger.exception("Fallback job %s failed unexpectedly", job_id)
        _update_fallback_job(
            job_id,
            status="failed",
            phase="failed",
            message="Fallback dispatch failed before completion.",
            finished_at=datetime.utcnow().isoformat(),
            done=True,
            result=DispatchResponse(
                success=False,
                provider=provider,
                error=str(exc),
                error_code="execution_failed",
            ).model_dump(),
            error_detail=str(exc),
            output_tail=None,
            log_file=str(log_file) if log_file else None,
        )


def _run_dispatch_job(job_id: str, prompt: str, project_path: Path) -> None:
    # Get the pre-generated log file path
    job = _get_dispatch_job(job_id)
    log_file_path = Path(job["log_file"]) if job and job.get("log_file") else None

    _update_dispatch_job(
        job_id,
        status="running",
        phase="launching",
        message="Launching Claude Code CLI...",
        started_at=datetime.utcnow().isoformat(),
    )

    try:
        _update_dispatch_job(
            job_id,
            phase="running",
            message="Claude Code is processing your task.",
        )
        # Pass the pre-generated output file so we can monitor it during execution
        result = dispatch_claude_task(prompt, project_path, output_file=log_file_path)

        # Log dispatch event for the Logs tab (both success and failure)
        _log_dispatch_event(result, prompt, project_path)

        if result.success or result.token_limit_reached:
            _record_usage_event(
                project_path=project_path,
                prompt=prompt,
                provider=result.provider,
                output=result.output,
                session_id=result.session_id,
                source="dispatch",
                token_limit_reached=result.token_limit_reached,
            )

        response = _dispatch_response_from_result(result)
        succeeded = bool(result.success)
        message = "Claude Code completed successfully." if succeeded else (
            "Claude Code token limit reached. Choose Codex or Gemini." if result.token_limit_reached else (
                result.error_message or "Claude Code did not complete successfully."
            )
        )

        _update_dispatch_job(
            job_id,
            status="succeeded" if succeeded else "failed",
            phase="complete" if succeeded else "failed",
            message=message,
            finished_at=datetime.utcnow().isoformat(),
            done=True,
            result=response.model_dump(),
            error_detail=_build_dispatch_error_detail(result),
            output_tail=_tail_text(result.output, max_lines=24, max_chars=2400),
            log_file=str(result.output_file) if result.output_file else None,
        )
    except Exception as exc:
        logger.exception("Dispatch job %s failed unexpectedly", job_id)
        _update_dispatch_job(
            job_id,
            status="failed",
            phase="failed",
            message="Dispatch failed before Claude Code completed.",
            finished_at=datetime.utcnow().isoformat(),
            done=True,
            result=DispatchResponse(success=False, error=str(exc)).model_dump(),
            error_detail=str(exc),
            output_tail=None,
            log_file=None,
        )


def _dispatch_response_from_result(
    result,
    *,
    success_override: bool | None = None,
    error_override: str | None = None,
    error_code: str | None = None,
    verification: dict[str, str] | None = None,
) -> DispatchResponse:
    success = bool(result.success if success_override is None else success_override)
    error = error_override if error_override is not None else result.error_message
    return DispatchResponse(
        success=success,
        sessionId=result.session_id,
        error=error,
        error_code=error_code,
        output=result.output,
        verification=verification,
        provider=result.provider,
        token_limit_reached=result.token_limit_reached,
    )


def _log_dispatch_event(
    result,
    prompt: str,
    project_path: Path,
) -> None:
    """Persist a dispatch event to the shared dispatch log for the Logs tab."""
    try:
        dispatch_logger = DispatchLogger()
        pid = project_id_for_path(project_path)
        dispatch_logger.log_dispatch(
            result=result,
            prompt=prompt,
            project_name=project_path.name,
            project_id=pid,
            project_path=project_path,
        )
    except Exception as exc:
        logger.warning("Failed to log dispatch event: %s", exc)


def _record_usage_event(
    project_path: Path,
    prompt: str,
    provider: str,
    output: str | None,
    session_id: str | None,
    source: str,
    token_limit_reached: bool = False,
) -> None:
    """Persist provider usage telemetry for dispatch/fallback executions."""
    try:
        project_runtime_id = project_id_for_path(project_path)
        usage_store = ProviderUsageStore(project_runtime_id)
        snapshot = usage_snapshot(provider=provider, prompt=prompt, output=output)
        usage_store.record(
            snapshot=snapshot,
            source=source,
            session_id=session_id,
            metadata={
                "token_limit_reached": token_limit_reached,
                "prompt": prompt,
            },
        )

        # Keep Claude API cost history compatible with existing budget logic.
        if provider == "claude":
            model = snapshot.model or "claude-3-5-sonnet-latest"
            cost_tracker = CostTracker(project_runtime_id)
            cost_tracker.record_usage(
                TokenUsage(
                    input_tokens=snapshot.input_tokens,
                    output_tokens=snapshot.output_tokens,
                    model=model,
                ),
                source="dispatch",
                session_id=session_id,
            )
    except Exception as exc:
        logger.warning("Failed to persist provider usage telemetry: %s", exc)


def _clamp_percent(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(100.0, float(value)))


def _clamp_threshold(value: float) -> float:
    return max(1.0, min(100.0, float(value)))


def _tail_text(value: str | None, max_lines: int = 20, max_chars: int = 2000) -> str | None:
    if not value:
        return None
    sanitized = _strip_ansi(value)
    lines = [line.rstrip() for line in sanitized.splitlines() if line.strip()]
    if not lines:
        return None
    text = "\n".join(lines[-max_lines:])
    if len(text) > max_chars:
        text = text[-max_chars:]
    return text


def _prompt_preview(prompt: str, max_chars: int = 180) -> str:
    compact = " ".join(prompt.split())
    if len(compact) <= max_chars:
        return compact
    return f"{compact[: max_chars - 3]}..."


def _build_dispatch_error_detail(result) -> str | None:
    details: list[str] = []
    if result.error_message:
        details.append(result.error_message.strip())
    tail = _tail_text(result.output, max_lines=20, max_chars=1800)
    if tail:
        details.append(f"CLI output tail:\n{tail}")
    if result.output_file:
        details.append(f"Dispatch log: {result.output_file}")
    joined = "\n\n".join(part for part in details if part)
    return joined or None


def _build_fallback_error_detail(
    response: DispatchResponse,
    output: str | None,
    output_file: Path | None,
) -> str | None:
    """Build detailed fallback failure context for status polling and logs."""
    details: list[str] = []
    if response.error_code:
        details.append(f"Error code: {response.error_code}")
    if response.error:
        details.append(response.error.strip())
    if response.verification:
        parts = [f"{name}={status}" for name, status in response.verification.items()]
        details.append(f"Verification: {', '.join(parts)}")
    tail = _tail_text(output, max_lines=24, max_chars=2200)
    if tail:
        details.append(f"CLI output tail:\n{tail}")
    if output_file:
        details.append(f"Dispatch log: {output_file}")
    message = "\n\n".join(part for part in details if part)
    return message or None


def _normalize_gate_name(value: str) -> str:
    """Normalize user-facing gate names to canonical gate IDs."""
    normalized = value.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    mapping = {
        "lint": "lint",
        "typecheck": "typecheck",
        "typing": "typecheck",
        "mypy": "typecheck",
        "documentation": "documentation",
        "docs": "documentation",
        "doc": "documentation",
    }
    return mapping.get(normalized, normalized)


def _extract_requested_gate_names(prompt: str) -> list[str]:
    """Extract failing gate names from a fallback prompt."""
    if not prompt:
        return []
    match = re.search(r"failed gate\(s\)\s*:\s*([^\n\r]+)", prompt, flags=re.IGNORECASE)
    if not match:
        return []
    raw = match.group(1)
    candidates = [token.strip() for token in raw.split(",") if token.strip()]
    normalized: list[str] = []
    for token in candidates:
        gate = _normalize_gate_name(token)
        if gate and gate not in normalized:
            normalized.append(gate)
    return normalized


def _verify_fallback_gates(project_path: Path, prompt: str) -> tuple[bool, dict[str, str], str | None]:
    """Run post-fallback verification for relevant gate(s)."""
    if not CORE_AVAILABLE:
        return True, {}, None

    requested = _extract_requested_gate_names(prompt)
    targets = requested or ["lint", "typecheck", "documentation"]
    statuses: dict[str, str] = {}

    try:
        runner = QualityGateRunner(project_path)
        runner.load_config()
    except Exception as exc:
        return False, dict.fromkeys(targets, "error"), f"Failed to initialize gate runner: {exc}"

    for gate_name in targets:
        if gate_name not in runner.gates:
            statuses[gate_name] = "missing"
            continue
        try:
            report = runner.run_gate(gate_name, session_id=None)
            status = report.results[0].status if report.results else "error"
            statuses[gate_name] = status
        except Exception as exc:
            statuses[gate_name] = "error"
            logger.warning("Fallback verification failed for gate %s: %s", gate_name, exc)

    failed = {name: status for name, status in statuses.items() if status not in {"pass", "skipped"}}
    if failed:
        summary = ", ".join(f"{name}={status}" for name, status in failed.items())
        return False, statuses, f"Post-run gate verification failed: {summary}."

    return True, statuses, None


def _classify_fallback_failure(provider: str, error: str | None, output: str | None) -> str:
    """Classify fallback failure for actionable UI messages."""
    text = f"{error or ''}\n{output or ''}".lower()

    if "not found at" in text:
        return "cli_not_found"
    if "cancelled by user" in text or "cancelled" in text:
        return "cancelled"
    if "timed out after" in text:
        return "timeout"
    if "stalled with no output" in text:
        return "stalled"
    if (
        "error sending request for url" in text
        or "stream disconnected" in text
        or "network request failed" in text
    ):
        return "network_disconnect"
    if (
        "stdin is not a terminal" in text
        or "confirm whether you want me to proceed" in text
        or "do you want me to proceed" in text
        or "please confirm" in text
        or "waiting for input" in text
    ):
        return "needs_user_input"
    if (
        "login" in text
        or "auth" in text
        or "unauthorized" in text
        or "invalid api key" in text
        or "api key" in text
    ):
        return "auth_required"
    if "verification failed" in text:
        return "verification_failed"
    return f"{provider}_execution_failed"
