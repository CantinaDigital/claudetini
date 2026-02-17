"""Tests for timeline builder."""

import json

from src.core.project import Project
from src.core.runtime import project_id_for_project, project_runtime_dir
from src.core.timeline import TimelineBuilder


def test_timeline_builder_parses_session(temp_dir):
    project_path = temp_dir / "proj"
    project_path.mkdir()
    (project_path / ".git").mkdir()
    project = Project.from_path(project_path)

    claude_dir = temp_dir / ".claude"
    project_dir = claude_dir / "projects" / project.claude_hash
    project_dir.mkdir(parents=True)

    session_id = "session-001"
    (project_dir / f"{session_id}.jsonl").write_text(
        '{"type":"human","content":"Prompt v1: do thing","timestamp":"2026-02-10T10:00:00Z"}\n'
        '{"type":"assistant","content":"47/47 passing","timestamp":"2026-02-10T10:10:00Z","usage":{"input_tokens":100,"output_tokens":50}}\n'
    )
    memory_dir = project_dir / session_id / "session-memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "summary.md").write_text("- Implemented thing\n")

    entries = TimelineBuilder(project, cache_root=temp_dir / ".cache", claude_dir=claude_dir).build()
    assert len(entries) == 1
    assert entries[0].prompt_version == 1
    assert entries[0].test_results is not None
    assert entries[0].token_usage is not None


def test_timeline_builder_parses_new_jsonl_format_and_filters_command_only(temp_dir):
    project_path = temp_dir / "proj"
    project_path.mkdir()
    (project_path / ".git").mkdir()
    project = Project.from_path(project_path)

    claude_dir = temp_dir / ".claude"
    project_dir = claude_dir / "projects" / project.claude_hash
    project_dir.mkdir(parents=True)

    meaningful_session = "session-meaningful"
    (project_dir / f"{meaningful_session}.jsonl").write_text(
        json.dumps(
            {
                "type": "user",
                "timestamp": "2026-02-10T10:00:00Z",
                "message": {"role": "user", "content": "Implement timeline parser improvements"},
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "assistant",
                "requestId": "req-1",
                "timestamp": "2026-02-10T10:05:00Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Implemented parser updates and added tests."}],
                    "usage": {"input_tokens": 120, "output_tokens": 80, "model": "claude-sonnet-4-20250514"},
                },
            }
        )
        + "\n"
    )

    command_only_session = "session-command-only"
    (project_dir / f"{command_only_session}.jsonl").write_text(
        json.dumps(
            {
                "type": "user",
                "timestamp": "2026-02-10T11:00:00Z",
                "message": {"role": "user", "content": "<command-name>/clear</command-name>"},
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "user",
                "timestamp": "2026-02-10T11:01:00Z",
                "message": {"role": "user", "content": "<local-command-stdout>done</local-command-stdout>"},
            }
        )
        + "\n"
    )

    entries = TimelineBuilder(project, cache_root=temp_dir / ".cache", claude_dir=claude_dir).build(limit=10)
    assert len(entries) == 1
    assert entries[0].session_id == meaningful_session
    assert entries[0].prompt_used == "Implement timeline parser improvements"
    assert entries[0].summary != "No summary available"
    assert entries[0].token_usage is not None
    assert entries[0].provider == "claude"


def test_timeline_builder_includes_codex_usage_events(temp_dir):
    project_path = temp_dir / "proj"
    project_path.mkdir()
    (project_path / ".git").mkdir()
    project = Project.from_path(project_path)

    claude_dir = temp_dir / ".claude"
    project_dir = claude_dir / "projects" / project.claude_hash
    project_dir.mkdir(parents=True)

    runtime_dir = project_runtime_dir(project_id_for_project(project), base_dir=temp_dir / ".cache")
    usage_file = runtime_dir / "provider-usage.json"
    usage_file.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "timestamp": "2026-02-11T12:34:56Z",
                        "provider": "codex",
                        "source": "fallback_dispatch",
                        "session_id": "dispatch-20260211123456-abc12345",
                        "input_tokens": 300,
                        "output_tokens": 700,
                        "total_tokens": 1000,
                        "effort_units": 1.0,
                        "cost_usd": None,
                        "confidence": "estimated",
                        "model": "gpt-5-codex",
                        "telemetry_source": "heuristic",
                        "metadata": {"prompt": "Fix failing timeline tests"},
                    }
                ]
            }
        )
    )

    dispatch_output_dir = runtime_dir / "dispatch-output"
    dispatch_output_dir.mkdir(parents=True, exist_ok=True)
    (dispatch_output_dir / "dispatch-20260211123456-abc12345-codex.log").write_text(
        "Codex completed timeline test fixes successfully.\n"
    )

    entries = TimelineBuilder(project, cache_root=temp_dir / ".cache", claude_dir=claude_dir).build(limit=10)
    codex_entries = [entry for entry in entries if entry.provider == "codex"]
    assert len(codex_entries) == 1
    assert codex_entries[0].session_id == "dispatch-20260211123456-abc12345"
    assert codex_entries[0].prompt_used == "Fix failing timeline tests"
    assert codex_entries[0].summary.startswith("Codex completed timeline test fixes")
