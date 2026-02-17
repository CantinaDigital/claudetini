"""Project intelligence scanning API endpoints.

Orchestrates the five core scanners (hardcoded, integration, freshness,
dependency, feature) and exposes them via REST endpoints for the frontend.
"""

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.dependency_analyzer import DependencyAnalyzer, DependencyReport
from src.core.feature_inventory import FeatureInventory, FeatureInventoryScanner
from src.core.freshness_analyzer import FreshnessAnalyzer, FreshnessReport
from src.core.hardcoded_scanner import HardcodedScanner, HardcodedScanResult
from src.core.integration_scanner import IntegrationReport, IntegrationScanner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])

# ── Request Models ──────────────────────────────────────────────────

class ScanRequest(BaseModel):
    """Request body for scan endpoints."""
    project_path: str


# ── Hardcoded Scanner Response Models ───────────────────────────────

class HardcodedFindingResponse(BaseModel):
    """A single hardcoded finding."""
    file_path: str
    line_number: int
    category: str
    severity: str
    matched_text: str
    suggestion: str


class HardcodedScanResultResponse(BaseModel):
    """Hardcoded scan results."""
    findings: list[HardcodedFindingResponse]
    scanned_file_count: int


# ── Dependency Analyzer Response Models ─────────────────────────────

class DependencyPackageResponse(BaseModel):
    """A dependency with version info."""
    name: str
    current_version: str
    latest_version: str | None = None
    update_severity: str | None = None
    ecosystem: str
    is_dev: bool


class DependencyVulnerabilityResponse(BaseModel):
    """A known vulnerability."""
    package_name: str
    severity: str
    advisory_id: str
    title: str
    fixed_in: str | None = None


class DependencyEcosystemResponse(BaseModel):
    """Results for a single ecosystem."""
    ecosystem: str
    manifest_path: str
    outdated: list[DependencyPackageResponse]
    vulnerabilities: list[DependencyVulnerabilityResponse]


# ── Integration Scanner Response Models ─────────────────────────────

class IntegrationPointResponse(BaseModel):
    """A detected integration point."""
    service_name: str
    integration_type: str
    file_path: str
    line_number: int
    matched_text: str
    endpoint_url: str | None = None
    http_method: str | None = None


class ServiceSummaryResponse(BaseModel):
    """Per-service integration summary."""
    service_name: str
    count: int
    endpoints: list[str]
    files: list[str]


class IntegrationMapResponse(BaseModel):
    """Integration scan results."""
    integrations: list[IntegrationPointResponse]
    services_detected: list[ServiceSummaryResponse]
    files_scanned: int


# ── Freshness Analyzer Response Models ──────────────────────────────

class FileFreshnessResponse(BaseModel):
    """Freshness data for a single file."""
    file_path: str
    last_modified: str | None = None
    days_since_modified: int
    commit_count: int
    category: str
    last_author: str | None = None


class AgeDistributionResponse(BaseModel):
    """File count by freshness bucket."""
    fresh: int
    aging: int
    stale: int
    abandoned: int


class FreshnessReportResponse(BaseModel):
    """Freshness analysis results."""
    files: list[FileFreshnessResponse]
    age_distribution: AgeDistributionResponse
    stale_files: list[FileFreshnessResponse]
    abandoned_files: list[FileFreshnessResponse]
    single_commit_files: list[str]
    freshness_score: int


# ── Feature Inventory Response Models ───────────────────────────────

class FeatureEntryResponse(BaseModel):
    """A detected feature."""
    name: str
    category: str
    file_path: str
    line_number: int
    framework: str | None = None
    loc: int
    is_exported: bool
    import_count: int | None = None
    roadmap_match: str | None = None


class UntrackedFeatureResponse(BaseModel):
    """A feature not matched to any roadmap item."""
    feature: FeatureEntryResponse
    reason: str


class FeatureInventoryResponse(BaseModel):
    """Feature inventory results."""
    features: list[FeatureEntryResponse]
    by_category: dict[str, int]
    roadmap_mappings: dict[str, str]
    untracked_features: list[UntrackedFeatureResponse]
    total_features: int
    most_coupled: list[dict]
    import_counts: dict[str, int]


# ── Aggregate Intelligence Models ───────────────────────────────────

