"""Project detection and registration."""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .plan_models import PlanSource
from .plan_scanner import ProjectPlanScanner


@dataclass
class Project:
    """Represents a Claude Code project."""

    path: Path
    name: str
    claude_hash: str | None = None
    last_session_id: str | None = None
    last_opened: datetime | None = None

    @classmethod
    def from_path(cls, path: Path) -> "Project":
        """Create a Project from a directory path."""
        path = path.resolve()
        name = path.name
        claude_hash = cls._compute_claude_hash(path)
        return cls(path=path, name=name, claude_hash=claude_hash)

    @staticmethod
    def _compute_claude_hash(path: Path) -> str | None:
        """Compute the hash Claude Code uses for project identification.

        Claude Code uses various hashing strategies. We try to auto-detect the correct
        hash by checking ~/.claude/projects/ for matching directories.
        """
        path = path.resolve()
        path_str = str(path)
        claude_projects_dir = Path.home() / ".claude" / "projects"

        if not claude_projects_dir.exists():
            # No Claude Code data exists, return computed hash
            return hashlib.md5(path_str.encode()).hexdigest()[:16]

        # Try to find existing project directory that matches this path
        # Claude Code stores project path info in session logs or settings
        for project_dir in claude_projects_dir.iterdir():
            if not project_dir.is_dir():
                continue

            # Check if any JSONL files exist and try to match project path
            jsonl_files = list(project_dir.glob("*.jsonl"))
            if jsonl_files:
                # Check the settings.local.json if it exists
                settings_file = project_dir / "settings.local.json"
                if settings_file.exists():
                    try:
                        settings_data = json.loads(settings_file.read_text())
                        stored_path = settings_data.get("projectPath", "")
                        if stored_path and Path(stored_path).resolve() == path:
                            return project_dir.name
                    except (json.JSONDecodeError, OSError):
                        pass

                # Check first few lines of JSONL for project path hints
                try:
                    with open(jsonl_files[0]) as f:
                        for i, line in enumerate(f):
                            if i > 20:  # Only check first 20 lines
                                break
                            try:
                                entry = json.loads(line)
                                # Claude Code often stores cwd in entries
                                cwd = entry.get("cwd") or entry.get("workingDirectory", "")
                                if cwd and Path(cwd).resolve() == path:
                                    return project_dir.name
                            except json.JSONDecodeError:
                                continue
                except OSError:
                    pass

        # Fall back to MD5-based hash computation
        return hashlib.md5(path_str.encode()).hexdigest()[:16]

    @property
    def claude_project_dir(self) -> Path | None:
        """Get the Claude Code project directory for this project."""
        if not self.claude_hash:
            return None
        claude_dir = Path.home() / ".claude" / "projects" / self.claude_hash
        return claude_dir if claude_dir.exists() else None

    def has_roadmap(self) -> bool:
        """Check if the project has a roadmap file."""
        # Check consolidated location first (single source of truth)
        consolidated = self.path / ".claude" / "planning" / "ROADMAP.md"
        if consolidated.exists():
            return True

        try:
            plan = ProjectPlanScanner(self.path).scan()
            return bool(plan.items)
        except Exception:
            roadmap_locations = [
                self.path / "ROADMAP.md",
                self.path / "docs" / "ROADMAP.md",
                self.path / "TODO.md",
            ]
            return any(loc.exists() for loc in roadmap_locations)

    def get_roadmap_path(self) -> Path | None:
        """Get the path to the project's roadmap file.

        Prioritizes consolidated roadmap in .claude/planning/ as single source of truth.
        """
        # Check consolidated location first (single source of truth)
        consolidated = self.path / ".claude" / "planning" / "ROADMAP.md"
        if consolidated.exists():
            return consolidated

        try:
            plan = ProjectPlanScanner(self.path).scan()
            for source in (
                PlanSource.ROADMAP_FILE,
                PlanSource.PHASE_FILE,
                PlanSource.PLANNING_DIR,
                PlanSource.EMBEDDED_SECTION,
                PlanSource.HEURISTIC,
            ):
                paths = plan.sources_found.get(source, [])
                if paths:
                    return paths[0]
        except Exception:
            pass

        roadmap_locations = [
            self.path / "ROADMAP.md",
            self.path / "docs" / "ROADMAP.md",
            self.path / "TODO.md",
        ]
        for loc in roadmap_locations:
            if loc.exists():
                return loc
        return None

    def has_claude_md(self) -> bool:
        """Check if the project has a CLAUDE.md file."""
        return (self.path / "CLAUDE.md").exists()

    def to_dict(self) -> dict:
        """Serialize project to dictionary."""
        return {
            "path": str(self.path),
            "name": self.name,
            "claude_hash": self.claude_hash,
            "last_session_id": self.last_session_id,
            "last_opened": self.last_opened.isoformat() if self.last_opened else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        """Deserialize project from dictionary."""
        last_opened = data.get("last_opened")
        if last_opened and isinstance(last_opened, str):
            last_opened = datetime.fromisoformat(last_opened)
        return cls(
            path=Path(data["path"]),
            name=data["name"],
            claude_hash=data.get("claude_hash"),
            last_session_id=data.get("last_session_id"),
            last_opened=last_opened,
        )


@dataclass
class ProjectRegistry:
    """Registry of known Claude Code projects."""

    projects: dict[str, Project] = field(default_factory=dict)
    config_path: Path = field(default_factory=lambda: Path.home() / ".claudetini" / "projects.json")

    def add_project(self, project: Project) -> None:
        """Add a project to the registry."""
        key = str(project.path)
        self.projects[key] = project
        self._save()

    def remove_project(self, path: Path) -> None:
        """Remove a project from the registry."""
        key = str(path.resolve())
        if key in self.projects:
            del self.projects[key]
            self._save()

    def get_project(self, path: Path) -> Project | None:
        """Get a project by path."""
        key = str(path.resolve())
        return self.projects.get(key)

    def list_projects(self) -> list[Project]:
        """List all registered projects."""
        return list(self.projects.values())

    def update_last_opened(self, path: Path) -> None:
        """Update the last_opened timestamp for a project."""
        key = str(path.resolve())
        if key in self.projects:
            self.projects[key].last_opened = datetime.now()
            self._save()

    def _save(self) -> None:
        """Save registry to disk."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {key: proj.to_dict() for key, proj in self.projects.items()}
        self.config_path.write_text(json.dumps(data, indent=2))

    def load(self) -> None:
        """Load registry from disk."""
        if self.config_path.exists():
            data = json.loads(self.config_path.read_text())
            self.projects = {key: Project.from_dict(proj) for key, proj in data.items()}

    @classmethod
    def load_or_create(cls) -> "ProjectRegistry":
        """Load existing registry or create a new one."""
        registry = cls()
        registry.load()
        return registry
