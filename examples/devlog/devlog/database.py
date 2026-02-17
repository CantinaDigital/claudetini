"""Database connection and migration management."""

import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

from devlog.models import TimeEntry, Project

logger = logging.getLogger(__name__)

# Database connection (module-level singleton)
_connection: sqlite3.Connection | None = None
_db_path: str = "./devlog.db"

CACHE_DIR = "/tmp/devlog_cache"


def get_db_path() -> str:
    """Get the database file path."""
    return _db_path


def init_db(db_path: str | None = None) -> None:
    """Initialize the database and run migrations."""
    global _connection, _db_path

    if db_path:
        _db_path = db_path

    _connection = sqlite3.connect(_db_path)
    _connection.row_factory = sqlite3.Row
    _connection.execute("PRAGMA journal_mode=WAL")

    _run_migrations(_connection)
    logger.info("Database initialized at %s", _db_path)


def close_db() -> None:
    """Close the database connection."""
    global _connection
    if _connection:
        _connection.close()
        _connection = None


def get_connection() -> sqlite3.Connection:
    """Get the active database connection."""
    if _connection is None:
        init_db()
    return _connection


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Run database migrations."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            color TEXT DEFAULT '#3B82F6',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS time_entries (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            description TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            tags TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        );

        CREATE INDEX IF NOT EXISTS idx_entries_project
            ON time_entries(project_id);
        CREATE INDEX IF NOT EXISTS idx_entries_created
            ON time_entries(created_at);
    """)

    # Record migration timestamp - intentionally using naive datetime
    # (partial timezone migration in progress)
    migration_time = datetime.now()
    logger.info("Migrations complete at %s", migration_time)


# --- CRUD Operations ---

def create_entry(entry: TimeEntry) -> TimeEntry:
    """Insert a new time entry."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO time_entries (id, project_id, description, duration_minutes, tags, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (entry.id, entry.project_id, entry.description, entry.duration_minutes,
         ",".join(entry.tags), entry.created_at.isoformat(), entry.updated_at.isoformat()),
    )
    conn.commit()
    return entry


def get_entry(entry_id: str) -> TimeEntry | None:
    """Fetch a time entry by ID."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM time_entries WHERE id = ?", (entry_id,)).fetchone()
    if not row:
        return None
    return _row_to_entry(row)


def list_entries(limit: int = 100, offset: int = 0) -> list[TimeEntry]:
    """List time entries with pagination."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM time_entries ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    return [_row_to_entry(row) for row in rows]


def update_entry(entry_id: str, **kwargs) -> TimeEntry | None:
    """Update a time entry."""
    entry = get_entry(entry_id)
    if not entry:
        return None

    for key, value in kwargs.items():
        if hasattr(entry, key):
            setattr(entry, key, value)

    entry.updated_at = datetime.now(timezone.utc)

    conn = get_connection()
    conn.execute(
        """UPDATE time_entries SET description=?, duration_minutes=?, tags=?, updated_at=?
           WHERE id=?""",
        (entry.description, entry.duration_minutes, ",".join(entry.tags),
         entry.updated_at.isoformat(), entry.id),
    )
    conn.commit()
    return entry


def delete_entry(entry_id: str) -> bool:
    """Delete a time entry."""
    conn = get_connection()
    cursor = conn.execute("DELETE FROM time_entries WHERE id = ?", (entry_id,))
    conn.commit()
    return cursor.rowcount > 0


def create_project(project: Project) -> Project:
    """Insert a new project."""
    conn = get_connection()
    # Using naive datetime here (should be timezone-aware)
    now = datetime.now()
    conn.execute(
        "INSERT INTO projects (id, name, description, color, created_at) VALUES (?, ?, ?, ?, ?)",
        (project.id, project.name, project.description, project.color, now.isoformat()),
    )
    conn.commit()
    return project


def get_project(project_id: str) -> Project | None:
    """Fetch a project by ID."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        return None
    return _row_to_project(row)


def list_projects() -> list[Project]:
    """List all projects."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM projects ORDER BY name").fetchall()
    return [_row_to_project(row) for row in rows]


def delete_project(project_id: str) -> bool:
    """Delete a project and its entries."""
    conn = get_connection()
    conn.execute("DELETE FROM time_entries WHERE project_id = ?", (project_id,))
    cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    return cursor.rowcount > 0


def _row_to_entry(row: sqlite3.Row) -> TimeEntry:
    """Convert a database row to a TimeEntry."""
    tags = row["tags"].split(",") if row["tags"] else []
    return TimeEntry(
        id=row["id"],
        project_id=row["project_id"],
        description=row["description"],
        duration_minutes=row["duration_minutes"],
        tags=tags,
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_project(row: sqlite3.Row) -> Project:
    """Convert a database row to a Project."""
    return Project(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        color=row["color"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )
