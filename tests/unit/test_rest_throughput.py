from __future__ import annotations

import time
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Literal

import pytest
from grid_contracts.canonical import canonical_sha256
from grid_contracts.market import MINUTE_MS
from grid_data.rest_throughput import (
    ThroughputProfile,
    build_rest_throughput_evidence,
    parse_profiles,
)


def inventory() -> dict[str, Any]:
    records = []
    for index, symbol in enumerate(("AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT")):
        records.append(
            {
                "contract_type": "LinearPerpetual",
                "launch_time_ms": 1_577_836_800_000 + index * MINUTE_MS,
                "quote_coin": "USDT",
                "settle_coin": "USDT",
                "status": "Trading",
                "symbol": symbol,
            }
        )
    return {
        "evidence_schema": "grid.bybit-public-inventory/v1",
        "fetched_at_utc": "2026-08-12T12:00:00Z",
        "inventory_status": "partial",
        "records": records,
    }


def source_assessment(inventory_hash: str = "a" * 64) -> dict[str, Any]:
    return {
        "evidence_schema": "grid.bybit-history-source-assessment/v2",
        "fetched_at_utc": "2026-08-12T12:05:00Z",
        "inventory_source": {"artifact_sha256": inventory_hash},
        "inventory_backfill_estimate": {
            "combined_requests": {
                "conservative_60m_funding_interval": 1_200,
                "current_funding_intervals": 1_000,
            }
        },
    }


class FullPageClient:
    def __init__(self, *, delay_seconds: float = 0, short: bool = False) -> None:
        self.delay_seconds = delay_seconds
        self.short = short

    def kline_page(
        self,
        *,
        kind: Literal["trade", "mark"],
        symbol: str,
        start_ms: int,
        end_ms: int,
        category: Literal["linear", "inverse"] = "linear",
        limit: int = 1000,
    ) -> tuple[tuple[str, ...], ...]:
        del symbol, start_ms, category
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        count = limit - 1 if self.short else limit
        width = 7 if kind == "trade" else 5
        return tuple(
            tuple([str(end_ms - index * MINUTE_MS), *("1" for _ in range(width - 1))])
            for index in range(count)
        )


def build(*, short: bool = False) -> dict[str, Any]:
    return build_rest_throughput_evidence(
        lambda: FullPageClient(short=short),
        inventory(),
        source_assessment(),
        command="grid-data rest-throughput",
        base_url="https://api.bybit.com",
        inventory_artifact="inventory.json",
        inventory_artifact_sha256="a" * 64,
        source_assessment_artifact="source.json",
        source_assessment_artifact_sha256="b" * 64,
        workstation_artifact="workstation.json",
        workstation_artifact_sha256="c" * 64,
        workstation_captured_at_utc="2026-08-12T12:10:00Z",
        profiles=(ThroughputProfile(workers=2, target_rps=20),),
        stage_seconds=Decimal("0.1"),
        cooldown_seconds=Decimal("0"),
        sample_size=2,
        max_requests=10,
    )


