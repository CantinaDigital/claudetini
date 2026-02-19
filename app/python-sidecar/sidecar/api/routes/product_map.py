"""Product Map API endpoints.

Uses Claude Code CLI to semantically analyze a project at the product level
and produce a feature-centric product map.

Scan runs as a background task. The frontend polls GET /scan/status for progress.

Supports smart diffing: on re-scan, if a cached product map exists and only
some files changed, sends a targeted delta prompt to Claude that includes the
existing map + changed file list, producing results much faster than a full scan.
"""

import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.core.runtime import project_id_for_path, project_runtime_dir

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/product-map", tags=["product-map"])

# ── Request / Response Models ─────────────────────────────────────────

class ProductMapScanRequest(BaseModel):
    """Request body for product map scan."""
    project_path: str


class ProductFeatureResponse(BaseModel):
    """A single product-level feature."""
    name: str
    status: str  # "active" | "planned" | "deprecated"
    readiness: int  # 0-100
    desc: str
    integrations: list[str] = []
    files: int = 0
    tests: int = 0
    roadmapRef: str | None = None
    lastTouched: str = ""
    momentum: dict = {}  # {commits: int, period: str}
    trend: int = 0
    lastSession: str | None = None
    readinessDetail: list[dict] = []  # [{dim, have, need}]
    lacks: list[str] = []
    dependsOn: list[str] = []
    dependedBy: list[str] = []


class ProductMapResponse(BaseModel):
    """Full product map response."""
    project_path: str
    generated_at: str
    features: list[ProductFeatureResponse]
    avg_readiness: int
    commit_hash: str | None = None
    scan_mode: str | None = None  # "full" | "delta" | "cached"


# ── In-memory cache ───────────────────────────────────────────────────

_product_map_cache: dict[str, ProductMapResponse] = {}


# ── Background job tracking ──────────────────────────────────────────

@dataclass
class _ScanJob:
    """Tracks a running product map scan."""
    status: str = "running"  # running | done | error
    progress: str = "Starting..."
    output_lines: list[str] = field(default_factory=list)
    result: ProductMapResponse | None = None
    error: str | None = None
    task: asyncio.Task | None = None


# Keyed by resolved project path
_scan_jobs: dict[str, _ScanJob] = {}


# ── Git helpers ──────────────────────────────────────────────────────

def _get_git_head(project_path: Path) -> str | None:
    """Get current HEAD commit hash, or None if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_path, capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _get_changed_files(project_path: Path, from_commit: str, to_commit: str) -> set[str] | None:
    """Get files changed between two commits. Returns None on error."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", from_commit, to_commit],
            cwd=project_path, capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        lines = result.stdout.strip()
        return set(lines.splitlines()) if lines else set()
    except Exception:
        return None


# ── Snapshot persistence ─────────────────────────────────────────────

def _get_snapshot_path(project_path: Path) -> Path:
    """Get path to the product map snapshot metadata file."""
    project_id = project_id_for_path(project_path)
    runtime_dir = project_runtime_dir(project_id)
    return runtime_dir / "product-map-snapshot.json"


