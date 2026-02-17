"""Tests for system prompt generation."""

from src.core.project import Project
from src.core.system_prompt import SystemPromptBuilder


def test_system_prompt_writes_file(temp_dir):
    (temp_dir / "ROADMAP.md").write_text(
        "# Plan\n\n## Milestone 1\n- [ ] Ship feature\n"
    )
    (temp_dir / "CLAUDE.md").write_text("# Conventions\n\nUse tests.\n")

    project = Project.from_path(temp_dir)
    builder = SystemPromptBuilder(project, base_dir=temp_dir / ".claudetini")
    path = builder.build_and_write()

    assert path.exists()
    content = path.read_text()
    assert "Project Context" in content
    assert "Ship feature" in content


def test_system_prompt_blitz_constraints(temp_dir):
    (temp_dir / "ROADMAP.md").write_text("# Plan\n\n## Milestone\n- [ ] Do thing\n")
    project = Project.from_path(temp_dir)
    builder = SystemPromptBuilder(project, base_dir=temp_dir / ".claudetini", blitz_mode=True)
    path = builder.build_and_write()
    content = path.read_text()
    assert "Blitz Mode Constraints" in content
    assert str(temp_dir) in content
