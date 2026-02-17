"""Tests for file overlap detection and task grouping."""

import subprocess
from pathlib import Path

import pytest

from src.core.task_dependency import (
    DependencyAnalysis,
    ParallelGroup,
    TaskDependencyAnalyzer,
    TaskFileProfile,
)


@pytest.fixture
def git_repo(tmp_path):
    """Create a real git repository with tracked files."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path, capture_output=True,
    )
    # Create some tracked files
    (tmp_path / "src" / "core").mkdir(parents=True)
    (tmp_path / "src" / "components").mkdir(parents=True)
    (tmp_path / "tests").mkdir(parents=True)
    (tmp_path / "src" / "core" / "utils.py").write_text("# utils\n")
    (tmp_path / "src" / "core" / "models.py").write_text("# models\n")
    (tmp_path / "src" / "components" / "Button.tsx").write_text("// button\n")
    (tmp_path / "tests" / "test_utils.py").write_text("# test\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path, capture_output=True,
    )
    return tmp_path


class TestTaskFileProfile:
    """Tests for the TaskFileProfile dataclass."""

    def test_defaults(self):
        profile = TaskFileProfile(task_index=0, task_text="Do something")
        assert profile.predicted_files == []
        assert profile.predicted_dirs == []
        assert profile.confidence == 0.5

    def test_custom_values(self):
        profile = TaskFileProfile(
            task_index=2,
            task_text="Update the API",
            predicted_files=["src/api/server.py"],
            predicted_dirs=["src/api"],
            confidence=0.8,
        )
        assert profile.task_index == 2
        assert len(profile.predicted_files) == 1
        assert profile.confidence == 0.8


class TestDependencyAnalysis:
    """Tests for the DependencyAnalysis dataclass."""

    def test_defaults(self):
        analysis = DependencyAnalysis()
        assert analysis.task_profiles == []
        assert analysis.groups == []
        assert analysis.max_parallel == 3
        assert analysis.analysis_method == "heuristic"
        assert analysis.warnings == []


class TestTaskDependencyAnalyzer:
    """Tests for TaskDependencyAnalyzer."""

    def test_empty_tasks(self):
        """Analyzing empty task list returns empty analysis."""
        analyzer = TaskDependencyAnalyzer()
        result = analyzer.analyze([], max_parallel=3)
        assert result.task_profiles == []
        assert result.groups == []
        assert result.max_parallel == 3

    def test_single_task(self):
        """Single task produces a single group."""
        analyzer = TaskDependencyAnalyzer()
        tasks = [{"text": "Add a new feature to src/core/utils.py"}]
        result = analyzer.analyze(tasks)

        assert len(result.task_profiles) == 1
        assert len(result.groups) == 1
        assert result.groups[0].task_indices == [0]

    def test_non_overlapping_tasks(self):
        """Tasks touching different files get separate groups."""
        analyzer = TaskDependencyAnalyzer()
        tasks = [
            {"text": "Update src/core/utils.py with new helper functions"},
            {"text": "Add styles to src/components/Button.tsx"},
        ]
        result = analyzer.analyze(tasks, max_parallel=3)

        assert len(result.task_profiles) == 2
        # Both should be in the same group (no overlap)
        # since they touch different files
        all_indices = set()
        for g in result.groups:
            all_indices.update(g.task_indices)
        assert all_indices == {0, 1}

    def test_overlapping_tasks_file_level(self):
        """Tasks touching the same file get different groups."""
        analyzer = TaskDependencyAnalyzer()
        tasks = [
            {"text": "Add logging to src/core/utils.py"},
            {"text": "Refactor src/core/utils.py for better naming"},
        ]
        result = analyzer.analyze(tasks, max_parallel=3)

        assert len(result.task_profiles) == 2
        # Both mention src/core/utils.py → they should be in different groups
        profile_0 = result.task_profiles[0]
        profile_1 = result.task_profiles[1]
        assert "src/core/utils.py" in profile_0.predicted_files
        assert "src/core/utils.py" in profile_1.predicted_files

        # They should NOT be in the same group
        for g in result.groups:
            assert not (0 in g.task_indices and 1 in g.task_indices), \
                "Overlapping tasks should not be in the same group"

    def test_file_path_extraction(self):
        """Extracts explicit file paths from task text."""
        analyzer = TaskDependencyAnalyzer()
        tasks = [
            {"text": "Modify `src/core/models.py` and `src/core/utils.py`"},
        ]
        result = analyzer.analyze(tasks)

        profile = result.task_profiles[0]
        assert "src/core/models.py" in profile.predicted_files
        assert "src/core/utils.py" in profile.predicted_files

    def test_keyword_directory_detection(self):
        """Keywords in task text produce predicted directories."""
        analyzer = TaskDependencyAnalyzer()
        tasks = [
            {"text": "Update frontend components for the dashboard"},
        ]
        result = analyzer.analyze(tasks)

        profile = result.task_profiles[0]
        # "frontend" and "component" keywords should produce directory predictions
        assert len(profile.predicted_dirs) > 0

    def test_confidence_with_files(self):
        """Tasks with explicit file paths have higher confidence."""
        analyzer = TaskDependencyAnalyzer()
        tasks = [
            {"text": "Update src/core/utils.py with new helpers"},
            {"text": "Improve the user experience"},
        ]
        result = analyzer.analyze(tasks)

        with_file = result.task_profiles[0]
        without_file = result.task_profiles[1]
        assert with_file.confidence > without_file.confidence

    def test_low_confidence_warning(self):
        """Tasks with very low confidence generate warnings."""
        analyzer = TaskDependencyAnalyzer()
        tasks = [
            {"text": "Do something vague"},
            {"text": "Another vague task"},
        ]
        result = analyzer.analyze(tasks)

        # These tasks have no file references → low confidence
        low = [p for p in result.task_profiles if p.confidence < 0.3]
        if low:
            assert len(result.warnings) > 0
            assert "low file-prediction confidence" in result.warnings[0]

    def test_with_project_path(self, git_repo):
        """Analyzer uses project files when project_path is provided."""
        analyzer = TaskDependencyAnalyzer(project_path=git_repo)
        tasks = [
            {"text": "Update src/core/utils.py"},
        ]
        result = analyzer.analyze(tasks)
        profile = result.task_profiles[0]
        assert "src/core/utils.py" in profile.predicted_files

    def test_many_tasks_grouping(self):
        """Multiple tasks get partitioned into valid groups."""
        analyzer = TaskDependencyAnalyzer()
        tasks = [
            {"text": "Update src/core/utils.py"},
            {"text": "Fix src/core/utils.py bug"},
            {"text": "Add src/components/Header.tsx"},
            {"text": "Style src/components/Footer.tsx"},
            {"text": "Write tests/test_utils.py"},
        ]
        result = analyzer.analyze(tasks, max_parallel=4)

        # All tasks should be assigned to a group
        all_indices = set()
        for g in result.groups:
            all_indices.update(g.task_indices)
        assert all_indices == {0, 1, 2, 3, 4}

        # Tasks 0 and 1 overlap (same file) → must be in different groups
        for g in result.groups:
            assert not (0 in g.task_indices and 1 in g.task_indices)

    def test_prompt_field_also_scanned(self):
        """The analyzer scans both 'text' and 'prompt' fields."""
        analyzer = TaskDependencyAnalyzer()
        tasks = [
            {"text": "Task one", "prompt": "Edit src/core/models.py"},
        ]
        result = analyzer.analyze(tasks)
        profile = result.task_profiles[0]
        assert "src/core/models.py" in profile.predicted_files

    def test_deduplication_of_files(self):
        """Duplicate file references are deduplicated."""
        analyzer = TaskDependencyAnalyzer()
        tasks = [
            {
                "text": "Fix src/core/utils.py",
                "prompt": "Update src/core/utils.py with better error handling",
            },
        ]
        result = analyzer.analyze(tasks)
        profile = result.task_profiles[0]
        count = profile.predicted_files.count("src/core/utils.py")
        assert count == 1


class TestBuildOverlapGraph:
    """Tests for the overlap graph builder."""

    def test_no_overlap(self):
        """Non-overlapping profiles produce empty graph."""
        analyzer = TaskDependencyAnalyzer()
        profiles = [
            TaskFileProfile(task_index=0, task_text="", predicted_files=["a.py"]),
            TaskFileProfile(task_index=1, task_text="", predicted_files=["b.py"]),
        ]
        overlap = analyzer._build_overlap_graph(profiles)
        assert overlap == {}

    def test_file_overlap(self):
        """Profiles sharing a file appear in the graph."""
        analyzer = TaskDependencyAnalyzer()
        profiles = [
            TaskFileProfile(task_index=0, task_text="", predicted_files=["shared.py"]),
            TaskFileProfile(task_index=1, task_text="", predicted_files=["shared.py"]),
        ]
        overlap = analyzer._build_overlap_graph(profiles)
        assert (0, 1) in overlap
        assert "shared.py" in overlap[(0, 1)]

    def test_directory_overlap(self):
        """Profiles sharing a directory (but no file) appear in the graph."""
        analyzer = TaskDependencyAnalyzer()
        profiles = [
            TaskFileProfile(task_index=0, task_text="", predicted_dirs=["src/core"]),
            TaskFileProfile(task_index=1, task_text="", predicted_dirs=["src/core"]),
        ]
        overlap = analyzer._build_overlap_graph(profiles)
        assert (0, 1) in overlap

    def test_file_overlap_takes_precedence(self):
        """If both file and directory overlap, file-level conflicts are listed."""
        analyzer = TaskDependencyAnalyzer()
        profiles = [
            TaskFileProfile(
                task_index=0, task_text="",
                predicted_files=["src/core/utils.py"],
                predicted_dirs=["src/core"],
            ),
            TaskFileProfile(
                task_index=1, task_text="",
                predicted_files=["src/core/utils.py"],
                predicted_dirs=["src/core"],
            ),
        ]
        overlap = analyzer._build_overlap_graph(profiles)
        conflicts = overlap[(0, 1)]
        # Should include file-level conflict, NOT directory (since file is present)
        assert "src/core/utils.py" in conflicts
        dir_entries = [c for c in conflicts if "(directory)" in c]
        assert len(dir_entries) == 0


class TestPartitionIntoGroups:
    """Tests for the greedy graph coloring partitioner."""

    def test_no_tasks(self):
        analyzer = TaskDependencyAnalyzer()
        groups = analyzer._partition_into_groups([], {}, 3)
        assert groups == []

    def test_single_task(self):
        analyzer = TaskDependencyAnalyzer()
        profiles = [TaskFileProfile(task_index=0, task_text="")]
        groups = analyzer._partition_into_groups(profiles, {}, 3)
        assert len(groups) == 1
        assert groups[0].task_indices == [0]

    def test_no_conflicts_single_group(self):
        """All tasks with no overlap end up in the same group."""
        analyzer = TaskDependencyAnalyzer()
        profiles = [
            TaskFileProfile(task_index=0, task_text=""),
            TaskFileProfile(task_index=1, task_text=""),
            TaskFileProfile(task_index=2, task_text=""),
        ]
        groups = analyzer._partition_into_groups(profiles, {}, 3)
        assert len(groups) == 1
        assert sorted(groups[0].task_indices) == [0, 1, 2]

    def test_full_conflict_separate_groups(self):
        """All tasks conflicting with each other → each in its own group."""
        analyzer = TaskDependencyAnalyzer()
        profiles = [
            TaskFileProfile(task_index=0, task_text=""),
            TaskFileProfile(task_index=1, task_text=""),
            TaskFileProfile(task_index=2, task_text=""),
        ]
        overlap = {
            (0, 1): ["shared.py"],
            (0, 2): ["shared.py"],
            (1, 2): ["shared.py"],
        }
        groups = analyzer._partition_into_groups(profiles, overlap, 3)
        assert len(groups) == 3
        for g in groups:
            assert len(g.task_indices) == 1

    def test_partial_conflict(self):
        """Tasks 0-1 conflict but not 0-2 or 1-2."""
        analyzer = TaskDependencyAnalyzer()
        profiles = [
            TaskFileProfile(task_index=0, task_text=""),
            TaskFileProfile(task_index=1, task_text=""),
            TaskFileProfile(task_index=2, task_text=""),
        ]
        overlap = {(0, 1): ["shared.py"]}
        groups = analyzer._partition_into_groups(profiles, overlap, 3)

        # 0 and 1 cannot be together, but 2 can be with either
        for g in groups:
            assert not (0 in g.task_indices and 1 in g.task_indices)

    def test_group_reason_text(self):
        """Groups have appropriate reason strings."""
        analyzer = TaskDependencyAnalyzer()
        profiles = [
            TaskFileProfile(task_index=0, task_text=""),
            TaskFileProfile(task_index=1, task_text=""),
        ]
        overlap = {(0, 1): ["shared.py"]}
        groups = analyzer._partition_into_groups(profiles, overlap, 3)
        for g in groups:
            assert g.reason != ""


class TestGetProjectFiles:
    """Tests for project file discovery."""

    def test_no_project_path(self):
        """Without project_path, returns empty set."""
        analyzer = TaskDependencyAnalyzer(project_path=None)
        files = analyzer._get_project_files()
        assert files == set()

    def test_with_git_repo(self, git_repo):
        """With a git repo, returns tracked files."""
        analyzer = TaskDependencyAnalyzer(project_path=git_repo)
        files = analyzer._get_project_files()
        assert "src/core/utils.py" in files
        assert "src/core/models.py" in files

    def test_caches_result(self, git_repo):
        """Second call returns cached result."""
        analyzer = TaskDependencyAnalyzer(project_path=git_repo)
        files1 = analyzer._get_project_files()
        files2 = analyzer._get_project_files()
        assert files1 is files2

    def test_non_git_directory(self, tmp_path):
        """Non-git directory returns empty set."""
        analyzer = TaskDependencyAnalyzer(project_path=tmp_path)
        files = analyzer._get_project_files()
        assert files == set()
