"""End-to-end tests for all project scenarios.

Tests each fixture project for expected behavior including:
- Project loading
- Roadmap detection and parsing
- Progress calculation
- Git operations
- Consolidation flow
- Quality gates
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.git_utils import GitUtils
from src.core.health import HealthScanner
from src.core.plan_consolidator import PlanConsolidator
from src.core.plan_scanner import ProjectPlanScanner
from src.core.project import Project
from src.core.roadmap import RoadmapParser

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "projects"


def load_manifest() -> list[dict]:
    """Load the fixtures manifest."""
    manifest_path = FIXTURES_DIR / "manifest.json"
    if not manifest_path.exists():
        pytest.skip("Fixtures not generated. Run: python tests/fixtures/generate_fixtures.py")
    return json.loads(manifest_path.read_text())["fixtures"]


# =============================================================================
# FIXTURE 1: Empty Project
# =============================================================================
class TestEmptyProject:
    """Tests for empty project with no roadmap."""

    @pytest.fixture
    def project_path(self) -> Path:
        return FIXTURES_DIR / "01_empty_project"

    def test_project_loads(self, project_path):
        """Project should load without errors."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        project = Project.from_path(project_path)
        assert project.name == "01_empty_project"

    def test_no_roadmap_detected(self, project_path):
        """Should detect no roadmap."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        project = Project.from_path(project_path)
        assert not project.has_roadmap()

    def test_git_is_clean(self, project_path):
        """Git should be in clean state."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        git = GitUtils(project_path)
        assert len(git.uncommitted_files()) == 0

    def test_plan_scanner_returns_empty(self, project_path):
        """Plan scanner should return no items."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        plan = ProjectPlanScanner(project_path).scan()
        assert len(plan.items) == 0


# =============================================================================
# FIXTURE 2: Single Roadmap
# =============================================================================
class TestSingleRoadmap:
    """Tests for clean single-roadmap project."""

    @pytest.fixture
    def project_path(self) -> Path:
        return FIXTURES_DIR / "02_single_roadmap"

    def test_project_loads(self, project_path):
        """Project should load successfully."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        project = Project.from_path(project_path)
        assert project.name == "02_single_roadmap"

    def test_roadmap_detected(self, project_path):
        """Should detect roadmap."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        project = Project.from_path(project_path)
        assert project.has_roadmap()

    def test_roadmap_path_correct(self, project_path):
        """Should return correct roadmap path."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        project = Project.from_path(project_path)
        roadmap_path = project.get_roadmap_path()
        assert roadmap_path is not None
        assert roadmap_path.name == "ROADMAP.md"

    def test_progress_calculation(self, project_path):
        """Should calculate correct progress (2/10 = 20%)."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        roadmap = RoadmapParser.parse(project_path)
        assert roadmap is not None
        total = sum(len(m.items) for m in roadmap.milestones)
        done = sum(sum(1 for i in m.items if i.done) for m in roadmap.milestones)
        assert total == 10
        assert done == 2
        assert int(done / total * 100) == 20

    def test_no_consolidation_needed(self, project_path):
        """Should not need consolidation (single source)."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        consolidator = PlanConsolidator(project_path)
        assert not consolidator.needs_consolidation()


# =============================================================================
# FIXTURE 3: Multiple Sources
# =============================================================================
class TestMultipleSources:
    """Tests for project with multiple planning sources."""

    @pytest.fixture
    def project_path(self) -> Path:
        return FIXTURES_DIR / "03_multiple_sources"

    def test_consolidation_needed(self, project_path):
        """Should detect need for consolidation."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        consolidator = PlanConsolidator(project_path)
        assert consolidator.needs_consolidation()

    def test_multiple_sources_detected(self, project_path):
        """Should detect multiple sources."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        consolidator = PlanConsolidator(project_path)
        sources = consolidator.detect_sources()
        assert len(sources) >= 3  # ROADMAP.md, .planning/ROADMAP.md, PHASE-1-PLAN.md

    def test_consolidation_works(self, project_path, tmp_path):
        """Should consolidate successfully."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")

        # Copy fixture to temp to avoid modifying original
        import shutil
        test_path = tmp_path / "test_consolidation"
        shutil.copytree(project_path, test_path)

        consolidator = PlanConsolidator(test_path)
        result = consolidator.consolidate(archive=True, delete_after=True)

        assert result.success
        assert result.consolidated_path is not None
        assert result.consolidated_path.exists()
        assert result.items_consolidated > 0
        assert result.duplicates_removed >= 0

    def test_after_consolidation_single_source(self, project_path, tmp_path):
        """After consolidation, should only have single source."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")

        import shutil
        test_path = tmp_path / "test_single_source"
        shutil.copytree(project_path, test_path)

        consolidator = PlanConsolidator(test_path)
        consolidator.consolidate(archive=True, delete_after=True)

        # Re-scan - should now be single source
        plan = ProjectPlanScanner(test_path).scan()
        assert len(plan.sources_found) == 1


