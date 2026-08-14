from __future__ import annotations

from decimal import Decimal

import pyarrow as pa  # type: ignore[import-untyped]
import pytest
from grid_contracts.market import Candle1m, DatasetType, FundingEvent, MarkCandle1m
from grid_market_store.physical import (
    BUCKET_COUNT,
    CANONICAL_LAYOUT_ID,
    FUNDING_CANONICAL_LAYOUT_ID,
    FUNDING_RATE_SCALE,
    PhysicalContractError,
    build_canonical_candle_batch,
    build_canonical_funding_batch,
    build_preordered_canonical_candle_batch,
    canonical_candle_schema,
    canonical_funding_partition_path,
    canonical_partition_path,
    stable_bucket,
    verify_canonical_candle_schema,
)


def trade_candle(**overrides: object) -> Candle1m:
    values: dict[str, object] = {
        "category": "linear",
        "instrument_id": 9,
        "open_time_ms": 1_767_225_600_000,
        "open": Decimal("100.00000001"),
        "high": Decimal("102"),
        "low": Decimal("99.5"),
        "close": Decimal("101"),
        "volume": Decimal("10.5000"),
        "turnover": Decimal("1050.000000000001"),
        "source_id": "bybit-v5-kline",
        "ingestion_id": "fixture-run",
        "quality_flags": 0,
    }
    values.update(overrides)
    return Candle1m(**values)  # type: ignore[arg-type]


def mark_candle(**overrides: object) -> MarkCandle1m:
    trade = trade_candle(**overrides)
    return MarkCandle1m(
        category=trade.category,
        instrument_id=trade.instrument_id,
        open_time_ms=trade.open_time_ms,
        open=trade.open,
        high=trade.high,
        low=trade.low,
        close=trade.close,
        source_id="bybit-v5-mark-price-kline",
        ingestion_id=trade.ingestion_id,
        quality_flags=trade.quality_flags,
    )


def funding_event(**overrides: object) -> FundingEvent:
    values: dict[str, object] = {
        "category": "linear",
        "instrument_id": 9,
        "funding_time_ms": 1_767_225_600_000,
        "funding_rate": Decimal("-0.000012345678901234"),
        "funding_interval_minutes": 480,
        "source_id": "bybit-v5-funding-history/v1",
        "ingestion_id": "fixture-run",
        "quality_flags": 0,
    }
    values.update(overrides)
    return FundingEvent(**values)  # type: ignore[arg-type]


def test_stable_bucket_matches_qualified_modulo_layout() -> None:
    assert BUCKET_COUNT == 8
    assert stable_bucket(1) == 1
    assert stable_bucket(8) == 0
    assert stable_bucket(9) == 1


@pytest.mark.parametrize("instrument_id", [0, -1, 1 << 32, True])
def test_stable_bucket_rejects_non_uint32_identity(instrument_id: object) -> None:
    with pytest.raises(PhysicalContractError, match="instrument_id"):
        stable_bucket(instrument_id)  # type: ignore[arg-type]


def test_partition_path_is_utc_month_and_stable_bucket() -> None:
    assert (
        canonical_partition_path(
            DatasetType.TRADE_KLINE_1M,
            instrument_id=9,
            open_time_ms=1_767_225_600_000,
        ).as_posix()
        == "dataset=trade_kline_1m/schema=v1/year=2026/month=01/bucket=01"
    )


def test_partition_path_rejects_timestamp_outside_supported_utc_range() -> None:
    with pytest.raises(PhysicalContractError, match="supported UTC range"):
        canonical_partition_path(
            DatasetType.TRADE_KLINE_1M,
            instrument_id=9,
            open_time_ms=((1 << 63) - 1) // 60_000 * 60_000,
        )


def test_trade_batch_sorts_rows_and_preserves_exact_physical_types() -> None:
    first = trade_candle()
    second = trade_candle(open_time_ms=first.open_time_ms + 60_000)
    batch = build_canonical_candle_batch((second, first), DatasetType.TRADE_KLINE_1M)

    assert batch.table.column("open_time_ms").to_pylist() == [
        first.open_time_ms,
        second.open_time_ms,
    ]
    assert batch.table.column("open").to_pylist() == [10_000_000_001, 10_000_000_001]
    assert batch.table.schema.field("volume").type == pa.decimal128(38, 4)
    assert batch.table.schema.field("turnover").type == pa.decimal128(38, 12)
    assert batch.table.schema.metadata[b"grid.layout_contract"] == CANONICAL_LAYOUT_ID.encode()
    verify_canonical_candle_schema(batch.table.schema, DatasetType.TRADE_KLINE_1M)