def _load_snapshot(project_path: Path) -> dict | None:
    """Load the last product map scan snapshot."""
    path = _get_snapshot_path(project_path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_snapshot(project_path: Path, commit: str | None) -> None:
    """Save snapshot metadata after a scan."""
    path = _get_snapshot_path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "commit": commit,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    try:
        path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    except Exception:
        logger.warning("Failed to save product map snapshot to %s", path)


# ── Cache helpers ────────────────────────────────────────────────────

def _get_cache_path(project_path: Path) -> Path:
    """Get the on-disk cache path for a project's product map."""
    project_id = project_id_for_path(project_path)
    runtime_dir = project_runtime_dir(project_id)
    return runtime_dir / "product-map.json"


def _load_cached(project_path: Path) -> ProductMapResponse | None:
    """Load product map from in-memory cache or disk."""
    cache_key = str(project_path)

    # In-memory first
    if cache_key in _product_map_cache:
        return _product_map_cache[cache_key]

    # Disk cache
    cache_file = _get_cache_path(project_path)
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            response = ProductMapResponse(**data)
            _product_map_cache[cache_key] = response
            return response
        except Exception:
            logger.warning("Failed to load cached product map from %s", cache_file)

    return None


def _save_cached(project_path: Path, response: ProductMapResponse) -> None:
    """Save product map to both in-memory and disk cache."""
    cache_key = str(project_path)
    _product_map_cache[cache_key] = response

    cache_file = _get_cache_path(project_path)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        cache_file.write_text(response.model_dump_json(indent=2), encoding="utf-8")
    except Exception:
        logger.warning("Failed to save product map cache to %s", cache_file)


# ── Local context gathering ──────────────────────────────────────────

def _read_file_safe(path: Path, max_chars: int = 8000) -> str:
    """Read a file's contents, truncated if too large."""
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_chars:
            return text[:max_chars] + "\n... (truncated)"
        return text
    except Exception:
        return ""


def _get_recent_git_log(project_path: Path, limit: int = 30) -> str:
    """Get recent git log summary."""
    try:
        result = subprocess.run(
            ["git", "log", f"--max-count={limit}", "--format=%h %s (%ar)", "--no-merges"],
            cwd=project_path, capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _get_directory_tree(project_path: Path, max_depth: int = 3) -> str:
    """Get a directory structure summary, excluding common noise."""
    ignore = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
              "build", ".next", ".cache", "coverage", ".tox", "target", ".mypy_cache"}
    lines: list[str] = []

    def _walk(path: Path, depth: int, prefix: str) -> None:
        if depth > max_depth or len(lines) > 200:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return
        dirs = [e for e in entries if e.is_dir() and e.name not in ignore and not e.name.startswith(".")]
        files = [e for e in entries if e.is_file()]
        for d in dirs:
            lines.append(f"{prefix}{d.name}/")
            _walk(d, depth + 1, prefix + "  ")
        for f in files[:20]:  # cap files per dir
            lines.append(f"{prefix}{f.name}")
        if len(files) > 20:
            lines.append(f"{prefix}... and {len(files) - 20} more files")

    _walk(project_path, 0, "")
    return "\n".join(lines[:300])


def _gather_local_context(project_path: Path) -> str:
    """Pre-gather project context locally to avoid Claude reading everything."""
    sections: list[str] = []

    # Project docs
    for name in ["CLAUDE.md", "README.md", "README", "readme.md"]:
        content = _read_file_safe(project_path / name, max_chars=6000)
        if content:
            sections.append(f"=== {name} ===\n{content}")
            break  # only include first README found

    claude_md = _read_file_safe(project_path / "CLAUDE.md", max_chars=6000)
    if claude_md and not any("CLAUDE.md" in s for s in sections):
        sections.insert(0, f"=== CLAUDE.md ===\n{claude_md}")

    # Roadmap
    for rpath in [".claude/planning/ROADMAP.md", "ROADMAP.md", "docs/ROADMAP.md"]:
        content = _read_file_safe(project_path / rpath, max_chars=4000)
        if content:
            sections.append(f"=== Roadmap ===\n{content}")
            break

    # Directory structure
    tree = _get_directory_tree(project_path)
    if tree:
        sections.append(f"=== Directory Structure ===\n{tree}")

    # Git log
    log = _get_recent_git_log(project_path)
    if log:
        sections.append(f"=== Recent Git Log (last 30 commits) ===\n{log}")

    # Package manifests (for dependency/integration hints)
    for mf in ["package.json", "pyproject.toml", "Cargo.toml", "go.mod"]:
        content = _read_file_safe(project_path / mf, max_chars=3000)
        if content:
            sections.append(f"=== {mf} ===\n{content}")

    return "\n\n".join(sections)


# ── Prompts ──────────────────────────────────────────────────────────

_FEATURE_SCHEMA = """For each user-facing feature or major capability, produce an entry with:
- name: human-readable product concept name (not code-level, e.g. "User Authentication" not "AuthController")
- status: "active" | "planned" | "deprecated"
- readiness: 0-100 based on tests, error handling, docs, edge cases
- desc: what this feature does for the user (1-2 sentences)
- files: approximate number of source files implementing it
- tests: approximate number of test files/functions covering it
- integrations: list of external services it calls (e.g. ["GitHub API", "SQLite"])
- roadmapRef: closest ROADMAP.md milestone reference if any, or null
- lastTouched: relative time from git log (e.g. "2 days ago", "3 weeks ago")
- momentum: { "commits": N, "period": "this week" or "this month" }
- readinessDetail: [{"dim": "Tests", "have": "3 unit tests", "need": "Integration tests"}, ...]
  Dimensions: Tests, Error handling, Docs, Edge cases
- lacks: specific gaps to production readiness (e.g. ["No rate limiting", "Missing input validation"])
- dependsOn: other feature names this depends on
- dependedBy: feature names that depend on this"""


def _build_full_analysis_prompt(project_path: Path) -> str:
    """Build the Claude prompt with pre-gathered local context."""
    context = _gather_local_context(project_path)

    return f"""Produce a product-level feature map as JSON for the project at {project_path}.

I have pre-gathered the project context below. Use this to understand the project's structure, features, and status. You may read a few specific source files if needed to clarify details, but DO NOT attempt to read all source files — use the context provided.

{context}

{_FEATURE_SCHEMA}

Output ONLY a valid JSON array of feature objects. No markdown, no explanation, no code fences.
Start with [ and end with ]."""


def _build_delta_prompt(
    project_path: Path,
    changed_files: set[str],
    existing_features: list[dict],
) -> str:
    """Build a targeted delta prompt that updates only affected features."""
    changed_list = "\n".join(f"  - {f}" for f in sorted(changed_files)[:100])
    existing_json = json.dumps(existing_features, indent=2)

    return f"""You have a previous product map for the project at {project_path}.

The following files have changed since the last scan:
{changed_list}

Here is the existing product map (JSON array):
{existing_json}

Your task:
1. Read ONLY the changed files listed above to understand what changed.
2. Update any features affected by those changes (readiness, status, files count, tests, lacks, momentum, lastTouched, readinessDetail, etc.)
3. Add any NEW features that the changes introduced.
4. Remove any features that no longer exist due to the changes.
5. Leave unchanged features exactly as they are.

Output ONLY the complete updated JSON array of ALL features (both changed and unchanged). No markdown, no explanation, no code fences.
Start with [ and end with ]."""


# ── CLI runner ───────────────────────────────────────────────────────

def _parse_features_json(output: str) -> list[dict]:
    """Extract JSON array from Claude's output."""
    text = output.strip()
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            result = json.loads(text[start:end + 1])
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    raise ValueError("Could not parse JSON array from Claude output")


def _build_product_map(
    project_path: Path,
    output: str,
    commit_hash: str | None,
    scan_mode: str,
) -> ProductMapResponse:
    """Parse Claude's output and build a ProductMapResponse."""
    features_raw = _parse_features_json(output)

    features: list[ProductFeatureResponse] = []
    for f in features_raw:
        try:
            features.append(ProductFeatureResponse(
                name=f.get("name", "Unknown"),
                status=f.get("status", "active"),
                readiness=int(f.get("readiness", 0)),
                desc=f.get("desc", ""),
                integrations=f.get("integrations", []),
                files=int(f.get("files", 0)),
                tests=int(f.get("tests", 0)),
                roadmapRef=f.get("roadmapRef"),
                lastTouched=f.get("lastTouched", ""),
                momentum=f.get("momentum", {}),
                trend=int(f.get("trend", 0)),
                lastSession=f.get("lastSession"),
                readinessDetail=f.get("readinessDetail", []),
                lacks=f.get("lacks", []),
                dependsOn=f.get("dependsOn", []),
                dependedBy=f.get("dependedBy", []),
            ))
        except Exception:
            logger.warning("Skipping malformed feature: %s", f.get("name", "?"))

    avg_readiness = (
        round(sum(f.readiness for f in features) / len(features))
        if features else 0
    )

    return ProductMapResponse(
        project_path=str(project_path),
        generated_at=datetime.now(UTC).isoformat(),
        features=features,
        avg_readiness=avg_readiness,
        commit_hash=commit_hash,
        scan_mode=scan_mode,
    )


async def _run_cli(project_path: Path, prompt: str, job: _ScanJob) -> str | None:
    """Run the Claude CLI with a prompt. Returns output string or None on failure."""
    # Using list form with create_subprocess_exec prevents shell injection
    command = ["claude", "--permission-mode", "acceptEdits", "-p", prompt]

    # Remove ANTHROPIC_API_KEY to force OAuth (matches sync dispatcher)
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)

    # create_subprocess_exec passes args directly — no shell involved
    proc = await asyncio.create_subprocess_exec(
        *command,
        cwd=project_path,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )

    logger.info("Product map CLI started (pid %s) for %s", proc.pid, project_path)

    # communicate() waits for process exit AND drains the pipe fully
    try:
        stdout_data, _ = await asyncio.wait_for(
            proc.communicate(),
            timeout=600,
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        job.status = "error"
        job.error = "Scan timed out after 10 minutes"
        logger.warning("Product map CLI timed out for %s", project_path)
        return None

    output = stdout_data.decode("utf-8", errors="replace") if stdout_data else ""
    logger.info(
        "Product map CLI finished (exit=%s, %d bytes) for %s",
        proc.returncode, len(output), project_path,
    )

    if proc.returncode != 0:
        error_line = ""
        for line in output.splitlines():
            stripped = line.strip()
            if stripped:
                error_line = stripped[:200]
                break
        job.status = "error"
        job.error = error_line or f"CLI exited with code {proc.returncode}"
        return None

    return output


# ── Background scan runner ───────────────────────────────────────────

async def _run_scan(project_path: Path, job: _ScanJob, force: bool = False) -> None:
    """Background task: runs full or delta scan based on git diff."""
    current_commit = _get_git_head(project_path)

    try:
        # ── Smart diff: check if we can do a delta scan ───────────
        if not force and current_commit:
            snapshot = _load_snapshot(project_path)
            cached = _load_cached(project_path)

            if snapshot and snapshot.get("commit") and cached:
                prev_commit = snapshot["commit"]

                if prev_commit == current_commit:
                    # Nothing changed — return cached immediately
                    cached.scan_mode = "cached"
                    cached.commit_hash = current_commit
                    job.result = cached
                    job.status = "done"
                    job.progress = "No changes detected — using cached map"
                    logger.info("Product map scan skipped for %s — no changes since %s", project_path, current_commit[:8])
                    return

                # Different commit — check what changed
                changed_files = _get_changed_files(project_path, prev_commit, current_commit)
                if changed_files is not None and len(changed_files) == 0:
                    # Commits differ but no file changes (merge commit, etc.)
                    cached.scan_mode = "cached"
                    cached.commit_hash = current_commit
                    job.result = cached
                    job.status = "done"
                    job.progress = "No file changes — using cached map"
                    _save_snapshot(project_path, current_commit)
                    return

                if changed_files is not None and len(changed_files) <= 200:
                    # Delta scan — send existing map + changed files to Claude
                    job.progress = f"Delta scan: {len(changed_files)} files changed..."
                    logger.info(
                        "Product map delta scan for %s: %d files changed since %s",
                        project_path, len(changed_files), prev_commit[:8],
                    )

                    existing_features = [f.model_dump() for f in cached.features]
                    prompt = _build_delta_prompt(project_path, changed_files, existing_features)

                    output = await _run_cli(project_path, prompt, job)
                    if output is None:
                        return  # error already set by _run_cli

                    try:
                        result = _build_product_map(project_path, output, current_commit, "delta")
                        _save_cached(project_path, result)
                        _save_snapshot(project_path, current_commit)
                        job.result = result
                        job.status = "done"
                        job.progress = f"Delta scan complete — {len(changed_files)} files analyzed"
                        logger.info(
                            "Product map delta scan complete for %s — %d features",
                            project_path, len(result.features),
                        )
                    except ValueError as exc:
                        job.status = "error"
                        job.error = f"Failed to parse delta output: {exc}"
                    return

        # ── Full scan ─────────────────────────────────────────────
        job.progress = "Launching Claude Code CLI..."
        prompt = _build_full_analysis_prompt(project_path)

        job.progress = "Claude is analyzing your project..."
        output = await _run_cli(project_path, prompt, job)
        if output is None:
            return  # error already set by _run_cli

        try:
            result = _build_product_map(project_path, output, current_commit, "full")
            _save_cached(project_path, result)
            _save_snapshot(project_path, current_commit)
            job.result = result
            job.status = "done"
            logger.info(
                "Product map scan complete for %s — %d features",
                project_path, len(result.features),
            )
        except ValueError as exc:
            job.status = "error"
            job.error = f"Failed to parse output: {exc}"

    except FileNotFoundError:
        job.status = "error"
        job.error = "Claude CLI not found. Is 'claude' on your PATH?"
    except Exception as exc:
        logger.exception("Product map background scan failed for %s", project_path)
        job.status = "error"
        job.error = str(exc)


# ── Endpoints ─────────────────────────────────────────────────────────

@router.post("/scan", status_code=202)
async def scan_product_map(
    request: ProductMapScanRequest,
    force: bool = Query(False, description="Force full rescan, ignoring diff cache"),
):
    """Start a product map scan as a background task.

    Returns 202 immediately. Poll GET /scan/status?project_path=... for progress.
    Pass force=true to skip diff logic and do a full re-analysis.
    """
    project_path = Path(request.project_path).resolve()
    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"Project path not found: {project_path}")
    if not project_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {project_path}")

    cache_key = str(project_path)

    # If a scan is already running for this project, just acknowledge
    existing = _scan_jobs.get(cache_key)
    if existing and existing.status == "running":
        return {"status": "running", "progress": existing.progress, "lines": len(existing.output_lines)}

    # Start new background scan
    job = _ScanJob()
    _scan_jobs[cache_key] = job
    job.task = asyncio.create_task(_run_scan(project_path, job, force=force))

    logger.info("Started background product map scan for %s (force=%s)", project_path, force)
    return {"status": "running", "progress": "Starting...", "lines": 0}


