"""Next steps recommendation engine."""

from dataclasses import dataclass, field
from typing import Literal

from .gate_results import GateFailureTodo, GateResultStore
from .git_utils import GitRepo
from .health import HealthChecker, HealthStatus
from .project import Project
from .roadmap import Roadmap, RoadmapItem, RoadmapParser
from .runtime import project_id_for_project
from .sessions import Session, SessionParser
from .todos import TodoItem, TodoParser

RecommendationSource = Literal[
    "roadmap",
    "todo_high_priority",
    "todo_incomplete",
    "uncommitted_changes",
    "failed_gate",
]


@dataclass
class NextStep:
    """A recommended next step for the user."""

    title: str
    description: str
    source: RecommendationSource
    priority_score: float
    prompt_template: str
    rationale: str = ""

    # Optional references
    roadmap_item: RoadmapItem | None = None
    todo_item: TodoItem | None = None
    milestone_name: str | None = None

    @property
    def formatted_prompt(self) -> str:
        """Get the formatted prompt for Claude Code."""
        return self.prompt_template


@dataclass
class RecommendationContext:
    """Context data used for generating recommendations."""

    project: Project
    roadmap: Roadmap | None = None
    last_session: Session | None = None
    git_status: dict | None = None
    pending_todos: list[TodoItem] = field(default_factory=list)
    health_status: HealthStatus | None = None
    gate_failure_todos: list[GateFailureTodo] = field(default_factory=list)


