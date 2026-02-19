"""
Quality Gates API routes
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
from collections import defaultdict
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Import core modules
try:
    from src.agents.gates import QualityGateRunner, GateReport, GateResult
    from src.core.project import ProjectRegistry
    from src.core.gate_results import GateResultStore
    from src.core.runtime import project_id_for_path
    CORE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Core modules not available: {e}")
    CORE_AVAILABLE = False

from ..ttl_cache import get as cache_get, put as cache_put


class FindingResponse(BaseModel):
    severity: str
    description: str
    file: Optional[str] = None
    line: Optional[int] = None


class GateResponse(BaseModel):
    name: str
    status: str  # "pass" | "warn" | "fail" | "skipped" | "error" | "pending"
    message: str
    detail: Optional[str] = None
    findings: list[FindingResponse]
    durationSeconds: float
    hardStop: bool
    costEstimate: float


class GateReportResponse(BaseModel):
    gates: list[GateResponse]
    runId: str
    timestamp: str
    trigger: str
    overallStatus: str  # "pass" | "warn" | "fail" | "pending"
    changedFiles: list[str]


class GateHistoryPointResponse(BaseModel):
    timestamp: str
    status: str
    score: float


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


def _compute_overall_status(gates: list) -> str:
    """Compute overall status from gate results."""
    has_fail = any(g.status == "fail" for g in gates)
    has_warn = any(g.status == "warn" for g in gates)
    if has_fail:
        return "fail"
    if has_warn:
        return "warn"
    return "pass"


def _status_to_score(status: str) -> float:
    """Convert gate status to a numeric score for sparkline trends."""
    return {"pass": 1.0, "warn": 0.5, "fail": 0.0}.get(status, 0.0)


# ── History endpoint MUST be registered before the catch-all GET ──


@router.get("/{project_id:path}/history")
def get_gate_history(
    project_id: str,
) -> dict[str, list[GateHistoryPointResponse]]:
    """Get gate result history for sparkline trends.

    Returns a dict mapping gate name -> list of historical data points.
    """
    if not CORE_AVAILABLE:
        return {}

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    cache_key = f"gates:history:{project_path}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        pid = project_id_for_path(project_path)
        store = GateResultStore(pid)
        reports = store.load_history(limit=20)
    except Exception as e:
        logger.error(f"Failed to load gate history: {e}")
        return {}

    # Group by gate name, chronological order (oldest first)
    history: dict[str, list[GateHistoryPointResponse]] = defaultdict(list)
    for report in reversed(reports):
        for gate in report.gates:
            history[gate.name].append(
                GateHistoryPointResponse(
                    timestamp=report.timestamp.isoformat(),
                    status=gate.status,
                    score=_status_to_score(gate.status),
                )
            )

    result = dict(history)
    cache_put(cache_key, result, ttl=30)
    return result


# ── Catch-all GET for current results ──


@router.get("/{project_id:path}")
def get_gate_results(project_id: str) -> GateReportResponse:
    """Get quality gate results"""
    if not CORE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Core modules not loaded - cannot retrieve gate results",
        )

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    cache_key = f"gates:results:{project_path}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        runner = QualityGateRunner(project_path)
        report = runner.latest_report()
    except Exception as e:
        logger.error(f"Failed to get gate results: {e}")
        return GateReportResponse(
            gates=[],
            runId="",
            timestamp="",
            trigger="none",
            overallStatus="warn",
            changedFiles=[],
        )

    # Always load the full gate config so we can show every configured gate,
    # even if the last run only produced partial results (e.g. old hard_stop
    # short-circuit) or has never been run at all.
    try:
        runner.load_config()
    except Exception:
        pass  # Best-effort — fall through with whatever config we have.

    if not report:
        # No previous run — return all gate definitions as "pending".
        pending_gates = [
            GateResponse(
                name=cfg.name,
                status="pending",
                message="Not yet run" if cfg.enabled else "Disabled",
                detail=cfg.agent_prompt if cfg.gate_type == "hook" else None,
                findings=[],
                durationSeconds=0.0,
                hardStop=cfg.hard_stop,
                costEstimate=0.0,
            )
            for cfg in runner.gates.values()
        ]
        result = GateReportResponse(
            gates=pending_gates,
            runId="",
            timestamp="",
            trigger="none",
            overallStatus="pending",
            changedFiles=[],
        )
        cache_put(cache_key, result, ttl=10)
        return result

    # Build response gates from report results.
    reported_names: set[str] = set()
    response_gates: list[GateResponse] = []
    for gate in report.results:
        reported_names.add(gate.name)
        response_gates.append(GateResponse(
            name=gate.name,
            status=gate.status,
            message=gate.message,
            detail=gate.details,
            findings=[
                FindingResponse(
                    severity=f.severity,
                    description=f.description,
                    file=f.file,
                    line=f.line,
                )
                for f in gate.findings
            ],
            durationSeconds=gate.duration_seconds,
            hardStop=gate.hard_stop,
            costEstimate=gate.cost_estimate,
        ))

    # Supplement with "pending" entries for any configured gates missing
    # from the report (stale report from before all gates ran).
    for cfg in runner.gates.values():
        if cfg.name in reported_names:
            continue
        response_gates.append(GateResponse(
            name=cfg.name,
            status="pending",
            message="Not yet run" if cfg.enabled else "Disabled",
            detail=cfg.agent_prompt if cfg.gate_type == "hook" else None,
            findings=[],
            durationSeconds=0.0,
            hardStop=cfg.hard_stop,
            costEstimate=0.0,
        ))

    result = GateReportResponse(
        gates=response_gates,
        runId=report.run_id,
        timestamp=report.timestamp.isoformat(),
        trigger=report.trigger,
        overallStatus="fail" if report.has_failures else ("pass" if report.all_passed else "warn"),
        changedFiles=report.changed_files,
    )
    cache_put(cache_key, result, ttl=10)
    return result


@router.post("/{project_id:path}/run")
async def run_gates(project_id: str) -> GateReportResponse:
    """Run quality gates"""
    if not CORE_AVAILABLE:
        # Cannot run gates without core modules
        raise HTTPException(
            status_code=503,
            detail="Core modules not loaded - cannot run quality gates"
        )

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        runner = QualityGateRunner(project_path)
        runner.load_config()
        report = runner.run_all_gates(staged_only=False, trigger="api")
    except Exception as e:
        logger.error(f"Failed to run gates: {e}")
        raise HTTPException(status_code=500, detail=f"Gate run failed: {e}")

    return GateReportResponse(
        gates=[
            GateResponse(
                name=gate.name,
                status=gate.status,
                message=gate.message,
                detail=gate.details,
                findings=[
                    FindingResponse(
                        severity=f.severity,
                        description=f.description,
                        file=f.file,
                        line=f.line,
                    )
                    for f in gate.findings
                ],
                durationSeconds=gate.duration_seconds,
                hardStop=gate.hard_stop,
                costEstimate=gate.cost_estimate,
            )
            for gate in report.results
        ],
        runId=report.run_id,
        timestamp=report.timestamp.isoformat(),
        trigger=report.trigger,
        overallStatus="fail" if report.has_failures else ("pass" if report.all_passed else "warn"),
        changedFiles=report.changed_files,
    )
