"""Async subprocess dispatcher for real-time Claude Code CLI streaming."""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..core.runtime import project_id_for_path, project_runtime_dir

# Token limit phrases to detect when Claude hits usage limits
TOKEN_LIMIT_PHRASES = (
    "usage limit reached",
    "you've exceeded your usage limit",
    "you've exceeded your usage limit",
    "please wait until your limit resets",
)


@dataclass
class AsyncDispatchResult:
    """Result of an async dispatch operation."""

    success: bool
    session_id: str | None = None
    error_message: str | None = None
    dispatched_at: datetime = field(default_factory=datetime.now)
    output_file: Path | None = None
    provider: str = "claude"
    output: str | None = None
    token_limit_reached: bool = False
    cancelled: bool = False
    exit_code: int | None = None


def get_async_dispatch_output_path(working_dir: Path, session_id: str | None = None) -> tuple[str, Path]:
    """Generate a session ID and output file path for async dispatch.

    Returns:
        Tuple of (session_id, output_file_path)
    """
    project_path = working_dir.resolve()
    project_id = project_id_for_path(project_path)
    runtime_dir = project_runtime_dir(project_id)
    dispatch_output_dir = runtime_dir / "dispatch-output"
    dispatch_output_dir.mkdir(parents=True, exist_ok=True)

    if session_id is None:
        session_id = f"stream-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    output_file = dispatch_output_dir / f"{session_id}.log"
    return session_id, output_file


async def async_dispatch_stream(
    prompt: str,
    working_dir: Path,
    cli_path: str = "claude",
    timeout_seconds: int = 900,
    output_file: Path | None = None,
) -> AsyncGenerator[tuple[str, str], None]:
    """Stream Claude CLI output as an async generator.

    Uses asyncio.create_subprocess_exec which is safe from shell injection
    as it passes arguments directly without shell interpretation.

    Yields tuples of (event_type, data) where:
    - event_type is "output", "status", "error", or "complete"
    - data is the line content or status message

    Args:
        prompt: The prompt to send to Claude
        working_dir: Working directory for the CLI
        cli_path: Path to the claude CLI executable
        timeout_seconds: Maximum execution time
        output_file: Optional file to write output to

    Yields:
        Tuples of (event_type, data)
    """
    project_path = working_dir.resolve()
    # Using list form prevents shell injection - arguments are passed directly
    command = [cli_path, "-p", prompt]

    # Open output file if specified
    file_handle = None
    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        file_handle = open(output_file, "w", encoding="utf-8")

    proc: asyncio.subprocess.Process | None = None
    output_lines: list[str] = []

    try:
        yield ("status", "Launching Claude Code CLI...")

        # create_subprocess_exec is safe - it doesn't invoke a shell
        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            limit=1024 * 1024,  # 1MB buffer
        )

        yield ("status", "Claude Code is processing your task...")

        start_time = asyncio.get_event_loop().time()

        while True:
            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout_seconds:
                proc.kill()
                await proc.wait()
                yield ("error", f"Claude CLI timed out after {timeout_seconds}s.")
                yield ("complete", "failed")
                return

            # Try to read a line with a short timeout
            try:
                line_bytes = await asyncio.wait_for(
                    proc.stdout.readline(),
                    timeout=0.1
                )
            except TimeoutError:
                # No data available, check if process ended
                if proc.returncode is not None:
                    break
                continue

            if not line_bytes:
                # EOF reached
                break

            line = line_bytes.decode("utf-8", errors="replace").rstrip("\n\r")
            output_lines.append(line)

            # Write to file immediately
            if file_handle:
                file_handle.write(line + "\n")
                file_handle.flush()

            # Yield the output line
            yield ("output", line)

        # Wait for process to complete
        await proc.wait()
        return_code = proc.returncode
        output = "\n".join(output_lines)

        # Check for token limit
        if _detect_token_limit_reached(output):
            yield ("error", "Claude Code token limit reached. Choose an alternative provider or wait for reset.")
            yield ("complete", "token_limit")
            return

        # Check return code
        if return_code != 0:
            error_msg = _extract_error_message(output, return_code)
            yield ("error", error_msg)
            yield ("complete", "failed")
            return

        yield ("status", "Claude Code completed successfully.")
        yield ("complete", "success")

    except FileNotFoundError:
        yield ("error", f"Claude CLI not found at '{cli_path}'.")
        yield ("complete", "failed")
    except asyncio.CancelledError:
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except TimeoutError:
                proc.kill()
                await proc.wait()
        yield ("status", "Dispatch cancelled.")
        yield ("complete", "cancelled")
        raise
    except Exception as exc:
        yield ("error", str(exc))
        yield ("complete", "failed")
    finally:
        if file_handle:
            file_handle.close()


