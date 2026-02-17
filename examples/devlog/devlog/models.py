"""Data models for DevLog."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# --- Pydantic Models (API Layer) ---

class TimeEntryCreate(BaseModel):
    """Schema for creating a time entry."""
    project_id: str
    description: str = Field(..., min_length=1, max_length=500)
    duration_minutes: int = Field(..., gt=0, le=1440)
    tags: list[str] = Field(default_factory=list)


class TimeEntryResponse(BaseModel):
    """Schema for time entry API responses."""
    id: str
    project_id: str
    description: str
    duration_minutes: int
    tags: list[str]
    created_at: str
    updated_at: str


class ProjectCreate(BaseModel):
    """Schema for creating a project."""
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    color: str = Field(default="#3B82F6", pattern=r"^#[0-9a-fA-F]{6}$")


class ProjectResponse(BaseModel):
    """Schema for project API responses."""
    id: str
    name: str
    description: str
    color: str
    created_at: str


# --- Dataclasses (Internal) ---

@dataclass
class TimeEntry:
    """Internal representation of a time entry."""
    id: str = field(default_factory=lambda: str(uuid4()))
    project_id: str = ""
    description: str = ""
    duration_minutes: int = 0
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_response(self) -> TimeEntryResponse:
        return TimeEntryResponse(
            id=self.id,
            project_id=self.project_id,
            description=self.description,
            duration_minutes=self.duration_minutes,
            tags=self.tags,
            created_at=self.created_at.isoformat(),
            updated_at=self.updated_at.isoformat(),
        )


@dataclass
class Project:
    """Internal representation of a project."""
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    color: str = "#3B82F6"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_response(self) -> ProjectResponse:
        return ProjectResponse(
            id=self.id,
            name=self.name,
            description=self.description,
            color=self.color,
            created_at=self.created_at.isoformat(),
        )
