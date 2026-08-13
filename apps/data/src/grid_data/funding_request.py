"""Resolve funding-history intent through verified registry and capacity evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from grid_contracts.canonical import canonical_sha256
from grid_contracts.market import InstrumentSnapshot
from grid_market_store import MIN_OPERATING_RESERVE_BYTES, CapacityBudget

from grid_data.funding_acquisition import (
    DEFAULT_PAGE_SPAN_MINUTES,
    MAX_HTTP_REQUESTS,
    MAX_PAGE_LIMIT,
    FundingAcquisitionError,
    FundingJobSpec,
    FundingSeries,
    required_funding_staging_bytes,
)
from grid_data.history_acquisition import HistoryAcquisitionError
from grid_data.history_request import (
    VerifiedRequestEvidence,
    active_and_building_bytes_from_capacity,
    load_verified_request_evidence,
)
from grid_data.instrument_registry import VerifiedInstrumentRegistry

FUNDING_REQUEST_CONTRACT: Final = "grid.bybit-funding-history-request/v1"
_REQUEST_KEYS: Final = frozenset(
    {
        "contract",
        "job_id",
        "series",
        "page_span_minutes",
        "page_limit",
        "workers",
        "target_rps",
        "max_attempts",
        "max_http_requests",
    }
)
_SERIES_KEYS: Final = frozenset({"symbol", "start_ms", "end_ms"})


@dataclass(frozen=True, slots=True)
class ResolvedFundingRequest:
    request_path: Path
    request_sha256: str
    registry: VerifiedInstrumentRegistry
    capacity_path: Path
    capacity_artifact_sha256: str
    spec: FundingJobSpec
    budget: CapacityBudget


def _object_file(path: Path) -> tuple[Path, dict[str, object]]:
    resolved = path.resolve()
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FundingAcquisitionError("funding request is not readable JSON") from error
    if not isinstance(raw, dict):
        raise FundingAcquisitionError("funding request must contain an object")
    return resolved, cast(dict[str, object], raw)


def _integer(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FundingAcquisitionError(f"{name} must be an integer")
    return value


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise FundingAcquisitionError(f"{name} must be non-empty trimmed text")
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
    registry: VerifiedInstrumentRegistry,
) -> tuple[FundingSeries, ...]:
    if not isinstance(raw, list) or not raw:
        raise FundingAcquisitionError("funding request series must be a non-empty array")
    by_symbol = registry.by_symbol()
    resolved: list[FundingSeries] = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != _SERIES_KEYS:
            raise FundingAcquisitionError("funding request series fields do not match v1")
        symbol = _text("symbol", item.get("symbol"))
        if symbol != symbol.upper() or not symbol.isalnum():
            raise FundingAcquisitionError("funding request symbol must be uppercase alphanumeric")
        instrument = by_symbol.get(symbol)
        if instrument is None:
            raise FundingAcquisitionError(f"funding symbol is absent from registry: {symbol}")
        if not _eligible_instrument(instrument):
            raise FundingAcquisitionError(
                f"funding symbol is not a USDT linear perpetual: {symbol}"
            )
        start_ms = _integer("start_ms", item.get("start_ms"))
        end_ms = _integer("end_ms", item.get("end_ms"))
        if start_ms <= instrument.launch_time_ms:
            raise FundingAcquisitionError(
                f"funding start must allow a predecessor after launch: {symbol}"
            )
        if instrument.delivery_time_ms is not None and end_ms > instrument.delivery_time_ms:
            raise FundingAcquisitionError(f"funding range exceeds registry delivery: {symbol}")
        resolved.append(
            FundingSeries(
                category="linear",
                symbol=symbol,
                instrument_id=instrument.instrument_id,
                launch_time_ms=instrument.launch_time_ms,
                start_ms=start_ms,
                end_ms=end_ms,
            )
        )
    return tuple(sorted(resolved, key=lambda item: item.instrument_id))


def resolve_funding_request_payload(
    request: dict[str, object],
    *,
    source_path: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    verified_evidence: VerifiedRequestEvidence | None = None,
) -> ResolvedFundingRequest:
    """Resolve an already-loaded funding request without mutating storage."""

    if set(request) - _REQUEST_KEYS or request.get("contract") != FUNDING_REQUEST_CONTRACT:
        raise FundingAcquisitionError("funding request fields or contract do not match v1")
    try:
        evidence = verified_evidence or load_verified_request_evidence(
            instrument_registry_path,
            capacity_evidence_path,
        )
    except HistoryAcquisitionError as error:
        raise FundingAcquisitionError(str(error)) from error
    if (
        evidence.registry.path != instrument_registry_path.resolve()
        or evidence.capacity_path != capacity_evidence_path.resolve()
    ):
        raise FundingAcquisitionError("verified request evidence paths do not match funding inputs")
    registry = evidence.registry
    series = _resolve_series(request.get("series"), registry=registry)
    capacity_path = evidence.capacity_path
    capacity = evidence.capacity
    capacity_hash = evidence.capacity_artifact_sha256
    defaults = {
        "page_span_minutes": DEFAULT_PAGE_SPAN_MINUTES,
        "page_limit": MAX_PAGE_LIMIT,
        "workers": 24,
        "target_rps": 10,
        "max_attempts": 3,
        "max_http_requests": MAX_HTTP_REQUESTS,
    }
    for name in defaults:
        if name in request:
            defaults[name] = _integer(name, request[name])
    request_sha = canonical_sha256(request)
    spec = FundingJobSpec(
        job_id=_text("job_id", request.get("job_id")),
        series=series,
        request_sha256=request_sha,
        instrument_evidence_sha256=registry.artifact_sha256,
        capacity_evidence_sha256=capacity_hash,
        **defaults,
    )
    budget = CapacityBudget(
        active_and_building_bytes=active_and_building_bytes_from_capacity(capacity),
        rest_staging_bytes=required_funding_staging_bytes(spec),
        operating_reserve_bytes=MIN_OPERATING_RESERVE_BYTES,
    )
    return ResolvedFundingRequest(
        request_path=source_path.resolve(),
        request_sha256=request_sha,
        registry=registry,
        capacity_path=capacity_path,
        capacity_artifact_sha256=capacity_hash,
        spec=spec,
        budget=budget,
    )


def resolve_funding_request(
    request_path: Path,
    *,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
) -> ResolvedFundingRequest:
    """Load and resolve one operator funding request."""

    resolved, request = _object_file(request_path)
    return resolve_funding_request_payload(
        request,
        source_path=resolved,
        instrument_registry_path=instrument_registry_path,
        capacity_evidence_path=capacity_evidence_path,
    )
