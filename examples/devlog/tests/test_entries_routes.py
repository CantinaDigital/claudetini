"""Tests for time entry API endpoints."""

import pytest
from fastapi.testclient import TestClient

from devlog.app import app
from devlog.models import Project
from devlog import database


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def project_id(test_db):
    project = Project(name="Route Test Project")
    created = database.create_project(project)
    return created.id


class TestEntryRoutes:
    def test_list_entries_empty(self, client):
        response = client.get("/api/v1/entries")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_entry(self, client, project_id):
        data = {
            "project_id": project_id,
            "description": "Test task",
            "duration_minutes": 60,
            "tags": ["test"],
        }
        response = client.post("/api/v1/entries", json=data)
        assert response.status_code == 201
        assert response.json()["description"] == "Test task"

    def test_get_entry(self, client, project_id):
        # Create first
        data = {
            "project_id": project_id,
            "description": "Fetch me",
            "duration_minutes": 30,
            "tags": [],
        }
        created = client.post("/api/v1/entries", json=data).json()

        # Then fetch
        response = client.get(f"/api/v1/entries/{created['id']}")
        assert response.status_code == 200
        assert response.json()["description"] == "Fetch me"

    def test_get_nonexistent_entry(self, client):
        response = client.get("/api/v1/entries/nonexistent")
        assert response.status_code == 404

    def test_delete_entry(self, client, project_id):
        data = {
            "project_id": project_id,
            "description": "Delete me",
            "duration_minutes": 15,
            "tags": [],
        }
        created = client.post("/api/v1/entries", json=data).json()

        response = client.delete(f"/api/v1/entries/{created['id']}")
        assert response.status_code == 204
