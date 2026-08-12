"""Bounded public sample evidence for trade, mark, and funding contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from typing import Any

from grid_bybit_public import BybitPublicClient
from grid_contracts.canonical import canonical_sha256, decimal_text
from grid_contracts.market import MINUTE_MS

MAX_SAMPLE_SPAN_MS = 31 * 24 * 60 * MINUTE_MS


def build_public_sample(
    client: BybitPublicClient,
    *,
    symbol: str,
    start_ms: int,
    end_ms: int,
) -> dict[str, Any]:
    _validate_request(symbol, start_ms, end_ms)
    instrument = client.instrument(symbol=symbol)
    funding_interval_minutes = _required_positive_int(instrument, "fundingInterval")
    launch_time_ms = _required_non_negative_int(instrument, "launchTime")
    if start_ms < launch_time_ms:
        raise ValueError("sample starts before the current instrument launch timestamp")
    if (
        instrument.get("contractType") != "LinearPerpetual"
        or instrument.get("settleCoin") != "USDT"
    ):
        raise ValueError("public sample requires a linear USDT perpetual instrument")
    trade_rows = tuple(
        client.iter_klines_backward(kind="trade", symbol=symbol, start_ms=start_ms, end_ms=end_ms)
    )
    mark_rows = tuple(
        client.iter_klines_backward(kind="mark", symbol=symbol, start_ms=start_ms, end_ms=end_ms)
    )
    funding_items = tuple(
        client.iter_funding_backward(symbol=symbol, start_ms=start_ms, end_ms=end_ms)
    )

    normalized_trade = tuple(_normalize_trade(row) for row in trade_rows)
    normalized_mark = tuple(_normalize_mark(row) for row in mark_rows)
    normalized_funding = tuple(_normalize_funding(item, symbol) for item in funding_items)
    datasets = {
        "funding_event": _periodic_summary(
            normalized_funding, start_ms, end_ms, funding_interval_minutes
        ),
        "mark_kline_1m": _candle_summary(normalized_mark, start_ms, end_ms),
        "trade_kline_1m": _candle_summary(normalized_trade, start_ms, end_ms),
    }
    evidence: dict[str, Any] = {
        "datasets": datasets,
        "evidence_schema": "grid.bybit-public-sample/v1",
        "fetched_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "request": {
            "category": "linear",
            "end_ms": end_ms,
            "funding_interval_minutes": funding_interval_minutes,
            "instrument_metadata_sha256": canonical_sha256(instrument),
            "instrument_metadata_source": "/v5/market/instruments-info",
            "start_ms": start_ms,
            "symbol": symbol,
        },
        "sample_status": "complete"
        if all(
            item["row_count"] and item["missing_expected_timestamp_count"] == 0
            for item in datasets.values()
        )
        else "partial",
        "storage_policy": "summary-and-content-hash-only; raw market rows are not committed",
    }
    evidence["content_sha256"] = canonical_sha256(evidence)
    return evidence


def _validate_request(symbol: str, start_ms: int, end_ms: int) -> None:
    if not symbol or symbol != symbol.upper() or not symbol.isalnum():
        raise ValueError("symbol must be non-empty uppercase alphanumeric text")
    if start_ms < 0 or end_ms < start_ms:
        raise ValueError("invalid sample time range")
    if start_ms % MINUTE_MS or end_ms % MINUTE_MS:
        raise ValueError("sample time bounds must be aligned to UTC minutes")
    if end_ms - start_ms > MAX_SAMPLE_SPAN_MS:
        raise ValueError("public sample range may not exceed 31 days")


def _normalize_trade(row: Sequence[str]) -> dict[str, Any]:
    timestamp, open_, high, low, close, volume, turnover = row
    normalized = _normalize_candle(timestamp, open_, high, low, close)
    normalized["turnover"] = _non_negative_decimal("turnover", turnover)
    normalized["volume"] = _non_negative_decimal("volume", volume)
    return normalized


def _normalize_mark(row: Sequence[str]) -> dict[str, Any]:
    timestamp, open_, high, low, close = row
    return _normalize_candle(timestamp, open_, high, low, close)


def _normalize_candle(
    timestamp: str, open_: str, high: str, low: str, close: str
) -> dict[str, Any]:
    open_time_ms = _non_negative_int("open_time_ms", timestamp)
    if open_time_ms % MINUTE_MS:
        raise ValueError("Bybit returned a candle not aligned to a UTC minute")
    prices = {
        "close": _positive_decimal("close", close),
        "high": _positive_decimal("high", high),
        "low": _positive_decimal("low", low),
        "open": _positive_decimal("open", open_),
    }
    if prices["low"] > prices["high"]:
        raise ValueError("candle low exceeds high")
    if any(
        prices[name] < prices["low"] or prices[name] > prices["high"] for name in ("open", "close")
    ):
        raise ValueError("candle open/close lies outside low/high")
    return {"open_time_ms": open_time_ms, **prices}


def _normalize_funding(item: Mapping[str, Any], expected_symbol: str) -> dict[str, Any]:
    symbol = item.get("symbol")
    if symbol != expected_symbol:
        raise ValueError("funding event symbol does not match the request")
    rate = item.get("fundingRate")
    timestamp = item.get("fundingRateTimestamp")
    if not isinstance(rate, str) or not isinstance(timestamp, str):
        raise ValueError("funding rate and timestamp must be text")
    return {
        "funding_rate": _decimal("funding_rate", rate),
        "funding_time_ms": _non_negative_int("funding_time_ms", timestamp),
    }


def _candle_summary(
    rows: Sequence[Mapping[str, Any]], start_ms: int, end_ms: int
) -> dict[str, Any]:
    timestamps = tuple(_timestamp(row, "open_time_ms") for row in rows)
    result = _summary(
        rows,
        timestamps,
        expected_timestamps=range(start_ms, end_ms + 1, MINUTE_MS),
        start_ms=start_ms,
        end_ms=end_ms,
    )
    result["coverage_semantics"] = "full-inclusive-request-range"
    return result


def _periodic_summary(
    rows: Sequence[Mapping[str, Any]],
    start_ms: int,
    end_ms: int,
    funding_interval_minutes: int,
) -> dict[str, Any]:
    timestamps = tuple(_timestamp(row, "funding_time_ms") for row in rows)
    _validate_timestamps(timestamps, start_ms, end_ms)
    expected_step_ms = funding_interval_minutes * MINUTE_MS
    missing_count = 0
    missing_sample: list[int] = []
    for newer, older in pairwise(timestamps):
        gap_count = max(0, (newer - older - 1) // expected_step_ms)
        missing_count += gap_count
        for offset in range(1, min(gap_count, 20 - len(missing_sample)) + 1):
            missing_sample.append(newer - offset * expected_step_ms)
    result = _summary_payload(rows, timestamps, start_ms, end_ms, missing_count, missing_sample)
    result["coverage_semantics"] = "internal-intervals; schedule phase inferred from events"
    return result


def _summary(
    rows: Sequence[Mapping[str, Any]],
    timestamps: Sequence[int],
    *,
    expected_timestamps: range,
    start_ms: int,
    end_ms: int,
) -> dict[str, Any]:
    _validate_timestamps(timestamps, start_ms, end_ms)
    actual = set(timestamps)
    missing_count = 0
    missing_sample: list[int] = []
    for expected in expected_timestamps:
        if expected in actual:
            continue
        missing_count += 1
        if len(missing_sample) < 20:
            missing_sample.append(expected)
    return _summary_payload(rows, timestamps, start_ms, end_ms, missing_count, missing_sample)


def _validate_timestamps(timestamps: Sequence[int], start_ms: int, end_ms: int) -> None:
    if timestamps != tuple(sorted(timestamps, reverse=True)) or len(timestamps) != len(
        set(timestamps)
    ):
        raise ValueError("normalized sample must be unique reverse chronological data")
    if any(timestamp < start_ms or timestamp > end_ms for timestamp in timestamps):
        raise ValueError("Bybit returned data outside the requested range")


def _summary_payload(
    rows: Sequence[Mapping[str, Any]],
    timestamps: Sequence[int],
    start_ms: int,
    end_ms: int,
    missing_count: int,
    missing_sample: Sequence[int],
) -> dict[str, Any]:
    return {
        "content_sha256": canonical_sha256(rows),
        "duplicate_timestamp_count": len(timestamps) - len(set(timestamps)),
        "first_time_ms": timestamps[-1] if timestamps else None,
        "last_time_ms": timestamps[0] if timestamps else None,
        "missing_expected_timestamp_count": missing_count,
        "missing_expected_timestamps_sample": list(missing_sample),
        "requested_end_ms": end_ms,
        "requested_start_ms": start_ms,
        "row_count": len(rows),
    }


def _timestamp(row: Mapping[str, Any], name: str) -> int:
    value = row.get(name)
    if not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _decimal(name: str, value: str) -> str:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{name} must be decimal text") from error
    if not parsed.is_finite():
        raise ValueError(f"{name} must be finite")
    return decimal_text(parsed)


def _positive_decimal(name: str, value: str) -> str:
    result = _decimal(name, value)
    if Decimal(result) <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def _non_negative_decimal(name: str, value: str) -> str:
    result = _decimal(name, value)
    if Decimal(result) < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _non_negative_int(name: str, value: str) -> int:
    try:
        result = int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be integer text") from error
    if result < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _required_positive_int(item: Mapping[str, Any], key: str) -> int:
    value = item.get(key)
    if isinstance(value, bool) or not isinstance(value, str | int):
        raise ValueError(f"instrument {key} must be integer-compatible")
    result = _non_negative_int(key, str(value))
    if result <= 0:
        raise ValueError(f"instrument {key} must be positive")
    return result


def _required_non_negative_int(item: Mapping[str, Any], key: str) -> int:
    value = item.get(key)
    if isinstance(value, bool) or not isinstance(value, str | int):
        raise ValueError(f"instrument {key} must be integer-compatible")
    return _non_negative_int(key, str(value))
