"""JSONL session log parser."""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class JSONLEntry:
    """A single entry from a JSONL file."""

    data: dict
    line_number: int

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the entry data."""
        return self.data.get(key, default)

    @property
    def type(self) -> str | None:
        """Get the entry type if present."""
        return self.data.get("type")


class JSONLParser:
    """Parser for JSONL (JSON Lines) files.

    JSONL files contain one JSON object per line, which is the format
    used by Claude Code session logs.
    """

    def __init__(self, path: Path):
        self.path = path

    def parse(self) -> list[JSONLEntry]:
        """Parse the entire file and return all entries."""
        return list(self.iter_entries())

    def iter_entries(self) -> Iterator[JSONLEntry]:
        """Iterate over entries in the file."""
        if not self.path.exists():
            return

        with open(self.path) as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    yield JSONLEntry(data=data, line_number=line_num)
                except json.JSONDecodeError:
                    # Skip malformed lines
                    continue

    def get_entries_of_type(self, entry_type: str) -> list[JSONLEntry]:
        """Get all entries of a specific type."""
        return [
            entry for entry in self.iter_entries()
            if entry.type == entry_type
        ]

    def get_first_entry(self) -> JSONLEntry | None:
        """Get the first entry in the file."""
        for entry in self.iter_entries():
            return entry
        return None

    def get_last_entry(self) -> JSONLEntry | None:
        """Get the last entry in the file.

        For large files, this reads from the end for efficiency.
        """
        last_entry = None
        for entry in self.iter_entries():
            last_entry = entry
        return last_entry

    def get_entries_between(
        self,
        start_line: int,
        end_line: int | None = None,
    ) -> list[JSONLEntry]:
        """Get entries between specific line numbers."""
        entries = []
        for entry in self.iter_entries():
            if entry.line_number >= start_line:
                if end_line is None or entry.line_number <= end_line:
                    entries.append(entry)
                elif entry.line_number > end_line:
                    break
        return entries

    def search(self, predicate: callable) -> list[JSONLEntry]:
        """Search for entries matching a predicate function."""
        return [
            entry for entry in self.iter_entries()
            if predicate(entry)
        ]

    @property
    def line_count(self) -> int:
        """Get the total number of lines in the file."""
        if not self.path.exists():
            return 0

        count = 0
        with open(self.path) as f:
            for _ in f:
                count += 1
        return count

    @property
    def entry_count(self) -> int:
        """Get the total number of valid JSON entries."""
        return sum(1 for _ in self.iter_entries())


class SessionLogParser(JSONLParser):
    """Specialized parser for Claude Code session logs."""

    def get_human_messages(self) -> list[JSONLEntry]:
        """Get all human (user) messages."""
        return self.get_entries_of_type("human")

    def get_assistant_messages(self) -> list[JSONLEntry]:
        """Get all assistant messages."""
        return self.get_entries_of_type("assistant")

    def get_tool_uses(self) -> list[JSONLEntry]:
        """Get all tool use entries."""
        return self.get_entries_of_type("tool_use")

    def get_tool_results(self) -> list[JSONLEntry]:
        """Get all tool result entries."""
        return self.get_entries_of_type("tool_result")

    def get_conversation_flow(self) -> list[dict]:
        """Get a simplified conversation flow.

        Returns a list of dicts with type and preview of each message.
        """
        flow = []
        for entry in self.iter_entries():
            entry_type = entry.type
            if entry_type in ("human", "assistant"):
                content = entry.get("content", "")
                if isinstance(content, str):
                    preview = content[:100] + "..." if len(content) > 100 else content
                else:
                    preview = str(content)[:100]

                flow.append({
                    "type": entry_type,
                    "preview": preview,
                    "line": entry.line_number,
                })
            elif entry_type == "tool_use":
                tool_name = entry.get("tool_name", "unknown")
                flow.append({
                    "type": "tool_use",
                    "tool": tool_name,
                    "line": entry.line_number,
                })

        return flow
