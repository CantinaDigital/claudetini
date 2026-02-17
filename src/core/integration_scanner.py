"""Integration scanner for detecting API integrations, SDK imports, and internal routes.

Scans project files to identify external API calls, SDK imports, database connections,
and internal route definitions. Produces a structured report of all integration points
grouped by service.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

IntegrationType = Literal["external_api", "internal_route", "sdk_import", "database"]


@dataclass
class IntegrationPoint:
    """A single detected integration reference in the codebase."""

    service_name: str
    integration_type: IntegrationType
    file_path: str
    line_number: int
    matched_text: str
    endpoint_url: str | None = None
    http_method: str | None = None


@dataclass
class ServiceSummary:
    """Aggregated integration summary for a single service."""

    service_name: str
    count: int
    endpoints: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)


@dataclass
class IntegrationReport:
    """Complete integration scan results."""

    integrations: list[IntegrationPoint] = field(default_factory=list)
    services_detected: list[ServiceSummary] = field(default_factory=list)
    files_scanned: int = 0

    @property
    def total_integrations(self) -> int:
        return len(self.integrations)

    @property
    def external_api_count(self) -> int:
        return sum(1 for i in self.integrations if i.integration_type == "external_api")

    @property
    def internal_route_count(self) -> int:
        return sum(1 for i in self.integrations if i.integration_type == "internal_route")


# File extensions worth scanning for integrations
SCANNABLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb", ".php",
    ".cs", ".c", ".cpp", ".h", ".hpp", ".rs", ".swift", ".kt", ".scala",
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".config",
    ".xml", ".properties", ".env", ".txt", ".md", ".sql",
}

SKIP_DIRECTORIES = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".tox", ".nox", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", ".eggs", "*.egg-info", ".coverage",
}

# Known external service URL patterns: (regex_pattern, service_name)
KNOWN_SERVICE_PATTERNS: list[tuple[str, str]] = [
    (r"api\.stripe\.com", "Stripe"),
    (r"\.amazonaws\.com", "AWS"),
    (r"s3[\.\-][\w\-]*\.amazonaws\.com", "AWS S3"),
    (r"firebaseio\.com|firebase\.googleapis\.com|firebasestorage\.googleapis\.com", "Firebase"),
    (r"supabase\.co|supabase\.com", "Supabase"),
    (r"api\.twilio\.com", "Twilio"),
    (r"api\.sendgrid\.com", "SendGrid"),
    (r"api\.openai\.com", "OpenAI"),
    (r"api\.anthropic\.com", "Anthropic"),
    (r"slack\.com/api|hooks\.slack\.com", "Slack"),
    (r"sentry\.io|o\d+\.ingest\.sentry\.io", "Sentry"),
    (r"api\.datadoghq\.com|app\.datadoghq\.com", "Datadog"),
    (r"api\.mailgun\.net", "Mailgun"),
    (r"[\w\-]+\.auth0\.com", "Auth0"),
    (r"api\.github\.com", "GitHub API"),
    (r"api\.gitlab\.com|gitlab\.com/api", "GitLab API"),
    (r"graph\.microsoft\.com", "Microsoft Graph"),
    (r"googleapis\.com", "Google Cloud"),
    (r"api\.cloudflare\.com", "Cloudflare"),
    (r"api\.paypal\.com|paypal\.com/v\d", "PayPal"),
    (r"api\.shopify\.com", "Shopify"),
    (r"api\.intercom\.io", "Intercom"),
    (r"api\.hubspot\.com|api\.hubapi\.com", "HubSpot"),
    (r"api\.segment\.io|cdn\.segment\.com", "Segment"),
    (r"api\.mixpanel\.com", "Mixpanel"),
    (r"api\.pagerduty\.com", "PagerDuty"),
    (r"api\.heroku\.com", "Heroku"),
    (r"api\.vercel\.com", "Vercel"),
    (r"api\.netlify\.com", "Netlify"),
    (r"api\.digitalocean\.com", "DigitalOcean"),
]

# SDK import patterns: (regex_pattern, service_name)
SDK_IMPORT_PATTERNS: list[tuple[str, str]] = [
    # Python imports
    (r"^\s*import\s+stripe\b", "Stripe"),
    (r"^\s*from\s+stripe\b", "Stripe"),
    (r"^\s*import\s+boto3\b", "AWS"),
    (r"^\s*from\s+boto3\b", "AWS"),
    (r"^\s*import\s+botocore\b", "AWS"),
    (r"^\s*from\s+botocore\b", "AWS"),
    (r"^\s*import\s+firebase_admin\b", "Firebase"),
    (r"^\s*from\s+firebase_admin\b", "Firebase"),
    (r"^\s*from\s+supabase\b", "Supabase"),
    (r"^\s*import\s+supabase\b", "Supabase"),
    (r"^\s*from\s+twilio\b", "Twilio"),
    (r"^\s*import\s+twilio\b", "Twilio"),
    (r"^\s*import\s+sendgrid\b", "SendGrid"),
    (r"^\s*from\s+sendgrid\b", "SendGrid"),
    (r"^\s*import\s+openai\b", "OpenAI"),
    (r"^\s*from\s+openai\b", "OpenAI"),
    (r"^\s*import\s+anthropic\b", "Anthropic"),
    (r"^\s*from\s+anthropic\b", "Anthropic"),
    (r"^\s*from\s+slack_sdk\b", "Slack"),
    (r"^\s*import\s+slack_sdk\b", "Slack"),
    (r"^\s*import\s+sentry_sdk\b", "Sentry"),
    (r"^\s*from\s+sentry_sdk\b", "Sentry"),
    (r"^\s*from\s+google\.cloud\b", "Google Cloud"),
    (r"^\s*import\s+google\.cloud\b", "Google Cloud"),
    (r"^\s*from\s+auth0\b", "Auth0"),
    (r"^\s*import\s+auth0\b", "Auth0"),
    # JS/TS imports
    (r"""(?:import|require)\s*\(?\s*['"]stripe['"]""", "Stripe"),
    (r"""(?:import|require)\s*\(?\s*['"]@aws-sdk/""", "AWS"),
    (r"""(?:import|require)\s*\(?\s*['"]aws-sdk['"]""", "AWS"),
    (r"""(?:import|require)\s*\(?\s*['"]firebase""", "Firebase"),
    (r"""(?:import|require)\s*\(?\s*['"]@supabase/""", "Supabase"),
    (r"""(?:import|require)\s*\(?\s*['"]twilio['"]""", "Twilio"),
    (r"""(?:import|require)\s*\(?\s*['"]@sendgrid/""", "SendGrid"),
    (r"""(?:import|require)\s*\(?\s*['"]openai['"]""", "OpenAI"),
    (r"""(?:import|require)\s*\(?\s*['"]@anthropic-ai/""", "Anthropic"),
    (r"""(?:import|require)\s*\(?\s*['"]@slack/""", "Slack"),
    (r"""(?:import|require)\s*\(?\s*['"]@sentry/""", "Sentry"),
    (r"""(?:import|require)\s*\(?\s*['"]@datadog/""", "Datadog"),
    (r"""(?:import|require)\s*\(?\s*['"]@auth0/""", "Auth0"),
    (r"""(?:import|require)\s*\(?\s*['"]@google-cloud/""", "Google Cloud"),
]

