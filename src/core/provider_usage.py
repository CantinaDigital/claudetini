"""Provider-aware usage telemetry persistence and aggregation."""

from __future__ import annotations

import fcntl
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from ..utils import parse_iso
from .provider_telemetry import ProviderUsageSnapshot
from .runtime import project_runtime_dir

logger = logging.getLogger(__name__)


@dataclass
class ProviderUsageTotals:
    """Aggregated totals for a provider over a time window."""

    tokens: int = 0
    effort_units: float = 0.0
    cost_usd: float = 0.0
    events: int = 0

    def to_dict(self) -> dict:
        return {
            "tokens": self.tokens,
            "effort_units": round(self.effort_units, 4),
            "cost_usd": round(self.cost_usd, 6),
            "events": self.events,
        }


class ProviderUsageStore:
    """Persist and aggregate usage telemetry across providers."""

    def __init__(self, project_id: str, base_dir: Path | None = None):
        self.project_dir = project_runtime_dir(project_id, base_dir=base_dir)
        self.usage_file = self.project_dir / "provider-usage.json"

    def record(
        self,
        snapshot: ProviderUsageSnapshot,
        source: str,
        session_id: str | None = None,
        timestamp: datetime | None = None,
        metadata: dict | None = None,
    ) -> bool:
        """Record a usage event with file locking for concurrent safety."""
        ts = timestamp or datetime.now()
        metadata = metadata or {}

        try:
            with open(self.usage_file, "a+") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    handle.seek(0)
                    content = handle.read()
                    data = json.loads(content) if content.strip() else {"events": []}
                    events = data.setdefault("events", [])

                    if session_id:
                        for event in events:
                            if (
                                event.get("session_id") == session_id
                                and event.get("provider") == snapshot.provider
                                and event.get("source") == source
                            ):
                                return False

                    events.append(
                        {
                            "timestamp": ts.isoformat(),
                            "provider": snapshot.provider,
                            "source": source,
                            "session_id": session_id,
                            "input_tokens": snapshot.input_tokens,
                            "output_tokens": snapshot.output_tokens,
                            "total_tokens": snapshot.total_tokens,
                            "effort_units": round(snapshot.effort_units, 6),
                            "cost_usd": (
                                round(snapshot.estimated_cost_usd, 6)
                                if snapshot.estimated_cost_usd is not None
                                else None
                            ),
                            "confidence": snapshot.confidence,
                            "model": snapshot.model,
                            "telemetry_source": snapshot.telemetry_source,
                            "metadata": metadata,
                        }
                    )

                    data["events"] = events[-5000:]
                    handle.seek(0)
                    handle.truncate()
                    handle.write(json.dumps(data, indent=2))
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            return True
        except OSError as exc:
            logger.warning("Failed to record provider usage: %s", exc)
            return False

    def events(self, days: int | None = None, now: datetime | None = None) -> list[dict]:
        """Return events, optionally filtered to the last N days."""
        data = self._load_raw()
        events = data.get("events", []) if isinstance(data, dict) else []
        if not isinstance(events, list):
            return []

        if days is None:
            return events

        threshold = (now or datetime.now()) - timedelta(days=days)
        filtered: list[dict] = []
        for event in events:
            ts = parse_iso(event.get("timestamp"))
            if ts and ts >= threshold:
                filtered.append(event)
        return filtered

    def totals(self, days: int | None = None, now: datetime | None = None) -> dict:
        """Aggregate totals by provider and all-providers."""
        rows = self.events(days=days, now=now)
        by_provider: dict[str, ProviderUsageTotals] = {}

        for event in rows:
            provider = str(event.get("provider") or "unknown")
            totals = by_provider.setdefault(provider, ProviderUsageTotals())
            totals.tokens += int(event.get("total_tokens") or 0)
            totals.effort_units += float(event.get("effort_units") or 0.0)
            cost = event.get("cost_usd")
            if cost is not None:
                try:
                    totals.cost_usd += float(cost)
                except (TypeError, ValueError):
                    pass
            totals.events += 1

        all_totals = ProviderUsageTotals()
        for totals in by_provider.values():
            all_totals.tokens += totals.tokens
            all_totals.effort_units += totals.effort_units
            all_totals.cost_usd += totals.cost_usd
            all_totals.events += totals.events

        return {
            "providers": {name: totals.to_dict() for name, totals in by_provider.items()},
            "all": all_totals.to_dict(),
        }

    def unique_session_count(self, provider: str | None = None) -> int:
        """Count unique session IDs recorded in telemetry."""
        ids: set[str] = set()
        for event in self.events():
            if provider and event.get("provider") != provider:
                continue
            session_id = event.get("session_id")
            if isinstance(session_id, str) and session_id.strip():
                ids.add(session_id)
        return len(ids)

    def latest_event_timestamp(self, provider: str | None = None) -> datetime | None:
        """Return timestamp of most recent event."""
        latest: datetime | None = None
        for event in self.events():
            if provider and event.get("provider") != provider:
                continue
            ts = parse_iso(event.get("timestamp"))
            if ts is None:
                continue
            if latest is None or ts > latest:
                latest = ts
        return latest

    def _load_raw(self) -> dict:
        if not self.usage_file.exists():
            return {"events": []}

        try:
            with open(self.usage_file) as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
                try:
                    raw = handle.read()
                    return json.loads(raw) if raw.strip() else {"events": []}
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load provider usage file %s: %s", self.usage_file, exc)
            return {"events": []}
