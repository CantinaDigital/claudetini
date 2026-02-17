"""Project business logic."""

from devlog.models import ProjectCreate, Project
from devlog import database


class ProjectService:
    """Service for managing projects."""

    def create(self, data: ProjectCreate) -> Project:
        """Create a new project."""
        project = Project(
            name=data.name,
            description=data.description,
            color=data.color,
        )
        return database.create_project(project)

    def get(self, project_id: str) -> Project | None:
        """Get a project by ID."""
        return database.get_project(project_id)

    def list_all(self) -> list[Project]:
        """List all projects."""
        return database.list_projects()

    def delete(self, project_id: str) -> bool:
        """Delete a project."""
        return database.delete_project(project_id)
