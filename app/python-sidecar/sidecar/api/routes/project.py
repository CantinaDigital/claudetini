"""
Project API routes
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
from datetime import datetime
import logging
import re

router = APIRouter()
logger = logging.getLogger(__name__)

# Import core modules
try:
    from src.core.project import Project, ProjectRegistry
    from src.core.health import HealthChecker, HealthLevel
    from src.core.git_utils import GitUtils
    from src.core.provider_usage import ProviderUsageStore
    from src.core.runtime import project_id_for_path, project_runtime_dir
    from src.core.sessions import SessionParser
    CORE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Core modules not available: {e}")
    CORE_AVAILABLE = False


class ProjectResponse(BaseModel):
    id: str
    name: str
    path: str
    branch: str
    uncommitted: int
    lastSession: Optional[str] = None
    lastOpened: Optional[str] = None
    lastOpenedTimestamp: Optional[str] = None
    costWeek: str = "$0.00"
    totalSessions: int = 0
    readmeSummary: Optional[str] = None


class HealthItemResponse(BaseModel):
    name: str
    status: str  # "pass" | "warn" | "fail"
    detail: str


class HealthResponse(BaseModel):
    items: list[HealthItemResponse]
    score: int


class RegisterRequest(BaseModel):
    path: str


def _get_project_path(project_id: str) -> Path | None:
    """Get project path from ID (path string).

    Only accepts absolute paths to prevent path traversal attacks.
    """
    # The project_id is actually the path string
    path = Path(project_id)
    if not path.is_absolute():
        return None  # Reject relative paths for defense-in-depth
    path = path.resolve()  # Collapse .. components to prevent traversal
    if path.exists():
        return path
    # Try to find in registry
    if CORE_AVAILABLE:
        registry = ProjectRegistry.load_or_create()
        for project in registry.list_projects():
            if str(project.path) == project_id or project.name == project_id:
                return project.path
    return None


def _relative_time_label(timestamp: datetime | None) -> str | None:
    if timestamp is None:
        return None
    # SessionParser can return timezone-aware datetimes (from ISO strings with Z).
    # Compare using a matching timezone-aware "now" to avoid naive/aware TypeError.
    if timestamp.tzinfo is not None and timestamp.utcoffset() is not None:
        now = datetime.now(timestamp.tzinfo)
    else:
        now = datetime.now()

    delta = now - timestamp
    total_seconds = max(0, int(delta.total_seconds()))
    if total_seconds < 60:
        return "just now"
    if total_seconds < 3600:
        return f"{total_seconds // 60}m ago"
    if total_seconds < 86400:
        return f"{total_seconds // 3600}h ago"
    return f"{total_seconds // 86400}d ago"


def _project_usage_snapshot(project: Project) -> tuple[str, str | None, int]:
    """Compute weekly usage label, last session time, and total sessions."""
    week_label = "$0.00"
    last_session = None
    total_sessions = 0

    try:
        usage_store = ProviderUsageStore(project_id_for_path(project.path))
        week_totals = usage_store.totals(days=7).get("all", {})
        week_cost = float(week_totals.get("cost_usd", 0.0))
        week_units = float(week_totals.get("effort_units", 0.0))
        week_tokens = int(week_totals.get("tokens", 0))

        if week_cost > 0:
            week_label = f"${week_cost:.2f}"
        elif week_units > 0:
            week_label = f"{week_units:.1f}u est"
        elif week_tokens > 0:
            week_label = f"{(week_tokens / 1000):.1f}k tok"

        last_session = _relative_time_label(usage_store.latest_event_timestamp())
        total_sessions = usage_store.unique_session_count()
    except Exception as exc:
        logger.debug("Failed to read provider usage telemetry for %s: %s", project.path, exc)

    if project.claude_hash:
        parser = SessionParser()
        if total_sessions == 0:
            total_sessions = parser.get_session_count(project.claude_hash)
        if last_session is None:
            latest = parser.get_latest_session(project.claude_hash)
            last_session = _relative_time_label(latest.start_time if latest else None)

    return week_label, last_session, total_sessions


def _extract_readme_summary(content: str) -> str | None:
    """Extract a concise first-paragraph summary from README content."""
    text = content.replace("\r\n", "\n")
    lines = text.split("\n")

    # Strip YAML front matter if present.
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                lines = lines[i + 1 :]
                break

    paragraphs: list[str] = []
    current: list[str] = []
    in_fence = False

    for raw in lines:
        line = raw.strip()

        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        if not line:
            if current:
                paragraphs.append(" ".join(current).strip())
                current = []
            continue

        if (
            line.startswith("#")
            or line.startswith("![")
            or line.startswith("[![")
            or line.startswith("<!--")
            or line.startswith("<img")
        ):
            continue

        line = re.sub(r"^>\s*", "", line)
        line = re.sub(r"^[-*+]\s+", "", line)
        line = re.sub(r"^\d+\.\s+", "", line)
        current.append(line)

    if current:
        paragraphs.append(" ".join(current).strip())

    for paragraph in paragraphs:
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", paragraph)  # links
        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)  # inline code
        cleaned = re.sub(r"[*_~]", "", cleaned)  # emphasis markers
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) >= 24:
            return cleaned[:480]

    return None


def _project_readme_summary(path: Path) -> str | None:
    readme_names = ["README.md", "README.rst", "README.txt", "README"]
    for name in readme_names:
        readme_path = path / name
        if not readme_path.exists() or not readme_path.is_file():
            continue
        try:
            content = readme_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        summary = _extract_readme_summary(content)
        if summary:
            return summary
    return None


@router.get("/list")
def list_projects() -> list[ProjectResponse]:
    """List all registered projects.

    Returns lightweight data for the project picker: id, name, path, lastOpened.
    Heavy fields (branch, uncommitted, sessions, readme) are fetched per-project
    via GET /{project_id} when a project is selected.
    """
    if not CORE_AVAILABLE:
        # Core modules not available - return empty list
        return []

    registry = ProjectRegistry.load_or_create()
    projects = registry.list_projects()

    result = []
    for project in projects:
        last_opened = _relative_time_label(project.last_opened) if project.last_opened else None
        last_opened_timestamp = project.last_opened.isoformat() if project.last_opened else None

        result.append(
            ProjectResponse(
                id=str(project.path),
                name=project.name,
                path=str(project.path),
                branch="",
                uncommitted=0,
                lastSession=None,
                lastOpened=last_opened,
                lastOpenedTimestamp=last_opened_timestamp,
                costWeek="$0.00",
                totalSessions=0,
                readmeSummary=_project_readme_summary(project.path),
            )
        )

    return result


@router.post("/register")
async def register_project(request: RegisterRequest) -> ProjectResponse:
    """Register a new project"""
    path = Path(request.path).resolve()

    if not path.exists():
        raise HTTPException(status_code=400, detail="Path does not exist")

    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Core modules not loaded")

    project = Project.from_path(path)
    registry = ProjectRegistry.load_or_create()
    registry.add_project(project)

    try:
        git = GitUtils(project.path)
        branch = git.current_branch()
        uncommitted = git.uncommitted_files()
    except Exception:
        branch = "unknown"
        uncommitted = []

    week_label, last_session, total_sessions = _project_usage_snapshot(project)
    readme_summary = _project_readme_summary(project.path)

    # Format last_opened timestamp
    last_opened = None
    last_opened_timestamp = None
    if project.last_opened:
        last_opened = _relative_time_label(project.last_opened)
        last_opened_timestamp = project.last_opened.isoformat()

    return ProjectResponse(
        id=str(project.path),
        name=project.name,
        path=str(project.path),
        branch=branch,
        uncommitted=len(uncommitted),
        lastSession=last_session,
        lastOpened=last_opened,
        lastOpenedTimestamp=last_opened_timestamp,
        costWeek=week_label,
        totalSessions=total_sessions,
        readmeSummary=readme_summary,
    )


class DiscoveredProjectResponse(BaseModel):
    path: str
    name: str
    claude_hash: str


@router.get("/discover")
def discover_projects() -> list[DiscoveredProjectResponse]:
    """Discover unregistered Claude Code projects."""
    if not CORE_AVAILABLE:
        return []
    registry = ProjectRegistry.load_or_create()
    discovered = registry.discover_unregistered()
    return [DiscoveredProjectResponse(**d) for d in discovered]


# IMPORTANT: This route MUST be defined BEFORE the generic /{project_id:path} route
# because FastAPI matches routes in order of definition
@router.get("/health/{project_id:path}")
def get_project_health(project_id: str) -> HealthResponse:
    """Get project health report"""
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Core modules not loaded")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    checker = HealthChecker(project_path)
    status = checker.run_all_checks()

    def level_to_status(level: HealthLevel) -> str:
        if level == HealthLevel.GOOD:
            return "pass"
        elif level == HealthLevel.WARNING:
            return "warn"
        else:
            return "fail"

    return HealthResponse(
        items=[
            HealthItemResponse(
                name=check.category,
                status=level_to_status(check.level),
                detail=check.message,
            )
            for check in status.checks
        ],
        score=status.overall_score,
    )


class ActionResponse(BaseModel):
    success: bool
    message: str


# IMPORTANT: These routes MUST be defined BEFORE the generic /{project_id:path} route
@router.post("/{project_id:path}/clear-history")
def clear_project_history(project_id: str) -> ActionResponse:
    """Clear dispatch output logs for a project.

    Removes all log files from the project's dispatch-output directory
    without affecting the project registration or other runtime data.
    """
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Core modules not loaded")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    pid = project_id_for_path(project_path)
    runtime_dir = project_runtime_dir(pid)
    dispatch_dir = runtime_dir / "dispatch-output"

    removed = 0
    if dispatch_dir.exists():
        for log_file in dispatch_dir.iterdir():
            if log_file.is_file():
                try:
                    log_file.unlink()
                    removed += 1
                except OSError as exc:
                    logger.warning("Failed to remove log file %s: %s", log_file, exc)

    logger.info("Cleared %d dispatch log(s) for project %s", removed, project_id)
    return ActionResponse(success=True, message=f"History cleared ({removed} log files removed)")


@router.delete("/{project_id:path}/remove")
def remove_project(project_id: str) -> ActionResponse:
    """Remove a project from the registry.

    Unregisters the project so it no longer appears in the project list.
    Does NOT delete any project files on disk.
    """
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Core modules not loaded")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    registry = ProjectRegistry.load_or_create()
    registry.remove_project(project_path)

    logger.info("Removed project %s from registry", project_id)
    return ActionResponse(success=True, message="Project removed")


# Generic project detail route - MUST be last due to {project_id:path} matching everything
@router.get("/{project_id:path}")
def get_project(project_id: str) -> ProjectResponse:
    """Get project details"""
    if not CORE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Core modules not loaded")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    # Update last_opened timestamp in registry
    registry = ProjectRegistry.load_or_create()
    registry.update_last_opened(project_path)

    project = Project.from_path(project_path)
    # Reload to get updated last_opened timestamp
    registered_project = registry.get_project(project_path)
    if registered_project:
        project = registered_project

    try:
        git = GitUtils(project.path)
        branch = git.current_branch()
        uncommitted = git.uncommitted_files()
    except Exception:
        branch = "unknown"
        uncommitted = []

    week_label, last_session, total_sessions = _project_usage_snapshot(project)
    readme_summary = _project_readme_summary(project.path)

    # Format last_opened timestamp
    last_opened = None
    last_opened_timestamp = None
    if project.last_opened:
        last_opened = _relative_time_label(project.last_opened)
        last_opened_timestamp = project.last_opened.isoformat()

    return ProjectResponse(
        id=str(project.path),
        name=project.name,
        path=str(project.path),
        branch=branch,
        uncommitted=len(uncommitted),
        lastSession=last_session,
        lastOpened=last_opened,
        lastOpenedTimestamp=last_opened_timestamp,
        costWeek=week_label,
        totalSessions=total_sessions,
        readmeSummary=readme_summary,
    )