class CategoryScoreResponse(BaseModel):
    """Score for a single intelligence category."""
    category: str
    score: int
    grade: str
    finding_count: int
    critical_count: int
    warning_count: int


class IntelligenceSummaryResponse(BaseModel):
    """Summary embedded in the full intelligence report."""
    total_findings: int
    critical_count: int
    warning_count: int
    info_count: int


class IntelligenceSummaryLightResponse(BaseModel):
    """Lightweight intelligence summary for the GET /summary endpoint."""
    score: int
    grade: str
    categories: list[CategoryScoreResponse]
    staleness_flag: bool


class TopIssueResponse(BaseModel):
    """A top-priority issue from the scan."""
    issue: str
    severity: str
    file_path: str | None = None


class IntelligenceReportResponse(BaseModel):
    """Full intelligence report across all scanners."""
    project_path: str
    generated_at: str
    overall_score: int
    grade: str
    hardcoded: HardcodedScanResultResponse
    dependencies: list[DependencyEcosystemResponse]
    integrations: IntegrationMapResponse
    freshness: FreshnessReportResponse
    features: FeatureInventoryResponse
    summary: IntelligenceSummaryResponse
    top_issues: list[TopIssueResponse]
    scan_duration_ms: int
    scans_completed: int
    scans_failed: int


# ── Converters ──────────────────────────────────────────────────────

def _hardcoded_to_response(result: HardcodedScanResult) -> HardcodedScanResultResponse:
    """Convert HardcodedScanResult dataclass to API response."""
    return HardcodedScanResultResponse(
        findings=[
            HardcodedFindingResponse(
                file_path=str(f.file_path),
                line_number=f.line_number,
                category=f.category,
                severity=f.severity,
                matched_text=f.matched_text,
                suggestion=f.suggestion,
            )
            for f in result.findings
        ],
        scanned_file_count=result.scanned_file_count,
    )


def _integration_to_response(report: IntegrationReport) -> IntegrationMapResponse:
    """Convert IntegrationReport dataclass to API response."""
    return IntegrationMapResponse(
        integrations=[
            IntegrationPointResponse(
                service_name=i.service_name,
                integration_type=i.integration_type,
                file_path=i.file_path,
                line_number=i.line_number,
                matched_text=i.matched_text,
                endpoint_url=i.endpoint_url,
                http_method=i.http_method,
            )
            for i in report.integrations
        ],
        services_detected=[
            ServiceSummaryResponse(
                service_name=s.service_name,
                count=s.count,
                endpoints=s.endpoints,
                files=s.files,
            )
            for s in report.services_detected
        ],
        files_scanned=report.files_scanned,
    )


def _file_freshness_response(f) -> FileFreshnessResponse:
    """Convert a FileFreshness dataclass to response model."""
    return FileFreshnessResponse(
        file_path=f.file_path,
        last_modified=f.last_modified.isoformat() if f.last_modified else None,
        days_since_modified=f.days_since_modified,
        commit_count=f.commit_count,
        category=f.category,
        last_author=f.last_author,
    )


def _freshness_to_response(report: FreshnessReport) -> FreshnessReportResponse:
    """Convert FreshnessReport dataclass to API response."""
    # Build lookup for stale/abandoned files as FileFreshnessResponse objects
    stale_set = set(report.stale_files)
    abandoned_set = set(report.abandoned_files)

    stale_responses = [
        _file_freshness_response(f)
        for f in report.files
        if f.file_path in stale_set
    ]
    abandoned_responses = [
        _file_freshness_response(f)
        for f in report.files
        if f.file_path in abandoned_set
    ]

    return FreshnessReportResponse(
        files=[_file_freshness_response(f) for f in report.files],
        age_distribution=AgeDistributionResponse(
            fresh=report.age_distribution.fresh,
            aging=report.age_distribution.aging,
            stale=report.age_distribution.stale,
            abandoned=report.age_distribution.abandoned,
        ),
        stale_files=stale_responses,
        abandoned_files=abandoned_responses,
        single_commit_files=report.single_commit_files,
        freshness_score=report.freshness_score,
    )


