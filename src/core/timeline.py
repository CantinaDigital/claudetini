"""Session timeline aggregation for Phase 2."""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..utils import parse_iso
from .cache import JsonCache
from .cost_tracker import DEFAULT_MODEL, TokenUsage, estimate_cost
from .dispatch_audit import DispatchAuditStore
from .gate_results import GateResultStore, GateRunReport
from .git_utils import GitRepo
from .project import Project
from .provider_usage import ProviderUsageStore
from .runtime import project_id_for_project, project_runtime_dir
from .sessions import Session, SessionParser

logger = logging.getLogger(__name__)


def _ensure_naive(dt: datetime | None) -> datetime | None:
    """Ensure datetime is naive (no timezone info) for consistent comparisons."""
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


@dataclass
class CommitInfo:
    """Commit info attached to a session timeline entry."""

    sha: str
    message: str
    timestamp: datetime


@dataclass
class TestResult:
    """Test summary parsed from session artifacts."""

    passed: bool
    total: int | None = None
    passed_count: int | None = None
    raw: str | None = None


@dataclass
class TimelineEntry:
    """A session timeline entry."""

    session_id: str
    date: datetime
    duration_minutes: int
    summary: str
    provider: str = "claude"
    branch: str | None = None
    commits: list[CommitInfo] = field(default_factory=list)
    files_changed: int = 0
    todos_created: int = 0
    todos_completed: int = 0
    roadmap_items_completed: list[str] = field(default_factory=list)
    test_results: TestResult | None = None
    prompt_used: str | None = None
    prompt_version: int | None = None
    token_usage: TokenUsage | None = None
    cost_estimate: float | None = None
    gate_statuses: dict[str, str] = field(default_factory=dict)
    gate_cost: float = 0.0
    retry_of: str | None = None
    override_events: list[str] = field(default_factory=list)