@router.get("/scan/status")
async def scan_status(project_path: str):
    """Poll for product map scan progress.

    Returns:
    - status: "running" | "done" | "error" | "idle"
    - progress: human-readable status message
    - lines: number of CLI output lines collected so far
    - result: ProductMapResponse (only when status == "done")
    - error: error message (only when status == "error")
    """
    resolved = str(Path(project_path).resolve())
    job = _scan_jobs.get(resolved)

    if not job:
        return {"status": "idle", "progress": "", "lines": 0}

    response: dict = {
        "status": job.status,
        "progress": job.progress,
        "lines": len(job.output_lines),
    }

    if job.status == "done" and job.result:
        response["result"] = job.result.model_dump()
        # Clean up finished job
        del _scan_jobs[resolved]
    elif job.status == "error":
        response["error"] = job.error or "Unknown error"
        # Clean up failed job
        del _scan_jobs[resolved]

    return response


@router.get("/{project_path:path}", response_model=ProductMapResponse)
async def get_product_map(project_path: str) -> ProductMapResponse:
    """Get a cached product map for a project.

    Returns 404 if no cached map exists. Use POST /scan to generate one.
    """
    resolved = Path(project_path).resolve()
    cached = _load_cached(resolved)

    if not cached:
        raise HTTPException(
            status_code=404,
            detail=f"No product map cached for: {project_path}. Run POST /scan first.",
        )

    return cached
