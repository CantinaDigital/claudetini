"""Product Map API endpoints.

Uses Claude Code CLI to semantically analyze a project at the product level
and produce a feature-centric product map.
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.agents.dispatcher import dispatch_task
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


# ── In-memory cache ───────────────────────────────────────────────────

_product_map_cache: dict[str, ProductMapResponse] = {}


# ── Helpers ───────────────────────────────────────────────────────────

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


def _build_analysis_prompt(project_path: Path) -> str:
    """Build the Claude prompt for product map analysis."""
    return f"""Analyze the project at {project_path} and produce a product-level feature map as JSON.

Read the project's source code, CLAUDE.md, ROADMAP.md (if present), and README to understand the product.

For each user-facing feature or major capability, produce an entry with:
- name: human-readable product concept name (not code-level, e.g. "User Authentication" not "AuthController")
- status: "active" | "planned" | "deprecated"
- readiness: 0-100 based on tests, error handling, docs, edge cases
- desc: what this feature does for the user (1-2 sentences)
- files: approximate number of source files implementing it
- tests: approximate number of test files/functions covering it
- integrations: list of external services it calls (e.g. ["GitHub API", "SQLite"])
- roadmapRef: closest ROADMAP.md milestone reference if any, or null
- lastTouched: relative time from git log (e.g. "2 days ago", "3 weeks ago")
- momentum: {{ "commits": N, "period": "this week" or "this month" }}
- readinessDetail: [{{dim: "Tests", have: "3 unit tests", need: "Integration tests"}}, ...]
  Dimensions: Tests, Error handling, Docs, Edge cases
- lacks: specific gaps to production readiness (e.g. ["No rate limiting", "Missing input validation"])
- dependsOn: other feature names this depends on
- dependedBy: feature names that depend on this

Output ONLY a valid JSON array of feature objects. No markdown, no explanation, no code fences.
Start with [ and end with ]."""


def _parse_features_json(output: str) -> list[dict]:
    """Extract JSON array from Claude's output."""
    # Try direct parse first
    text = output.strip()
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Try to find JSON array in the output
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


# ── Endpoints ─────────────────────────────────────────────────────────

@router.post("/scan", response_model=ProductMapResponse)
async def scan_product_map(request: ProductMapScanRequest) -> ProductMapResponse:
    """Dispatch Claude to analyze a project and produce a product-level feature map.

    This runs Claude Code CLI with a structured prompt to analyze the project.
    Results are cached in-memory and on disk.
    """
    project_path = Path(request.project_path).resolve()
    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"Project path not found: {project_path}")
    if not project_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {project_path}")

    logger.info("Starting product map scan for %s", project_path)

    prompt = _build_analysis_prompt(project_path)

    try:
        result = dispatch_task(
            prompt=prompt,
            working_dir=project_path,
            timeout_seconds=180,
        )
    except Exception as exc:
        logger.exception("Product map dispatch failed for %s", project_path)
        raise HTTPException(status_code=500, detail=f"Dispatch failed: {exc}")

    if not result.success:
        error_msg = result.error_message or "Claude dispatch failed"
        if result.token_limit_reached:
            error_msg = "Claude token limit reached. Try again later."
        raise HTTPException(status_code=500, detail=error_msg)

    if not result.output:
        raise HTTPException(status_code=500, detail="No output from Claude")

    # Parse the JSON output
    try:
        features_raw = _parse_features_json(result.output)
    except ValueError as exc:
        logger.error("Failed to parse product map JSON: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse Claude output as JSON: {exc}",
        )

    # Convert to response models
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

    response = ProductMapResponse(
        project_path=str(project_path),
        generated_at=datetime.now(UTC).isoformat(),
        features=features,
        avg_readiness=avg_readiness,
    )

    _save_cached(project_path, response)

    logger.info(
        "Product map scan complete for %s — %d features, avg readiness %d%%",
        project_path, len(features), avg_readiness,
    )

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
