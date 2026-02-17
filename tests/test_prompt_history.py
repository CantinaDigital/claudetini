"""Tests for prompt history storage."""

from src.core.cost_tracker import TokenUsage
from src.core.prompt_history import PromptHistoryStore


def test_prompt_history_versioning(temp_dir):
    store = PromptHistoryStore("proj-1", base_dir=temp_dir)
    v1 = store.add_version("Item A", "Prompt 1")
    v2 = store.add_version("Item A", "Prompt 2")

    assert v1.version == 1
    assert v2.version == 2


def test_prompt_history_outcome(temp_dir):
    store = PromptHistoryStore("proj-1", base_dir=temp_dir)
    version = store.add_version("Item A", "Prompt 1")
    store.mark_dispatched("Item A", version.version, session_id="session-1")
    store.mark_outcome(
        "Item A",
        version.version,
        "success",
        usage=TokenUsage(input_tokens=10, output_tokens=20),
    )

    history = store.get_history("Item A")
    assert len(history.versions) == 1
    assert history.versions[0].outcome == "success"
    assert history.versions[0].token_usage is not None


def test_prompt_history_mark_outcome_for_session(temp_dir):
    store = PromptHistoryStore("proj-1", base_dir=temp_dir)
    version = store.add_version("Milestone Item", "Prompt 1")
    store.mark_dispatched("Milestone Item", version.version, session_id="session-2")

    marked = store.mark_outcome_for_session(
        session_id="session-2",
        outcome="partial",
        usage=TokenUsage(input_tokens=5, output_tokens=7),
    )

    assert marked is True
    history = store.get_history("Milestone Item")
    assert history.versions[0].outcome == "partial"