def test_rest_throughput_builds_bounded_value_free_evidence() -> None:
    payload = build()

    assert payload["status"] == "bounded-benchmark-complete"
    assert payload["request_audit"] == {
        "actual_request_count": 2,
        "executed_profile_count": 1,
        "max_requests": 10,
        "planned_profile_count": 1,
        "planned_request_count": 2,
    }
    assert payload["storage_policy"] == {
        "market_rows_persisted": False,
        "market_values_persisted": False,
        "response_content_hashes_persisted": True,
        "tick_rows_requested": False,
    }
    assert payload["profiles"][0]["success_count"] == 2
    assert payload["profiles"][0]["row_count"] == 2_000
    assert payload["recommendation"]["candidate_workers"] == 2
    assert (
        payload["bootstrap_request_only_projection"]["current_funding_intervals"]["request_count"]
        == 1_000
    )
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == canonical_sha256(hash_input)

    forbidden_keys = {"open", "high", "low", "close", "volume", "turnover"}

    def assert_no_market_values(value: Any) -> None:
        if isinstance(value, Mapping):
            assert forbidden_keys.isdisjoint(value)
            for nested in value.values():
                assert_no_market_values(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_no_market_values(nested)

    assert_no_market_values(payload)


def test_rest_throughput_stops_after_short_page() -> None:
    payload = build(short=True)

    assert payload["status"] == "bounded-benchmark-partial"
    assert payload["profiles"][0]["status"] == "failed"
    assert payload["profiles"][0]["error_counts"] == {"short-kline-page": 1}
    assert payload["recommendation"] is None
    assert payload["bootstrap_request_only_projection"] is None


def test_rest_throughput_continues_after_under_target_profile() -> None:
    payload = build_rest_throughput_evidence(
        lambda: FullPageClient(delay_seconds=0.1),
        inventory(),
        source_assessment(),
        command="test",
        base_url="https://api.bybit.com",
        inventory_artifact="inventory.json",
        inventory_artifact_sha256="a" * 64,
        source_assessment_artifact="source.json",
        source_assessment_artifact_sha256="b" * 64,
        workstation_artifact="workstation.json",
        workstation_artifact_sha256="c" * 64,
        workstation_captured_at_utc="2026-08-12T12:10:00Z",
        profiles=(
            ThroughputProfile(workers=1, target_rps=20),
            ThroughputProfile(workers=2, target_rps=40),
        ),
        stage_seconds=Decimal("0.1"),
        cooldown_seconds=Decimal("0"),
        sample_size=2,
        max_requests=10,
    )

    assert payload["status"] == "bounded-benchmark-complete"
    assert [profile["status"] for profile in payload["profiles"]] == [
        "under-target",
        "under-target",
    ]
    assert payload["request_audit"]["executed_profile_count"] == 2
    assert payload["recommendation"] is None


def test_rest_throughput_rejects_request_plan_before_client_creation() -> None:
    created = 0

    def factory() -> FullPageClient:
        nonlocal created
        created += 1
        return FullPageClient()

    with pytest.raises(ValueError, match="exceed max_requests"):
        build_rest_throughput_evidence(
            factory,
            inventory(),
            source_assessment(),
            command="test",
            base_url="https://api.bybit.com",
            inventory_artifact="inventory.json",
            inventory_artifact_sha256="a" * 64,
            source_assessment_artifact="source.json",
            source_assessment_artifact_sha256="b" * 64,
            workstation_artifact="workstation.json",
            workstation_artifact_sha256="c" * 64,
            workstation_captured_at_utc="2026-08-12T12:10:00Z",
            profiles=(ThroughputProfile(workers=32, target_rps=96),),
            stage_seconds=Decimal("10"),
            cooldown_seconds=Decimal("0"),
            sample_size=2,
            max_requests=10,
        )

    assert created == 0


def test_rest_throughput_rejects_cross_inventory_assessment() -> None:
    with pytest.raises(ValueError, match="not bound"):
        build_rest_throughput_evidence(
            FullPageClient,
            inventory(),
            source_assessment("d" * 64),
            command="test",
            base_url="https://api.bybit.com",
            inventory_artifact="inventory.json",
            inventory_artifact_sha256="a" * 64,
            source_assessment_artifact="source.json",
            source_assessment_artifact_sha256="b" * 64,
            workstation_artifact="workstation.json",
            workstation_artifact_sha256="c" * 64,
            workstation_captured_at_utc="2026-08-12T12:10:00Z",
            profiles=(ThroughputProfile(workers=1, target_rps=1),),
            stage_seconds=Decimal("0.1"),
            cooldown_seconds=Decimal("0"),
            sample_size=1,
            max_requests=1,
        )


def test_profile_parser_enforces_safe_ceiling_and_strict_order() -> None:
    assert parse_profiles("1:5,4:20") == (
        ThroughputProfile(workers=1, target_rps=5),
        ThroughputProfile(workers=4, target_rps=20),
    )
    with pytest.raises(ValueError, match=r"\[1, 96\]"):
        parse_profiles("32:97")
    with pytest.raises(ValueError, match="nondecreasing"):
        parse_profiles("4:20,2:40")