def test_preordered_trade_batch_is_exactly_equivalent_and_fails_closed_on_order() -> None:
    first = trade_candle()
    second = trade_candle(open_time_ms=first.open_time_ms + 60_000)
    reference = build_canonical_candle_batch((second, first), DatasetType.TRADE_KLINE_1M)
    preordered = build_preordered_canonical_candle_batch(
        (first, second),
        DatasetType.TRADE_KLINE_1M,
    )

    assert preordered.partition_path == reference.partition_path
    assert preordered.table.equals(reference.table, check_metadata=True)
    with pytest.raises(PhysicalContractError, match="not preordered"):
        build_preordered_canonical_candle_batch(
            (second, first),
            DatasetType.TRADE_KLINE_1M,
        )
    with pytest.raises(PhysicalContractError, match="duplicate"):
        build_preordered_canonical_candle_batch(
            (first, first),
            DatasetType.TRADE_KLINE_1M,
        )


def test_mark_batch_has_no_trade_only_columns() -> None:
    batch = build_canonical_candle_batch((mark_candle(),), DatasetType.MARK_KLINE_1M)
    assert "volume" not in batch.table.column_names
    assert "turnover" not in batch.table.column_names


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"open": Decimal("100.000000001")}, "1e-8"),
        ({"volume": Decimal("1.00001")}, "scale 4"),
        ({"turnover": Decimal("1.0000000000001")}, "scale 12"),
    ],
)
def test_trade_batch_never_rounds_to_fit(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(PhysicalContractError, match=message):
        build_canonical_candle_batch((trade_candle(**overrides),), DatasetType.TRADE_KLINE_1M)


def test_batch_rejects_duplicate_keys_and_cross_partition_rows() -> None:
    candle = trade_candle()
    with pytest.raises(PhysicalContractError, match="duplicate"):
        build_canonical_candle_batch((candle, candle), DatasetType.TRADE_KLINE_1M)

    next_month = trade_candle(open_time_ms=1_769_904_000_000)
    with pytest.raises(PhysicalContractError, match="one month/bucket"):
        build_canonical_candle_batch((candle, next_month), DatasetType.TRADE_KLINE_1M)


def test_batch_rejects_logical_dataset_mismatch() -> None:
    with pytest.raises(PhysicalContractError, match="row class"):
        build_canonical_candle_batch((mark_candle(),), DatasetType.TRADE_KLINE_1M)


def test_batch_rejects_quality_flags_outside_uint32() -> None:
    with pytest.raises(PhysicalContractError, match="quality_flags"):
        build_canonical_candle_batch(
            (trade_candle(quality_flags=1 << 32),),
            DatasetType.TRADE_KLINE_1M,
        )


def test_schema_verifier_rejects_missing_layout_metadata() -> None:
    schema = canonical_candle_schema(DatasetType.TRADE_KLINE_1M).remove_metadata()
    with pytest.raises(PhysicalContractError, match="metadata"):
        verify_canonical_candle_schema(schema, DatasetType.TRADE_KLINE_1M)


def test_funding_batch_sorts_and_preserves_exact_rate_and_interval() -> None:
    first = funding_event()
    second = funding_event(
        funding_time_ms=first.funding_time_ms + 480 * 60_000,
        funding_rate=Decimal("0.000000000000000001"),
    )
    batch = build_canonical_funding_batch((second, first))

    assert batch.dataset_type is DatasetType.FUNDING_EVENT
    assert batch.partition_path == canonical_funding_partition_path(
        instrument_id=9,
        funding_time_ms=first.funding_time_ms,
    )
    assert batch.table.column("funding_time_ms").to_pylist() == [
        first.funding_time_ms,
        second.funding_time_ms,
    ]
    assert batch.table.column("funding_rate").to_pylist() == [
        first.funding_rate,
        second.funding_rate,
    ]
    assert batch.table.schema.field("funding_rate").type == pa.decimal128(38, FUNDING_RATE_SCALE)
    assert (
        batch.table.schema.metadata[b"grid.layout_contract"] == FUNDING_CANONICAL_LAYOUT_ID.encode()
    )


def test_funding_batch_rejects_rounding_duplicates_and_interval_mismatch() -> None:
    with pytest.raises(PhysicalContractError, match="scale 18"):
        build_canonical_funding_batch(
            (funding_event(funding_rate=Decimal("0.0000000000000000001")),)
        )
    event = funding_event()
    with pytest.raises(PhysicalContractError, match="duplicate"):
        build_canonical_funding_batch((event, event))
    with pytest.raises(PhysicalContractError, match="previous settlement"):
        build_canonical_funding_batch(
            (
                event,
                funding_event(
                    funding_time_ms=event.funding_time_ms + 240 * 60_000,
                    funding_interval_minutes=480,
                ),
            )
        )


def test_funding_batch_requires_one_month_bucket_and_minute_aligned_time() -> None:
    event = funding_event()
    with pytest.raises(PhysicalContractError, match="one month/bucket"):
        build_canonical_funding_batch(
            (
                event,
                funding_event(
                    funding_time_ms=1_769_904_000_000,
                    funding_interval_minutes=44_640,
                ),
            )
        )
    with pytest.raises(ValueError, match="funding timestamp"):
        funding_event(funding_time_ms=event.funding_time_ms + 1)
