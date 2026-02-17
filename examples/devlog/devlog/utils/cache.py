"""Simple file-based cache for report results."""

import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta

CACHE_DIR = Path("/tmp/devlog_cache")
CACHE_TTL = timedelta(hours=1)


def get_cached(key: str) -> dict | None:
    """Get a value from the cache."""
    cache_file = CACHE_DIR / f"{_hash_key(key)}.json"
    if not cache_file.exists():
        return None

    data = json.loads(cache_file.read_text())
    cached_at = datetime.fromisoformat(data["cached_at"])

    if datetime.now() - cached_at > CACHE_TTL:
        cache_file.unlink()
        return None

    return data["value"]


def set_cached(key: str, value: dict) -> None:
    """Set a value in the cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{_hash_key(key)}.json"
    cache_file.write_text(json.dumps({
        "cached_at": datetime.now().isoformat(),
        "value": value,
    }))


def _hash_key(key: str) -> str:
    return hashlib.md5(key.encode()).hexdigest()
