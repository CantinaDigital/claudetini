"""Tests for session hook manager."""

from src.core.session_hooks import HookConfig, HookSpec, SessionHookManager


def test_session_hooks_success_and_required_failure(temp_dir):
    manager = SessionHookManager("proj123", temp_dir, base_dir=temp_dir)
    manager.save_config(
        HookConfig(
            pre_session=[HookSpec(command="echo hello", timeout=5, required=True)],
        )
    )

    ok, results = manager.run_hooks("pre_session")
    assert ok is True
    assert results
    assert results[0].success is True

    manager.save_config(
        HookConfig(
            pre_session=[HookSpec(command="command_that_does_not_exist", timeout=5, required=True)],
        )
    )

    ok, results = manager.run_hooks("pre_session")
    assert ok is False
    assert results
    assert results[0].success is False
