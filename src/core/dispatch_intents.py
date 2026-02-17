"""Dispatch envelope parsing and local-action intent detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

LocalAction = Literal["git_push", "git_commit_all", "git_stash_pop"]

_LOCAL_ACTIONS: set[str] = {"git_push", "git_commit_all", "git_stash_pop"}


@dataclass(frozen=True)
class DispatchEnvelope:
    """Normalized dispatch payload extracted from a raw UI prompt string."""

    prompt: str
    dispatch_mode: str
    force_dispatch: bool
    local_action: LocalAction | None
    roadmap_item: str | None


def parse_dispatch_envelope(prompt: str) -> DispatchEnvelope:
    """Parse optional dispatch tags prepended by UI controls."""
    mode = "standard"
    force_dispatch = False
    local_action: LocalAction | None = None
    roadmap_item: str | None = None
    lines = prompt.splitlines()
    start = 0

    while start < len(lines):
        line = lines[start].strip()
        if not line:
            start += 1
            continue

        if line.startswith("[dispatch_mode:") and line.endswith("]"):
            mode = line[len("[dispatch_mode:"):-1].strip() or "standard"
            start += 1
            continue

        if line == "[queue_force:true]":
            force_dispatch = True
            start += 1
            continue

        if line.startswith("[local_action:") and line.endswith("]"):
            candidate = line[len("[local_action:"):-1].strip().lower()
            if candidate in _LOCAL_ACTIONS:
                local_action = candidate  # type: ignore[assignment]
            start += 1
            continue

        if line.startswith("[roadmap_item:") and line.endswith("]"):
            roadmap_item = line[len("[roadmap_item:"):-1].strip() or None
            start += 1
            continue

        break

    cleaned = "\n".join(lines[start:]).strip()
    normalized_prompt = cleaned or prompt.strip()

    if local_action is None:
        local_action = detect_local_action(normalized_prompt)

    return DispatchEnvelope(
        prompt=normalized_prompt,
        dispatch_mode=mode,
        force_dispatch=force_dispatch,
        local_action=local_action,
        roadmap_item=roadmap_item,
    )


def detect_local_action(prompt: str) -> LocalAction | None:
    """Infer a direct local action from simple explicit git commands."""
    normalized = " ".join(prompt.strip().lower().split())
    if normalized == "git push":
        return "git_push"
    if normalized == "git stash pop":
        return "git_stash_pop"
    if normalized in {"git add -a && git commit", "commit all"}:
        return "git_commit_all"
    return None
