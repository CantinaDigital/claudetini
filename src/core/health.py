"""Project health checks."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from .gate_results import GateResultStore
from .roadmap import RoadmapParser
from .runtime import project_id_for_path


class HealthLevel(Enum):
    """Health status level."""
    GOOD = "good"        # ✅
    WARNING = "warning"  # ⚠️
    BAD = "bad"          # ❌
    UNKNOWN = "unknown"  # ?


@dataclass
class HealthCheck:
    """Result of a single health check."""

    category: str
    name: str
    level: HealthLevel
    message: str
    remediation: str | None = None

    @property
    def is_good(self) -> bool:
        return self.level == HealthLevel.GOOD

    @property
    def needs_attention(self) -> bool:
        return self.level in (HealthLevel.WARNING, HealthLevel.BAD)


@dataclass
class HealthStatus:
    """Overall health status for a project."""

    checks: list[HealthCheck] = field(default_factory=list)

    @property
    def overall_score(self) -> int:
        """Calculate overall health score (0-100)."""
        if not self.checks:
            return 0

        good_count = sum(1 for c in self.checks if c.level == HealthLevel.GOOD)
        return int((good_count / len(self.checks)) * 100)

    @property
    def good_checks(self) -> list[HealthCheck]:
        return [c for c in self.checks if c.level == HealthLevel.GOOD]

    @property
    def warning_checks(self) -> list[HealthCheck]:
        return [c for c in self.checks if c.level == HealthLevel.WARNING]

    @property
    def bad_checks(self) -> list[HealthCheck]:
        return [c for c in self.checks if c.level == HealthLevel.BAD]


class HealthChecker:
    """Project health checker."""

    def __init__(self, project_path: Path):
        self.path = project_path.resolve()

    def run_all_checks(self) -> HealthStatus:
        """Run all health checks and return status."""
        status = HealthStatus()

        # Security check is first and most important
        status.checks.append(self._check_secrets())
        status.checks.append(self._check_roadmap())
        status.checks.append(self._check_readme())
        status.checks.append(self._check_claude_md())
        status.checks.append(self._check_gitignore())
        status.checks.append(self._check_tests())
        status.checks.append(self._check_quality_gates())
        status.checks.append(self._check_ci())

        return status

    def _check_secrets(self) -> HealthCheck:
        """CRITICAL: Check for exposed secrets, API keys, and credentials."""
        from .secrets_scanner import SecretsScanner

        scanner = SecretsScanner(self.path)
        result = scanner.scan(staged_only=True)

        if result.is_clean:
            return HealthCheck(
                category="Security",
                name="Secrets Scan",
                level=HealthLevel.GOOD,
                message=f"No secrets detected in {result.files_scanned} files",
            )

        if result.has_critical:
            return HealthCheck(
                category="Security",
                name="Secrets Scan",
                level=HealthLevel.BAD,
                message=f"CRITICAL: {len(result.secrets_found)} secrets/credentials detected!",
                remediation="Remove secrets immediately. Use environment variables instead. "
                           "If already committed, rotate all exposed credentials.",
            )

        if result.has_high:
            return HealthCheck(
                category="Security",
                name="Secrets Scan",
                level=HealthLevel.BAD,
                message=f"HIGH: {len(result.secrets_found)} potential secrets detected",
                remediation="Review and remove any real credentials. Use .env files (gitignored) "
                           "or environment variables for sensitive data.",
            )

        return HealthCheck(
            category="Security",
            name="Secrets Scan",
            level=HealthLevel.WARNING,
            message=f"{len(result.secrets_found)} potential secrets detected (review recommended)",
            remediation="Review flagged items to ensure no real credentials are exposed.",
        )

    def _check_roadmap(self) -> HealthCheck:
        """Check if project has a roadmap."""
        roadmap = RoadmapParser.parse(self.path)
        roadmap_path = self.path / "ROADMAP.md"
        if roadmap_path.exists():
            try:
                days_stale = (datetime.now() - datetime.fromtimestamp(roadmap_path.stat().st_mtime)).days
            except OSError:
                days_stale = 0
        else:
            days_stale = 0

        if roadmap:
            if roadmap.total_items == 0:
                return HealthCheck(
                    category="Roadmap",
                    name="Roadmap",
                    level=HealthLevel.WARNING,
                    message="Roadmap found but has no checkbox items",
                    remediation="Add milestone checklists to track progress.",
                )
            if days_stale > 28:
                return HealthCheck(
                    category="Roadmap",
                    name="Roadmap",
                    level=HealthLevel.WARNING,
                    message=f"Roadmap appears stale ({days_stale} days since update)",
                    remediation="Review roadmap and refresh milestone statuses.",
                )
            return HealthCheck(
                category="Roadmap",
                name="Roadmap",
                level=HealthLevel.GOOD,
                message=f"{roadmap.completed_items}/{roadmap.total_items} roadmap items completed",
            )

        return HealthCheck(
            category="Roadmap",
            name="Roadmap",
            level=HealthLevel.BAD,
            message="No roadmap found",
            remediation="Create ROADMAP.md with project milestones",
        )

    def _check_readme(self) -> HealthCheck:
        """Check if project has a README."""
        readme_names = ["README.md", "README.rst", "README.txt", "README"]

        for name in readme_names:
            readme = self.path / name
            if readme.exists():
                content = readme.read_text()
                text = content.strip()
                if len(text) > 500:
                    section_hits = 0
                    for keyword in ("install", "usage", "getting started", "overview"):
                        if re.search(rf"^#+\s+.*{re.escape(keyword)}", content, re.IGNORECASE | re.MULTILINE):
                            section_hits += 1
                    if section_hits >= 2:
                        return HealthCheck(
                            category="Documentation",
                            name="README",
                            level=HealthLevel.GOOD,
                            message="README found with strong coverage",
                        )
                    return HealthCheck(
                        category="Documentation",
                        name="README",
                        level=HealthLevel.WARNING,
                        message="README exists but is missing key sections",
                        remediation="Add install and usage sections.",
                    )
                return HealthCheck(
                    category="Documentation",
                    name="README",
                    level=HealthLevel.WARNING,
                    message="README exists but is minimal",
                    remediation="Add project description, setup instructions, usage examples",
                )

        return HealthCheck(
            category="Documentation",
            name="README",
            level=HealthLevel.BAD,
            message="No README found",
            remediation="Create README.md with project documentation",
        )

    def _check_claude_md(self) -> HealthCheck:
        """Check if project has CLAUDE.md."""
        claude_md = self.path / "CLAUDE.md"

        if claude_md.exists():
            content = claude_md.read_text()
            text = content.strip()
            if len(text) > 200:
                has_conventions = any(
                    keyword in text.lower()
                    for keyword in ("convention", "style", "test", "lint", "pattern")
                )
                if has_conventions:
                    is_managed = "claudetini:managed" in text.lower() or "claudetini:managed" in text.lower()
                    status = "auto-managed by Claudetini" if is_managed else "with project instructions"
                    return HealthCheck(
                        category="Claude Code",
                        name="CLAUDE.md",
                        level=HealthLevel.GOOD,
                        message=f"CLAUDE.md found {status}",
                    )
                return HealthCheck(
                    category="Claude Code",
                    name="CLAUDE.md",
                    level=HealthLevel.WARNING,
                    message="CLAUDE.md exists but lacks conventions",
                    remediation="Add conventions for style, tests, and architecture.",
                )
            return HealthCheck(
                category="Claude Code",
                name="CLAUDE.md",
                level=HealthLevel.WARNING,
                message="CLAUDE.md exists but is minimal",
                remediation="Add project conventions, architecture notes, and coding guidelines",
            )

        return HealthCheck(
            category="Claude Code",
            name="CLAUDE.md",
            level=HealthLevel.WARNING,
            message="No CLAUDE.md found",
            remediation="Create CLAUDE.md with project instructions for Claude Code",
        )

    def _check_gitignore(self) -> HealthCheck:
        """Check if project has .gitignore."""
        gitignore = self.path / ".gitignore"
        env_file = self.path / ".env"

        if gitignore.exists():
            content = gitignore.read_text()
            lines = [line for line in content.split("\n") if line.strip() and not line.startswith("#")]
            has_env_rule = any(".env" in line for line in lines)
            if len(lines) >= 5 and (not env_file.exists() or has_env_rule):
                return HealthCheck(
                    category="Git",
                    name=".gitignore",
                    level=HealthLevel.GOOD,
                    message=f".gitignore found with {len(lines)} rules",
                )
            if env_file.exists() and not has_env_rule:
                return HealthCheck(
                    category="Git",
                    name=".gitignore",
                    level=HealthLevel.BAD,
                    message=".env exists but is not ignored",
                    remediation="Add `.env` to .gitignore to avoid leaking secrets.",
                )
            return HealthCheck(
                category="Git",
                name=".gitignore",
                level=HealthLevel.WARNING,
                message=".gitignore exists but is minimal",
                remediation="Add rules for IDE files, build artifacts, dependencies",
            )

        return HealthCheck(
            category="Git",
            name=".gitignore",
            level=HealthLevel.WARNING,
            message="No .gitignore found",
            remediation="Create .gitignore to exclude build artifacts and secrets",
        )

    def _check_tests(self) -> HealthCheck:
        """Check if project has tests."""
        test_indicators = [
            self.path / "tests",
            self.path / "test",
            self.path / "spec",
            self.path / "__tests__",
            self.path / "pytest.ini",
            self.path / "jest.config.js",
            self.path / "vitest.config.ts",
        ]
        test_runner_config = [
            self.path / "pyproject.toml",
            self.path / "package.json",
            self.path / "Makefile",
        ]

        for indicator in test_indicators:
            if indicator.exists():
                if indicator.is_dir():
                    # Check if directory has test files
                    test_files = list(indicator.glob("test_*.py")) + \
                                list(indicator.glob("*_test.py")) + \
                                list(indicator.glob("*.test.js")) + \
                                list(indicator.glob("*.test.ts")) + \
                                list(indicator.glob("*.spec.js")) + \
                                list(indicator.glob("*.spec.ts"))
                    if test_files:
                        return HealthCheck(
                            category="Testing",
                            name="Test Suite",
                            level=HealthLevel.GOOD,
                            message=f"Found {len(test_files)} test files in {indicator.name}/",
                        )
                    return HealthCheck(
                        category="Testing",
                        name="Test Suite",
                        level=HealthLevel.WARNING,
                        message="Test directory exists but no test files found",
                        remediation="Add test files to the tests directory",
                    )
                else:
                    config_state = any(path.exists() for path in test_runner_config)
                    return HealthCheck(
                        category="Testing",
                        name="Test Suite",
                        level=HealthLevel.GOOD if config_state else HealthLevel.WARNING,
                        message=f"Test configuration found: {indicator.name}",
                    )

        return HealthCheck(
            category="Testing",
            name="Test Suite",
            level=HealthLevel.BAD,
            message="No test suite found",
            remediation="Create tests/ directory and add tests for your code",
        )

    def _check_ci(self) -> HealthCheck:
        """Check if project has CI/CD configuration."""
        ci_indicators = [
            self.path / ".github" / "workflows",
            self.path / ".gitlab-ci.yml",
            self.path / ".circleci",
            self.path / "Jenkinsfile",
            self.path / ".travis.yml",
            self.path / "azure-pipelines.yml",
        ]

        for indicator in ci_indicators:
            if indicator.exists():
                if indicator.is_dir():
                    workflow_files = list(indicator.glob("*.yml")) + list(indicator.glob("*.yaml"))
                    if workflow_files:
                        has_tests = False
                        for workflow in workflow_files:
                            try:
                                text = workflow.read_text()
                            except OSError:
                                continue
                            if any(token in text for token in ("pytest", "npm test", "vitest", "ruff check")):
                                has_tests = True
                                break
                        return HealthCheck(
                            category="CI/CD",
                            name="CI Configuration",
                            level=HealthLevel.GOOD if has_tests else HealthLevel.WARNING,
                            message=(
                                f"Found {len(workflow_files)} CI workflow(s)"
                                if has_tests
                                else "CI config exists but no obvious test step"
                            ),
                            remediation=None if has_tests else "Add test steps to CI workflow.",
                        )
                else:
                    return HealthCheck(
                        category="CI/CD",
                        name="CI Configuration",
                        level=HealthLevel.GOOD,
                        message=f"CI configuration found: {indicator.name}",
                    )

        return HealthCheck(
            category="CI/CD",
            name="CI Configuration",
            level=HealthLevel.WARNING,
            message="No CI/CD configuration found",
            remediation="Add GitHub Actions or other CI workflow",
        )

    def _check_quality_gates(self) -> HealthCheck:
        """Check quality gate status from the latest gate run."""
        project_id = project_id_for_path(self.path)
        report = GateResultStore(project_id).load_latest()
        if not report:
            return HealthCheck(
                category="Quality",
                name="Quality Gates",
                level=HealthLevel.WARNING,
                message="No quality gate run found",
                remediation="Run quality gates from the Claudetini dashboard.",
            )

        failed = [gate for gate in report.gates if gate.status == "fail"]
        warned = [gate for gate in report.gates if gate.status == "warn"]
        if failed:
            gate_names = ", ".join(gate.name for gate in failed[:3])
            return HealthCheck(
                category="Quality",
                name="Quality Gates",
                level=HealthLevel.BAD,
                message=f"{len(failed)} failed gate(s): {gate_names}",
                remediation="Resolve failed gates to restore project quality.",
            )
        if warned:
            gate_names = ", ".join(gate.name for gate in warned[:3])
            return HealthCheck(
                category="Quality",
                name="Quality Gates",
                level=HealthLevel.WARNING,
                message=f"{len(warned)} warning gate(s): {gate_names}",
                remediation="Review warning-level gate findings.",
            )
        return HealthCheck(
            category="Quality",
            name="Quality Gates",
            level=HealthLevel.GOOD,
            message=f"Latest gate run passed ({len(report.gates)} gates)",
        )


@dataclass
class ScanResult:
    """Result of a health scan for UI compatibility."""

    passed: bool
    partial: bool = False
    detail: str = ""


class HealthScanner:
    """Simplified health scanner for UI components."""

    def __init__(self, project_path: Path):
        self.path = project_path.resolve()
        self._checker = HealthChecker(project_path)

    def scan_all(self) -> dict[str, ScanResult]:
        """Run all scans and return results keyed by category."""
        status = self._checker.run_all_checks()

        results = {}
        for check in status.checks:
            if check.level == HealthLevel.GOOD:
                results[check.category.lower()] = ScanResult(
                    passed=True,
                    partial=False,
                    detail=check.message,
                )
            elif check.level == HealthLevel.WARNING:
                results[check.category.lower()] = ScanResult(
                    passed=False,
                    partial=True,
                    detail=check.message,
                )
            else:
                results[check.category.lower()] = ScanResult(
                    passed=False,
                    partial=False,
                    detail=check.message,
                )

        return results
