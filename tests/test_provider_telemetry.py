from src.core.provider_telemetry import usage_snapshot


def test_usage_snapshot_estimates_when_output_missing() -> None:
    snapshot = usage_snapshot("claude", "Short prompt")

    assert snapshot.provider == "claude"
    assert snapshot.confidence == "estimated"
    assert snapshot.total_tokens >= 480
    assert snapshot.estimated_cost_usd is not None


def test_usage_snapshot_parses_tokens_from_output() -> None:
    output = "Input tokens: 1,200\nOutput tokens: 3,400\nEstimated cost: $0.42"
    snapshot = usage_snapshot("codex", "Implement parser", output=output)

    assert snapshot.confidence == "parsed"
    assert snapshot.input_tokens == 1200
    assert snapshot.output_tokens == 3400
    assert snapshot.total_tokens == 4600
    assert snapshot.telemetry_source == "output_parse"
    assert snapshot.estimated_cost_usd == 0.42
