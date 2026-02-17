"""
AI-powered reconciliation agent using Claude Code for semantic code analysis.

This agent uses Claude Code to intelligently determine if roadmap items have been
completed by reading and analyzing the actual codebase, rather than relying on
simple keyword matching.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class AIAnalysisResult:
    """Result of AI analysis for a single roadmap item."""

    confidence: float  # 0.0 to 1.0
    completed: bool
    reasoning: list[str]
    evidence: list[str]  # File paths with line numbers
    missing_aspects: list[str]
    files_analyzed: list[str]


class ReconciliationAgent:
    """AI-powered agent for analyzing roadmap item completion."""

    def __init__(self, project_path: Path):
        """Initialize the reconciliation agent.

        Args:
            project_path: Path to the project root
        """
        self.project_path = project_path

    async def analyze_item(
        self,
        item_text: str,
        milestone_name: str,
        candidate_files: list[str],
    ) -> AIAnalysisResult:
        """Use Claude Code to analyze if a roadmap item has been completed.

        Args:
            item_text: The roadmap item text to analyze
            milestone_name: The milestone this item belongs to
            candidate_files: List of file paths that might be relevant (from heuristic pre-filter)

        Returns:
            AIAnalysisResult with confidence, reasoning, and evidence
        """
        # Limit to top 10 most relevant files to avoid context bloat
        files_to_analyze = candidate_files[:10]

        # Build the analysis prompt
        prompt = self._build_analysis_prompt(item_text, milestone_name, files_to_analyze)

        # Run Claude Code analysis (synchronous for now, will optimize later)
        result = await self._run_claude_analysis(prompt)

        return result

    def _build_analysis_prompt(
        self, item_text: str, milestone_name: str, candidate_files: list[str]
    ) -> str:
        """Build the prompt for Claude Code to analyze a roadmap item.

        Args:
            item_text: The roadmap item description
            milestone_name: The milestone name for context
            candidate_files: List of file paths to analyze

        Returns:
            Formatted prompt string
        """
        # Read file stats (LOC, last modified) for context
        file_info = []
        for filepath in candidate_files:
            full_path = self.project_path / filepath
            if full_path.exists() and full_path.is_file():
                try:
                    with open(full_path, errors="ignore") as f:
                        lines = sum(1 for _ in f)
                    file_info.append(f"- {filepath} ({lines} lines)")
                except Exception:
                    file_info.append(f"- {filepath}")
            else:
                file_info.append(f"- {filepath} (not found)")

        files_section = "\n".join(file_info) if file_info else "No candidate files found"

        prompt = f"""You are analyzing a codebase to determine if a specific roadmap item has been completed.

CONTEXT:
Milestone: {milestone_name}

ROADMAP ITEM TO VERIFY:
"{item_text}"

RELEVANT FILES FOUND (via heuristic pre-filter):
{files_section}

YOUR TASK:
1. Read the relevant files listed above (use standard file reading tools)
2. Analyze the code to determine if this roadmap item has been substantially implemented
3. Consider both completion and quality of implementation
4. Provide a confidence score based on evidence

RESPONSE FORMAT:
You MUST respond with ONLY a valid JSON object (no markdown, no code blocks, just raw JSON):

{{
  "confidence": <integer 0-100>,
  "completed": <boolean>,
  "reasoning": [
    "<brief explanation of what you found>",
    "<another key finding>",
    "<etc>"
  ],
  "evidence": [
    "<filepath:line_range - description>",
    "<another file reference>"
  ],
  "missing_aspects": [
    "<what's missing or incomplete>",
    "<another gap>"
  ]
}}

CONFIDENCE SCORING GUIDELINES:
- 90-100%: Fully implemented, production-ready, meets all requirements
- 70-89%: Substantially complete, minor gaps or polish needed
- 50-69%: Partially implemented, significant work done but incomplete
- 30-49%: Some relevant code exists but far from complete
- 0-29%: Little to no evidence of implementation

IMPORTANT:
- Be strict: Only give 70%+ if the implementation is genuinely substantial
- Look for actual functionality, not just placeholder code or comments
- Consider test coverage if tests exist
- Return ONLY the JSON object, nothing else

Begin analysis now.
"""
        return prompt

    async def _run_claude_analysis(self, prompt: str) -> AIAnalysisResult:
        """Run the analysis prompt through Claude Code.

        Args:
            prompt: The formatted prompt

        Returns:
            Parsed AIAnalysisResult
        """
        try:
            # Import here to avoid circular dependency
            from .dispatcher import dispatch_task

            # Run the prompt via Claude CLI
            result = await asyncio.to_thread(
                dispatch_task,
                prompt=prompt,
                working_dir=self.project_path,
                timeout_seconds=120,
            )

            # Parse the output
            if result.success:
                output = result.output or ""
                return self._parse_claude_response(output)
            else:
                # Analysis failed, return low confidence
                logger.warning(f"Claude Code analysis failed: {result.error_message}")
                return AIAnalysisResult(
                    confidence=0.0,
                    completed=False,
                    reasoning=["Analysis failed - Claude Code dispatch error"],
                    evidence=[],
                    missing_aspects=["Could not analyze code"],
                    files_analyzed=[],
                )

        except Exception as e:
            logger.exception("Failed to run Claude analysis")
            return AIAnalysisResult(
                confidence=0.0,
                completed=False,
                reasoning=[f"Analysis error: {str(e)}"],
                evidence=[],
                missing_aspects=["Could not analyze code"],
                files_analyzed=[],
            )

    def _parse_claude_response(self, output: str) -> AIAnalysisResult:
        """Parse Claude's JSON response into AIAnalysisResult.

        Args:
            output: Raw output from Claude Code

        Returns:
            Parsed AIAnalysisResult
        """
        try:
            # Extract JSON from output (Claude might include extra text)
            # Look for JSON object pattern
            json_match = re.search(r"\{[\s\S]*\}", output)
            if not json_match:
                raise ValueError("No JSON object found in Claude's response")

            json_str = json_match.group(0)
            data = json.loads(json_str)

            # Validate required fields
            required_fields = ["confidence", "completed", "reasoning", "evidence"]
            for field in required_fields:
                if field not in data:
                    raise ValueError(f"Missing required field: {field}")

            # Normalize confidence to 0.0-1.0 range
            confidence = float(data["confidence"]) / 100.0
            confidence = max(0.0, min(1.0, confidence))  # Clamp to valid range

            return AIAnalysisResult(
                confidence=confidence,
                completed=bool(data["completed"]),
                reasoning=data["reasoning"][:5],  # Limit to 5 items
                evidence=data["evidence"][:10],  # Limit to 10 items
                missing_aspects=data.get("missing_aspects", [])[:5],
                files_analyzed=[],  # Will be populated by caller
            )

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"Failed to parse Claude response: {e}")
            logger.debug(f"Raw output: {output}")

            # Fallback: try to extract confidence from text
            confidence_match = re.search(r"confidence[\":\s]+(\d+)", output, re.IGNORECASE)
            if confidence_match:
                confidence = float(confidence_match.group(1)) / 100.0
            else:
                confidence = 0.0

            return AIAnalysisResult(
                confidence=confidence,
                completed=confidence >= 0.7,
                reasoning=["Failed to parse structured response from Claude"],
                evidence=[],
                missing_aspects=["Could not extract detailed analysis"],
                files_analyzed=[],
            )
