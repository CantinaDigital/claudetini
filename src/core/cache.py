"""Simple JSON cache helpers for Phase 2 modules."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class CachePayload:
    """Cached data with metadata fingerprint."""

    fingerprint: str
    generated_at: str
    data: Any


class JsonCache:
    """A tiny cache store for JSON-serializable payloads."""

    def __init__(self, cache_path: Path):
        self.cache_path = cache_path
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> CachePayload | None:
        """Load cache payload if present and valid."""
        if not self.cache_path.exists():
            return None
        try:
            raw = json.loads(self.cache_path.read_text())
        except json.JSONDecodeError:
            return None

        if not isinstance(raw, dict):
            return None
        if "fingerprint" not in raw or "generated_at" not in raw:
            return None
        return CachePayload(
            fingerprint=str(raw["fingerprint"]),
            generated_at=str(raw["generated_at"]),
            data=raw.get("data"),
        )

    def save(self, fingerprint: str, data: Any) -> None:
        """Write cache payload."""
        payload = {
            "fingerprint": fingerprint,
            "generated_at": datetime.now().isoformat(),
            "data": data,
        }
        self.cache_path.write_text(json.dumps(payload, indent=2))

