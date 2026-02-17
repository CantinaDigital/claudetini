"""Shared runtime identity and storage helpers."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import uuid
from pathlib import Path


def _is_writable_dir(path: Path) -> bool:
    """Return whether path exists and accepts create/write/delete operations."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / f".cp-write-probe-{uuid.uuid4().hex}"
        probe.write_text("ok")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _resolve_runtime_home() -> Path:
    """Resolve canonical runtime home with writable fallback for restricted envs."""
    # Check new env var first, then legacy
    configured = os.environ.get("CLAUDETINI_HOME")
    if configured:
        path = Path(configured).expanduser()
        if _is_writable_dir(path):
            return path

    preferred = Path.home() / ".claudetini"
    if _is_writable_dir(preferred):
        return preferred

    fallback = Path(tempfile.gettempdir()) / "claudetini-runtime"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


RUNTIME_HOME = _resolve_runtime_home()
RUNTIME_ROOT = RUNTIME_HOME / "projects"
# Migrate from old .claudetini location
LEGACY_RUNTIME_ROOTS: tuple[Path, ...] = (
    Path.home() / ".claudetini" / "projects",
)


def project_id_for_path(project_path: Path) -> str:
    """Return a stable canonical project id from the absolute path."""
    return hashlib.md5(str(project_path.resolve()).encode("utf-8")).hexdigest()[:16]


def project_id_for_project(project: object) -> str:
    """Return canonical project id for a Project-like object."""
    path = getattr(project, "path", None)
    if isinstance(path, Path):
        return project_id_for_path(path)
    if isinstance(path, str):
        return project_id_for_path(Path(path))
    raise ValueError("Project object must expose a Path `path` attribute")


def project_runtime_dir(project_id: str, base_dir: Path | None = None) -> Path:
    """Return (and create) the canonical runtime directory for a project id."""
    root = base_dir or RUNTIME_ROOT
    target = root / project_id
    target.mkdir(parents=True, exist_ok=True)
    if base_dir is None:
        _migrate_legacy_runtime(project_id=project_id, target=target)
    return target


def project_runtime_dir_for_path(project_path: Path, base_dir: Path | None = None) -> Path:
    """Return runtime directory for a project path."""
    return project_runtime_dir(project_id_for_path(project_path), base_dir=base_dir)


def _migrate_legacy_runtime(project_id: str, target: Path) -> None:
    """Best-effort forward migration from legacy per-project runtime roots."""
    for legacy_root in LEGACY_RUNTIME_ROOTS:
        legacy_dir = legacy_root / project_id
        if not legacy_dir.exists() or legacy_dir.resolve() == target.resolve():
            continue
        _merge_tree(legacy_dir, target)


def _merge_tree(source: Path, target: Path) -> None:
    """Copy source tree into target without overwriting existing target files."""
    target.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        rel = path.relative_to(source)
        dest = target / rel
        if path.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            continue
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
