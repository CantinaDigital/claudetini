"""File overlap detection and task grouping for parallel execution.

Analyzes roadmap task descriptions to predict which files each task
will touch, then partitions tasks into parallel groups that can safely
run concurrently (no overlapping files).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TaskFileProfile:
    """Predicted file footprint for a single task."""

    task_index: int
    task_text: str
    predicted_files: list[str] = field(default_factory=list)
    predicted_dirs: list[str] = field(default_factory=list)
    confidence: float = 0.5


@dataclass
class ParallelGroup:
    """A group of tasks that can run concurrently."""

    group_id: int
    task_indices: list[int] = field(default_factory=list)
    reason: str = ""


@dataclass
class DependencyAnalysis:
    """Result of analyzing tasks for parallel execution."""

    task_profiles: list[TaskFileProfile] = field(default_factory=list)
    groups: list[ParallelGroup] = field(default_factory=list)
    max_parallel: int = 3
    analysis_method: str = "heuristic"
    warnings: list[str] = field(default_factory=list)


# Common file path patterns in task descriptions
_FILE_PATH_RE = re.compile(
    r"""
    (?:^|[\s`"'(])                  # word boundary or quote/backtick
    (
        (?:src|lib|app|tests?|pkg|cmd|internal|api|core|components?|utils?|hooks?|stores?|managers?|routes?|services?)
        (?:/[\w.-]+)+                # at least one more path segment
        (?:\.\w{1,10})?              # optional file extension
    )
    """,
    re.VERBOSE | re.MULTILINE,
)

# Module/component name patterns
_COMPONENT_RE = re.compile(
    r"""
    (?:component|module|class|function|file|create|add|update|modify|implement|refactor)
    \s+
    [`"]?([\w./]+)[`"]?
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Common directory keywords mapped to likely paths
_DIR_KEYWORDS: dict[str, list[str]] = {
    "frontend": ["src/components", "src/stores", "src/api", "app/src"],
    "backend": ["src/core", "src/agents", "python-sidecar"],
    "api": ["src/api", "sidecar/api", "api/routes"],
    "test": ["tests"],
    "config": ["src/config", "."],
    "database": ["src/db", "src/models"],
    "style": ["src/styles"],
    "type": ["src/types"],
    "route": ["sidecar/api/routes", "src/api/routes"],
    "component": ["src/components"],
    "store": ["src/stores"],
    "manager": ["src/managers"],
    "hook": ["src/hooks"],
    "util": ["src/utils", "src/core"],
    "gate": ["src/agents", "sidecar/api/routes"],
    "dispatch": ["src/agents", "sidecar/api/routes"],
    "git": ["src/core"],
    "roadmap": ["src/core", "src/components/roadmap"],
    "worktree": ["src/core"],
    "parallel": ["src/agents", "src/core"],
}


class TaskDependencyAnalyzer:
    """Analyze task descriptions to detect file overlap and partition into groups."""

    def __init__(self, project_path: Path | None = None) -> None:
        self.project_path = project_path
        self._project_files: set[str] | None = None

    def analyze(
        self,
        tasks: list[dict],
        max_parallel: int = 3,
    ) -> DependencyAnalysis:
        """Analyze tasks and partition into parallel execution groups.

        Args:
            tasks: List of dicts with at least ``text`` key.
            max_parallel: Maximum concurrent agents.

        Returns:
            DependencyAnalysis with groups and profiles.
        """
        if not tasks:
            return DependencyAnalysis(max_parallel=max_parallel)

        profiles = self._heuristic_analysis(tasks)
        overlap = self._build_overlap_graph(profiles)
        groups = self._partition_into_groups(profiles, overlap, max_parallel)

        warnings: list[str] = []
        low_confidence = [p for p in profiles if p.confidence < 0.3]
        if low_confidence:
            warnings.append(
                f"{len(low_confidence)} task(s) have low file-prediction confidence. "
                "They may conflict unexpectedly."
            )

        return DependencyAnalysis(
            task_profiles=profiles,
            groups=groups,
            max_parallel=max_parallel,
            analysis_method="heuristic",
            warnings=warnings,
        )

    def _heuristic_analysis(self, tasks: list[dict]) -> list[TaskFileProfile]:
        """Extract file path references from task text using heuristics."""
        project_files = self._get_project_files()
        profiles: list[TaskFileProfile] = []

        for idx, task in enumerate(tasks):
            text = task.get("text", "") + " " + task.get("prompt", "")
            predicted_files: list[str] = []
            predicted_dirs: set[str] = set()

            # Extract explicit file paths
            for match in _FILE_PATH_RE.finditer(text):
                path = match.group(1)
                if project_files and path in project_files:
                    predicted_files.append(path)
                else:
                    predicted_files.append(path)
                    # Also add the directory
                    parent = str(Path(path).parent)
                    if parent != ".":
                        predicted_dirs.add(parent)

            # Extract component/module names
            for match in _COMPONENT_RE.finditer(text):
                name = match.group(1)
                # Check if it looks like a path
                if "/" in name:
                    predicted_files.append(name)
                    parent = str(Path(name).parent)
                    if parent != ".":
                        predicted_dirs.add(parent)

            # Extract directory hints from keywords
            text_lower = text.lower()
            for keyword, dirs in _DIR_KEYWORDS.items():
                if keyword in text_lower:
                    predicted_dirs.update(dirs)

            # Deduplicate
            seen: set[str] = set()
            unique_files: list[str] = []
            for f in predicted_files:
                if f not in seen:
                    seen.add(f)
                    unique_files.append(f)

            # Confidence based on how specific the predictions are
            if unique_files:
                confidence = min(0.9, 0.5 + 0.1 * len(unique_files))
            elif predicted_dirs:
                confidence = 0.4
            else:
                confidence = 0.2

            profiles.append(
                TaskFileProfile(
                    task_index=idx,
                    task_text=task.get("text", ""),
                    predicted_files=unique_files,
                    predicted_dirs=sorted(predicted_dirs),
                    confidence=confidence,
                )
            )

        return profiles

    def _build_overlap_graph(
        self, profiles: list[TaskFileProfile]
    ) -> dict[tuple[int, int], list[str]]:
        """Build a graph of which task pairs have overlapping file predictions.

        Returns:
            Dict mapping (task_i, task_j) to list of overlapping files/dirs.
        """
        overlap: dict[tuple[int, int], list[str]] = {}

        for i, pi in enumerate(profiles):
            files_i = set(pi.predicted_files)
            dirs_i = set(pi.predicted_dirs)

            for j in range(i + 1, len(profiles)):
                pj = profiles[j]
                files_j = set(pj.predicted_files)
                dirs_j = set(pj.predicted_dirs)

                # File-level overlap
                common_files = files_i & files_j

                # Directory-level overlap (weaker signal)
                common_dirs = dirs_i & dirs_j

                conflicts: list[str] = sorted(common_files)

                # Also flag directory overlap if significant
                if common_dirs and not common_files:
                    # Only flag dirs if there's no file-level conflict
                    conflicts.extend(f"{d}/ (directory)" for d in sorted(common_dirs))

                if conflicts:
                    overlap[(i, j)] = conflicts

        return overlap

    def _partition_into_groups(
        self,
        profiles: list[TaskFileProfile],
        overlap: dict[tuple[int, int], list[str]],
        max_parallel: int,
    ) -> list[ParallelGroup]:
        """Partition tasks into groups using greedy graph coloring.

        Tasks with file overlap cannot be in the same group.
        """
        n = len(profiles)
        if n == 0:
            return []

        # Build adjacency list (tasks that conflict)
        adj: dict[int, set[int]] = {i: set() for i in range(n)}
        for (i, j) in overlap:
            adj[i].add(j)
            adj[j].add(i)

        # Greedy coloring
        colors: dict[int, int] = {}
        for task_idx in range(n):
            # Find colors used by neighbors
            neighbor_colors = {colors[nb] for nb in adj[task_idx] if nb in colors}
            # Assign first available color
            color = 0
            while color in neighbor_colors:
                color += 1
            colors[task_idx] = color

        # Group by color
        color_groups: dict[int, list[int]] = {}
        for task_idx, color in sorted(colors.items()):
            color_groups.setdefault(color, []).append(task_idx)

        groups: list[ParallelGroup] = []
        for group_id, (_color, indices) in enumerate(sorted(color_groups.items())):
            # Build reason
            if len(indices) == 1:
                reason = "Single task (has file overlap with other groups)"
            else:
                reason = f"{len(indices)} tasks with no predicted file overlap"

            groups.append(
                ParallelGroup(
                    group_id=group_id,
                    task_indices=indices,
                    reason=reason,
                )
            )

        return groups

    def _get_project_files(self) -> set[str]:
        """Get the set of tracked files in the project."""
        if self._project_files is not None:
            return self._project_files

        if self.project_path is None:
            self._project_files = set()
            return self._project_files

        try:
            result = subprocess.run(
                ["git", "ls-files"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                self._project_files = {
                    f.strip() for f in result.stdout.split("\n") if f.strip()
                }
            else:
                self._project_files = set()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self._project_files = set()

        return self._project_files


