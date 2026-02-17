"""Quality gate result persistence and failure feedback loop."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from ..utils import parse_iso
from .runtime import project_runtime_dir

GateOutcome = Literal["pass", "warn", "fail", "skipped", "error"]


@dataclass
class GateFinding:
    """A single issue produced by a gate run."""

    source_gate: str
    severity: str
    description: str
    file: str | None = None
    line: int | None = None
    suggested_fix_prompt: str | None = None

    @property
    def key(self) -> str:
        payload = "|".join(
            [
                self.source_gate,
                self.severity,
                self.file or "",
                str(self.line or 0),
                self.description,
            ]
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


@dataclass
class StoredGateResult:
    """Structured result for one gate."""

    name: str
    status: GateOutcome
    summary: str
    hard_stop: bool = False
    details: str | None = None
    duration_seconds: float = 0.0
    metric: float | None = None
    findings: list[GateFinding] = field(default_factory=list)
    cost_estimate: float = 0.0


@dataclass
class GateRunReport:
    """Full report for one gate execution cycle."""

    run_id: str
    timestamp: datetime
    session_id: str | None = None
    trigger: str = "manual"
    changed_files: list[str] = field(default_factory=list)
    head_sha: str | None = None
    index_fingerprint: str | None = None
    working_tree_fingerprint: str | None = None
    gates: list[StoredGateResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(g.status == "pass" for g in self.gates if g.status != "skipped")

    @property
    def has_failures(self) -> bool:
        return any(g.status == "fail" for g in self.gates)

    @property
    def hard_stop_failures(self) -> list[StoredGateResult]:
        return [g for g in self.gates if g.hard_stop and g.status == "fail"]

    @property
    def total_cost(self) -> float:
        return round(sum(g.cost_estimate for g in self.gates), 6)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "trigger": self.trigger,
            "changed_files": self.changed_files,
            "head_sha": self.head_sha,
            "index_fingerprint": self.index_fingerprint,
            "working_tree_fingerprint": self.working_tree_fingerprint,
            "total_cost": self.total_cost,
            "gates": [
                {
                    **asdict(gate),
                    "findings": [asdict(item) for item in gate.findings],
                }
                for gate in self.gates
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> GateRunReport:
        gates: list[StoredGateResult] = []
        for raw_gate in data.get("gates", []):
            findings = [
                GateFinding(
                    source_gate=item.get("source_gate", raw_gate.get("name", "unknown")),
                    severity=item.get("severity", "medium"),
                    description=item.get("description", ""),
                    file=item.get("file"),
                    line=item.get("line"),
                    suggested_fix_prompt=item.get("suggested_fix_prompt"),
                )
                for item in raw_gate.get("findings", [])
            ]
            gates.append(
                StoredGateResult(
                    name=raw_gate.get("name", "unknown"),
                    status=raw_gate.get("status", "error"),
                    summary=raw_gate.get("summary", ""),
                    hard_stop=bool(raw_gate.get("hard_stop", False)),
                    details=raw_gate.get("details"),
                    duration_seconds=float(raw_gate.get("duration_seconds", 0.0)),
                    metric=raw_gate.get("metric"),
                    findings=findings,
                    cost_estimate=float(raw_gate.get("cost_estimate", 0.0)),
                )
            )

        timestamp = parse_iso(data.get("timestamp")) or datetime.now()
        return cls(
            run_id=data.get("run_id", f"run-{int(timestamp.timestamp())}"),
            timestamp=timestamp,
            session_id=data.get("session_id"),
            trigger=data.get("trigger", "manual"),
            changed_files=[str(item) for item in data.get("changed_files", [])],
            head_sha=data.get("head_sha"),
            index_fingerprint=data.get("index_fingerprint"),
            working_tree_fingerprint=data.get("working_tree_fingerprint"),
            gates=gates,
        )


@dataclass
class GateFailureTodo:
    """Todo generated from a failed gate finding."""

    id: str
    source_gate: str
    severity: str
    file: str | None
    line: int | None
    description: str
    suggested_fix_prompt: str
    created_at: datetime
    session_id: str | None = None
    resolved_at: datetime | None = None

    @property
    def is_open(self) -> bool:
        return self.resolved_at is None

    @classmethod
    def from_dict(cls, data: dict) -> GateFailureTodo:
        return cls(
            id=data.get("id", ""),
            source_gate=data.get("source_gate", "unknown"),
            severity=data.get("severity", "medium"),
            file=data.get("file"),
            line=data.get("line"),
            description=data.get("description", ""),
            suggested_fix_prompt=data.get("suggested_fix_prompt", ""),
            created_at=parse_iso(data.get("created_at")) or datetime.now(),
            session_id=data.get("session_id"),
            resolved_at=parse_iso(data.get("resolved_at")),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_gate": self.source_gate,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "description": self.description,
            "suggested_fix_prompt": self.suggested_fix_prompt,
            "created_at": self.created_at.isoformat(),
            "session_id": self.session_id,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class GateResultStore:
    """Persist gate run reports and derived gate-failure todos."""

    def __init__(self, project_id: str, base_dir: Path | None = None):
        self.project_dir = project_runtime_dir(project_id, base_dir=base_dir)
        self.results_dir = self.project_dir / "gate-results"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.latest_file = self.results_dir / "latest.json"
        self.last_status_file = self.project_dir / "last-gate-status.json"
        self.failure_todos_file = self.project_dir / "gate-failure-todos.json"

    def save_report(self, report: GateRunReport) -> Path:
        payload = report.to_dict()
        timestamp_slug = report.timestamp.strftime("%Y-%m-%dT%H-%M-%S")
        report_path = self.results_dir / f"{timestamp_slug}-{report.run_id}.json"
        report_path.write_text(json.dumps(payload, indent=2))
        self.latest_file.write_text(json.dumps(payload, indent=2))

        status_payload = {
            "run_id": report.run_id,
            "timestamp": report.timestamp.isoformat(),
            "session_id": report.session_id,
            "head_sha": report.head_sha,
            "index_fingerprint": report.index_fingerprint,
            "working_tree_fingerprint": report.working_tree_fingerprint,
            "gates": [
                {
                    "name": gate.name,
                    "status": gate.status,
                    "summary": gate.summary,
                    "hard_stop": gate.hard_stop,
                }
                for gate in report.gates
            ],
        }
        self.last_status_file.write_text(json.dumps(status_payload, indent=2))
        self._sync_failure_todos(report)
        return report_path

    def load_latest(self) -> GateRunReport | None:
        if not self.latest_file.exists():
            return None
        try:
            return GateRunReport.from_dict(json.loads(self.latest_file.read_text()))
        except (json.JSONDecodeError, OSError):
            return None

    def load_history(self, limit: int = 50) -> list[GateRunReport]:
        reports: list[GateRunReport] = []
        files = sorted(
            [path for path in self.results_dir.glob("*.json") if path.name != "latest.json"],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in files[:limit]:
            try:
                reports.append(GateRunReport.from_dict(json.loads(path.read_text())))
            except (json.JSONDecodeError, OSError):
                continue
        return reports

    def load_for_session(self, session_id: str) -> GateRunReport | None:
        for report in self.load_history(limit=200):
            if report.session_id == session_id:
                return report
        return None

    def open_failure_todos(self) -> list[GateFailureTodo]:
        todos = self._load_todos()
        return [item for item in todos if item.is_open]

    def all_failure_todos(self) -> list[GateFailureTodo]:
        return self._load_todos()

    def _sync_failure_todos(self, report: GateRunReport) -> None:
        existing = self._load_todos()
        index = {item.id: item for item in existing}

        active_ids: set[str] = set()
        for gate in report.gates:
            if gate.status not in {"fail", "warn"}:
                continue

            findings = gate.findings or [
                GateFinding(
                    source_gate=gate.name,
                    severity=("high" if gate.status == "fail" else "medium"),
                    description=gate.summary,
                    suggested_fix_prompt=_default_fix_prompt(
                        gate_name=gate.name,
                        summary=gate.summary,
                        details=gate.details,
                    ),
                )
            ]

            for finding in findings:
                todo_id = finding.key
                active_ids.add(todo_id)
                if todo_id in index:
                    index[todo_id].resolved_at = None
                    continue

                index[todo_id] = GateFailureTodo(
                    id=todo_id,
                    source_gate=finding.source_gate,
                    severity=finding.severity,
                    file=finding.file,
                    line=finding.line,
                    description=finding.description,
                    suggested_fix_prompt=(
                        finding.suggested_fix_prompt
                        or _default_fix_prompt(
                            gate_name=finding.source_gate,
                            summary=finding.description,
                            details=gate.details,
                            file=finding.file,
                            line=finding.line,
                        )
                    ),
                    created_at=report.timestamp,
                    session_id=report.session_id,
                )

        for todo in index.values():
            if todo.id not in active_ids and todo.resolved_at is None:
                todo.resolved_at = report.timestamp

        serialized = [item.to_dict() for item in sorted(index.values(), key=lambda item: item.created_at)]
        self.failure_todos_file.write_text(json.dumps(serialized[-1000:], indent=2))

    def _load_todos(self) -> list[GateFailureTodo]:
        if not self.failure_todos_file.exists():
            return []
        try:
            raw = json.loads(self.failure_todos_file.read_text())
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(raw, list):
            return []
        return [GateFailureTodo.from_dict(item) for item in raw]


def _default_fix_prompt(
    gate_name: str,
    summary: str,
    details: str | None = None,
    file: str | None = None,
    line: int | None = None,
) -> str:
    location = ""
    if file:
        location = f"\nLocation: {file}{':' + str(line) if line else ''}"
    return (
        f"Fix the failing {gate_name} quality gate.\n"
        f"Finding: {summary}{location}\n"
        f"Details: {details or 'n/a'}\n"
        "Implement the fix, add/update tests, and update docs if behavior changed."
    )
