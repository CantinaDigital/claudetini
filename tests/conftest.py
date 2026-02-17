"""Pytest configuration and shared fixtures."""

import pytest
from pathlib import Path
import tempfile
import shutil


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    path = Path(tempfile.mkdtemp())
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def sample_roadmap_content():
    """Sample roadmap markdown content."""
    return """# Project Roadmap

## Milestone 1: Core Features
- [x] User authentication
- [x] Database setup
- [ ] API endpoints
- [ ] Error handling

## Milestone 2: UI Components
- [ ] Dashboard layout
- [ ] Navigation menu
- [ ] Settings page

## Milestone 3: Polish
- [ ] Performance optimization
- [ ] Documentation
- [ ] Testing
"""


@pytest.fixture
def sample_roadmap_file(temp_dir, sample_roadmap_content):
    """Create a sample roadmap file."""
    roadmap_path = temp_dir / "ROADMAP.md"
    roadmap_path.write_text(sample_roadmap_content)
    return roadmap_path


@pytest.fixture
def sample_todo_json():
    """Sample todo JSON data."""
    return [
        {
            "content": "Fix authentication bug",
            "status": "pending",
            "priority": "high",
            "activeForm": "Fixing authentication bug",
        },
        {
            "content": "Add unit tests",
            "status": "in_progress",
            "priority": "medium",
            "activeForm": "Adding unit tests",
        },
        {
            "content": "Update README",
            "status": "completed",
            "priority": "low",
            "activeForm": "Updating README",
        },
    ]


@pytest.fixture
def sample_project(temp_dir, sample_roadmap_content):
    """Create a sample project structure."""
    # Create project files
    (temp_dir / "ROADMAP.md").write_text(sample_roadmap_content)
    (temp_dir / "CLAUDE.md").write_text("# Project Guide\n\nThis is a test project.")
    (temp_dir / "README.md").write_text("# Test Project\n\nA sample project for testing.")
    (temp_dir / ".gitignore").write_text("*.pyc\n__pycache__/\n.env\n")

    # Create src directory
    src_dir = temp_dir / "src"
    src_dir.mkdir()
    (src_dir / "__init__.py").write_text("")

    # Create tests directory
    tests_dir = temp_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("")
    (tests_dir / "test_example.py").write_text("def test_example():\n    assert True\n")

    # Initialize git repo
    git_dir = temp_dir / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")

    return temp_dir


@pytest.fixture
def mock_claude_dir(temp_dir):
    """Create a mock ~/.claude directory structure."""
    claude_dir = temp_dir / ".claude"
    claude_dir.mkdir()

    # Create projects directory
    projects_dir = claude_dir / "projects"
    projects_dir.mkdir()

    # Create a sample project hash directory
    project_hash = "abc123def456"
    project_dir = projects_dir / project_hash
    project_dir.mkdir()

    # Create a session log
    session_id = "session-001"
    session_log = project_dir / f"{session_id}.jsonl"
    session_log.write_text(
        '{"type": "human", "content": "Hello", "timestamp": "2024-02-10T10:00:00Z"}\n'
        '{"type": "assistant", "content": "Hi there!", "timestamp": "2024-02-10T10:00:05Z"}\n'
    )

    # Create session memory
    memory_dir = project_dir / session_id / "session-memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "summary.md").write_text(
        "# Session Summary\n\n"
        "- Implemented user authentication\n"
        "- Fixed login bug\n"
        "- Added unit tests\n"
    )

    # Create todos directory
    todos_dir = claude_dir / "todos"
    todos_dir.mkdir()

    return claude_dir
