"""Readiness scanner for Claude Code projects.

This module scans projects and generates a readiness score (0-100) indicating
how well-prepared the project is for Claude Code development.

It checks for:
- Essential artifacts (ROADMAP.md, CLAUDE.md, README.md)
- Git setup and configuration
- Dependency management
- Documentation quality
- Test infrastructure
- Security practices
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol

from .git_utils import is_git_repo


class CheckSeverity(Enum):
    """Severity level for readiness checks."""

    CRITICAL = "critical"  # Must have for Claude Code
    IMPORTANT = "important"  # Strongly recommended
    NICE_TO_HAVE = "nice_to_have"  # Optional but helpful


@dataclass
class ReadinessCheck:
    """A single readiness check result."""

    name: str
    category: str
    passed: bool
    severity: CheckSeverity
    weight: float  # Contribution to overall score (0-1)
    message: str
    remediation: str | None = None  # How to fix if failed
    details: dict[str, any] = field(default_factory=dict)

    # Educational context (for user decision-making)
    what_is_it: str = ""  # Brief explanation
    why_need_it: str = ""  # Benefits/reasoning
    recommended_for: str = "All projects"  # Who should have this
    can_auto_generate: bool = False  # Can bootstrap create this
    complexity: str = "Easy"  # Easy, Medium, Hard
    example: str | None = None  # Example of what this looks like


@dataclass
class ReadinessReport:
    """Complete readiness assessment for a project."""

    score: float  # 0-100
    checks: list[ReadinessCheck]
    project_path: Path
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    critical_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        """Project is ready if score >= 70 and no critical issues."""
        return self.score >= 70.0 and len(self.critical_issues) == 0


class CheckFunction(Protocol):
    """Protocol for check functions."""

    def __call__(self, project_path: Path) -> ReadinessCheck:
        """Run a check and return result."""
        ...


class ReadinessScanner:
    """Scans projects for Claude Code readiness."""

    def __init__(self, project_path: Path):
        self.project_path = project_path.resolve()

        if not self.project_path.exists():
            raise ValueError(f"Project path does not exist: {self.project_path}")

    def scan(self) -> ReadinessReport:
        """Run all readiness checks and generate report."""
        checks: list[ReadinessCheck] = []

        # Run all checks
        checks.append(self._check_git_initialized())
        checks.append(self._check_readme_exists())
        checks.append(self._check_roadmap_exists())
        checks.append(self._check_claude_md_exists())
        checks.append(self._check_gitignore_exists())
        checks.append(self._check_dependencies_declared())
        checks.append(self._check_license_exists())
        checks.append(self._check_architecture_docs())
        checks.append(self._check_test_structure())
        checks.append(self._check_ci_hints())
        checks.append(self._check_no_secrets())
        checks.append(self._check_git_clean())

        # Calculate weighted score
        total_weight = sum(check.weight for check in checks)
        earned_weight = sum(check.weight for check in checks if check.passed)
        score = (earned_weight / total_weight) * 100 if total_weight > 0 else 0

        # Collect critical issues and warnings
        critical_issues = []
        warnings = []
        for check in checks:
            if not check.passed:
                if check.severity == CheckSeverity.CRITICAL:
                    critical_issues.append(f"{check.name}: {check.message}")
                elif check.severity == CheckSeverity.IMPORTANT:
                    warnings.append(f"{check.name}: {check.message}")

        report = ReadinessReport(
            score=score,
            checks=checks,
            project_path=self.project_path,
            total_checks=len(checks),
            passed_checks=sum(1 for c in checks if c.passed),
            failed_checks=sum(1 for c in checks if not c.passed),
            critical_issues=critical_issues,
            warnings=warnings,
        )

        return report

    def _check_git_initialized(self) -> ReadinessCheck:
        """Check if Git repository is initialized."""
        passed = is_git_repo(self.project_path)

        return ReadinessCheck(
            name="Git Repository",
            category="version_control",
            passed=passed,
            severity=CheckSeverity.CRITICAL,
            weight=0.15,
            message="Git repository initialized" if passed else "No Git repository found",
            remediation="Run: git init" if not passed else None,
            what_is_it="Version control system that tracks your code changes over time",
            why_need_it="Lets Claude Code see what changed, create commits, and safely revert if needed. Essential for tracking AI-generated changes.",
            recommended_for="All projects",
            can_auto_generate=True,
            complexity="Easy",
        )

    def _check_readme_exists(self) -> ReadinessCheck:
        """Check if README exists."""
        readme_files = ["README.md", "README.rst", "README.txt", "README"]
        found = any((self.project_path / name).exists() for name in readme_files)

        return ReadinessCheck(
            name="README",
            category="documentation",
            passed=found,
            severity=CheckSeverity.IMPORTANT,
            weight=0.10,
            message="README file exists" if found else "No README file found",
            remediation="Create README.md explaining the project" if not found else None,
        )

    def _check_roadmap_exists(self) -> ReadinessCheck:
        """Check if ROADMAP.md exists."""
        roadmap_path = self.project_path / ".claude" / "planning" / "ROADMAP.md"
        passed = roadmap_path.exists()

        return ReadinessCheck(
            name="ROADMAP.md",
            category="planning",
            passed=passed,
            severity=CheckSeverity.CRITICAL,
            weight=0.20,
            message="ROADMAP.md exists" if passed else "ROADMAP.md not found",
            remediation="Run bootstrap to generate ROADMAP.md" if not passed else None,
            details={"path": str(roadmap_path)},
        )

    def _check_claude_md_exists(self) -> ReadinessCheck:
        """Check if CLAUDE.md exists."""
        claude_md_path = self.project_path / "CLAUDE.md"
        passed = claude_md_path.exists()

        return ReadinessCheck(
            name="CLAUDE.md",
            category="documentation",
            passed=passed,
            severity=CheckSeverity.CRITICAL,
            weight=0.20,
            message="CLAUDE.md exists" if passed else "CLAUDE.md not found",
            remediation="Run bootstrap to generate CLAUDE.md" if not passed else None,
            details={"path": str(claude_md_path)},
        )

    def _check_gitignore_exists(self) -> ReadinessCheck:
        """Check if .gitignore exists and is not empty."""
        gitignore_path = self.project_path / ".gitignore"
        exists = gitignore_path.exists()
        non_empty = exists and gitignore_path.stat().st_size > 0

        return ReadinessCheck(
            name=".gitignore",
            category="version_control",
            passed=non_empty,
            severity=CheckSeverity.IMPORTANT,
            weight=0.08,
            message=".gitignore configured" if non_empty else ".gitignore missing or empty",
            remediation="Run bootstrap to generate .gitignore" if not non_empty else None,
        )

    def _check_dependencies_declared(self) -> ReadinessCheck:
        """Check if dependencies are declared (package.json, requirements.txt, etc.)."""
        dependency_files = [
            "package.json",
            "requirements.txt",
            "Pipfile",
            "pyproject.toml",
            "Cargo.toml",
            "go.mod",
            "Gemfile",
            "pom.xml",
            "build.gradle",
        ]

        found = any((self.project_path / name).exists() for name in dependency_files)
        found_files = [name for name in dependency_files if (self.project_path / name).exists()]

        return ReadinessCheck(
            name="Dependencies",
            category="project_structure",
            passed=found,
            severity=CheckSeverity.IMPORTANT,
            weight=0.10,
            message=f"Dependencies declared in {', '.join(found_files)}" if found else "No dependency manifest found",
            remediation="Create package.json, requirements.txt, or appropriate dependency file" if not found else None,
            details={"files": found_files},
        )

    def _check_license_exists(self) -> ReadinessCheck:
        """Check if LICENSE file exists."""
        license_files = ["LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"]
        found = any((self.project_path / name).exists() for name in license_files)

        return ReadinessCheck(
            name="License",
            category="legal",
            passed=found,
            severity=CheckSeverity.NICE_TO_HAVE,
            weight=0.03,
            message="License file exists" if found else "No license file found",
            remediation="Add LICENSE file (MIT, Apache 2.0, etc.)" if not found else None,
        )

    def _check_architecture_docs(self) -> ReadinessCheck:
        """Check if architecture documentation exists."""
        arch_paths = [
            self.project_path / "docs" / "ARCHITECTURE.md",
            self.project_path / "ARCHITECTURE.md",
            self.project_path / "docs" / "architecture.md",
        ]

        found = any(path.exists() for path in arch_paths)

        return ReadinessCheck(
            name="Architecture Docs",
            category="documentation",
            passed=found,
            severity=CheckSeverity.NICE_TO_HAVE,
            weight=0.05,
            message="Architecture documentation exists" if found else "No architecture docs found",
            remediation="Run bootstrap with architecture docs enabled" if not found else None,
        )

    def _check_test_structure(self) -> ReadinessCheck:
        """Check if test directory structure exists."""
        test_dirs = ["tests", "test", "__tests__", "spec"]
        test_files = [
            "test_*.py",
            "*_test.py",
            "*.test.js",
            "*.test.ts",
            "*.spec.js",
            "*.spec.ts",
        ]

        # Check for test directories
        has_test_dir = any((self.project_path / dir_name).is_dir() for dir_name in test_dirs)

        # Check for test files in root or common locations
        has_test_files = False
        for pattern in test_files:
            if list(self.project_path.glob(pattern)) or list(self.project_path.glob(f"**/{pattern}")):
                has_test_files = True
                break

        passed = has_test_dir or has_test_files

        return ReadinessCheck(
            name="Test Infrastructure",
            category="testing",
            passed=passed,
            severity=CheckSeverity.IMPORTANT,
            weight=0.07,
            message="Test structure exists" if passed else "No test directory or files found",
            remediation="Create tests/ directory and add test files" if not passed else None,
        )

    def _check_ci_hints(self) -> ReadinessCheck:
        """Check for CI/CD configuration hints."""
        ci_files = [
            ".github/workflows",
            ".gitlab-ci.yml",
            ".circleci/config.yml",
            "Jenkinsfile",
            ".travis.yml",
            "azure-pipelines.yml",
        ]

        found = any((self.project_path / name).exists() for name in ci_files)

        return ReadinessCheck(
            name="CI/CD",
            category="automation",
            passed=found,
            severity=CheckSeverity.NICE_TO_HAVE,
            weight=0.02,
            message="CI/CD configuration found" if found else "No CI/CD configuration",
            remediation="Consider adding GitHub Actions or similar CI/CD" if not found else None,
        )

    def _check_no_secrets(self) -> ReadinessCheck:
        """Check for common secret patterns (basic scan)."""
        # This is a lightweight check - full scan would use secrets_scanner.py
        env_files = [".env", ".env.local", ".env.production"]
        exposed_secrets = []

        for env_file in env_files:
            path = self.project_path / env_file
            if path.exists():
                # Check if .env is properly ignored
                gitignore_path = self.project_path / ".gitignore"
                if gitignore_path.exists():
                    gitignore_content = gitignore_path.read_text()
                    if env_file not in gitignore_content:
                        exposed_secrets.append(env_file)

        passed = len(exposed_secrets) == 0

        return ReadinessCheck(
            name="Secret Protection",
            category="security",
            passed=passed,
            severity=CheckSeverity.CRITICAL,
            weight=0.10,
            message="No exposed secrets detected" if passed else f"Potential secret exposure: {', '.join(exposed_secrets)}",
            remediation=f"Add {', '.join(exposed_secrets)} to .gitignore" if not passed else None,
            details={"exposed_files": exposed_secrets},
        )

    def _check_git_clean(self) -> ReadinessCheck:
        """Check if git working directory is clean."""
        if not is_git_repo(self.project_path):
            # Skip if not a git repo
            return ReadinessCheck(
                name="Git Status",
                category="version_control",
                passed=True,
                severity=CheckSeverity.NICE_TO_HAVE,
                weight=0.00,  # Don't count if not a git repo
                message="Not a git repository",
            )

        try:
            import subprocess

            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=5,
            )

            is_clean = len(result.stdout.strip()) == 0

            return ReadinessCheck(
                name="Git Status",
                category="version_control",
                passed=is_clean,
                severity=CheckSeverity.NICE_TO_HAVE,
                weight=0.00,  # Informational only, doesn't affect score
                message="Working directory clean" if is_clean else "Uncommitted changes detected",
                remediation="Commit or stash changes before proceeding" if not is_clean else None,
            )

        except Exception:
            # If git check fails, pass silently
            return ReadinessCheck(
                name="Git Status",
                category="version_control",
                passed=True,
                severity=CheckSeverity.NICE_TO_HAVE,
                weight=0.00,
                message="Unable to check git status",
            )


def scan_project_readiness(project_path: Path) -> ReadinessReport:
    """Convenience function to scan project readiness.

    Args:
        project_path: Path to project to scan

    Returns:
        ReadinessReport with score and recommendations
    """
    scanner = ReadinessScanner(project_path)
    return scanner.scan()
