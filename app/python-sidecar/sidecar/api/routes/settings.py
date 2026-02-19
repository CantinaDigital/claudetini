"""
Settings API routes — providers, branch strategy, context files, budget.

TODO: These are stub implementations returning sensible defaults.
      Wire up to real detection logic as core modules mature.
"""

import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Core module imports (optional — stubs work without them)
# ---------------------------------------------------------------------------
try:
    from src.core.branch_strategy import BranchStrategyDetector
    BRANCH_STRATEGY_AVAILABLE = True
except ImportError:
    BRANCH_STRATEGY_AVAILABLE = False

try:
    from src.core.token_budget import TokenBudgetManager
    from src.core.runtime import project_id_for_path
    BUDGET_AVAILABLE = True
except ImportError:
    BUDGET_AVAILABLE = False


# =========================================================================
# Pydantic response models
# =========================================================================

class ProviderInfoResponse(BaseModel):
    name: str
    version: str
    status: str  # "authenticated" | "not configured" | "error"
    color: str
    installed: bool


class TestProviderRequest(BaseModel):
    provider: str


class TestProviderResponse(BaseModel):
    success: bool
    message: str
    version: str | None = None


class BranchStrategyResponse(BaseModel):
    detected: str
    description: str
    evidence: str


class ContextFileInfoResponse(BaseModel):
    file: str
    status: str  # "pass" | "warn" | "missing"
    detail: str
    icon: str


class GenerateContextFileRequest(BaseModel):
    project_path: str
    filename: str


class GenerateContextFileResponse(BaseModel):
    success: bool
    message: str


class BudgetResponse(BaseModel):
    monthly: float
    spent: float
    weeklySpent: float
    perSession: float


# =========================================================================
# Provider detection helpers
# =========================================================================

def _detect_cli(name: str, version_flag: str = "--version") -> tuple[bool, str]:
    """Check if a CLI tool is on PATH and grab its version string."""
    path = shutil.which(name)
    if path is None:
        return False, ""
    try:
        result = subprocess.run(
            [name, version_flag],
            capture_output=True,
            text=True,
            timeout=5,
        )
        version = result.stdout.strip() or result.stderr.strip()
        # Grab first line only
        version = version.splitlines()[0] if version else ""
        return True, version
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False, ""


def _detect_providers() -> list[ProviderInfoResponse]:
    """Detect available AI coding providers on this machine."""
    providers: list[ProviderInfoResponse] = []

    # Claude Code
    installed, version = _detect_cli("claude")
    providers.append(ProviderInfoResponse(
        name="Claude Code",
        version=version or "unknown",
        status="authenticated" if installed else "not configured",
        color="#8b7cf6",
        installed=installed,
    ))

    # OpenAI Codex CLI
    installed, version = _detect_cli("codex")
    providers.append(ProviderInfoResponse(
        name="Codex CLI",
        version=version or "unknown",
        status="authenticated" if installed else "not configured",
        color="#10b981",
        installed=installed,
    ))

    # Gemini CLI
    installed, version = _detect_cli("gemini")
    providers.append(ProviderInfoResponse(
        name="Gemini CLI",
        version=version or "unknown",
        status="authenticated" if installed else "not configured",
        color="#3b82f6",
        installed=installed,
    ))

    return providers


# =========================================================================
# Routes
# =========================================================================

@router.get("/providers")
def detect_providers(
    project_path: str = Query(..., description="Absolute path to the project"),
) -> list[ProviderInfoResponse]:
    """Detect installed AI coding providers.

    TODO: Use project_path to check for project-level provider config.
    """
    return _detect_providers()


@router.post("/providers/test")
def test_provider(request: TestProviderRequest) -> TestProviderResponse:
    """Test connectivity for a named provider.

    TODO: Actually invoke the provider with a minimal prompt to verify auth.
    """
    name_lower = request.provider.lower()

    # Map display names to CLI names
    cli_map = {
        "claude code": "claude",
        "claude": "claude",
        "codex cli": "codex",
        "codex": "codex",
        "gemini cli": "gemini",
        "gemini": "gemini",
    }

    cli_name = cli_map.get(name_lower)
    if cli_name is None:
        return TestProviderResponse(
            success=False,
            message=f"Unknown provider: {request.provider}",
        )

    installed, version = _detect_cli(cli_name)
    if not installed:
        return TestProviderResponse(
            success=False,
            message=f"{request.provider} CLI not found on PATH.",
        )

    return TestProviderResponse(
        success=True,
        message=f"{request.provider} is installed and reachable.",
        version=version or None,
    )


