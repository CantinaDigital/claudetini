"""Tests for dispatch command construction and escaping."""

from __future__ import annotations

from types import SimpleNamespace

import src.agents.dispatcher as dispatcher_module
from src.agents.dispatcher import (
    ClaudeDispatcher,
    DispatchLogger,
    DispatchResult,
    _detect_token_limit_reached,
    _escape_applescript_text,
    _redact_prompt_preview,
    dispatch_task,
)


def test_escape_applescript_text_handles_quotes_backslashes_and_newlines() -> None:
    raw = 'echo "quote" \\ path\n$(uname -a)'
    escaped = _escape_applescript_text(raw)

    assert '\\"quote\\"' in escaped
    assert "\\\\ path" in escaped
    assert "\\n" in escaped
    assert "\n" not in escaped


def test_build_claude_command_quotes_prompt_safely(temp_dir) -> None:
    project = temp_dir / "project"
    project.mkdir()
    dispatcher = ClaudeDispatcher(project)
    output = project / "dispatch-output.jsonl"

    cmd = dispatcher._build_claude_command(
        prompt='Finish task "$(whoami)" with "quotes" and \\slashes',
        output_file=output,
    )

    assert cmd.startswith("cd ")
    assert "claude " in cmd
    assert "$(whoami)" in cmd
    assert "tee " in cmd


def test_redact_prompt_preview_masks_secret_patterns() -> None:
    preview = _redact_prompt_preview(
        "Use token sk-ant-abcdefghijklmnopqrstuvwxyz0123456789ABCD in this prompt",
        max_chars=200,
    )
    assert "[REDACTED]" in preview


def test_dispatch_logger_persists_project_identity(temp_dir) -> None:
    logger = DispatchLogger(log_path=temp_dir / "dispatch-log.json")
    result = DispatchResult(success=True, session_id="session-1")
    logger.log_dispatch(
        result=result,
        prompt="Work on roadmap item",
        project_name="sample",
        project_id="project-123",
        project_path=temp_dir / "sample",
    )
    records = logger.get_recent_dispatches(limit=1)
    assert records[0]["project_id"] == "project-123"
    assert records[0]["project_path"].endswith("sample")


def test_detect_token_limit_reached_matches_known_phrases() -> None:
    text = "Error: You've exceeded your usage limit for Claude Code."
    assert _detect_token_limit_reached(text)


def test_dispatch_task_marks_token_limit_result(monkeypatch, temp_dir) -> None:
    project = temp_dir / "project"
    project.mkdir()

    monkeypatch.setattr(dispatcher_module, "project_id_for_path", lambda _path: "proj-test")
    monkeypatch.setattr(dispatcher_module, "project_runtime_dir", lambda _project_id: temp_dir / "runtime")
    monkeypatch.setattr(
        dispatcher_module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1,
            stdout="Usage limit reached. Please wait until your limit resets.",
            stderr="",
        ),
    )

    result = dispatch_task("Implement fallback flow", project)

    assert not result.success
    assert result.token_limit_reached
    assert result.provider == "claude"
    assert result.output_file is not None
    assert result.output_file.exists()
