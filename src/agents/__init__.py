"""Claude Code integration and sub-agent dispatch."""

from .claude_agents import AgentRegistry, ClaudeSubAgent, build_agents_flag_json
from .dispatcher import ClaudeDispatcher, DispatchResult, dispatch_task
from .executor import GateExecutor
from .gates import QualityGateRunner
from .hooks import GitPrePushHookManager
from .parser import AgentOutputParser
from .prompts import PromptBuilder

__all__ = [
    "ClaudeDispatcher",
    "DispatchResult",
    "dispatch_task",
    "PromptBuilder",
    "GateExecutor",
    "QualityGateRunner",
    "GitPrePushHookManager",
    "AgentOutputParser",
    "AgentRegistry",
    "ClaudeSubAgent",
    "build_agents_flag_json",
]
