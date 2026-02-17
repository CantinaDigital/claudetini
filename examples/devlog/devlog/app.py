"""DevLog FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from devlog.database import init_db, close_db
from devlog.routes import entries, projects

# TODO: Move CORS origins to configuration
ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://localhost:3000",
]

logger = logging.getLogger(__name__)

# Optional Sentry integration
try:
    import sentry_sdk
    sentry_sdk.init(dsn="", traces_sample_rate=0.1)
except ImportError:
    pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    init_db()
    yield
    close_db()


app = FastAPI(
    title="DevLog API",
    description="Developer time-tracking API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(entries.router, prefix="/api/v1")
app.include_router(projects.router, prefix="/api/v1")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error("Unhandled error: %s", str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again."},
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}
