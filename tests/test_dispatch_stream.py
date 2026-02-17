"""Tests for async dispatch streaming functionality."""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.async_dispatcher import (
    AsyncDispatchJob,
    AsyncDispatchResult,
    async_dispatch_stream,
    get_async_dispatch_output_path,
    _detect_token_limit_reached,
    _extract_error_message,
)


class TestAsyncDispatchOutputPath:
    """Tests for get_async_dispatch_output_path."""

    def test_generates_unique_session_id(self, tmp_path: Path):
        """Should generate unique session IDs."""
        with patch("src.agents.async_dispatcher.project_id_for_path") as mock_pid:
            with patch("src.agents.async_dispatcher.project_runtime_dir") as mock_runtime:
                mock_pid.return_value = "test-project"
                mock_runtime.return_value = tmp_path

                session_id1, path1 = get_async_dispatch_output_path(tmp_path)
                session_id2, path2 = get_async_dispatch_output_path(tmp_path)

                assert session_id1 != session_id2
                assert "stream-" in session_id1
                assert "stream-" in session_id2

    def test_uses_provided_session_id(self, tmp_path: Path):
        """Should use provided session ID."""
        with patch("src.agents.async_dispatcher.project_id_for_path") as mock_pid:
            with patch("src.agents.async_dispatcher.project_runtime_dir") as mock_runtime:
                mock_pid.return_value = "test-project"
                mock_runtime.return_value = tmp_path

                session_id, path = get_async_dispatch_output_path(
                    tmp_path, session_id="custom-session"
                )

                assert session_id == "custom-session"
                assert "custom-session.log" in str(path)


class TestTokenLimitDetection:
    """Tests for token limit detection."""

    @pytest.mark.parametrize(
        "output,expected",
        [
            ("usage limit reached", True),
            ("you've exceeded your usage limit", True),
            ("please wait until your limit resets", True),
            ("Normal output here", False),
            ("Error: something else", False),
            ("USAGE LIMIT REACHED", True),  # Case insensitive
        ],
    )
    def test_detect_token_limit(self, output: str, expected: bool):
        """Should detect token limit messages."""
        assert _detect_token_limit_reached(output) == expected


class TestErrorMessageExtraction:
    """Tests for error message extraction."""

    def test_extracts_first_non_empty_line(self):
        """Should extract first non-empty line as error."""
        output = "\n\nError: Something went wrong\nMore details"
        result = _extract_error_message(output, 1)
        assert result == "Error: Something went wrong"

    def test_truncates_long_messages(self):
        """Should truncate long error messages."""
        long_line = "x" * 300
        result = _extract_error_message(long_line, 1)
        assert len(result) <= 240

    def test_fallback_to_exit_code(self):
        """Should use exit code when no output."""
        result = _extract_error_message("", 42)
        assert result == "Claude CLI exited with code 42."


class TestAsyncDispatchStream:
    """Tests for the async dispatch stream generator."""

    @pytest.mark.asyncio
    async def test_yields_status_events(self, tmp_path: Path):
        """Should yield status events at start."""
        events = []

        # Mock subprocess to return immediately
        mock_proc = AsyncMock()
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.returncode = 0
        mock_proc.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            async for event_type, data in async_dispatch_stream(
                prompt="test",
                working_dir=tmp_path,
            ):
                events.append((event_type, data))
                if event_type == "complete":
                    break

        # Check we got status events
        status_events = [e for e in events if e[0] == "status"]
        assert len(status_events) >= 2

    @pytest.mark.asyncio
    async def test_yields_output_events(self, tmp_path: Path):
        """Should yield output events for each line."""
        lines = [b"Line 1\n", b"Line 2\n", b""]
        line_iter = iter(lines)

        mock_proc = AsyncMock()
        mock_proc.stdout.readline = AsyncMock(side_effect=lambda: next(line_iter))
        mock_proc.returncode = None
        mock_proc.poll = MagicMock(side_effect=[None, None, 0])
        mock_proc.wait = AsyncMock()

        # Set returncode after lines are consumed
        async def set_returncode():
            await asyncio.sleep(0)
            mock_proc.returncode = 0

        events = []
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            async for event_type, data in async_dispatch_stream(
                prompt="test",
                working_dir=tmp_path,
            ):
                events.append((event_type, data))
                if event_type == "complete":
                    break

        output_events = [e for e in events if e[0] == "output"]
        assert len(output_events) == 2
        assert output_events[0][1] == "Line 1"
        assert output_events[1][1] == "Line 2"

    @pytest.mark.asyncio
    async def test_handles_cli_not_found(self, tmp_path: Path):
        """Should yield error when CLI not found."""
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("not found"),
        ):
            events = []
            async for event_type, data in async_dispatch_stream(
                prompt="test",
                working_dir=tmp_path,
                cli_path="nonexistent-cli",
            ):
                events.append((event_type, data))

        error_events = [e for e in events if e[0] == "error"]
        assert len(error_events) == 1
        assert "not found" in error_events[0][1].lower()

    @pytest.mark.asyncio
    async def test_handles_cancellation(self, tmp_path: Path):
        """Should handle cancellation gracefully."""
        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        # Make readline block indefinitely
        async def blocking_readline():
            await asyncio.sleep(100)
            return b""

        mock_proc.stdout.readline = blocking_readline

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            gen = async_dispatch_stream(prompt="test", working_dir=tmp_path)

            # Start iteration
            await gen.asend(None)  # Get first event

            # Cancel
            with pytest.raises(asyncio.CancelledError):
                await gen.athrow(asyncio.CancelledError())


class TestAsyncDispatchJob:
    """Tests for AsyncDispatchJob class."""

    @pytest.mark.asyncio
    async def test_job_lifecycle(self, tmp_path: Path):
        """Should manage job lifecycle correctly."""
        job = AsyncDispatchJob(
            job_id="test-job-1",
            prompt="test prompt",
            working_dir=tmp_path,
        )

        assert not job.is_running
        assert not job.is_cancelled
        assert job.get_result() is None

    @pytest.mark.asyncio
    async def test_cancel_not_started(self, tmp_path: Path):
        """Should return False when cancelling non-started job."""
        job = AsyncDispatchJob(
            job_id="test-job-2",
            prompt="test",
            working_dir=tmp_path,
        )

        result = job.cancel()
        assert result is False


class TestAsyncDispatchResult:
    """Tests for AsyncDispatchResult dataclass."""

    def test_default_values(self):
        """Should have correct default values."""
        result = AsyncDispatchResult(success=True)

        assert result.success is True
        assert result.session_id is None
        assert result.error_message is None
        assert result.provider == "claude"
        assert result.token_limit_reached is False
        assert result.cancelled is False

    def test_with_all_values(self):
        """Should store all provided values."""
        output_file = Path("/tmp/test.log")
        result = AsyncDispatchResult(
            success=False,
            session_id="test-session",
            error_message="Test error",
            output_file=output_file,
            output="Some output",
            token_limit_reached=True,
            cancelled=False,
            exit_code=1,
        )

        assert result.success is False
        assert result.session_id == "test-session"
        assert result.error_message == "Test error"
        assert result.output_file == output_file
        assert result.output == "Some output"
        assert result.token_limit_reached is True
        assert result.exit_code == 1