def _dependency_to_ecosystems(report: DependencyReport) -> list[DependencyEcosystemResponse]:
    """Convert DependencyReport to a flat list of ecosystem responses."""
    return [
        DependencyEcosystemResponse(
            ecosystem=eco.ecosystem,
            manifest_path=str(eco.manifest_path),
            outdated=[
                DependencyPackageResponse(
                    name=dep.name,
                    current_version=dep.current_version,
                    latest_version=dep.latest_version,
                    update_severity=dep.update_severity,
                    ecosystem=dep.ecosystem,
                    is_dev=dep.is_dev,
                )
                for dep in eco.outdated
            ],
            vulnerabilities=[
                DependencyVulnerabilityResponse(
                    package_name=v.package_name,
                    severity=v.severity,
                    advisory_id=v.advisory_id,
                    title=v.title,
                    fixed_in=v.fixed_in,
                )
                for v in eco.vulnerabilities
            ],
        )
        for eco in report.ecosystems
    ]


def _feature_to_response(inventory: FeatureInventory) -> FeatureInventoryResponse:
    """Convert FeatureInventory dataclass to API response."""
    # Build a set of feature→roadmap_item_text for the first mapping
    roadmap_flat: dict[str, str] = {}
    for feat_name, mappings in inventory.roadmap_mappings.items():
        if mappings:
            roadmap_flat[feat_name] = mappings[0].roadmap_item_text

    def _feat(f) -> FeatureEntryResponse:
        return FeatureEntryResponse(
            name=f.name,
            category=f.category,
            file_path=f.file_path,
            line_number=f.line_number,
            framework=f.framework,
            loc=f.loc,
            is_exported=f.is_exported,
            import_count=inventory.import_counts.get(f.name),
            roadmap_match=roadmap_flat.get(f.name),
        )

    # by_category as counts
    by_category_counts: dict[str, int] = {
        cat: len(feats) for cat, feats in inventory.by_category.items()
    }

    # untracked features
    untracked = [
        UntrackedFeatureResponse(
            feature=_feat(uf.feature),
            reason=uf.reason,
        )
        for uf in inventory.untracked_features
    ]

    return FeatureInventoryResponse(
        features=[_feat(f) for f in inventory.features],
        by_category=by_category_counts,
        roadmap_mappings=roadmap_flat,
        untracked_features=untracked,
        total_features=inventory.total_features,
        most_coupled=inventory.most_coupled,
        import_counts=inventory.import_counts,
    )


def _compute_summary(
    hardcoded: HardcodedScanResultResponse,
    dep_ecosystems: list[DependencyEcosystemResponse],
    freshness: FreshnessReportResponse,
) -> IntelligenceSummaryResponse:
    """Compute a summary by counting findings across all scanners."""
    critical = 0
    warning = 0
    info = 0

    for f in hardcoded.findings:
        if f.severity == "critical":
            critical += 1
        elif f.severity == "warning":
            warning += 1
        else:
            info += 1

    for eco in dep_ecosystems:
        for v in eco.vulnerabilities:
            if v.severity == "critical":
                critical += 1
            elif v.severity in ("high", "warning"):
                warning += 1
            else:
                info += 1
        # Count major outdated as warnings
        for dep in eco.outdated:
            if dep.update_severity == "major":
                warning += 1
            elif dep.update_severity in ("minor", "patch"):
                info += 1

    # Stale/abandoned files count as warnings/critical
    critical += len(freshness.abandoned_files)
    warning += len(freshness.stale_files)

    total = critical + warning + info

    return IntelligenceSummaryResponse(
        total_findings=total,
        critical_count=critical,
        warning_count=warning,
        info_count=info,
    )


