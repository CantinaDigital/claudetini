"""Build Claude Code --agents payloads for dispatch modes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..core.runtime import project_runtime_dir


@dataclass
class ClaudeSubAgent:
    """Definition of a Claude CLI sub-agent."""

    name: str
    description: str
    prompt: str
    tools: list[str]
    model: str = "sonnet"

    def to_cli_entry(self) -> dict:
        return {
            "description": self.description,
            "prompt": self.prompt,
            "tools": self.tools,
            "model": self.model,
        }

    @classmethod
    def from_dict(cls, key: str, data: dict) -> ClaudeSubAgent:
        return cls(
            name=key,
            description=str(data.get("description", "")),
            prompt=str(data.get("prompt", "")),
            tools=[str(item) for item in data.get("tools", ["Read", "Grep"])],
            model=str(data.get("model", "sonnet")),
        )


DEFAULT_REVIEW_AGENT = ClaudeSubAgent(
    name="code-reviewer",
    description="Reviews completed changes for quality and risks.",
    prompt=(
        "You are a senior code reviewer. Focus on correctness, security, and maintainability. "
        "Produce concrete findings and suggested fixes."
    ),
    tools=["Read", "Grep", "Glob"],
)

DEFAULT_TEST_AGENT = ClaudeSubAgent(
    name="test-writer",
    description="Writes and updates tests for newly changed behavior.",
    prompt=(
        "You are a testing specialist. Add or update tests for behavioral changes, edge cases, "
        "and regressions introduced by the implementation."
    ),
    tools=["Read", "Write", "Bash", "Grep"],
)

DEFAULT_DOC_AGENT = ClaudeSubAgent(
    name="doc-reviewer",
    description="Checks documentation gaps in changed code.",
    prompt=(
        "You are a documentation reviewer. Identify missing docstrings, outdated examples, and "
        "user-facing behavior changes that require docs updates."
    ),
    tools=["Read", "Grep", "Glob"],
)


class AgentRegistry:
    """Project-local custom agent registry."""

    def __init__(self, project_id: str, base_dir: Path | None = None):
        self.project_dir = project_runtime_dir(project_id, base_dir=base_dir)
        self.agents_file = self.project_dir / "agents.json"

    def list_agents(self) -> dict[str, ClaudeSubAgent]:
        if not self.agents_file.exists():
            return {}
        try:
            payload = json.loads(self.agents_file.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

        raw_agents = payload.get("agents", {}) if isinstance(payload, dict) else {}
        if not isinstance(raw_agents, dict):
            return {}

        agents: dict[str, ClaudeSubAgent] = {}
        for key, data in raw_agents.items():
            if isinstance(data, dict):
                agents[key] = ClaudeSubAgent.from_dict(key, data)
        return agents

    def save_agents(self, agents: dict[str, ClaudeSubAgent]) -> None:
        payload = {
            "agents": {
                name: agent.to_cli_entry()
                for name, agent in agents.items()
            }
        }
        self.agents_file.write_text(json.dumps(payload, indent=2))

    def upsert_agent(self, agent: ClaudeSubAgent) -> None:
        agents = self.list_agents()
        agents[agent.name] = agent
        self.save_agents(agents)

    def remove_agent(self, name: str) -> None:
        agents = self.list_agents()
        if name in agents:
            del agents[name]
            self.save_agents(agents)


def agents_for_mode(mode: str, custom_agents: dict[str, ClaudeSubAgent] | None = None) -> dict[str, dict]:
    """Return CLI-ready agent mapping for a dispatch mode."""
    mode = (mode or "standard").strip().lower()
    agents: dict[str, ClaudeSubAgent] = {}

    if mode in {"with_review", "review", "start_with_review_agent"}:
        agents[DEFAULT_REVIEW_AGENT.name] = DEFAULT_REVIEW_AGENT
    elif mode in {"full_pipeline", "pipeline", "start_full_pipeline"}:
        agents[DEFAULT_REVIEW_AGENT.name] = DEFAULT_REVIEW_AGENT
        agents[DEFAULT_TEST_AGENT.name] = DEFAULT_TEST_AGENT
        agents[DEFAULT_DOC_AGENT.name] = DEFAULT_DOC_AGENT

    if custom_agents:
        # Custom agents are appended for non-standard modes.
        if mode != "standard":
            agents.update(custom_agents)

    return {name: agent.to_cli_entry() for name, agent in agents.items()}


def build_agents_flag_json(mode: str, custom_agents: dict[str, ClaudeSubAgent] | None = None) -> str | None:
    """Return serialized JSON for --agents or None for standard mode."""
    payload = agents_for_mode(mode=mode, custom_agents=custom_agents)
    if not payload:
        return None
    return json.dumps(payload, separators=(",", ":"))
