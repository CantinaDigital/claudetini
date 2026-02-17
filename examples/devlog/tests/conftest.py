"""Shared test fixtures."""

import os
import tempfile
import pytest

from devlog import database
from devlog.models import TimeEntry, Project, TimeEntryCreate, ProjectCreate


# Test constants
TEST_USER_EMAIL = "test@example.com"
TEST_PROJECT_NAME = "Test Project"


@pytest.fixture(autouse=True)
def test_db(tmp_path):
    """Create a temporary database for each test."""
    db_path = str(tmp_path / "test.db")
    database.init_db(db_path)
    yield db_path
    database.close_db()


@pytest.fixture
def sample_project():
    """Create a sample project."""
    project = Project(
        name=TEST_PROJECT_NAME,
        description="A test project for unit tests",
        color="#FF5733",
    )
    return database.create_project(project)


@pytest.fixture
def sample_entry(sample_project):
    """Create a sample time entry."""
    entry = TimeEntry(
        project_id=sample_project.id,
        description="Wrote unit tests",
        duration_minutes=90,
        tags=["testing", "backend"],
    )
    return database.create_entry(entry)


@pytest.fixture
def sample_entries(sample_project):
    """Create multiple sample time entries."""
    entries = []
    descriptions = [
        ("Set up project structure", 30, ["setup"]),
        ("Implement user model", 60, ["backend", "models"]),
        ("Write API endpoints", 120, ["backend", "api"]),
        ("Add input validation", 45, ["backend", "validation"]),
        ("Fix database migration", 20, ["backend", "bugfix"]),
    ]

    for desc, duration, tags in descriptions:
        entry = TimeEntry(
            project_id=sample_project.id,
            description=desc,
            duration_minutes=duration,
            tags=tags,
        )
        entries.append(database.create_entry(entry))

    return entries
