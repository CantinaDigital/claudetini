"""Claude Code CLI dispatch with Phase 2 system-prompt and usage capture."""

from __future__ import annotations

import json
import os
import platform
import re
import shlex
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..core.runtime import RUNTIME_HOME, project_id_for_path, project_runtime_dir
from ..core.secrets_scanner import SecretsScanner

TOKEN_LIMIT_PHRASES = (
    "you've exceeded your usage limit",
    "please wait until your limit resets",
    "your claude.ai usage limit",
)


def get_dispatch_output_path(working_dir: Path, session_id: str | None = None) -> tuple[str, Path]:
    """Generate a session ID and output file path for a dispatch.

    This allows callers to know the output file path before dispatch starts,
    enabling them to monitor the file during execution.

    Returns:
        Tuple of (session_id, output_file_path)
    """
    project_path = working_dir.resolve()
    project_id = project_id_for_path(project_path)
    runtime_dir = project_runtime_dir(project_id)
    dispatch_output_dir = runtime_dir / "dispatch-output"
    dispatch_output_dir.mkdir(parents=True, exist_ok=True)

    if session_id is None:
        session_id = f"dispatch-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    output_file = dispatch_output_dir / f"{session_id}.log"
    return session_id, output_file


@dataclass
class DispatchResult:
    """Result of dispatching a Claude Code session."""

    success: bool
    session_id: str | None = None
    terminal_pid: int | None = None
    error_message: str | None = None
    dispatched_at: datetime = field(default_factory=datetime.now)
    output_file: Path | None = None
    system_prompt_file: Path | None = None
    agents_enabled: bool = False
    provider: str = "claude"
    output: str | None = None
    token_limit_reached: bool = False


def dispatch_task(
    prompt: str,
    working_dir: Path,
    cli_path: str = "claude",
    timeout_seconds: int = 900,
    system_prompt_file: Path | None = None,
    agents_json: str | None = None,
    output_file: Path | None = None,
    model: str | None = None,
) -> DispatchResult:
    """Run Claude CLI directly and return a normalized dispatch result.

    Output is streamed to file incrementally so callers can monitor progress
    by reading the log file during execution.

    Args:
        output_file: Optional pre-determined output file path. If provided,
            allows callers to monitor the file during execution. If not
            provided, a new file will be created.
    """
    project_path = working_dir.resolve()
    project_id = project_id_for_path(project_path)
    runtime_dir = project_runtime_dir(project_id)
    dispatch_output_dir = runtime_dir / "dispatch-output"
    dispatch_output_dir.mkdir(parents=True, exist_ok=True)

    session_id = f"dispatch-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    if output_file is None:
        output_file = dispatch_output_dir / f"{session_id}.log"

    command = [cli_path]
    # acceptEdits permission mode ensures Claude can make file changes without
    # interactive prompts. Essential for automated dispatch from the sidecar.
    command.extend(["--permission-mode", "acceptEdits"])
    if model:
        command.extend(["--model", model])
    if system_prompt_file:
        command.extend(["--append-system-prompt-file", str(system_prompt_file)])
    if agents_json:
        command.extend(["--agents", agents_json])
    command.extend(["-p", prompt])

    try:
        # Use Popen to stream output incrementally to file
        # CRITICAL: stdin=DEVNULL prevents hanging when Claude CLI tries to read input
        # in a non-TTY environment (like the sidecar daemon). Without this, any
        # interactive prompt (permissions, confirmations) blocks indefinitely.
        # Also unset ANTHROPIC_API_KEY to ensure OAuth login is used instead
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        proc = subprocess.Popen(
            command,
            cwd=project_path,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # Line buffered
            env=env,
        )
    except FileNotFoundError:
        return DispatchResult(
            success=False,
            session_id=session_id,
            error_message=f"Claude CLI not found at '{cli_path}'.",
            output_file=output_file,
            provider="claude",
        )
    except Exception as exc:
        return DispatchResult(
            success=False,
            session_id=session_id,
            error_message=str(exc),
            output_file=output_file,
            provider="claude",
        )

    # Stream output to file incrementally so callers can monitor progress
    output_lines: list[str] = []
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            start_time = datetime.now()
            while True:
                # Check timeout
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > timeout_seconds:
                    proc.kill()
                    proc.wait()
                    output = "\n".join(output_lines)
                    return DispatchResult(
                        success=False,
                        session_id=session_id,
                        error_message=f"Claude CLI timed out after {timeout_seconds}s.",
                        output_file=output_file,
                        provider="claude",
                        output=output or None,
                    )

                # Read line (non-blocking would be better but this works)
                line = proc.stdout.readline()
                if line:
                    output_lines.append(line.rstrip("\n\r"))
                    f.write(line)
                    f.flush()  # Ensure line is written immediately
                elif proc.poll() is not None:
                    # Process finished
                    break
    except Exception as exc:
        proc.kill()
        proc.wait()
        return DispatchResult(
            success=False,
            session_id=session_id,
            error_message=f"Error reading CLI output: {exc}",
            output_file=output_file,
            provider="claude",
            output="\n".join(output_lines) or None,
        )

    return_code = proc.returncode
    output = "\n".join(output_lines)
    token_limit_reached = _detect_token_limit_reached(output)

    if token_limit_reached:
        return DispatchResult(
            success=False,
            session_id=session_id,
            error_message="Claude Code token limit reached. Choose an alternative provider or wait for reset.",
            output_file=output_file,
            provider="claude",
            output=output or None,
            token_limit_reached=True,
        )

    if return_code != 0:
        return DispatchResult(
            success=False,
            session_id=session_id,
            error_message=_extract_error_message(output, return_code),
            output_file=output_file,
            provider="claude",
            output=output or None,
        )

    return DispatchResult(
        success=True,
        session_id=session_id,
        output_file=output_file,
        provider="claude",
        output=output or None,
        system_prompt_file=system_prompt_file,
        agents_enabled=bool(agents_json),
    )


