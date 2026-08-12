from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any, Literal

import pytest
from grid_contracts.canonical import canonical_sha256
from grid_contracts.market import MINUTE_MS
from grid_data.rest_history_boundary import build_rest_history_boundary


class FakeHistoryClient:
    def __init__(
        self,
        earliest: Mapping[tuple[str, str], int],
        calls: list[tuple[str, str, int, int]],
        lock: Lock,
    ) -> None:
        self._earliest = earliest
        self._calls = calls
        self._lock = lock

    def _timestamp(self, dataset: str, symbol: str, start_ms: int, end_ms: int) -> int | None:
        with self._lock:
            self._calls.append((dataset, symbol, start_ms, end_ms))
        earliest = self._earliest[(dataset, symbol)]
        if end_ms < earliest:
            return None
        return max(start_ms, earliest) // MINUTE_MS * MINUTE_MS

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
        assert category == "linear"
        assert limit in (1, 1_000)
        dataset = "trade_price_1m" if kind == "trade" else "mark_price_1m"
        timestamp = self._timestamp(dataset, symbol, start_ms, end_ms)
        if timestamp is None:
            return ()
        width = 7 if kind == "trade" else 5
        return ((str(timestamp), *("1" for _ in range(width - 1))),)

    def funding_page(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        category: Literal["linear", "inverse"] = "linear",
        limit: int = 200,
    ) -> tuple[Mapping[str, Any], ...]:
        assert category == "linear"
        assert limit in (1, 200)
        timestamp = self._timestamp("funding", symbol, start_ms, end_ms)
        if timestamp is None:
            return ()
        return (
            {
                "fundingRate": "0.0001",
                "fundingRateTimestamp": str(timestamp),
                "symbol": symbol,
            },
        )


def inventory(*, minutes: int = 16) -> dict[str, Any]:
    end = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=minutes)
    end_ms = int(end.timestamp() * 1_000)
    start_ms = end_ms - minutes * MINUTE_MS
    records = []
    for index, (symbol, status) in enumerate(
        (
            ("AAAUSDT", "Trading"),
            ("BBBUSDT", "Trading"),
            ("CCCUSDT", "Closed"),
            ("DDDUSDT", "Closed"),
        )
    ):
        records.append(
            {
                "contract_type": "LinearPerpetual",
                "delivery_time_ms": end_ms if status == "Closed" else 0,
                "funding_interval_minutes": 60,
                "launch_time_ms": start_ms + index * MINUTE_MS,
                "quote_coin": "USDT",
                "settle_coin": "USDT",
                "status": status,
                "symbol": symbol,
            }
        )
    return {
        "evidence_schema": "grid.bybit-public-inventory/v1",
        "fetched_at_utc": end.isoformat().replace("+00:00", "Z"),
        "inventory_status": "partial",
        "records": records,
    }


def test_rest_boundary_is_bounded_and_persists_no_market_values() -> None:
    source = inventory()
    records = source["records"]
    earliest: dict[tuple[str, str], int] = {}
    for record in records:
        for dataset_index, dataset in enumerate(("funding", "mark_price_1m", "trade_price_1m")):
            earliest[(dataset, record["symbol"])] = (
                record["launch_time_ms"] + (dataset_index + 1) * MINUTE_MS
            )
    calls: list[tuple[str, str, int, int]] = []
    lock = Lock()
    payload = build_rest_history_boundary(
        lambda: FakeHistoryClient(earliest, calls, lock),
        source,
        command="grid-data rest-history-boundary",
        inventory_artifact="inventory.json",
        inventory_artifact_sha256="a" * 64,
        sample_size=4,
        workers=1,
        max_requests=100,
    )

    assert payload["status"] == "bounded-sample-complete"
    assert payload["selection"]["selected_status_counts"] == {"Closed": 2, "Trading": 2}
    assert payload["storage_policy"] == {
        "market_rows_persisted": False,
        "market_values_persisted": False,
        "response_content_hashes_persisted": True,
        "tick_rows_requested": False,
    }
    assert (
        payload["request_audit"]["actual_request_count"]
        <= payload["request_audit"]["planned_request_upper_bound"]
    )
    for symbol in payload["symbols"]:
        assert symbol["datasets"]["funding"]["delay_after_probe_start_minutes"] == 1
        assert symbol["datasets"]["mark_price_1m"]["delay_after_probe_start_minutes"] == 2
        assert symbol["datasets"]["trade_price_1m"]["delay_after_probe_start_minutes"] == 3
        assert all(
            dataset["observation_semantics"] == "exact-within-launch-window"
            for dataset in symbol["datasets"].values()
        )
        assert all(
            "price" not in key and "rate" not in key and "volume" not in key
            for dataset in symbol["datasets"].values()
            for checkpoint in dataset["checkpoints"]
            for key in checkpoint
        )
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == canonical_sha256(hash_input)
    assert len(calls) == payload["request_audit"]["actual_request_count"]


def test_rest_boundary_rejects_request_plan_before_client_creation() -> None:
    created = 0

    def factory() -> FakeHistoryClient:
        nonlocal created
        created += 1
        return FakeHistoryClient({}, [], Lock())

    with pytest.raises(ValueError, match="exceed max_requests"):
        build_rest_history_boundary(
            factory,
            inventory(minutes=1_000),
            command="test",
            inventory_artifact="inventory.json",
            inventory_artifact_sha256="a" * 64,
            sample_size=4,
            workers=4,
            max_requests=1,
        )

    assert created == 0


def test_rest_boundary_terminal_checkpoint_detects_late_history() -> None:
    source = inventory(minutes=2_000)
    earliest = {
        (dataset, record["symbol"]): record["launch_time_ms"] + 1_500 * MINUTE_MS
        for record in source["records"]
        for dataset in ("funding", "mark_price_1m", "trade_price_1m")
    }
    calls: list[tuple[str, str, int, int]] = []
    lock = Lock()

    payload = build_rest_history_boundary(
        lambda: FakeHistoryClient(earliest, calls, lock),
        source,
        command="test",
        inventory_artifact="inventory.json",
        inventory_artifact_sha256="a" * 64,
        sample_size=4,
        workers=1,
        max_requests=100,
    )

    assert payload["request_audit"]["planned_request_upper_bound"] == 24
    for symbol in payload["symbols"]:
        for dataset in symbol["datasets"].values():
            assert dataset["launch_window_nonempty"] is False
            assert dataset["status"] == "available"
            assert dataset["observation_semantics"] == ("sampled-checkpoint-not-exact-boundary")
            assert dataset["checkpoints"][-1]["kind"] == "terminal"


def test_rest_boundary_rejects_duplicate_inventory_symbols() -> None:
    source = inventory()
    source["records"].append(dict(source["records"][0]))

    with pytest.raises(ValueError, match="unique"):
        build_rest_history_boundary(
            lambda: FakeHistoryClient({}, [], Lock()),
            source,
            command="test",
            inventory_artifact="inventory.json",
            inventory_artifact_sha256="a" * 64,
            sample_size=4,
        )
