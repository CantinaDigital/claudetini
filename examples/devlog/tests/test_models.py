"""Tests for data models."""

import pytest
from pydantic import ValidationError

from devlog.models import (
    TimeEntryCreate,
    TimeEntryResponse,
    ProjectCreate,
    ProjectResponse,
    TimeEntry,
    Project,
)


class TestTimeEntryCreate:
    def test_valid_entry(self):
        entry = TimeEntryCreate(
            project_id="proj-1",
            description="Working on feature",
            duration_minutes=60,
            tags=["backend"],
        )
        assert entry.project_id == "proj-1"
        assert entry.duration_minutes == 60

    def test_empty_description_rejected(self):
        with pytest.raises(ValidationError):
            TimeEntryCreate(
                project_id="proj-1",
                description="",
                duration_minutes=60,
            )

    def test_zero_duration_rejected(self):
        with pytest.raises(ValidationError):
            TimeEntryCreate(
                project_id="proj-1",
                description="Work",
                duration_minutes=0,
            )

    def test_excessive_duration_rejected(self):
        with pytest.raises(ValidationError):
            TimeEntryCreate(
                project_id="proj-1",
                description="Work",
                duration_minutes=1441,
            )

    def test_default_tags_empty(self):
        entry = TimeEntryCreate(
            project_id="proj-1",
            description="Work",
            duration_minutes=30,
        )
        assert entry.tags == []


class TestProjectCreate:
    def test_valid_project(self):
        project = ProjectCreate(name="My Project")
        assert project.name == "My Project"
        assert project.color == "#3B82F6"

    def test_custom_color(self):
        project = ProjectCreate(name="Test", color="#FF5733")
        assert project.color == "#FF5733"

    def test_invalid_color_rejected(self):
        with pytest.raises(ValidationError):
            ProjectCreate(name="Test", color="not-a-color")

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            ProjectCreate(name="")


class TestTimeEntryDataclass:
    def test_default_values(self):
        entry = TimeEntry()
        assert entry.id
        assert entry.duration_minutes == 0
        assert entry.tags == []

    def test_to_response(self):
        entry = TimeEntry(
            project_id="proj-1",
            description="Test",
            duration_minutes=30,
        )
        response = entry.to_response()
        assert isinstance(response, TimeEntryResponse)
        assert response.project_id == "proj-1"


class TestProjectDataclass:
    def test_default_values(self):
        project = Project()
        assert project.id
        assert project.color == "#3B82F6"

    def test_to_response(self):
        project = Project(name="Test Project")
        response = project.to_response()
        assert isinstance(response, ProjectResponse)
        assert response.name == "Test Project"
