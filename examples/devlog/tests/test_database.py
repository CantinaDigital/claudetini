"""Tests for database operations."""

import pytest

from devlog import database
from devlog.models import TimeEntry, Project


class TestEntryOperations:
    def test_create_entry(self, sample_project):
        entry = TimeEntry(
            project_id=sample_project.id,
            description="Test entry",
            duration_minutes=60,
            tags=["test"],
        )
        created = database.create_entry(entry)
        assert created.id == entry.id
        assert created.description == "Test entry"

    def test_get_entry(self, sample_entry):
        fetched = database.get_entry(sample_entry.id)
        assert fetched is not None
        assert fetched.id == sample_entry.id
        assert fetched.description == sample_entry.description

    def test_get_nonexistent_entry(self):
        assert database.get_entry("nonexistent") is None

    def test_list_entries(self, sample_entries):
        entries = database.list_entries()
        assert len(entries) == len(sample_entries)

    def test_list_entries_with_limit(self, sample_entries):
        entries = database.list_entries(limit=2)
        assert len(entries) == 2

    def test_update_entry(self, sample_entry):
        updated = database.update_entry(
            sample_entry.id,
            description="Updated description",
        )
        assert updated is not None
        assert updated.description == "Updated description"

    def test_delete_entry(self, sample_entry):
        assert database.delete_entry(sample_entry.id) is True
        assert database.get_entry(sample_entry.id) is None

    def test_delete_nonexistent_entry(self):
        assert database.delete_entry("nonexistent") is False


class TestProjectOperations:
    def test_create_project(self):
        project = Project(name="New Project", description="A new project")
        created = database.create_project(project)
        assert created.name == "New Project"

    def test_get_project(self, sample_project):
        fetched = database.get_project(sample_project.id)
        assert fetched is not None
        assert fetched.name == sample_project.name

    def test_list_projects(self, sample_project):
        projects = database.list_projects()
        assert len(projects) >= 1

    def test_delete_project(self, sample_project):
        assert database.delete_project(sample_project.id) is True
        assert database.get_project(sample_project.id) is None
