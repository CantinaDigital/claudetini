"""Tests for the next steps recommendation engine."""

import pytest

from src.core.health import HealthCheck, HealthLevel, HealthStatus
from src.core.project import Project
from src.core.recommender import (
    NextStep,
    NextStepRecommender,
    RecommendationContext,
)
from src.core.roadmap import Roadmap
from src.core.todos import TodoItem


class TestNextStepRecommender:
    """Tests for NextStepRecommender class."""

    @pytest.fixture
    def project(self, sample_project):
        """Create a Project from sample project."""
        return Project.from_path(sample_project)

    @pytest.fixture
    def recommender(self, project):
        """Create a recommender for testing."""
        return NextStepRecommender(project)

    def test_gather_context(self, recommender, sample_project):
        """Test context gathering."""
        context = recommender.gather_context()

        assert context.project is not None
        assert context.roadmap is not None  # sample_project has ROADMAP.md

    def test_generate_recommendations_basic(self, recommender):
        """Test basic recommendation generation."""
        recommendations = recommender.generate_recommendations()

        # Should have at least one recommendation (from roadmap)
        assert len(recommendations) >= 1

    def test_recommendations_sorted_by_priority(self, recommender):
        """Test that recommendations are sorted by priority."""
        recommendations = recommender.generate_recommendations()

        if len(recommendations) > 1:
            for i in range(len(recommendations) - 1):
                assert recommendations[i].priority_score >= recommendations[i + 1].priority_score

    def test_max_recommendations(self, recommender):
        """Test max recommendations limit."""
        recommendations = recommender.generate_recommendations(max_recommendations=2)

        assert len(recommendations) <= 2

    def test_roadmap_recommendation(self, recommender):
        """Test that roadmap items generate recommendations."""
        recommendations = recommender.generate_recommendations()

        roadmap_recs = [r for r in recommendations if r.source == "roadmap"]
        assert len(roadmap_recs) >= 1

    def test_recommendation_has_prompt(self, recommender):
        """Test that recommendations include prompts."""
        recommendations = recommender.generate_recommendations()

        for rec in recommendations:
            assert rec.prompt_template
            assert len(rec.prompt_template) > 0

    def test_get_quick_actions(self, recommender):
        """Test quick actions list."""
        actions = recommender.get_quick_actions()

        assert len(actions) >= 1
        assert any(a["action"] == "recommend" for a in actions)

    def test_health_issues_affect_recommendations(self, recommender, project):
        """Health failures should surface as high-priority recommendations."""
        health = HealthStatus(
            checks=[
                HealthCheck(
                    category="Testing",
                    name="Test Suite",
                    level=HealthLevel.BAD,
                    message="No tests found",
                )
            ]
        )
        context = RecommendationContext(project=project, health_status=health)
        recs = recommender.generate_recommendations(context=context)
        assert recs
        assert recs[0].source == "failed_gate"
        assert "health issue" in recs[0].title.lower()


class TestNextStep:
    """Tests for NextStep class."""

    def test_formatted_prompt(self):
        """Test formatted prompt property."""
        step = NextStep(
            title="Test Task",
            description="Test description",
            source="roadmap",
            priority_score=3.0,
            prompt_template="Do the thing",
        )

        assert step.formatted_prompt == "Do the thing"


class TestRecommendationContext:
    """Tests for RecommendationContext class."""

    def test_context_creation(self, sample_project):
        """Test context creation."""
        project = Project.from_path(sample_project)
        context = RecommendationContext(project=project)

        assert context.project == project
        assert context.roadmap is None  # Not loaded yet
        assert context.pending_todos == []

    def test_context_with_roadmap(self, sample_project):
        """Test context with loaded roadmap."""
        project = Project.from_path(sample_project)
        roadmap_path = sample_project / "ROADMAP.md"
        roadmap = Roadmap.parse(roadmap_path)

        context = RecommendationContext(
            project=project,
            roadmap=roadmap,
        )

        assert context.roadmap is not None
        assert len(context.roadmap.milestones) > 0

    def test_context_with_todos(self, sample_project):
        """Test context with pending todos."""
        project = Project.from_path(sample_project)
        todos = [
            TodoItem(content="Task 1", status="pending", priority="high"),
            TodoItem(content="Task 2", status="pending", priority="medium"),
        ]

        context = RecommendationContext(
            project=project,
            pending_todos=todos,
        )

        assert len(context.pending_todos) == 2
