# DevLog Architecture

## Overview

DevLog follows a layered architecture with clear separation between HTTP handling, business logic, and data access.

## Layers

### 1. Routes (HTTP Layer)
- `routes/entries.py` — Time entry CRUD endpoints
- `routes/projects.py` — Project CRUD endpoints
- Handles request/response serialization via Pydantic
- Delegates all business logic to services

### 2. Services (Business Logic)
- `services/entries.py` — Entry creation, validation, duration calculation
- `services/projects.py` — Project management, tag handling
- `services/reports.py` — Aggregation, summary generation, export
- Contains all business rules and validation logic

### 3. Database (Data Access)
- `database.py` — SQLite connection management, migrations
- `models.py` — Pydantic models for API + dataclasses for internal use
- Direct SQL via sqlite3 (no ORM)

### 4. Utilities
- `utils/formatting.py` — Date/time formatting, duration display
- `utils/validation.py` — Input sanitization, range checks

## Data Flow

```
HTTP Request → Route → Service → Database
                                    ↓
HTTP Response ← Route ← Service ← Result
```

## Database Schema

### time_entries
| Column | Type | Description |
|--------|------|-------------|
| id | TEXT | UUID primary key |
| project_id | TEXT | FK to projects |
| description | TEXT | What was done |
| duration_minutes | INTEGER | Time spent |
| tags | TEXT | Comma-separated tags |
| created_at | TEXT | ISO timestamp |
| updated_at | TEXT | ISO timestamp |

### projects
| Column | Type | Description |
|--------|------|-------------|
| id | TEXT | UUID primary key |
| name | TEXT | Project name |
| description | TEXT | Project description |
| color | TEXT | Display color hex |
| created_at | TEXT | ISO timestamp |

## Design Decisions

- **SQLite over PostgreSQL:** Simplicity for a single-user tool. No server to manage.
- **No ORM:** Direct SQL keeps the data layer transparent and debuggable.
- **Pydantic for API, dataclasses for internals:** Clear boundary between external and internal data structures.
- **Service layer:** Keeps routes thin and business logic testable.
