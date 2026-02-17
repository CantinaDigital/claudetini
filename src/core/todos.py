"""Claude Code todo file parsing."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

TodoStatus = Literal["pending", "in_progress", "completed"]
TodoPriority = Literal["high", "medium", "low"]


@dataclass
class TodoItem:
    """A single todo item from Claude Code's todo system."""

    content: str
    status: TodoStatus = "pending"
    priority: TodoPriority = "medium"
    session_id: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    active_form: str | None = None  # Present continuous form

    @property
    def is_completed(self) -> bool:
        return self.status == "completed"

    @property
    def is_pending(self) -> bool:
        return self.status == "pending"

    @property
    def is_in_progress(self) -> bool:
        return self.status == "in_progress"

    @classmethod
    def from_dict(cls, data: dict, session_id: str | None = None) -> "TodoItem":
        """Create a TodoItem from a dictionary."""
        created_at = None
        if "created_at" in data:
            try:
                created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        completed_at = None
        if "completed_at" in data:
            try:
                completed_at = datetime.fromisoformat(data["completed_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        return cls(
            content=data.get("content", ""),
            status=data.get("status", "pending"),
            priority=data.get("priority", "medium"),
            session_id=session_id,
            created_at=created_at,
            completed_at=completed_at,
            active_form=data.get("activeForm"),
        )


@dataclass
class TodoList:
    """A collection of todo items from a session."""

    session_id: str
    items: list[TodoItem] = field(default_factory=list)
    file_path: Path | None = None

    @property
    def pending_items(self) -> list[TodoItem]:
        return [item for item in self.items if item.is_pending]

    @property
    def in_progress_items(self) -> list[TodoItem]:
        return [item for item in self.items if item.is_in_progress]

    @property
    def completed_items(self) -> list[TodoItem]:
        return [item for item in self.items if item.is_completed]

    @property
    def high_priority_pending(self) -> list[TodoItem]:
        return [item for item in self.pending_items if item.priority == "high"]


class TodoParser:
    """Parser for Claude Code todo JSON files."""

    def __init__(self, claude_dir: Path | None = None):
        self.claude_dir = claude_dir or Path.home() / ".claude"
        self.todos_dir = self.claude_dir / "todos"

    def find_todo_files(self) -> list[Path]:
        """Find all todo JSON files."""
        if not self.todos_dir.exists():
            return []
        return list(self.todos_dir.glob("*.json"))

    def parse_todo_file(self, path: Path) -> TodoList | None:
        """Parse a single todo JSON file."""
        try:
            content = path.read_text()
            data = json.loads(content)

            # Extract session ID from filename
            # Format: {session-id}-{timestamp}.json or {session-id}.json
            session_id = path.stem.split("-")[0] if "-" in path.stem else path.stem

            # Handle both array and object formats
            if isinstance(data, list):
                items = [TodoItem.from_dict(item, session_id) for item in data]
            elif isinstance(data, dict) and "todos" in data:
                items = [TodoItem.from_dict(item, session_id) for item in data["todos"]]
            else:
                return None

            return TodoList(
                session_id=session_id,
                items=items,
                file_path=path,
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def get_all_todos(self) -> list[TodoList]:
        """Get all todo lists from all files."""
        todo_lists = []
        for path in self.find_todo_files():
            todo_list = self.parse_todo_file(path)
            if todo_list:
                todo_lists.append(todo_list)
        return todo_lists

    def get_session_todos(self, session_id: str) -> TodoList | None:
        """Get todos for a specific session."""
        for path in self.find_todo_files():
            if session_id in path.stem:
                return self.parse_todo_file(path)
        return None

    def get_pending_high_priority(self) -> list[TodoItem]:
        """Get all pending high-priority todos across all sessions."""
        items = []
        for todo_list in self.get_all_todos():
            items.extend(todo_list.high_priority_pending)
        return items

    def get_incomplete_todos(self) -> list[TodoItem]:
        """Get all incomplete (pending or in_progress) todos."""
        items = []
        for todo_list in self.get_all_todos():
            items.extend(todo_list.pending_items)
            items.extend(todo_list.in_progress_items)
        return items
