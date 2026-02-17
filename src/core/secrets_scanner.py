"""Security scanner for detecting secrets and sensitive data before commits.

CRITICAL: This module prevents accidental exposure of credentials, API keys,
private keys, and other sensitive data in public repositories.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SecretMatch:
    """A detected secret or sensitive data."""

    file_path: Path
    line_number: int
    secret_type: str
    matched_text: str  # Redacted version for display
    severity: str  # "critical", "high", "medium", "low"
    description: str

    def __str__(self) -> str:
        return f"{self.severity.upper()}: {self.secret_type} in {self.file_path}:{self.line_number}"


@dataclass
class ScanResult:
    """Result of a secrets scan."""

    secrets_found: list[SecretMatch] = field(default_factory=list)
    files_scanned: int = 0
    skipped_files: list[str] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        return any(s.severity == "critical" for s in self.secrets_found)

    @property
    def has_high(self) -> bool:
        return any(s.severity == "high" for s in self.secrets_found)

    @property
    def should_block_commit(self) -> bool:
        """Returns True if secrets are serious enough to block a commit."""
        return self.has_critical or self.has_high

    @property
    def is_clean(self) -> bool:
        return len(self.secrets_found) == 0


class SecretsScanner:
    """Scanner for detecting secrets and sensitive data in code.

    This scanner looks for:
    - API keys (AWS, Google, GitHub, Stripe, etc.)
    - Private keys (RSA, SSH, PGP)
    - Passwords and tokens in code
    - .env files and other credential files
    - Database connection strings with credentials
    - JWT tokens
    - OAuth tokens
    """

    # Patterns for detecting secrets
    # Each tuple: (name, pattern, severity, description)
    SECRET_PATTERNS = [
        # AWS
        (
            "AWS Access Key ID",
            r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}",
            "critical",
            "AWS Access Key ID detected",
        ),
        (
            "AWS Secret Access Key",
            r"(?i)aws[_\-\.]?secret[_\-\.]?access[_\-\.]?key['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}",
            "critical",
            "AWS Secret Access Key detected",
        ),
        # Google
        (
            "Google API Key",
            r"AIza[0-9A-Za-z\-_]{35}",
            "critical",
            "Google API Key detected",
        ),
        (
            "Google OAuth Token",
            r"ya29\.[0-9A-Za-z\-_]+",
            "critical",
            "Google OAuth token detected",
        ),
        # GitHub
        (
            "GitHub Token",
            r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}",
            "critical",
            "GitHub personal access token detected",
        ),
        (
            "GitHub OAuth",
            r"github[_\-\.]?oauth[_\-\.]?token['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9_]{40}",
            "critical",
            "GitHub OAuth token detected",
        ),
        # Stripe
        (
            "Stripe API Key",
            r"(?:sk|pk)_(?:live|test)_[A-Za-z0-9]{24,}",
            "critical",
            "Stripe API key detected",
        ),
        # Slack
        (
            "Slack Token",
            r"xox[baprs]-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*",
            "critical",
            "Slack token detected",
        ),
        (
            "Slack Webhook",
            r"https://hooks\.slack\.com/services/T[A-Z0-9]{8}/B[A-Z0-9]{8,}/[A-Za-z0-9]{24}",
            "high",
            "Slack webhook URL detected",
        ),
        # Private Keys
        (
            "RSA Private Key",
            r"-----BEGIN RSA PRIVATE KEY-----",
            "critical",
            "RSA private key detected",
        ),
        (
            "SSH Private Key",
            r"-----BEGIN (?:OPENSSH|DSA|EC|PGP) PRIVATE KEY-----",
            "critical",
            "SSH/DSA/EC/PGP private key detected",
        ),
        (
            "PEM Certificate",
            r"-----BEGIN (?:CERTIFICATE|PRIVATE KEY)-----",
            "high",
            "PEM certificate or private key detected",
        ),
        # Database
        (
            "Database URL with Password",
            r"(?i)(?:postgres|mysql|mongodb|redis)://[^:]+:[^@]+@[^\s]+",
            "critical",
            "Database connection string with credentials detected",
        ),
        # Generic secrets
        (
            "Generic API Key",
            r"(?i)(?:api[_\-\.]?key|apikey)['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}['\"]?",
            "high",
            "Generic API key pattern detected",
        ),
        (
            "Generic Secret",
            r"(?i)(?:secret|password|passwd|pwd)['\"]?\s*[:=]\s*['\"]?[^\s'\"]{8,}['\"]?",
            "high",
            "Password or secret pattern detected",
        ),
        (
            "Generic Token",
            r"(?i)(?:auth[_\-\.]?token|access[_\-\.]?token|bearer)['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{20,}['\"]?",
            "high",
            "Authentication token pattern detected",
        ),
        # JWT
        (
            "JWT Token",
            r"eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*",
            "high",
            "JWT token detected",
        ),
        # Anthropic/OpenAI
        (
            "Anthropic API Key",
            r"sk-ant-[A-Za-z0-9_-]{40,}",
            "critical",
            "Anthropic API key detected",
        ),
        (
            "OpenAI API Key",
            r"sk-[A-Za-z0-9]{48}",
            "critical",
            "OpenAI API key detected",
        ),
        # Heroku
        (
            "Heroku API Key",
            r"(?i)heroku[_\-\.]?api[_\-\.]?key['\"]?\s*[:=]\s*['\"]?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "critical",
            "Heroku API key detected",
        ),
        # NPM
        (
            "NPM Token",
            r"(?i)npm[_\-\.]?token['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9_-]{36}",
            "critical",
            "NPM token detected",
        ),
    ]

    # Files that should NEVER be committed
    DANGEROUS_FILES = [
        ".env",
        ".env.local",
        ".env.development",
        ".env.production",
        ".env.test",
        ".env.*",
        "credentials.json",
        "credentials.yaml",
        "credentials.yml",
        "secrets.json",
        "secrets.yaml",
        "secrets.yml",
        "*.pem",
        "*.key",
        "*.p12",
        "*.pfx",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        ".htpasswd",
        ".pgpass",
        ".netrc",
        ".npmrc",  # May contain tokens
        ".pypirc",  # May contain tokens
        "aws_credentials",
        "gcloud_credentials.json",
        "service_account.json",
        "firebase_credentials.json",
        "keyfile.json",
    ]

    # Extensions to scan
    SCANNABLE_EXTENSIONS = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb", ".php",
        ".cs", ".c", ".cpp", ".h", ".hpp", ".rs", ".swift", ".kt", ".scala",
        ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
        ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".config",
        ".xml", ".properties", ".env", ".txt", ".md", ".sql",
    }

    # Directories to skip
    SKIP_DIRECTORIES = {
        ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
        ".tox", ".nox", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        "dist", "build", ".eggs", "*.egg-info", ".coverage",
        "tests", "test", "testing", "fixtures",  # Test directories have fake secrets
    }

    # Files to skip (contain patterns, not actual secrets)
    SKIP_FILES = {
        "secrets_scanner.py",  # This file contains detection patterns
    }

    def __init__(self, project_path: Path):
        self.project_path = project_path.resolve()

    def scan(self, staged_only: bool = False) -> ScanResult:
        """Scan the project for secrets.

        Args:
            staged_only: If True, only scan files staged for commit
        """
        result = ScanResult()

        if staged_only:
            files_to_scan = self._get_staged_files()
        else:
            files_to_scan = self._get_all_files()

        for file_path in files_to_scan:
            # Check if it's a dangerous file by name
            dangerous_match = self._check_dangerous_filename(file_path)
            if dangerous_match:
                result.secrets_found.append(dangerous_match)
                continue

            # Check file extension
            if file_path.suffix.lower() not in self.SCANNABLE_EXTENSIONS:
                result.skipped_files.append(str(file_path))
                continue

            # Scan file content
            secrets = self._scan_file(file_path)
            result.secrets_found.extend(secrets)
            result.files_scanned += 1

        return result

    def _get_staged_files(self) -> list[Path]:
        """Get files staged for commit."""
        import subprocess

        try:
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return [
                    self.project_path / f
                    for f in result.stdout.strip().split("\n")
                    if f
                ]
        except Exception:
            pass

        return []

    def _get_all_files(self) -> list[Path]:
        """Get all files in the project (respecting skip directories and files)."""
        files = []

        for item in self.project_path.rglob("*"):
            # Skip directories in SKIP_DIRECTORIES
            if any(skip in item.parts for skip in self.SKIP_DIRECTORIES):
                continue

            # Skip specific files (e.g., this scanner file)
            if item.name in self.SKIP_FILES:
                continue

            if item.is_file():
                files.append(item)

        return files

    def _check_dangerous_filename(self, file_path: Path) -> SecretMatch | None:
        """Check if a file is dangerous by its name."""
        name = file_path.name.lower()

        for dangerous in self.DANGEROUS_FILES:
            if dangerous.startswith("*"):
                # Wildcard pattern
                if name.endswith(dangerous[1:]):
                    return SecretMatch(
                        file_path=file_path,
                        line_number=0,
                        secret_type="Sensitive File",
                        matched_text=f"[BLOCKED: {name}]",
                        severity="critical",
                        description=f"Sensitive file type should not be committed: {name}",
                    )
            elif dangerous.endswith("*"):
                # Prefix pattern
                if name.startswith(dangerous[:-1]):
                    return SecretMatch(
                        file_path=file_path,
                        line_number=0,
                        secret_type="Sensitive File",
                        matched_text=f"[BLOCKED: {name}]",
                        severity="critical",
                        description=f"Sensitive file type should not be committed: {name}",
                    )
            elif name == dangerous:
                return SecretMatch(
                    file_path=file_path,
                    line_number=0,
                    secret_type="Sensitive File",
                    matched_text=f"[BLOCKED: {name}]",
                    severity="critical",
                    description=f"Sensitive file should not be committed: {name}",
                )

        return None

    def _scan_file(self, file_path: Path) -> list[SecretMatch]:
        """Scan a single file for secrets."""
        secrets = []

        try:
            content = file_path.read_text(errors="ignore")
            lines = content.split("\n")

            for line_num, line in enumerate(lines, start=1):
                # Skip empty lines and comments
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                    continue

                for name, pattern, severity, description in self.SECRET_PATTERNS:
                    matches = re.finditer(pattern, line)
                    for match in matches:
                        # Redact the actual secret for safety
                        matched_text = match.group()
                        redacted = self._redact_secret(matched_text)

                        secrets.append(SecretMatch(
                            file_path=file_path,
                            line_number=line_num,
                            secret_type=name,
                            matched_text=redacted,
                            severity=severity,
                            description=description,
                        ))

        except Exception:
            pass  # Skip files that can't be read

        return secrets

    def _redact_secret(self, secret: str) -> str:
        """Redact a secret for safe display."""
        if len(secret) <= 8:
            return "*" * len(secret)
        return secret[:4] + "*" * (len(secret) - 8) + secret[-4:]

    def format_report(self, result: ScanResult) -> str:
        """Format a scan result as a human-readable report."""
        lines = []

        if result.is_clean:
            lines.append("✅ No secrets detected")
            lines.append(f"   Scanned {result.files_scanned} files")
            return "\n".join(lines)

        lines.append("🚨 SECRETS DETECTED - COMMIT BLOCKED")
        lines.append("")

        # Group by severity
        by_severity = {"critical": [], "high": [], "medium": [], "low": []}
        for secret in result.secrets_found:
            by_severity[secret.severity].append(secret)

        for severity in ["critical", "high", "medium", "low"]:
            secrets = by_severity[severity]
            if not secrets:
                continue

            icon = "🔴" if severity == "critical" else "🟠" if severity == "high" else "🟡"
            lines.append(f"{icon} {severity.upper()} ({len(secrets)} found):")

            for secret in secrets:
                rel_path = secret.file_path.relative_to(self.project_path)
                lines.append(f"   • {rel_path}:{secret.line_number}")
                lines.append(f"     {secret.secret_type}: {secret.matched_text}")
                lines.append(f"     {secret.description}")
            lines.append("")

        if result.should_block_commit:
            lines.append("❌ COMMIT SHOULD BE BLOCKED")
            lines.append("   Remove or secure these secrets before committing.")
            lines.append("")
            lines.append("   Recommended actions:")
            lines.append("   1. Remove secrets from code")
            lines.append("   2. Use environment variables instead")
            lines.append("   3. Add sensitive files to .gitignore")
            lines.append("   4. If already committed, rotate the credentials immediately")

        return "\n".join(lines)


def scan_before_commit(project_path: Path) -> tuple[bool, str]:
    """Convenience function to scan before commit.

    Returns:
        Tuple of (should_allow_commit, report_message)
    """
    scanner = SecretsScanner(project_path)
    result = scanner.scan(staged_only=True)
    report = scanner.format_report(result)

    return not result.should_block_commit, report