@router.get("/branch-strategy")
def get_branch_strategy(
    project_path: str = Query(..., description="Absolute path to the project"),
) -> BranchStrategyResponse:
    """Detect the branch strategy for a project."""
    path = Path(project_path)
    if not path.exists():
        raise HTTPException(status_code=400, detail="Project path does not exist")

    if BRANCH_STRATEGY_AVAILABLE:
        try:
            detector = BranchStrategyDetector(path)
            result = detector.detect()
            return BranchStrategyResponse(
                detected=result.label,
                description=_strategy_description(result.label),
                evidence=result.reason,
            )
        except Exception as exc:
            logger.warning("Branch strategy detection failed: %s", exc)

    # Fallback stub
    return BranchStrategyResponse(
        detected="Unknown",
        description="Could not detect branch strategy.",
        evidence="No branch data available.",
    )


def _strategy_description(label: str) -> str:
    """Return a human-readable description for a strategy label."""
    descriptions = {
        "Trunk-based": "Direct commits to main branch with short-lived feature branches.",
        "Git Flow": "Long-lived develop and main branches with feature/release/hotfix branches.",
        "Feature Branch": "Feature branches merged into main via pull requests.",
        "PR-based": "Pull request workflow with code review before merging.",
    }
    return descriptions.get(label, "Could not detect branch strategy.")


# Context file definitions: (filename, icon, description when present, description when missing)
_CONTEXT_FILES = [
    ("CLAUDE.md", "doc", "Claude Code instructions found", "No CLAUDE.md — Claude lacks project context"),
    (".claude/planning/ROADMAP.md", "map", "Roadmap found", "No roadmap — progress tracking unavailable"),
    ("README.md", "book", "README found", "No README — project lacks overview"),
    (".gitignore", "shield", "Gitignore configured", "No .gitignore — risk of committing junk files"),
    (".cursorrules", "cursor", "Cursor rules found", "No .cursorrules (optional)"),
    (".github/copilot-instructions.md", "copilot", "Copilot instructions found", "No copilot instructions (optional)"),
]


@router.get("/context-files")
def get_context_files(
    project_path: str = Query(..., description="Absolute path to the project"),
) -> list[ContextFileInfoResponse]:
    """List context/instruction files and their status for a project."""
    path = Path(project_path)
    if not path.exists():
        raise HTTPException(status_code=400, detail="Project path does not exist")

    results: list[ContextFileInfoResponse] = []
    for filename, icon, present_detail, missing_detail in _CONTEXT_FILES:
        file_path = path / filename
        exists = file_path.exists() and file_path.is_file()

        if exists:
            size = file_path.stat().st_size
            if size == 0:
                status = "warn"
                detail = f"{filename} exists but is empty"
            else:
                status = "pass"
                detail = present_detail
        else:
            # Optional files get "warn" not "missing"
            optional = filename in (".cursorrules", ".github/copilot-instructions.md")
            status = "warn" if optional else "missing"
            detail = missing_detail

        results.append(ContextFileInfoResponse(
            file=filename,
            status=status,
            detail=detail,
            icon=icon,
        ))

    return results


@router.post("/context-files/generate")
def generate_context_file(request: GenerateContextFileRequest) -> GenerateContextFileResponse:
    """Generate a context file for the project.

    TODO: Hook into bootstrap / claude_md_manager to actually generate files.
    """
    path = Path(request.project_path)
    if not path.exists():
        raise HTTPException(status_code=400, detail="Project path does not exist")

    # Stub: return a helpful message without actually generating
    return GenerateContextFileResponse(
        success=False,
        message=f"Generation of {request.filename} is not yet implemented. Use the Bootstrap flow to create project files.",
    )


@router.get("/budget")
def get_budget(
    project_path: str = Query(..., description="Absolute path to the project"),
) -> BudgetResponse:
    """Return budget settings and current spend for a project."""
    if BUDGET_AVAILABLE:
        try:
            pid = project_id_for_path(Path(project_path))
            manager = TokenBudgetManager(pid)
            budget = manager.load_budget()
            status = manager.status()

            monthly_limit = budget.monthly_limit_usd or 0.0
            monthly_spent = float(status.get("monthly", {}).get("spent", 0.0))
            weekly_spent = float(status.get("weekly", {}).get("spent", 0.0))
            per_session = budget.per_session_limit_usd or 0.0

            return BudgetResponse(
                monthly=monthly_limit,
                spent=monthly_spent,
                weeklySpent=weekly_spent,
                perSession=per_session,
            )
        except Exception as exc:
            logger.warning("Budget lookup failed: %s", exc)

    # Fallback: no budget configured
    return BudgetResponse(
        monthly=0.0,
        spent=0.0,
        weeklySpent=0.0,
        perSession=0.0,
    )
