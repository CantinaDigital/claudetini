from src.core.provider_telemetry import ProviderUsageSnapshot
from src.core.provider_usage import ProviderUsageStore


def test_provider_usage_store_records_and_aggregates(temp_dir) -> None:
    store = ProviderUsageStore("proj-usage", base_dir=temp_dir)

    claude_snapshot = ProviderUsageSnapshot(
        provider="claude",
        input_tokens=100,
        output_tokens=300,
        total_tokens=400,
        effort_units=0.4,
        estimated_cost_usd=0.012,
        confidence="parsed",
        model="claude-sonnet-4-20250514",
        telemetry_source="output_parse",
    )
    codex_snapshot = ProviderUsageSnapshot(
        provider="codex",
        input_tokens=200,
        output_tokens=500,
        total_tokens=700,
        effort_units=0.7,
        estimated_cost_usd=None,
        confidence="estimated",
        model="gpt-5-codex",
        telemetry_source="heuristic",
    )

    first = store.record(claude_snapshot, source="dispatch", session_id="sess-1")
    duplicate = store.record(claude_snapshot, source="dispatch", session_id="sess-1")
    second = store.record(codex_snapshot, source="fallback_dispatch", session_id="sess-2")

    totals = store.totals()

    assert first is True
    assert duplicate is False
    assert second is True

    assert totals["providers"]["claude"]["tokens"] == 400
    assert totals["providers"]["codex"]["tokens"] == 700
    assert totals["all"]["tokens"] == 1100
    assert totals["all"]["events"] == 2
    assert store.unique_session_count() == 2
    assert store.latest_event_timestamp() is not None
