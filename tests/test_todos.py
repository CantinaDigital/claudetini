"""Tests for todo parsing."""

import pytest
from pathlib import Path
import json

from src.core.todos import TodoParser, TodoItem, TodoList


class TestTodoItem:
    """Tests for TodoItem class."""

    def test_from_dict_basic(self):
        """Test creating TodoItem from dict."""
        data = {
            "content": "Fix bug",
            "status": "pending",
            "priority": "high",
        }

        item = TodoItem.from_dict(data)

        assert item.content == "Fix bug"
        assert item.status == "pending"
        assert item.priority == "high"
        assert item.is_pending is True

    def test_from_dict_with_active_form(self):
        """Test creating TodoItem with active form."""
        data = {
            "content": "Add tests",
            "status": "in_progress",
            "priority": "medium",
            "activeForm": "Adding tests",
        }

        item = TodoItem.from_dict(data)

        assert item.active_form == "Adding tests"
        assert item.is_in_progress is True

    def test_completed_item(self):
        """Test completed item properties."""
        item = TodoItem(content="Done", status="completed", priority="low")

        assert item.is_completed is True
        assert item.is_pending is False
        assert item.is_in_progress is False

    def test_default_values(self):
        """Test default values."""
        item = TodoItem(content="Task")

        assert item.status == "pending"
        assert item.priority == "medium"


class TestTodoList:
    """Tests for TodoList class."""

    def test_pending_items(self):
        """Test filtering pending items."""
        items = [
            TodoItem(content="A", status="pending"),
            TodoItem(content="B", status="completed"),
            TodoItem(content="C", status="pending"),
        ]
        todo_list = TodoList(session_id="test", items=items)

        pending = todo_list.pending_items

        assert len(pending) == 2
        assert all(item.is_pending for item in pending)

    def test_in_progress_items(self):
        """Test filtering in-progress items."""
        items = [
            TodoItem(content="A", status="in_progress"),
            TodoItem(content="B", status="pending"),
        ]
        todo_list = TodoList(session_id="test", items=items)

        in_progress = todo_list.in_progress_items

        assert len(in_progress) == 1
        assert in_progress[0].content == "A"

    def test_completed_items(self):
        """Test filtering completed items."""
        items = [
            TodoItem(content="A", status="completed"),
            TodoItem(content="B", status="completed"),
            TodoItem(content="C", status="pending"),
        ]
        todo_list = TodoList(session_id="test", items=items)

        completed = todo_list.completed_items

        assert len(completed) == 2

    def test_high_priority_pending(self):
        """Test filtering high priority pending items."""
        items = [
            TodoItem(content="A", status="pending", priority="high"),
            TodoItem(content="B", status="pending", priority="low"),
            TodoItem(content="C", status="completed", priority="high"),
        ]
        todo_list = TodoList(session_id="test", items=items)

        high_priority = todo_list.high_priority_pending

        assert len(high_priority) == 1
        assert high_priority[0].content == "A"


class TestTodoParser:
    """Tests for TodoParser class."""

    @pytest.fixture
    def parser_with_todos(self, temp_dir, sample_todo_json):
        """Create parser with sample todo files."""
        todos_dir = temp_dir / "todos"
        todos_dir.mkdir()

        # Create a todo file
        todo_file = todos_dir / "session-001-123456.json"
        todo_file.write_text(json.dumps(sample_todo_json))

        return TodoParser(claude_dir=temp_dir)

    def test_find_todo_files(self, parser_with_todos):
        """Test finding todo files."""
        files = parser_with_todos.find_todo_files()

        assert len(files) == 1

    def test_parse_todo_file(self, parser_with_todos):
        """Test parsing a todo file."""
        files = parser_with_todos.find_todo_files()
        todo_list = parser_with_todos.parse_todo_file(files[0])

        assert todo_list is not None
        assert len(todo_list.items) == 3

    def test_get_all_todos(self, parser_with_todos):
        """Test getting all todos."""
        all_todos = parser_with_todos.get_all_todos()

        assert len(all_todos) == 1
        assert len(all_todos[0].items) == 3

    def test_get_pending_high_priority(self, parser_with_todos):
        """Test getting pending high priority todos."""
        high_priority = parser_with_todos.get_pending_high_priority()

        assert len(high_priority) == 1
        assert high_priority[0].content == "Fix authentication bug"

    def test_get_incomplete_todos(self, parser_with_todos):
        """Test getting incomplete todos."""
        incomplete = parser_with_todos.get_incomplete_todos()

        # 1 pending + 1 in_progress = 2 incomplete
        assert len(incomplete) == 2

    def test_empty_todos_dir(self, temp_dir):
        """Test with empty todos directory."""
        parser = TodoParser(claude_dir=temp_dir)

        assert len(parser.find_todo_files()) == 0
        assert len(parser.get_all_todos()) == 0
