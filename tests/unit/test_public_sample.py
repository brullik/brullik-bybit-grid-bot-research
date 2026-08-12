from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from grid_bybit_public import BybitPublicClient
from grid_contracts.canonical import canonical_sha256
from grid_data.public_sample import MAX_SAMPLE_SPAN_MS, build_public_sample


class QueueTransport:
    def __init__(self, responses: list[Mapping[str, Any]]) -> None:
        self.responses = responses

    def get(self, _path: str, _params: Mapping[str, str | int]) -> Mapping[str, Any]:
        return self.responses.pop(0)


def response(result: Mapping[str, Any]) -> Mapping[str, Any]:
    return {"retCode": 0, "retMsg": "OK", "result": result}


def instrument() -> Mapping[str, Any]:
    return {
        "contractType": "LinearPerpetual",
        "fundingInterval": 1,
        "launchTime": "0",
        "settleCoin": "USDT",
        "symbol": "BTCUSDT",
    }


def trade(timestamp: int, *, low: str = "1", high: str = "2") -> list[str]:
    return [str(timestamp), "1.5", high, low, "1.6", "10", "16"]


def mark(timestamp: int) -> list[str]:
    return [str(timestamp), "1.5", "2", "1", "1.6"]


def funding(timestamp: int) -> dict[str, str]:
    return {
        "fundingRate": "0.0001000",
        "fundingRateTimestamp": str(timestamp),
        "symbol": "BTCUSDT",
    }


def client_for(
    trade_rows: list[list[str]],
    mark_rows: list[list[str]] | None = None,
    funding_rows: list[dict[str, str]] | None = None,
) -> BybitPublicClient:
    return BybitPublicClient(
        QueueTransport(
            [
                response({"list": [instrument()]}),
                response({"list": trade_rows}),
                response({"list": mark_rows or [mark(180_000), mark(120_000), mark(60_000)]}),
                response(
                    {"list": funding_rows or [funding(180_000), funding(120_000), funding(60_000)]}
                ),
            ]
        )
    )


def test_public_sample_validates_and_hashes_without_persisting_rows() -> None:
    payload = build_public_sample(
        client_for([trade(180_000), trade(120_000), trade(60_000)]),
        symbol="BTCUSDT",
        start_ms=60_000,
        end_ms=180_000,
    )

    assert payload["sample_status"] == "complete"
    assert payload["request"]["funding_interval_minutes"] == 1
    assert payload["datasets"]["trade_kline_1m"]["row_count"] == 3
    assert payload["datasets"]["funding_event"]["content_sha256"] == canonical_sha256(
        [
            {"funding_rate": "0.0001", "funding_time_ms": 180_000},
            {"funding_rate": "0.0001", "funding_time_ms": 120_000},
            {"funding_rate": "0.0001", "funding_time_ms": 60_000},
        ]
    )
    assert all("rows" not in summary for summary in payload["datasets"].values())


def test_public_sample_reports_each_missing_candle() -> None:
    payload = build_public_sample(
        client_for([trade(180_000), trade(60_000)]),
        symbol="BTCUSDT",
        start_ms=60_000,
        end_ms=180_000,
    )
    summary = payload["datasets"]["trade_kline_1m"]
    assert summary["missing_expected_timestamp_count"] == 1
    assert summary["missing_expected_timestamps_sample"] == [120_000]
    assert payload["sample_status"] == "partial"


def test_public_sample_rejects_invalid_ohlc() -> None:
    with pytest.raises(ValueError, match="outside"):
        build_public_sample(
            client_for([trade(60_000, low="1.6", high="2")]),
            symbol="BTCUSDT",
            start_ms=60_000,
            end_ms=60_000,
        )


def test_public_sample_is_bounded_to_31_days() -> None:
    with pytest.raises(ValueError, match="31 days"):
        build_public_sample(
            BybitPublicClient(QueueTransport([])),
            symbol="BTCUSDT",
            start_ms=0,
            end_ms=MAX_SAMPLE_SPAN_MS + 60_000,
        )
