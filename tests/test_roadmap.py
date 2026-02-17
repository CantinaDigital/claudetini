"""Tests for roadmap parsing and tracking."""

import pytest
from pathlib import Path

from src.core.roadmap import Roadmap, Milestone, RoadmapItem


class TestRoadmapItem:
    """Tests for RoadmapItem class."""

    def test_from_line_completed(self):
        """Test parsing a completed item."""
        item = RoadmapItem.from_line("- [x] Completed task")
        assert item is not None
        assert item.text == "Completed task"
        assert item.completed is True

    def test_from_line_pending(self):
        """Test parsing a pending item."""
        item = RoadmapItem.from_line("- [ ] Pending task")
        assert item is not None
        assert item.text == "Pending task"
        assert item.completed is False

    def test_from_line_uppercase_x(self):
        """Test parsing with uppercase X."""
        item = RoadmapItem.from_line("- [X] Completed with uppercase")
        assert item is not None
        assert item.completed is True

    def test_from_line_with_asterisk(self):
        """Test parsing with asterisk instead of dash."""
        item = RoadmapItem.from_line("* [x] Using asterisk")
        assert item is not None
        assert item.text == "Using asterisk"

    def test_from_line_invalid(self):
        """Test parsing an invalid line."""
        item = RoadmapItem.from_line("Just some text")
        assert item is None

    def test_from_line_with_leading_spaces(self):
        """Test parsing with leading whitespace."""
        item = RoadmapItem.from_line("  - [ ] Indented task")
        assert item is not None
        assert item.text == "Indented task"

    def test_to_markdown(self):
        """Test converting item back to markdown."""
        item = RoadmapItem(text="My task", completed=True)
        assert item.to_markdown() == "- [x] My task"

        item.completed = False
        assert item.to_markdown() == "- [ ] My task"


class TestMilestone:
    """Tests for Milestone class."""

    def test_progress_empty(self):
        """Test progress with no items."""
        milestone = Milestone(name="Empty")
        assert milestone.total_items == 0
        assert milestone.completed_items == 0
        assert milestone.progress_percent == 0.0

    def test_progress_partial(self):
        """Test progress with some items completed."""
        milestone = Milestone(
            name="Partial",
            items=[
                RoadmapItem(text="Done", completed=True),
                RoadmapItem(text="Pending", completed=False),
            ],
        )
        assert milestone.total_items == 2
        assert milestone.completed_items == 1
        assert milestone.progress_percent == 50.0

    def test_progress_complete(self):
        """Test progress with all items completed."""
        milestone = Milestone(
            name="Complete",
            items=[
                RoadmapItem(text="Done 1", completed=True),
                RoadmapItem(text="Done 2", completed=True),
            ],
        )
        assert milestone.is_complete is True
        assert milestone.progress_percent == 100.0

    def test_is_in_progress(self):
        """Test in-progress status."""
        milestone = Milestone(
            name="In Progress",
            items=[
                RoadmapItem(text="Done", completed=True),
                RoadmapItem(text="Pending", completed=False),
            ],
        )
        assert milestone.is_in_progress is True
        assert milestone.is_complete is False
        assert milestone.is_not_started is False

    def test_is_not_started(self):
        """Test not-started status."""
        milestone = Milestone(
            name="Not Started",
            items=[
                RoadmapItem(text="Pending 1", completed=False),
                RoadmapItem(text="Pending 2", completed=False),
            ],
        )
        assert milestone.is_not_started is True
        assert milestone.is_in_progress is False


class TestRoadmap:
    """Tests for Roadmap class."""

    def test_parse_basic(self, sample_roadmap_file):
        """Test parsing a basic roadmap file."""
        roadmap = Roadmap.parse(sample_roadmap_file)

        assert roadmap.title == "Project Roadmap"
        assert len(roadmap.milestones) == 3

    def test_parse_milestones(self, sample_roadmap_file):
        """Test that milestones are parsed correctly."""
        roadmap = Roadmap.parse(sample_roadmap_file)

        assert roadmap.milestones[0].name == "Milestone 1: Core Features"
        assert roadmap.milestones[1].name == "Milestone 2: UI Components"
        assert roadmap.milestones[2].name == "Milestone 3: Polish"

    def test_parse_items(self, sample_roadmap_file):
        """Test that items are parsed correctly."""
        roadmap = Roadmap.parse(sample_roadmap_file)

        milestone1 = roadmap.milestones[0]
        assert len(milestone1.items) == 4
        assert milestone1.items[0].text == "User authentication"
        assert milestone1.items[0].completed is True
        assert milestone1.items[2].text == "API endpoints"
        assert milestone1.items[2].completed is False

    def test_overall_progress(self, sample_roadmap_file):
        """Test overall progress calculation."""
        roadmap = Roadmap.parse(sample_roadmap_file)

        # 2 completed out of 10 total = 20%
        assert roadmap.completed_items == 2
        assert roadmap.total_items == 10
        assert roadmap.progress_percent == 20.0

    def test_find_next_incomplete(self, sample_roadmap_file):
        """Test finding the next incomplete item."""
        roadmap = Roadmap.parse(sample_roadmap_file)

        result = roadmap.find_next_incomplete()
        assert result is not None

        m_idx, i_idx, item = result
        assert m_idx == 0  # First milestone
        assert i_idx == 2  # Third item (first two are complete)
        assert item.text == "API endpoints"

    def test_find_items_matching(self, sample_roadmap_file):
        """Test finding items by text match."""
        roadmap = Roadmap.parse(sample_roadmap_file)

        matches = roadmap.find_items_matching("auth")
        assert len(matches) == 1
        assert matches[0][2].text == "User authentication"

    def test_mark_item_complete(self, sample_roadmap_file):
        """Test marking an item as complete."""
        roadmap = Roadmap.parse(sample_roadmap_file)

        # Mark "API endpoints" as complete
        roadmap.mark_item_complete(0, 2)

        assert roadmap.milestones[0].items[2].completed is True
        assert roadmap.completed_items == 3

    def test_to_markdown(self, sample_roadmap_file):
        """Test converting roadmap back to markdown."""
        roadmap = Roadmap.parse(sample_roadmap_file)

        markdown = roadmap.to_markdown()

        assert "# Project Roadmap" in markdown
        assert "## Milestone 1: Core Features" in markdown
        assert "- [x] User authentication" in markdown
        assert "- [ ] API endpoints" in markdown

    def test_parse_file_not_found(self, temp_dir):
        """Test parsing a non-existent file."""
        with pytest.raises(FileNotFoundError):
            Roadmap.parse(temp_dir / "nonexistent.md")
