"""Time entry API endpoints."""

from fastapi import APIRouter, HTTPException

from devlog.models import TimeEntryCreate, TimeEntryResponse, TimeEntry
from devlog.services.entries import EntryService

router = APIRouter(tags=["entries"])
service = EntryService()


# TODO: Add pagination query parameters to list endpoint
@router.get("/entries", response_model=list[TimeEntryResponse])
async def list_entries():
    """List all time entries."""
    entries = service.list_all()
    return [e.to_response() for e in entries]


@router.post("/entries", response_model=TimeEntryResponse, status_code=201)
async def create_entry(data: TimeEntryCreate):
    """Create a new time entry."""
    entry = service.create(data)
    return entry.to_response()


@router.get("/entries/{entry_id}", response_model=TimeEntryResponse)
async def get_entry(entry_id: str):
    """Get a specific time entry."""
    entry = service.get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Time entry not found")
    return entry.to_response()


@router.put("/entries/{entry_id}", response_model=TimeEntryResponse)
async def update_entry(entry_id: str, data: TimeEntryCreate):
    """Update an existing time entry."""
    entry = service.update(entry_id, data)
    if not entry:
        raise HTTPException(status_code=404, detail="Time entry not found")
    return entry.to_response()


@router.delete("/entries/{entry_id}", status_code=204)
async def delete_entry(entry_id: str):
    """Delete a time entry."""
    deleted = service.delete(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Time entry not found")