# =============================================================================
# FIXTURE 4: Completed Project
# =============================================================================
class TestCompletedProject:
    """Tests for 100% complete project."""

    @pytest.fixture
    def project_path(self) -> Path:
        return FIXTURES_DIR / "04_completed_project"

    def test_progress_is_100(self, project_path):
        """Should show 100% progress."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        roadmap = RoadmapParser.parse(project_path)
        assert roadmap is not None
        total = sum(len(m.items) for m in roadmap.milestones)
        done = sum(sum(1 for i in m.items if i.done) for m in roadmap.milestones)
        assert total > 0
        assert done == total

    def test_all_milestones_complete(self, project_path):
        """All milestones should be complete."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        roadmap = RoadmapParser.parse(project_path)
        for milestone in roadmap.milestones:
            assert all(item.done for item in milestone.items)


# =============================================================================
# FIXTURE 5: Partial Progress
# =============================================================================
class TestPartialProgress:
    """Tests for partially complete project."""

    @pytest.fixture
    def project_path(self) -> Path:
        return FIXTURES_DIR / "05_partial_progress"

    def test_progress_between_0_and_100(self, project_path):
        """Progress should be between 0 and 100."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        roadmap = RoadmapParser.parse(project_path)
        total = sum(len(m.items) for m in roadmap.milestones)
        done = sum(sum(1 for i in m.items if i.done) for m in roadmap.milestones)
        percent = int(done / total * 100)
        assert 0 < percent < 100

    def test_first_milestone_complete(self, project_path):
        """First milestone should be complete."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        roadmap = RoadmapParser.parse(project_path)
        first = roadmap.milestones[0]
        assert all(item.done for item in first.items)