def _compute_score_and_grade(
    hardcoded: HardcodedScanResultResponse,
    dep_ecosystems: list[DependencyEcosystemResponse],
    integrations: IntegrationMapResponse,
    freshness: FreshnessReportResponse,
    features: FeatureInventoryResponse,
) -> tuple[int, str]:
    """Compute overall_score (0-100) and letter grade.

    Weights: hardcoded=0.20, dependencies=0.25, integrations=0.10,
             freshness=0.25, features=0.20.
    """
    # Hardcoded score
    hc_critical = sum(1 for f in hardcoded.findings if f.severity == "critical")
    hc_warning = sum(1 for f in hardcoded.findings if f.severity == "warning")
    hardcoded_score = max(0, 100 - hc_critical * 10 - hc_warning * 2)

    # Dependency score: count vulns and major outdated
    dep_penalty = 0
    for eco in dep_ecosystems:
        for v in eco.vulnerabilities:
            dep_penalty += 15 if v.severity == "critical" else 3
        for dep in eco.outdated:
            if dep.update_severity == "major":
                dep_penalty += 5
            elif dep.update_severity == "minor":
                dep_penalty += 1
    dependency_score = max(0, 100 - dep_penalty)

    # Integration score
    total_integrations = len(integrations.integrations)
    integration_score = min(100, 50 + total_integrations * 5) if total_integrations > 0 else 50

    # Freshness score
    freshness_score = freshness.freshness_score

    # Feature score
    feature_score = min(100, 50 + features.total_features * 2) if features.total_features > 0 else 50

    overall = int(
        hardcoded_score * 0.20
        + dependency_score * 0.25
        + integration_score * 0.10
        + freshness_score * 0.25
        + feature_score * 0.20
    )

    if overall >= 90:
        grade = "A"
    elif overall >= 80:
        grade = "B"
    elif overall >= 70:
        grade = "C"
    elif overall >= 60:
        grade = "D"
    else:
        grade = "F"

    return overall, grade


def _build_top_issues(
    hardcoded: HardcodedScanResultResponse,
    dep_ecosystems: list[DependencyEcosystemResponse],
    freshness: FreshnessReportResponse,
) -> list[TopIssueResponse]:
    """Build a list of top issues, sorted by severity."""
    issues: list[TopIssueResponse] = []

    for f in hardcoded.findings:
        if f.severity in ("critical", "warning"):
            issues.append(TopIssueResponse(
                issue=f.suggestion or f.matched_text,
                severity=f.severity,
                file_path=f.file_path,
            ))

    for eco in dep_ecosystems:
        for v in eco.vulnerabilities:
            if v.severity in ("critical", "high"):
                issues.append(TopIssueResponse(
                    issue=f"{v.title} ({v.package_name})",
                    severity=v.severity,
                ))

    for f in freshness.abandoned_files:
        issues.append(TopIssueResponse(
            issue=f"Abandoned file: {f.file_path} ({f.days_since_modified} days)",
            severity="warning",
            file_path=f.file_path,
        ))

    # Sort: critical first, then warning
    severity_order = {"critical": 0, "high": 1, "warning": 2}
    issues.sort(key=lambda x: severity_order.get(x.severity, 3))

    return issues[:20]


def _build_light_summary(
    hardcoded: HardcodedScanResultResponse,
    dep_ecosystems: list[DependencyEcosystemResponse],
    integrations: IntegrationMapResponse,
    freshness: FreshnessReportResponse,
    features: FeatureInventoryResponse,
) -> IntelligenceSummaryLightResponse:
    """Build the lightweight summary (score/grade/categories/staleness)."""
    # Per-category scores
    hc_critical = sum(1 for f in hardcoded.findings if f.severity == "critical")
    hc_warning = sum(1 for f in hardcoded.findings if f.severity == "warning")
    hc_score = max(0, 100 - hc_critical * 10 - hc_warning * 2)

    dep_penalty = 0
    dep_critical = 0
    dep_warning_count = 0
    dep_finding_count = 0
    for eco in dep_ecosystems:
        for v in eco.vulnerabilities:
            dep_finding_count += 1
            if v.severity == "critical":
                dep_critical += 1
                dep_penalty += 15
            else:
                dep_warning_count += 1
                dep_penalty += 3
        for dep in eco.outdated:
            dep_finding_count += 1
            if dep.update_severity == "major":
                dep_warning_count += 1
                dep_penalty += 5
            elif dep.update_severity == "minor":
                dep_penalty += 1
    dep_score = max(0, 100 - dep_penalty)

    total_integrations = len(integrations.integrations)
    int_score = min(100, 50 + total_integrations * 5) if total_integrations > 0 else 50

    fresh_score = freshness.freshness_score
    feat_score = min(100, 50 + features.total_features * 2) if features.total_features > 0 else 50

    def _grade(s: int) -> str:
        if s >= 90:
            return "A"
        if s >= 80:
            return "B"
        if s >= 70:
            return "C"
        if s >= 60:
            return "D"
        return "F"

    categories = [
        CategoryScoreResponse(
            category="hardcoded",
            score=hc_score,
            grade=_grade(hc_score),
            finding_count=len(hardcoded.findings),
            critical_count=hc_critical,
            warning_count=hc_warning,
        ),
        CategoryScoreResponse(
            category="dependency",
            score=dep_score,
            grade=_grade(dep_score),
            finding_count=dep_finding_count,
            critical_count=dep_critical,
            warning_count=dep_warning_count,
        ),
        CategoryScoreResponse(
            category="integration",
            score=int_score,
            grade=_grade(int_score),
            finding_count=total_integrations,
            critical_count=0,
            warning_count=0,
        ),
        CategoryScoreResponse(
            category="freshness",
            score=fresh_score,
            grade=_grade(fresh_score),
            finding_count=len(freshness.stale_files) + len(freshness.abandoned_files),
            critical_count=len(freshness.abandoned_files),
            warning_count=len(freshness.stale_files),
        ),
        CategoryScoreResponse(
            category="feature",
            score=feat_score,
            grade=_grade(feat_score),
            finding_count=features.total_features,
            critical_count=0,
            warning_count=0,
        ),
    ]

    overall, grade = _compute_score_and_grade(
        hardcoded, dep_ecosystems, integrations, freshness, features,
    )

    staleness_flag = len(freshness.stale_files) > 0 or len(freshness.abandoned_files) > 0

    return IntelligenceSummaryLightResponse(
        score=overall,
        grade=grade,
        categories=categories,
        staleness_flag=staleness_flag,
    )


