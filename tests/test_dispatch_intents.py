"""Tests for dispatch intent parsing and local-action detection."""

from src.core.dispatch_intents import detect_local_action, parse_dispatch_envelope


def test_parse_dispatch_envelope_with_tags() -> None:
    envelope = parse_dispatch_envelope(
        "[dispatch_mode:with_review]\n[queue_force:true]\n[roadmap_item:Refactor parser]\n[local_action:git_push]\ngit push"
    )

    assert envelope.dispatch_mode == "with_review"
    assert envelope.force_dispatch is True
    assert envelope.roadmap_item == "Refactor parser"
    assert envelope.local_action == "git_push"
    assert envelope.prompt == "git push"


def test_parse_dispatch_envelope_infers_local_action_from_prompt() -> None:
    envelope = parse_dispatch_envelope("git stash pop")
    assert envelope.local_action == "git_stash_pop"
    assert envelope.roadmap_item is None
    assert envelope.prompt == "git stash pop"


def test_detect_local_action_commit_all_alias() -> None:
    assert detect_local_action("commit all") == "git_commit_all"
    assert detect_local_action("git add -A && git commit") == "git_commit_all"


def test_detect_local_action_returns_none_for_regular_prompt() -> None:
    assert detect_local_action("Implement roadmap task with tests") is None
