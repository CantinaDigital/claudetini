"""
Git API routes
"""

from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from typing import Optional
from pathlib import Path
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Shared thread pool for parallelizing git subprocess calls
_git_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="git")

# Maximum characters of git diff to send to the AI commit message generator.
_MAX_DIFF_CHARS = 24000

# Use a cheap/fast model for menial tasks like commit message generation.
# Saves the user's high-end model tokens for real coding work.
_COMMIT_MSG_MODEL = "claude-haiku-4-5-20251001"

# Human-friendly label for Co-Authored-By (derived from model ID).
_MODEL_LABELS: dict[str, str] = {
    "claude-haiku-4-5-20251001": "Claude Haiku 4.5",
    "claude-sonnet-4-5-20250929": "Claude Sonnet 4.5",
    "claude-opus-4-6": "Claude Opus 4.6",
}


def _model_display_name(model_id: str) -> str:
    """Return a human-friendly model name for Co-Authored-By lines."""
    if model_id in _MODEL_LABELS:
        return _MODEL_LABELS[model_id]
    # Fallback: title-case the model ID
    return model_id.replace("-", " ").title()

# Import core modules
try:
    from src.core.git_utils import GitUtils, GitRepo
    from src.core.project import ProjectRegistry
    from src.agents.dispatcher import dispatch_task
    CORE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Core modules not available: {e}")
    CORE_AVAILABLE = False

from ..ttl_cache import get as cache_get, put as cache_put


class UnpushedCommitResponse(BaseModel):
    """A commit that exists locally but has not been pushed to the remote."""

    hash: str
    msg: str
    time: str


class UncommittedFileResponse(BaseModel):
    """A file with uncommitted changes (staged or working-tree modifications)."""

    file: str
    status: str
    lines: Optional[str] = None


class UntrackedFileResponse(BaseModel):
    """An untracked file not yet added to the git index."""

    file: str


class StashResponse(BaseModel):
    """A single git stash entry."""

    id: str
    msg: str
    time: str


class SubmoduleIssueResponse(BaseModel):
    """A submodule with uncommitted or out-of-sync changes."""

    file: str


class GitStatusResponse(BaseModel):
    """Full git status including branch, staged, unstaged, untracked, and stash info."""

    branch: str
    unpushed: list[UnpushedCommitResponse]
    staged: list[UncommittedFileResponse]
    uncommitted: list[UncommittedFileResponse]
    untracked: list[UntrackedFileResponse]
    stashed: list[StashResponse]
    submodule_issues: list[SubmoduleIssueResponse]


class CommitResponse(BaseModel):
    """A single commit from the repository history."""

    hash: str
    msg: str
    branch: str
    date: str
    time: str
    merge: Optional[bool] = None


class ActionResponse(BaseModel):
    """Generic response for git actions (commit, push, stash, etc.)."""

    success: bool
    message: str
    hash: Optional[str] = None


class CommitRequest(BaseModel):
    """Request body for creating a commit with a message."""

    message: str = Field(..., min_length=1, max_length=10000)


class StashDropRequest(BaseModel):
    """Request body for dropping a specific stash entry."""

    stash_id: Optional[str] = None


class StageRequest(BaseModel):
    """Request body specifying files to stage or unstage."""

    files: list[str]


class StageResponse(BaseModel):
    """Response after staging files, listing which files were staged."""

    success: bool
    message: str
    staged: list[str] = []


class UnstageResponse(BaseModel):
    """Response after unstaging files, listing which files were unstaged."""

    success: bool
    message: str
    unstaged: list[str] = []


class CommitStagedRequest(BaseModel):
    """Request body for committing only staged changes."""

    message: str


class DiscardRequest(BaseModel):
    """Request body identifying a file to discard or delete."""

    file: str = Field(..., min_length=1, max_length=2048)


class QuickCommitResponse(BaseModel):
    """Response for the quick-commit action (stage all + auto-message + commit)."""

    success: bool
    message: str
    commit_message: Optional[str] = None
    hash: Optional[str] = None
    files_committed: int = 0


