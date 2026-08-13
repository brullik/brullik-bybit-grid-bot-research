"""Canonical market dataset value objects and fail-closed invariants."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from pathlib import PurePosixPath

MINUTE_MS = 60_000
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ContractViolation(ValueError):
    """A persisted contract value violates a schema or semantic invariant."""


class DatasetType(StrEnum):
    INSTRUMENT_SNAPSHOT = "instrument_snapshot"
    TRADE_KLINE_1M = "trade_kline_1m"
    MARK_KLINE_1M = "mark_kline_1m"
    FUNDING_EVENT = "funding_event"


class DatasetStatus(StrEnum):
    BUILDING = "building"
    FAILED = "failed"
    COMPLETE = "complete"


def _require_nonempty(name: str, value: str) -> None:
    if not value or value.strip() != value:
        raise ContractViolation(f"{name} must be non-empty and trimmed")


def _require_decimal(name: str, value: Decimal, *, positive: bool = False) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ContractViolation(f"{name} must be a finite Decimal")
    if positive and value <= 0:
        raise ContractViolation(f"{name} must be positive")


def _require_sha256(name: str, value: str) -> None:
    if not SHA256_RE.fullmatch(value):
        raise ContractViolation(f"{name} must be a lowercase SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class InstrumentSnapshot:
    snapshot_time_ms: int
    category: str
    instrument_id: int
    source_symbol_id: int
    symbol: str
    contract_type: str
    status: str
    base_coin: str
    quote_coin: str
    settle_coin: str
    launch_time_ms: int
    delivery_time_ms: int | None
    tick_size: Decimal
    quantity_step: Decimal
    min_order_quantity: Decimal
    max_order_quantity: Decimal
    min_leverage: Decimal
    max_leverage: Decimal
    funding_interval_minutes: int | None
    source_payload_sha256: str

    def __post_init__(self) -> None:
        if self.snapshot_time_ms < 0 or self.launch_time_ms < 0:
            raise ContractViolation("timestamps must be non-negative Unix milliseconds")
        if self.instrument_id <= 0 or self.source_symbol_id <= 0:
            raise ContractViolation("instrument identities must be positive")
        for name in (
            "category",
            "symbol",
            "contract_type",
            "status",
            "base_coin",
            "quote_coin",
            "settle_coin",
        ):
            _require_nonempty(name, getattr(self, name))
        for name in (
            "tick_size",
            "quantity_step",
            "min_order_quantity",
            "max_order_quantity",
            "min_leverage",
            "max_leverage",
        ):
            _require_decimal(name, getattr(self, name), positive=True)
        if self.min_order_quantity > self.max_order_quantity:
            raise ContractViolation("min_order_quantity exceeds max_order_quantity")
        if self.min_leverage > self.max_leverage:
            raise ContractViolation("min_leverage exceeds max_leverage")
        if self.delivery_time_ms is not None and self.delivery_time_ms < self.launch_time_ms:
            raise ContractViolation("delivery time precedes launch time")
        if self.funding_interval_minutes is not None and self.funding_interval_minutes <= 0:
            raise ContractViolation("funding interval must be positive")
        _require_sha256("source_payload_sha256", self.source_payload_sha256)


@dataclass(frozen=True, slots=True)
class Candle1m:
    category: str
    instrument_id: int
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    turnover: Decimal
    source_id: str
    ingestion_id: str
    quality_flags: int = 0

    def __post_init__(self) -> None:
        _validate_candle(self)
        _require_decimal("volume", self.volume)
        _require_decimal("turnover", self.turnover)
        if self.volume < 0 or self.turnover < 0:
            raise ContractViolation("volume and turnover must be non-negative")


@dataclass(frozen=True, slots=True)
class MarkCandle1m:
    category: str
    instrument_id: int
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    source_id: str
    ingestion_id: str
    quality_flags: int = 0

    def __post_init__(self) -> None:
        _validate_candle(self)


def _validate_candle(candle: Candle1m | MarkCandle1m) -> None:
    _require_nonempty("category", candle.category)
    _require_nonempty("source_id", candle.source_id)
    _require_nonempty("ingestion_id", candle.ingestion_id)
    if candle.instrument_id <= 0:
        raise ContractViolation("instrument_id must be positive")
    if candle.open_time_ms < 0 or candle.open_time_ms % MINUTE_MS:
        raise ContractViolation("open_time_ms must be aligned to an exact UTC minute")
    for name in ("open", "high", "low", "close"):
        _require_decimal(name, getattr(candle, name), positive=True)
    if candle.low > candle.high:
        raise ContractViolation("low exceeds high")
    if not candle.low <= candle.open <= candle.high:
        raise ContractViolation("open lies outside low/high")
    if not candle.low <= candle.close <= candle.high:
        raise ContractViolation("close lies outside low/high")
    if candle.quality_flags < 0:
        raise ContractViolation("quality_flags must be non-negative")


@dataclass(frozen=True, slots=True)
class FundingEvent:
    category: str
    instrument_id: int
    funding_time_ms: int
    funding_rate: Decimal
    funding_interval_minutes: int
    source_id: str
    ingestion_id: str
    quality_flags: int = 0

    def __post_init__(self) -> None:
        _require_nonempty("category", self.category)
        _require_nonempty("source_id", self.source_id)
        _require_nonempty("ingestion_id", self.ingestion_id)
        if self.instrument_id <= 0 or self.funding_time_ms < 0 or self.funding_time_ms % MINUTE_MS:
            raise ContractViolation("invalid instrument identity or funding timestamp")
        _require_decimal("funding_rate", self.funding_rate)
        if self.funding_interval_minutes <= 0:
            raise ContractViolation("funding interval must be positive")
        if self.quality_flags < 0:
            raise ContractViolation("quality_flags must be non-negative")


@dataclass(frozen=True, slots=True)
class DatasetFile:
    path: str
    sha256: str
    size_bytes: int
    row_count: int
    min_time_ms: int | None
    max_time_ms: int | None
    min_instrument_id: int | None
    max_instrument_id: int | None

    def __post_init__(self) -> None:
        parsed = PurePosixPath(self.path)
        if parsed.is_absolute() or ".." in parsed.parts or self.path != parsed.as_posix():
            raise ContractViolation(
                "dataset file path must be normalized, relative, and traversal-free"
            )
        _require_sha256("sha256", self.sha256)
        if self.size_bytes < 0 or self.row_count < 0:
            raise ContractViolation("file size and row count must be non-negative")
        if (self.min_time_ms is None) != (self.max_time_ms is None):
            raise ContractViolation("time bounds must both be set or both be absent")
        if self.min_time_ms is not None and self.min_time_ms > self.max_time_ms:  # type: ignore[operator]
            raise ContractViolation("invalid time bounds")
        if (self.min_instrument_id is None) != (self.max_instrument_id is None):
            raise ContractViolation("instrument bounds must both be set or both be absent")
        if self.min_instrument_id is not None and self.min_instrument_id > self.max_instrument_id:  # type: ignore[operator]
            raise ContractViolation("invalid instrument bounds")


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    dataset_id: str
    dataset_type: DatasetType
    schema_version: str
    semantic_version: str
    status: DatasetStatus
    parent_dataset_ids: tuple[str, ...]
    instrument_count: int
    row_count: int
    min_time_ms: int | None
    max_time_ms: int | None
    files: tuple[DatasetFile, ...]
    source_evidence_sha256: tuple[str, ...]
    build_config_sha256: str
    software_identity: str
    audit_report_sha256: tuple[str, ...] = field(default_factory=tuple)
    committed_at_ms: int | None = None

    def __post_init__(self) -> None:
        for name in ("dataset_id", "schema_version", "semantic_version", "software_identity"):
            _require_nonempty(name, getattr(self, name))
        if self.instrument_count < 0 or self.row_count < 0:
            raise ContractViolation("manifest counts must be non-negative")
        if sum(item.row_count for item in self.files) != self.row_count:
            raise ContractViolation("manifest row_count does not equal file inventory")
        if (self.min_time_ms is None) != (self.max_time_ms is None):
            raise ContractViolation("manifest time bounds must both be set or absent")
        if self.min_time_ms is not None and self.min_time_ms > self.max_time_ms:  # type: ignore[operator]
            raise ContractViolation("invalid manifest time bounds")
        for digest in (*self.source_evidence_sha256, *self.audit_report_sha256):
            _require_sha256("evidence digest", digest)
        _require_sha256("build_config_sha256", self.build_config_sha256)
        if self.status is DatasetStatus.COMPLETE:
            if self.committed_at_ms is None:
                raise ContractViolation("complete manifests require committed_at_ms")
            if not self.files or not self.source_evidence_sha256 or not self.audit_report_sha256:
                raise ContractViolation(
                    "complete manifests require files, source evidence, and audits"
                )
        elif self.committed_at_ms is not None:
            raise ContractViolation("only complete manifests may have committed_at_ms")


@dataclass(frozen=True, slots=True)
class CompletionReceipt:
    dataset_id: str
    manifest_sha256: str
    status: DatasetStatus
    committed_at_ms: int

    def __post_init__(self) -> None:
        _require_nonempty("dataset_id", self.dataset_id)
        _require_sha256("manifest_sha256", self.manifest_sha256)
        if self.status is not DatasetStatus.COMPLETE:
            raise ContractViolation("a completion receipt can commit only complete status")
        if self.committed_at_ms < 0:
            raise ContractViolation("committed_at_ms must be non-negative")
