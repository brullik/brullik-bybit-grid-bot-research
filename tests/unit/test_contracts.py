from __future__ import annotations

from decimal import Decimal

import pytest
from grid_contracts.canonical import CanonicalizationError, canonical_json_bytes
from grid_contracts.market import Candle1m, ContractViolation, FundingEvent


def candle(**overrides: object) -> Candle1m:
    values: dict[str, object] = {
        "category": "linear",
        "instrument_id": 1,
        "open_time_ms": 1_700_000_040_000,
        "open": Decimal("100.00"),
        "high": Decimal("102.00"),
        "low": Decimal("99.00"),
        "close": Decimal("101.00"),
        "volume": Decimal("10.5"),
        "turnover": Decimal("1050"),
        "source_id": "fixture",
        "ingestion_id": "test-run",
    }
    values.update(overrides)
    return Candle1m(**values)  # type: ignore[arg-type]


def test_canonical_json_normalizes_decimals_and_keys() -> None:
    assert canonical_json_bytes({"z": Decimal("1.00"), "a": 2}) == b'{"a":2,"z":"1"}'


def test_canonical_json_rejects_binary_float() -> None:
    with pytest.raises(CanonicalizationError, match="binary floating-point"):
        canonical_json_bytes({"price": 0.1})


def test_candle_accepts_exact_minute_and_ohlc_invariants() -> None:
    assert candle().close == Decimal("101.00")


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"open_time_ms": 1_700_000_040_001}, "aligned"),
        ({"low": Decimal("103")}, "low exceeds high"),
        ({"open": Decimal("0")}, "open must be positive"),
        ({"volume": Decimal("-1")}, "non-negative"),
    ],
)
def test_candle_fails_closed(overrides: dict[str, object], expected: str) -> None:
    with pytest.raises(ContractViolation, match=expected):
        candle(**overrides)


def test_funding_event_requires_an_exact_utc_minute() -> None:
    values = {
        "category": "linear",
        "instrument_id": 1,
        "funding_time_ms": 1_700_000_040_000,
        "funding_rate": Decimal("-0.0001"),
        "funding_interval_minutes": 480,
        "source_id": "fixture",
        "ingestion_id": "test-run",
    }
    assert FundingEvent(**values).funding_rate == Decimal("-0.0001")  # type: ignore[arg-type]
    values["funding_time_ms"] = 1_700_000_040_001
    with pytest.raises(ContractViolation, match="funding timestamp"):
        FundingEvent(**values)  # type: ignore[arg-type]
