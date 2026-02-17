"""Tests for Codex/Gemini fallback dispatcher behavior."""

from __future__ import annotations

import threading
from pathlib import Path

import src.agents.codex_dispatcher as codex_dispatcher
import src.agents.gemini_dispatcher as gemini_dispatcher


def _write_executable(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
    return path


def test_codex_dispatch_task_streams_output(temp_dir, monkeypatch) -> None:
    """Codex dispatcher should stream output to log and return success."""
    project = temp_dir / "project"
    project.mkdir()
    runtime = temp_dir / "runtime"

    cli = _write_executable(
        temp_dir / "fake-codex.sh",
        """#!/bin/sh
if [ "$1" = "exec" ]; then
  shift
fi
echo "starting: $1"
sleep 0.1
echo "finished"
exit 0
""",
    )

    monkeypatch.setattr(codex_dispatcher, "project_id_for_path", lambda _path: "proj-test")
    monkeypatch.setattr(codex_dispatcher, "project_runtime_dir", lambda _project_id: runtime)

    result = codex_dispatcher.dispatch_task(
        prompt="Fix lint",
        working_dir=project,
        cli_path=str(cli),
        timeout_seconds=20,
    )

    assert result.success is True
    assert result.output is not None
    assert "starting: Fix lint" in result.output
    assert "finished" in result.output
    assert result.output_file is not None
    assert "finished" in result.output_file.read_text(encoding="utf-8")


def test_codex_dispatch_task_stall_watchdog(temp_dir, monkeypatch) -> None:
    """Codex dispatcher should fail fast when the process stalls without output."""
    project = temp_dir / "project"
    project.mkdir()
    runtime = temp_dir / "runtime"

    cli = _write_executable(
        temp_dir / "fake-codex-stall.sh",
        """#!/bin/sh
if [ "$1" = "exec" ]; then
  shift
fi
sleep 3
echo "late output"
exit 0
""",
    )

    monkeypatch.setattr(codex_dispatcher, "project_id_for_path", lambda _path: "proj-test")
    monkeypatch.setattr(codex_dispatcher, "project_runtime_dir", lambda _project_id: runtime)

    result = codex_dispatcher.dispatch_task(
        prompt="Fix lint",
        working_dir=project,
        cli_path=str(cli),
        timeout_seconds=20,
        stall_timeout_seconds=1,
    )

    assert result.success is False
    assert result.error_message is not None
    assert "stalled with no output" in result.error_message.lower()


def test_gemini_dispatch_task_cancelled(temp_dir, monkeypatch) -> None:
    """Gemini dispatcher should terminate when cancellation is requested."""
    project = temp_dir / "project"
    project.mkdir()
    runtime = temp_dir / "runtime"

    cli = _write_executable(
        temp_dir / "fake-gemini.sh",
        """#!/bin/sh
echo "tick"
sleep 5
echo "done"
exit 0
""",
    )

    cancel_event = threading.Event()
    cancel_event.set()

    monkeypatch.setattr(gemini_dispatcher, "project_id_for_path", lambda _path: "proj-test")
    monkeypatch.setattr(gemini_dispatcher, "project_runtime_dir", lambda _project_id: runtime)

    result = gemini_dispatcher.dispatch_task(
        prompt="Fix typecheck",
        working_dir=project,
        cli_path=str(cli),
        timeout_seconds=20,
        cancel_event=cancel_event,
    )

    assert result.success is False
    assert result.error_message is not None
    assert "cancelled" in result.error_message.lower()


def test_gemini_dispatch_task_non_zero_exit(temp_dir, monkeypatch) -> None:
    """Gemini dispatcher should surface a concise error on non-zero exit."""
    project = temp_dir / "project"
    project.mkdir()
    runtime = temp_dir / "runtime"

    cli = _write_executable(
        temp_dir / "fake-gemini-fail.sh",
        """#!/bin/sh
echo "fatal: unable to proceed"
exit 3
""",
    )

    monkeypatch.setattr(gemini_dispatcher, "project_id_for_path", lambda _path: "proj-test")
    monkeypatch.setattr(gemini_dispatcher, "project_runtime_dir", lambda _project_id: runtime)

    result = gemini_dispatcher.dispatch_task(
        prompt="Fix docs",
        working_dir=project,
        cli_path=str(cli),
        timeout_seconds=20,
    )

    assert result.success is False
    assert result.error_message is not None
    assert "fatal: unable to proceed" in result.error_message
