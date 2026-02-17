"""Tests for the secrets scanner.

CRITICAL: This scanner prevents accidental exposure of credentials.
"""

import pytest
from pathlib import Path

from src.core.secrets_scanner import SecretsScanner, SecretMatch, ScanResult


class TestSecretsScanner:
    """Tests for SecretsScanner class."""

    @pytest.fixture
    def scanner(self, temp_dir):
        """Create a scanner for testing."""
        return SecretsScanner(temp_dir)

    def test_clean_project(self, temp_dir):
        """Test scanning a project with no secrets."""
        # Create a clean Python file
        (temp_dir / "app.py").write_text("""
def hello():
    return "Hello, World!"
""")

        scanner = SecretsScanner(temp_dir)
        result = scanner.scan()

        assert result.is_clean
        assert len(result.secrets_found) == 0

    def test_detect_aws_access_key(self, temp_dir):
        """Test detection of AWS access key."""
        (temp_dir / "config.py").write_text("""
AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
""")

        scanner = SecretsScanner(temp_dir)
        result = scanner.scan()

        assert not result.is_clean
        assert result.has_critical
        assert any("AWS" in s.secret_type for s in result.secrets_found)

    def test_detect_github_token(self, temp_dir):
        """Test detection of GitHub personal access token."""
        (temp_dir / "deploy.sh").write_text("""
#!/bin/bash
GITHUB_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
""")

        scanner = SecretsScanner(temp_dir)
        result = scanner.scan()

        assert not result.is_clean
        assert any("GitHub" in s.secret_type for s in result.secrets_found)

    def test_detect_private_key(self, temp_dir):
        """Test detection of RSA private key."""
        (temp_dir / "key.txt").write_text("""
-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z3VS5JJcds...
-----END RSA PRIVATE KEY-----
""")

        scanner = SecretsScanner(temp_dir)
        result = scanner.scan()

        assert not result.is_clean
        assert result.has_critical
        assert any("RSA" in s.secret_type or "Private Key" in s.secret_type
                   for s in result.secrets_found)

    def test_detect_env_file(self, temp_dir):
        """Test detection of .env file."""
        (temp_dir / ".env").write_text("""
DATABASE_URL=postgres://user:password@localhost/db
SECRET_KEY=supersecretkey123
""")

        scanner = SecretsScanner(temp_dir)
        result = scanner.scan()

        assert not result.is_clean
        assert result.has_critical
        assert any("Sensitive File" in s.secret_type for s in result.secrets_found)

    def test_detect_database_url_with_password(self, temp_dir):
        """Test detection of database connection string with password."""
        (temp_dir / "settings.py").write_text("""
DATABASE_URL = "postgres://admin:secretpassword@db.example.com:5432/myapp"
""")

        scanner = SecretsScanner(temp_dir)
        result = scanner.scan()

        assert not result.is_clean
        assert any("Database" in s.secret_type for s in result.secrets_found)

    def test_detect_jwt_token(self, temp_dir):
        """Test detection of JWT token."""
        (temp_dir / "auth.py").write_text("""
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
""")

        scanner = SecretsScanner(temp_dir)
        result = scanner.scan()

        assert not result.is_clean
        assert any("JWT" in s.secret_type for s in result.secrets_found)

    def test_detect_openai_key(self, temp_dir):
        """Test detection of OpenAI API key."""
        (temp_dir / "llm.py").write_text("""
OPENAI_API_KEY = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
""")

        scanner = SecretsScanner(temp_dir)
        result = scanner.scan()

        assert not result.is_clean
        assert any("OpenAI" in s.secret_type for s in result.secrets_found)

    def test_detect_anthropic_key(self, temp_dir):
        """Test detection of Anthropic API key."""
        (temp_dir / "claude.py").write_text("""
ANTHROPIC_API_KEY = "sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
""")

        scanner = SecretsScanner(temp_dir)
        result = scanner.scan()

        assert not result.is_clean
        assert any("Anthropic" in s.secret_type for s in result.secrets_found)

    def test_skip_gitignored_patterns(self, temp_dir):
        """Test that common ignored directories are skipped."""
        # Create node_modules with a "secret"
        node_modules = temp_dir / "node_modules" / "some-package"
        node_modules.mkdir(parents=True)
        (node_modules / "config.js").write_text('API_KEY = "sk-test123456789012345678901234567890123456"')

        # Create a clean source file
        (temp_dir / "app.py").write_text("print('hello')")

        scanner = SecretsScanner(temp_dir)
        result = scanner.scan()

        # Should not find the secret in node_modules
        assert result.is_clean

    def test_should_block_commit(self, temp_dir):
        """Test that critical secrets block commits."""
        (temp_dir / "config.py").write_text("""
STRIPE_KEY = "pk_test_FAKEFAKEFAKEFAKEFAKEFAKE"
""")

        scanner = SecretsScanner(temp_dir)
        result = scanner.scan()

        assert result.should_block_commit

    def test_redact_secret(self, temp_dir):
        """Test that secrets are redacted in output."""
        scanner = SecretsScanner(temp_dir)

        # Test redaction
        redacted = scanner._redact_secret("sk_live_1234567890abcdef")
        assert "sk_l" in redacted
        assert "cdef" in redacted
        assert "1234567890ab" not in redacted

    def test_format_report(self, temp_dir):
        """Test report formatting."""
        (temp_dir / "secrets.py").write_text("""
API_KEY = "AKIAIOSFODNN7EXAMPLE"
""")

        scanner = SecretsScanner(temp_dir)
        result = scanner.scan()
        report = scanner.format_report(result)

        assert "SECRETS DETECTED" in report
        assert "CRITICAL" in report
        assert "COMMIT SHOULD BE BLOCKED" in report


class TestScanResult:
    """Tests for ScanResult class."""

    def test_is_clean_when_empty(self):
        """Test is_clean with no secrets."""
        result = ScanResult()
        assert result.is_clean

    def test_has_critical(self):
        """Test has_critical detection."""
        result = ScanResult(
            secrets_found=[
                SecretMatch(
                    file_path=Path("test.py"),
                    line_number=1,
                    secret_type="AWS Key",
                    matched_text="****",
                    severity="critical",
                    description="AWS key",
                )
            ]
        )
        assert result.has_critical
        assert result.should_block_commit

    def test_has_high(self):
        """Test has_high detection."""
        result = ScanResult(
            secrets_found=[
                SecretMatch(
                    file_path=Path("test.py"),
                    line_number=1,
                    secret_type="Generic Secret",
                    matched_text="****",
                    severity="high",
                    description="Secret",
                )
            ]
        )
        assert result.has_high
        assert result.should_block_commit

    def test_medium_does_not_block(self):
        """Test that medium severity doesn't block commit."""
        result = ScanResult(
            secrets_found=[
                SecretMatch(
                    file_path=Path("test.py"),
                    line_number=1,
                    secret_type="Possible Secret",
                    matched_text="****",
                    severity="medium",
                    description="Possible secret",
                )
            ]
        )
        assert not result.should_block_commit
