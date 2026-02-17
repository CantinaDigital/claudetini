"""
Claudetini Backend - FastAPI Server

This server runs as a Tauri sidecar and provides API endpoints
for the React frontend to access project data.
"""

import argparse
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add parent claudetini project to path for core modules
# The app directory is inside claudetini/
# We add the claudetini root (not src) to preserve package hierarchy
# This allows relative imports like "from ..utils" to work properly
_this_file = Path(__file__).resolve()
# Path: .../claudetini/app/python-sidecar/sidecar/api/server.py
# We want: .../claudetini
_claudetini_root = _this_file.parent.parent.parent.parent.parent

# Also try finding it relative to cwd if __file__ doesn't resolve correctly
if not (_claudetini_root / "src" / "core").exists():
    _cwd = Path.cwd().resolve()
    if _cwd.name == "python-sidecar":
        _claudetini_root = _cwd.parent.parent
    elif _cwd.name == "app":
        _claudetini_root = _cwd.parent
    elif _cwd.name == "sidecar" and _cwd.parent.name == "python-sidecar":
        _claudetini_root = _cwd.parent.parent.parent

if (_claudetini_root / "src" / "core").exists():
    # Insert at position 0 to take precedence
    sys.path.insert(0, str(_claudetini_root))
else:
    print(f"WARNING: Could not find claudetini root. Tried: {_claudetini_root}")

from .routes import (
    bootstrap,
    dispatch,
    dispatch_stream,
    gates,
    git,
    intelligence,
    live_sessions,
    logs,
    parallel,
    product_map,
    project,
    readiness,
    reconciliation,
    roadmap,
    timeline,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage server lifecycle — gracefully shut down worker threads on exit."""
    yield
    # Graceful shutdown: signal threads and wait
    from .routes.parallel import _active_threads, _shutdown_event

    _shutdown_event.set()
    for thread in _active_threads:
        thread.join(timeout=10)


app = FastAPI(
    title="Claudetini Backend",
    description="Python backend sidecar for Claudetini dashboard",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration for Tauri
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:5173",
        "http://localhost:1420",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:1420",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
# IMPORTANT: Register reconciliation BEFORE project to avoid route conflicts
# (reconciliation has /{project_id}/reconcile/*, project has catch-all /{project_id})
app.include_router(reconciliation.router, prefix="/api/project", tags=["reconciliation"])
app.include_router(project.router, prefix="/api/project", tags=["project"])
app.include_router(timeline.router, prefix="/api/timeline", tags=["timeline"])
app.include_router(roadmap.router, prefix="/api/roadmap", tags=["roadmap"])
app.include_router(gates.router, prefix="/api/gates", tags=["gates"])
app.include_router(git.router, prefix="/api/git", tags=["git"])
app.include_router(dispatch.router, prefix="/api/dispatch", tags=["dispatch"])
app.include_router(dispatch_stream.router, prefix="/api/dispatch/stream", tags=["dispatch-stream"])
app.include_router(logs.router, prefix="/api/logs", tags=["logs"])
app.include_router(live_sessions.router, prefix="/api/live-sessions", tags=["live-sessions"])
app.include_router(readiness.router, prefix="/api", tags=["readiness"])
app.include_router(bootstrap.router, prefix="/api", tags=["bootstrap"])
app.include_router(parallel.router, prefix="/api/parallel", tags=["parallel"])
app.include_router(intelligence.router, prefix="/api", tags=["intelligence"])
app.include_router(product_map.router, prefix="/api", tags=["product-map"])


@app.get("/health")
def health():
    """Health check endpoint"""
    return {"status": "ok"}


@app.get("/")
def root():
    """Root endpoint with API info"""
    return {
        "name": "Claudetini Backend",
        "version": "1.0.0",
        "docs": "/docs",
    }


def main():
    """Main entry point for the sidecar"""
    parser = argparse.ArgumentParser(description="Claudetini Backend Server")
    parser.add_argument(
        "--port",
        type=int,
        default=9876,
        help="Port to run the server on (default: 9876)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    args = parser.parse_args()

    print(f"Starting Claudetini backend on {args.host}:{args.port}")

    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["access"]["fmt"] = "%(asctime)s %(levelprefix)s %(client_addr)s - \"%(request_line)s\" %(status_code)s"
    log_config["formatters"]["default"]["fmt"] = "%(asctime)s %(levelprefix)s %(message)s"
    log_config["formatters"]["access"]["datefmt"] = "%H:%M:%S"
    log_config["formatters"]["default"]["datefmt"] = "%H:%M:%S"

    uvicorn.run(app, host=args.host, port=args.port, log_level="info", workers=2, log_config=log_config)


if __name__ == "__main__":
    main()
