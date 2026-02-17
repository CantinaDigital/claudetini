"""Tests for entry service."""

import pytest

from devlog.models import TimeEntryCreate
from devlog.services.entries import EntryService


@pytest.fixture
def service():
    return EntryService()


class TestEntryService:
    def test_create_entry(self, service, sample_project):
        data = TimeEntryCreate(
            project_id=sample_project.id,
            description="Service test",
            duration_minutes=45,
            tags=["service"],
        )
        entry = service.create(data)
        assert entry.description == "Service test"
        assert entry.duration_minutes == 45

    def test_get_entry(self, service, sample_entry):
        entry = service.get(sample_entry.id)
        assert entry is not None
        assert entry.id == sample_entry.id

    def test_list_all(self, service, sample_entries):
        entries = service.list_all()
        assert len(entries) == len(sample_entries)

    def test_delete_entry(self, service, sample_entry):
        assert service.delete(sample_entry.id) is True
        assert service.get(sample_entry.id) is None

    def test_get_total_duration(self, service, sample_entries):
        project_id = sample_entries[0].project_id
        total = service.get_total_duration(project_id)
        expected = sum(e.duration_minutes for e in sample_entries)
        assert total == expected
