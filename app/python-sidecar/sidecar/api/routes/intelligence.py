"""Project intelligence scanning API endpoints.

Orchestrates the five core scanners (hardcoded, integration, freshness,
dependency, feature) and exposes them via REST endpoints for the frontend.
"""

import asyncio
import fnmatch
import json
import logging
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.core.dependency_analyzer import DependencyAnalyzer, DependencyReport
from src.core.feature_inventory import FeatureInventory, FeatureInventoryScanner
from src.core.freshness_analyzer import FreshnessAnalyzer, FreshnessReport
from src.core.hardcoded_scanner import HardcodedScanner, HardcodedScanResult
from src.core.integration_scanner import IntegrationReport, IntegrationScanner
from src.core.runtime import project_id_for_path, project_runtime_dir

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
    top_finding: str | None = None


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
    dim: str | None = None
    line_number: int | None = None
    issue_type: str | None = None


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
    category_scores: list[CategoryScoreResponse] = []
    total_files_scanned: int = 0
    scan_duration_ms: int
    scans_completed: int
    scans_failed: int
    commit_hash: str | None = None
    scanners_rerun: list[str] | None = None


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
             freshness=0.20, features=0.25.
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
        + freshness_score * 0.20
        + feature_score * 0.25
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
    features: FeatureInventoryResponse | None = None,
) -> list[TopIssueResponse]:
    """Build a list of top issues, sorted by severity."""
    issues: list[TopIssueResponse] = []

    for f in hardcoded.findings:
        if f.severity in ("critical", "warning"):
            issues.append(TopIssueResponse(
                issue=f.suggestion or f.matched_text,
                severity=f.severity,
                file_path=f.file_path,
                dim="hardcoded",
                line_number=f.line_number,
                issue_type=f.category.upper(),
            ))

    for eco in dep_ecosystems:
        for v in eco.vulnerabilities:
            if v.severity in ("critical", "high"):
                issues.append(TopIssueResponse(
                    issue=f"{v.title} ({v.package_name})",
                    severity=v.severity,
                    dim="dependency",
                    issue_type="VULNERABILITY",
                ))
        for dep in eco.outdated:
            if dep.update_severity == "major":
                issues.append(TopIssueResponse(
                    issue=f"Outdated: {dep.name} {dep.current_version} → {dep.latest_version}",
                    severity="warning",
                    dim="dependency",
                    issue_type="OUTDATED",
                ))

    for f in freshness.abandoned_files:
        issues.append(TopIssueResponse(
            issue=f"Abandoned file: {f.file_path} ({f.days_since_modified} days)",
            severity="warning",
            file_path=f.file_path,
            dim="freshness",
            issue_type="ABANDONED",
        ))

    # Feature-based issues
    if features:
        for coupled in features.most_coupled:
            import_count = coupled.get("import_count", 0)
            if import_count > 10:
                issues.append(TopIssueResponse(
                    issue=f"High coupling: {coupled.get('name', 'unknown')} ({import_count} dependents)",
                    severity="warning",
                    dim="feature",
                    issue_type="HIGH_COUPLING",
                ))
        for uf in features.untracked_features:
            issues.append(TopIssueResponse(
                issue=f"Untracked feature: {uf.feature.name} ({uf.reason})",
                severity="info",
                file_path=uf.feature.file_path,
                dim="feature",
                line_number=uf.feature.line_number,
                issue_type="UNTRACKED",
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

    # Generate top_finding per dimension
    hc_top_finding: str | None = None
    if hc_critical > 0:
        first_crit = next((f for f in hardcoded.findings if f.severity == "critical"), None)
        if first_crit:
            hc_top_finding = first_crit.suggestion or first_crit.matched_text
    elif len(hardcoded.findings) > 0:
        hc_top_finding = f"{len(hardcoded.findings)} hardcoded values found"

    dep_top_finding: str | None = None
    for eco in dep_ecosystems:
        for v in eco.vulnerabilities:
            if v.severity in ("critical", "high"):
                dep_top_finding = v.title
                break
        if dep_top_finding:
            break
    if not dep_top_finding and dep_finding_count > 0:
        total_outdated = sum(len(eco.outdated) for eco in dep_ecosystems)
        dep_top_finding = f"{total_outdated} outdated packages"

    int_top_finding: str | None = None
    if total_integrations > 0:
        service_count = len(integrations.services_detected)
        int_top_finding = f"{service_count} services auto-mapped"

    fresh_top_finding: str | None = None
    n_stale = len(freshness.stale_files)
    n_abandoned = len(freshness.abandoned_files)
    if n_stale > 0 or n_abandoned > 0:
        parts = []
        if n_stale > 0:
            parts.append(f"{n_stale} stale")
        if n_abandoned > 0:
            parts.append(f"{n_abandoned} abandoned")
        fresh_top_finding = ", ".join(parts)
    else:
        fresh_top_finding = "All files fresh"

    feat_top_finding: str | None = None
    if features.most_coupled:
        top = features.most_coupled[0]
        feat_top_finding = f"Most coupled: {top.get('name', 'unknown')}"
    elif features.untracked_features:
        feat_top_finding = f"{len(features.untracked_features)} untracked features"

    categories = [
        CategoryScoreResponse(
            category="hardcoded",
            score=hc_score,
            grade=_grade(hc_score),
            finding_count=len(hardcoded.findings),
            critical_count=hc_critical,
            warning_count=hc_warning,
            top_finding=hc_top_finding,
        ),
        CategoryScoreResponse(
            category="dependency",
            score=dep_score,
            grade=_grade(dep_score),
            finding_count=dep_finding_count,
            critical_count=dep_critical,
            warning_count=dep_warning_count,
            top_finding=dep_top_finding,
        ),
        CategoryScoreResponse(
            category="integration",
            score=int_score,
            grade=_grade(int_score),
            finding_count=total_integrations,
            critical_count=0,
            warning_count=0,
            top_finding=int_top_finding,
        ),
        CategoryScoreResponse(
            category="freshness",
            score=fresh_score,
            grade=_grade(fresh_score),
            finding_count=len(freshness.stale_files) + len(freshness.abandoned_files),
            critical_count=len(freshness.abandoned_files),
            warning_count=len(freshness.stale_files),
            top_finding=fresh_top_finding,
        ),
        CategoryScoreResponse(
            category="feature",
            score=feat_score,
            grade=_grade(feat_score),
            finding_count=features.total_features,
            critical_count=0,
            warning_count=0,
            top_finding=feat_top_finding,
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


# ── Scanner defaults (for fallback on failure) ────────────────────

_SCANNER_DEFAULTS: dict[str, object] = {
    "hardcoded": lambda: HardcodedScanResultResponse(findings=[], scanned_file_count=0),
    "integration": lambda: IntegrationMapResponse(integrations=[], services_detected=[], files_scanned=0),
    "freshness": lambda: FreshnessReportResponse(
        files=[], age_distribution=AgeDistributionResponse(fresh=0, aging=0, stale=0, abandoned=0),
        stale_files=[], abandoned_files=[], single_commit_files=[], freshness_score=100,
    ),
    "dependency": lambda: [],
    "feature": lambda: FeatureInventoryResponse(
        features=[], by_category={}, roadmap_mappings={},
        untracked_features=[], total_features=0, most_coupled=[], import_counts={},
    ),
}

ALL_SCANNER_NAMES = ["hardcoded", "integration", "freshness", "dependency", "feature"]


def _run_scanner_safe(scanner_name: str, project_path: Path) -> tuple[str, object, bool]:
    """Run a scanner with error handling. Returns (name, result, succeeded)."""
    try:
        result = _run_scanner(scanner_name, project_path)
        return (scanner_name, result, True)
    except Exception:
        logger.exception("%s scanner failed", scanner_name)
        return (scanner_name, _SCANNER_DEFAULTS[scanner_name](), False)


# ── Git helpers ────────────────────────────────────────────────────

def _get_git_head(project_path: Path) -> str | None:
    """Get current HEAD commit hash, or None if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_path, capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _get_changed_files(project_path: Path, from_commit: str, to_commit: str) -> set[str] | None:
    """Get files changed between two commits. Returns None on error (run all scanners)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", from_commit, to_commit],
            cwd=project_path, capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        lines = result.stdout.strip()
        return set(lines.splitlines()) if lines else set()
    except Exception:
        return None


# ── Smart diff: which scanners care about which files ──────────────

SCANNER_FILE_PATTERNS: dict[str, list[str]] = {
    "hardcoded": ["*.py", "*.js", "*.ts", "*.tsx", "*.jsx", "*.json", "*.yaml", "*.yml", "*.toml", "*.env", "*.ini", "*.cfg", "*.conf"],
    "integration": ["*.py", "*.js", "*.ts", "*.tsx", "*.jsx", "*.json", "*.yaml", "*.yml"],
    "freshness": ["*.py", "*.js", "*.ts", "*.tsx", "*.jsx", "*.java", "*.go", "*.rb", "*.rs"],
    "dependency": ["package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod"],
    "feature": ["*.py", "*.js", "*.ts", "*.tsx", "*.jsx", "*.mjs"],
}


def _scanners_needing_rerun(changed_files: set[str]) -> list[str]:
    """Determine which scanners need re-running based on changed files."""
    needs_rerun: list[str] = []
    for scanner_name, patterns in SCANNER_FILE_PATTERNS.items():
        for changed_file in changed_files:
            basename = changed_file.split("/")[-1]
            if any(fnmatch.fnmatch(basename, pat) or fnmatch.fnmatch(changed_file, pat) for pat in patterns):
                needs_rerun.append(scanner_name)
                break
    return needs_rerun


# ── Snapshot persistence ───────────────────────────────────────────

def _get_snapshot_path(project_path: Path) -> Path:
    """Get path to the snapshot metadata file."""
    project_id = project_id_for_path(project_path)
    runtime_dir = project_runtime_dir(project_id)
    return runtime_dir / "intelligence-snapshot.json"


def _load_snapshot(project_path: Path) -> dict | None:
    """Load the last scan snapshot metadata."""
    path = _get_snapshot_path(project_path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_snapshot(project_path: Path, commit: str | None, scanners_run: list[str]) -> None:
    """Save snapshot metadata after a scan."""
    path = _get_snapshot_path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing snapshot to preserve per-scanner versions
    existing = _load_snapshot(project_path) or {}
    scanner_versions = existing.get("scanner_versions", {})
    for name in scanners_run:
        scanner_versions[name] = commit

    snapshot = {
        "commit": commit,
        "generated_at": datetime.now(UTC).isoformat(),
        "scanner_versions": scanner_versions,
    }
    try:
        path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    except Exception:
        logger.warning("Failed to save intelligence snapshot to %s", path)


# ── Cache (in-memory + disk) ───────────────────────────────────────

_report_cache: dict[str, IntelligenceReportResponse] = {}
_light_summary_cache: dict[str, IntelligenceSummaryLightResponse] = {}


def _get_cache_paths(project_path: Path) -> tuple[Path, Path]:
    """Get on-disk cache paths for a project's intelligence data."""
    project_id = project_id_for_path(project_path)
    runtime_dir = project_runtime_dir(project_id)
    return (
        runtime_dir / "intelligence-report.json",
        runtime_dir / "intelligence-summary.json",
    )


def _load_cached_report(project_path: Path) -> IntelligenceReportResponse | None:
    """Load intelligence report from in-memory cache or disk."""
    cache_key = str(project_path)
    if cache_key in _report_cache:
        return _report_cache[cache_key]

    report_file, summary_file = _get_cache_paths(project_path)
    if report_file.exists():
        try:
            data = json.loads(report_file.read_text(encoding="utf-8"))
            report = IntelligenceReportResponse(**data)
            _report_cache[cache_key] = report
            # Also restore the light summary if it exists on disk
            if summary_file.exists() and cache_key not in _light_summary_cache:
                sdata = json.loads(summary_file.read_text(encoding="utf-8"))
                _light_summary_cache[cache_key] = IntelligenceSummaryLightResponse(**sdata)
            return report
        except Exception:
            logger.warning("Failed to load cached intelligence report from %s", report_file)
    return None


def _load_cached_summary(project_path: Path) -> IntelligenceSummaryLightResponse | None:
    """Load intelligence summary from in-memory cache or disk."""
    cache_key = str(project_path)
    if cache_key in _light_summary_cache:
        return _light_summary_cache[cache_key]

    _, summary_file = _get_cache_paths(project_path)
    if summary_file.exists():
        try:
            data = json.loads(summary_file.read_text(encoding="utf-8"))
            summary = IntelligenceSummaryLightResponse(**data)
            _light_summary_cache[cache_key] = summary
            return summary
        except Exception:
            logger.warning("Failed to load cached intelligence summary from %s", summary_file)
    return None


def _save_cached(
    project_path: Path,
    report: IntelligenceReportResponse,
    summary: IntelligenceSummaryLightResponse,
) -> None:
    """Save intelligence data to both in-memory and disk cache."""
    cache_key = str(project_path)
    _report_cache[cache_key] = report
    _light_summary_cache[cache_key] = summary

    report_file, summary_file = _get_cache_paths(project_path)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        report_file.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        summary_file.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    except Exception:
        logger.warning("Failed to save intelligence cache to %s", report_file.parent)


# ── Endpoints ───────────────────────────────────────────────────────

async def _run_scanners_parallel(
    project_path: Path,
    scanner_names: list[str],
) -> dict[str, tuple[object, bool]]:
    """Run the given scanners in parallel via thread pool.

    Returns dict of scanner_name -> (result, succeeded).
    """
    tasks = [
        asyncio.to_thread(_run_scanner_safe, name, project_path)
        for name in scanner_names
    ]
    results = await asyncio.gather(*tasks)
    return {name: (result, ok) for name, result, ok in results}


def _build_report(
    project_path: Path,
    scanner_results: dict[str, tuple[object, bool]],
    elapsed_ms: int,
    commit_hash: str | None,
    scanners_rerun: list[str],
) -> tuple[IntelligenceReportResponse, IntelligenceSummaryLightResponse]:
    """Build a full report + light summary from scanner results."""
    hardcoded = scanner_results["hardcoded"][0]
    integrations = scanner_results["integration"][0]
    freshness = scanner_results["freshness"][0]
    dep_ecosystems = scanner_results["dependency"][0]
    features = scanner_results["feature"][0]

    scans_completed = sum(1 for _, ok in scanner_results.values() if ok)
    scans_failed = sum(1 for _, ok in scanner_results.values() if not ok)

    summary = _compute_summary(hardcoded, dep_ecosystems, freshness)
    overall_score, grade = _compute_score_and_grade(
        hardcoded, dep_ecosystems, integrations, freshness, features,
    )
    top_issues = _build_top_issues(hardcoded, dep_ecosystems, freshness, features)
    light_summary = _build_light_summary(
        hardcoded, dep_ecosystems, integrations, freshness, features,
    )
    total_files_scanned = hardcoded.scanned_file_count + integrations.files_scanned

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
        category_scores=light_summary.categories,
        total_files_scanned=total_files_scanned,
        scan_duration_ms=elapsed_ms,
        scans_completed=scans_completed,
        scans_failed=scans_failed,
        commit_hash=commit_hash,
        scanners_rerun=scanners_rerun,
    )
    return report, light_summary


@router.post("/scan", response_model=IntelligenceReportResponse)
async def scan_intelligence(
    request: ScanRequest,
    force: bool = Query(False, description="Force full rescan, ignoring diff cache"),
) -> IntelligenceReportResponse:
    """Run an intelligence scan across all scanners.

    By default uses smart diffing: only re-runs scanners whose relevant files
    changed since the last snapshot. Pass force=true to re-run all scanners.

    All scanners execute in parallel for maximum speed.
    """
    project_path = _validate_project_path(request.project_path)
    current_commit = _get_git_head(project_path)

    start_time = time.monotonic()

    try:
        # ── Smart diff: determine which scanners to run ───────────
        scanners_to_run = ALL_SCANNER_NAMES  # default: run all
        cached_report = None

        if not force and current_commit:
            snapshot = _load_snapshot(project_path)
            if snapshot and snapshot.get("commit"):
                prev_commit = snapshot["commit"]
                if prev_commit == current_commit:
                    # Same commit — check for uncommitted changes too
                    changed_files = _get_changed_files(project_path, prev_commit, "HEAD")
                    if changed_files is not None and len(changed_files) == 0:
                        # Nothing changed — return cached report if available
                        cached = _load_cached_report(project_path)
                        if cached:
                            elapsed_ms = int((time.monotonic() - start_time) * 1000)
                            # Return cached with updated metadata
                            cached.scan_duration_ms = elapsed_ms
                            cached.scanners_rerun = []
                            cached.commit_hash = current_commit
                            logger.info(
                                "Intelligence scan skipped for %s — no changes since %s, %dms",
                                project_path, current_commit[:8], elapsed_ms,
                            )
                            return cached
                else:
                    # Different commit — check which files changed
                    changed_files = _get_changed_files(project_path, prev_commit, current_commit)
                    if changed_files is not None and len(changed_files) > 0:
                        needed = _scanners_needing_rerun(changed_files)
                        if needed and len(needed) < len(ALL_SCANNER_NAMES):
                            # Partial rescan: load cached, re-run only affected scanners
                            cached_report = _load_cached_report(project_path)
                            if cached_report:
                                scanners_to_run = needed
                                logger.info(
                                    "Partial rescan for %s: %d/%d scanners (%s)",
                                    project_path, len(needed), len(ALL_SCANNER_NAMES),
                                    ", ".join(needed),
                                )
                    elif changed_files is not None and len(changed_files) == 0:
                        # Commits differ but no file changes (e.g. merge commit)
                        cached = _load_cached_report(project_path)
                        if cached:
                            elapsed_ms = int((time.monotonic() - start_time) * 1000)
                            cached.scan_duration_ms = elapsed_ms
                            cached.scanners_rerun = []
                            cached.commit_hash = current_commit
                            _save_snapshot(project_path, current_commit, [])
                            return cached

        is_full_scan = len(scanners_to_run) == len(ALL_SCANNER_NAMES)
        log_msg = "full" if is_full_scan else f"partial ({len(scanners_to_run)}/{len(ALL_SCANNER_NAMES)})"
        logger.info("Starting %s intelligence scan for %s", log_msg, project_path)

        # ── Run scanners in parallel ──────────────────────────────
        fresh_results = await _run_scanners_parallel(project_path, scanners_to_run)

        # ── Merge with cached results for partial rescans ─────────
        if cached_report and not is_full_scan:
            scanner_results: dict[str, tuple[object, bool]] = {}
            for name in ALL_SCANNER_NAMES:
                if name in fresh_results:
                    scanner_results[name] = fresh_results[name]
                else:
                    # Use cached data
                    cached_data = _get_scanner_data_from_report(cached_report, name)
                    scanner_results[name] = (cached_data, True)
        else:
            scanner_results = fresh_results

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        report, light_summary = _build_report(
            project_path, scanner_results, elapsed_ms, current_commit, scanners_to_run,
        )

        # Cache the report and save snapshot
        _save_cached(project_path, report, light_summary)
        _save_snapshot(project_path, current_commit, scanners_to_run)

        logger.info(
            "Intelligence scan complete for %s — score: %d (%s), %d/%d scanners ran, %dms",
            project_path, report.overall_score, report.grade,
            len(scanners_to_run), len(ALL_SCANNER_NAMES), elapsed_ms,
        )

        return report

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Intelligence scan failed for %s", project_path)
        raise HTTPException(status_code=500, detail=f"Intelligence scan failed: {exc}")


def _get_scanner_data_from_report(
    report: IntelligenceReportResponse, scanner_name: str,
) -> object:
    """Extract a scanner's data from an existing report for merge."""
    if scanner_name == "hardcoded":
        return report.hardcoded
    elif scanner_name == "integration":
        return report.integrations
    elif scanner_name == "freshness":
        return report.freshness
    elif scanner_name == "dependency":
        return report.dependencies
    elif scanner_name == "feature":
        return report.features
    return _SCANNER_DEFAULTS[scanner_name]()


@router.get("/summary/{project_path:path}", response_model=IntelligenceSummaryLightResponse)
async def get_summary(project_path: str) -> IntelligenceSummaryLightResponse:
    """Get a lightweight intelligence summary for a project.

    Returns score, grade, per-category scores, and a staleness flag.
    Uses the cached report if available (in-memory or disk); returns 404 otherwise.
    """
    resolved = Path(project_path).resolve()
    cached = _load_cached_summary(resolved)
    if not cached:
        raise HTTPException(status_code=404, detail=f"No cached report for: {project_path}. Run POST /scan first.")
    return cached


@router.get("/{project_path:path}", response_model=IntelligenceReportResponse)
async def get_cached_report(project_path: str) -> IntelligenceReportResponse:
    """Retrieve a cached intelligence report for a project.

    Returns 404 if no cached report exists (checked in-memory then disk).
    Use POST /scan to generate one.
    """
    resolved = Path(project_path).resolve()
    cached = _load_cached_report(resolved)
    if not cached:
        raise HTTPException(status_code=404, detail=f"No cached report for: {project_path}. Run POST /scan first.")
    return cached


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


class OpenFileRequest(BaseModel):
    """Request to open a file in the user's editor."""
    file_path: str
    line_number: int | None = None
    project_path: str


@router.post("/open-file")
async def open_file_in_editor(request: OpenFileRequest):
    """Open a file in the user's editor."""
    file_path = request.file_path
    if not Path(file_path).is_absolute():
        file_path = str(Path(request.project_path).resolve() / file_path)
    if not Path(file_path).exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    code_bin = shutil.which("code")
    if code_bin:
        target = f"{file_path}:{request.line_number}" if request.line_number else file_path
        subprocess.Popen([code_bin, "--goto", target])
        return {"opened": True, "editor": "vscode"}

    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        subprocess.Popen([editor, file_path])
        return {"opened": True, "editor": editor}

    subprocess.Popen(["open", file_path])  # macOS fallback
    return {"opened": True, "editor": "system"}
