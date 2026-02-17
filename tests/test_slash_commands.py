"""Tests for slash command generation."""

from src.core.project import Project
from src.core.slash_commands import SlashCommandGenerator


def test_generate_slash_commands(temp_dir):
    (temp_dir / "ROADMAP.md").write_text("# Plan\n\n## M1\n- [ ] Item\n")
    project = Project.from_path(temp_dir)
    files = SlashCommandGenerator(project).generate()

    assert len(files) == 4
    assert (temp_dir / ".claude" / "commands" / "next.md").exists()

