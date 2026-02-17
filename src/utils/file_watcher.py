"""File system monitoring for live updates."""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


@dataclass
class WatchConfig:
    """Configuration for file watching."""

    path: Path
    patterns: list[str]  # File patterns to watch (e.g., ["*.md", "*.json"])
    recursive: bool = False
    debounce_ms: int = 500  # Debounce rapid changes


class FileChangeHandler(FileSystemEventHandler):
    """Handler for file system events."""

    def __init__(
        self,
        callback: Callable[[Path, str], None],
        patterns: list[str],
        debounce_ms: int = 500,
    ):
        super().__init__()
        self.callback = callback
        self.patterns = patterns
        self.debounce_ms = debounce_ms
        self._debounce_timer: threading.Timer | None = None
        self._pending_events: dict[str, str] = {}
        self._lock = threading.Lock()

    def _matches_pattern(self, path: Path) -> bool:
        """Check if path matches any of the watched patterns."""
        import fnmatch
        name = path.name
        return any(fnmatch.fnmatch(name, pattern) for pattern in self.patterns)

    def _handle_event(self, event: FileSystemEvent, event_type: str) -> None:
        """Handle a file system event with debouncing."""
        if event.is_directory:
            return

        path = Path(event.src_path)
        if not self._matches_pattern(path):
            return

        with self._lock:
            # Store the event
            self._pending_events[str(path)] = event_type

            # Cancel existing timer
            if self._debounce_timer:
                self._debounce_timer.cancel()

            # Start new timer
            self._debounce_timer = threading.Timer(
                self.debounce_ms / 1000.0,
                self._flush_events,
            )
            self._debounce_timer.start()

    def _flush_events(self) -> None:
        """Flush pending events after debounce period."""
        with self._lock:
            events = self._pending_events.copy()
            self._pending_events.clear()

        for path_str, event_type in events.items():
            try:
                self.callback(Path(path_str), event_type)
            except Exception:
                pass  # Ignore callback errors

    def on_created(self, event: FileSystemEvent) -> None:
        self._handle_event(event, "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle_event(event, "modified")

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._handle_event(event, "deleted")

    def on_moved(self, event: FileSystemEvent) -> None:
        self._handle_event(event, "moved")


class FileWatcher:
    """Watches files for changes and triggers callbacks.

    Usage:
        watcher = FileWatcher()
        watcher.watch(
            path=Path("/project"),
            patterns=["ROADMAP.md"],
            callback=lambda p, t: print(f"{p} was {t}"),
        )
        watcher.start()
        # ... later
        watcher.stop()
    """

    def __init__(self):
        self._observer: Observer | None = None
        self._handlers: list[FileChangeHandler] = []
        self._running = False

    def watch(
        self,
        path: Path,
        patterns: list[str],
        callback: Callable[[Path, str], None],
        recursive: bool = False,
        debounce_ms: int = 500,
    ) -> None:
        """Add a watch for files matching patterns.

        Args:
            path: Directory to watch
            patterns: File patterns to match (e.g., ["*.md"])
            callback: Function to call on changes (receives path and event type)
            recursive: Whether to watch subdirectories
            debounce_ms: Debounce time for rapid changes
        """
        if not self._observer:
            self._observer = Observer()

        handler = FileChangeHandler(
            callback=callback,
            patterns=patterns,
            debounce_ms=debounce_ms,
        )
        self._handlers.append(handler)

        self._observer.schedule(
            handler,
            str(path),
            recursive=recursive,
        )

    def start(self) -> None:
        """Start watching for changes."""
        if self._observer and not self._running:
            self._observer.start()
            self._running = True

    def stop(self) -> None:
        """Stop watching for changes."""
        if self._observer and self._running:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._running = False

    def is_running(self) -> bool:
        """Check if the watcher is running."""
        return self._running

    def __enter__(self) -> "FileWatcher":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()


class RoadmapWatcher(FileWatcher):
    """Specialized watcher for roadmap files."""

    def __init__(self, project_path: Path, on_change: Callable[[Path], None]):
        super().__init__()

        # Watch for roadmap file changes
        self.watch(
            path=project_path,
            patterns=["ROADMAP.md", "TODO.md"],
            callback=lambda p, t: on_change(p) if t != "deleted" else None,
            recursive=False,
            debounce_ms=1000,
        )

        # Also watch docs directory if it exists
        docs_path = project_path / "docs"
        if docs_path.exists():
            self.watch(
                path=docs_path,
                patterns=["ROADMAP.md"],
                callback=lambda p, t: on_change(p) if t != "deleted" else None,
                recursive=False,
                debounce_ms=1000,
            )
