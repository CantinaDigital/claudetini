"""
Parallel execution API routes — AI-orchestrated planning, phased execution,
and verification.
"""

import json
import logging
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger(__name__)

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_ANSI_OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")

try:
    from src.agents.planning_agent import PlanningAgent, ExecutionPlan as _EPlan
    from src.agents.parallel_orchestrator import ParallelOrchestrator

    CORE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Parallel modules not available: {e}")
    CORE_AVAILABLE = False


def _strip_ansi(value: str) -> str:
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


def _read_log_tail(log_file: str | None, max_lines: int = 15, max_chars: int = 1500) -> str | None:
    """Read tail of a log file for agent output preview."""
    if not log_file:
        return None
    try:
        path = Path(log_file).resolve()
        allowed_prefixes = (
            Path.home() / ".claude",
            Path.home() / ".claudetini",
            Path("/tmp"),
        )
        if not any(str(path).startswith(str(p.resolve())) for p in allowed_prefixes):
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
        return text[-max_chars:] if len(text) > max_chars else text
    except Exception:
        return None


# ── Request / Response Models ──


class TaskItem(BaseModel):
    text: str = Field(..., min_length=1)
    prompt: str | None = None


# Plan models

class AgentAssignmentResponse(BaseModel):
    agent_id: int
    theme: str
    task_indices: list[int]
    rationale: str
    agent_prompt: str = ""

class ExecutionPhaseResponse(BaseModel):
    phase_id: int
    name: str
    description: str
    parallel: bool
    agents: list[AgentAssignmentResponse]

class ExecutionPlanResponse(BaseModel):
    summary: str
    phases: list[ExecutionPhaseResponse]
    success_criteria: list[str]
    estimated_total_agents: int
    warnings: list[str]

class PlanRequest(BaseModel):
    project_path: str = Field(..., min_length=1, max_length=2048)
    tasks: list[TaskItem] = Field(..., min_length=1)
    milestone_title: str = ""
    model: str | None = None

class PlanStartResponse(BaseModel):
    plan_job_id: str
    output_file: str

class PlanStatusResponse(BaseModel):
    status: str  # "running", "complete", "failed"
    output_tail: str | None = None
    plan: ExecutionPlanResponse | None = None
    error: str | None = None

class ReplanRequest(BaseModel):
    project_path: str = Field(..., min_length=1, max_length=2048)
    tasks: list[TaskItem] = Field(..., min_length=1)
    milestone_title: str = ""
    model: str | None = None
    previous_plan: ExecutionPlanResponse
    feedback: str = Field(..., min_length=1)

# Execution models

class ExecuteRequest(BaseModel):
    project_path: str = Field(..., min_length=1, max_length=2048)
    tasks: list[TaskItem] = Field(..., min_length=1)
    plan: ExecutionPlanResponse
    plan_job_id: str | None = None
    max_parallel: int = Field(3, ge=1, le=8)

class ExecuteStartResponse(BaseModel):
    batch_id: str
    status: str
    message: str

class AgentSlotResponse(BaseModel):
    task_index: int
    task_text: str
    status: str
    output_tail: str | None = None
    error: str | None = None
    cost_estimate: float = 0.0
    group_id: int = 0
    phase_id: int = 0

class MergeResultResponse(BaseModel):
    branch: str
    success: bool
    conflict_files: list[str]
    resolution_method: str
    message: str

class CriterionResultResponse(BaseModel):
    criterion: str
    passed: bool
    evidence: str
    notes: str

class VerificationResultResponse(BaseModel):
    overall_pass: bool
    criteria_results: list[CriterionResultResponse]
    summary: str

class BatchStatusResponse(BaseModel):
    batch_id: str
    phase: str
    current_phase_id: int = 0
    current_phase_name: str = ""
    agents: list[AgentSlotResponse]
    merge_results: list[MergeResultResponse]
    verification: VerificationResultResponse | None = None
    verification_output_tail: str | None = None
    finalize_message: str | None = None
    plan_summary: str = ""
    total_cost: float = 0.0
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None

class CancelResponse(BaseModel):
    success: bool
    message: str


# ── In-memory state ──

_plan_jobs: dict[str, dict] = {}
_plan_jobs_lock = threading.Lock()
_orchestrators: dict[str, ParallelOrchestrator] = {}
_orchestrators_lock = threading.Lock()

# ── Thread management ──

_active_threads: list[threading.Thread] = []
_active_threads_lock = threading.Lock()
_shutdown_event = threading.Event()


def _register_thread(thread: threading.Thread) -> None:
    """Register a managed thread for graceful shutdown tracking."""
    with _active_threads_lock:
        # Prune dead threads while we're here
        _active_threads[:] = [t for t in _active_threads if t.is_alive()]
        _active_threads.append(thread)


