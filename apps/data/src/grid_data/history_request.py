"""Resolve operator history intent through verified registry and capacity evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_contracts.market import MINUTE_MS, InstrumentSnapshot
from grid_market_store import (
    BUCKET_COUNT,
    COMPRESSION,
    COMPRESSION_LEVEL,
    MIN_OPERATING_RESERVE_BYTES,
    NUMERIC_REPRESENTATION,
    TARGET_FILE_SIZE_BYTES,
    CapacityBudget,
)

from grid_data.evidence import verify_evidence
from grid_data.history_acquisition import (
    HistoryAcquisitionError,
    HistoryJobSpec,
    HistorySeries,
    KlineKind,
    required_rest_staging_bytes,
)
from grid_data.instrument_registry import (
    VerifiedInstrumentRegistry,
    load_verified_instrument_registry,
)

HISTORY_REQUEST_CONTRACT: Final = "grid.bybit-1m-history-request/v1"
CAPACITY_CONTRACT: Final = "grid.current-universe-capacity/v1"
ACTIVE_BUILDING_SCENARIO: Final = "full-rebuild-active-plus-building"
_REQUEST_KEYS: Final = frozenset(
    {
        "contract",
        "job_id",
        "kind",
        "series",
        "page_limit",
        "workers",
        "target_rps",
        "max_attempts",
        "max_http_requests",
    }
)
_SERIES_KEYS: Final = frozenset({"symbol", "start_ms", "end_ms"})


@dataclass(frozen=True, slots=True)
class ResolvedHistoryRequest:
    request_path: Path
    request_sha256: str
    registry: VerifiedInstrumentRegistry
    capacity_path: Path
    capacity_artifact_sha256: str
    spec: HistoryJobSpec
    budget: CapacityBudget


@dataclass(frozen=True, slots=True)
class VerifiedRequestEvidence:
    """One receipt-verified registry/capacity snapshot reusable within a single preflight."""

    registry: VerifiedInstrumentRegistry
    capacity_path: Path
    capacity: dict[str, object]
    capacity_artifact_sha256: str


def _object_file(path: Path, *, name: str) -> tuple[Path, dict[str, object]]:
    resolved = path.resolve()
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryAcquisitionError(f"{name} is not a readable JSON object") from error
    if not isinstance(raw, dict):
        raise HistoryAcquisitionError(f"{name} must contain a JSON object")
    return resolved, cast(dict[str, object], raw)


def _integer(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HistoryAcquisitionError(f"{name} must be an integer")
    return value


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise HistoryAcquisitionError(f"{name} must be non-empty trimmed text")
    return value


def _eligible_instrument(snapshot: InstrumentSnapshot) -> bool:
    return (
        snapshot.category == "linear"
        and snapshot.contract_type == "LinearPerpetual"
        and snapshot.quote_coin == "USDT"
        and snapshot.settle_coin == "USDT"
    )


def _resolve_series(
    raw: object,
    *,
    kind: KlineKind,
    registry: VerifiedInstrumentRegistry,
) -> tuple[HistorySeries, ...]:
    if not isinstance(raw, list) or not raw:
        raise HistoryAcquisitionError("history request series must be a non-empty array")
    by_symbol = registry.by_symbol()
    resolved: list[HistorySeries] = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != _SERIES_KEYS:
            raise HistoryAcquisitionError("history request series fields do not match v1")
        symbol = _text("symbol", item.get("symbol"))
        if symbol != symbol.upper() or not symbol.isalnum():
            raise HistoryAcquisitionError("history request symbol must be uppercase alphanumeric")
        instrument = by_symbol.get(symbol)
        if instrument is None:
            raise HistoryAcquisitionError(f"history symbol is absent from the registry: {symbol}")
        if not _eligible_instrument(instrument):
            raise HistoryAcquisitionError(
                f"history symbol is not a USDT linear perpetual: {symbol}"
            )
        start_ms = _integer("start_ms", item.get("start_ms"))
        end_ms = _integer("end_ms", item.get("end_ms"))
        if start_ms < instrument.launch_time_ms:
            raise HistoryAcquisitionError(f"history range precedes registry launch time: {symbol}")
        if instrument.delivery_time_ms is not None and end_ms > instrument.delivery_time_ms:
            raise HistoryAcquisitionError(f"history range exceeds registry delivery time: {symbol}")
        resolved.append(
            HistorySeries(
                kind=kind,
                category="linear",
                symbol=symbol,
                instrument_id=instrument.instrument_id,
                start_ms=start_ms,
                end_ms=end_ms,
            )
        )
    return tuple(sorted(resolved, key=lambda item: item.instrument_id))


def active_and_building_bytes_from_capacity(capacity: dict[str, object]) -> int:
    """Extract the accepted-layout active-plus-building requirement from capacity evidence."""

    if capacity.get("evidence_schema") != CAPACITY_CONTRACT:
        raise HistoryAcquisitionError("unsupported capacity evidence contract")
    raw_layouts = capacity.get("layout_projections")
    if not isinstance(raw_layouts, list):
        raise HistoryAcquisitionError("capacity evidence has no layout projections")
    accepted_layouts = []
    for raw in raw_layouts:
        if not isinstance(raw, dict) or not isinstance(raw.get("layout"), dict):
            continue
        layout = raw["layout"]
        if layout == {
            "bucket_count": BUCKET_COUNT,
            "compression": COMPRESSION,
            "compression_level": COMPRESSION_LEVEL,
            "numeric_representation": NUMERIC_REPRESENTATION,
            "target_file_mb": TARGET_FILE_SIZE_BYTES // (1024 * 1024),
        }:
            accepted_layouts.append(raw)
    if len(accepted_layouts) != 1:
        raise HistoryAcquisitionError(
            "capacity evidence does not uniquely contain the accepted canonical layout"
        )
    disk = capacity.get("disk_headroom")
    scenarios = disk.get("scenarios") if isinstance(disk, dict) else None
    if not isinstance(scenarios, list):
        raise HistoryAcquisitionError("capacity evidence has no disk-headroom scenarios")
    matches = [
        item
        for item in scenarios
        if isinstance(item, dict) and item.get("id") == ACTIVE_BUILDING_SCENARIO
    ]
    if len(matches) != 1:
        raise HistoryAcquisitionError("capacity evidence has no unique active/building scenario")
    required = _integer("active_and_building_bytes", matches[0].get("required_bytes"))
    if required <= 0:
        raise HistoryAcquisitionError("capacity active/building requirement must be positive")
    return required


def load_verified_capacity_evidence(
    path: Path,
) -> tuple[Path, dict[str, object], str]:
    """Load a receipt-verified capacity artifact and return its exact artifact digest."""

    capacity_path, capacity = _object_file(path, name="capacity evidence")
    if not verify_evidence(capacity_path):
        raise HistoryAcquisitionError("capacity evidence receipt does not verify")
    active_and_building_bytes_from_capacity(capacity)
    return capacity_path, capacity, sha256_file(capacity_path)


def load_verified_request_evidence(
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
) -> VerifiedRequestEvidence:
    """Verify campaign-wide immutable inputs once and retain their exact artifact identities."""

    registry = load_verified_instrument_registry(instrument_registry_path)
    capacity_path, capacity, capacity_hash = load_verified_capacity_evidence(capacity_evidence_path)
    return VerifiedRequestEvidence(
        registry=registry,
        capacity_path=capacity_path,
        capacity=capacity,
        capacity_artifact_sha256=capacity_hash,
    )


def resolve_history_request_payload(
    request: dict[str, object],
    *,
    source_path: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    verified_evidence: VerifiedRequestEvidence | None = None,
) -> ResolvedHistoryRequest:
    """Resolve an already-loaded v1 request without materializing a temporary request file."""

    resolved_request = source_path.resolve()
    if set(request) - _REQUEST_KEYS or request.get("contract") != HISTORY_REQUEST_CONTRACT:
        raise HistoryAcquisitionError("history request fields or contract do not match v1")
    kind = request.get("kind")
    if kind not in ("trade", "mark"):
        raise HistoryAcquisitionError("history request kind must be trade or mark")
    evidence = verified_evidence or load_verified_request_evidence(
        instrument_registry_path,
        capacity_evidence_path,
    )
    if (
        evidence.registry.path != instrument_registry_path.resolve()
        or evidence.capacity_path != capacity_evidence_path.resolve()
    ):
        raise HistoryAcquisitionError("verified request evidence paths do not match request inputs")
    registry = evidence.registry
    series = _resolve_series(
        request.get("series"),
        kind=kind,
        registry=registry,
    )
    capacity_path = evidence.capacity_path
    capacity = evidence.capacity
    capacity_hash = evidence.capacity_artifact_sha256
    defaults = {
        "page_limit": 1000,
        "workers": 24,
        "target_rps": 10,
        "max_attempts": 3,
        "max_http_requests": 100_000,
    }
    for name in defaults:
        if name in request:
            defaults[name] = _integer(name, request[name])
    spec = HistoryJobSpec(
        job_id=_text("job_id", request.get("job_id")),
        series=series,
        request_sha256=canonical_sha256(request),
        instrument_evidence_sha256=registry.artifact_sha256,
        capacity_evidence_sha256=capacity_hash,
        **defaults,
    )
    budget = CapacityBudget(
        active_and_building_bytes=active_and_building_bytes_from_capacity(capacity),
        rest_staging_bytes=required_rest_staging_bytes(spec),
        operating_reserve_bytes=MIN_OPERATING_RESERVE_BYTES,
    )
    return ResolvedHistoryRequest(
        request_path=resolved_request,
        request_sha256=canonical_sha256(request),
        registry=registry,
        capacity_path=capacity_path,
        capacity_artifact_sha256=capacity_hash,
        spec=spec,
        budget=budget,
    )


def resolve_history_request(
    request_path: Path,
    *,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
) -> ResolvedHistoryRequest:
    """Bind a v1 request to immutable evidence and derive its complete staging budget."""

    resolved_request, request = _object_file(request_path, name="history request")
    return resolve_history_request_payload(
        request,
        source_path=resolved_request,
        instrument_registry_path=instrument_registry_path,
        capacity_evidence_path=capacity_evidence_path,
    )


def closed_before_now_ms(now_ms: int) -> int:
    """Return the first UTC minute that cannot yet be requested as a closed candle."""

    if isinstance(now_ms, bool) or not isinstance(now_ms, int) or now_ms < 0:
        raise HistoryAcquisitionError("current time must be non-negative Unix milliseconds")
    return now_ms // MINUTE_MS * MINUTE_MS
