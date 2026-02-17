"""Git pre-push hook management for quality gate enforcement."""

from __future__ import annotations

import os
from pathlib import Path

from ..core.runtime import project_runtime_dir

START_MARKER = "# >>> claudetini pre-push >>>"
END_MARKER = "# <<< claudetini pre-push <<<"
# Legacy markers for backwards compatibility during migration
LEGACY_START_MARKER = "# >>> claudetini pre-push >>>"
LEGACY_END_MARKER = "# <<< claudetini pre-push <<<"


class GitPrePushHookManager:
    """Install/remove an opt-in pre-push hook that checks hard-stop gates."""

    def __init__(self, project_path: Path, project_id: str, base_dir: Path | None = None):
        self.project_path = project_path.resolve()
        self.project_dir = project_runtime_dir(project_id, base_dir=base_dir)
        self.git_hooks_dir = self.project_path / ".git" / "hooks"
        self.pre_push_hook = self.git_hooks_dir / "pre-push"
        self.status_file = self.project_dir / "last-gate-status.json"

    def install(self) -> tuple[bool, str]:
        if not self.git_hooks_dir.exists():
            return False, "Not a git repository (missing .git/hooks)."

        existing = ""
        if self.pre_push_hook.exists():
            existing = self.pre_push_hook.read_text()
            if START_MARKER in existing and END_MARKER in existing:
                return True, "Pre-push hook already installed."

        managed_block = self._managed_block()

        if not existing:
            script = "#!/bin/bash\nset -e\n\n" + managed_block + "\n"
        else:
            script = existing.rstrip() + "\n\n" + managed_block + "\n"

        self.pre_push_hook.write_text(script)
        os.chmod(self.pre_push_hook, 0o755)
        return True, "Installed quality gate pre-push hook."

    def remove(self) -> tuple[bool, str]:
        if not self.pre_push_hook.exists():
            return True, "No pre-push hook to remove."

        content = self.pre_push_hook.read_text()
        if START_MARKER not in content or END_MARKER not in content:
            return False, "Pre-push hook exists but is not managed by Claudetini."

        start = content.find(START_MARKER)
        end = content.find(END_MARKER)
        if start == -1 or end == -1:
            return False, "Managed markers not found."

        end += len(END_MARKER)
        updated = (content[:start] + content[end:]).strip()

        if not updated:
            self.pre_push_hook.unlink(missing_ok=True)
            return True, "Removed managed pre-push hook."

        self.pre_push_hook.write_text(updated + "\n")
        return True, "Removed Claudetini managed section from pre-push hook."

    def is_installed(self) -> bool:
        if not self.pre_push_hook.exists():
            return False
        content = self.pre_push_hook.read_text()
        return START_MARKER in content and END_MARKER in content

    def _managed_block(self) -> str:
        status = self.status_file
        return "\n".join(
            [
                START_MARKER,
                f"GATE_STATUS={status!s}",
                "export GATE_STATUS",
                "REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)",
                "cd \"$REPO_ROOT\"",
                "if [ ! -f \"$GATE_STATUS\" ]; then",
                "  echo \"No gate results found. Run quality gates from Claudetini dashboard.\"",
                "  echo \"Bypass: git push --no-verify\"",
                "  exit 1",
                "fi",
                "if ! python3 - <<'PY'",
                "import hashlib, json, os, subprocess, sys",
                "path = os.environ.get('GATE_STATUS')",
                "with open(path) as f:",
                "    data = json.load(f)",
                "def run(cmd):",
                "    proc = subprocess.run(cmd, capture_output=True, text=True)",
                "    if proc.returncode != 0:",
                "        return None",
                "    return proc.stdout.strip()",
                "head = run(['git', 'rev-parse', 'HEAD']) or 'UNBORN'",
                "index_state = run(['git', 'diff', '--cached', '--name-status']) or ''",
                "worktree_state = run(['git', 'status', '--porcelain=v1']) or ''",
                "index_fp = hashlib.sha1(index_state.encode('utf-8')).hexdigest()",
                "worktree_fp = hashlib.sha1(worktree_state.encode('utf-8')).hexdigest()",
                "if data.get('head_sha') != head or data.get('index_fingerprint') != index_fp or data.get('working_tree_fingerprint') != worktree_fp:",
                "    print('Gate results are stale for current commit/index. Run quality gates from Claudetini dashboard.')",
                "    sys.exit(1)",
                "failed = [g for g in data.get('gates', []) if g.get('hard_stop') and g.get('status') == 'fail']",
                "if failed:",
                "    print('Push blocked by quality gates:')",
                "    for gate in failed:",
                "        print(f\"  - {gate.get('name')}: {gate.get('summary')}\")",
                "    sys.exit(1)",
                "print('Quality gates fresh and passing.')",
                "PY",
                "then",
                "  echo \"Bypass: git push --no-verify\"",
                "  exit 1",
                "fi",
                END_MARKER,
            ]
        )
