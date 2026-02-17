"""Core business logic for Claudetini."""

from .branch_strategy import BranchStrategy, BranchStrategyDetector, BranchStrategyResult
from .cache import CachePayload, JsonCache
from .claude_md_manager import ClaudeMdManager, ClaudeMdStatus
from .cost_tracker import CostTracker, TokenUsage, UsageTotals, estimate_cost, parse_usage_file
from .diff_summary import DiffSummary, DiffSummaryBuilder, FileChange
from .gate_results import (
    GateFailureTodo,
    GateFinding,
    GateResultStore,
    GateRunReport,
    StoredGateResult,
)
from .gate_trends import GateHistoryPoint, GateTrend, GateTrendStore, render_sparkline
from .git_utils import GitRepo
from .health import HealthChecker, HealthStatus
from .intelligence import IntelligenceReport, IntelligenceSummary, ProjectIntelligence
from .plan_models import (
    PlanItem,
    PlanItemStatus,
    PlanMilestone,
    PlanSource,
    UnifiedProjectPlan,
)
from .plan_scanner import ProjectPlanScanner
from .preflight import PreflightCheck, PreflightChecker, PreflightResult
from .project import Project, ProjectRegistry
from .prompt_history import PromptHistory, PromptHistoryStore, PromptVersion
from .provider_telemetry import ProviderUsageSnapshot, usage_snapshot
from .provider_usage import ProviderUsageStore, ProviderUsageTotals
from .recommender import NextStep, NextStepRecommender
from .retry import RetryAttempt, RetryChain, RetryComposer
from .roadmap import Milestone, Roadmap, RoadmapItem
from .scheduling import DispatchScheduler, QueuedDispatch, SchedulingConfig
from .secrets_scanner import ScanResult, SecretsScanner, scan_before_commit
from .session_hooks import HookConfig, HookResult, HookSpec, SessionHookManager
from .session_report import SessionReport, SessionReportBuilder, SessionReportStore
from .sessions import SessionParser, SessionSummary
from .slash_commands import SlashCommandGenerator
from .system_prompt import SystemPromptBuilder, SystemPromptContext
from .timeline import CommitInfo, TestResult, TimelineBuilder, TimelineEntry
from .todos import TodoItem, TodoParser
from .token_budget import BudgetDecision, TokenBudget, TokenBudgetManager

__all__ = [
    "Project",
    "ProjectRegistry",
    "ProviderUsageSnapshot",
    "ProviderUsageStore",
    "ProviderUsageTotals",
    "Roadmap",
    "Milestone",
    "RoadmapItem",
    "SessionParser",
    "SessionSummary",
    "TodoParser",
    "TodoItem",
    "GitRepo",
    "HealthChecker",
    "HealthStatus",
    "NextStepRecommender",
    "NextStep",
    "SecretsScanner",
    "ScanResult",
    "scan_before_commit",
    "PlanItem",
    "PlanItemStatus",
    "PlanSource",
    "PlanMilestone",
    "UnifiedProjectPlan",
    "ProjectPlanScanner",
    "BranchStrategy",
    "BranchStrategyDetector",
    "BranchStrategyResult",
    "CachePayload",
    "JsonCache",
    "ClaudeMdManager",
    "ClaudeMdStatus",
    "CostTracker",
    "TokenUsage",
    "UsageTotals",
    "estimate_cost",
    "parse_usage_file",
    "GateResultStore",
    "GateRunReport",
    "StoredGateResult",
    "GateFinding",
    "GateFailureTodo",
    "GateTrendStore",
    "GateTrend",
    "GateHistoryPoint",
    "render_sparkline",
    "DiffSummary",
    "DiffSummaryBuilder",
    "FileChange",
    "PreflightCheck",
    "PreflightChecker",
    "PreflightResult",
    "PromptHistory",
    "PromptHistoryStore",
    "PromptVersion",
    "usage_snapshot",
    "RetryAttempt",
    "RetryChain",
    "RetryComposer",
    "SessionReport",
    "SessionReportBuilder",
    "SessionReportStore",
    "HookSpec",
    "HookResult",
    "HookConfig",
    "SessionHookManager",
    "DispatchScheduler",
    "QueuedDispatch",
    "SchedulingConfig",
    "TokenBudget",
    "BudgetDecision",
    "TokenBudgetManager",
    "SlashCommandGenerator",
    "SystemPromptBuilder",
    "SystemPromptContext",
    "CommitInfo",
    "TestResult",
    "TimelineBuilder",
    "TimelineEntry",
    "ProjectIntelligence",
    "IntelligenceReport",
    "IntelligenceSummary",
]
