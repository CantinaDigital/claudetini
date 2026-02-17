"""Gate history trend computation and compact sparkline rendering."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..utils import parse_iso
from .gate_results import GateResultStore
from .runtime import project_runtime_dir


@dataclass
class GateHistoryPoint:
    """One historical data point for a gate."""

    date: datetime
    status: str
    metric: float


@dataclass
class GateTrend:
    """Trend series for one gate."""

    gate_name: str
    results: list[GateHistoryPoint]


class GateTrendStore:
    """Compute and persist aggregated gate trends."""

    def __init__(self, project_id: str, base_dir: Path | None = None):
        self.project_id = project_id
        self.project_dir = project_runtime_dir(project_id, base_dir=base_dir)
        self.trends_file = self.project_dir / "gate-trends.json"
        self.result_store = GateResultStore(project_id, base_dir=base_dir)

    def compute(self, limit: int = 10) -> dict[str, GateTrend]:
        reports = list(reversed(self.result_store.load_history(limit=200)))
        trend_map: dict[str, list[GateHistoryPoint]] = {}

        for report in reports:
            for gate in report.gates:
                metric = float(gate.metric) if gate.metric is not None else _status_metric(gate.status)
                point = GateHistoryPoint(date=report.timestamp, status=gate.status, metric=metric)
                trend_map.setdefault(gate.name, []).append(point)

        trends = {
            gate_name: GateTrend(gate_name=gate_name, results=points[-limit:])
            for gate_name, points in trend_map.items()
        }
        self._save(trends)
        return trends

    def load(self) -> dict[str, GateTrend]:
        if not self.trends_file.exists():
            return {}
        try:
            raw = json.loads(self.trends_file.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

        trends: dict[str, GateTrend] = {}
        for name, payload in raw.items():
            points = [
                GateHistoryPoint(
                    date=parse_iso(item.get("date")) or datetime.now(),
                    status=item.get("status", "unknown"),
                    metric=float(item.get("metric", 0.0)),
                )
                for item in payload.get("results", [])
            ]
            trends[name] = GateTrend(gate_name=name, results=points)
        return trends

    def sparkline_for(self, gate_name: str, limit: int = 10) -> str:
        trends = self.load()
        if gate_name not in trends:
            trends = self.compute(limit=limit)

        points = trends.get(gate_name, GateTrend(gate_name=gate_name, results=[])).results[-limit:]
        if not points:
            return "-"
        values = [point.metric for point in points]
        return render_sparkline(values)

    def _save(self, trends: dict[str, GateTrend]) -> None:
        payload = {
            name: {
                "results": [
                    {
                        "date": point.date.isoformat(),
                        "status": point.status,
                        "metric": point.metric,
                    }
                    for point in trend.results
                ]
            }
            for name, trend in trends.items()
        }
        self.trends_file.write_text(json.dumps(payload, indent=2))


def render_sparkline(values: list[float]) -> str:
    """Render a tiny unicode sparkline from numeric values."""
    if not values:
        return "-"

    blocks = "▁▂▃▄▅▆▇█"
    low = min(values)
    high = max(values)
    if high == low:
        return blocks[-1] * len(values)

    chars = []
    for value in values:
        ratio = (value - low) / (high - low)
        index = int(round(ratio * (len(blocks) - 1)))
        chars.append(blocks[max(0, min(index, len(blocks) - 1))])
    return "".join(chars)


def _status_metric(status: str) -> float:
    mapping = {
        "pass": 3.0,
        "warn": 2.0,
        "fail": 1.0,
        "skipped": 2.0,
        "error": 1.0,
    }
    return mapping.get(status, 2.0)