def dispatch_bootstrap(
    prompts: list[tuple[str, str]],
    working_dir: Path,
    cli_path: str = "claude",
    timeout_per_prompt: int = 600,
    progress_callback: callable | None = None,
) -> list[DispatchResult]:
    """Run multiple Claude CLI prompts sequentially for bootstrap operations.

    This is specifically designed for bootstrap workflows where multiple
    artifacts need to be generated in sequence, with each step potentially
    building on the results of previous steps.

    Args:
        prompts: List of (step_name, prompt_text) tuples to execute in order
        working_dir: Project directory
        cli_path: Path to Claude CLI
        timeout_per_prompt: Timeout for each individual prompt
        progress_callback: Optional callback(step_name, index, total, result)
                          called after each step completes

    Returns:
        List of DispatchResult objects, one per prompt

    Example:
        prompts = [
            ("analyze", "Analyze this project..."),
            ("roadmap", "Generate a roadmap..."),
            ("claude_md", "Create CLAUDE.md..."),
        ]
        results = dispatch_bootstrap(prompts, Path("/my/project"))
        for result in results:
            if not result.success:
                print(f"Failed: {result.error_message}")
    """
    results: list[DispatchResult] = []
    total_prompts = len(prompts)

    for idx, (step_name, prompt) in enumerate(prompts, start=1):
        # Execute this prompt
        result = dispatch_task(
            prompt=prompt,
            working_dir=working_dir,
            cli_path=cli_path,
            timeout_seconds=timeout_per_prompt,
        )

        results.append(result)

        # Call progress callback if provided
        if progress_callback:
            try:
                progress_callback(step_name, idx, total_prompts, result)
            except Exception:
                # Don't let callback failures break the bootstrap
                pass

        # If this step failed and was critical, stop the bootstrap
        if not result.success:
            # For now, continue even on failure to collect all errors
            # Caller can decide whether to stop based on result.success
            pass

    return results


