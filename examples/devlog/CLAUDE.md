# DevLog Development Guide

> A FastAPI application for tracking developer work logs with time entries, project tags, and weekly summaries.

## Project Overview

DevLog is a REST API built with FastAPI and SQLite for tracking developer time entries across projects. It supports time logging, project tagging, weekly/monthly summaries, and Markdown/CSV export.

**Tech Stack:**
- **Framework:** FastAPI 0.109+
- **Database:** SQLite via sqlite3
- **Validation:** Pydantic 2.5+
- **Server:** Uvicorn
- **Testing:** pytest
- **Linting:** Ruff

## Architecture

```
devlog/
├── app.py              # FastAPI application setup
├── models.py           # Pydantic models + dataclasses
├── database.py         # SQLite connection + migrations
├── routes/
│   ├── entries.py      # Time entry CRUD endpoints
│   └── projects.py     # Project CRUD endpoints
├── services/
│   ├── entries.py      # Business logic for entries
│   ├── projects.py     # Business logic for projects
│   └── reports.py      # Summary + export logic
└── utils/
    ├── formatting.py   # Time/date formatting helpers
    └── validation.py   # Input validation utilities
```

## Code Conventions

### Python
- Follow PEP 8
- Use type hints for all function signatures
- Use Pydantic models for request/response schemas
- Use dataclasses for internal data structures
- Prefer f-strings for string formatting
- Use `pathlib.Path` for file operations

### Naming
- snake_case for functions, variables, modules
- PascalCase for classes and Pydantic models
- SCREAMING_SNAKE_CASE for constants

### API Design
- RESTful endpoints under /api/v1/
- Return consistent error responses with detail messages
- Use Pydantic for input validation
- Include pagination for list endpoints

### Testing
- Tests in `tests/` directory
- Use pytest with fixtures in conftest.py
- Mock database connections in tests
- Aim for 70%+ coverage on services

### Error Handling
- Raise HTTPException with appropriate status codes
- Log errors with context
- Return user-friendly error messages

## Commands

```bash
# Run the development server
uvicorn devlog.app:app --reload --port 8000

# Run tests
pytest

# Run linting
ruff check devlog/

# Type checking
mypy devlog/
```

## Dependencies

See `pyproject.toml` for full dependency list.

<!-- claudetini:managed -->
## Current Status
- Active branch: main
- Last updated: 2026-02-16

## What's In Progress
- Milestone 2: API Layer (75% complete)
- Milestone 3: Reporting & Export (25% complete)

## What's Next
- Remaining items in Milestone 2 (pagination, rate limiting)
- Milestone 3 items (monthly summaries, exports)
- Milestone 4: Polish & Deploy

## Progress
- Overall: 14/26 items (54%)
<!-- /claudetini:managed -->
