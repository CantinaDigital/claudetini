"""Scanner for detecting hardcoded values, environment config issues, and documentation drift.

Detects hardcoded URLs, IPs, TODO/FIXME markers, placeholder data, magic numbers,
absolute paths, undocumented env var references, and stale documentation references.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class HardcodedFinding:
    """A detected hardcoded value or code quality issue."""

    file_path: Path
    line_number: int
    category: str  # url, ip_address, port, todo_marker, placeholder, absolute_path, magic_number, env_reference, doc_drift
    severity: str  # "critical", "warning", "info"
    matched_text: str
    suggestion: str

    def __str__(self) -> str:
        return f"{self.severity.upper()}: [{self.category}] {self.file_path}:{self.line_number} — {self.matched_text}"


@dataclass
class HardcodedScanResult:
    """Result of a hardcoded values scan."""

    findings: list[HardcodedFinding] = field(default_factory=list)
    scanned_file_count: int = 0

    @property
    def is_clean(self) -> bool:
        return len(self.findings) == 0

    @property
    def has_critical(self) -> bool:
        return any(f.severity == "critical" for f in self.findings)

    def by_category(self) -> dict[str, list[HardcodedFinding]]:
        """Group findings by category."""
        grouped: dict[str, list[HardcodedFinding]] = {}
        for finding in self.findings:
            grouped.setdefault(finding.category, []).append(finding)
        return grouped

    def by_severity(self) -> dict[str, list[HardcodedFinding]]:
        """Group findings by severity."""
        grouped: dict[str, list[HardcodedFinding]] = {}
        for finding in self.findings:
            grouped.setdefault(finding.severity, []).append(finding)
        return grouped


# Production-like path segments — placeholders here are CRITICAL
_PRODUCTION_PATH_SEGMENTS = {"src", "lib", "app", "pkg", "internal", "cmd"}

# Test-like path segments — placeholders here are INFO
_TEST_PATH_SEGMENTS = {
    "test", "tests", "testing", "spec", "specs",
    "fixtures", "fixture", "__tests__", "__mocks__",
    "mock", "mocks", "testdata", "test_data",
}


def _is_production_path(file_path: Path) -> bool:
    """Check if a file path looks like production code."""
    parts = {p.lower() for p in file_path.parts}
    if parts & _TEST_PATH_SEGMENTS:
        return False
    return bool(parts & _PRODUCTION_PATH_SEGMENTS)


def _is_test_path(file_path: Path) -> bool:
    """Check if a file path looks like test code."""
    parts = {p.lower() for p in file_path.parts}
    return bool(parts & _TEST_PATH_SEGMENTS)


class HardcodedScanner:
    """Scanner for detecting hardcoded values and code quality issues.

    Detects:
    - Hardcoded URLs, IPv4 addresses, ports
    - TODO/FIXME markers
    - Placeholder data (test@example.com, lorem ipsum, nil UUIDs, foo/bar)
    - Absolute file paths
    - Magic numbers
    - Undocumented environment variable references
    - Documentation drift (stale paths, commands, function names)
    """

    # Extensions to scan (duplicated from secrets_scanner — intentionally not imported)
    SCANNABLE_EXTENSIONS = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb", ".php",
        ".cs", ".c", ".cpp", ".h", ".hpp", ".rs", ".swift", ".kt", ".scala",
        ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
        ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".config",
        ".xml", ".properties", ".env", ".txt", ".md", ".sql",
    }

    # Directories to skip (duplicated from secrets_scanner — intentionally not imported)
    SKIP_DIRECTORIES = {
        ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
        ".tox", ".nox", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        "dist", "build", ".eggs", "*.egg-info", ".coverage",
    }

    # Files to skip (e.g., this scanner itself)
    SKIP_FILES = {
        "hardcoded_scanner.py",
    }

    # ── Detection patterns ──────────────────────────────────────────────
    # Each tuple: (category, compiled_regex, base_severity, suggestion)
    # base_severity may be overridden for placeholders depending on path context.

    _PATTERNS: list[tuple[str, re.Pattern[str], str, str]] = [
        # URLs (http/https, but not localhost which is common in dev)
        (
            "url",
            re.compile(
                r"""https?://(?!localhost\b|127\.0\.0\.1\b|0\.0\.0\.0\b)[a-zA-Z0-9\-._~:/?#\[\]@!$&'()*+,;=%]{8,}""",
            ),
            "info",
            "Consider extracting URL to a configuration variable",
        ),
        # IPv4 addresses (skip 127.0.0.1 and 0.0.0.0 — common dev addresses)
        (
            "ip_address",
            re.compile(
                r"\b(?!127\.0\.0\.1\b|0\.0\.0\.0\b)(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b",
            ),
            "warning",
            "Consider extracting IP address to a configuration variable",
        ),
        # Port numbers in common patterns (e.g., :8080, PORT=3000)
        (
            "port",
            re.compile(
                r"(?i)(?:port\s*[:=]\s*|:\s*)(\d{4,5})\b",
            ),
            "info",
            "Consider making port number configurable",
        ),
        # TODO / FIXME / HACK / XXX markers
        (
            "todo_marker",
            re.compile(
                r"\b(TODO|FIXME|HACK|XXX|BUG|OPTIMIZE)\b\s*:?\s*(.*)",
                re.IGNORECASE,
            ),
            "warning",
            "Resolve or track this marker in your issue tracker",
        ),
        # Placeholder emails
        (
            "placeholder",
            re.compile(
                r"\b[\w.+-]+@example\.\w+\b",
                re.IGNORECASE,
            ),
            "warning",  # overridden by path context
            "Replace placeholder email with a real value or config variable",
        ),
        # Lorem ipsum
        (
            "placeholder",
            re.compile(
                r"\blorem\s+ipsum\b",
                re.IGNORECASE,
            ),
            "warning",
            "Replace lorem ipsum with real content",
        ),
        # Nil / zero UUIDs
        (
            "placeholder",
            re.compile(
                r"\b00000000-0000-0000-0000-000000000000\b",
            ),
            "warning",
            "Replace nil UUID with a generated value or config variable",
        ),
        # foo / bar / baz placeholder names in strings
        (
            "placeholder",
            re.compile(
                r"""(?:['"])(?:foo|bar|baz|foobar|foobaz|qux|quux)(?:['"])""",
                re.IGNORECASE,
            ),
            "warning",
            "Replace placeholder name with a meaningful value",
        ),
        # Absolute Unix paths (skip common system paths used legitimately)
        (
            "absolute_path",
            re.compile(
                r"""(?<![a-zA-Z0-9_])(/(?:Users|home|tmp|var|opt|etc)/[^\s'"`,;)}\]>]{3,})""",
            ),
            "warning",
            "Replace absolute path with a relative path or config variable",
        ),
        # Windows absolute paths
        (
            "absolute_path",
            re.compile(
                r"""[A-Z]:\\(?:Users|Documents|Program Files)[^\s'"`,;)}\]>]{3,}""",
            ),
            "warning",
            "Replace absolute path with a relative path or config variable",
        ),
        # Magic numbers (integers > 1 used in assignments or comparisons, skip 0/1/2
        # and common screen sizes, HTTP codes, etc.)
        (
            "magic_number",
            re.compile(
                r"(?<![a-zA-Z_\d.])(?:==|!=|<=?|>=?|=)\s*(\d{3,})\b",
            ),
            "info",
            "Consider extracting magic number to a named constant",
        ),
    ]

    # ── Environment variable patterns ───────────────────────────────────
    _ENV_PATTERNS: list[re.Pattern[str]] = [
        # Python: os.environ["X"], os.environ.get("X"), os.getenv("X")
        re.compile(r"""os\.(?:environ\s*\[?\s*['"]([\w]+)['"]\]?|environ\.get\s*\(\s*['"]([\w]+)['"]|getenv\s*\(\s*['"]([\w]+)['"])"""),
        # JavaScript/TypeScript: process.env.X
        re.compile(r"""process\.env\.([\w]+)"""),
        # Generic: ${VAR_NAME} in config files
        re.compile(r"""\$\{([\w]+)\}"""),
    ]

    def __init__(self, project_path: Path):
        self.project_path = project_path.resolve()

    def scan(self) -> HardcodedScanResult:
        """Scan the project for hardcoded values, env config issues, and doc drift."""
        result = HardcodedScanResult()

        files = self._get_all_files()
        env_example_vars = self._parse_env_example()

        for file_path in files:
            if file_path.suffix.lower() not in self.SCANNABLE_EXTENSIONS:
                continue

            findings = self._scan_file(file_path, env_example_vars)
            result.findings.extend(findings)
            result.scanned_file_count += 1

        # Documentation drift detection
        drift_findings = self._scan_documentation_drift()
        result.findings.extend(drift_findings)

        return result

    # ── File enumeration ────────────────────────────────────────────────

    def _get_all_files(self) -> list[Path]:
        """Get all scannable files, respecting skip directories."""
        files: list[Path] = []
        for item in self.project_path.rglob("*"):
            if any(skip in item.parts for skip in self.SKIP_DIRECTORIES):
                continue
            if item.name in self.SKIP_FILES:
                continue
            if item.is_file():
                files.append(item)
        return files

    # ── Core file scanning ──────────────────────────────────────────────

    def _scan_file(
        self,
        file_path: Path,
        env_example_vars: set[str],
    ) -> list[HardcodedFinding]:
        """Scan a single file for hardcoded values and env references."""
        findings: list[HardcodedFinding] = []

        try:
            content = file_path.read_text(errors="ignore")
        except Exception:
            return findings

        lines = content.split("\n")

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            # Core pattern detection
            for category, pattern, base_severity, suggestion in self._PATTERNS:
                for match in pattern.finditer(line):
                    severity = self._resolve_severity(
                        category, base_severity, file_path,
                    )
                    matched_text = match.group().strip()
                    # Truncate very long matches for readability
                    if len(matched_text) > 120:
                        matched_text = matched_text[:117] + "..."
                    findings.append(HardcodedFinding(
                        file_path=file_path,
                        line_number=line_num,
                        category=category,
                        severity=severity,
                        matched_text=matched_text,
                        suggestion=suggestion,
                    ))

            # Environment variable reference detection
            for env_pattern in self._ENV_PATTERNS:
                for match in env_pattern.finditer(line):
                    # Extract the variable name from whichever group matched
                    var_name = next(
                        (g for g in match.groups() if g is not None), None,
                    )
                    if var_name is None:
                        continue

                    # Skip common non-project env vars
                    if var_name in {
                        "PATH", "HOME", "USER", "SHELL", "TERM", "LANG",
                        "PWD", "OLDPWD", "HOSTNAME", "LOGNAME", "TMPDIR",
                        "EDITOR", "VISUAL", "PAGER",
                    }:
                        continue

                    if var_name not in env_example_vars:
                        findings.append(HardcodedFinding(
                            file_path=file_path,
                            line_number=line_num,
                            category="env_reference",
                            severity="warning",
                            matched_text=var_name,
                            suggestion="Document in .env.example",
                        ))

        return findings

    # ── Severity resolution ─────────────────────────────────────────────

    def _resolve_severity(
        self,
        category: str,
        base_severity: str,
        file_path: Path,
    ) -> str:
        """Resolve severity based on category and file location.

        Placeholders in production paths are CRITICAL.
        Placeholders in test paths are INFO.
        """
        if category == "placeholder":
            if _is_production_path(file_path):
                return "critical"
            if _is_test_path(file_path):
                return "info"
        return base_severity

    # ── Environment config audit ────────────────────────────────────────

    def _parse_env_example(self) -> set[str]:
        """Parse .env.example from project root for documented env variable names."""
        env_example = self.project_path / ".env.example"
        documented_vars: set[str] = set()

        if not env_example.is_file():
            return documented_vars

        try:
            content = env_example.read_text(errors="ignore")
        except Exception:
            return documented_vars

        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Match KEY=value or KEY= (no value)
            match = re.match(r"^([A-Za-z_]\w*)\s*=", line)
            if match:
                documented_vars.add(match.group(1))

        return documented_vars

    # ── Documentation drift detection ───────────────────────────────────

    def _scan_documentation_drift(self) -> list[HardcodedFinding]:
        """Scan documentation files for references to items that no longer exist."""
        findings: list[HardcodedFinding] = []

        doc_files = [
            self.project_path / "README.md",
            self.project_path / "CLAUDE.md",
        ]

        for doc_path in doc_files:
            if not doc_path.is_file():
                continue
            try:
                content = doc_path.read_text(errors="ignore")
            except Exception:
                continue

            lines = content.split("\n")
            for line_num, line in enumerate(lines, start=1):
                findings.extend(
                    self._check_line_for_drift(doc_path, line_num, line),
                )

        return findings

    def _check_line_for_drift(
        self,
        doc_path: Path,
        line_num: int,
        line: str,
    ) -> list[HardcodedFinding]:
        """Check a single documentation line for drift indicators."""
        findings: list[HardcodedFinding] = []

        # Detect file path references (e.g., `src/core/foo.py` or src/core/foo.py)
        path_pattern = re.compile(
            r"""(?:`|^|\s)((?:\.?\.?/)?(?:[\w\-./]+\.(?:py|js|ts|tsx|jsx|json|yaml|yml|toml|md|rs|go|sh|sql|css|html))\b)""",
        )
        for match in path_pattern.finditer(line):
            ref_path_str = match.group(1)
            ref_path = self.project_path / ref_path_str
            if not ref_path.exists():
                findings.append(HardcodedFinding(
                    file_path=doc_path,
                    line_number=line_num,
                    category="doc_drift",
                    severity="warning",
                    matched_text=ref_path_str,
                    suggestion="Update documentation or restore missing item",
                ))

        # Detect npm/yarn/pnpm command references (e.g., `npm run build`)
        cmd_pattern = re.compile(
            r"""(?:`|^|\s)((?:npm|yarn|pnpm)\s+run\s+([\w:.\-]+))""",
        )
        for match in cmd_pattern.finditer(line):
            script_name = match.group(2)
            if not self._script_exists(script_name):
                findings.append(HardcodedFinding(
                    file_path=doc_path,
                    line_number=line_num,
                    category="doc_drift",
                    severity="warning",
                    matched_text=match.group(1),
                    suggestion="Update documentation or restore missing item",
                ))

        return findings

    def _script_exists(self, script_name: str) -> bool:
        """Check if an npm script exists in any package.json in the project."""
        import json

        # Check root package.json
        package_files = [self.project_path / "package.json"]
        # Also check immediate subdirectories (monorepo)
        try:
            for child in self.project_path.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    pkg = child / "package.json"
                    if pkg.is_file():
                        package_files.append(pkg)
        except Exception:
            pass

        for pkg_path in package_files:
            if not pkg_path.is_file():
                continue
            try:
                data = json.loads(pkg_path.read_text(errors="ignore"))
                scripts = data.get("scripts", {})
                if script_name in scripts:
                    return True
            except Exception:
                continue

        return False