# ── Helper: convert API plan to internal plan ──

def _api_plan_to_internal(plan_resp: ExecutionPlanResponse, tasks: list[TaskItem]) -> "_EPlan":
    """Convert API ExecutionPlanResponse to internal ExecutionPlan."""
    from src.agents.planning_agent import (
        ExecutionPlan,
        ExecutionPhase,
        AgentAssignment,
    )

    phases = []
    for p in plan_resp.phases:
        agents = []
        for a in p.agents:
            agents.append(
                AgentAssignment(
                    agent_id=a.agent_id,
                    theme=a.theme,
                    task_indices=a.task_indices,
                    rationale=a.rationale,
                    agent_prompt=a.agent_prompt,
                )
            )
        phases.append(
            ExecutionPhase(
                phase_id=p.phase_id,
                name=p.name,
                description=p.description,
                parallel=p.parallel,
                agents=agents,
            )
        )

    return ExecutionPlan(
        summary=plan_resp.summary,
        phases=phases,
        success_criteria=plan_resp.success_criteria,
        estimated_total_agents=plan_resp.estimated_total_agents,
        warnings=plan_resp.warnings,
    )


def _internal_plan_to_api(plan) -> ExecutionPlanResponse:
    """Convert internal ExecutionPlan to API response."""
    return ExecutionPlanResponse(
        summary=plan.summary,
        phases=[
            ExecutionPhaseResponse(
                phase_id=p.phase_id,
                name=p.name,
                description=p.description,
                parallel=p.parallel,
                agents=[
                    AgentAssignmentResponse(
                        agent_id=a.agent_id,
                        theme=a.theme,
                        task_indices=a.task_indices,
                        rationale=a.rationale,
                        agent_prompt=a.agent_prompt,
                    )
                    for a in p.agents
                ],
            )
            for p in plan.phases
        ],
        success_criteria=plan.success_criteria,
        estimated_total_agents=plan.estimated_total_agents,
        warnings=plan.warnings,
    )


# ── Endpoints ──


class GitCheckRequest(BaseModel):
    project_path: str = Field(..., min_length=1, max_length=2048)


class GitCheckResponse(BaseModel):
    clean: bool
    dirty_files: list[str] = []


@router.post("/git-check")
async def git_check(req: GitCheckRequest) -> GitCheckResponse:
    """Check if working tree is clean for parallel execution.

    Only checks tracked file changes (ignores untracked files).
    """
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Parallel modules not loaded")

    project_path = Path(req.project_path).expanduser().resolve()
    if not project_path.exists() or not project_path.is_dir():
        raise HTTPException(status_code=404, detail="Project path not found")

    from src.core.worktree_manager import WorktreeManager

    try:
        wm = WorktreeManager(project_path)
        clean = wm.is_working_tree_clean()
        dirty_files = [] if clean else wm.get_dirty_files()
        return GitCheckResponse(clean=clean, dirty_files=dirty_files)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cleanup-orphans")