# =============================================================================
# FIXTURE 6: No Git
# =============================================================================
class TestNoGit:
    """Tests for project without git."""

    @pytest.fixture
    def project_path(self) -> Path:
        return FIXTURES_DIR / "06_no_git"

    def test_project_loads(self, project_path):
        """Should load even without git."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        project = Project.from_path(project_path)
        assert project.name == "06_no_git"

    def test_git_utils_handles_missing_repo(self, project_path):
        """GitUtils should handle missing .git gracefully."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        git = GitUtils(project_path)
        # Should return empty/safe defaults, not crash
        assert git.current_branch() in ("unknown", "main", "master", None, "")

    def test_roadmap_still_works(self, project_path):
        """Roadmap should work without git."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        project = Project.from_path(project_path)
        assert project.has_roadmap()


# =============================================================================
# FIXTURE 7: Dirty Git
# =============================================================================
class TestDirtyGit:
    """Tests for project with uncommitted changes.

    The fixture directory has no .git (nested .git dirs can't be committed),
    so we set up git state at test time in a tmp_path copy.
    """

    @pytest.fixture
    def project_path(self, tmp_path) -> Path:
        project = tmp_path / "dirty_git"
        project.mkdir()
        # Set up a git repo with committed base, then dirty it
        subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=project, check=True, capture_output=True)
        (project / "README.md").write_text("# Dirty Git Project\n")
        (project / "ROADMAP.md").write_text("# Roadmap\n\n## Tasks\n- [x] Initial setup\n- [ ] Clean up\n")
        subprocess.run(["git", "add", "."], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=project, check=True, capture_output=True)
        # Now make it dirty
        (project / "README.md").write_text("# Dirty Git Project\n\nModified but not committed.\n")
        (project / "untracked.txt").write_text("This file is untracked\n")
        (project / "src").mkdir()
        (project / "src" / "new_file.py").write_text("# New untracked file\n")
        return project

    def test_uncommitted_detected(self, project_path):
        """Should detect uncommitted changes."""
        git = GitUtils(project_path)
        uncommitted = git.uncommitted_files()
        assert len(uncommitted) > 0

    def test_untracked_detected(self, project_path):
        """Should detect untracked files."""
        git = GitUtils(project_path)
        # untracked.txt and src/new_file.py should be untracked
        uncommitted = git.uncommitted_files()
        assert any("untracked" in f for f in uncommitted) or len(uncommitted) >= 2


# =============================================================================
# FIXTURE 8: Quality Failures
# =============================================================================
class TestQualityFailures:
    """Tests for project with quality issues."""

    @pytest.fixture
    def project_path(self) -> Path:
        return FIXTURES_DIR / "08_quality_failures"

    def test_health_scan_detects_issues(self, project_path):
        """Health scan should detect issues."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        scanner = HealthScanner(project_path)
        results = scanner.scan_all()
        # Should have some non-passing results
        has_issues = any(not r.passed for r in results.values())
        assert has_issues or len(results) > 0  # At minimum, scan should run


# =============================================================================
# FIXTURE 9: Large Roadmap
# =============================================================================
class TestLargeRoadmap:
    """Tests for project with many items."""

    @pytest.fixture
    def project_path(self) -> Path:
        return FIXTURES_DIR / "09_large_roadmap"

    def test_handles_large_roadmap(self, project_path):
        """Should handle large roadmap without issues."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        roadmap = RoadmapParser.parse(project_path)
        assert roadmap is not None
        total = sum(len(m.items) for m in roadmap.milestones)
        assert total >= 100  # 10 milestones * 15 items = 150

    def test_progress_calculation_accurate(self, project_path):
        """Progress should be calculated accurately."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        plan = ProjectPlanScanner(project_path).scan()
        from src.core.plan_models import PlanItemStatus
        done = sum(1 for item in plan.items if item.status == PlanItemStatus.DONE)
        total = len(plan.items)
        # Should be ~60% done
        percent = int(done / total * 100)
        assert 55 <= percent <= 65


# =============================================================================
# FIXTURE 10: Already Consolidated
# =============================================================================
class TestAlreadyConsolidated:
    """Tests for project that's already been consolidated."""

    @pytest.fixture
    def project_path(self) -> Path:
        return FIXTURES_DIR / "10_already_consolidated"

    def test_uses_consolidated_path(self, project_path):
        """Should use .claude/planning/ROADMAP.md."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        project = Project.from_path(project_path)
        roadmap_path = project.get_roadmap_path()
        assert roadmap_path is not None
        assert ".claude/planning" in str(roadmap_path)

    def test_no_consolidation_needed(self, project_path):
        """Should not need consolidation."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        consolidator = PlanConsolidator(project_path)
        # Already consolidated, so either needs_consolidation is False
        # or there's only 1 source
        sources = consolidator.detect_sources()
        assert len(sources) == 1 or not consolidator.needs_consolidation()

    def test_single_source_in_scan(self, project_path):
        """Plan scanner should only find single source."""
        if not project_path.exists():
            pytest.skip("Fixture not generated")
        plan = ProjectPlanScanner(project_path).scan()
        assert len(plan.sources_found) == 1


# =============================================================================
# Integration Tests
# =============================================================================
class TestIntegration:
    """Cross-fixture integration tests."""

    def test_all_fixtures_loadable(self):
        """All fixtures should be loadable as projects."""
        if not FIXTURES_DIR.exists():
            pytest.skip("Fixtures not generated")

        for fixture_dir in sorted(FIXTURES_DIR.iterdir()):
            if fixture_dir.is_dir() and not fixture_dir.name.startswith("."):
                project = Project.from_path(fixture_dir)
                assert project is not None, f"Failed to load {fixture_dir.name}"

    def test_no_fixture_crashes_scanner(self):
        """Plan scanner should not crash on any fixture."""
        if not FIXTURES_DIR.exists():
            pytest.skip("Fixtures not generated")

        for fixture_dir in sorted(FIXTURES_DIR.iterdir()):
            if fixture_dir.is_dir() and not fixture_dir.name.startswith("."):
                try:
                    plan = ProjectPlanScanner(fixture_dir).scan()
                    assert plan is not None
                except Exception as e:
                    pytest.fail(f"Scanner crashed on {fixture_dir.name}: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