class AsyncDispatchJob:
    """Manages an async dispatch job with cancellation support."""

    def __init__(
        self,
        job_id: str,
        prompt: str,
        working_dir: Path,
        cli_path: str = "claude",
        timeout_seconds: int = 900,
    ):
        self.job_id = job_id
        self.prompt = prompt
        self.working_dir = working_dir
        self.cli_path = cli_path
        self.timeout_seconds = timeout_seconds

        self._task: asyncio.Task | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._cancelled = False
        self._output_lines: list[str] = []
        self._queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue()
        self._started_at: datetime | None = None
        self._finished_at: datetime | None = None
        self._result: AsyncDispatchResult | None = None
        self._output_file: Path | None = None
        self._sequence = 0

    @property
    def output_file(self) -> Path | None:
        return self._output_file

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def start(self, output_file: Path | None = None) -> None:
        """Start the dispatch job."""
        if self._task is not None:
            raise RuntimeError("Job already started")

        self._output_file = output_file
        self._started_at = datetime.now()
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        """Internal coroutine that runs the dispatch and populates the queue."""
        try:
            async for event_type, data in async_dispatch_stream(
                prompt=self.prompt,
                working_dir=self.working_dir,
                cli_path=self.cli_path,
                timeout_seconds=self.timeout_seconds,
                output_file=self._output_file,
            ):
                if event_type == "output":
                    self._output_lines.append(data)
                self._sequence += 1
                await self._queue.put((event_type, data))

                if event_type == "complete":
                    self._finished_at = datetime.now()
                    self._build_result(data)
                    break

        except asyncio.CancelledError:
            self._cancelled = True
            self._finished_at = datetime.now()
            self._sequence += 1
            await self._queue.put(("complete", "cancelled"))
            self._build_result("cancelled")
        finally:
            # Signal end of stream
            await self._queue.put(None)

    def _build_result(self, completion_status: str) -> None:
        """Build the final result from completion status."""
        output = "\n".join(self._output_lines)
        self._result = AsyncDispatchResult(
            success=(completion_status == "success"),
            session_id=self.job_id,
            output_file=self._output_file,
            output=output or None,
            token_limit_reached=(completion_status == "token_limit"),
            cancelled=(completion_status == "cancelled"),
            exit_code=self._proc.returncode if self._proc else None,
        )

    async def events(self) -> AsyncGenerator[tuple[str, str, int], None]:
        """Yield events as (event_type, data, sequence) tuples."""
        while True:
            event = await self._queue.get()
            if event is None:
                break
            event_type, data = event
            yield (event_type, data, self._sequence)

    def cancel(self) -> bool:
        """Cancel the running job."""
        if self._task is None or self._task.done():
            return False

        self._cancelled = True
        self._task.cancel()
        return True

    def get_result(self) -> AsyncDispatchResult | None:
        """Get the final result if job is complete."""
        return self._result


def _detect_token_limit_reached(output: str) -> bool:
    """Detect Claude usage-limit messages in CLI output."""
    normalized = output.lower()
    return any(phrase in normalized for phrase in TOKEN_LIMIT_PHRASES)


def _extract_error_message(output: str, return_code: int) -> str:
    """Extract a concise error message from CLI output."""
    for line in output.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned[:240]
    return f"Claude CLI exited with code {return_code}."