class ClaudeDispatcher:
    """Dispatcher for launching Claude Code sessions."""

    def __init__(self, project_path: Path):
        self.project_path = project_path.resolve()
        self.project_id = project_id_for_path(self.project_path)
        self.runtime_dir = project_runtime_dir(self.project_id)
        self.dispatch_output_dir = self.runtime_dir / "dispatch-output"
        self.dispatch_output_dir.mkdir(parents=True, exist_ok=True)

    def dispatch(
        self,
        prompt: str,
        terminal: str = "default",
        system_prompt_file: Path | None = None,
        agents_json: str | None = None,
    ) -> DispatchResult:
        """Dispatch a Claude Code session with output capture."""
        session_id = f"dispatch-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        output_file = self.dispatch_output_dir / f"{session_id}.jsonl"

        try:
            claude_cmd = self._build_claude_command(
                prompt=prompt,
                output_file=output_file,
                system_prompt_file=system_prompt_file,
                agents_json=agents_json,
            )

            if platform.system() == "Darwin":
                result = self._dispatch_macos(claude_cmd, terminal)
            else:
                result = DispatchResult(
                    success=False,
                    error_message=f"Unsupported platform: {platform.system()}. macOS only for MVP.",
                )

            if result.success:
                result.session_id = session_id
                result.output_file = output_file
                result.system_prompt_file = system_prompt_file
                result.agents_enabled = bool(agents_json)
            return result

        except FileNotFoundError:
            return DispatchResult(
                success=False,
                error_message="Claude CLI not found. Ensure 'claude' is installed and in PATH.",
            )
        except Exception as exc:
            return DispatchResult(
                success=False,
                error_message=str(exc),
            )

    def _build_claude_command(
        self,
        prompt: str,
        output_file: Path,
        system_prompt_file: Path | None = None,
        agents_json: str | None = None,
    ) -> str:
        quoted_project = shlex.quote(str(self.project_path))
        quoted_prompt = shlex.quote(prompt.replace("\n", " ").strip())
        quoted_output = shlex.quote(str(output_file))

        prompt_flag = f"-p {quoted_prompt}"
        system_flag = ""
        if system_prompt_file:
            system_flag = f"--append-system-prompt-file {shlex.quote(str(system_prompt_file))} "
        agents_flag = ""
        if agents_json:
            agents_flag = f"--agents {shlex.quote(agents_json)} "

        # Build the core claude command
        # Use streaming text output (not JSON) so user sees real-time progress
        # The output is still saved to file for later reference
        claude_cmd = f"claude {system_flag}{agents_flag}{prompt_flag} 2>&1 | tee {quoted_output}"

        # Wrap with clear user feedback
        return (
            f"cd {quoted_project} && "
            f"printf '\\033[1;36m' && "  # Cyan bold
            f"printf '╔══════════════════════════════════════╗\\n' && "
            f"printf '║     Claudetini Dispatch           ║\\n' && "
            f"printf '╠══════════════════════════════════════╣\\n' && "
            f"printf '\\033[0m' && "  # Reset
            f"printf '\\033[36m' && "  # Cyan
            f"printf '║ Project: {self.project_path.name:<28} ║\\n' && "
            f"printf '║ Log: {output_file.name:<32} ║\\n' && "
            f"printf '╚══════════════════════════════════════╝\\n' && "
            f"printf '\\033[0m\\n' && "  # Reset
            f"{claude_cmd}; "  # Use ; not && so we always show completion message
            f"EXIT_CODE=$?; "
            f"printf '\\n\\033[1;36m' && "  # Cyan bold
            f"printf '╔══════════════════════════════════════╗\\n' && "
            f"if [ $EXIT_CODE -eq 0 ]; then "
            f"printf '║  ✓ Session Complete                  ║\\n'; "
            f"else "
            f"printf '║  ✗ Session Ended (exit: '$EXIT_CODE')           ║\\n'; "
            f"fi && "
            f"printf '╚══════════════════════════════════════╝\\n' && "
            f"printf '\\033[0m'"  # Reset
        )

    def _dispatch_macos(self, claude_cmd: str, terminal: str) -> DispatchResult:
        """Dispatch on macOS using osascript."""
        if terminal == "iterm":
            # Check if iTerm is available BEFORE trying to open a window
            if self._is_iterm_available():
                return self._dispatch_iterm(claude_cmd)
            # iTerm not available - use Terminal.app without fallback
            # (Don't silently fall back - that causes two windows if iTerm
            # partially succeeds before failing)
        return self._dispatch_terminal_app(claude_cmd)

    def _is_iterm_available(self) -> bool:
        """Check if iTerm2 is installed and accessible."""
        try:
            # Check if iTerm exists in Applications
            result = subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to (name of processes) contains "iTerm2"'],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0 and "true" in result.stdout.lower()
        except Exception:
            return False

    def _dispatch_iterm(self, claude_cmd: str) -> DispatchResult:
        """Dispatch using iTerm2."""
        escaped_cmd = _escape_applescript_text(claude_cmd)
        script = (
            "tell application \"iTerm\"\n"
            "    activate\n"
            "    create window with default profile\n"
            "    tell current session of current window\n"
            f"        write text \"{escaped_cmd}\"\n"
            "    end tell\n"
            "end tell"
        )

        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"iTerm dispatch failed: {result.stderr}")
        return DispatchResult(success=True)

    def _dispatch_terminal_app(self, claude_cmd: str) -> DispatchResult:
        """Dispatch using macOS Terminal.app."""
        escaped = _escape_applescript_text(claude_cmd)
        # Use a precise AppleScript that:
        # 1. Creates a new window with our command
        # 2. Focuses ONLY that window (not all Terminal windows)
        # 3. Sets a title so user knows it's from Claudetini
        applescript = (
            "tell application \"Terminal\"\n"
            f"    set newWindow to do script \"{escaped}\"\n"
            "    set custom title of front window to \"Claudetini Dispatch\"\n"
            "    tell front window\n"
            "        set visible to true\n"
            "    end tell\n"
            "end tell\n"
            "tell application \"System Events\"\n"
            "    tell process \"Terminal\"\n"
            "        set frontmost to true\n"
            "        perform action \"AXRaise\" of front window\n"
            "    end tell\n"
            "end tell"
        )
        result = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Terminal dispatch failed: {result.stderr}")
        return DispatchResult(success=True)

    def check_claude_available(self) -> tuple[bool, str | None]:
        """Check if Claude CLI is available."""
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
            return False, "Claude CLI returned non-zero exit code"
        except FileNotFoundError:
            return False, "Claude CLI not found in PATH"
        except subprocess.TimeoutExpired:
            return False, "Claude CLI check timed out"
        except Exception as exc:
            return False, str(exc)


