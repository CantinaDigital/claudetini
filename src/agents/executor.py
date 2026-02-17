"""Gate executor: command gates in parallel, agent gates sequentially.

Security Model
--------------
Command gates use shell=True for subprocess execution. This is acceptable because:

1. Trust boundary: Commands are sourced from project-local configuration files
   (gates.json) that are controlled by the project owner, not external input.

2. No user input: Gate commands are statically configured, never constructed
   from runtime user input or untrusted sources.

3. Project scope: Commands execute within the project directory with the
   developer's permissions - the same trust level as running make/npm scripts.

4. Audit trail: All gate configurations are stored in version-controlled or
   user-controlled config files, providing traceability.

If you need to accept dynamic commands from untrusted sources, use shlex.split()
and shell=False instead. For this use case, shell=True enables developers to
use familiar shell syntax (pipes, redirects, env vars) in their gate commands.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from ..core.cost_tracker import CostTracker, TokenUsage, estimate_cost
from ..core.gate_results import GateFinding, StoredGateResult
from ..core.secrets_scanner import SecretsScanner
from .parser import AgentOutputParser

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\([A-Za-z]|\x1b\][^\x07]*\x07|\x1b[=>]")


def _strip_ansi(text: str) -> str:
    """Strip ANSI escape codes from terminal output."""
    return _ANSI_RE.sub("", text)


class GateExecutor:
    """Execute command and agent gates for a project."""

    def __init__(self, project_path: Path, project_id: str):
        self.project_path = project_path.resolve()
        self.project_id = project_id
        self._cost_tracker = CostTracker(project_id)
        self._agent_parser = AgentOutputParser()

    def run_command_gates(self, gates: list[dict]) -> list[StoredGateResult]:
        """Execute command-based gates in parallel and return results."""
        if not gates:
            return []

        results: list[StoredGateResult] = []
        max_workers = min(4, len(gates))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(self._run_command_gate, gate) for gate in gates]
            for future in as_completed(futures):
                results.append(future.result())

        order = {gate.get("name", ""): idx for idx, gate in enumerate(gates)}
        results.sort(key=lambda item: order.get(item.name, 999))
        return results

    def run_agent_gates(
        self,
        gates: list[dict],
        changed_files: list[str],
        system_prompt_file: Path | None = None,
    ) -> list[StoredGateResult]:
        """Execute agent-based gates sequentially and return results."""
        results: list[StoredGateResult] = []
        for gate in gates:
            result = self._run_agent_gate(gate, changed_files, system_prompt_file=system_prompt_file)
            results.append(result)
            if result.cost_estimate > 0:
                usage = self._estimate_usage_for_cost(result.cost_estimate)
                self._cost_tracker.record_usage(usage=usage, source="gate")
        return results

    def _run_command_gate(self, gate: dict) -> StoredGateResult:
        name = gate.get("name", "unknown")
        command = gate.get("command") or ""
        hard_stop = bool(gate.get("hard_stop", False))
        timeout = int(gate.get("timeout", 300) or 300)

        if not command:
            return StoredGateResult(
                name=name,
                status="error",
                summary="No command configured",
                hard_stop=hard_stop,
            )

        env = {**os.environ, "NO_COLOR": "1", "TERM": "dumb", "FORCE_COLOR": "0"}
        start = datetime.now()
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            elapsed = (datetime.now() - start).total_seconds()
            stdout = _strip_ansi((proc.stdout or "").strip())
            stderr = _strip_ansi((proc.stderr or "").strip())
            if proc.returncode == 0:
                summary = _summarize_pass_output(name, stdout)
                metric = _extract_metric(name, stdout)
                return StoredGateResult(
                    name=name,
                    status="pass",
                    summary=summary,
                    hard_stop=hard_stop,
                    details=(stdout[:2000] if stdout else None),
                    duration_seconds=elapsed,
                    metric=metric,
                )

            findings = [
                GateFinding(
                    source_gate=name,
                    severity="high" if hard_stop else "medium",
                    description=(stderr or stdout or f"{name} command failed"),
                    suggested_fix_prompt=(
                        f"Fix the failing {name} gate by addressing this output:\n{(stderr or stdout)[:1200]}"
                    ),
                )
            ]
            return StoredGateResult(
                name=name,
                status="fail",
                summary=f"Command failed (exit {proc.returncode})",
                hard_stop=hard_stop,
                details=(stderr or stdout)[:2500] if (stderr or stdout) else None,
                duration_seconds=elapsed,
                findings=findings,
                metric=_extract_metric(name, stdout),
            )
        except subprocess.TimeoutExpired:
            return StoredGateResult(
                name=name,
                status="error",
                summary=f"Timed out after {timeout}s",
                hard_stop=hard_stop,
            )
        except Exception as exc:
            return StoredGateResult(
                name=name,
                status="error",
                summary=str(exc),
                hard_stop=hard_stop,
            )

    def _run_agent_gate(
        self,
        gate: dict,
        changed_files: list[str],
        system_prompt_file: Path | None,
    ) -> StoredGateResult:
        name = gate.get("name", "agent")
        hard_stop = bool(gate.get("hard_stop", False))

        # Optional direct Claude execution when explicitly configured.
        if gate.get("command") == "claude" and shutil.which("claude"):
            result = self._run_claude_agent(gate, changed_files, system_prompt_file)
            result.hard_stop = hard_stop
            return result

        if name == "security":
            return self._run_security_review(name=name, hard_stop=hard_stop)
        if name == "documentation":
            fail_threshold = int(gate.get("fail_threshold", 3) or 3)
            return self._run_doc_review(
                changed_files=changed_files, name=name, hard_stop=hard_stop, fail_threshold=fail_threshold
            )
        if name == "test_coverage":
            return self._run_test_coverage_review(changed_files=changed_files, name=name, hard_stop=hard_stop)

        return StoredGateResult(
            name=name,
            status="skipped",
            summary="No agent implementation configured",
            hard_stop=hard_stop,
        )

    def _run_claude_agent(
        self,
        gate: dict,
        changed_files: list[str],
        system_prompt_file: Path | None,
    ) -> StoredGateResult:
        name = gate.get("name", "agent")
        prompt_template = gate.get("agent_prompt") or "Review these files and return JSON findings."
        file_list = "\n".join(f"- {item}" for item in changed_files[:80])
        prompt = f"{prompt_template}\n\nFiles:\n{file_list}\n\nRespond in JSON."

        command = ["claude"]
        if system_prompt_file:
            command += ["--append-system-prompt-file", str(system_prompt_file)]
        command += ["-p", prompt, "--output-format", "json"]

        start = datetime.now()
        try:
            proc = subprocess.run(
                command,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=int(gate.get("timeout", 180) or 180),
            )
        except Exception as exc:
            return StoredGateResult(name=name, status="error", summary=str(exc), hard_stop=bool(gate.get("hard_stop")))

        elapsed = (datetime.now() - start).total_seconds()
        text = (proc.stdout or proc.stderr or "").strip()
        parsed = self._agent_parser.parse(text)

        findings = [
            GateFinding(
                source_gate=name,
                severity=item.severity,
                description=item.description,
                file=item.file,
                line=item.line,
            )
            for item in parsed.findings
        ]
        usage = _extract_usage_from_text(text)
        cost = estimate_cost(usage, usage.model) if usage else 0.0
        if usage:
            self._cost_tracker.record_usage(usage=usage, source="gate")

        status = parsed.status
        if proc.returncode != 0 and status == "pass":
            status = "fail"

        return StoredGateResult(
            name=name,
            status=status,
            summary=parsed.summary,
            hard_stop=bool(gate.get("hard_stop", False)),
            details=text[:2500],
            duration_seconds=elapsed,
            findings=findings,
            cost_estimate=round(cost, 6),
        )

    def _run_security_review(self, name: str, hard_stop: bool) -> StoredGateResult:
        scanner = SecretsScanner(self.project_path)
        result = scanner.scan(staged_only=False)
        if result.is_clean:
            return StoredGateResult(
                name=name,
                status="pass",
                summary="No obvious security findings",
                hard_stop=hard_stop,
                metric=0.0,
            )

        findings: list[GateFinding] = []
        for hit in result.secrets_found[:30]:
            findings.append(
                GateFinding(
                    source_gate=name,
                    severity=hit.severity,
                    description=hit.message,
                    file=hit.file,
                    line=hit.line,
                    suggested_fix_prompt=(
                        f"Remove exposed credential pattern '{hit.pattern_name}' in {hit.file}:{hit.line}. "
                        "Replace with environment variable based configuration."
                    ),
                )
            )

        severity_fail = result.has_high or result.has_critical
        return StoredGateResult(
            name=name,
            status="fail" if severity_fail else "warn",
            summary=f"{len(findings)} security finding(s)",
            hard_stop=hard_stop,
            details=scanner.format_report(result),
            findings=findings,
            metric=float(len(findings)),
        )

    def _run_doc_review(
        self, changed_files: list[str], name: str, hard_stop: bool, fail_threshold: int = 3
    ) -> StoredGateResult:
        findings: list[GateFinding] = []

        for rel_path in changed_files:
            path = self.project_path / rel_path
            if not path.exists() or path.suffix != ".py":
                continue
            try:
                content = path.read_text()
            except OSError:
                continue

            findings.extend(_find_missing_python_docstrings(name=name, rel_path=rel_path, content=content))

        if not findings:
            return StoredGateResult(
                name=name,
                status="pass",
                summary="Documentation review clean",
                hard_stop=hard_stop,
                metric=0.0,
            )

        status = "fail" if len(findings) >= fail_threshold else "warn"
        return StoredGateResult(
            name=name,
            status=status,
            summary=f"{len(findings)} missing docstring(s)",
            hard_stop=hard_stop,
            findings=findings,
            metric=float(len(findings)),
        )

    def _run_test_coverage_review(self, changed_files: list[str], name: str, hard_stop: bool) -> StoredGateResult:
        source_files = [
            rel_path
            for rel_path in changed_files
            if not rel_path.startswith("tests/")
            and not rel_path.endswith("_test.py")
            and Path(rel_path).suffix in {".py", ".js", ".ts"}
        ]

        findings: list[GateFinding] = []
        for rel_path in source_files:
            path = Path(rel_path)
            stem = path.stem
            candidate_tests = [
                self.project_path / "tests" / f"test_{stem}.py",
                self.project_path / "tests" / f"{stem}_test.py",
                self.project_path / f"{path.with_suffix('')}_test{path.suffix}",
            ]
            if any(candidate.exists() for candidate in candidate_tests):
                continue

            findings.append(
                GateFinding(
                    source_gate=name,
                    severity="medium",
                    description=f"No matching test file found for {rel_path}",
                    file=rel_path,
                    suggested_fix_prompt=f"Add or update tests that cover behavior in {rel_path}.",
                )
            )

        if not findings:
            return StoredGateResult(
                name=name,
                status="pass",
                summary="Coverage review found matching tests",
                hard_stop=hard_stop,
                metric=100.0,
            )

        return StoredGateResult(
            name=name,
            status="warn",
            summary=f"{len(findings)} file(s) may need test coverage",
            hard_stop=hard_stop,
            findings=findings,
            metric=float(max(0, 100 - len(findings) * 10)),
        )

    @staticmethod
    def _estimate_usage_for_cost(cost: float) -> TokenUsage:
        # Approximate from Sonnet output-heavy ratio for tracking buckets.
        output_tokens = max(1, int((cost / 15.0) * 1_000_000))
        input_tokens = max(1, output_tokens // 4)
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model="claude-sonnet-4-5",
        )


def _summarize_pass_output(name: str, output: str) -> str:
    if not output:
        return "Gate passed"
    if name == "tests":
        ratio = re.search(r"(\d+)\s*/\s*(\d+)", output)
        if ratio:
            return f"{ratio.group(1)}/{ratio.group(2)} passing"
    if name == "lint":
        return "Clean" if "error" not in output.lower() else "Lint passed with notices"
    return output.splitlines()[-1][:120]


def _extract_metric(name: str, output: str) -> float | None:
    if not output:
        return None
    if name == "tests":
        coverage = re.search(r"(\d+(?:\.\d+)?)%\s*cov", output, flags=re.IGNORECASE)
        if coverage:
            return float(coverage.group(1))
    if name == "lint":
        errors = re.search(r"(\d+)\s+error", output, flags=re.IGNORECASE)
        if errors:
            return float(max(0, 100 - int(errors.group(1))))
    return None


def _extract_usage_from_text(text: str) -> TokenUsage | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None

    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return None

    input_tokens = int(usage.get("input_tokens") or usage.get("input") or 0)
    output_tokens = int(usage.get("output_tokens") or usage.get("output") or 0)
    if not input_tokens and not output_tokens:
        return None

    model = payload.get("model") or usage.get("model") or "claude-sonnet-4-5"
    return TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens, model=model)


def _find_missing_python_docstrings(name: str, rel_path: str, content: str) -> list[GateFinding]:
    findings: list[GateFinding] = []
    lines = content.splitlines()

    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not (stripped.startswith("def ") or stripped.startswith("class ")):
            continue

        # Skip private helpers for doc gate signal quality.
        if stripped.startswith("def _"):
            continue

        # For multi-line signatures, find where the signature ends (line ending with colon).
        cursor = index
        while cursor <= len(lines):
            check_line = lines[cursor - 1].rstrip()
            if check_line.endswith(":"):
                break
            cursor += 1

        # Now seek first meaningful line after signature.
        while cursor < len(lines):
            candidate = lines[cursor].strip()
            if not candidate or candidate.startswith("#"):
                cursor += 1
                continue
            if candidate.startswith('"""') or candidate.startswith("'''"):
                break
            findings.append(
                GateFinding(
                    source_gate=name,
                    severity="medium",
                    description=f"Missing docstring for `{stripped.split(':')[0]}`",
                    file=rel_path,
                    line=index,
                    suggested_fix_prompt=f"Add a concise docstring for `{stripped.split(':')[0]}` in {rel_path}:{index}.",
                )
            )
            break

    return findings