class GenerateMessageResponse(BaseModel):
    """Heuristic-generated commit message based on changed file paths."""

    message: str
    files: list[str]
    summary: str


class AIGenerateMessageResponse(BaseModel):
    """AI-generated commit message with metadata."""
    message: str
    files: list[str]
    summary: str
    ai_generated: bool = True
    model: Optional[str] = None
    error: Optional[str] = None


def _get_project_path(project_id: str) -> Path | None:
    """Get project path from ID."""
    path = Path(project_id)
    if path.exists():
        return path
    if CORE_AVAILABLE:
        registry = ProjectRegistry.load_or_create()
        for project in registry.list_projects():
            if str(project.path) == project_id or project.name == project_id:
                return project.path
    return None


@router.get("/{project_id:path}/status")
def get_git_status(project_id: str) -> GitStatusResponse:
    """Get git status (unpushed, staged, uncommitted, stashes)"""
    if not CORE_AVAILABLE:
        return GitStatusResponse(
            branch="unknown",
            unpushed=[],
            staged=[],
            uncommitted=[],
            untracked=[],
            stashed=[],
            submodule_issues=[],
        )

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    cache_key = f"git:status:{project_path}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        git = GitUtils(project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Not a git repository: {e}")

    # Run independent git operations in parallel instead of sequentially
    branch_future = _git_pool.submit(git.current_branch)
    status_future = _git_pool.submit(git.get_status_detailed)
    unpushed_future = _git_pool.submit(git.unpushed_commits)
    stash_future = _git_pool.submit(git.list_stashes)

    branch = branch_future.result(timeout=15)
    status_data = status_future.result(timeout=15)
    unpushed_commits = unpushed_future.result(timeout=15)
    stashes = stash_future.result(timeout=15)

    result = GitStatusResponse(
        branch=branch,
        unpushed=[
            UnpushedCommitResponse(
                hash=c.get("hash", "")[:7],
                msg=c.get("message", ""),
                time=c.get("time", ""),
            )
            for c in unpushed_commits
        ],
        staged=[
            UncommittedFileResponse(
                file=f["path"],
                status=f.get("status", "A"),
                lines=f.get("lines"),
            )
            for f in status_data.get("staged", [])
        ],
        uncommitted=[
            UncommittedFileResponse(
                file=f["path"],
                status=f.get("status", "M"),
                lines=f.get("lines"),
            )
            for f in status_data.get("modified", [])
        ],
        untracked=[
            UntrackedFileResponse(file=f)
            for f in status_data.get("untracked", [])
        ],
        stashed=[
            StashResponse(
                id=s.get("id", ""),
                msg=s.get("message", ""),
                time=s.get("time", ""),
            )
            for s in stashes
        ],
        submodule_issues=[
            SubmoduleIssueResponse(file=f)
            for f in status_data.get("submodule_issues", [])
        ],
    )
    cache_put(cache_key, result, ttl=3)
    return result


@router.get("/{project_id:path}/commits")
def get_commits(project_id: str, limit: int = Query(30, ge=1, le=500)) -> list[CommitResponse]:
    """Get recent commits"""
    if not CORE_AVAILABLE:
        return []

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    cache_key = f"git:commits:{project_path}:{limit}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        git = GitUtils(project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Not a git repository: {e}")

    commits = git.recent_commits(limit=limit)

    result = [
        CommitResponse(
            hash=c.get("hash", "")[:7],
            msg=c.get("message", ""),
            branch=c.get("branch", "unknown"),
            date=c.get("date", ""),
            time=c.get("time", ""),
            merge=c.get("is_merge", None),
        )
        for c in commits
    ]
    cache_put(cache_key, result, ttl=5)
    return result


