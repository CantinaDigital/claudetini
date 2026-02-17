"""Tests for agent JSON output parser."""

from src.agents.parser import AgentOutputParser


def test_agent_parser_accepts_markdown_json_block():
    parser = AgentOutputParser()
    parsed = parser.parse(
        """```json
{"status":"fail","summary":"2 issues","findings":[{"severity":"high","description":"Issue A"}]}
```"""
    )

    assert parsed.status == "fail"
    assert parsed.summary == "2 issues"
    assert len(parsed.findings) == 1


def test_agent_parser_falls_back_on_non_json():
    parser = AgentOutputParser()
    parsed = parser.parse("not json")
    assert parsed.status == "warn"
