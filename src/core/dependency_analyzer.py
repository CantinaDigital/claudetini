"""Dependency health analysis for project ecosystems.

Detects package ecosystems (npm, pip, cargo, go), checks for outdated
dependencies and known vulnerabilities, and produces a health score.
"""

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class DependencyInfo:
    """A single dependency with version information."""

    name: str
    current_version: str
    latest_version: str | None
    update_severity: Literal["major", "minor", "patch"] | None
    ecosystem: str
    is_dev: bool


@dataclass(frozen=True)
class VulnerabilityInfo:
    """A known vulnerability affecting a dependency."""

    package_name: str
    severity: Literal["critical", "high", "medium", "low"]
    advisory_id: str
    title: str
    fixed_in: str | None


@dataclass
class EcosystemReport:
    """Analysis results for a single package ecosystem."""

    ecosystem: str
    manifest_path: Path
    outdated: list[DependencyInfo] = field(default_factory=list)
    vulnerabilities: list[VulnerabilityInfo] = field(default_factory=list)


@dataclass
class DependencyReport:
    """Full dependency health report across all ecosystems."""

    ecosystems: list[EcosystemReport] = field(default_factory=list)
    health_score: int = 100


class DependencyAnalyzer:
    """Analyze dependency health across detected ecosystems."""

    # Manifest files that identify each ecosystem
    ECOSYSTEM_MANIFESTS: dict[str, list[str]] = {
        "npm": ["package.json"],
        "pip": ["pyproject.toml", "requirements.txt"],
        "cargo": ["Cargo.toml"],
        "go": ["go.mod"],
    }

    def __init__(self, project_path: Path):
        self.project_path = project_path.resolve()

    def analyze(self) -> DependencyReport:
        """Run dependency analysis across all detected ecosystems.

        Returns:
            DependencyReport with per-ecosystem results and overall health score.
        """
        ecosystems: list[EcosystemReport] = []

        for ecosystem, manifests in self.ECOSYSTEM_MANIFESTS.items():
            for manifest_name in manifests:
                manifest_path = self.project_path / manifest_name
                if not manifest_path.exists():
                    continue

                if ecosystem == "npm":
                    report = self._analyze_npm(manifest_path)
                elif ecosystem == "pip":
                    report = self._analyze_pip(manifest_path)
                elif ecosystem == "cargo":
                    report = self._analyze_cargo(manifest_path)
                elif ecosystem == "go":
                    report = self._analyze_go(manifest_path)
                else:
                    continue

                if report:
                    ecosystems.append(report)

        health_score = self._compute_health_score(ecosystems)

        return DependencyReport(ecosystems=ecosystems, health_score=health_score)

    # ── npm ──────────────────────────────────────────────────────────

    def _analyze_npm(self, manifest_path: Path) -> EcosystemReport:
        """Analyze npm ecosystem from package.json."""
        report = EcosystemReport(ecosystem="npm", manifest_path=manifest_path)

        # Parse package.json for dependency list
        deps, dev_deps = self._parse_package_json(manifest_path)

        # Check for outdated packages
        outdated_data = self._run_json_command(
            ["npm", "outdated", "--json"],
            cwd=manifest_path.parent,
        )
        if outdated_data and isinstance(outdated_data, dict):
            for pkg_name, info in outdated_data.items():
                if not isinstance(info, dict):
                    continue
                current = info.get("current", "")
                latest = info.get("latest", "")
                if current and latest and current != latest:
                    severity = self._semver_severity(current, latest)
                    report.outdated.append(
                        DependencyInfo(
                            name=pkg_name,
                            current_version=current,
                            latest_version=latest,
                            update_severity=severity,
                            ecosystem="npm",
                            is_dev=pkg_name in dev_deps,
                        )
                    )

        # Check for vulnerabilities
        audit_data = self._run_json_command(
            ["npm", "audit", "--json"],
            cwd=manifest_path.parent,
        )
        if audit_data and isinstance(audit_data, dict):
            vulns = audit_data.get("vulnerabilities", {})
            if isinstance(vulns, dict):
                for pkg_name, vuln_info in vulns.items():
                    if not isinstance(vuln_info, dict):
                        continue
                    severity_raw = vuln_info.get("severity", "medium")
                    severity = self._normalize_severity(severity_raw)
                    via = vuln_info.get("via", [])
                    title = ""
                    advisory_id = ""
                    fixed_in = vuln_info.get("fixAvailable", {})
                    fixed_version = None
                    if isinstance(fixed_in, dict):
                        fixed_version = fixed_in.get("version")

                    # Extract advisory info from via entries
                    if isinstance(via, list):
                        for entry in via:
                            if isinstance(entry, dict):
                                title = entry.get("title", title)
                                advisory_id = str(entry.get("url", advisory_id))
                                break

                    report.vulnerabilities.append(
                        VulnerabilityInfo(
                            package_name=pkg_name,
                            severity=severity,
                            advisory_id=advisory_id,
                            title=title or f"Vulnerability in {pkg_name}",
                            fixed_in=fixed_version,
                        )
                    )

        return report

    def _parse_package_json(self, path: Path) -> tuple[dict[str, str], dict[str, str]]:
        """Parse package.json and return (dependencies, devDependencies)."""
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}, {}

        deps = data.get("dependencies", {})
        dev_deps = data.get("devDependencies", {})
        return deps if isinstance(deps, dict) else {}, dev_deps if isinstance(dev_deps, dict) else {}

    # ── pip ──────────────────────────────────────────────────────────

    def _analyze_pip(self, manifest_path: Path) -> EcosystemReport:
        """Analyze pip ecosystem from pyproject.toml or requirements.txt."""
        report = EcosystemReport(ecosystem="pip", manifest_path=manifest_path)

        # Parse declared dependencies
        declared: dict[str, str] = {}
        if manifest_path.name == "pyproject.toml":
            declared = self._parse_pyproject_deps(manifest_path)
        elif manifest_path.name == "requirements.txt":
            declared = self._parse_requirements_txt(manifest_path)

        # Check for outdated packages
        outdated_data = self._run_json_command(
            ["pip", "list", "--outdated", "--format=json"],
            cwd=manifest_path.parent,
        )
        if outdated_data and isinstance(outdated_data, list):
            declared_lower = {k.lower().replace("-", "_"): k for k in declared}
            for entry in outdated_data:
                if not isinstance(entry, dict):
                    continue
                pkg_name = entry.get("name", "")
                pkg_key = pkg_name.lower().replace("-", "_")
                # Only report packages that are declared in the manifest
                if pkg_key not in declared_lower:
                    continue
                current = entry.get("version", "")
                latest = entry.get("latest_version", "")
                if current and latest and current != latest:
                    severity = self._semver_severity(current, latest)
                    report.outdated.append(
                        DependencyInfo(
                            name=pkg_name,
                            current_version=current,
                            latest_version=latest,
                            update_severity=severity,
                            ecosystem="pip",
                            is_dev=False,
                        )
                    )

        # Optionally check pip-audit for vulnerabilities
        audit_data = self._run_json_command(
            ["pip-audit", "--format=json"],
            cwd=manifest_path.parent,
        )
        if audit_data and isinstance(audit_data, dict):
            dependencies = audit_data.get("dependencies", [])
            if isinstance(dependencies, list):
                for dep in dependencies:
                    if not isinstance(dep, dict):
                        continue
                    vulns = dep.get("vulns", [])
                    if not vulns:
                        continue
                    pkg_name = dep.get("name", "")
                    for vuln in vulns:
                        if not isinstance(vuln, dict):
                            continue
                        report.vulnerabilities.append(
                            VulnerabilityInfo(
                                package_name=pkg_name,
                                severity=self._normalize_severity(vuln.get("severity", "medium")),
                                advisory_id=vuln.get("id", ""),
                                title=vuln.get("description", f"Vulnerability in {pkg_name}"),
                                fixed_in=vuln.get("fix_versions", [None])[0] if vuln.get("fix_versions") else None,
                            )
                        )

        return report

    def _parse_pyproject_deps(self, path: Path) -> dict[str, str]:
        """Extract dependency names from pyproject.toml (simple parsing)."""
        deps: dict[str, str] = {}
        try:
            content = path.read_text()
        except OSError:
            return deps

        # Match lines like: "package>=1.0.0" in dependencies array
        in_deps = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped in ("dependencies = [", 'dependencies= ['):
                in_deps = True
                continue
            if re.match(r"^\[.*?dependencies\]", stripped, re.IGNORECASE):
                in_deps = True
                continue
            if in_deps:
                if stripped == "]" or (stripped.startswith("[") and not stripped.startswith('["')):
                    in_deps = False
                    continue
                # Extract package name from requirement specifier
                match = re.match(r"""['"]([a-zA-Z0-9_.-]+)\s*([><=!~].+)?['"]""", stripped.rstrip(","))
                if match:
                    pkg_name = match.group(1)
                    version_spec = match.group(2) or ""
                    deps[pkg_name] = version_spec.strip()

        return deps

    def _parse_requirements_txt(self, path: Path) -> dict[str, str]:
        """Extract dependency names from requirements.txt."""
        deps: dict[str, str] = {}
        try:
            content = path.read_text()
        except OSError:
            return deps

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            match = re.match(r"([a-zA-Z0-9_.-]+)\s*([><=!~].+)?", line)
            if match:
                deps[match.group(1)] = (match.group(2) or "").strip()

        return deps

    # ── cargo / go (manifest parsing only) ───────────────────────────

    def _analyze_cargo(self, manifest_path: Path) -> EcosystemReport:
        """Parse Cargo.toml for dependency inventory (no subprocess calls)."""
        report = EcosystemReport(ecosystem="cargo", manifest_path=manifest_path)
        try:
            content = manifest_path.read_text()
        except OSError:
            return report

        in_deps = False
        in_dev_deps = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped == "[dependencies]":
                in_deps = True
                in_dev_deps = False
                continue
            if stripped == "[dev-dependencies]":
                in_deps = False
                in_dev_deps = True
                continue
            if stripped.startswith("[") and stripped != "[dependencies]" and stripped != "[dev-dependencies]":
                in_deps = False
                in_dev_deps = False
                continue

            if in_deps or in_dev_deps:
                match = re.match(r'(\S+)\s*=\s*"([^"]*)"', stripped)
                if match:
                    report.outdated.append(
                        DependencyInfo(
                            name=match.group(1),
                            current_version=match.group(2),
                            latest_version=None,
                            update_severity=None,
                            ecosystem="cargo",
                            is_dev=in_dev_deps,
                        )
                    )
                # Handle table-style: package = { version = "x.y.z", ... }
                table_match = re.match(r'(\S+)\s*=\s*\{.*version\s*=\s*"([^"]*)"', stripped)
                if table_match and not match:
                    report.outdated.append(
                        DependencyInfo(
                            name=table_match.group(1),
                            current_version=table_match.group(2),
                            latest_version=None,
                            update_severity=None,
                            ecosystem="cargo",
                            is_dev=in_dev_deps,
                        )
                    )

        return report

    def _analyze_go(self, manifest_path: Path) -> EcosystemReport:
        """Parse go.mod for dependency inventory (no subprocess calls)."""
        report = EcosystemReport(ecosystem="go", manifest_path=manifest_path)
        try:
            content = manifest_path.read_text()
        except OSError:
            return report

        in_require = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped == "require (":
                in_require = True
                continue
            if stripped == ")":
                in_require = False
                continue

            if in_require:
                match = re.match(r"(\S+)\s+(v\S+)", stripped)
                if match:
                    report.outdated.append(
                        DependencyInfo(
                            name=match.group(1),
                            current_version=match.group(2),
                            latest_version=None,
                            update_severity=None,
                            ecosystem="go",
                            is_dev=False,
                        )
                    )
            else:
                # Single-line require
                req_match = re.match(r"require\s+(\S+)\s+(v\S+)", stripped)
                if req_match:
                    report.outdated.append(
                        DependencyInfo(
                            name=req_match.group(1),
                            current_version=req_match.group(2),
                            latest_version=None,
                            update_severity=None,
                            ecosystem="go",
                            is_dev=False,
                        )
                    )

        return report

    # ── Helpers ──────────────────────────────────────────────────────

    def _run_json_command(
        self,
        cmd: list[str],
        cwd: Path | None = None,
    ) -> dict | list | None:
        """Run a command that outputs JSON, returning parsed result or None."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=cwd or self.project_path,
            )
            # npm audit / npm outdated return non-zero when issues exist,
            # but still produce valid JSON on stdout
            output = result.stdout.strip()
            if output:
                return json.loads(output)
        except subprocess.TimeoutExpired:
            return None
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            return None
        except OSError:
            return None
        return None

    @staticmethod
    def _semver_severity(current: str, latest: str) -> Literal["major", "minor", "patch"] | None:
        """Compare two semver strings and return update severity."""
        cur_parts = _parse_semver(current)
        lat_parts = _parse_semver(latest)

        if cur_parts is None or lat_parts is None:
            return None

        cur_major, cur_minor, _cur_patch = cur_parts
        lat_major, lat_minor, _lat_patch = lat_parts

        if lat_major > cur_major:
            return "major"
        if lat_minor > cur_minor:
            return "minor"
        return "patch"

    @staticmethod
    def _normalize_severity(raw: str) -> Literal["critical", "high", "medium", "low"]:
        """Normalize a severity string to one of the four levels."""
        raw_lower = raw.lower().strip() if raw else ""
        if raw_lower in ("critical", "crit"):
            return "critical"
        if raw_lower in ("high", "h"):
            return "high"
        if raw_lower in ("low", "l"):
            return "low"
        return "medium"

    def _compute_health_score(self, ecosystems: list[EcosystemReport]) -> int:
        """Compute health score: start at 100, deduct for issues.

        Deductions:
        - -5 per major outdated dependency
        - -1 per minor outdated dependency
        - -15 per critical vulnerability
        - -3 per other vulnerability
        """
        score = 100

        for eco in ecosystems:
            for dep in eco.outdated:
                if dep.update_severity == "major":
                    score -= 5
                elif dep.update_severity == "minor":
                    score -= 1

            for vuln in eco.vulnerabilities:
                if vuln.severity == "critical":
                    score -= 15
                else:
                    score -= 3

        return max(0, score)


def _parse_semver(version: str) -> tuple[int, int, int] | None:
    """Parse a semver string into (major, minor, patch). Returns None on failure."""
    # Strip leading 'v' or '^' or '~'
    cleaned = version.lstrip("v^~")
    match = re.match(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", cleaned)
    if not match:
        return None
    major = int(match.group(1))
    minor = int(match.group(2)) if match.group(2) else 0
    patch = int(match.group(3)) if match.group(3) else 0
    return major, minor, patch
