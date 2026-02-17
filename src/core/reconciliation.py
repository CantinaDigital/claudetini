"""Smart roadmap reconciliation for automatic progress tracking.

This module provides automatic detection of completed roadmap items by comparing
project state snapshots (git commits, file changes, LOC deltas) against roadmap
item descriptions.

Supports both heuristic-based matching and AI-powered semantic analysis via Claude Code.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from .git_utils import GitRepo
from .roadmap import Roadmap


@dataclass(frozen=True)
class ProjectStateSnapshot:
    """Immutable snapshot of project state at a point in time."""

    snapshot_id: str
    timestamp: datetime
    project_id: str

    # Git state
    git_head_sha: str | None
    git_branch: str | None
    git_uncommitted_count: int

    # File tree state
    file_tree_fingerprint: str  # SHA1 of (path, size, mtime) tuples
    total_files: int
    total_loc: int  # Estimated via sampling

    # Dependency state
    dependency_fingerprint: str  # SHA1 of package files

    # Roadmap state
    roadmap_fingerprint: str
    completed_items: list[str]
    total_items: int

    # Session context
    last_session_id: str | None
    work_source: str  # "claude" | "manual" | "unknown"


@dataclass(frozen=True)
class FileChange:
    """Represents a change to a single file."""

    path: str
    change_type: Literal["added", "modified", "deleted"]
    loc_delta: int  # Positive = added, negative = deleted
    is_substantial: bool  # True if loc_delta >= 50


@dataclass(frozen=True)
class RoadmapSuggestion:
    """Suggested roadmap item completion with evidence."""

    item_text: str
    milestone_name: str
    confidence: float  # 0.0 to 1.0
    reasoning: list[str]  # Human-readable evidence
    matched_files: list[str]
    matched_commits: list[str]  # SHAs
    session_id: str | None = None  # Attribution to Claude session


@dataclass(frozen=True)
class ReconciliationReport:
    """Full analysis report comparing two snapshots."""

    report_id: str
    timestamp: datetime
    old_snapshot_id: str
    new_snapshot_id: str

    commits_added: int
    files_changed: list[FileChange]
    dependencies_changed: bool

    suggestions: list[RoadmapSuggestion]
    already_completed_externally: list[str]  # Manually marked


class SnapshotStore:
    """Manages persistence of project snapshots."""

    def __init__(self, storage_dir: Path):
        """Initialize snapshot store.

        Args:
            storage_dir: Directory to store snapshots (typically ~/.claudetini/projects/{id}/snapshots/)
        """
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def save_snapshot(self, snapshot: ProjectStateSnapshot) -> None:
        """Save a snapshot to disk."""
        snapshot_file = self.storage_dir / f"snapshot-{snapshot.snapshot_id}.json"
        data = {
            "snapshot_id": snapshot.snapshot_id,
            "timestamp": snapshot.timestamp.isoformat(),
            "project_id": snapshot.project_id,
            "git_head_sha": snapshot.git_head_sha,
            "git_branch": snapshot.git_branch,
            "git_uncommitted_count": snapshot.git_uncommitted_count,
            "file_tree_fingerprint": snapshot.file_tree_fingerprint,
            "total_files": snapshot.total_files,
            "total_loc": snapshot.total_loc,
            "dependency_fingerprint": snapshot.dependency_fingerprint,
            "roadmap_fingerprint": snapshot.roadmap_fingerprint,
            "completed_items": snapshot.completed_items,
            "total_items": snapshot.total_items,
            "last_session_id": snapshot.last_session_id,
            "work_source": snapshot.work_source,
        }
        snapshot_file.write_text(json.dumps(data, indent=2))

        # Cleanup old snapshots (keep max 10)
        self._cleanup_old_snapshots()

    def load_snapshot(self, snapshot_id: str) -> ProjectStateSnapshot | None:
        """Load a snapshot from disk."""
        snapshot_file = self.storage_dir / f"snapshot-{snapshot_id}.json"
        if not snapshot_file.exists():
            return None

        data = json.loads(snapshot_file.read_text())
        return ProjectStateSnapshot(
            snapshot_id=data["snapshot_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            project_id=data["project_id"],
            git_head_sha=data["git_head_sha"],
            git_branch=data["git_branch"],
            git_uncommitted_count=data["git_uncommitted_count"],
            file_tree_fingerprint=data["file_tree_fingerprint"],
            total_files=data["total_files"],
            total_loc=data["total_loc"],
            dependency_fingerprint=data["dependency_fingerprint"],
            roadmap_fingerprint=data["roadmap_fingerprint"],
            completed_items=data["completed_items"],
            total_items=data["total_items"],
            last_session_id=data.get("last_session_id"),
            work_source=data.get("work_source", "unknown"),
        )

    def get_latest_snapshot(self) -> ProjectStateSnapshot | None:
        """Get the most recent snapshot."""
        snapshots = self.list_snapshots()
        return snapshots[0] if snapshots else None

    def list_snapshots(self) -> list[ProjectStateSnapshot]:
        """List all snapshots, sorted by timestamp descending."""
        snapshots = []
        for snapshot_file in self.storage_dir.glob("snapshot-*.json"):
            try:
                data = json.loads(snapshot_file.read_text())
                snapshot = ProjectStateSnapshot(
                    snapshot_id=data["snapshot_id"],
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    project_id=data["project_id"],
                    git_head_sha=data["git_head_sha"],
                    git_branch=data["git_branch"],
                    git_uncommitted_count=data["git_uncommitted_count"],
                    file_tree_fingerprint=data["file_tree_fingerprint"],
                    total_files=data["total_files"],
                    total_loc=data["total_loc"],
                    dependency_fingerprint=data["dependency_fingerprint"],
                    roadmap_fingerprint=data["roadmap_fingerprint"],
                    completed_items=data["completed_items"],
                    total_items=data["total_items"],
                    last_session_id=data.get("last_session_id"),
                    work_source=data.get("work_source", "unknown"),
                )
                snapshots.append(snapshot)
            except (json.JSONDecodeError, KeyError):
                # Skip corrupted snapshots
                continue

        # Sort by timestamp descending
        snapshots.sort(key=lambda s: s.timestamp, reverse=True)
        return snapshots

    def _cleanup_old_snapshots(self) -> None:
        """Keep only the 10 most recent snapshots."""
        snapshots = self.list_snapshots()
        if len(snapshots) > 10:
            for old_snapshot in snapshots[10:]:
                snapshot_file = self.storage_dir / f"snapshot-{old_snapshot.snapshot_id}.json"
                if snapshot_file.exists():
                    snapshot_file.unlink()


class ReconciliationStore:
    """Manages persistence of reconciliation reports and dismissals."""

    def __init__(self, storage_dir: Path):
        """Initialize reconciliation store.

        Args:
            storage_dir: Directory to store reports (typically ~/.claudetini/projects/{id}/)
        """
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir = self.storage_dir / "reconciliation-reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.audit_log = self.storage_dir / "reconciliation-audit.jsonl"
        self.dismissals_file = self.storage_dir / "reconciliation-dismissals.json"

    def save_report(self, report: ReconciliationReport) -> None:
        """Save a reconciliation report to disk."""
        report_file = self.reports_dir / f"reconcile-{report.report_id}.json"
        data = {
            "report_id": report.report_id,
            "timestamp": report.timestamp.isoformat(),
            "old_snapshot_id": report.old_snapshot_id,
            "new_snapshot_id": report.new_snapshot_id,
            "commits_added": report.commits_added,
            "files_changed": [
                {
                    "path": fc.path,
                    "change_type": fc.change_type,
                    "loc_delta": fc.loc_delta,
                    "is_substantial": fc.is_substantial,
                }
                for fc in report.files_changed
            ],
            "dependencies_changed": report.dependencies_changed,
            "suggestions": [
                {
                    "item_text": s.item_text,
                    "milestone_name": s.milestone_name,
                    "confidence": s.confidence,
                    "reasoning": s.reasoning,
                    "matched_files": s.matched_files,
                    "matched_commits": s.matched_commits,
                    "session_id": s.session_id,
                }
                for s in report.suggestions
            ],
            "already_completed_externally": report.already_completed_externally,
        }
        report_file.write_text(json.dumps(data, indent=2))

    def load_report(self, report_id: str) -> ReconciliationReport | None:
        """Load a reconciliation report from disk."""
        report_file = self.reports_dir / f"reconcile-{report_id}.json"
        if not report_file.exists():
            return None

        data = json.loads(report_file.read_text())
        return ReconciliationReport(
            report_id=data["report_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            old_snapshot_id=data["old_snapshot_id"],
            new_snapshot_id=data["new_snapshot_id"],
            commits_added=data["commits_added"],
            files_changed=[
                FileChange(
                    path=fc["path"],
                    change_type=fc["change_type"],
                    loc_delta=fc["loc_delta"],
                    is_substantial=fc["is_substantial"],
                )
                for fc in data["files_changed"]
            ],
            dependencies_changed=data["dependencies_changed"],
            suggestions=[
                RoadmapSuggestion(
                    item_text=s["item_text"],
                    milestone_name=s["milestone_name"],
                    confidence=s["confidence"],
                    reasoning=s["reasoning"],
                    matched_files=s["matched_files"],
                    matched_commits=s["matched_commits"],
                    session_id=s.get("session_id"),
                )
                for s in data["suggestions"]
            ],
            already_completed_externally=data.get("already_completed_externally", []),
        )

    def log_action(self, action: str, details: dict) -> None:
        """Append an action to the audit log."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details,
        }
        with open(self.audit_log, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def save_dismissals(self, dismissals: dict[str, list[str]]) -> None:
        """Save dismissed suggestions.

        Args:
            dismissals: Map of report_id -> list of dismissed item texts
        """
        self.dismissals_file.write_text(json.dumps(dismissals, indent=2))

    def load_dismissals(self) -> dict[str, list[str]]:
        """Load dismissed suggestions."""
        if not self.dismissals_file.exists():
            return {}
        return json.loads(self.dismissals_file.read_text())

    def add_dismissal(self, report_id: str, item_text: str) -> None:
        """Add a dismissed suggestion."""
        dismissals = self.load_dismissals()
        if report_id not in dismissals:
            dismissals[report_id] = []
        if item_text not in dismissals[report_id]:
            dismissals[report_id].append(item_text)
        self.save_dismissals(dismissals)


class ReconciliationEngine:
    """Orchestrates roadmap reconciliation workflow."""

    def __init__(self, project_path: Path, project_id: str):
        """Initialize reconciliation engine.

        Args:
            project_path: Path to the project root
            project_id: Unique project identifier (can be path or hash)
        """
        self.project_path = project_path
        self.project_id = project_id

        # Set up storage - hash the project_id if it's an absolute path
        if project_id.startswith("/"):
            # Hash absolute paths to avoid path joining issues
            safe_id = hashlib.sha1(project_id.encode()).hexdigest()[:16]
        else:
            safe_id = project_id

        storage_root = Path.home() / ".claudetini" / "projects" / safe_id
        self.snapshot_store = SnapshotStore(storage_root / "snapshots")
        self.reconciliation_store = ReconciliationStore(storage_root)

        # Initialize git if available
        self.git_repo = GitRepo(project_path) if GitRepo.is_git_repo(project_path) else None

    def create_snapshot(self, trigger: str = "manual") -> ProjectStateSnapshot:
        """Create a new snapshot of current project state.

        Args:
            trigger: What triggered this snapshot ("manual", "reconciliation", "app_launch")

        Returns:
            The created snapshot
        """
        # Generate snapshot ID
        snapshot_id = datetime.now().strftime("%Y%m%d%H%M%S")

        # Git state
        git_head_sha = None
        git_branch = None
        git_uncommitted_count = 0
        if self.git_repo:
            git_branch = self.git_repo.get_current_branch()
            try:
                output, code = self.git_repo._run_git("rev-parse", "HEAD")
                if code == 0:
                    git_head_sha = output.strip()
            except Exception:
                pass

            status = self.git_repo.get_status()
            git_uncommitted_count = status.total_changed_files + len(status.untracked_files)

        # File tree fingerprint
        file_tree_fingerprint, total_files, total_loc = self._compute_file_tree_fingerprint()

        # Dependency fingerprint
        dependency_fingerprint = self._compute_dependency_fingerprint()

        # Roadmap state
        roadmap_fingerprint, completed_items, total_items = self._compute_roadmap_state()

        # Session context (TODO: detect from Claude session data)
        last_session_id = None
        work_source = "unknown"

        snapshot = ProjectStateSnapshot(
            snapshot_id=snapshot_id,
            timestamp=datetime.now(),
            project_id=self.project_id,
            git_head_sha=git_head_sha,
            git_branch=git_branch,
            git_uncommitted_count=git_uncommitted_count,
            file_tree_fingerprint=file_tree_fingerprint,
            total_files=total_files,
            total_loc=total_loc,
            dependency_fingerprint=dependency_fingerprint,
            roadmap_fingerprint=roadmap_fingerprint,
            completed_items=completed_items,
            total_items=total_items,
            last_session_id=last_session_id,
            work_source=work_source,
        )

        self.snapshot_store.save_snapshot(snapshot)
        self.reconciliation_store.log_action("snapshot_created", {"snapshot_id": snapshot_id, "trigger": trigger})

        return snapshot

    def quick_check_for_changes(self) -> dict:
        """Fast check (<100ms) for changes since last snapshot.

        Returns:
            Dict with {has_changes, commits_count, files_modified, uncommitted_count}
        """
        latest_snapshot = self.snapshot_store.get_latest_snapshot()

        has_changes = False
        commits_count = 0
        uncommitted_count = 0

        if self.git_repo:
            # Check uncommitted files (always check current state)
            status = self.git_repo.get_status()
            uncommitted_count = status.total_changed_files + len(status.untracked_files)

            if not latest_snapshot:
                # First time - no snapshot to compare against
                # But we should still detect if there are current uncommitted changes
                if uncommitted_count > 0:
                    has_changes = True

                return {
                    "has_changes": has_changes,
                    "commits_count": 0,
                    "files_modified": uncommitted_count,
                    "uncommitted_count": uncommitted_count,
                }

            # Check git HEAD for new commits
            try:
                output, code = self.git_repo._run_git("rev-parse", "HEAD")
                current_head = output.strip() if code == 0 else None
                if current_head != latest_snapshot.git_head_sha:
                    has_changes = True
                    # Count commits since last snapshot
                    if latest_snapshot.git_head_sha and current_head:
                        commits = self.git_repo.get_commits_since(latest_snapshot.timestamp)
                        commits_count = len(commits)
            except Exception:
                pass

            # Check if there are ANY uncommitted files (indicates ongoing work)
            # OR if the uncommitted count changed since last snapshot
            if uncommitted_count > 0 or uncommitted_count != latest_snapshot.git_uncommitted_count:
                has_changes = True

        return {
            "has_changes": has_changes,
            "commits_count": commits_count,
            "files_modified": uncommitted_count,
            "uncommitted_count": uncommitted_count,
        }

    def detect_changes(
        self, old_snapshot: ProjectStateSnapshot, new_snapshot: ProjectStateSnapshot
    ) -> tuple[list[FileChange], list[str]]:
        """Detect file changes and commits between two snapshots.

        Returns:
            Tuple of (file_changes, commit_shas)
        """
        file_changes = []
        commit_shas = []

        if not self.git_repo:
            return file_changes, commit_shas

        # Get commits between snapshots (if git HEAD changed)
        if old_snapshot.git_head_sha and new_snapshot.git_head_sha:
            if old_snapshot.git_head_sha != new_snapshot.git_head_sha:
                # Git HEAD changed - there are new commits
                commits = self.git_repo.get_commits_since(old_snapshot.timestamp)
                commit_shas = [c.sha for c in commits]

                # Get file changes using git diff between commits
                try:
                    output, code = self.git_repo._run_git(
                        "diff", "--numstat", old_snapshot.git_head_sha, new_snapshot.git_head_sha
                    )
                    if code == 0 and output:
                        for line in output.strip().split("\n"):
                            if not line:
                                continue
                            parts = line.split("\t")
                            if len(parts) >= 3:
                                added_str, removed_str, filepath = parts[0], parts[1], parts[2]

                                # Handle binary files (- indicates binary)
                                if added_str == "-" or removed_str == "-":
                                    continue

                                added = int(added_str)
                                removed = int(removed_str)
                                loc_delta = added - removed

                                # Determine change type
                                if added > 0 and removed == 0:
                                    change_type = "added"
                                elif added == 0 and removed > 0:
                                    change_type = "deleted"
                                else:
                                    change_type = "modified"

                                file_changes.append(
                                    FileChange(
                                        path=filepath,
                                        change_type=change_type,
                                        loc_delta=loc_delta,
                                        is_substantial=abs(loc_delta) >= 50,
                                    )
                                )
                except Exception:
                    pass

        # ALSO check for uncommitted file changes (files modified but not committed)
        # This catches the case where git HEAD hasn't changed but files are being edited
        if new_snapshot.git_uncommitted_count > 0:
            try:
                # Get uncommitted changes using git diff (working directory vs HEAD)
                output, code = self.git_repo._run_git("diff", "--numstat", "HEAD")
                if code == 0 and output:
                    for line in output.strip().split("\n"):
                        if not line:
                            continue
                        parts = line.split("\t")
                        if len(parts) >= 3:
                            added_str, removed_str, filepath = parts[0], parts[1], parts[2]

                            # Skip binary files
                            if added_str == "-" or removed_str == "-":
                                continue

                            # Skip if this file was already detected from commits
                            if any(fc.path == filepath for fc in file_changes):
                                continue

                            added = int(added_str)
                            removed = int(removed_str)
                            loc_delta = added - removed

                            # Determine change type
                            if added > 0 and removed == 0:
                                change_type = "added"
                            elif added == 0 and removed > 0:
                                change_type = "deleted"
                            else:
                                change_type = "modified"

                            file_changes.append(
                                FileChange(
                                    path=filepath,
                                    change_type=change_type,
                                    loc_delta=loc_delta,
                                    is_substantial=abs(loc_delta) >= 50,
                                )
                            )
            except Exception:
                pass

        return file_changes, commit_shas

    def generate_suggestions(
        self, roadmap: Roadmap, file_changes: list[FileChange], commit_shas: list[str]
    ) -> list[RoadmapSuggestion]:
        """Generate roadmap completion suggestions based on changes.

        Args:
            roadmap: Current roadmap
            file_changes: List of file changes
            commit_shas: List of commit SHAs

        Returns:
            List of suggestions with confidence scores
        """
        suggestions = []

        # Get commit messages and timestamps for matching
        commit_messages = []
        commit_timestamps = {}
        if self.git_repo:
            for sha in commit_shas:
                try:
                    output, code = self.git_repo._run_git("log", "-1", "--format=%s|%aI", sha)
                    if code == 0 and output:
                        parts = output.strip().split("|", 1)
                        if len(parts) == 2:
                            message, timestamp_str = parts
                            commit_messages.append((sha, message))
                            try:
                                from datetime import datetime
                                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                                commit_timestamps[sha] = timestamp.replace(tzinfo=None)
                            except Exception:
                                pass
                except Exception:
                    pass

        # Iterate through incomplete roadmap items
        for milestone in roadmap.milestones:
            for item in milestone.items:
                if item.completed:
                    continue

                # Match this item against changes
                confidence, reasoning, matched_files, matched_commits = self._match_item_to_changes(
                    item.text, milestone.name, file_changes, commit_messages
                )

                if confidence >= 0.30:  # Minimum 30% confidence threshold
                    # Try to find session attribution from matched commits
                    session_id = self._find_session_for_commits(matched_commits, commit_timestamps)

                    suggestions.append(
                        RoadmapSuggestion(
                            item_text=item.text,
                            milestone_name=milestone.name,
                            confidence=confidence,
                            reasoning=reasoning,
                            matched_files=matched_files,
                            matched_commits=matched_commits,
                            session_id=session_id,
                        )
                    )

        # Sort by confidence descending
        suggestions.sort(key=lambda s: s.confidence, reverse=True)

        return suggestions

    def detect_external_completions(
        self, old_snapshot: ProjectStateSnapshot, new_snapshot: ProjectStateSnapshot
    ) -> list[str]:
        """Detect items that were completed externally (manual edits).

        Returns:
            List of item texts that were marked complete externally
        """
        old_completed = set(old_snapshot.completed_items)
        new_completed = set(new_snapshot.completed_items)
        return list(new_completed - old_completed)

    def apply_suggestions(self, roadmap_path: Path, accepted_items: list[str]) -> int:
        """Apply accepted suggestions to the roadmap file.

        Args:
            roadmap_path: Path to roadmap file
            accepted_items: List of item texts to mark complete

        Returns:
            Number of items successfully marked complete
        """
        roadmap = Roadmap.parse(roadmap_path)
        completed_count = 0

        for item_text in accepted_items:
            for milestone in roadmap.milestones:
                for item in milestone.items:
                    if item.text == item_text and not item.completed:
                        item.completed = True
                        completed_count += 1
                        break

        # Save roadmap
        roadmap.save()

        # Log action
        self.reconciliation_store.log_action(
            "suggestions_applied", {"accepted_items": accepted_items, "completed_count": completed_count}
        )

        return completed_count

    def _compute_file_tree_fingerprint(self) -> tuple[str, int, int]:
        """Compute fingerprint of file tree.

        Returns:
            Tuple of (fingerprint, total_files, estimated_loc)
        """
        # Use git ls-files for tracked files (fast)
        file_entries = []
        total_files = 0

        if self.git_repo:
            try:
                output, code = self.git_repo._run_git("ls-files")
                if code == 0 and output:
                    files = [f for f in output.split("\n") if f]
                    total_files = len(files)

                    # Sample files for fingerprint (limit to 1000 for performance)
                    sampled_files = files[:1000]
                    for filepath in sampled_files:
                        full_path = self.project_path / filepath
                        if full_path.exists():
                            stat = full_path.stat()
                            file_entries.append(f"{filepath}:{stat.st_size}:{stat.st_mtime}")
            except Exception:
                pass

        # Compute SHA1 fingerprint
        fingerprint_data = "\n".join(sorted(file_entries))
        fingerprint = hashlib.sha1(fingerprint_data.encode()).hexdigest()

        # Estimate LOC (sample 50 code files)
        estimated_loc = self._estimate_total_loc()

        return fingerprint, total_files, estimated_loc

    def _estimate_total_loc(self) -> int:
        """Estimate total lines of code by sampling."""
        if not self.git_repo:
            return 0

        try:
            # Get list of code files (exclude common non-code extensions)
            output, code = self.git_repo._run_git("ls-files")
            if code != 0 or not output:
                return 0

            code_files = []
            non_code_exts = {
                ".md",
                ".txt",
                ".json",
                ".yml",
                ".yaml",
                ".lock",
                ".ico",
                ".png",
                ".jpg",
                ".svg",
                ".gif",
            }
            for filepath in output.split("\n"):
                if not filepath:
                    continue
                ext = Path(filepath).suffix.lower()
                if ext not in non_code_exts:
                    code_files.append(filepath)

            if not code_files:
                return 0

            # Sample up to 50 files
            sample_size = min(50, len(code_files))
            sample_files = code_files[:sample_size]

            total_sample_lines = 0
            for filepath in sample_files:
                full_path = self.project_path / filepath
                if full_path.exists() and full_path.is_file():
                    try:
                        with open(full_path, errors="ignore") as f:
                            total_sample_lines += sum(1 for _ in f)
                    except Exception:
                        pass

            # Extrapolate to total
            if sample_size > 0:
                avg_lines_per_file = total_sample_lines / sample_size
                estimated_total = int(avg_lines_per_file * len(code_files))
                return estimated_total

            return 0
        except Exception:
            return 0

    def _compute_dependency_fingerprint(self) -> str:
        """Compute fingerprint of dependency files."""
        dependency_files = [
            "package.json",
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "requirements.txt",
            "Pipfile",
            "Pipfile.lock",
            "poetry.lock",
            "Cargo.toml",
            "Cargo.lock",
            "go.mod",
            "go.sum",
        ]

        hashes = []
        for dep_file in dependency_files:
            dep_path = self.project_path / dep_file
            if dep_path.exists():
                content = dep_path.read_text(errors="ignore")
                file_hash = hashlib.sha1(content.encode()).hexdigest()
                hashes.append(f"{dep_file}:{file_hash}")

        combined = "\n".join(sorted(hashes))
        return hashlib.sha1(combined.encode()).hexdigest()

    def _compute_roadmap_state(self) -> tuple[str, list[str], int]:
        """Compute roadmap state fingerprint.

        Returns:
            Tuple of (fingerprint, completed_items, total_items)
        """
        from .project import Project

        project = Project.from_path(self.project_path)
        roadmap_path = project.get_roadmap_path()

        if not roadmap_path or not roadmap_path.exists():
            return "no-roadmap", [], 0

        try:
            roadmap = Roadmap.parse(roadmap_path)
            content = roadmap_path.read_text()
            fingerprint = hashlib.sha1(content.encode()).hexdigest()

            completed_items = []
            for milestone in roadmap.milestones:
                for item in milestone.items:
                    if item.completed:
                        completed_items.append(item.text)

            return fingerprint, completed_items, roadmap.total_items
        except Exception:
            return "error", [], 0

    def _match_item_to_changes(
        self, item_text: str, milestone_name: str, file_changes: list[FileChange], commit_messages: list[tuple[str, str]]
    ) -> tuple[float, list[str], list[str], list[str]]:
        """Match a roadmap item to file changes and commits.

        Returns:
            Tuple of (confidence, reasoning, matched_files, matched_commits)
        """
        confidence = 0.0
        reasoning = []
        matched_files = []
        matched_commits = []

        # Extract keywords from item text
        keywords = self._extract_keywords(item_text)

        # Match against file changes
        file_confidence = 0.0
        for file_change in file_changes:
            filepath_lower = file_change.path.lower()
            filename = Path(file_change.path).stem.lower()

            # Check for keyword matches in path
            for keyword in keywords:
                if keyword in filepath_lower or keyword in filename:
                    matched_files.append(file_change.path)
                    file_confidence += 0.15
                    if file_change.is_substantial:
                        file_confidence += 0.10
                        reasoning.append(
                            f"Substantial changes ({abs(file_change.loc_delta)} LOC) to {file_change.path}"
                        )
                    else:
                        reasoning.append(f"Modified {file_change.path}")
                    break
        confidence += min(file_confidence, 0.40)  # Cap file contribution

        # Match against commit messages
        for commit_sha, commit_message in commit_messages:
            commit_message_lower = commit_message.lower()
            item_text_lower = item_text.lower()

            # Check for keyword matches
            match_count = sum(1 for keyword in keywords if keyword in commit_message_lower)
            if match_count > 0:
                matched_commits.append(commit_sha)
                confidence += 0.20 * min(match_count / len(keywords), 1.0)
                reasoning.append(f"Commit mentions: {commit_message}")

            # Check for direct item text mention (partial)
            # Split item text into words and check for multi-word matches
            item_words = re.findall(r"\b\w+\b", item_text_lower)
            if len(item_words) >= 2:
                # Check for any 2+ consecutive words matching
                for i in range(len(item_words) - 1):
                    phrase = " ".join(item_words[i : i + 2])
                    if phrase in commit_message_lower and len(phrase) > 6:  # Ignore very short phrases
                        if commit_sha not in matched_commits:
                            matched_commits.append(commit_sha)
                        confidence += 0.25
                        reasoning.append(f"Commit references task: {commit_message}")
                        break

        # Cap confidence at 1.0
        confidence = min(confidence, 1.0)

        return confidence, reasoning[:5], matched_files[:10], matched_commits[:10]  # Limit results

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract meaningful keywords from item text.

        Returns:
            List of lowercase keywords (3+ chars, excluding common words)
        """
        # Remove markdown and special chars
        text = re.sub(r"\[.*?\]|\(.*?\)|[*_`]", "", text)

        # Extract words
        words = re.findall(r"\b\w+\b", text.lower())

        # Filter out common words and short words
        common_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "up", "about", "into", "through", "during",
            "including", "add", "create", "implement", "update", "fix", "remove",
            "show", "display", "handle", "support", "use", "make", "set", "get",
            "new", "all", "each", "when", "not", "also", "based",
        }
        keywords = [w for w in words if len(w) >= 3 and w not in common_words]

        return keywords

    async def verify_all_items_ai(
        self, roadmap: Roadmap, progress_callback=None
    ) -> tuple[list[RoadmapSuggestion], dict]:
        """Verify all roadmap items using AI-powered semantic analysis via Claude Code.

        This is the premium verification mode that uses Claude to actually read and
        understand your code, rather than just keyword matching.

        Args:
            roadmap: Current roadmap
            progress_callback: Optional callback function(current, total, item_text) for progress updates

        Returns:
            Tuple of (suggestions, metadata) where metadata includes ai_calls_succeeded, ai_calls_failed.
        """
        from ..agents.reconciliation_agent import ReconciliationAgent

        suggestions = []

        # First, run heuristic pre-filter to identify candidates (30% threshold to cast wide net)
        heuristic_suggestions = self.verify_all_items(roadmap, min_confidence=0.30)

        # Already filtered at 30% by verify_all_items
        candidates = heuristic_suggestions

        if not candidates:
            metadata = {
                "candidates_found": 0,
                "ai_calls_succeeded": 0,
                "ai_calls_failed": 0,
            }
            return [], metadata

        # Create AI agent
        agent = ReconciliationAgent(self.project_path)

        # Analyze each candidate with AI
        ai_succeeded = 0
        ai_failed = 0
        total = len(candidates)
        for idx, candidate in enumerate(candidates):
            if progress_callback:
                progress_callback(idx + 1, total, candidate.item_text)

            # Use matched files from heuristic as starting point
            ai_result = await agent.analyze_item(
                item_text=candidate.item_text,
                milestone_name=candidate.milestone_name,
                candidate_files=candidate.matched_files,
            )

            if ai_result.confidence > 0.0 or ai_result.completed:
                ai_succeeded += 1
            else:
                ai_failed += 1

            # Only include if AI confidence is 50%+
            if ai_result.confidence >= 0.50:
                suggestions.append(
                    RoadmapSuggestion(
                        item_text=candidate.item_text,
                        milestone_name=candidate.milestone_name,
                        confidence=ai_result.confidence,
                        reasoning=ai_result.reasoning,
                        matched_files=candidate.matched_files,
                        matched_commits=candidate.matched_commits,
                        session_id=candidate.session_id,
                    )
                )

        # Sort by confidence descending
        suggestions.sort(key=lambda s: s.confidence, reverse=True)

        metadata = {
            "candidates_found": len(candidates),
            "ai_calls_succeeded": ai_succeeded,
            "ai_calls_failed": ai_failed,
        }
        return suggestions, metadata

    def verify_all_items(self, roadmap: Roadmap, min_confidence: float = 0.50) -> list[RoadmapSuggestion]:
        """Verify all roadmap items against current codebase state.

        This is more aggressive than reconciliation - it checks ALL uncompleted items
        against the current codebase (file existence, git history, content) to determine
        what might actually be complete despite showing as incomplete.

        Args:
            roadmap: Current roadmap

        Returns:
            List of suggestions for items that appear complete
        """
        suggestions = []

        # Get all git commits (last 100) for keyword matching
        commit_messages = []
        commit_timestamps = {}

        if self.git_repo:
            try:
                # Get last 100 commits with message and timestamp
                output, code = self.git_repo._run_git(
                    "log", "-100", "--pretty=format:%H|%s|%cI"
                )
                if code == 0 and output:
                    for line in output.strip().split("\n"):
                        if not line:
                            continue
                        parts = line.split("|", 2)
                        if len(parts) == 3:
                            sha, message, timestamp_str = parts
                            commit_messages.append((sha, message))
                            try:
                                from datetime import datetime
                                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                                commit_timestamps[sha] = timestamp.replace(tzinfo=None)
                            except Exception:
                                pass
            except Exception:
                pass

        # Get all tracked files
        all_files = []
        if self.git_repo:
            try:
                output, code = self.git_repo._run_git("ls-files")
                if code == 0 and output:
                    all_files = [f for f in output.split("\n") if f]
            except Exception:
                pass

        # Check each uncompleted roadmap item
        for milestone in roadmap.milestones:
            for item in milestone.items:
                if item.completed:
                    continue  # Already marked done

                # Verify this item against codebase
                confidence, reasoning, matched_files, matched_commits = self._verify_item_against_codebase(
                    item.text, milestone.name, all_files, commit_messages
                )

                if confidence >= min_confidence:
                    # Try to find session attribution
                    session_id = self._find_session_for_commits(matched_commits, commit_timestamps)

                    suggestions.append(
                        RoadmapSuggestion(
                            item_text=item.text,
                            milestone_name=milestone.name,
                            confidence=confidence,
                            reasoning=reasoning,
                            matched_files=matched_files,
                            matched_commits=matched_commits,
                            session_id=session_id,
                        )
                    )

        # Sort by confidence descending
        suggestions.sort(key=lambda s: s.confidence, reverse=True)

        return suggestions

    def _verify_item_against_codebase(
        self,
        item_text: str,
        milestone_name: str,
        all_files: list[str],
        commit_messages: list[tuple[str, str]]
    ) -> tuple[float, list[str], list[str], list[str]]:
        """Verify a roadmap item against current codebase state.

        Returns:
            Tuple of (confidence, reasoning, matched_files, matched_commits)
        """
        confidence = 0.0
        reasoning = []
        matched_files = []
        matched_commits = []

        # Extract keywords from item text
        keywords = self._extract_keywords(item_text)

        # Match against existing files
        file_confidence = 0.0
        for filepath in all_files:
            filepath_lower = filepath.lower()
            filename = Path(filepath).stem.lower()

            # Check for keyword matches
            for keyword in keywords:
                if keyword in filepath_lower or keyword in filename:
                    matched_files.append(filepath)

                    # Check if file is substantial (exists and has content)
                    try:
                        full_path = self.project_path / filepath
                        if full_path.exists() and full_path.is_file():
                            with open(full_path, errors='ignore') as f:
                                lines = sum(1 for _ in f)

                            if lines >= 50:  # Substantial file
                                file_confidence += 0.20
                                reasoning.append(
                                    f"Found substantial implementation: {filepath} ({lines} lines)"
                                )
                            elif lines >= 10:  # Non-trivial file
                                file_confidence += 0.10
                                reasoning.append(f"Found file: {filepath} ({lines} lines)")
                            else:  # Small file
                                file_confidence += 0.05
                    except Exception:
                        pass
                    break  # Only count each file once
        confidence += min(file_confidence, 0.40)  # Cap file contribution

        # Match against commit history
        for commit_sha, commit_message in commit_messages:
            commit_message_lower = commit_message.lower()
            item_text_lower = item_text.lower()

            # Check for keyword matches
            match_count = sum(1 for keyword in keywords if keyword in commit_message_lower)
            if match_count > 0:
                if commit_sha not in matched_commits:
                    matched_commits.append(commit_sha)
                confidence += 0.15 * min(match_count / len(keywords), 1.0)
                reasoning.append(f"Git history mentions: {commit_message}")

            # Check for direct item text mention (partial)
            item_words = re.findall(r"\b\w+\b", item_text_lower)
            if len(item_words) >= 2:
                # Check for any 2+ consecutive words matching
                for i in range(len(item_words) - 1):
                    phrase = " ".join(item_words[i : i + 2])
                    if phrase in commit_message_lower and len(phrase) > 6:
                        if commit_sha not in matched_commits:
                            matched_commits.append(commit_sha)
                        confidence += 0.20
                        reasoning.append(f"Commit references task: {commit_message}")
                        break

        # Bonus for multiple pieces of evidence
        if len(matched_files) >= 2 and len(matched_commits) >= 1:
            confidence += 0.10
            reasoning.append("Multiple files + commit history found")

        # Cap confidence at 1.0
        confidence = min(confidence, 1.0)

        return confidence, reasoning[:5], matched_files[:10], matched_commits[:10]

    def _find_session_for_commits(self, commit_shas: list[str], commit_timestamps: dict) -> str | None:
        """Find the Claude session that created these commits.

        Args:
            commit_shas: List of commit SHAs to attribute
            commit_timestamps: Map of SHA -> datetime

        Returns:
            Session ID if found, None otherwise
        """
        if not commit_shas or not commit_timestamps:
            return None

        try:
            # Get the earliest commit timestamp
            earliest_commit = min((commit_timestamps.get(sha) for sha in commit_shas if sha in commit_timestamps), default=None)
            if not earliest_commit:
                return None

            # Try to find session from timeline
            from .project import Project
            from .sessions import SessionParser

            project = Project.from_path(self.project_path)
            if not project.claude_hash:
                return None

            parser = SessionParser()
            sessions = parser.find_sessions(project.claude_hash)

            # Find session that overlaps with commit time (within 5 minutes)
            from datetime import timedelta
            for session in sessions:
                if not session.start_time:
                    continue

                # Session window: start_time to start_time + duration (or +1 hour if no duration)
                session_start = session.start_time.replace(tzinfo=None) if session.start_time.tzinfo else session.start_time
                session_end = session_start + timedelta(hours=1)  # Default 1 hour window

                # Allow 5 minute buffer
                if (session_start - timedelta(minutes=5)) <= earliest_commit <= (session_end + timedelta(minutes=5)):
                    return session.session_id

            return None

        except Exception:
            # Silently fail - session attribution is optional
            return None