class NextStepRecommender:
    """Engine for recommending next steps based on project state."""

    # Priority weights from spec
    WEIGHTS = {
        "failed_gate": 5.0,
        "todo_high_priority": 4.0,
        "roadmap_next": 3.0,
        "uncommitted_changes": 2.0,
        "oldest_incomplete": 1.0,
    }

    def __init__(self, project: Project):
        self.project = project
        self.session_parser = SessionParser()
        self.todo_parser = TodoParser()

    def gather_context(self) -> RecommendationContext:
        """Gather all context needed for recommendations."""
        context = RecommendationContext(project=self.project)

        # Load roadmap if exists
        try:
            context.roadmap = RoadmapParser.parse(self.project.path)
        except Exception:
            pass

        # Load last session
        if self.project.claude_hash:
            context.last_session = self.session_parser.get_latest_session(
                self.project.claude_hash
            )

        # Get git status
        if GitRepo.is_git_repo(self.project.path):
            try:
                repo = GitRepo(self.project.path)
                status = repo.get_status()
                context.git_status = {
                    "branch": status.branch,
                    "uncommitted_count": status.total_changed_files,
                    "has_changes": status.has_uncommitted_changes,
                }
            except Exception:
                pass

        # Get pending todos
        all_todos = self.todo_parser.get_incomplete_todos()
        if self.project.claude_hash:
            project_sessions = self.session_parser.find_sessions(self.project.claude_hash)
            project_session_ids = {session.session_id for session in project_sessions}
            context.pending_todos = [
                todo
                for todo in all_todos
                if todo.session_id and todo.session_id in project_session_ids
            ]
        else:
            context.pending_todos = []

        # Health checks influence priority.
        try:
            context.health_status = HealthChecker(self.project.path).run_all_checks()
        except Exception:
            pass

        # Gate failures are treated as highest-priority actionable work.
        try:
            project_id = project_id_for_project(self.project)
            context.gate_failure_todos = GateResultStore(project_id).open_failure_todos()
        except Exception:
            pass

        return context

    def generate_recommendations(
        self,
        context: RecommendationContext | None = None,
        max_recommendations: int = 5,
    ) -> list[NextStep]:
        """Generate ranked list of next step recommendations."""
        if context is None:
            context = self.gather_context()

        recommendations: list[NextStep] = []

        # 0. Gate failures (weight: 5x).
        for todo in context.gate_failure_todos[:3]:
            recommendations.append(
                self._create_gate_failure_recommendation(
                    todo,
                    priority_score=self.WEIGHTS["failed_gate"],
                )
            )

        # 0b. Health issues (still high priority but below explicit gate failures).
        if context.health_status:
            for check in context.health_status.bad_checks[:2]:
                recommendations.append(self._create_health_recommendation(check.name, check.message, 4.5))
            for check in context.health_status.warning_checks[:2]:
                recommendations.append(self._create_health_recommendation(check.name, check.message, 3.5))

        # 1. High-priority incomplete todos (weight: 4x)
        high_priority_todos = [
            t for t in context.pending_todos
            if t.priority == "high"
        ]
        for todo in high_priority_todos[:2]:
            recommendations.append(self._create_todo_recommendation(
                todo,
                priority_score=self.WEIGHTS["todo_high_priority"],
            ))

        # 2. Next roadmap item (weight: 3x)
        if context.roadmap:
            next_item = context.roadmap.find_next_incomplete()
            if next_item:
                m_idx, i_idx, item = next_item
                milestone = context.roadmap.milestones[m_idx]
                recommendations.append(self._create_roadmap_recommendation(
                    item,
                    milestone.name,
                    priority_score=self.WEIGHTS["roadmap_next"],
                ))

        # 3. Uncommitted changes (weight: 2x)
        if context.git_status and context.git_status.get("has_changes"):
            recommendations.append(self._create_uncommitted_recommendation(
                context.git_status,
                priority_score=self.WEIGHTS["uncommitted_changes"],
            ))

        # 4. Other incomplete todos (weight: 1x for oldest)
        other_todos = [
            t for t in context.pending_todos
            if t.priority != "high"
        ][:3]
        for idx, todo in enumerate(other_todos):
            # Older todos get slightly higher priority
            score = self.WEIGHTS["oldest_incomplete"] + (0.1 * (len(other_todos) - idx))
            recommendations.append(self._create_todo_recommendation(
                todo,
                priority_score=score,
            ))

        # Sort by priority score descending
        recommendations.sort(key=lambda r: r.priority_score, reverse=True)

        return recommendations[:max_recommendations]

    def _create_health_recommendation(
        self,
        check_name: str,
        finding: str,
        priority_score: float,
    ) -> NextStep:
        prompt = self._build_prompt(
            task=f"Address health issue: {check_name}",
            context_note=f"Issue details: {finding}",
        )
        return NextStep(
            title=f"Fix health issue: {check_name}",
            description=finding,
            source="failed_gate",
            priority_score=priority_score,
            prompt_template=prompt,
            rationale=f"Health check {check_name} currently failing.",
        )

    def _create_gate_failure_recommendation(
        self,
        todo: GateFailureTodo,
        priority_score: float,
    ) -> NextStep:
        location = ""
        if todo.file:
            location = todo.file if todo.line is None else f"{todo.file}:{todo.line}"
        description = todo.description
        if location:
            description = f"{description} ({location})"

        return NextStep(
            title=f"Fix gate failure: {todo.source_gate}",
            description=description,
            source="failed_gate",
            priority_score=priority_score,
            prompt_template=todo.suggested_fix_prompt,
            rationale="Hard-stop/quality gate issue should be resolved before new work.",
        )

    def _create_todo_recommendation(
        self,
        todo: TodoItem,
        priority_score: float,
    ) -> NextStep:
        """Create a recommendation from a todo item."""
        source: RecommendationSource = (
            "todo_high_priority" if todo.priority == "high" else "todo_incomplete"
        )

        prompt = self._build_prompt(
            task=todo.content,
            context_note=f"This was a {todo.priority}-priority todo item.",
        )

        return NextStep(
            title=todo.content,
            description=f"{todo.priority.capitalize()} priority from previous session",
            source=source,
            priority_score=priority_score,
            prompt_template=prompt,
            todo_item=todo,
            rationale=f"{todo.priority.capitalize()} priority carry-over from this project.",
        )

    def _create_roadmap_recommendation(
        self,
        item: RoadmapItem,
        milestone_name: str,
        priority_score: float,
    ) -> NextStep:
        """Create a recommendation from a roadmap item."""
        prompt = self._build_prompt(
            task=item.text,
            context_note=f"This is the next item in milestone: {milestone_name}",
        )

        return NextStep(
            title=item.text,
            description=f"Next item in {milestone_name}",
            source="roadmap",
            priority_score=priority_score,
            prompt_template=prompt,
            roadmap_item=item,
            milestone_name=milestone_name,
            rationale=f"Earliest incomplete roadmap item in {milestone_name}.",
        )

    def _create_uncommitted_recommendation(
        self,
        git_status: dict,
        priority_score: float,
    ) -> NextStep:
        """Create a recommendation for uncommitted changes."""
        count = git_status.get("uncommitted_count", 0)

        prompt = self._build_prompt(
            task=f"Review and commit the {count} uncommitted file(s)",
            context_note="There are uncommitted changes that should be reviewed.",
        )

        return NextStep(
            title=f"Review {count} uncommitted changes",
            description="Uncommitted changes from previous work",
            source="uncommitted_changes",
            priority_score=priority_score,
            prompt_template=prompt,
            rationale="Uncommitted changes increase merge and context risk.",
        )

    def _build_prompt(
        self,
        task: str,
        context_note: str = "",
    ) -> str:
        """Build a prompt template for Claude Code."""
        parts = [
            f"You are working on {self.project.name}.",
            "",
        ]

        if context_note:
            parts.extend([
                "Context:",
                context_note,
                "",
            ])

        parts.extend([
            f"Task: {task}",
            "",
            "Requirements:",
            "- Follow existing code patterns and conventions",
            "- Write tests for new functionality",
            "- Update documentation if adding public APIs",
        ])

        return "\n".join(parts)

    def get_quick_actions(self) -> list[dict]:
        """Get list of quick actions for the UI."""
        actions = []

        # Always available: "What should I work on?"
        actions.append({
            "label": "What should I work on?",
            "action": "recommend",
            "icon": "lightbulb",
        })

        # If git repo with changes
        if GitRepo.is_git_repo(self.project.path):
            actions.append({
                "label": "Review git status",
                "action": "git_status",
                "icon": "git",
            })

        # Run health check
        actions.append({
            "label": "Check project health",
            "action": "health_check",
            "icon": "health",
        })

        return actions
