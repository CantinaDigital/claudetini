"""Shared utilities for Claudetini."""

from .datetime_utils import parse_iso
from .jsonl_parser import JSONLParser
from .markdown_parser import MarkdownParser


# Lazy import for FileWatcher to avoid watchdog dependency at import time
def __getattr__(name):
    if name == "FileWatcher":
        from .file_watcher import FileWatcher
        return FileWatcher
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "JSONLParser",
    "MarkdownParser",
    "FileWatcher",
    "parse_iso",
]