@router.get("/{project_id:path}/stashes")
async def get_stashes(project_id: str) -> list[StashResponse]:
    """Get git stashes"""
    if not CORE_AVAILABLE:
        # Core modules not available - return empty data
        return []

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        git = GitUtils(project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Not a git repository: {e}")

    stashes = git.list_stashes()

    return [
        StashResponse(
            id=s.get("id", ""),
            msg=s.get("message", ""),
            time=s.get("time", ""),
        )
        for s in stashes
    ]


@router.post("/{project_id:path}/push")
async def push_to_remote(project_id: str) -> ActionResponse:
    """Push current branch to origin"""
    if not CORE_AVAILABLE:
        return ActionResponse(success=False, message="Core modules not available")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        git = GitUtils(project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Not a git repository: {e}")

    success, message = git.push_to_remote()
    return ActionResponse(success=success, message=message)


@router.post("/{project_id:path}/commit")
async def commit_all(project_id: str, request: CommitRequest) -> ActionResponse:
    """Stage all changes and commit"""
    if not CORE_AVAILABLE:
        return ActionResponse(success=False, message="Core modules not available")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        git = GitUtils(project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Not a git repository: {e}")

    success, message, commit_hash = git.commit_all(request.message)
    return ActionResponse(success=success, message=message, hash=commit_hash)


@router.post("/{project_id:path}/stash/pop")
async def stash_pop(project_id: str) -> ActionResponse:
    """Pop the most recent stash"""
    if not CORE_AVAILABLE:
        return ActionResponse(success=False, message="Core modules not available")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        git = GitUtils(project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Not a git repository: {e}")

    success, message = git.stash_pop()
    return ActionResponse(success=success, message=message)


@router.post("/{project_id:path}/stash/drop")
async def stash_drop(project_id: str, request: StashDropRequest) -> ActionResponse:
    """Drop a stash (defaults to most recent)"""
    if not CORE_AVAILABLE:
        return ActionResponse(success=False, message="Core modules not available")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        git = GitUtils(project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Not a git repository: {e}")

    success, message = git.stash_drop(request.stash_id)
    return ActionResponse(success=success, message=message)


def _categorize_files(files: list[dict]) -> tuple[list[str], list[str], list[str]]:
    """Split file dicts into (added, modified, deleted) path lists."""
    added: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []
    for f in files:
        status = f.get("status", "M")
        path = f.get("path", f.get("file", "unknown"))
        if status in ("?", "A"):
            added.append(path)
        elif status == "D":
            deleted.append(path)
        else:
            modified.append(path)
    return added, modified, deleted


def _infer_commit_type(
    all_files: list[str],
    added: list[str],
    modified: list[str],
    deleted: list[str],
) -> str:
    """Infer conventional commit type from file paths and change kinds."""
    paths_lower = " ".join(all_files).lower()
    if any(p in paths_lower for p in ["test", "spec", "__test__"]):
        return "test"
    if any(p in paths_lower for p in ["readme", "docs/", "doc/", ".md"]):
        return "docs"
    if any(p in paths_lower for p in ["fix", "bug", "patch"]):
        return "fix"
    if added and not modified and not deleted:
        return "feat"
    if modified and not added:
        return "refactor"
    return "chore"


def _infer_scope(all_files: list[str]) -> str | None:
    """Derive a conventional-commit scope from common directory of changed files."""
    from collections import Counter

    dirs = [Path(f).parent.as_posix() for f in all_files if "/" in f or "\\" in f]
    if not dirs:
        return None
    top_dirs = [d.split("/")[0] for d in dirs if d and d != "."]
    if not top_dirs:
        return None
    scope = Counter(top_dirs).most_common(1)[0][0]
    if scope in ("src", "lib", "app"):
        deeper = [d.split("/")[1] for d in dirs if len(d.split("/")) > 1]
        if deeper:
            scope = Counter(deeper).most_common(1)[0][0]
    return scope


def _build_description(all_files: list[str]) -> str:
    """Build a short description string from the changed file list."""
    file_count = len(all_files)
    if file_count == 1:
        return Path(all_files[0]).name
    if file_count <= 3:
        return ", ".join(Path(f).name for f in all_files[:3])
    exts = set(Path(f).suffix for f in all_files)
    if len(exts) == 1:
        return f"{file_count} {list(exts)[0]} files"
    first_three = ", ".join(Path(f).name for f in all_files[:3])
    return f"{first_three} and {file_count - 3} more"


def _generate_commit_message(files: list[dict]) -> tuple[str, str]:
    """Generate a conventional commit message from changed files.

    Returns (commit_message, summary).
    """
    if not files:
        return "chore: empty commit", "No files changed"

    added, modified, deleted = _categorize_files(files)
    all_files = added + modified + deleted

    commit_type = _infer_commit_type(all_files, added, modified, deleted)
    scope = _infer_scope(all_files)
    desc = _build_description(all_files)

    verb = "update"
    if added and not modified and not deleted:
        verb = "add"
    elif deleted and not added and not modified:
        verb = "remove"

    message = f"{commit_type}({scope}): {verb} {desc}" if scope else f"{commit_type}: {verb} {desc}"

    parts = []
    if added:
        parts.append(f"{len(added)} added")
    if modified:
        parts.append(f"{len(modified)} modified")
    if deleted:
        parts.append(f"{len(deleted)} deleted")
    summary = ", ".join(parts) if parts else "No changes"

    return message, summary


_COMMIT_TYPES = ("feat", "fix", "refactor", "docs", "test", "chore", "style", "perf")


def _extract_commit_message(raw_output: str) -> str | None:
    """Extract the full commit message (subject + body) from Claude output.

    Finds the conventional commit subject line, then captures all subsequent
    non-decoration lines as the body.
    """
    lines = raw_output.strip().splitlines()
    subject_idx: int | None = None
    subject_line: str | None = None

    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line or line.startswith("```") or line.startswith("#") or line.startswith(">"):
            continue
        # Strip surrounding quotes
        if len(line) > 2 and line[0] in ('"', "'") and line[-1] == line[0]:
            line = line[1:-1]
        if ":" in line and any(line.startswith(t) for t in _COMMIT_TYPES):
            subject_idx = i
            subject_line = line
            break

    if subject_line is None:
        return None

    # Collect body lines after the subject
    body_lines: list[str] = []
    for raw in lines[subject_idx + 1 :]:
        line = raw.strip()
        # Stop at markdown fences or other decoration that signals end of message
        if line.startswith("```"):
            break
        body_lines.append(line)

    # Trim trailing blank lines
    while body_lines and not body_lines[-1]:
        body_lines.pop()

    if body_lines:
        return subject_line + "\n" + "\n".join(body_lines)
    return subject_line


@router.get("/{project_id:path}/generate-message")
async def generate_commit_message(project_id: str) -> GenerateMessageResponse:
    """Generate a commit message based on current changes (fast, no LLM)"""
    if not CORE_AVAILABLE:
        return GenerateMessageResponse(
            message="chore: update files",
            files=[],
            summary="Core modules not available"
        )

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        git = GitUtils(project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Not a git repository: {e}")

    uncommitted = git.uncommitted_files_with_lines()
    files = [{"path": f.get("path", ""), "status": f.get("status", "M")} for f in uncommitted]

    message, summary = _generate_commit_message(files)

    return GenerateMessageResponse(
        message=message,
        files=[f["path"] for f in files],
        summary=summary
    )


@router.get("/{project_id:path}/generate-message-ai")
async def generate_commit_message_ai(
    project_id: str,
    model: str = Query(default=_COMMIT_MSG_MODEL, description="Claude model to use"),
) -> AIGenerateMessageResponse:
    """Generate a commit message using Claude Code to analyze the actual diff.

    This uses the Claude Code CLI to intelligently analyze changes and generate
    a proper conventional commit message based on the actual code changes, not
    just file paths.
    """
    if not CORE_AVAILABLE:
        return AIGenerateMessageResponse(
            message="chore: update files",
            files=[],
            summary="Core modules not available",
            ai_generated=False,
            error="Core modules not loaded"
        )

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        git = GitUtils(project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Not a git repository: {e}")

    # Get the diff of all changes (staged + unstaged)
    try:
        diff_output = git.get_diff()
        if not diff_output or not diff_output.strip():
            # No diff available, fall back to heuristic
            uncommitted = git.uncommitted_files_with_lines()
            files = [{"path": f.get("path", ""), "status": f.get("status", "M")} for f in uncommitted]
            message, summary = _generate_commit_message(files)
            return AIGenerateMessageResponse(
                message=message,
                files=[f["path"] for f in files],
                summary=summary,
                ai_generated=False,
                error="No diff available - used heuristic"
            )
    except Exception as e:
        logger.error(f"Failed to get diff: {e}")
        return AIGenerateMessageResponse(
            message="chore: update files",
            files=[],
            summary="Failed to get diff",
            ai_generated=False,
            error=str(e)
        )

    # Truncate diff if too large
    if len(diff_output) > _MAX_DIFF_CHARS:
        diff_output = diff_output[:_MAX_DIFF_CHARS] + "\n... [diff truncated]"

    # Get list of changed files for context
    uncommitted = git.uncommitted_files_with_lines()
    file_list = [f.get("path", "") for f in uncommitted]

    # Create prompt for Claude Code
    prompt = f"""Look at the git diff below and write ONE conventional commit message.

Rules:
- First line: type(scope): summary in imperative mood ("add" not "added")
- Types: feat, fix, refactor, docs, test, chore, style, perf
- After the first line, add a blank line then a body with 2-4 sentences explaining what changed and why
- Mention key files, moved logic, new types, or wiring changes — be specific, not generic
- Do NOT use bullet points or markdown — just plain sentences
- Output ONLY the commit message, nothing else — no quotes, no explanation, no preamble

Changed files:
{chr(10).join(f"- {f}" for f in file_list[:20])}

Git diff:
```
{diff_output}
```"""

    # Resolve human-friendly label for Co-Authored-By
    model_label = _model_display_name(model)

    # Call Claude Code to generate the message (run in threadpool since dispatch_task blocks)
    try:
        result = await run_in_threadpool(
            dispatch_task,
            prompt=prompt,
            working_dir=project_path,
            timeout_seconds=90,
            model=model,
        )

        if result.success and result.output:
            generated_message = _extract_commit_message(result.output)

            if generated_message:
                # Append Co-Authored-By trailer
                co_author = f"\n\nCo-Authored-By: {model_label} & Claudetini <noreply@anthropic.com>"
                return AIGenerateMessageResponse(
                    message=generated_message + co_author,
                    files=file_list,
                    summary=f"AI-generated from {len(file_list)} file(s) via {model_label}",
                    ai_generated=True,
                    model=model,
                )
            else:
                logger.warning(f"AI output didn't contain conventional commit: {result.output[:200]}")
                files = [{"path": f.get("path", ""), "status": f.get("status", "M")} for f in uncommitted]
                message, summary = _generate_commit_message(files)
                return AIGenerateMessageResponse(
                    message=message,
                    files=file_list,
                    summary=f"AI output didn't match format — used heuristic",
                    ai_generated=False,
                    model=model,
                    error=f"AI output: {result.output[:150]}"
                )
        else:
            logger.error(f"Claude Code dispatch failed: {result.error_message}")
            files = [{"path": f.get("path", ""), "status": f.get("status", "M")} for f in uncommitted]
            message, summary = _generate_commit_message(files)
            return AIGenerateMessageResponse(
                message=message,
                files=file_list,
                summary="AI generation failed - used heuristic",
                ai_generated=False,
                error=result.error_message or "Claude Code dispatch failed"
            )

    except Exception as e:
        logger.exception(f"Failed to generate AI commit message: {e}")
        files = [{"path": f.get("path", ""), "status": f.get("status", "M")} for f in uncommitted]
        message, summary = _generate_commit_message(files)
        return AIGenerateMessageResponse(
            message=message,
            files=file_list,
            summary="AI generation error - used heuristic",
            ai_generated=False,
            error=str(e)
        )


@router.post("/{project_id:path}/quick-commit")
async def quick_commit(project_id: str) -> QuickCommitResponse:
    """Stage all changes, generate message, and commit in one fast operation"""
    if not CORE_AVAILABLE:
        return QuickCommitResponse(
            success=False,
            message="Core modules not available"
        )

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        git = GitUtils(project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Not a git repository: {e}")

    # Get files before commit
    uncommitted = git.uncommitted_files_with_lines()
    if not uncommitted:
        return QuickCommitResponse(
            success=False,
            message="No changes to commit",
            files_committed=0
        )

    files = [{"path": f.get("path", ""), "status": f.get("status", "M")} for f in uncommitted]
    commit_message, _ = _generate_commit_message(files)

    # Stage and commit
    success, result_message, commit_hash = git.commit_all(commit_message)

    return QuickCommitResponse(
        success=success,
        message=result_message,
        commit_message=commit_message if success else None,
        hash=commit_hash,
        files_committed=len(files) if success else 0
    )


@router.post("/{project_id:path}/stage")
async def stage_files(project_id: str, request: StageRequest) -> StageResponse:
    """Stage specific files"""
    if not CORE_AVAILABLE:
        return StageResponse(success=False, message="Core modules not available")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        git = GitUtils(project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Not a git repository: {e}")

    success, message, staged = git.stage_files(request.files)
    return StageResponse(success=success, message=message, staged=staged)


@router.post("/{project_id:path}/stage-all")
async def stage_all(project_id: str) -> ActionResponse:
    """Stage all changes"""
    if not CORE_AVAILABLE:
        return ActionResponse(success=False, message="Core modules not available")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        git = GitUtils(project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Not a git repository: {e}")

    success, message = git.stage_all()
    return ActionResponse(success=success, message=message)


@router.post("/{project_id:path}/unstage")
async def unstage_files(project_id: str, request: StageRequest) -> UnstageResponse:
    """Unstage specific files"""
    if not CORE_AVAILABLE:
        return UnstageResponse(success=False, message="Core modules not available")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        git = GitUtils(project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Not a git repository: {e}")

    success, message, unstaged = git.unstage_files(request.files)
    return UnstageResponse(success=success, message=message, unstaged=unstaged)


@router.post("/{project_id:path}/unstage-all")
async def unstage_all(project_id: str) -> ActionResponse:
    """Unstage all staged changes"""
    if not CORE_AVAILABLE:
        return ActionResponse(success=False, message="Core modules not available")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        git = GitUtils(project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Not a git repository: {e}")

    success, message = git.unstage_all()
    return ActionResponse(success=success, message=message)


@router.post("/{project_id:path}/commit-staged")
async def commit_staged(project_id: str, request: CommitStagedRequest) -> ActionResponse:
    """Commit only staged changes (does not auto-stage)"""
    if not CORE_AVAILABLE:
        return ActionResponse(success=False, message="Core modules not available")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        git = GitUtils(project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Not a git repository: {e}")

    success, message, commit_hash = git.commit_staged(request.message)
    return ActionResponse(success=success, message=message, hash=commit_hash)


@router.post("/{project_id:path}/discard")
async def discard_file(project_id: str, request: DiscardRequest) -> ActionResponse:
    """Discard changes to a file (restore to last commit)"""
    if not CORE_AVAILABLE:
        return ActionResponse(success=False, message="Core modules not available")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        git = GitUtils(project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Not a git repository: {e}")

    success, message = git.discard_file(request.file)
    return ActionResponse(success=success, message=message)


@router.delete("/{project_id:path}/untracked")
async def delete_untracked(project_id: str, request: DiscardRequest) -> ActionResponse:
    """Delete an untracked file"""
    if not CORE_AVAILABLE:
        return ActionResponse(success=False, message="Core modules not available")

    project_path = _get_project_path(project_id)
    if not project_path:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        git = GitUtils(project_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Not a git repository: {e}")

    success, message = git.delete_untracked(request.file)
    return ActionResponse(success=success, message=message)