async def cleanup_orphans(req: GitCheckRequest) -> dict:
    """Clean up orphaned worktrees from crashed executions."""
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Parallel modules not loaded")

    project_path = Path(req.project_path).expanduser().resolve()
    if not project_path.exists() or not project_path.is_dir():
        raise HTTPException(status_code=404, detail="Project path not found")

    from src.core.worktree_manager import WorktreeManager

    try:
        wm = WorktreeManager(project_path)
        count = wm.cleanup_orphans()
        return {"cleaned": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/plan")
async def start_plan(req: PlanRequest) -> PlanStartResponse:
    """Start planning agent dispatch. Returns immediately with a plan_job_id + output_file."""
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Parallel modules not loaded")

    project_path = Path(req.project_path).expanduser().resolve()
    if not project_path.exists() or not project_path.is_dir():
        raise HTTPException(status_code=404, detail="Project path not found")

    from src.agents.dispatcher import get_dispatch_output_path

    _session_id, output_file = get_dispatch_output_path(project_path)
    plan_job_id = f"plan-{uuid.uuid4().hex[:12]}"

    with _plan_jobs_lock:
        _plan_jobs[plan_job_id] = {
            "status": "running",
            "output_file": str(output_file),
            "plan": None,
            "internal_plan": None,
            "error": None,
        }

    tasks = [{"text": t.text, "prompt": t.prompt or t.text} for t in req.tasks]

    def _run_plan():
        try:
            agent = PlanningAgent(project_path)
            plan = agent.create_plan(
                tasks=tasks,
                milestone_title=req.milestone_title,
                model=req.model,
                output_file=output_file,
            )
            with _plan_jobs_lock:
                job = _plan_jobs.get(plan_job_id)
                if job:
                    if plan.phases:
                        job["status"] = "complete"
                        job["plan"] = _internal_plan_to_api(plan)
                        job["internal_plan"] = plan
                    else:
                        job["status"] = "failed"
                        job["error"] = plan.summary or "Planning produced no phases"
        except Exception as exc:
            logger.exception("Planning agent failed for job %s", plan_job_id)
            with _plan_jobs_lock:
                job = _plan_jobs.get(plan_job_id)
                if job:
                    job["status"] = "failed"
                    job["error"] = str(exc)

    thread = threading.Thread(target=_run_plan, daemon=True, name=f"plan-{plan_job_id}")
    _register_thread(thread)
    thread.start()

    return PlanStartResponse(plan_job_id=plan_job_id, output_file=str(output_file))


@router.get("/plan/status/{plan_job_id}")
async def get_plan_status(plan_job_id: str) -> PlanStatusResponse:
    """Poll planning agent: live output + parsed plan when done."""
    with _plan_jobs_lock:
        job = _plan_jobs.get(plan_job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Plan job not found")
        job = dict(job)

    output_tail = _read_log_tail(job.get("output_file"))

    return PlanStatusResponse(
        status=job["status"],
        output_tail=output_tail,
        plan=job.get("plan"),
        error=job.get("error"),
    )


@router.post("/plan/replan")
async def replan(req: ReplanRequest) -> PlanStartResponse:
    """Re-plan with user feedback. Returns new plan_job_id + output_file."""
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Parallel modules not loaded")

    project_path = Path(req.project_path).expanduser().resolve()
    if not project_path.exists() or not project_path.is_dir():
        raise HTTPException(status_code=404, detail="Project path not found")

    from src.agents.dispatcher import get_dispatch_output_path

    _session_id, output_file = get_dispatch_output_path(project_path)
    plan_job_id = f"plan-{uuid.uuid4().hex[:12]}"

    with _plan_jobs_lock:
        _plan_jobs[plan_job_id] = {
            "status": "running",
            "output_file": str(output_file),
            "plan": None,
            "internal_plan": None,
            "error": None,
        }

    tasks = [{"text": t.text, "prompt": t.prompt or t.text} for t in req.tasks]

    # Convert the previous plan response back to internal format
    prev_internal = _api_plan_to_internal(req.previous_plan, req.tasks)

    def _run_replan():
        try:
            agent = PlanningAgent(project_path)
            plan = agent.create_plan(
                tasks=tasks,
                milestone_title=req.milestone_title,
                model=req.model,
                output_file=output_file,
                previous_plan=prev_internal,
                user_feedback=req.feedback,
            )
            with _plan_jobs_lock:
                job = _plan_jobs.get(plan_job_id)
                if job:
                    if plan.phases:
                        job["status"] = "complete"
                        job["plan"] = _internal_plan_to_api(plan)
                        job["internal_plan"] = plan
                    else:
                        job["status"] = "failed"
                        job["error"] = plan.summary or "Re-planning produced no phases"
        except Exception as exc:
            logger.exception("Re-planning agent failed for job %s", plan_job_id)
            with _plan_jobs_lock:
                job = _plan_jobs.get(plan_job_id)
                if job:
                    job["status"] = "failed"
                    job["error"] = str(exc)

    thread = threading.Thread(target=_run_replan, daemon=True, name=f"replan-{plan_job_id}")
    _register_thread(thread)
    thread.start()

    return PlanStartResponse(plan_job_id=plan_job_id, output_file=str(output_file))


@router.post("/execute")
async def start_execution(req: ExecuteRequest) -> ExecuteStartResponse:
    """Start phased execution with an approved plan. Returns immediately with batch_id."""
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Parallel modules not loaded")

    project_path = Path(req.project_path).expanduser().resolve()
    if not project_path.exists() or not project_path.is_dir():
        raise HTTPException(status_code=404, detail="Project path not found")

    orchestrator = ParallelOrchestrator(project_path)
    batch_id = orchestrator.generate_batch_id()

    # Find the internal plan from plan jobs (has agent_prompts)
    # Prefer stable lookup by plan_job_id, fall back to summary matching
    internal_plan = None
    if req.plan_job_id:
        with _plan_jobs_lock:
            job = _plan_jobs.get(req.plan_job_id)
            if job and job.get("internal_plan"):
                internal_plan = job["internal_plan"]

    if internal_plan is None:
        with _plan_jobs_lock:
            for job in _plan_jobs.values():
                ip = job.get("internal_plan")
                if ip and ip.summary == req.plan.summary:
                    internal_plan = ip
                    break

    if internal_plan is None:
        # Fallback: convert API plan (agent_prompt now preserved in API model)
        internal_plan = _api_plan_to_internal(req.plan, req.tasks)

    tasks = [{"text": t.text, "prompt": t.prompt or t.text} for t in req.tasks]

    with _orchestrators_lock:
        _orchestrators[batch_id] = orchestrator

    def _run_batch():
        import asyncio

        # Check for shutdown before starting
        if _shutdown_event.is_set():
            orchestrator.cancel_batch(batch_id)
            return

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                orchestrator.execute_plan(
                    batch_id=batch_id,
                    tasks=tasks,
                    plan=internal_plan,
                    max_parallel=req.max_parallel,
                )
            )
        except Exception as exc:
            logger.exception("Parallel batch %s failed: %s", batch_id, exc)
        finally:
            loop.close()

    worker = threading.Thread(
        target=_run_batch,
        daemon=True,
        name=f"parallel-{batch_id}",
    )
    _register_thread(worker)
    worker.start()

    total_agents = sum(
        len(p.agents) for p in internal_plan.phases
    )

    return ExecuteStartResponse(
        batch_id=batch_id,
        status="starting",
        message=f"Execution started: {total_agents} agent(s) across {len(internal_plan.phases)} phase(s).",
    )


@router.get("/execute/status/{batch_id}")
async def get_execution_status(batch_id: str) -> BatchStatusResponse:
    """Poll execution status: agents, merges, verification."""
    with _orchestrators_lock:
        orchestrator = _orchestrators.get(batch_id)
    if not orchestrator:
        raise HTTPException(status_code=404, detail="Batch not found")

    batch_status = orchestrator.get_status(batch_id)
    if not batch_status:
        raise HTTPException(status_code=404, detail="Batch status not found")

    agents: list[AgentSlotResponse] = []
    for agent in batch_status.agents:
        output_tail = None
        if agent.output_file:
            output_tail = _read_log_tail(str(agent.output_file), max_lines=80, max_chars=6000)

        agents.append(
            AgentSlotResponse(
                task_index=agent.task_index,
                task_text=agent.task_text,
                status=agent.status,
                output_tail=output_tail,
                error=agent.error,
                cost_estimate=agent.cost_estimate,
                group_id=agent.group_id,
                phase_id=agent.phase_id,
            )
        )

    merge_results = [
        MergeResultResponse(
            branch=mr.branch,
            success=mr.success,
            conflict_files=mr.conflict_files,
            resolution_method=mr.resolution_method,
            message=mr.message,
        )
        for mr in batch_status.merge_results
    ]

    verification = None
    if batch_status.verification:
        v = batch_status.verification
        verification = VerificationResultResponse(
            overall_pass=v.get("overall_pass", False),
            criteria_results=[
                CriterionResultResponse(**cr)
                for cr in v.get("criteria_results", [])
            ],
            summary=v.get("summary", ""),
        )

    verification_output_tail = None
    if batch_status.verification_output_file:
        verification_output_tail = _read_log_tail(
            str(batch_status.verification_output_file), max_lines=80, max_chars=6000
        )

    return BatchStatusResponse(
        batch_id=batch_status.batch_id,
        phase=batch_status.phase,
        current_phase_id=batch_status.current_phase_id,
        current_phase_name=batch_status.current_phase_name,
        agents=agents,
        merge_results=merge_results,
        verification=verification,
        verification_output_tail=verification_output_tail,
        finalize_message=batch_status.finalize_message,
        plan_summary=batch_status.plan_summary,
        total_cost=batch_status.total_cost,
        started_at=batch_status.started_at.isoformat() if batch_status.started_at else None,
        finished_at=batch_status.finished_at.isoformat() if batch_status.finished_at else None,
        error=batch_status.error,
    )


@router.post("/cancel/{id}")
async def cancel(id: str) -> CancelResponse:
    """Cancel a running planning or execution job."""
    # Try cancelling a plan job
    with _plan_jobs_lock:
        job = _plan_jobs.get(id)
        if job and job["status"] == "running":
            job["status"] = "failed"
            job["error"] = "Cancelled by user"
            return CancelResponse(success=True, message="Plan cancelled")

    # Try cancelling an execution batch
    with _orchestrators_lock:
        orchestrator = _orchestrators.get(id)
    if orchestrator:
        success = orchestrator.cancel_batch(id)
        if success:
            return CancelResponse(success=True, message="Execution cancellation requested")

    return CancelResponse(success=False, message="Job not found or already completed")


@router.post("/release-hmr-lock")
async def release_hmr_lock(req: GitCheckRequest) -> dict:
    """Remove the .parallel-running lock file so Vite resumes normal HMR."""
    project_path = Path(req.project_path).expanduser().resolve()
    lock = project_path / "app" / ".parallel-running"
    try:
        lock.unlink(missing_ok=True)
    except OSError:
        pass
    return {"released": True}
