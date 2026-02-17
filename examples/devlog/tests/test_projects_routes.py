"""Tests for project API endpoints."""

import pytest
from fastapi.testclient import TestClient

from devlog.app import app


@pytest.fixture
def client():
    return TestClient(app)


class TestProjectRoutes:
    def test_list_projects_empty(self, client):
        response = client.get("/api/v1/projects")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_project(self, client):
        data = {
            "name": "Test Project",
            "description": "A test project",
            "color": "#FF5733",
        }
        response = client.post("/api/v1/projects", json=data)
        assert response.status_code == 201
        assert response.json()["name"] == "Test Project"

    def test_get_project(self, client):
        data = {"name": "Fetch Project"}
        created = client.post("/api/v1/projects", json=data).json()

        response = client.get(f"/api/v1/projects/{created['id']}")
        assert response.status_code == 200
        assert response.json()["name"] == "Fetch Project"

    def test_delete_project(self, client):
        data = {"name": "Delete Project"}
        created = client.post("/api/v1/projects", json=data).json()

        response = client.delete(f"/api/v1/projects/{created['id']}")
        assert response.status_code == 204
