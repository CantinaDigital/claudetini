"""Readiness scanning API endpoints."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.readiness import ReadinessCheck, ReadinessReport, scan_project_readiness

router = APIRouter(prefix="/readiness", tags=["readiness"])


class ReadinessCheckResponse(BaseModel):
    """API response for a single readiness check."""

    name: str
    category: str
    passed: bool
    severity: str
    weight: float
    message: str
    remediation: str | None = None
    why: str | None = None
    can_auto_generate: bool = False
    details: dict = {}


class ReadinessReportResponse(BaseModel):
    """API response for readiness report."""

    score: float
    is_ready: bool
    total_checks: int
    passed_checks: int
    failed_checks: int
    checks: list[ReadinessCheckResponse]
    critical_issues: list[str]
    warnings: list[str]
    project_path: str


class ScanRequest(BaseModel):
    """Request to scan project readiness."""

    project_path: str


def _check_to_response(check: ReadinessCheck) -> ReadinessCheckResponse:
    """Convert ReadinessCheck to API response."""
    return ReadinessCheckResponse(
        name=check.name,
        category=check.category,
        passed=check.passed,
        severity=check.severity.value,
        weight=check.weight,
        message=check.message,
        remediation=check.remediation,
        why=check.why_need_it if check.why_need_it else None,
        can_auto_generate=check.can_auto_generate,
        details=check.details,
    )


def _report_to_response(report: ReadinessReport) -> ReadinessReportResponse:
    """Convert ReadinessReport to API response."""
    return ReadinessReportResponse(
        score=report.score,
        is_ready=report.is_ready,
        total_checks=report.total_checks,
        passed_checks=report.passed_checks,
        failed_checks=report.failed_checks,
        checks=[_check_to_response(check) for check in report.checks],
        critical_issues=report.critical_issues,
        warnings=report.warnings,
        project_path=str(report.project_path),
    )


@router.post("/scan", response_model=ReadinessReportResponse)
async def scan_readiness(request: ScanRequest) -> ReadinessReportResponse:
    """Scan a project for Claude Code readiness.

    Returns a score (0-100) and detailed check results.
    """
    project_path = Path(request.project_path).resolve()

    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"Project path does not exist: {project_path}")

    if not project_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {project_path}")

    try:
        report = scan_project_readiness(project_path)
        return _report_to_response(report)

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Readiness scan failed: {exc}")


@router.get("/score/{project_path:path}", response_model=dict)
async def get_score_only(project_path: str) -> dict:
    """Get just the readiness score for a project (lightweight check).

    Returns:
        {"score": 75.0, "is_ready": true}
    """
    path = Path(project_path).resolve()

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Project path does not exist: {path}")

    try:
        report = scan_project_readiness(path)
        return {"score": report.score, "is_ready": report.is_ready}

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Score check failed: {exc}")