def _validate_project_path(project_path: str) -> Path:
    """Validate and resolve a project path, raising HTTPException on failure."""
    path = Path(project_path).resolve()
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Project path does not exist: {path}")
    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {path}")
    return path


def _run_scanner(scanner_name: str, project_path: Path):
    """Run a single scanner by name and return the converted response."""
    if scanner_name == "hardcoded":
        result = HardcodedScanner(project_path).scan()
        return _hardcoded_to_response(result)
    elif scanner_name == "integration":
        report = IntegrationScanner(project_path).scan()
        return _integration_to_response(report)
    elif scanner_name == "freshness":
        report = FreshnessAnalyzer(project_path).analyze()
        return _freshness_to_response(report)
    elif scanner_name == "dependency":
        report = DependencyAnalyzer(project_path).analyze()
        return _dependency_to_ecosystems(report)
    elif scanner_name == "feature":
        inventory = FeatureInventoryScanner(project_path).scan()
        return _feature_to_response(inventory)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scanner: {scanner_name}. Valid scanners: hardcoded, integration, freshness, dependency, feature",
        )


# ── In-memory cache for reports ─────────────────────────────────────

_report_cache: dict[str, IntelligenceReportResponse] = {}
_light_summary_cache: dict[str, IntelligenceSummaryLightResponse] = {}


# ── Endpoints ───────────────────────────────────────────────────────

