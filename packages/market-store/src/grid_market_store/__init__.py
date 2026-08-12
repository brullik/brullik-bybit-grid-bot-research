"""Canonical market-store physical contracts; no network or live dependencies."""

from grid_market_store.physical import (
    BUCKET_ALGORITHM_ID,
    BUCKET_COUNT,
    CANONICAL_LAYOUT_ID,
    COMPRESSION,
    COMPRESSION_LEVEL,
    EXACT_PHYSICAL_CONTRACT,
    NUMERIC_REPRESENTATION,
    PRICE_SCALE,
    TARGET_FILE_SIZE_BYTES,
    TURNOVER_SCALE,
    VOLUME_SCALE,
    CanonicalCandleBatch,
    PhysicalContractError,
    build_canonical_candle_batch,
    canonical_candle_schema,
    canonical_partition_path,
    stable_bucket,
    verify_canonical_candle_schema,
)

__all__ = [
    "BUCKET_ALGORITHM_ID",
    "BUCKET_COUNT",
    "CANONICAL_LAYOUT_ID",
    "COMPRESSION",
    "COMPRESSION_LEVEL",
    "EXACT_PHYSICAL_CONTRACT",
    "NUMERIC_REPRESENTATION",
    "PRICE_SCALE",
    "TARGET_FILE_SIZE_BYTES",
    "TURNOVER_SCALE",
    "VOLUME_SCALE",
    "CanonicalCandleBatch",
    "PhysicalContractError",
    "build_canonical_candle_batch",
    "canonical_candle_schema",
    "canonical_partition_path",
    "stable_bucket",
    "verify_canonical_candle_schema",
]

__version__ = "0.2.0"
