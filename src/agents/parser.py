"""Parser for agent JSON output payloads."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


@dataclass
class AgentIssue:
    """Structured issue from agent output."""

    severity: str
    description: str
    file: str | None = None
    line: int | None = None


@dataclass
class ParsedAgentOutput:
    """Normalized parsed output from an agent run."""

    status: str
    summary: str
    findings: list[AgentIssue] = field(default_factory=list)
    raw: str = ""


class AgentOutputParser:
    """Resilient parser that accepts strict JSON or loose markdown wrappers."""

    def parse(self, text: str) -> ParsedAgentOutput:
        payload = self._extract_json_payload(text)
        if payload is None:
            return ParsedAgentOutput(status="warn", summary="Agent output was not JSON", raw=text)

        status = str(payload.get("status") or payload.get("result") or "warn").lower()
        if status in {"passed", "ok", "success"}:
            status = "pass"
        elif status in {"failed", "error"}:
            status = "fail"
        elif status not in {"pass", "warn", "fail"}:
            status = "warn"

        summary = str(payload.get("summary") or payload.get("message") or "No summary provided")

        findings_data = payload.get("findings", [])
        findings: list[AgentIssue] = []
        if isinstance(findings_data, list):
            for item in findings_data:
                if not isinstance(item, dict):
                    continue
                findings.append(
                    AgentIssue(
                        severity=str(item.get("severity", "medium")),
                        description=str(item.get("description") or item.get("finding") or ""),
                        file=item.get("file"),
                        line=item.get("line"),
                    )
                )

        return ParsedAgentOutput(status=status, summary=summary, findings=findings, raw=text)

    def _extract_json_payload(self, text: str) -> dict | None:
        stripped = text.strip()
        candidates = [stripped]

        code_match = re.search(r"```(?:json)?\s*(\{[\s\S]*\}|\[[\s\S]*\])\s*```", stripped)
        if code_match:
            candidates.append(code_match.group(1).strip())

        brace_match = re.search(r"(\{[\s\S]*\})", stripped)
        if brace_match:
            candidates.append(brace_match.group(1).strip())

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue

            if isinstance(parsed, dict):
                return parsed

            if isinstance(parsed, list):
                # Treat list payload as findings-only report.
                return {
                    "status": "warn" if parsed else "pass",
                    "summary": f"{len(parsed)} finding(s)",
                    "findings": parsed,
                }

        return None
