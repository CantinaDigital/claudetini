"""
Quality Gates API routes
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
    from src.agents.gates import QualityGateRunner, GateReport, GateResult
    from src.core.project import ProjectRegistry
    from src.core.gate_results import GateResultStore
    from src.core.runtime import project_id_for_path
    CORE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Core modules not available: {e}")
    CORE_AVAILABLE = False


class FindingResponse(BaseModel):
    severity: str
    description: str
    file: Optional[str] = None
    line: Optional[int] = None


class GateResponse(BaseModel):
    name: str
    status: str  # "pass" | "warn" | "fail" | "skipped" | "error"
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
    overallStatus: str  # "pass" | "warn" | "fail"
    changedFiles: list[str]


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

    if not report:
        return GateReportResponse(
            gates=[],
            runId="",
            timestamp="",
            trigger="none",
            overallStatus="warn",
            changedFiles=[],
        )

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