# HTTP client library patterns: (regex_pattern, library_name)
HTTP_CLIENT_PATTERNS: list[tuple[str, str]] = [
    # Python
    (r"\brequests\.(get|post|put|patch|delete|head|options)\b", "requests"),
    (r"\bhttpx\.(get|post|put|patch|delete|head|options)\b", "httpx"),
    (r"\baiohttp\.ClientSession\b", "aiohttp"),
    (r"\burllib\.request\b", "urllib"),
    # JavaScript/TypeScript
    (r"\bfetch\s*\(", "fetch"),
    (r"\baxios\.(get|post|put|patch|delete|head|options|request)\b", "axios"),
    (r"\baxios\s*\(", "axios"),
    (r"\bgot\s*\(", "got"),
    (r"\bgot\.(get|post|put|patch|delete|head|options)\b", "got"),
    (r"\bky\.(get|post|put|patch|delete|head|options)\b", "ky"),
    (r"\bky\s*\(", "ky"),
]

# Internal route patterns: (regex_pattern, framework_name, http_method_group_index_or_none)
ROUTE_PATTERNS: list[tuple[str, str, int | None]] = [
    # FastAPI
    (r"@(?:router|app)\.(get|post|put|patch|delete|head|options)\s*\(", "FastAPI", 1),
    # Flask
    (r"@(?:app|blueprint|bp)\.(route)\s*\(", "Flask", None),
    (r"@(?:app|blueprint|bp)\.(get|post|put|patch|delete)\s*\(", "Flask", 1),
    # Express
    (r"\b(?:app|router)\.(get|post|put|patch|delete|all|use)\s*\(", "Express", 1),
    # Django
    (r"\bpath\s*\(\s*['\"]", "Django", None),
    (r"\bre_path\s*\(\s*['\"]", "Django", None),
]

# URL extraction regex - matches http(s) URLs in string literals
URL_PATTERN = re.compile(
    r"""['"`]"""
    r"(https?://[a-zA-Z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+)"
    r"""['"`]"""
)


