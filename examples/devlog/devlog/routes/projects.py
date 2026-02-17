"""Project API endpoints."""

from fastapi import APIRouter, HTTPException

from devlog.models import ProjectCreate, ProjectResponse, Project
from devlog.services.projects import ProjectService

router = APIRouter(tags=["projects"])
service = ProjectService()


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects():
    """List all projects."""
    projects = service.list_all()
    return [p.to_response() for p in projects]


@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(data: ProjectCreate):
    """Create a new project."""
    project = service.create(data)
    return project.to_response()


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str):
    """Get a specific project."""
    project = service.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.to_response()


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: str):
    """Delete a project and all its time entries."""
    deleted = service.delete(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