class TimelineBuilder:
    """Build session timeline entries from Claude logs and git history."""

    def __init__(
        self,
        project: Project,
        cache_root: Path | None = None,
        claude_dir: Path | None = None,
    ):
        self.project = project
        self.session_parser = SessionParser(claude_dir=claude_dir)
        self.project_id = project_id_for_project(project)
        self.runtime_dir = project_runtime_dir(self.project_id, base_dir=cache_root)
        cache_dir = self.runtime_dir
        self.cache = JsonCache(cache_dir / "timeline-cache.json")
        self.gate_store = GateResultStore(self.project_id, base_dir=cache_root)
        self.audit_store = DispatchAuditStore(self.project_id, base_dir=cache_root)
        self.usage_store = ProviderUsageStore(self.project_id, base_dir=cache_root)

    def build(self, limit: int = 20, use_cache: bool = True) -> list[TimelineEntry]:
        """Build timeline entries newest-first."""
        if not self.project.claude_hash:
            supplemental = self._supplemental_provider_entries()
            all_entries = supplemental
            all_entries.sort(key=lambda entry: entry.date, reverse=True)
            return all_entries[:limit]

        sessions = self.session_parser.find_sessions(self.project.claude_hash)
        gate_reports_by_session = self._gate_reports_by_session()
        audit_overrides_by_session = self._audit_overrides_by_session()
        supplemental_markers = self._supplemental_fingerprint_markers()
        fingerprint = self._fingerprint(
            sessions,
            gate_reports_by_session,
            audit_overrides_by_session,
            supplemental_markers,
        )

        if use_cache:
            cached = self.cache.load()
            if cached and cached.fingerprint == fingerprint:
                return [self._entry_from_dict(item) for item in (cached.data or [])][:limit]

        entries = [
            self._build_entry(
                session,
                gate_reports_by_session,
                audit_overrides_by_session,
            )
            for session in sessions
        ]
        entries = [entry for entry in entries if self._should_keep_claude_entry(entry)]
        entries.extend(self._supplemental_provider_entries())
        entries.sort(key=lambda entry: entry.date, reverse=True)
        serialized = [self._entry_to_dict(entry) for entry in entries]
        self.cache.save(fingerprint, serialized)
        return entries[:limit]

    def _build_entry(
        self,
        session: Session,
        gate_reports_by_session: dict[str, GateRunReport],
        audit_overrides_by_session: dict[str, list[str]],
    ) -> TimelineEntry:
        metadata = self._parse_session_metadata(session.log_path)

        summary_text = ""
        if session.summary and session.summary.summary_text:
            summary_text = session.summary.summary_text.strip().split("\n")[0]
        if not summary_text:
            summary_text = metadata.get("assistant_summary") or ""

        date = _ensure_naive(session.start_time) or datetime.now()
        end_time = _ensure_naive(session.end_time) or _ensure_naive(session.start_time) or datetime.now()
        duration = int((end_time - date).total_seconds() / 60) if end_time and date else 0
        if duration < 0:
            duration = 0

        commits, files_changed = self._correlate_commits(date, end_time)
        usage = metadata.get("token_usage")
        cost = estimate_cost(usage, usage.model) if usage else None
        gate_statuses: dict[str, str] = {}
        gate_cost = 0.0
        override_events = audit_overrides_by_session.get(session.session_id, [])
        gate_report = gate_reports_by_session.get(session.session_id)
        if gate_report:
            gate_statuses = {gate.name: gate.status for gate in gate_report.gates}
            gate_cost = gate_report.total_cost
            cost = (cost or 0.0) + gate_cost

        return TimelineEntry(
            session_id=session.session_id,
            date=date,
            duration_minutes=duration,
            summary=summary_text or "No summary available",
            provider="claude",
            branch=metadata.get("branch"),
            commits=commits,
            files_changed=files_changed,
            todos_created=int(metadata.get("todos_created", 0)),
            todos_completed=int(metadata.get("todos_completed", 0)),
            roadmap_items_completed=metadata.get("roadmap_items_completed", []),
            test_results=metadata.get("test_results"),
            prompt_used=metadata.get("prompt_used"),
            prompt_version=metadata.get("prompt_version"),
            token_usage=usage,
            cost_estimate=cost,
            gate_statuses=gate_statuses,
            gate_cost=gate_cost,
            retry_of=metadata.get("retry_of"),
            override_events=override_events,
        )

    def _parse_session_metadata(self, log_path: Path) -> dict:
        """Stream metadata from jsonl without loading full file."""
        todos_created = 0
        todos_completed = 0
        roadmap_items_completed: list[str] = []
        prompt_used: str | None = None
        prompt_version: int | None = None
        retry_of: str | None = None
        branch: str | None = None
        test_results: TestResult | None = None
        assistant_texts: list[str] = []
        total_input = 0
        total_output = 0
        model = DEFAULT_MODEL
        seen_usage_requests: set[str] = set()
        seen_usage_markers: set[str] = set()

        try:
            with open(log_path) as handle:
                for line in handle:
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    role = self._entry_role(entry)
                    content = self._entry_text(entry)
                    normalized = self._normalize_whitespace(content)

                    if branch is None:
                        branch_value = entry.get("gitBranch")
                        if isinstance(branch_value, str) and branch_value.strip():
                            branch = branch_value.strip()

                    if (
                        prompt_used is None
                        and role == "user"
                        and normalized
                        and not self._is_command_artifact(normalized)
                    ):
                        prompt_used = normalized
                        version_match = re.search(
                            r"prompt\s*v(?:ersion)?\s*(\d+)",
                            normalized,
                            re.IGNORECASE,
                        )
                        if version_match:
                            prompt_version = int(version_match.group(1))

                    lowered = normalized.lower()
                    if "todowrite" in lowered or entry.get("tool_name") == "TodoWrite":
                        todos_created += lowered.count("pending")
                        todos_completed += lowered.count("completed")

                    if "[x]" in normalized and "roadmap" in lowered:
                        roadmap_items_completed.extend(self._extract_checkbox_items(content))

                    if retry_of is None:
                        retry_match = re.search(
                            r"retry[_ -]?of[:=]\s*([a-zA-Z0-9_-]+)",
                            normalized,
                            re.IGNORECASE,
                        )
                        if retry_match:
                            retry_of = retry_match.group(1)

                    if role == "assistant" and normalized and not self._is_command_artifact(normalized):
                        assistant_texts.append(normalized)

                    parsed_test = self._extract_test_result(normalized)
                    if parsed_test:
                        test_results = parsed_test

                    usage = self._extract_usage(entry)
                    if usage:
                        request_id = str(entry.get("requestId") or "").strip()
                        if request_id:
                            if request_id in seen_usage_requests:
                                usage = None
                            else:
                                seen_usage_requests.add(request_id)
                        else:
                            marker = str(entry.get("uuid") or "").strip()
                            if not marker:
                                marker = (
                                    f"{entry.get('timestamp')}|{usage.input_tokens}|"
                                    f"{usage.output_tokens}|{usage.model}"
                                )
                            if marker in seen_usage_markers:
                                usage = None
                            else:
                                seen_usage_markers.add(marker)

                    if usage:
                        total_input += usage.input_tokens
                        total_output += usage.output_tokens
                        model = usage.model or model
        except OSError as e:
            logger.warning("Failed to parse session metadata from %s: %s", log_path, e)

        token_usage = None
        if total_input > 0 or total_output > 0:
            token_usage = TokenUsage(
                input_tokens=total_input,
                output_tokens=total_output,
                model=model,
            )

        return {
            "todos_created": todos_created,
            "todos_completed": todos_completed,
            "roadmap_items_completed": list(dict.fromkeys(roadmap_items_completed)),
            "test_results": test_results,
            "prompt_used": prompt_used,
            "prompt_version": prompt_version,
            "token_usage": token_usage,
            "retry_of": retry_of,
            "assistant_summary": self._select_assistant_summary(assistant_texts),
            "branch": branch,
        }

    def _correlate_commits(self, start: datetime, end: datetime) -> tuple[list[CommitInfo], int]:
        if not GitRepo.is_git_repo(self.project.path):
            return [], 0
        try:
            repo = GitRepo(self.project.path)
        except ValueError:
            return [], 0

        commits_raw = repo.get_commits_since(start)
        commits = [c for c in commits_raw if c.timestamp <= end]
        infos: list[CommitInfo] = []
        files_changed = 0
        for commit in commits:
            infos.append(CommitInfo(sha=commit.sha, message=commit.message, timestamp=commit.timestamp))
            files_changed += len(repo.get_files_changed_in_commit(commit.sha))

        return infos, files_changed

    @staticmethod
    def _extract_checkbox_items(content: str) -> list[str]:
        items: list[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            # Skip diff removal lines (e.g. "-- [x] item" = diff "-" + markdown "- [x]")
            if stripped.startswith("--"):
                continue
            # Skip diff headers
            if stripped.startswith("diff --git") or stripped.startswith("@@"):
                continue
            match = re.search(r"\[x\]\s*(.+)", stripped, re.IGNORECASE)
            if match:
                text = match.group(1).strip()
                if text and len(text) < 200:
                    items.append(text)
        return items

    @staticmethod
    def _extract_test_result(content: str) -> TestResult | None:
        # Supports "47/47 passing" and "3 failed, 40 passed".
        ratio_match = re.search(r"(\d+)\s*/\s*(\d+)\s+passing", content, re.IGNORECASE)
        if ratio_match:
            passed = int(ratio_match.group(1))
            total = int(ratio_match.group(2))
            return TestResult(passed=(passed == total), total=total, passed_count=passed, raw=content)

        py_match = re.search(r"(\d+)\s+failed,\s+(\d+)\s+passed", content, re.IGNORECASE)
        if py_match:
            failed = int(py_match.group(1))
            passed = int(py_match.group(2))
            total = failed + passed
            return TestResult(passed=(failed == 0), total=total, passed_count=passed, raw=content)
        return None

    @staticmethod
    def _extract_usage(entry: dict) -> TokenUsage | None:
        usage_candidates: list[dict] = []
        root_usage = entry.get("usage")
        if isinstance(root_usage, dict):
            usage_candidates.append(root_usage)

        message = entry.get("message")
        if isinstance(message, dict):
            message_usage = message.get("usage")
            if isinstance(message_usage, dict):
                usage_candidates.append(message_usage)

        data = entry.get("data")
        if isinstance(data, dict):
            data_usage = data.get("usage")
            if isinstance(data_usage, dict):
                usage_candidates.append(data_usage)

        for usage in usage_candidates:
            model = str(entry.get("model") or usage.get("model") or DEFAULT_MODEL)
            input_tokens = int(usage.get("input_tokens") or usage.get("input") or 0)
            output_tokens = int(usage.get("output_tokens") or usage.get("output") or 0)
            if input_tokens or output_tokens:
                return TokenUsage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model=model,
                )
        return None

    @staticmethod
    def _entry_role(entry: dict) -> str:
        entry_type = str(entry.get("type", "")).lower()
        if entry_type in {"assistant", "user", "human"}:
            return "user" if entry_type in {"user", "human"} else "assistant"

        message = entry.get("message")
        if isinstance(message, dict):
            role = str(message.get("role", "")).lower()
            if role in {"assistant", "user", "human"}:
                return "user" if role in {"user", "human"} else "assistant"

        return entry_type or "unknown"

    @classmethod
    def _entry_text(cls, entry: dict) -> str:
        chunks: list[str] = []
        chunks.extend(cls._content_chunks(entry.get("content")))

        message = entry.get("message")
        if isinstance(message, dict):
            chunks.extend(cls._content_chunks(message.get("content")))

        return "\n".join(chunk for chunk in chunks if chunk).strip()

    @staticmethod
    def _content_chunks(content: object) -> list[str]:
        if isinstance(content, str):
            return [content.strip()] if content.strip() else []

        if not isinstance(content, list):
            return []

        chunks: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type", "")).lower()
            text: str | None = None
            if item_type == "text":
                value = item.get("text")
                if isinstance(value, str):
                    text = value
            elif item_type == "thinking":
                # Skip chain-of-thought traces for timeline UX.
                text = None
            else:
                for key in ("text", "content"):
                    value = item.get(key)
                    if isinstance(value, str):
                        text = value
                        break

            if text:
                cleaned = text.strip()
                if cleaned:
                    chunks.append(cleaned)

        return chunks

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _is_command_artifact(text: str) -> bool:
        lowered = text.strip().lower()
        if not lowered:
            return True
        if "<command-name>" in lowered or "<command-message>" in lowered:
            return True
        if "<local-command" in lowered or "<local-command-caveat>" in lowered:
            return True
        if lowered.startswith("/clear") or lowered.startswith("/exit"):
            return True
        return False

    @classmethod
    def _select_assistant_summary(cls, texts: list[str]) -> str | None:
        if not texts:
            return None

        best = max(texts, key=len)
        lines = [line.strip() for line in best.splitlines() if line.strip()]
        preferred = ""
        for line in lines:
            if line.startswith("```"):
                continue
            if line.startswith("#"):
                continue
            preferred = line
            break
        if not preferred:
            preferred = lines[0] if lines else best

        summary = cls._normalize_whitespace(preferred)
        if len(summary) > 220:
            summary = f"{summary[:217].rstrip()}..."
        return summary or None

    @staticmethod
    def _should_keep_claude_entry(entry: TimelineEntry) -> bool:
        if entry.prompt_used:
            return True
        if entry.summary and entry.summary != "No summary available":
            return True
        if entry.commits:
            return True
        if entry.token_usage:
            return True
        if entry.todos_created > 0 or entry.todos_completed > 0:
            return True
        return False

    def _supplemental_fingerprint_markers(self) -> list[str]:
        markers: list[str] = []

        usage_file = self.usage_store.usage_file
        if usage_file.exists():
            try:
                stat = usage_file.stat()
                markers.append(f"usage:{stat.st_mtime_ns}:{stat.st_size}")
            except OSError:
                pass

        dispatch_dir = self.runtime_dir / "dispatch-output"
        if dispatch_dir.exists():
            for path in sorted(dispatch_dir.glob("dispatch-*.*")):
                try:
                    stat = path.stat()
                except OSError:
                    continue
                markers.append(f"dispatch:{path.name}:{stat.st_mtime_ns}:{stat.st_size}")

        return markers

    def _supplemental_provider_entries(self) -> list[TimelineEntry]:
        artifacts = self._dispatch_artifacts()
        events = self.usage_store.events()
        entries: list[TimelineEntry] = []
        seen_keys: set[tuple[str, str]] = set()

        for event in events:
            provider = str(event.get("provider") or "").strip().lower()
            if provider not in {"codex", "gemini"}:
                continue

            session_id = str(event.get("session_id") or "").strip()
            if not session_id:
                continue

            key = (session_id, provider)
            seen_keys.add(key)
            artifact = artifacts.get(key, {})
            metadata = event.get("metadata")
            metadata_map = metadata if isinstance(metadata, dict) else {}

            timestamp = _ensure_naive(
                parse_iso(event.get("timestamp"))
                or parse_iso(artifact.get("timestamp"))
            ) or datetime.now()
            prompt = metadata_map.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                prompt = artifact.get("prompt")
            if isinstance(prompt, str):
                prompt = self._normalize_whitespace(prompt)
            else:
                prompt = None

            summary = artifact.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                summary = f"{provider.title()} dispatch completed"

            model = str(event.get("model") or artifact.get("model") or DEFAULT_MODEL)
            input_tokens = int(event.get("input_tokens") or 0)
            output_tokens = int(event.get("output_tokens") or 0)
            token_usage = (
                TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens, model=model)
                if (input_tokens or output_tokens)
                else None
            )

            cost_raw = event.get("cost_usd")
            try:
                cost = float(cost_raw) if cost_raw is not None else None
            except (TypeError, ValueError):
                cost = None

            entries.append(
                TimelineEntry(
                    session_id=session_id,
                    date=timestamp,
                    duration_minutes=0,
                    summary=self._normalize_whitespace(summary),
                    provider=provider,
                    branch=None,
                    commits=[],
                    files_changed=0,
                    todos_created=0,
                    todos_completed=0,
                    roadmap_items_completed=[],
                    test_results=None,
                    prompt_used=prompt,
                    prompt_version=None,
                    token_usage=token_usage,
                    cost_estimate=cost,
                    gate_statuses={},
                    gate_cost=0.0,
                    retry_of=None,
                    override_events=[],
                )
            )

        for key, artifact in artifacts.items():
            if key in seen_keys:
                continue
            session_id, provider = key
            if provider not in {"codex", "gemini"}:
                continue

            timestamp = _ensure_naive(parse_iso(artifact.get("timestamp"))) or datetime.now()
            summary = artifact.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                summary = f"{provider.title()} dispatch completed"
            prompt = artifact.get("prompt")
            if isinstance(prompt, str):
                prompt = self._normalize_whitespace(prompt)
            else:
                prompt = None

            entries.append(
                TimelineEntry(
                    session_id=session_id,
                    date=timestamp,
                    duration_minutes=0,
                    summary=self._normalize_whitespace(summary),
                    provider=provider,
                    branch=None,
                    commits=[],
                    files_changed=0,
                    todos_created=0,
                    todos_completed=0,
                    roadmap_items_completed=[],
                    test_results=None,
                    prompt_used=prompt,
                    prompt_version=None,
                    token_usage=None,
                    cost_estimate=None,
                    gate_statuses={},
                    gate_cost=0.0,
                    retry_of=None,
                    override_events=[],
                )
            )

        return entries

    def _dispatch_artifacts(self) -> dict[tuple[str, str], dict]:
        dispatch_dir = self.runtime_dir / "dispatch-output"
        if not dispatch_dir.exists():
            return {}

        artifacts: dict[tuple[str, str], dict] = {}
        for output_file in dispatch_dir.glob("dispatch-*-*.log"):
            match = re.match(
                r"^(dispatch-\d{14}-[a-f0-9]+)-(codex|gemini)\.log$",
                output_file.name,
                flags=re.IGNORECASE,
            )
            if not match:
                continue
            session_id = match.group(1)
            provider = match.group(2).lower()
            key = (session_id, provider)

            record = artifacts.setdefault(key, {})
            record["summary"] = self._summary_from_output(output_file)

            meta_file = output_file.with_suffix(".meta.json")
            if meta_file.exists():
                try:
                    raw = json.loads(meta_file.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    raw = {}
                if isinstance(raw, dict):
                    prompt = raw.get("prompt")
                    if isinstance(prompt, str) and prompt.strip():
                        record["prompt"] = prompt
                    timestamp = raw.get("timestamp")
                    if isinstance(timestamp, str):
                        record["timestamp"] = timestamp
                    model = raw.get("model")
                    if isinstance(model, str) and model.strip():
                        record["model"] = model

            if "timestamp" not in record:
                ts_match = re.match(r"dispatch-(\d{14})-", session_id)
                if ts_match:
                    try:
                        dt = datetime.strptime(ts_match.group(1), "%Y%m%d%H%M%S")
                        record["timestamp"] = dt.isoformat()
                    except ValueError:
                        pass

        return artifacts

    @staticmethod
    def _summary_from_output(path: Path) -> str:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return "Dispatch output captured"

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("{") and line.endswith("}"):
                continue
            # Skip diff artifacts — they make poor summaries
            if line.startswith(("diff --git", "@@", "+++", "---", "+", "-")):
                continue
            if len(line) > 220:
                return f"{line[:217].rstrip()}..."
            return line
        return "Dispatch output captured"

    @staticmethod
    def _entry_to_dict(entry: TimelineEntry) -> dict:
        return {
            "session_id": entry.session_id,
            "date": entry.date.isoformat(),
            "duration_minutes": entry.duration_minutes,
            "summary": entry.summary,
            "provider": entry.provider,
            "branch": entry.branch,
            "commits": [
                {"sha": commit.sha, "message": commit.message, "timestamp": commit.timestamp.isoformat()}
                for commit in entry.commits
            ],
            "files_changed": entry.files_changed,
            "todos_created": entry.todos_created,
            "todos_completed": entry.todos_completed,
            "roadmap_items_completed": entry.roadmap_items_completed,
            "test_results": (
                {
                    "passed": entry.test_results.passed,
                    "total": entry.test_results.total,
                    "passed_count": entry.test_results.passed_count,
                    "raw": entry.test_results.raw,
                }
                if entry.test_results
                else None
            ),
            "prompt_used": entry.prompt_used,
            "prompt_version": entry.prompt_version,
            "token_usage": (
                {
                    "input_tokens": entry.token_usage.input_tokens,
                    "output_tokens": entry.token_usage.output_tokens,
                    "model": entry.token_usage.model,
                }
                if entry.token_usage
                else None
            ),
            "cost_estimate": entry.cost_estimate,
            "gate_statuses": entry.gate_statuses,
            "gate_cost": entry.gate_cost,
            "retry_of": entry.retry_of,
            "override_events": entry.override_events,
        }

    @staticmethod
    def _entry_from_dict(data: dict) -> TimelineEntry:
        commits = [
            CommitInfo(
                sha=item["sha"],
                message=item["message"],
                timestamp=_ensure_naive(datetime.fromisoformat(item["timestamp"])),
            )
            for item in data.get("commits", [])
        ]

        test_result = None
        if data.get("test_results"):
            raw = data["test_results"]
            test_result = TestResult(
                passed=bool(raw.get("passed")),
                total=raw.get("total"),
                passed_count=raw.get("passed_count"),
                raw=raw.get("raw"),
            )

        token_usage = None
        if data.get("token_usage"):
            raw_usage = data["token_usage"]
            token_usage = TokenUsage(
                input_tokens=int(raw_usage.get("input_tokens", 0)),
                output_tokens=int(raw_usage.get("output_tokens", 0)),
                model=raw_usage.get("model", DEFAULT_MODEL),
            )

        return TimelineEntry(
            session_id=data["session_id"],
            date=_ensure_naive(datetime.fromisoformat(data["date"])),
            duration_minutes=int(data.get("duration_minutes", 0)),
            summary=data.get("summary", ""),
            provider=data.get("provider", "claude"),
            branch=data.get("branch"),
            commits=commits,
            files_changed=int(data.get("files_changed", 0)),
            todos_created=int(data.get("todos_created", 0)),
            todos_completed=int(data.get("todos_completed", 0)),
            roadmap_items_completed=data.get("roadmap_items_completed", []),
            test_results=test_result,
            prompt_used=data.get("prompt_used"),
            prompt_version=data.get("prompt_version"),
            token_usage=token_usage,
            cost_estimate=data.get("cost_estimate"),
            gate_statuses={str(key): str(value) for key, value in (data.get("gate_statuses") or {}).items()},
            gate_cost=float(data.get("gate_cost", 0.0) or 0.0),
            retry_of=data.get("retry_of"),
            override_events=[str(item) for item in (data.get("override_events") or [])],
        )

    @staticmethod
    def _fingerprint(
        sessions: list[Session],
        gate_reports_by_session: dict[str, GateRunReport],
        audit_overrides_by_session: dict[str, list[str]],
        supplemental_markers: list[str] | None = None,
    ) -> str:
        digest = hashlib.sha1()
        digest.update(b"timeline-v2")
        for session in sessions:
            digest.update(session.session_id.encode("utf-8"))
            try:
                stat = session.log_path.stat()
            except OSError:
                continue
            digest.update(str(stat.st_mtime_ns).encode("utf-8"))
            digest.update(str(stat.st_size).encode("utf-8"))
            gate_report = gate_reports_by_session.get(session.session_id)
            if gate_report:
                digest.update(str(getattr(gate_report, "run_id", "")).encode("utf-8"))
                digest.update(str(getattr(gate_report, "timestamp", "")).encode("utf-8"))
            for event in audit_overrides_by_session.get(session.session_id, []):
                digest.update(event.encode("utf-8"))
        for marker in supplemental_markers or []:
            digest.update(marker.encode("utf-8"))
        return digest.hexdigest()

    def _gate_reports_by_session(self) -> dict[str, GateRunReport]:
        reports = self.gate_store.load_history(limit=500)
        by_session: dict[str, GateRunReport] = {}
        for report in reports:
            if report.session_id and report.session_id not in by_session:
                by_session[report.session_id] = report
        return by_session

    def _audit_overrides_by_session(self) -> dict[str, list[str]]:
        by_session: dict[str, list[str]] = {}
        for event in self.audit_store.recent(limit=500):
            if not event.session_id:
                continue
            marker = f"{event.override_type}:{event.reason}"
            by_session.setdefault(event.session_id, []).append(marker)
        return by_session
