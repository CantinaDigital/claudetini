"""Quality gates for Phase 3 execution and persistence."""

from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from ..core.gate_results import GateFinding, GateResultStore, GateRunReport, StoredGateResult
from ..core.gate_trends import GateTrendStore
from ..core.runtime import project_id_for_path, project_runtime_dir
from ..core.secrets_scanner import SecretsScanner
from .executor import GateExecutor, _strip_ansi
from .hooks import GitPrePushHookManager

GateType = Literal["command", "agent", "secrets", "hook"]
GateStatus = Literal["pass", "warn", "fail", "skipped", "error"]


@dataclass
class LegacyGateResult:
    """Backward-compatible gate result for older UI code."""

    passed: bool
    partial: bool
    summary: str
    finding: str | None = None
    metric: float | None = None
    cost_estimate: float = 0.0


@dataclass
class GateConfig:
    """Configuration for an individual gate."""

    name: str
    gate_type: GateType
    enabled: bool = True
    hard_stop: bool = False
    command: str | None = None
    agent_prompt: str | None = None
    auto_detect: bool = True
    timeout: int = 300
    min_coverage: int | None = None
    severity_threshold: str | None = None
    fail_threshold: int = 3  # Number of findings before gate fails (vs warns)

    def to_dict(self) -> dict:
        """Serialize gate configuration to dictionary."""
        return {
            "enabled": self.enabled,
            "type": self.gate_type,
            "hard_stop": self.hard_stop,
            "command": self.command,
            "agent_prompt": self.agent_prompt,
            "auto_detect": self.auto_detect,
            "timeout": self.timeout,
            "min_coverage": self.min_coverage,
            "severity_threshold": self.severity_threshold,
            "fail_threshold": self.fail_threshold,
        }


@dataclass
class GateResult:
    """Runtime gate result for UI and report rendering."""

    name: str
    status: GateStatus
    message: str
    details: str | None = None
    duration_seconds: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    hard_stop: bool = False
    finding: str | None = None
    findings: list[GateFinding] = field(default_factory=list)
    metric: float | None = None
    cost_estimate: float = 0.0


@dataclass
class GateReport:
    """Aggregate report for a gate run."""

    results: list[GateResult] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    run_id: str = ""
    session_id: str | None = None
    trigger: str = "manual"
    changed_files: list[str] = field(default_factory=list)
    head_sha: str | None = None
    index_fingerprint: str | None = None
    working_tree_fingerprint: str | None = None

    @property
    def all_passed(self) -> bool:
        """Check if all non-skipped gates passed."""
        return all(r.status == "pass" for r in self.results if r.status != "skipped")

    @property
    def has_failures(self) -> bool:
        """Check if any gates failed."""
        return any(r.status == "fail" for r in self.results)

    @property
    def hard_stop_failures(self) -> list[GateResult]:
        """Get all failing gates marked as hard-stop."""
        return [r for r in self.results if r.status == "fail" and r.hard_stop]


