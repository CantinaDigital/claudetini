"""Provider usage telemetry adapters.

This module normalizes token/cost telemetry across supported CLI providers.
If provider output does not expose usage counters, we fall back to prompt-size
heuristics so the UI can still offer routing guidance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .cost_tracker import TokenUsage, estimate_cost

ProviderName = Literal["claude", "codex", "gemini"]
TelemetryConfidence = Literal["estimated", "parsed"]

INPUT_PATTERNS = (
    r"input[_\s-]*tokens?\s*[:=]\s*([\d,]+)",
    r"prompt[_\s-]*tokens?\s*[:=]\s*([\d,]+)",
)
OUTPUT_PATTERNS = (
    r"output[_\s-]*tokens?\s*[:=]\s*([\d,]+)",
    r"completion[_\s-]*tokens?\s*[:=]\s*([\d,]+)",
)
TOTAL_PATTERNS = (
    r"total[_\s-]*tokens?\s*[:=]\s*([\d,]+)",
    r"tokens?\s*used\s*[:=]\s*([\d,]+)",
)
COST_PATTERNS = (
    r"(?:estimated\s+)?cost(?:\s+usd)?\s*[:=]\s*\$?\s*([\d]+(?:\.[\d]+)?)",
    r"\$\s*([\d]+(?:\.[\d]+)?)\s*(?:usd)?",
)


@dataclass(frozen=True)
class ProviderUsageSnapshot:
    """Normalized usage snapshot for a single prompt run."""

    provider: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    effort_units: float
    estimated_cost_usd: float | None
    confidence: TelemetryConfidence
    model: str | None
    telemetry_source: str


class ProviderTelemetryAdapter:
    """Base adapter for provider usage extraction."""

    provider: str = "claude"
    model: str | None = None
    output_multiplier: float = 3.0

    def estimate(self, prompt: str) -> ProviderUsageSnapshot:
        input_tokens = max(120, len(prompt) // 4)
        output_tokens = max(0, int(round(input_tokens * self.output_multiplier)))
        total_tokens = input_tokens + output_tokens
        cost = self._estimate_cost(input_tokens, output_tokens)
        return ProviderUsageSnapshot(
            provider=self.provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            effort_units=round(total_tokens / 1000, 3),
            estimated_cost_usd=cost,
            confidence="estimated",
            model=self.model,
            telemetry_source="heuristic",
        )

    def from_output(self, prompt: str, output: str | None) -> ProviderUsageSnapshot:
        baseline = self.estimate(prompt)
        if not output:
            return baseline

        input_tokens = _extract_first_int(output, INPUT_PATTERNS)
        output_tokens = _extract_first_int(output, OUTPUT_PATTERNS)
        total_tokens = _extract_first_int(output, TOTAL_PATTERNS)

        parsed_any = False

        if input_tokens is None and output_tokens is None and total_tokens is None:
            return baseline

        if total_tokens is not None:
            parsed_any = True
            if input_tokens is None and output_tokens is None:
                input_tokens = max(1, int(total_tokens * 0.3))
                output_tokens = max(0, total_tokens - input_tokens)

        if input_tokens is not None:
            parsed_any = True
        if output_tokens is not None:
            parsed_any = True

        if input_tokens is None:
            input_tokens = baseline.input_tokens
        if output_tokens is None:
            output_tokens = max(0, int(round(input_tokens * self.output_multiplier)))

        total = input_tokens + output_tokens

        parsed_cost = _extract_first_float(output, COST_PATTERNS)
        estimated_cost = parsed_cost if parsed_cost is not None else self._estimate_cost(input_tokens, output_tokens)

        if not parsed_any:
            return baseline

        return ProviderUsageSnapshot(
            provider=self.provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total,
            effort_units=round(total / 1000, 3),
            estimated_cost_usd=estimated_cost,
            confidence="parsed",
            model=self.model,
            telemetry_source="output_parse",
        )

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float | None:
        if self.provider != "claude":
            return None
        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model or "claude-3-5-sonnet-latest",
        )
        return round(estimate_cost(usage, usage.model), 6)


class ClaudeTelemetryAdapter(ProviderTelemetryAdapter):
    provider = "claude"
    model = "claude-sonnet-4-20250514"
    output_multiplier = 3.0


class CodexTelemetryAdapter(ProviderTelemetryAdapter):
    provider = "codex"
    model = "gpt-5-codex"
    output_multiplier = 2.6


class GeminiTelemetryAdapter(ProviderTelemetryAdapter):
    provider = "gemini"
    model = "gemini-2.5-pro"
    output_multiplier = 2.8


def get_provider_adapter(provider: str) -> ProviderTelemetryAdapter:
    key = provider.strip().lower()
    if key == "claude":
        return ClaudeTelemetryAdapter()
    if key == "codex":
        return CodexTelemetryAdapter()
    if key == "gemini":
        return GeminiTelemetryAdapter()

    fallback = ProviderTelemetryAdapter()
    fallback.provider = key or "claude"
    fallback.model = None
    fallback.output_multiplier = 2.8
    return fallback


def usage_snapshot(provider: str, prompt: str, output: str | None = None) -> ProviderUsageSnapshot:
    """Return normalized usage telemetry for a prompt execution."""
    adapter = get_provider_adapter(provider)
    return adapter.from_output(prompt=prompt, output=output)


def _extract_first_int(text: str, patterns: tuple[str, ...]) -> int | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        raw = match.group(1).replace(",", "").strip()
        if raw.isdigit():
            return int(raw)
    return None


def _extract_first_float(text: str, patterns: tuple[str, ...]) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        raw = match.group(1).replace(",", "").strip()
        try:
            value = float(raw)
        except ValueError:
            continue
        if value >= 0:
            return value
    return None
