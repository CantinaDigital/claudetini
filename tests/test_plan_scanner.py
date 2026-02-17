"""Tests for Phase 2 unified project plan scanning."""

import hashlib
import json

from src.core.plan_models import ConflictResolution, PlanItemStatus, PlanSource
from src.core.plan_scanner import ProjectPlanScanner
from src.core.roadmap import RoadmapParser


def test_scan_explicit_file(temp_dir):
    roadmap = temp_dir / "ROADMAP.md"
    roadmap.write_text(
        "# Plan\n\n"
        "## Milestone One\n"
        "- [x] Build scanner\n"
        "- [ ] Add tests\n"
    )

    scanner = ProjectPlanScanner(temp_dir)
    plan = scanner.scan()

    assert len(plan.items) == 2
    assert plan.progress_percent == 50.0
    assert PlanSource.ROADMAP_FILE in plan.sources_found


def test_scan_embedded_sections(temp_dir):
    readme = temp_dir / "README.md"
    readme.write_text(
        "# App\n\n"
        "## What's Next\n"
        "- [ ] Add OAuth\n"
        "- [x] Set up linting\n"
    )

    plan = ProjectPlanScanner(temp_dir).scan()
    contents = {item.content: item for item in plan.items}

    assert "Add OAuth" in contents
    assert contents["Add OAuth"].source == PlanSource.EMBEDDED_SECTION


def test_conflict_resolution_roadmap_wins(temp_dir):
    project_path = temp_dir
    (project_path / "ROADMAP.md").write_text(
        "# Plan\n\n"
        "## Milestone 1\n"
        "- [x] Implement OAuth\n"
    )

    claude_dir = temp_dir / ".claude"
    project_hash = hashlib.md5(str(project_path.resolve()).encode("utf-8")).hexdigest()[:16]
    project_claude_dir = claude_dir / "projects" / project_hash
    project_claude_dir.mkdir(parents=True)
    (project_claude_dir / "session-123.jsonl").write_text("{}\n")

    todos_dir = claude_dir / "todos"
    todos_dir.mkdir(parents=True)
    (todos_dir / "session-123-1.json").write_text(
        json.dumps(
            [
                {
                    "content": "Implement OAuth",
                    "status": "in_progress",
                    "priority": "high",
                }
            ]
        )
    )

    plan = ProjectPlanScanner(project_path, claude_dir=claude_dir).scan()
    oauth_item = next(item for item in plan.items if item.content == "Implement OAuth")

    assert plan.has_conflicts is True
    assert oauth_item.status == PlanItemStatus.DONE
    assert oauth_item.conflicts[0].resolution == ConflictResolution.ROADMAP_WINS


def test_roadmap_parser_backward_compat_uses_unified_scanner(temp_dir):
    planning_dir = temp_dir / ".planning"
    planning_dir.mkdir(parents=True)
    (planning_dir / "phase1.md").write_text(
        "# Phase 1\n\n"
        "## Milestone A\n"
        "- [ ] Ship onboarding\n"
    )

    roadmap = RoadmapParser.parse(temp_dir)

    assert roadmap is not None
    assert len(roadmap.milestones) == 1
    assert roadmap.milestones[0].items[0].text == "Ship onboarding"
    assert roadmap.milestones[0].items[0].completed is False
