"""Simple in-memory TTL cache for API responses.

Prevents redundant expensive computations when the frontend fires
many concurrent requests on page load. Thread-safe via a lock.
"""

import threading
import time
from typing import Any

_lock = threading.Lock()
_store: dict[str, tuple[float, Any]] = {}  # key -> (expires_at, value)

DEFAULT_TTL = 5  # seconds


def get(key: str) -> Any | None:
    """Return cached value if still fresh, else None."""
    with _lock:
        entry = _store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del _store[key]
            return None
        return value


def put(key: str, value: Any, ttl: float = DEFAULT_TTL) -> None:
    """Store a value with a TTL (in seconds)."""
    with _lock:
        _store[key] = (time.monotonic() + ttl, value)


def invalidate(prefix: str = "") -> None:
    """Remove entries matching a prefix (or all if empty)."""
    with _lock:
        if not prefix:
            _store.clear()
        else:
            keys = [k for k in _store if k.startswith(prefix)]
            for k in keys:
                del _store[k]
