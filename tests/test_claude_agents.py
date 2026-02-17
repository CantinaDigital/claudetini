"""Tests for Claude sub-agent payload generation."""

from src.agents.claude_agents import AgentRegistry, ClaudeSubAgent, build_agents_flag_json


def test_agents_flag_generation_modes():
    assert build_agents_flag_json("standard") is None

    review = build_agents_flag_json("with_review")
    assert review is not None
    assert "code-reviewer" in review

    full = build_agents_flag_json("full_pipeline")
    assert full is not None
    assert "test-writer" in full


def test_agent_registry_roundtrip(temp_dir):
    registry = AgentRegistry("proj123", base_dir=temp_dir)
    registry.upsert_agent(
        ClaudeSubAgent(
            name="api-checker",
            description="Checks API contracts",
            prompt="Review API contract changes",
            tools=["Read", "Grep"],
        )
    )

    agents = registry.list_agents()
    assert "api-checker" in agents
    assert agents["api-checker"].description == "Checks API contracts"
