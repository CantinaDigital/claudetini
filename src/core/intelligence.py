"""Project intelligence orchestrator.

Coordinates all backend scanners (hardcoded, integration, freshness,
dependency, feature inventory), aggregates results into a scored report,
and caches the output for quick retrieval.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .cache import JsonCache
from .dependency_analyzer import DependencyAnalyzer, DependencyReport
from .feature_inventory import FeatureInventory, FeatureInventoryScanner
from .freshness_analyzer import FreshnessAnalyzer, FreshnessReport
from .hardcoded_scanner import HardcodedScanner, HardcodedScanResult
from .integration_scanner import IntegrationReport, IntegrationScanner

logger = logging.getLogger(__name__)

# Cache TTL in seconds (1 hour)
_CACHE_TTL_SECONDS = 3600

# Score weights for each scanner dimension
_WEIGHTS: dict[str, float] = {
    "hardcoded": 0.20,
    "dependencies": 0.25,
    "integrations": 0.10,
    "freshness": 0.25,
    "features": 0.20,
}

# Issue priority tiers (lower = higher priority)
_ISSUE_PRIORITY: dict[str, int] = {
    "critical_vuln": 0,
    "hardcoded_critical": 1,
    "stale_file": 2,
    "outdated_major_dep": 3,
    "untracked_feature": 4,
}


@dataclass
class IntelligenceSummary:
    """Aggregate counts across all scanner findings."""

    total_findings: int = 0
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0


@dataclass
class IntelligenceReport:
    """Full intelligence report aggregating all scanner results."""

    project_path: str
    generated_at: str
    overall_score: float
    grade: str
    hardcoded: dict[str, Any] | None = None
    dependencies: dict[str, Any] | None = None
    integrations: dict[str, Any] | None = None
    freshness: dict[str, Any] | None = None
    features: dict[str, Any] | None = None
    summary: IntelligenceSummary = field(default_factory=IntelligenceSummary)
    top_issues: list[dict[str, Any]] = field(default_factory=list)
    scan_duration_ms: float = 0.0
    scans_completed: int = 0
    scans_failed: int = 0

    def __repr__(self) -> str:
        return (
            f"IntelligenceReport(project={self.project_path!r}, "
            f"score={self.overall_score:.1f}, grade={self.grade!r}, "
            f"findings={self.summary.total_findings}, "
            f"completed={self.scans_completed}, failed={self.scans_failed})"
        )


def _score_to_grade(score: float) -> str:
    """Convert a 0-100 score to a letter grade."""
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _compute_project_hash(project_path: Path) -> str:
    """Compute MD5-based hash consistent with Project._compute_claude_hash."""
    path_str = str(project_path.resolve())
    return hashlib.md5(path_str.encode()).hexdigest()[:16]


def _safe_asdict(obj: Any) -> dict[str, Any]:
    """Convert a dataclass to dict, handling Path objects."""
    d = asdict(obj)
    return _convert_paths(d)


def _convert_paths(obj: Any) -> Any:
    """Recursively convert Path objects to strings for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _convert_paths(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_paths(item) for item in obj]
    if isinstance(obj, Path):
        return str(obj)
    return obj