class QualityGateRunner:
    """Orchestrate command + agent gates for a project."""

    def __init__(self, project_path: Path, config_path: Path | None = None, project_id: str | None = None):
        self.project_path = project_path.resolve()
        self.project_id = project_id or project_id_for_path(self.project_path)
        runtime_dir = project_runtime_dir(self.project_id)

        self.config_path = config_path or runtime_dir / "gates.json"
        self.gates: dict[str, GateConfig] = {}

        self.result_store = GateResultStore(self.project_id)
        self.trend_store = GateTrendStore(self.project_id)
        self.executor = GateExecutor(self.project_path, self.project_id)
        self.hook_manager = GitPrePushHookManager(self.project_path, self.project_id)

    def load_config(self) -> dict[str, GateConfig]:
        """Load gate configuration from runtime storage with safe fallbacks."""
        if not self.config_path.exists():
            self.gates = self._default_config()
            self.save_config()
            return self.gates

        try:
            data = json.loads(self.config_path.read_text())
        except (json.JSONDecodeError, OSError):
            self.gates = self._default_config()
            self.save_config()
            return self.gates

        raw_gates = data.get("gates", {}) if isinstance(data, dict) else {}

        # Backward compatibility for list-form scaffolding config.
        if isinstance(raw_gates, list):
            converted = {}
            for item in raw_gates:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if not name:
                    continue
                converted[name] = {
                    "enabled": item.get("enabled", True),
                    "type": item.get("gate_type", "command"),
                    "hard_stop": item.get("hard_stop", False),
                    "command": item.get("command"),
                    "agent_prompt": item.get("agent_prompt"),
                    "timeout": item.get("timeout", 300),
                    "auto_detect": item.get("auto_detect", True),
                }
            raw_gates = converted

        detected_defaults = self._default_config()
        self.gates = {}
        for name, default in detected_defaults.items():
            source = raw_gates.get(name, {}) if isinstance(raw_gates, dict) else {}
            self.gates[name] = GateConfig(
                name=name,
                gate_type=source.get("type", default.gate_type),
                enabled=bool(source.get("enabled", default.enabled)),
                hard_stop=bool(source.get("hard_stop", default.hard_stop)),
                command=source.get("command", default.command),
                agent_prompt=source.get("agent_prompt", default.agent_prompt),
                auto_detect=bool(source.get("auto_detect", default.auto_detect)),
                timeout=int(source.get("timeout", default.timeout) or default.timeout),
                min_coverage=source.get("min_coverage", default.min_coverage),
                severity_threshold=source.get("severity_threshold", default.severity_threshold),
                fail_threshold=int(source.get("fail_threshold", default.fail_threshold) or default.fail_threshold),
            )

        # Preserve any custom gates not in defaults.
        if isinstance(raw_gates, dict):
            for name, source in raw_gates.items():
                if name in self.gates or not isinstance(source, dict):
                    continue
                self.gates[name] = GateConfig(
                    name=name,
                    gate_type=source.get("type", "command"),
                    enabled=bool(source.get("enabled", True)),
                    hard_stop=bool(source.get("hard_stop", False)),
                    command=source.get("command"),
                    agent_prompt=source.get("agent_prompt"),
                    auto_detect=bool(source.get("auto_detect", True)),
                    timeout=int(source.get("timeout", 300) or 300),
                    min_coverage=source.get("min_coverage"),
                    severity_threshold=source.get("severity_threshold"),
                    fail_threshold=int(source.get("fail_threshold", 3) or 3),
                )

        # Merge any Claude Code hooks detected from settings files.
        for hook_gate in self._detect_claude_hooks():
            if hook_gate.name not in self.gates:
                self.gates[hook_gate.name] = hook_gate

        return self.gates

    def save_config(self, triggers: dict | None = None) -> None:
        """Persist gate configuration and trigger metadata to disk."""
        payload = {
            "gates": {
                name: gate.to_dict()
                for name, gate in self.gates.items()
            },
            "triggers": triggers or {
                "on_session_end": True,
                "on_demand": True,
                "pre_push": self.hook_manager.is_installed(),
            },
            "git_hook_installed": self.hook_manager.is_installed(),
        }
        self.config_path.write_text(json.dumps(payload, indent=2))

    def run_all_gates(self, staged_only: bool = True, session_id: str | None = None, trigger: str = "manual", changed_files: list[str] | None = None, system_prompt_file: Path | None = None) -> GateReport:
        """Execute all configured gates and persist a single run report."""
        if not self.gates:
            self.load_config()

        run_id = f"gate-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        changed = changed_files or self._changed_files(staged_only=staged_only)
        head_sha, index_fp, worktree_fp = self._snapshot_git_state()

        results: list[GateResult] = []

        # Secrets gate always runs first and cannot be disabled.
        secrets_gate = self.gates.get("secrets")
        if secrets_gate is None:
            secrets_gate = GateConfig(name="secrets", gate_type="secrets", enabled=True, hard_stop=True)
            self.gates["secrets"] = secrets_gate

        secrets_result = self._run_secrets_gate(secrets_gate, staged_only=staged_only)
        results.append(secrets_result)

        # All gates run regardless of individual failures — hard_stop only
        # affects the overall report status, not whether other gates execute.

        command_configs = []
        agent_configs = []
        for gate in self.gates.values():
            if gate.name == "secrets":
                continue
            if not gate.enabled:
                results.append(
                    GateResult(
                        name=gate.name,
                        status="skipped",
                        message="Gate disabled",
                        hard_stop=gate.hard_stop,
                    )
                )
                continue
            if gate.gate_type == "hook":
                # Hook gates are informational — they represent Claude Code
                # hooks detected from settings files. We can't execute them
                # (they run inside Claude Code's process), so report them.
                results.append(GateResult(
                    name=gate.name,
                    status="pass",
                    message=f"Claude Code hook: {gate.command or 'agent hook'}",
                    details=gate.agent_prompt,
                    hard_stop=gate.hard_stop,
                ))
                continue
            if gate.gate_type == "command":
                command_configs.append(self._config_payload(gate))
            elif gate.gate_type == "agent":
                agent_configs.append(self._config_payload(gate))

        try:
            for outcome in self.executor.run_command_gates(command_configs):
                results.append(self._from_stored(outcome))
        except Exception as exc:
            # Record an error for each command gate that didn't produce a result.
            ran_names = {r.name for r in results}
            for cfg in command_configs:
                if cfg.get("name") not in ran_names:
                    results.append(GateResult(
                        name=cfg.get("name", "unknown"),
                        status="error",
                        message=f"Executor error: {exc}",
                        hard_stop=cfg.get("hard_stop", False),
                    ))

        try:
            for outcome in self.executor.run_agent_gates(
                agent_configs,
                changed_files=changed,
                system_prompt_file=system_prompt_file,
            ):
                results.append(self._from_stored(outcome))
        except Exception as exc:
            ran_names = {r.name for r in results}
            for cfg in agent_configs:
                if cfg.get("name") not in ran_names:
                    results.append(GateResult(
                        name=cfg.get("name", "unknown"),
                        status="error",
                        message=f"Executor error: {exc}",
                        hard_stop=cfg.get("hard_stop", False),
                    ))

        report = GateReport(
            results=results,
            timestamp=datetime.now(),
            run_id=run_id,
            session_id=session_id,
            trigger=trigger,
            changed_files=changed,
            head_sha=head_sha,
            index_fingerprint=index_fp,
            working_tree_fingerprint=worktree_fp,
        )
        self._persist(report)
        return report

    def run_all(self, staged_only: bool = True) -> dict[str, LegacyGateResult]:
        """Backward-compatible API used by older UI code."""
        report = self.run_all_gates(staged_only=staged_only)
        return {
            result.name: LegacyGateResult(
                passed=result.status == "pass",
                partial=result.status == "warn",
                summary=result.message,
                finding=result.finding,
                metric=result.metric,
                cost_estimate=result.cost_estimate,
            )
            for result in report.results
        }

    def run_gate(self, gate_name: str, session_id: str | None = None) -> GateReport:
        """Execute one named gate and persist the resulting report."""
        if not self.gates:
            self.load_config()
        if gate_name not in self.gates:
            raise ValueError(f"Unknown gate: {gate_name}")

        gate = self.gates[gate_name]
        head_sha, index_fp, worktree_fp = self._snapshot_git_state()
        report = GateReport(
            run_id=f"gate-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(),
            session_id=session_id,
            head_sha=head_sha,
            index_fingerprint=index_fp,
            working_tree_fingerprint=worktree_fp,
        )

        if gate.gate_type == "secrets":
            report.results.append(self._run_secrets_gate(gate))
        elif gate.gate_type == "command":
            outcome = self.executor.run_command_gates([self._config_payload(gate)])
            report.results.extend(self._from_stored(item) for item in outcome)
        elif gate.gate_type == "agent":
            files = self._changed_files(staged_only=False)
            outcome = self.executor.run_agent_gates([self._config_payload(gate)], changed_files=files)
            report.results.extend(self._from_stored(item) for item in outcome)

        report.changed_files = self._changed_files(staged_only=False)
        self._persist(report)
        return report

    def latest_report(self) -> GateReport | None:
        """Load the latest persisted gate report, if available."""
        loaded = self.result_store.load_latest()
        if not loaded:
            return None
        return self._report_from_store(loaded)

    def install_pre_push_hook(self) -> tuple[bool, str]:
        """Install the optional pre-push quality-gate hook."""
        ok, message = self.hook_manager.install()
        if ok:
            self.save_config()
        return ok, message

    def remove_pre_push_hook(self) -> tuple[bool, str]:
        """Remove the optional pre-push quality-gate hook."""
        ok, message = self.hook_manager.remove()
        if ok:
            self.save_config()
        return ok, message

    def pre_push_hook_installed(self) -> bool:
        """Return whether the quality-gate pre-push hook is currently installed."""
        return self.hook_manager.is_installed()

    def trends(self, limit: int = 10) -> dict[str, str]:
        """Return sparkline history for each tracked gate."""
        trend_data = self.trend_store.compute(limit=limit)
        return {
            name: self.trend_store.sparkline_for(name, limit=limit)
            for name in trend_data.keys()
        }

    def _run_secrets_gate(self, gate: GateConfig, staged_only: bool = True) -> GateResult:
        start = datetime.now()
        try:
            scanner = SecretsScanner(self.project_path)
            result = scanner.scan(staged_only=staged_only)
            elapsed = (datetime.now() - start).total_seconds()

            if result.is_clean:
                return GateResult(
                    name=gate.name,
                    status="pass",
                    message=f"No secrets detected in {result.files_scanned} files",
                    duration_seconds=elapsed,
                    hard_stop=gate.hard_stop,
                    metric=0.0,
                )

            findings: list[GateFinding] = []
            for hit in result.secrets_found[:40]:
                findings.append(
                    GateFinding(
                        source_gate=gate.name,
                        severity=hit.severity,
                        description=hit.description,
                        file=str(hit.file_path),
                        line=hit.line_number,
                        suggested_fix_prompt=(
                            f"Remove credential-like content ({hit.secret_type}) "
                            f"from {hit.file_path}:{hit.line_number}. "
                            "Move sensitive values into environment variables."
                        ),
                    )
                )

            status: GateStatus
            if result.has_critical or result.has_high:
                status = "fail"
            else:
                status = "warn"

            message = f"{len(findings)} potential secret(s) detected"
            return GateResult(
                name=gate.name,
                status=status,
                message=message,
                details=scanner.format_report(result),
                duration_seconds=elapsed,
                hard_stop=gate.hard_stop,
                findings=findings,
                finding=(findings[0].description if findings else message),
                metric=float(len(findings)),
            )
        except Exception as exc:
            return GateResult(
                name=gate.name,
                status="error",
                message=f"Secrets scan failed: {exc}",
                hard_stop=gate.hard_stop,
            )

    def _persist(self, report: GateReport) -> None:
        stored = GateRunReport(
            run_id=report.run_id,
            timestamp=report.timestamp,
            session_id=report.session_id,
            trigger=report.trigger,
            changed_files=report.changed_files,
            head_sha=report.head_sha,
            index_fingerprint=report.index_fingerprint,
            working_tree_fingerprint=report.working_tree_fingerprint,
            gates=[
                StoredGateResult(
                    name=item.name,
                    status=item.status,
                    summary=item.message,
                    hard_stop=item.hard_stop,
                    details=item.details,
                    duration_seconds=item.duration_seconds,
                    metric=item.metric,
                    findings=item.findings,
                    cost_estimate=item.cost_estimate,
                )
                for item in report.results
            ],
        )
        self.result_store.save_report(stored)
        self.trend_store.compute(limit=10)

    def _report_from_store(self, stored: GateRunReport) -> GateReport:
        return GateReport(
            run_id=stored.run_id,
            timestamp=stored.timestamp,
            session_id=stored.session_id,
            trigger=stored.trigger,
            changed_files=stored.changed_files,
            head_sha=stored.head_sha,
            index_fingerprint=stored.index_fingerprint,
            working_tree_fingerprint=stored.working_tree_fingerprint,
            results=[
                GateResult(
                    name=item.name,
                    status=item.status,
                    message=_strip_ansi(item.summary),
                    details=_strip_ansi(item.details) if item.details else None,
                    duration_seconds=item.duration_seconds,
                    hard_stop=item.hard_stop,
                    finding=_strip_ansi(item.findings[0].description) if item.findings else None,
                    findings=item.findings,
                    metric=item.metric,
                    cost_estimate=item.cost_estimate,
                )
                for item in stored.gates
            ],
        )

    @staticmethod
    def _from_stored(result: StoredGateResult) -> GateResult:
        return GateResult(
            name=result.name,
            status=result.status,
            message=_strip_ansi(result.summary),
            details=_strip_ansi(result.details) if result.details else None,
            duration_seconds=result.duration_seconds,
            hard_stop=result.hard_stop,
            finding=_strip_ansi(result.findings[0].description) if result.findings else None,
            findings=result.findings,
            metric=result.metric,
            cost_estimate=result.cost_estimate,
        )

    @staticmethod
    def _config_payload(config: GateConfig) -> dict:
        return {
            "name": config.name,
            "type": config.gate_type,
            "command": config.command,
            "agent_prompt": config.agent_prompt,
            "hard_stop": config.hard_stop,
            "timeout": config.timeout,
            "severity_threshold": config.severity_threshold,
            "min_coverage": config.min_coverage,
            "fail_threshold": config.fail_threshold,
        }

    def _default_config(self) -> dict[str, GateConfig]:
        detected = self._auto_detect_commands()

        return {
            "secrets": GateConfig(
                name="secrets",
                gate_type="secrets",
                enabled=True,
                hard_stop=True,
                auto_detect=False,
            ),
            "tests": GateConfig(
                name="tests",
                gate_type="command",
                enabled=True,
                hard_stop=True,  # ENFORCED: Block dispatch on test failure
                command=detected.get("tests") or "pytest --tb=short -q",
            ),
            "lint": GateConfig(
                name="lint",
                gate_type="command",
                enabled=True,
                hard_stop=True,  # ENFORCED: Block dispatch on lint failure
                command=detected.get("lint") or "ruff check .",
            ),
            "typecheck": GateConfig(
                name="typecheck",
                gate_type="command",
                enabled=bool(detected.get("typecheck")),
                hard_stop=True,  # ENFORCED: Block dispatch on type errors
                command=detected.get("typecheck"),
            ),
            "security": GateConfig(
                name="security",
                gate_type="agent",
                enabled=True,
                hard_stop=True,  # ENFORCED: Block dispatch on security issues
                severity_threshold="high",
                timeout=120,
            ),
            "documentation": GateConfig(
                name="documentation",
                gate_type="agent",
                enabled=True,
                hard_stop=False,  # Advisory: docs are important but not blocking
                timeout=90,
            ),
            "test_coverage": GateConfig(
                name="test_coverage",
                gate_type="agent",
                enabled=False,
                hard_stop=False,
                timeout=90,
            ),
        }

    def _auto_detect_commands(self) -> dict[str, str]:
        commands: dict[str, str] = {}

        pyproject = self.project_path / "pyproject.toml"
        if pyproject.exists():
            content = pyproject.read_text(errors="ignore").lower()
            if "pytest" in content:
                commands["tests"] = "pytest --tb=short -q"
            if "ruff" in content:
                commands["lint"] = "ruff check ."
            if "mypy" in content:
                commands["typecheck"] = "mypy ."

        package_json = self.project_path / "package.json"
        if package_json.exists():
            try:
                pkg = json.loads(package_json.read_text())
                scripts = pkg.get("scripts", {}) if isinstance(pkg, dict) else {}
            except (json.JSONDecodeError, OSError):
                scripts = {}

            if "test" in scripts:
                test_cmd = scripts.get("test", "")
                if "vitest" in test_cmd:
                    commands["tests"] = "npx vitest run"
                else:
                    commands["tests"] = "npm test"
            if "lint" in scripts:
                commands["lint"] = "npm run lint"
            elif "eslint" in json.dumps(pkg).lower() if isinstance(pkg, dict) else False:
                commands["lint"] = "npx eslint ."
            if "typecheck" in scripts:
                commands["typecheck"] = "npm run typecheck"
            elif (self.project_path / "tsconfig.json").exists():
                commands["typecheck"] = "npx tsc --noEmit"

        makefile = self.project_path / "Makefile"
        if makefile.exists():
            text = makefile.read_text(errors="ignore")
            if "test:" in text:
                commands["tests"] = "make test"
            if "lint:" in text:
                commands["lint"] = "make lint"
            if "typecheck:" in text:
                commands["typecheck"] = "make typecheck"

        if (self.project_path / "Cargo.toml").exists():
            commands["tests"] = "cargo test"
            commands["lint"] = "cargo clippy -- -D warnings"

        if (self.project_path / "go.mod").exists():
            commands["tests"] = "go test ./..."
            commands["lint"] = "golangci-lint run"

        return commands

    def _detect_claude_hooks(self) -> list[GateConfig]:
        """Read Claude Code settings files and extract hook definitions.

        Checks three locations (in priority order):
        1. <project>/.claude/settings.json       (project, committed)
        2. <project>/.claude/settings.local.json  (project, local)
        3. ~/.claude/settings.json                (global)

        Returns GateConfig entries of type "hook" for any PreToolUse hooks found.
        """
        settings_files = [
            self.project_path / ".claude" / "settings.json",
            self.project_path / ".claude" / "settings.local.json",
            Path.home() / ".claude" / "settings.json",
        ]

        hooks_found: list[GateConfig] = []
        seen_commands: set[str] = set()

        for settings_path in settings_files:
            if not settings_path.exists():
                continue
            try:
                data = json.loads(settings_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue

            if not isinstance(data, dict):
                continue

            hooks_section = data.get("hooks", {})
            if not isinstance(hooks_section, dict):
                continue

            for event_name, event_hooks in hooks_section.items():
                if not isinstance(event_hooks, list):
                    continue

                for entry in event_hooks:
                    if not isinstance(entry, dict):
                        continue

                    matcher = entry.get("matcher", "")
                    inner_hooks = entry.get("hooks", [])
                    if not isinstance(inner_hooks, list):
                        continue

                    for hook_def in inner_hooks:
                        if not isinstance(hook_def, dict):
                            continue

                        hook_type = hook_def.get("type", "command")
                        command = hook_def.get("command", "")
                        prompt = hook_def.get("prompt", "")

                        # Build a unique key to avoid duplicates across files.
                        key = f"{event_name}:{matcher}:{command or prompt}"
                        if key in seen_commands:
                            continue
                        seen_commands.add(key)

                        # Build a readable name.
                        if command:
                            short = Path(command).name if "/" in command else command
                            if len(short) > 30:
                                short = short[:27] + "..."
                            label = f"hook:{short}"
                        elif prompt:
                            label = f"hook:{prompt[:25]}..." if len(prompt) > 25 else f"hook:{prompt}"
                        else:
                            label = f"hook:{event_name}"

                        detail_parts = [f"Event: {event_name}"]
                        if matcher:
                            detail_parts.append(f"Matcher: {matcher}")
                        if command:
                            detail_parts.append(f"Command: {command}")
                        if prompt:
                            detail_parts.append(f"Prompt: {prompt}")
                        detail_parts.append(f"Source: {settings_path.name}")

                        hooks_found.append(GateConfig(
                            name=label,
                            gate_type="hook",
                            enabled=True,
                            hard_stop=False,
                            command=command or None,
                            agent_prompt="\n".join(detail_parts),
                            auto_detect=False,
                        ))

        return hooks_found

    def _changed_files(self, staged_only: bool) -> list[str]:
        if not (self.project_path / ".git").exists():
            return []

        cmd = ["git", "diff", "--name-only", "--cached"] if staged_only else ["git", "diff", "--name-only"]
        proc = subprocess.run(
            cmd,
            cwd=self.project_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            fallback = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if fallback.returncode != 0:
                return []
            files = []
            for line in fallback.stdout.splitlines():
                if len(line) >= 4:
                    files.append(line[3:].strip())
            return [item for item in files if item]

        files = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        if staged_only:
            return files

        # Include untracked files for advisory gates (docs/security coverage checks).
        status_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self.project_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if status_proc.returncode == 0:
            for line in status_proc.stdout.splitlines():
                if line.startswith("?? ") and len(line) >= 4:
                    files.append(line[3:].strip())

        deduped: dict[str, None] = {}
        for item in files:
            if item:
                deduped[item] = None
        return list(deduped.keys())

    def _snapshot_git_state(self) -> tuple[str | None, str | None, str | None]:
        if not (self.project_path / ".git").exists():
            return None, None, None

        head = self._git_output(["git", "rev-parse", "HEAD"]) or "UNBORN"
        index_state = self._git_output(["git", "diff", "--cached", "--name-status"]) or ""
        worktree_state = self._git_output(["git", "status", "--porcelain=v1"]) or ""
        return head, _hash_text(index_state), _hash_text(worktree_state)

    def _git_output(self, command: list[str]) -> str | None:
        try:
            proc = subprocess.run(
                command,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            return None
        if proc.returncode != 0:
            return None
        return proc.stdout.strip()


def _hash_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()
