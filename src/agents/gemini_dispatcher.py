"""Gemini CLI dispatcher."""

from __future__ import annotations

import json
import selectors
import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path

from ..core.runtime import project_id_for_path, project_runtime_dir
from .dispatcher import DispatchResult


def dispatch_task(
    prompt: str,
    working_dir: Path,
    cli_path: str = "gemini",
    timeout_seconds: int = 900,
    output_file: Path | None = None,
    cancel_event: threading.Event | None = None,
    stall_timeout_seconds: int = 180,
) -> DispatchResult:
    """Run Gemini CLI and return normalized dispatch output.

    Output is streamed incrementally to ``output_file`` so callers can
    display live progress while the CLI is running.
    """
    project_path = working_dir.resolve()
    project_id = project_id_for_path(project_path)
    runtime_dir = project_runtime_dir(project_id)
    dispatch_output_dir = runtime_dir / "dispatch-output"
    dispatch_output_dir.mkdir(parents=True, exist_ok=True)

    session_id = f"dispatch-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    if output_file is None:
        output_file = dispatch_output_dir / f"{session_id}-gemini.log"
    # Gemini CLI: use -p for non-interactive (headless) mode
    command = [cli_path, "-p", prompt]

    try:
        proc = subprocess.Popen(
            command,
            cwd=project_path,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            text=True,
        )
    except FileNotFoundError:
        _write_metadata_file(
            output_file=output_file,
            session_id=session_id,
            provider="gemini",
            prompt=prompt,
            success=False,
        )
        return DispatchResult(
            success=False,
            session_id=session_id,
            error_message=f"Gemini CLI not found at '{cli_path}'.",
            output_file=output_file,
            provider="gemini",
        )
    except Exception as exc:
        _write_metadata_file(
            output_file=output_file,
            session_id=session_id,
            provider="gemini",
            prompt=prompt,
            success=False,
        )
        return DispatchResult(
            success=False,
            session_id=session_id,
            error_message=str(exc),
            output_file=output_file,
            provider="gemini",
        )

    output_lines: list[str] = []
    last_output_at = datetime.now()
    start_time = datetime.now()
    selector = selectors.DefaultSelector()

    try:
        if proc.stdout is not None:
            selector.register(proc.stdout, selectors.EVENT_READ)

        with open(output_file, "w", encoding="utf-8") as handle:
            while True:
                if cancel_event and cancel_event.is_set():
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                    output = "\n".join(output_lines)
                    _write_metadata_file(
                        output_file=output_file,
                        session_id=session_id,
                        provider="gemini",
                        prompt=prompt,
                        success=False,
                    )
                    return DispatchResult(
                        success=False,
                        session_id=session_id,
                        error_message="Fallback run cancelled by user.",
                        output_file=output_file,
                        output=output or None,
                        provider="gemini",
                    )

                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > timeout_seconds:
                    proc.kill()
                    proc.wait()
                    output = "\n".join(output_lines)
                    _write_metadata_file(
                        output_file=output_file,
                        session_id=session_id,
                        provider="gemini",
                        prompt=prompt,
                        success=False,
                    )
                    return DispatchResult(
                        success=False,
                        session_id=session_id,
                        error_message=f"Gemini CLI timed out after {timeout_seconds}s.",
                        output_file=output_file,
                        output=output or None,
                        provider="gemini",
                    )

                stalled_for = (datetime.now() - last_output_at).total_seconds()
                if (
                    stall_timeout_seconds > 0
                    and stalled_for > stall_timeout_seconds
                    and proc.poll() is None
                ):
                    proc.kill()
                    proc.wait()
                    output = "\n".join(output_lines)
                    _write_metadata_file(
                        output_file=output_file,
                        session_id=session_id,
                        provider="gemini",
                        prompt=prompt,
                        success=False,
                    )
                    return DispatchResult(
                        success=False,
                        session_id=session_id,
                        error_message=(
                            f"Gemini CLI stalled with no output for {stall_timeout_seconds}s."
                        ),
                        output_file=output_file,
                        output=output or None,
                        provider="gemini",
                    )

                events = selector.select(timeout=0.25)
                for key, _ in events:
                    line = key.fileobj.readline()
                    if not line:
                        continue
                    normalized = line.rstrip("\n\r")
                    output_lines.append(normalized)
                    handle.write(line)
                    handle.flush()
                    last_output_at = datetime.now()

                if proc.poll() is not None:
                    break

            if proc.stdout is not None:
                remainder = proc.stdout.read()
                if remainder:
                    for line in remainder.splitlines():
                        output_lines.append(line.rstrip("\n\r"))
                    handle.write(remainder)
                    handle.flush()
    finally:
        selector.close()

    output = "\n".join(output_lines)
    _write_metadata_file(
        output_file=output_file,
        session_id=session_id,
        provider="gemini",
        prompt=prompt,
        success=(proc.returncode == 0),
    )

    if proc.returncode != 0:
        return DispatchResult(
            success=False,
            session_id=session_id,
            error_message=_extract_error_message(output, proc.returncode, "Gemini CLI"),
            output_file=output_file,
            output=output or None,
            provider="gemini",
        )

    return DispatchResult(
        success=True,
        session_id=session_id,
        output_file=output_file,
        output=output or None,
        provider="gemini",
    )


def _combine_cli_output(stdout: str, stderr: str) -> str:
    stdout = stdout.strip()
    stderr = stderr.strip()
    if stdout and stderr:
        return f"{stdout}\n{stderr}"
    return stdout or stderr


def _extract_error_message(output: str, return_code: int, name: str) -> str:
    for line in output.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned[:240]
    return f"{name} exited with code {return_code}."


def _write_output_file(output_file: Path, output: str) -> None:
    try:
        output_file.write_text(output or "", encoding="utf-8")
    except OSError:
        return


def _write_metadata_file(
    output_file: Path,
    session_id: str,
    provider: str,
    prompt: str,
    success: bool,
) -> None:
    metadata_file = output_file.with_suffix(".meta.json")
    payload = {
        "session_id": session_id,
        "provider": provider,
        "prompt": prompt,
        "success": success,
        "timestamp": datetime.now().isoformat(),
        "model": "gemini-2.5-pro",
    }
    try:
        metadata_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        return
