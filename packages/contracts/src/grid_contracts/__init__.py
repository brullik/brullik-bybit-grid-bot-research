"""Stable, dependency-free contracts shared by deployable applications."""

from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file
from grid_contracts.market import (
    Candle1m,
    CompletionReceipt,
    DatasetFile,
    DatasetManifest,
    DatasetStatus,
    DatasetType,
    FundingEvent,
    InstrumentSnapshot,
    MarkCandle1m,
)

__all__ = [
    "Candle1m",
    "CompletionReceipt",
    "DatasetFile",
    "DatasetManifest",
    "DatasetStatus",
    "DatasetType",
    "FundingEvent",
    "InstrumentSnapshot",
    "MarkCandle1m",
    "canonical_json_bytes",
    "canonical_sha256",
    "sha256_file",
]

__version__ = "0.2.0"
