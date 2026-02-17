"""Tests for managed CLAUDE.md lifecycle."""

from src.core.claude_md_manager import END_MARKER, START_MARKER, ClaudeMdManager
from src.core.project import Project


def test_claude_md_manager_creates_managed_block(temp_dir):
    project = Project.from_path(temp_dir)
    manager = ClaudeMdManager(project)
    manager.update_managed_section(active_branch="main")

    content = (temp_dir / "CLAUDE.md").read_text()
    assert START_MARKER in content
    assert END_MARKER in content


def test_claude_md_manager_preserves_user_content(temp_dir):
    path = temp_dir / "CLAUDE.md"
    path.write_text("# Notes\n\nUser text\n")
    project = Project.from_path(temp_dir)
    manager = ClaudeMdManager(project)
    manager.update_managed_section(active_branch="main")

    content = path.read_text()
    assert "User text" in content
    assert START_MARKER in content


def test_claude_md_manager_includes_health_snapshot(temp_dir):
    project = Project.from_path(temp_dir)
    manager = ClaudeMdManager(project)
    manager.update_managed_section(
        active_branch="main",
        health_score=88,
        health_issues=["Testing: missing integration tests"],
    )
    content = (temp_dir / "CLAUDE.md").read_text()
    assert "Health Snapshot" in content
    assert "88/100" in content
    assert "missing integration tests" in content
