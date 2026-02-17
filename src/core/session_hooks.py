"""Configurable pre/post session hook execution."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .runtime import project_runtime_dir

HOOK_TYPES = ("pre_session", "post_session", "pre_merge", "post_merge")


@dataclass
class HookSpec:
    """Single configured command hook."""

    command: str
    timeout: int = 60
    required: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> HookSpec:
        return cls(
            command=str(data.get("command", "")).strip(),
            timeout=int(data.get("timeout", 60) or 60),
            required=bool(data.get("required", False)),
        )

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "timeout": self.timeout,
            "required": self.required,
        }


@dataclass
class HookConfig:
    """All hook lists keyed by hook type."""

    pre_session: list[HookSpec] = field(default_factory=list)
    post_session: list[HookSpec] = field(default_factory=list)
    pre_merge: list[HookSpec] = field(default_factory=list)
    post_merge: list[HookSpec] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> HookConfig:
        hooks = data.get("hooks", data) if isinstance(data, dict) else {}

        def _list(name: str) -> list[HookSpec]:
            values = hooks.get(name, []) if isinstance(hooks, dict) else []
            if not isinstance(values, list):
                return []
            return [HookSpec.from_dict(item) for item in values if isinstance(item, dict)]

        return cls(
            pre_session=_list("pre_session"),
            post_session=_list("post_session"),
            pre_merge=_list("pre_merge"),
            post_merge=_list("post_merge"),
        )

    def to_dict(self) -> dict:
        return {
            "hooks": {
                "pre_session": [item.to_dict() for item in self.pre_session],
                "post_session": [item.to_dict() for item in self.post_session],
                "pre_merge": [item.to_dict() for item in self.pre_merge],
                "post_merge": [item.to_dict() for item in self.post_merge],
            }
        }


@dataclass
class HookResult:
    """Result for one executed hook."""

    hook_type: str
    command: str
    success: bool
    required: bool
    output: str = ""
    error: str = ""


class SessionHookManager:
    """Load and execute session hooks for a project."""

    def __init__(self, project_id: str, project_path: Path, base_dir: Path | None = None):
        self.project_id = project_id
        self.project_path = project_path.resolve()
        self.project_dir = project_runtime_dir(project_id, base_dir=base_dir)
        self.config_file = self.project_dir / "session-hooks.json"

    def load_config(self) -> HookConfig:
        if not self.config_file.exists():
            return HookConfig()
        try:
            data = json.loads(self.config_file.read_text())
        except (json.JSONDecodeError, OSError):
            return HookConfig()
        return HookConfig.from_dict(data)

    def save_config(self, config: HookConfig) -> None:
        self.config_file.write_text(json.dumps(config.to_dict(), indent=2))

    def run_hooks(self, hook_type: str) -> tuple[bool, list[HookResult]]:
        if hook_type not in HOOK_TYPES:
            return False, [HookResult(hook_type=hook_type, command="", success=False, required=True, error="Unknown hook type")]

        config = self.load_config()
        hooks: list[HookSpec] = list(getattr(config, hook_type))
        results: list[HookResult] = []

        for hook in hooks:
            if not hook.command:
                continue

            result = self._run_single(hook_type, hook)
            results.append(result)

            if hook.required and not result.success:
                return False, results

        return True, results

    def _run_single(self, hook_type: str, hook: HookSpec) -> HookResult:
        try:
            process = subprocess.run(
                hook.command,
                shell=True,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=max(1, int(hook.timeout)),
            )
            return HookResult(
                hook_type=hook_type,
                command=hook.command,
                success=(process.returncode == 0),
                required=hook.required,
                output=(process.stdout or "")[:4000],
                error=(process.stderr or "")[:4000],
            )
        except subprocess.TimeoutExpired:
            return HookResult(
                hook_type=hook_type,
                command=hook.command,
                success=False,
                required=hook.required,
                error=f"Timed out after {hook.timeout}s",
            )
        except Exception as exc:
            return HookResult(
                hook_type=hook_type,
                command=hook.command,
                success=False,
                required=hook.required,
                error=str(exc),
            )