class DispatchLogger:
    """Logger for tracking dispatched sessions."""

    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path or (RUNTIME_HOME / "dispatch-log.json")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_log()

    def log_dispatch(
        self,
        result: DispatchResult,
        prompt: str,
        project_name: str,
        project_id: str | None = None,
        project_path: Path | None = None,
    ) -> None:
        """Log a dispatch event."""
        safe_prompt = _redact_prompt_preview(prompt, max_chars=240)
        entry = {
            "timestamp": result.dispatched_at.isoformat(),
            "project": project_name,
            "project_id": project_id,
            "project_path": str(project_path) if project_path else None,
            "prompt_preview": safe_prompt,
            "success": result.success,
            "error": result.error_message,
            "session_id": result.session_id,
            "output_file": str(result.output_file) if result.output_file else None,
            "system_prompt_file": str(result.system_prompt_file) if result.system_prompt_file else None,
            "agents_enabled": result.agents_enabled,
            "provider": result.provider,
            "token_limit_reached": result.token_limit_reached,
        }

        logs = []
        if self.log_path.exists():
            try:
                logs = json.loads(self.log_path.read_text())
            except json.JSONDecodeError:
                logs = []

        logs.append(entry)
        logs = logs[-500:]
        self.log_path.write_text(json.dumps(logs, indent=2))

    def get_recent_dispatches(self, limit: int = 10) -> list[dict]:
        """Get recent dispatch events."""
        if not self.log_path.exists():
            return []
        try:
            logs = json.loads(self.log_path.read_text())
        except json.JSONDecodeError:
            return []
        return logs[-limit:][::-1]

    def _migrate_legacy_log(self) -> None:
        legacy = Path.home() / ".claudetini" / "dispatch_log.json"
        if self.log_path.exists() or not legacy.exists():
            return
        try:
            self.log_path.write_text(legacy.read_text())
        except OSError:
            return


def _escape_applescript_text(text: str) -> str:
    """Escape text payload used inside AppleScript string literals."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\r", "")
    escaped = escaped.replace("\n", "\\n")
    return escaped


def _redact_prompt_preview(prompt: str, max_chars: int = 120) -> str:
    """Redact sensitive patterns in persisted prompt previews."""
    preview = prompt.strip()
    if len(preview) > max_chars:
        preview = preview[:max_chars] + "..."
    redacted = preview
    for _name, pattern, _severity, _description in SecretsScanner.SECRET_PATTERNS:
        try:
            redacted = re.sub(pattern, "[REDACTED]", redacted)
        except re.error:
            continue
    return redacted


def _combine_cli_output(stdout: str, stderr: str) -> str:
    """Return normalized CLI output from stdout/stderr."""
    stdout = stdout.strip()
    stderr = stderr.strip()
    if stdout and stderr:
        return f"{stdout}\n{stderr}"
    return stdout or stderr


def _detect_token_limit_reached(output: str) -> bool:
    """Detect Claude usage-limit messages in CLI output.

    Only detects actual Claude subscription/API token limits, not:
    - Generic rate limits (e.g., from external APIs)
    - Quota errors from other services
    - Error messages that mention these words in passing
    """
    normalized = output.lower()
    # Must match specific Claude token limit phrases to avoid false positives
    # Do NOT trigger on generic "rate limit" or "quota exceeded" messages
    for phrase in TOKEN_LIMIT_PHRASES:
        if phrase in normalized:
            # Additional validation: ensure it's not just mentioning limits in context
            # Look for actual error indicators near the phrase
            lines_with_phrase = [line for line in output.lower().split('\n') if phrase in line]
            for line in lines_with_phrase:
                # Check if this line contains actual error indicators
                if any(indicator in line for indicator in ['error', 'failed', 'exceeded', 'reached']):
                    return True
    return False


def _extract_error_message(output: str, return_code: int) -> str:
    """Extract a concise error message from CLI output."""
    for line in output.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned[:240]
    return f"Claude CLI exited with code {return_code}."


def _write_output_file(output_file: Path, output: str) -> None:
    try:
        output_file.write_text(output or "", encoding="utf-8")
    except OSError:
        return