@router.post("/scan", response_model=IntelligenceReportResponse)
async def scan_intelligence(request: ScanRequest) -> IntelligenceReportResponse:
    """Run a full intelligence scan across all scanners.

    Executes hardcoded, integration, freshness, dependency, and feature
    scanners, then computes an aggregate summary with overall score and grade.
    """
    project_path = _validate_project_path(request.project_path)
    logger.info("Starting full intelligence scan for %s", project_path)

    start_time = time.monotonic()
    scans_completed = 0
    scans_failed = 0

    try:
        # Run hardcoded scanner
        try:
            hardcoded = _hardcoded_to_response(HardcodedScanner(project_path).scan())
            scans_completed += 1
        except Exception:
            logger.exception("Hardcoded scanner failed")
            hardcoded = HardcodedScanResultResponse(findings=[], scanned_file_count=0)
            scans_failed += 1

        # Run integration scanner
        try:
            integrations = _integration_to_response(IntegrationScanner(project_path).scan())
            scans_completed += 1
        except Exception:
            logger.exception("Integration scanner failed")
            integrations = IntegrationMapResponse(integrations=[], services_detected=[], files_scanned=0)
            scans_failed += 1

        # Run freshness analyzer
        try:
            freshness = _freshness_to_response(FreshnessAnalyzer(project_path).analyze())
            scans_completed += 1
        except Exception:
            logger.exception("Freshness analyzer failed")
            freshness = FreshnessReportResponse(
                files=[], age_distribution=AgeDistributionResponse(fresh=0, aging=0, stale=0, abandoned=0),
                stale_files=[], abandoned_files=[], single_commit_files=[], freshness_score=100,
            )
            scans_failed += 1

        # Run dependency analyzer
        try:
            dep_report = DependencyAnalyzer(project_path).analyze()
            dep_ecosystems = _dependency_to_ecosystems(dep_report)
            scans_completed += 1
        except Exception:
            logger.exception("Dependency analyzer failed")
            dep_ecosystems = []
            scans_failed += 1

        # Run feature inventory scanner
        try:
            features = _feature_to_response(FeatureInventoryScanner(project_path).scan())
            scans_completed += 1
        except Exception:
            logger.exception("Feature inventory scanner failed")
            features = FeatureInventoryResponse(
                features=[], by_category={}, roadmap_mappings={},
                untracked_features=[], total_features=0, most_coupled=[], import_counts={},
            )
            scans_failed += 1

        # Compute summary and score
        summary = _compute_summary(hardcoded, dep_ecosystems, freshness)
        overall_score, grade = _compute_score_and_grade(
            hardcoded, dep_ecosystems, integrations, freshness, features,
        )
        top_issues = _build_top_issues(hardcoded, dep_ecosystems, freshness)

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        report = IntelligenceReportResponse(
            project_path=str(project_path),
            generated_at=datetime.now(UTC).isoformat(),
            overall_score=overall_score,
            grade=grade,
            hardcoded=hardcoded,
            dependencies=dep_ecosystems,
            integrations=integrations,
            freshness=freshness,
            features=features,
            summary=summary,
            top_issues=top_issues,
            scan_duration_ms=elapsed_ms,
            scans_completed=scans_completed,
            scans_failed=scans_failed,
        )

        # Cache the report and light summary
        cache_key = str(project_path)
        _report_cache[cache_key] = report
        _light_summary_cache[cache_key] = _build_light_summary(
            hardcoded, dep_ecosystems, integrations, freshness, features,
        )

        logger.info(
            "Intelligence scan complete for %s — score: %d (%s), %d/%d scanners ok, %dms",
            project_path, overall_score, grade, scans_completed,
            scans_completed + scans_failed, elapsed_ms,
        )

        return report

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Intelligence scan failed for %s", project_path)
        raise HTTPException(status_code=500, detail=f"Intelligence scan failed: {exc}")


@router.get("/summary/{project_path:path}", response_model=IntelligenceSummaryLightResponse)
async def get_summary(project_path: str) -> IntelligenceSummaryLightResponse:
    """Get a lightweight intelligence summary for a project.

    Returns score, grade, per-category scores, and a staleness flag.
    Uses the cached report if available; returns 404 otherwise.
    """
    resolved = str(Path(project_path).resolve())

    if resolved not in _light_summary_cache:
        raise HTTPException(status_code=404, detail=f"No cached report for: {project_path}. Run POST /scan first.")

    return _light_summary_cache[resolved]


@router.get("/{project_path:path}", response_model=IntelligenceReportResponse)
async def get_cached_report(project_path: str) -> IntelligenceReportResponse:
    """Retrieve a cached intelligence report for a project.

    Returns 404 if no cached report exists. Use POST /scan to generate one.
    """
    resolved = str(Path(project_path).resolve())

    if resolved not in _report_cache:
        raise HTTPException(status_code=404, detail=f"No cached report for: {project_path}. Run POST /scan first.")

    return _report_cache[resolved]


@router.post("/scan/{scanner_name}")
async def scan_individual(scanner_name: str, request: ScanRequest):
    """Run a single intelligence scanner.

    Valid scanner names: hardcoded, integration, freshness, dependency, feature.
    """
    project_path = _validate_project_path(request.project_path)
    logger.info("Running %s scanner for %s", scanner_name, project_path)

    try:
        return _run_scanner(scanner_name, project_path)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("%s scanner failed for %s", scanner_name, project_path)
        raise HTTPException(status_code=500, detail=f"{scanner_name} scanner failed: {exc}")
