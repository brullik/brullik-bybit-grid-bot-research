"""Machine-verifiable physical contract selected by the qualified Gate 1 campaign."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Final

import pyarrow as pa  # type: ignore[import-untyped]
from grid_contracts.market import Candle1m, DatasetType, FundingEvent, MarkCandle1m

EXACT_PHYSICAL_CONTRACT: Final = "grid.candle-exact-physical/v1"
CANONICAL_LAYOUT_ID: Final = "grid.canonical-candle-layout/v1"
FUNDING_EXACT_PHYSICAL_CONTRACT: Final = "grid.funding-exact-physical/v1"
FUNDING_CANONICAL_LAYOUT_ID: Final = "grid.canonical-funding-layout/v1"
NUMERIC_REPRESENTATION: Final = "hybrid_int64_decimal"
BUCKET_ALGORITHM_ID: Final = "instrument-id-modulo-v1"
BUCKET_COUNT: Final = 8
TARGET_FILE_SIZE_BYTES: Final = 16 * 1024 * 1024
COMPRESSION: Final = "zstd"
COMPRESSION_LEVEL: Final = 3
PRICE_SCALE: Final = 8
VOLUME_SCALE: Final = 4
TURNOVER_SCALE: Final = 12
FUNDING_RATE_SCALE: Final = 18
DECIMAL_PRECISION: Final = 38
UINT32_MAX: Final = (1 << 32) - 1
INT64_MIN: Final = -(1 << 63)
INT64_MAX: Final = (1 << 63) - 1
PRICE_COLUMNS: Final = ("open", "high", "low", "close")
SUPPORTED_CANDLE_TYPES: Final = frozenset({DatasetType.TRADE_KLINE_1M, DatasetType.MARK_KLINE_1M})


class PhysicalContractError(ValueError):
    """Logical market rows cannot be represented by the accepted physical contract."""


@dataclass(frozen=True, slots=True)
class CanonicalCandleBatch:
    """One sorted, unique, single-month/single-bucket canonical write unit."""

    dataset_type: DatasetType
    partition_path: PurePosixPath
    table: pa.Table

    def __post_init__(self) -> None:
        if self.dataset_type not in SUPPORTED_CANDLE_TYPES:
            raise PhysicalContractError("canonical candle batch has an unsupported dataset type")
        if self.table.num_rows <= 0:
            raise PhysicalContractError("canonical candle batch cannot be empty")
        verify_canonical_candle_schema(self.table.schema, self.dataset_type)


@dataclass(frozen=True, slots=True)
class CanonicalFundingBatch:
    """One sorted, unique, single-month/single-bucket canonical funding write unit."""

    partition_path: PurePosixPath
    table: pa.Table
    dataset_type: DatasetType = DatasetType.FUNDING_EVENT

    def __post_init__(self) -> None:
        if self.table.num_rows <= 0:
            raise PhysicalContractError("canonical funding batch cannot be empty")
        verify_canonical_funding_schema(self.table.schema)


def stable_bucket(instrument_id: int) -> int:
    """Map a stable UInt32 instrument identity exactly as the Gate 1 benchmark did."""

    if isinstance(instrument_id, bool) or not isinstance(instrument_id, int):
        raise PhysicalContractError("instrument_id must be an integer")
    if not 1 <= instrument_id <= UINT32_MAX:
        raise PhysicalContractError("instrument_id must fit unsigned 32-bit storage")
    return instrument_id % BUCKET_COUNT


def canonical_partition_path(
    dataset_type: DatasetType,
    *,
    instrument_id: int,
    open_time_ms: int,
) -> PurePosixPath:
    """Return the accepted UTC month/bucket path for a canonical candle key."""

    if dataset_type not in SUPPORTED_CANDLE_TYPES:
        raise PhysicalContractError("partition path requires a canonical candle dataset type")
    if (
        isinstance(open_time_ms, bool)
        or not isinstance(open_time_ms, int)
        or open_time_ms < 0
        or open_time_ms % 60_000
    ):
        raise PhysicalContractError("open_time_ms must be a non-negative exact UTC minute")
    try:
        timestamp = datetime.fromtimestamp(open_time_ms / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError) as error:
        raise PhysicalContractError("open_time_ms is outside the supported UTC range") from error
    return PurePosixPath(
        f"dataset={dataset_type.value}",
        "schema=v1",
        f"year={timestamp.year:04d}",
        f"month={timestamp.month:02d}",
        f"bucket={stable_bucket(instrument_id):02d}",
    )


def canonical_funding_partition_path(
    *,
    instrument_id: int,
    funding_time_ms: int,
) -> PurePosixPath:
    """Return the accepted UTC month/bucket path for a canonical funding key."""

    if (
        isinstance(funding_time_ms, bool)
        or not isinstance(funding_time_ms, int)
        or funding_time_ms < 0
        or funding_time_ms % 60_000
    ):
        raise PhysicalContractError("funding_time_ms must be a non-negative exact UTC minute")
    try:
        timestamp = datetime.fromtimestamp(funding_time_ms / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError) as error:
        raise PhysicalContractError("funding_time_ms is outside the supported UTC range") from error
    return PurePosixPath(
        f"dataset={DatasetType.FUNDING_EVENT.value}",
        "schema=v1",
        f"year={timestamp.year:04d}",
        f"month={timestamp.month:02d}",
        f"bucket={stable_bucket(instrument_id):02d}",
    )


def _price_units(name: str, value: Decimal) -> int:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise PhysicalContractError(f"{name} must be a finite positive Decimal")
    scaled = value.scaleb(PRICE_SCALE)
    if scaled != scaled.to_integral_value():
        raise PhysicalContractError(f"{name} exceeds the accepted 1e-8 price precision")
    units = int(scaled)
    if not INT64_MIN <= units <= INT64_MAX:
        raise PhysicalContractError(f"{name} exceeds signed Int64 units")
    return units


def _decimal128(name: str, value: Decimal, *, scale: int) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise PhysicalContractError(f"{name} must be a finite non-negative Decimal")
    scaled = value.scaleb(scale)
    if scaled != scaled.to_integral_value():
        raise PhysicalContractError(f"{name} exceeds the accepted scale {scale}")
    coefficient = abs(int(scaled))
    digits = 1 if coefficient == 0 else len(str(coefficient))
    if digits > DECIMAL_PRECISION:
        raise PhysicalContractError(f"{name} exceeds Decimal128({DECIMAL_PRECISION}, {scale})")
    return value


def _signed_decimal128(name: str, value: Decimal, *, scale: int) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise PhysicalContractError(f"{name} must be a finite Decimal")
    scaled = value.scaleb(scale)
    if scaled != scaled.to_integral_value():
        raise PhysicalContractError(f"{name} exceeds the accepted scale {scale}")
    coefficient = abs(int(scaled))
    digits = 1 if coefficient == 0 else len(str(coefficient))
    if digits > DECIMAL_PRECISION:
        raise PhysicalContractError(f"{name} exceeds Decimal128({DECIMAL_PRECISION}, {scale})")
    return value


def _price_field(name: str) -> pa.Field:
    return pa.field(
        name,
        pa.int64(),
        nullable=False,
        metadata={
            b"grid.logical_type": b"decimal",
            b"grid.scale": str(PRICE_SCALE).encode("ascii"),
            b"grid.unit": b"1e-8",
        },
    )


def canonical_candle_schema(dataset_type: DatasetType) -> pa.Schema:
    """Build the full Arrow schema and metadata required for canonical candle files."""

    if dataset_type not in SUPPORTED_CANDLE_TYPES:
        raise PhysicalContractError("canonical schema requires a candle dataset type")
    fields = [
        pa.field("category", pa.string(), nullable=False),
        pa.field("instrument_id", pa.uint32(), nullable=False),
        pa.field("open_time_ms", pa.int64(), nullable=False),
        *(_price_field(name) for name in PRICE_COLUMNS),
    ]
    if dataset_type is DatasetType.TRADE_KLINE_1M:
        fields.extend(
            (
                pa.field(
                    "volume",
                    pa.decimal128(DECIMAL_PRECISION, VOLUME_SCALE),
                    nullable=False,
                ),
                pa.field(
                    "turnover",
                    pa.decimal128(DECIMAL_PRECISION, TURNOVER_SCALE),
                    nullable=False,
                ),
            )
        )
    fields.extend(
        (
            pa.field("source_id", pa.string(), nullable=False),
            pa.field("ingestion_id", pa.string(), nullable=False),
            pa.field("quality_flags", pa.uint32(), nullable=False),
        )
    )
    return pa.schema(
        fields,
        metadata={
            b"grid.bucket_algorithm": BUCKET_ALGORITHM_ID.encode("ascii"),
            b"grid.bucket_count": str(BUCKET_COUNT).encode("ascii"),
            b"grid.compression": COMPRESSION.encode("ascii"),
            b"grid.compression_level": str(COMPRESSION_LEVEL).encode("ascii"),
            b"grid.dataset_type": dataset_type.value.encode("ascii"),
            b"grid.layout_contract": CANONICAL_LAYOUT_ID.encode("ascii"),
            b"grid.numeric_contract": EXACT_PHYSICAL_CONTRACT.encode("ascii"),
            b"grid.numeric_representation": NUMERIC_REPRESENTATION.encode("ascii"),
            b"grid.sort_order": b"instrument_id,open_time_ms",
            b"grid.target_file_size_bytes": str(TARGET_FILE_SIZE_BYTES).encode("ascii"),
        },
    )


def verify_canonical_candle_schema(schema: pa.Schema, dataset_type: DatasetType) -> None:
    expected = canonical_candle_schema(dataset_type)
    if not schema.equals(expected, check_metadata=True):
        raise PhysicalContractError("Arrow schema or canonical layout metadata does not match")


def canonical_funding_schema() -> pa.Schema:
    """Build the full Arrow schema and metadata required for canonical funding files."""

    return pa.schema(
        (
            pa.field("category", pa.string(), nullable=False),
            pa.field("instrument_id", pa.uint32(), nullable=False),
            pa.field("funding_time_ms", pa.int64(), nullable=False),
            pa.field(
                "funding_rate",
                pa.decimal128(DECIMAL_PRECISION, FUNDING_RATE_SCALE),
                nullable=False,
            ),
            pa.field("funding_interval_minutes", pa.uint32(), nullable=False),
            pa.field("source_id", pa.string(), nullable=False),
            pa.field("ingestion_id", pa.string(), nullable=False),
            pa.field("quality_flags", pa.uint32(), nullable=False),
        ),
        metadata={
            b"grid.bucket_algorithm": BUCKET_ALGORITHM_ID.encode("ascii"),
            b"grid.bucket_count": str(BUCKET_COUNT).encode("ascii"),
            b"grid.compression": COMPRESSION.encode("ascii"),
            b"grid.compression_level": str(COMPRESSION_LEVEL).encode("ascii"),
            b"grid.dataset_type": DatasetType.FUNDING_EVENT.value.encode("ascii"),
            b"grid.funding_interval_semantics": b"elapsed-minutes-since-previous-settlement",
            b"grid.funding_rate_scale": str(FUNDING_RATE_SCALE).encode("ascii"),
            b"grid.layout_contract": FUNDING_CANONICAL_LAYOUT_ID.encode("ascii"),
            b"grid.numeric_contract": FUNDING_EXACT_PHYSICAL_CONTRACT.encode("ascii"),
            b"grid.numeric_representation": b"decimal128",
            b"grid.sort_order": b"instrument_id,funding_time_ms",
            b"grid.target_file_size_bytes": str(TARGET_FILE_SIZE_BYTES).encode("ascii"),
        },
    )


def verify_canonical_funding_schema(schema: pa.Schema) -> None:
    if not schema.equals(canonical_funding_schema(), check_metadata=True):
        raise PhysicalContractError(
            "Arrow schema or canonical funding layout metadata does not match"
        )


def _ordered_unique_rows(
    rows: Sequence[Candle1m | MarkCandle1m], dataset_type: DatasetType
) -> tuple[Candle1m | MarkCandle1m, ...]:
    if not rows:
        raise PhysicalContractError("cannot build a canonical batch from no rows")
    expected_class = Candle1m if dataset_type is DatasetType.TRADE_KLINE_1M else MarkCandle1m
    if any(not isinstance(row, expected_class) for row in rows):
        raise PhysicalContractError("logical row class does not match dataset_type")
    ordered = tuple(sorted(rows, key=lambda row: (row.instrument_id, row.open_time_ms)))
    keys = [(row.instrument_id, row.open_time_ms) for row in ordered]
    if len(keys) != len(set(keys)):
        raise PhysicalContractError("duplicate canonical candle key")
    return ordered


def build_canonical_candle_batch(
    rows: Sequence[Candle1m | MarkCandle1m],
    dataset_type: DatasetType,
) -> CanonicalCandleBatch:
    """Validate and convert logical candle rows without filesystem mutation."""

    if dataset_type not in SUPPORTED_CANDLE_TYPES:
        raise PhysicalContractError("canonical batch requires a candle dataset type")
    ordered = _ordered_unique_rows(rows, dataset_type)
    if any(
        isinstance(row.quality_flags, bool)
        or not isinstance(row.quality_flags, int)
        or not 0 <= row.quality_flags <= UINT32_MAX
        for row in ordered
    ):
        raise PhysicalContractError("quality_flags must fit unsigned 32-bit storage")
    partitions = {
        canonical_partition_path(
            dataset_type,
            instrument_id=row.instrument_id,
            open_time_ms=row.open_time_ms,
        )
        for row in ordered
    }
    if len(partitions) != 1:
        raise PhysicalContractError("one canonical batch must fit exactly one month/bucket")
    arrays: list[pa.Array] = [
        pa.array([row.category for row in ordered], type=pa.string()),
        pa.array([row.instrument_id for row in ordered], type=pa.uint32()),
        pa.array([row.open_time_ms for row in ordered], type=pa.int64()),
    ]
    for name in PRICE_COLUMNS:
        arrays.append(
            pa.array([_price_units(name, getattr(row, name)) for row in ordered], type=pa.int64())
        )
    if dataset_type is DatasetType.TRADE_KLINE_1M:
        trade_rows = tuple(row for row in ordered if isinstance(row, Candle1m))
        arrays.extend(
            (
                pa.array(
                    [_decimal128("volume", row.volume, scale=VOLUME_SCALE) for row in trade_rows],
                    type=pa.decimal128(DECIMAL_PRECISION, VOLUME_SCALE),
                ),
                pa.array(
                    [
                        _decimal128("turnover", row.turnover, scale=TURNOVER_SCALE)
                        for row in trade_rows
                    ],
                    type=pa.decimal128(DECIMAL_PRECISION, TURNOVER_SCALE),
                ),
            )
        )
    arrays.extend(
        (
            pa.array([row.source_id for row in ordered], type=pa.string()),
            pa.array([row.ingestion_id for row in ordered], type=pa.string()),
            pa.array([row.quality_flags for row in ordered], type=pa.uint32()),
        )
    )
    table = pa.Table.from_arrays(arrays, schema=canonical_candle_schema(dataset_type))
    return CanonicalCandleBatch(
        dataset_type=dataset_type,
        partition_path=next(iter(partitions)),
        table=table,
    )


def build_canonical_funding_batch(rows: Sequence[FundingEvent]) -> CanonicalFundingBatch:
    """Validate and convert logical funding rows without filesystem mutation."""

    if not rows:
        raise PhysicalContractError("cannot build a canonical funding batch from no rows")
    if any(not isinstance(row, FundingEvent) for row in rows):
        raise PhysicalContractError("canonical funding rows must be FundingEvent values")
    ordered = tuple(sorted(rows, key=lambda row: (row.instrument_id, row.funding_time_ms)))
    keys = [(row.instrument_id, row.funding_time_ms) for row in ordered]
    if len(keys) != len(set(keys)):
        raise PhysicalContractError("duplicate canonical funding key")
    if any(
        isinstance(row.quality_flags, bool)
        or not isinstance(row.quality_flags, int)
        or not 0 <= row.quality_flags <= UINT32_MAX
        for row in ordered
    ):
        raise PhysicalContractError("quality_flags must fit unsigned 32-bit storage")
    if any(
        isinstance(row.funding_interval_minutes, bool)
        or not isinstance(row.funding_interval_minutes, int)
        or not 1 <= row.funding_interval_minutes <= UINT32_MAX
        for row in ordered
    ):
        raise PhysicalContractError("funding_interval_minutes must fit positive UInt32 storage")
    previous_by_instrument: dict[int, FundingEvent] = {}
    for row in ordered:
        previous = previous_by_instrument.get(row.instrument_id)
        if previous is not None:
            elapsed_ms = row.funding_time_ms - previous.funding_time_ms
            if elapsed_ms != row.funding_interval_minutes * 60_000:
                raise PhysicalContractError(
                    "funding interval does not match the previous settlement timestamp"
                )
        previous_by_instrument[row.instrument_id] = row
    partitions = {
        canonical_funding_partition_path(
            instrument_id=row.instrument_id,
            funding_time_ms=row.funding_time_ms,
        )
        for row in ordered
    }
    if len(partitions) != 1:
        raise PhysicalContractError("one canonical funding batch must fit one month/bucket")
    table = pa.Table.from_arrays(
        (
            pa.array([row.category for row in ordered], type=pa.string()),
            pa.array([row.instrument_id for row in ordered], type=pa.uint32()),
            pa.array([row.funding_time_ms for row in ordered], type=pa.int64()),
            pa.array(
                [
                    _signed_decimal128("funding_rate", row.funding_rate, scale=FUNDING_RATE_SCALE)
                    for row in ordered
                ],
                type=pa.decimal128(DECIMAL_PRECISION, FUNDING_RATE_SCALE),
            ),
            pa.array(
                [row.funding_interval_minutes for row in ordered],
                type=pa.uint32(),
            ),
            pa.array([row.source_id for row in ordered], type=pa.string()),
            pa.array([row.ingestion_id for row in ordered], type=pa.string()),
            pa.array([row.quality_flags for row in ordered], type=pa.uint32()),
        ),
        schema=canonical_funding_schema(),
    )
    return CanonicalFundingBatch(
        partition_path=next(iter(partitions)),
        table=table,
    )