class IntegrationScanner:
    """Scans a project for API integrations, SDK imports, and route definitions."""

    def __init__(self, project_path: Path):
        self.project_path = project_path.resolve()
        # Pre-compile patterns for performance
        self._service_regexes = [
            (re.compile(pat, re.IGNORECASE), name)
            for pat, name in KNOWN_SERVICE_PATTERNS
        ]
        self._sdk_regexes = [
            (re.compile(pat), name) for pat, name in SDK_IMPORT_PATTERNS
        ]
        self._http_regexes = [
            (re.compile(pat), name) for pat, name in HTTP_CLIENT_PATTERNS
        ]
        self._route_regexes = [
            (re.compile(pat), fw, grp) for pat, fw, grp in ROUTE_PATTERNS
        ]

    def scan(self) -> IntegrationReport:
        """Scan the project for all integration points.

        Returns an IntegrationReport with detected integrations grouped by service.
        """
        report = IntegrationReport()

        for file_path in self._get_scannable_files():
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except (OSError, PermissionError):
                continue

            report.files_scanned += 1
            rel_path = str(file_path.relative_to(self.project_path))

            for line_number, line in enumerate(content.splitlines(), start=1):
                self._scan_line(line, rel_path, line_number, report)

        report.services_detected = self._build_service_summaries(report.integrations)
        return report

    def _get_scannable_files(self) -> list[Path]:
        """Get all files eligible for scanning."""
        files = []
        for item in self.project_path.rglob("*"):
            if any(skip in item.parts for skip in SKIP_DIRECTORIES):
                continue
            if item.is_file() and item.suffix.lower() in SCANNABLE_EXTENSIONS:
                files.append(item)
        return files

    def _scan_line(
        self,
        line: str,
        file_path: str,
        line_number: int,
        report: IntegrationReport,
    ) -> None:
        """Scan a single line for integration points."""
        self._check_sdk_imports(line, file_path, line_number, report)
        self._check_http_clients(line, file_path, line_number, report)
        self._check_routes(line, file_path, line_number, report)
        self._check_urls(line, file_path, line_number, report)

    def _check_sdk_imports(
        self,
        line: str,
        file_path: str,
        line_number: int,
        report: IntegrationReport,
    ) -> None:
        """Detect SDK import statements."""
        for regex, service in self._sdk_regexes:
            if regex.search(line):
                report.integrations.append(IntegrationPoint(
                    service_name=service,
                    integration_type="sdk_import",
                    file_path=file_path,
                    line_number=line_number,
                    matched_text=line.strip(),
                ))
                return  # One import match per line is enough

    def _check_http_clients(
        self,
        line: str,
        file_path: str,
        line_number: int,
        report: IntegrationReport,
    ) -> None:
        """Detect HTTP client library usage and extract method."""
        for regex, library in self._http_regexes:
            match = regex.search(line)
            if match:
                method = match.group(1).upper() if match.lastindex else None
                # Try to extract a URL from the same line
                url_match = URL_PATTERN.search(line)
                endpoint = url_match.group(1) if url_match else None

                # Identify the service from the URL if present
                service = library
                if endpoint:
                    detected = self._identify_service_from_url(endpoint)
                    if detected:
                        service = detected

                report.integrations.append(IntegrationPoint(
                    service_name=service,
                    integration_type="external_api",
                    file_path=file_path,
                    line_number=line_number,
                    matched_text=line.strip(),
                    endpoint_url=endpoint,
                    http_method=method,
                ))
                return

    def _check_routes(
        self,
        line: str,
        file_path: str,
        line_number: int,
        report: IntegrationReport,
    ) -> None:
        """Detect internal route definitions (FastAPI, Flask, Express, Django)."""
        for regex, framework, method_group in self._route_regexes:
            match = regex.search(line)
            if match:
                method = None
                if method_group is not None and match.lastindex and match.lastindex >= method_group:
                    method = match.group(method_group).upper()

                # Try to extract the route path from string literal on same line
                route_match = re.search(r"""['"](/[^'"]*?)['"]""", line)
                endpoint = route_match.group(1) if route_match else None

                report.integrations.append(IntegrationPoint(
                    service_name=framework,
                    integration_type="internal_route",
                    file_path=file_path,
                    line_number=line_number,
                    matched_text=line.strip(),
                    endpoint_url=endpoint,
                    http_method=method,
                ))
                return

    def _check_urls(
        self,
        line: str,
        file_path: str,
        line_number: int,
        report: IntegrationReport,
    ) -> None:
        """Extract URLs from string literals and match against known services."""
        for url_match in URL_PATTERN.finditer(line):
            url = url_match.group(1)
            service = self._identify_service_from_url(url)
            if service:
                # Avoid duplicate if already detected by HTTP client check
                if any(
                    i.file_path == file_path
                    and i.line_number == line_number
                    and i.service_name == service
                    for i in report.integrations
                ):
                    continue
                report.integrations.append(IntegrationPoint(
                    service_name=service,
                    integration_type="external_api",
                    file_path=file_path,
                    line_number=line_number,
                    matched_text=line.strip(),
                    endpoint_url=url,
                ))

    def _identify_service_from_url(self, url: str) -> str | None:
        """Match a URL against known external service patterns."""
        for regex, service in self._service_regexes:
            if regex.search(url):
                return service
        return None

    def _build_service_summaries(
        self, integrations: list[IntegrationPoint]
    ) -> list[ServiceSummary]:
        """Aggregate integration points into per-service summaries."""
        service_map: dict[str, ServiceSummary] = {}

        for point in integrations:
            if point.service_name not in service_map:
                service_map[point.service_name] = ServiceSummary(
                    service_name=point.service_name,
                    count=0,
                )

            summary = service_map[point.service_name]
            summary.count += 1

            if point.endpoint_url and point.endpoint_url not in summary.endpoints:
                summary.endpoints.append(point.endpoint_url)
            if point.file_path not in summary.files:
                summary.files.append(point.file_path)

        return sorted(service_map.values(), key=lambda s: s.count, reverse=True)