class ProjectIntelligence:
    """Orchestrates all project scanners and produces an intelligence report."""

    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path.resolve()
        self._project_hash = _compute_project_hash(self.project_path)
        cache_dir = Path.home() / ".claudetini" / "projects" / self._project_hash
        self._cache = JsonCache(cache_dir / "intelligence-cache.json")

    def __repr__(self) -> str:
        return f"ProjectIntelligence(project_path={self.project_path!r})"

    def run_full_scan(self) -> IntelligenceReport:
        """Execute all 5 scanners, aggregate results into a scored report."""
        start = time.monotonic()

        # Scanner results (None means scanner failed)
        hardcoded_result: HardcodedScanResult | None = None
        dependency_result: DependencyReport | None = None
        integration_result: IntegrationReport | None = None
        freshness_result: FreshnessReport | None = None
        feature_result: FeatureInventory | None = None

        scans_completed = 0
        scans_failed = 0

        # Run each scanner with error isolation
        try:
            hardcoded_result = HardcodedScanner(self.project_path).scan()
            scans_completed += 1
        except Exception:
            logger.exception("Hardcoded scanner failed")
            scans_failed += 1

        try:
            dependency_result = DependencyAnalyzer(self.project_path).analyze()
            scans_completed += 1
        except Exception:
            logger.exception("Dependency analyzer failed")
            scans_failed += 1

        try:
            integration_result = IntegrationScanner(self.project_path).scan()
            scans_completed += 1
        except Exception:
            logger.exception("Integration scanner failed")
            scans_failed += 1

        try:
            freshness_result = FreshnessAnalyzer(self.project_path).analyze()
            scans_completed += 1
        except Exception:
            logger.exception("Freshness analyzer failed")
            scans_failed += 1

        try:
            feature_result = FeatureInventoryScanner(self.project_path).scan()
            scans_completed += 1
        except Exception:
            logger.exception("Feature inventory scanner failed")
            scans_failed += 1

        # Compute per-dimension scores
        dimension_scores = self._compute_dimension_scores(
            hardcoded_result,
            dependency_result,
            integration_result,
            freshness_result,
            feature_result,
        )

        # Weighted overall score
        overall_score = sum(
            dimension_scores[dim] * _WEIGHTS[dim] for dim in _WEIGHTS
        )
        overall_score = max(0.0, min(100.0, overall_score))

        # Build summary counts
        summary = self._build_summary(
            hardcoded_result, dependency_result, integration_result,
            freshness_result, feature_result,
        )

        # Collect and rank top issues
        top_issues = self._rank_top_issues(
            hardcoded_result, dependency_result, freshness_result, feature_result,
        )

        elapsed_ms = (time.monotonic() - start) * 1000
        generated_at = datetime.now(UTC).isoformat()

        report = IntelligenceReport(
            project_path=str(self.project_path),
            generated_at=generated_at,
            overall_score=round(overall_score, 1),
            grade=_score_to_grade(overall_score),
            hardcoded=_safe_asdict(hardcoded_result) if hardcoded_result else None,
            dependencies=_safe_asdict(dependency_result) if dependency_result else None,
            integrations=_safe_asdict(integration_result) if integration_result else None,
            freshness=_safe_asdict(freshness_result) if freshness_result else None,
            features=_safe_asdict(feature_result) if feature_result else None,
            summary=summary,
            top_issues=top_issues[:10],
            scan_duration_ms=round(elapsed_ms, 1),
            scans_completed=scans_completed,
            scans_failed=scans_failed,
        )

        # Cache the report
        self._save_to_cache(report)

        return report

    def run_scanner(self, name: str) -> dict[str, Any]:
        """Run an individual scanner by name.

        Args:
            name: One of 'hardcoded', 'integration', 'freshness', 'dependency', 'feature'.

        Returns:
            Scanner result as a dict.

        Raises:
            ValueError: If scanner name is unknown.
        """
        scanners: dict[str, Any] = {
            "hardcoded": lambda: HardcodedScanner(self.project_path).scan(),
            "integration": lambda: IntegrationScanner(self.project_path).scan(),
            "freshness": lambda: FreshnessAnalyzer(self.project_path).analyze(),
            "dependency": lambda: DependencyAnalyzer(self.project_path).analyze(),
            "feature": lambda: FeatureInventoryScanner(self.project_path).scan(),
        }
        if name not in scanners:
            raise ValueError(
                f"Unknown scanner {name!r}. "
                f"Valid names: {', '.join(sorted(scanners))}"
            )
        result = scanners[name]()
        return _safe_asdict(result)

    def get_cached_report(self) -> IntelligenceReport | None:
        """Load a cached report if it exists and is still fresh (< 1 hour old)."""
        payload = self._cache.load()
        if payload is None:
            return None

        # Check freshness
        try:
            generated = datetime.fromisoformat(payload.generated_at)
            # Ensure timezone-aware comparison
            now = datetime.now(UTC)
            if generated.tzinfo is None:
                generated = generated.replace(tzinfo=UTC)
            age_seconds = (now - generated).total_seconds()
            if age_seconds > _CACHE_TTL_SECONDS:
                return None
        except (ValueError, TypeError):
            return None

        return self._report_from_cache(payload.data)

    # ---- Private helpers ----

    def _compute_dimension_scores(
        self,
        hardcoded: HardcodedScanResult | None,
        dependencies: DependencyReport | None,
        integrations: IntegrationReport | None,
        freshness: FreshnessReport | None,
        features: FeatureInventory | None,
    ) -> dict[str, float]:
        """Compute 0-100 score for each dimension."""
        scores: dict[str, float] = {}

        # Hardcoded: fewer issues = higher score
        if hardcoded is not None:
            findings = hardcoded.findings
            critical = sum(1 for f in findings if f.severity == "critical")
            warnings = sum(1 for f in findings if f.severity == "warning")
            # Deduct 15 per critical, 5 per warning, cap at 0
            scores["hardcoded"] = max(0.0, 100.0 - critical * 15 - warnings * 5)
        else:
            scores["hardcoded"] = 50.0  # Unknown = neutral

        # Dependencies: use the analyzer's built-in health_score
        if dependencies is not None:
            scores["dependencies"] = float(dependencies.health_score)
        else:
            scores["dependencies"] = 50.0

        # Integrations: high external dependency count = lower score
        if integrations is not None:
            ext_count = integrations.external_api_count
            # Deduct 5 points per external API, cap at 0
            scores["integrations"] = max(0.0, 100.0 - ext_count * 5)
        else:
            scores["integrations"] = 50.0

        # Freshness: use the analyzer's built-in freshness_score
        if freshness is not None:
            scores["freshness"] = float(freshness.freshness_score)
        else:
            scores["freshness"] = 50.0

        # Features: untracked ratio lowers the score
        if features is not None:
            total = features.total_features
            untracked = len(features.untracked_features)
            if total > 0:
                tracked_ratio = 1.0 - (untracked / total)
                scores["features"] = max(0.0, tracked_ratio * 100.0)
            else:
                scores["features"] = 100.0  # No features to track
        else:
            scores["features"] = 50.0

        return scores

    def _build_summary(
        self,
        hardcoded: HardcodedScanResult | None,
        dependencies: DependencyReport | None,
        integrations: IntegrationReport | None,
        freshness: FreshnessReport | None,
        features: FeatureInventory | None,
    ) -> IntelligenceSummary:
        """Aggregate finding counts across all scanners."""
        total = 0
        critical = 0
        warning = 0
        info = 0

        if hardcoded is not None:
            for f in hardcoded.findings:
                total += 1
                if f.severity == "critical":
                    critical += 1
                elif f.severity == "warning":
                    warning += 1
                else:
                    info += 1

        if dependencies is not None:
            for eco in dependencies.ecosystems:
                for v in eco.vulnerabilities:
                    total += 1
                    if v.severity in ("critical", "high"):
                        critical += 1
                    elif v.severity == "medium":
                        warning += 1
                    else:
                        info += 1
                # Outdated deps as warnings
                for dep in eco.outdated:
                    total += 1
                    if dep.update_severity == "major":
                        warning += 1
                    else:
                        info += 1

        if integrations is not None:
            # Integration points are informational
            total += integrations.total_integrations
            info += integrations.total_integrations

        if freshness is not None:
            stale_count = len(freshness.stale_files)
            abandoned_count = len(freshness.abandoned_files)
            total += stale_count + abandoned_count
            warning += stale_count
            critical += abandoned_count

        if features is not None:
            untracked_count = len(features.untracked_features)
            total += untracked_count
            info += untracked_count

        return IntelligenceSummary(
            total_findings=total,
            critical_count=critical,
            warning_count=warning,
            info_count=info,
        )

    def _rank_top_issues(
        self,
        hardcoded: HardcodedScanResult | None,
        dependencies: DependencyReport | None,
        freshness: FreshnessReport | None,
        features: FeatureInventory | None,
    ) -> list[dict[str, Any]]:
        """Collect and prioritize issues. Returns sorted list."""
        issues: list[dict[str, Any]] = []

        # Critical vulnerabilities (priority 0)
        if dependencies is not None:
            for eco in dependencies.ecosystems:
                for v in eco.vulnerabilities:
                    if v.severity in ("critical", "high"):
                        issues.append({
                            "priority": _ISSUE_PRIORITY["critical_vuln"],
                            "category": "vulnerability",
                            "severity": v.severity,
                            "title": v.title,
                            "package": v.package_name,
                            "advisory_id": v.advisory_id,
                            "fixed_in": v.fixed_in,
                        })

        # Hardcoded critical findings (priority 1)
        if hardcoded is not None:
            for f in hardcoded.findings:
                if f.severity == "critical":
                    issues.append({
                        "priority": _ISSUE_PRIORITY["hardcoded_critical"],
                        "category": "hardcoded",
                        "severity": "critical",
                        "title": f"Hardcoded {f.category} in {f.file_path}:{f.line_number}",
                        "matched_text": f.matched_text,
                        "suggestion": f.suggestion,
                    })

        # Stale files (priority 2)
        if freshness is not None:
            for sf in freshness.stale_files:
                issues.append({
                    "priority": _ISSUE_PRIORITY["stale_file"],
                    "category": "freshness",
                    "severity": "warning",
                    "title": f"Stale file: {sf}",
                })

        # Outdated major dependencies (priority 3)
        if dependencies is not None:
            for eco in dependencies.ecosystems:
                for dep in eco.outdated:
                    if dep.update_severity == "major":
                        issues.append({
                            "priority": _ISSUE_PRIORITY["outdated_major_dep"],
                            "category": "dependency",
                            "severity": "warning",
                            "title": f"{dep.name} {dep.current_version} -> {dep.latest_version}",
                            "ecosystem": dep.ecosystem,
                        })

        # Untracked features (priority 4)
        if features is not None:
            for uf in features.untracked_features:
                issues.append({
                    "priority": _ISSUE_PRIORITY["untracked_feature"],
                    "category": "feature",
                    "severity": "info",
                    "title": f"Untracked: {uf.feature.name} ({uf.reason})",
                    "file_path": uf.feature.file_path,
                })

        # Sort by priority (ascending), then by severity
        severity_order = {"critical": 0, "high": 1, "warning": 2, "medium": 3, "info": 4}
        issues.sort(key=lambda i: (i["priority"], severity_order.get(i.get("severity", "info"), 5)))

        return issues[:10]

    def _save_to_cache(self, report: IntelligenceReport) -> None:
        """Persist report to cache."""
        data = {
            "project_path": report.project_path,
            "generated_at": report.generated_at,
            "overall_score": report.overall_score,
            "grade": report.grade,
            "hardcoded": report.hardcoded,
            "dependencies": report.dependencies,
            "integrations": report.integrations,
            "freshness": report.freshness,
            "features": report.features,
            "summary": asdict(report.summary),
            "top_issues": report.top_issues,
            "scan_duration_ms": report.scan_duration_ms,
            "scans_completed": report.scans_completed,
            "scans_failed": report.scans_failed,
        }
        self._cache.save(fingerprint=report.generated_at, data=data)

    def _report_from_cache(self, data: dict[str, Any]) -> IntelligenceReport | None:
        """Reconstruct an IntelligenceReport from cached data."""
        if not isinstance(data, dict):
            return None
        try:
            summary_data = data.get("summary", {})
            summary = IntelligenceSummary(
                total_findings=summary_data.get("total_findings", 0),
                critical_count=summary_data.get("critical_count", 0),
                warning_count=summary_data.get("warning_count", 0),
                info_count=summary_data.get("info_count", 0),
            )
            return IntelligenceReport(
                project_path=data.get("project_path", ""),
                generated_at=data.get("generated_at", ""),
                overall_score=data.get("overall_score", 0.0),
                grade=data.get("grade", "F"),
                hardcoded=data.get("hardcoded"),
                dependencies=data.get("dependencies"),
                integrations=data.get("integrations"),
                freshness=data.get("freshness"),
                features=data.get("features"),
                summary=summary,
                top_issues=data.get("top_issues", []),
                scan_duration_ms=data.get("scan_duration_ms", 0.0),
                scans_completed=data.get("scans_completed", 0),
                scans_failed=data.get("scans_failed", 0),
            )
        except (TypeError, KeyError):
            logger.exception("Failed to reconstruct report from cache")
            return None
