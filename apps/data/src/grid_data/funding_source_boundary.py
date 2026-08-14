"""Receipt-resumable discovery of the earliest public funding-history boundary."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final, Literal, Protocol, cast

from grid_bybit_public import BybitPublicError
from grid_bybit_public.transport import TransportError
from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file
from grid_contracts.market import InstrumentSnapshot
from grid_market_store import MIN_OPERATING_RESERVE_BYTES, HostSnapshot

from grid_data.instrument_registry import load_verified_instrument_registry
from grid_data.public_rate_limit import (
    AdaptiveRateLimitAbort,
    AdaptiveRateLimitError,
    AdaptiveRatePacer,
    verify_adaptive_rate_summary,
)

BOUNDARY_REQUEST_CONTRACT: Final = "grid.bybit-funding-source-boundary-request/v1"
BOUNDARY_PLAN_CONTRACT: Final = "grid.bybit-funding-source-boundary-plan/v1"
BOUNDARY_PAGE_CONTRACT: Final = "grid.bybit-funding-source-boundary-page/v1"
BOUNDARY_MANIFEST_CONTRACT: Final = "grid.bybit-funding-source-boundary/v1"
BOUNDARY_RECEIPT_CONTRACT: Final = "grid.funding-source-boundary-receipt/v1"
DISCOVERY_ID_RE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{2,79}$")
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
MAX_SYMBOLS: Final = 700
MAX_WORKERS: Final = 32
MAX_TARGET_RPS: Final = 96
MAX_ATTEMPTS: Final = 5
MAX_PAGE_LIMIT: Final = 200
MAX_PAGES_PER_SYMBOL: Final = 512
MAX_PAGE_ARTIFACT_BYTES: Final = 64 * 1024
METADATA_BYTES: Final = 512 * 1024**2
PLANNED_MEMORY_BYTES: Final = 768 * 1024**2
MAX_PREFLIGHT_AGE_MS: Final = 60_000
_REQUEST_KEYS: Final = {
    "contract",
    "discovery_id",
    "end_ms",
    "max_attempts",
    "max_pages_per_symbol",
    "page_limit",
    "start_ms",
    "symbols",
    "target_rps",
    "workers",
}
_PLAN_KEYS: Final = {
    "contract",
    "discovery_id",
    "max_attempts",
    "max_pages_per_symbol",
    "page_limit",
    "registry_sha256",
    "request",
    "request_sha256",
    "series",
    "software_identity",
    "target_rps",
    "workers",
}
_SERIES_KEYS: Final = {"instrument_id", "scan_end_ms", "scan_start_ms", "symbol"}
_MANIFEST_KEYS: Final = {
    "adaptive_throttling",
    "completed_at_ms",
    "contract",
    "event_count",
    "http_attempt_count",
    "page_count",
    "pages",
    "plan_sha256",
    "results",
    "source_policy",
    "status",
    "symbol_count",
}
_SOURCE_POLICY: Final = {
    "category": "linear",
    "endpoint": "/v5/market/funding/history",
    "pagination": "inclusive-end-oldest-minus-one-v1",
    "persisted_fields": ["fundingRateTimestamp"],
    "private_credentials_used": False,
    "source_rates_validated_not_retained": True,
}


class FundingSourceBoundaryError(RuntimeError):
    """A public funding source boundary cannot be proven safely."""


class FundingBoundaryClient(Protocol):
    def funding_page(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        category: Literal["linear", "inverse"] = "linear",
        limit: int = 200,
    ) -> tuple[Mapping[str, Any], ...]: ...


@dataclass(frozen=True, slots=True)
class BoundarySeries:
    instrument_id: int
    symbol: str
    scan_start_ms: int
    scan_end_ms: int


@dataclass(frozen=True, slots=True)
class FundingBoundaryPlan:
    request_path: Path
    request_sha256: str
    registry_sha256: str
    output_root: Path
    job_root: Path
    snapshot: HostSnapshot
    series: tuple[BoundarySeries, ...]
    page_limit: int
    workers: int
    target_rps: int
    max_attempts: int
    max_pages_per_symbol: int
    software_identity: str
    plan_payload: dict[str, object]
    plan_sha256: str
    required_free_bytes: int
    planned_peak_memory_bytes: int
    existing_complete: bool


@dataclass(frozen=True, slots=True)
class FundingBoundaryResult:
    canonical_start_ms: int
    event_count: int
    first_observed_settlement_ms: int
    instrument_id: int
    page_count: int
    predecessor_settlement_ms: int
    symbol: str


@dataclass(frozen=True, slots=True)
class CompletedFundingBoundary:
    job_root: Path
    manifest_path: Path
    receipt_path: Path
    manifest_sha256: str
    plan_sha256: str
    request_sha256: str
    registry_sha256: str
    software_identity: str
    scan_start_ms: int
    scan_end_ms: int
    symbol_count: int
    page_count: int
    event_count: int
    http_attempt_count: int
    adaptive_throttling: dict[str, object]
    results: tuple[FundingBoundaryResult, ...]


def _integer(name: str, value: object, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise FundingSourceBoundaryError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _load_json_object(path: Path, *, canonical: bool) -> dict[str, object]:
    try:
        data = path.read_bytes()
        raw = json.loads(data)
    except (OSError, json.JSONDecodeError) as error:
        raise FundingSourceBoundaryError(f"cannot load funding boundary JSON: {path}") from error
    if not isinstance(raw, dict) or (canonical and canonical_json_bytes(raw) != data):
        raise FundingSourceBoundaryError(f"funding boundary JSON is invalid: {path}")
    return cast(dict[str, object], raw)


def _receipt_payload(artifact: str, digest: str) -> dict[str, object]:
    return {
        "artifact": artifact,
        "artifact_sha256": digest,
        "contract": BOUNDARY_RECEIPT_CONTRACT,
        "status": "complete",
    }


def _atomic_write_new(path: Path, payload: Mapping[str, object]) -> str:
    if path.exists():
        raise FundingSourceBoundaryError(f"refusing to replace funding boundary artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".building",
    )
    temporary = Path(temporary_name)
    try:
        data = canonical_json_bytes(payload)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return sha256_file(path)


def _publish_with_receipt(path: Path, payload: Mapping[str, object]) -> str:
    digest = _atomic_write_new(path, payload)
    _atomic_write_new(path.with_suffix(".receipt.json"), _receipt_payload(path.name, digest))
    return digest


def _verify_artifact(path: Path) -> tuple[dict[str, object], str]:
    receipt_path = path.with_suffix(".receipt.json")
    if not path.is_file() or not receipt_path.is_file():
        raise FundingSourceBoundaryError(f"funding boundary artifact pair is incomplete: {path}")
    payload = _load_json_object(path, canonical=True)
    receipt = _load_json_object(receipt_path, canonical=True)
    digest = sha256_file(path)
    if receipt != _receipt_payload(path.name, digest):
        raise FundingSourceBoundaryError(f"funding boundary receipt does not verify: {path}")
    if path.parent.name == "pages" and path.stat().st_size > MAX_PAGE_ARTIFACT_BYTES:
        raise FundingSourceBoundaryError("funding boundary page exceeds its fixed byte bound")
    return payload, digest


def _verified_plan(
    plan: Mapping[str, object],
) -> tuple[tuple[BoundarySeries, ...], int, int, int, int]:
    request = plan.get("request")
    raw_series = plan.get("series")
    if (
        set(plan) != _PLAN_KEYS
        or plan.get("contract") != BOUNDARY_PLAN_CONTRACT
        or not isinstance(request, dict)
        or set(request) != _REQUEST_KEYS
        or request.get("contract") != BOUNDARY_REQUEST_CONTRACT
        or not isinstance(raw_series, list)
    ):
        raise FundingSourceBoundaryError("funding boundary plan fields do not match v1")
    discovery_id = request.get("discovery_id")
    software_identity = plan.get("software_identity")
    registry_sha = plan.get("registry_sha256")
    request_sha = plan.get("request_sha256")
    if (
        not isinstance(discovery_id, str)
        or DISCOVERY_ID_RE.fullmatch(discovery_id) is None
        or plan.get("discovery_id") != discovery_id
        or not isinstance(software_identity, str)
        or SOFTWARE_IDENTITY_RE.fullmatch(software_identity) is None
        or not isinstance(registry_sha, str)
        or SHA256_RE.fullmatch(registry_sha) is None
        or not isinstance(request_sha, str)
        or request_sha != canonical_sha256(request)
    ):
        raise FundingSourceBoundaryError("funding boundary plan identity is invalid")
    start_ms = _integer("start_ms", request.get("start_ms"), minimum=0, maximum=2**63 - 1)
    end_ms = _integer("end_ms", request.get("end_ms"), minimum=0, maximum=2**63 - 1)
    page_limit = _integer(
        "page_limit", request.get("page_limit"), minimum=1, maximum=MAX_PAGE_LIMIT
    )
    _integer("workers", request.get("workers"), minimum=1, maximum=MAX_WORKERS)
    target_rps = _integer(
        "target_rps", request.get("target_rps"), minimum=1, maximum=MAX_TARGET_RPS
    )
    max_attempts = _integer(
        "max_attempts", request.get("max_attempts"), minimum=1, maximum=MAX_ATTEMPTS
    )
    max_pages = _integer(
        "max_pages_per_symbol",
        request.get("max_pages_per_symbol"),
        minimum=1,
        maximum=MAX_PAGES_PER_SYMBOL,
    )
    raw_symbols = request.get("symbols")
    if (
        end_ms < start_ms
        or start_ms % 60_000
        or end_ms % 60_000
        or not isinstance(raw_symbols, list)
        or not 1 <= len(raw_symbols) <= MAX_SYMBOLS
        or any(
            not isinstance(symbol, str) or symbol != symbol.upper() or not symbol.isalnum()
            for symbol in raw_symbols
        )
        or raw_symbols != sorted(raw_symbols)
        or len(raw_symbols) != len(set(raw_symbols))
        or len(raw_series) != len(raw_symbols)
        or any(
            plan.get(name) != request.get(name)
            for name in (
                "discovery_id",
                "max_attempts",
                "max_pages_per_symbol",
                "page_limit",
                "target_rps",
                "workers",
            )
        )
    ):
        raise FundingSourceBoundaryError("funding boundary plan request is invalid")
    series: list[BoundarySeries] = []
    for expected_symbol, raw in zip(raw_symbols, raw_series, strict=True):
        if not isinstance(raw, dict) or set(raw) != _SERIES_KEYS:
            raise FundingSourceBoundaryError("funding boundary plan series fields are invalid")
        instrument_id = _integer(
            "instrument_id", raw.get("instrument_id"), minimum=1, maximum=2**32 - 1
        )
        scan_start = _integer(
            "scan_start_ms", raw.get("scan_start_ms"), minimum=0, maximum=2**63 - 1
        )
        scan_end = _integer("scan_end_ms", raw.get("scan_end_ms"), minimum=0, maximum=2**63 - 1)
        if (
            raw.get("symbol") != expected_symbol
            or scan_start < start_ms
            or scan_end > end_ms
            or scan_end <= scan_start
        ):
            raise FundingSourceBoundaryError("funding boundary plan series bounds are invalid")
        series.append(BoundarySeries(instrument_id, expected_symbol, scan_start, scan_end))
    if len({item.instrument_id for item in series}) != len(series):
        raise FundingSourceBoundaryError("funding boundary instrument IDs are not unique")
    return tuple(series), page_limit, target_rps, max_attempts, max_pages


def _eligible(snapshot: InstrumentSnapshot) -> bool:
    return (
        snapshot.category == "linear"
        and snapshot.contract_type == "LinearPerpetual"
        and snapshot.quote_coin == "USDT"
        and snapshot.settle_coin == "USDT"
    )


def _assert_host(plan_root: Path, snapshot: HostSnapshot, *, now_ms: int) -> None:
    age = now_ms - snapshot.observed_at_ms
    if age < 0 or age > MAX_PREFLIGHT_AGE_MS:
        raise FundingSourceBoundaryError("funding boundary host snapshot is stale")
    if snapshot.storage_kind not in ("nvme", "ssd"):
        raise FundingSourceBoundaryError("funding boundary output requires SSD/NVMe storage")
    try:
        plan_root.resolve().relative_to(snapshot.volume_root.resolve())
    except ValueError as error:
        raise FundingSourceBoundaryError(
            "funding boundary output is outside observed volume"
        ) from error


def _page_path(job_root: Path, series: BoundarySeries, index: int) -> Path:
    return job_root / "pages" / f"{series.instrument_id:010d}-{index:04d}.json"


def _page_payload(
    series: BoundarySeries,
    *,
    query_end_ms: int,
    limit: int,
    attempts: int,
    items: tuple[Mapping[str, Any], ...],
) -> dict[str, object]:
    timestamps: list[int] = []
    for item in items:
        if item.get("symbol") != series.symbol:
            raise FundingSourceBoundaryError("funding discovery response symbol mismatch")
        raw_timestamp = item.get("fundingRateTimestamp")
        raw_rate = item.get("fundingRate")
        if not isinstance(raw_timestamp, str) or not raw_timestamp.isdigit():
            raise FundingSourceBoundaryError("funding discovery timestamp is invalid")
        if not isinstance(raw_rate, str):
            raise FundingSourceBoundaryError("funding discovery rate is not exact text")
        try:
            rate = Decimal(raw_rate)
        except InvalidOperation as error:
            raise FundingSourceBoundaryError("funding discovery rate is invalid") from error
        timestamp = int(raw_timestamp)
        if not rate.is_finite():
            raise FundingSourceBoundaryError("funding discovery rate is invalid")
        if timestamp < series.scan_start_ms or timestamp > query_end_ms or timestamp % 60_000:
            raise FundingSourceBoundaryError("funding discovery row escapes its query")
        timestamps.append(timestamp)
    if timestamps != sorted(timestamps, reverse=True) or len(timestamps) != len(set(timestamps)):
        raise FundingSourceBoundaryError("funding discovery page is not unique reverse chronology")
    terminal = not timestamps or timestamps[-1] <= series.scan_start_ms
    payload: dict[str, object] = {
        "attempt_count": attempts,
        "contract": BOUNDARY_PAGE_CONTRACT,
        "end_ms": query_end_ms,
        "instrument_id": series.instrument_id,
        "limit": limit,
        "row_count": len(timestamps),
        "start_ms": series.scan_start_ms,
        "symbol": series.symbol,
        "terminal": terminal,
        "timestamps": timestamps,
    }
    if len(canonical_json_bytes(payload)) > MAX_PAGE_ARTIFACT_BYTES:
        raise FundingSourceBoundaryError("funding discovery page exceeds fixed byte bound")
    return payload


def _validate_page(
    payload: Mapping[str, object],
    series: BoundarySeries,
    *,
    expected_end_ms: int,
    page_limit: int,
    max_attempts: int,
) -> tuple[tuple[int, ...], bool]:
    expected_fields = {
        "attempt_count",
        "contract",
        "end_ms",
        "instrument_id",
        "limit",
        "row_count",
        "start_ms",
        "symbol",
        "terminal",
        "timestamps",
    }
    attempts = payload.get("attempt_count")
    raw_timestamps = payload.get("timestamps")
    if (
        set(payload) != expected_fields
        or payload.get("contract") != BOUNDARY_PAGE_CONTRACT
        or payload.get("end_ms") != expected_end_ms
        or payload.get("instrument_id") != series.instrument_id
        or payload.get("limit") != page_limit
        or payload.get("start_ms") != series.scan_start_ms
        or payload.get("symbol") != series.symbol
        or isinstance(attempts, bool)
        or not isinstance(attempts, int)
        or not 1 <= attempts <= max_attempts
        or not isinstance(raw_timestamps, list)
        or len(raw_timestamps) > page_limit
        or any(isinstance(item, bool) or not isinstance(item, int) for item in raw_timestamps)
    ):
        raise FundingSourceBoundaryError("funding discovery page identity is invalid")
    timestamps = tuple(cast(list[int], raw_timestamps))
    terminal = not timestamps or timestamps[-1] <= series.scan_start_ms
    if (
        list(timestamps) != sorted(timestamps, reverse=True)
        or len(timestamps) != len(set(timestamps))
        or any(
            value < series.scan_start_ms or value > expected_end_ms or value % 60_000
            for value in timestamps
        )
        or payload.get("row_count") != len(timestamps)
        or payload.get("terminal") is not terminal
    ):
        raise FundingSourceBoundaryError("funding discovery page chronology is invalid")
    return timestamps, terminal


def _load_progress(
    job_root: Path,
    series: BoundarySeries,
    *,
    page_limit: int,
    max_attempts: int,
    max_pages_per_symbol: int,
) -> tuple[list[dict[str, object]], list[int], int, int, bool]:
    entries: list[dict[str, object]] = []
    all_timestamps: list[int] = []
    query_end = series.scan_end_ms
    attempts_total = 0
    terminal = False
    for index in range(max_pages_per_symbol):
        page = _page_path(job_root, series, index)
        receipt = page.with_suffix(".receipt.json")
        if page.exists() != receipt.exists():
            raise FundingSourceBoundaryError("partial funding discovery page detected")
        if not page.exists():
            return entries, all_timestamps, query_end, attempts_total, terminal
        payload, digest = _verify_artifact(page)
        timestamps, terminal = _validate_page(
            payload,
            series,
            expected_end_ms=query_end,
            page_limit=page_limit,
            max_attempts=max_attempts,
        )
        attempts_total += cast(int, payload["attempt_count"])
        all_timestamps.extend(timestamps)
        entries.append(
            {
                "artifact": f"pages/{page.name}",
                "artifact_sha256": digest,
                "attempt_count": payload["attempt_count"],
                "row_count": len(timestamps),
                "sequence": index,
            }
        )
        if terminal:
            return entries, all_timestamps, query_end, attempts_total, terminal
        query_end = timestamps[-1] - 1
    return entries, all_timestamps, query_end, attempts_total, terminal


def preflight_funding_source_boundary(
    request_path: Path,
    *,
    instrument_registry_path: Path,
    output_root: Path,
    snapshot: HostSnapshot,
    now_ms: int,
    software_identity: str,
) -> FundingBoundaryPlan:
    """Resolve a bounded public discovery plan without filesystem mutation."""

    request_file = request_path.resolve()
    request = _load_json_object(request_file, canonical=False)
    if set(request) != _REQUEST_KEYS or request.get("contract") != BOUNDARY_REQUEST_CONTRACT:
        raise FundingSourceBoundaryError("funding boundary request fields do not match v1")
    discovery_id = request.get("discovery_id")
    if not isinstance(discovery_id, str) or DISCOVERY_ID_RE.fullmatch(discovery_id) is None:
        raise FundingSourceBoundaryError("funding boundary discovery_id is invalid")
    if SOFTWARE_IDENTITY_RE.fullmatch(software_identity) is None:
        raise FundingSourceBoundaryError("funding boundary software identity must be immutable")
    start_ms = _integer("start_ms", request.get("start_ms"), minimum=0, maximum=2**63 - 1)
    end_ms = _integer("end_ms", request.get("end_ms"), minimum=0, maximum=2**63 - 1)
    if end_ms < start_ms or end_ms >= now_ms or start_ms % 60_000 or end_ms % 60_000:
        raise FundingSourceBoundaryError("funding boundary range is not closed and ordered")
    page_limit = _integer("page_limit", request.get("page_limit"), minimum=1, maximum=200)
    workers = _integer("workers", request.get("workers"), minimum=1, maximum=MAX_WORKERS)
    target_rps = _integer(
        "target_rps", request.get("target_rps"), minimum=1, maximum=MAX_TARGET_RPS
    )
    max_attempts = _integer(
        "max_attempts", request.get("max_attempts"), minimum=1, maximum=MAX_ATTEMPTS
    )
    max_pages = _integer(
        "max_pages_per_symbol",
        request.get("max_pages_per_symbol"),
        minimum=1,
        maximum=MAX_PAGES_PER_SYMBOL,
    )
    raw_symbols = request.get("symbols")
    if (
        not isinstance(raw_symbols, list)
        or not 1 <= len(raw_symbols) <= MAX_SYMBOLS
        or any(
            not isinstance(symbol, str) or symbol != symbol.upper() or not symbol.isalnum()
            for symbol in raw_symbols
        )
        or raw_symbols != sorted(raw_symbols)
        or len(raw_symbols) != len(set(raw_symbols))
    ):
        raise FundingSourceBoundaryError("funding boundary symbols must be sorted unique text")
    registry = load_verified_instrument_registry(instrument_registry_path)
    by_symbol = registry.by_symbol()
    series: list[BoundarySeries] = []
    for symbol in cast(list[str], raw_symbols):
        instrument = by_symbol.get(symbol)
        if instrument is None or not _eligible(instrument):
            raise FundingSourceBoundaryError(f"funding boundary symbol is not eligible: {symbol}")
        scan_start = max(start_ms, instrument.launch_time_ms)
        scan_end = min(end_ms, instrument.delivery_time_ms or end_ms)
        if scan_end <= scan_start:
            raise FundingSourceBoundaryError(f"funding boundary range is empty: {symbol}")
        series.append(
            BoundarySeries(
                instrument_id=instrument.instrument_id,
                symbol=symbol,
                scan_start_ms=scan_start,
                scan_end_ms=scan_end,
            )
        )
    resolved_output = output_root.resolve()
    required_free = (
        MIN_OPERATING_RESERVE_BYTES
        + METADATA_BYTES
        + len(series) * max_pages * MAX_PAGE_ARTIFACT_BYTES
    )
    _assert_host(resolved_output, snapshot, now_ms=now_ms)
    if snapshot.volume_free_bytes < required_free:
        raise FundingSourceBoundaryError("insufficient free space for funding boundary discovery")
    if snapshot.memory_available_bytes < PLANNED_MEMORY_BYTES:
        raise FundingSourceBoundaryError("insufficient available memory for funding discovery")
    if snapshot.memory_total_bytes * 70 < PLANNED_MEMORY_BYTES * 100:
        raise FundingSourceBoundaryError("funding boundary exceeds the 70% total-memory gate")
    request_sha = canonical_sha256(request)
    plan_payload: dict[str, object] = {
        "contract": BOUNDARY_PLAN_CONTRACT,
        "discovery_id": discovery_id,
        "max_attempts": max_attempts,
        "max_pages_per_symbol": max_pages,
        "page_limit": page_limit,
        "registry_sha256": registry.artifact_sha256,
        "request": request,
        "request_sha256": request_sha,
        "series": tuple(series),
        "software_identity": software_identity,
        "target_rps": target_rps,
        "workers": workers,
    }
    plan_sha = canonical_sha256(plan_payload)
    job_root = resolved_output / f"{discovery_id}--{plan_sha[:16]}"
    existing_complete = False
    if job_root.exists():
        if not job_root.is_dir() or job_root.is_symlink() or (job_root / ".run-lock").exists():
            raise FundingSourceBoundaryError("funding boundary root is unsafe or active")
        existing_plan, _digest = _verify_artifact(job_root / "plan.json")
        if existing_plan != json.loads(canonical_json_bytes(plan_payload)):
            raise FundingSourceBoundaryError("existing funding boundary plan differs")
        if (job_root / "completion-receipt.json").exists():
            verify_completed_funding_source_boundary(job_root)
            existing_complete = True
    return FundingBoundaryPlan(
        request_path=request_file,
        request_sha256=request_sha,
        registry_sha256=registry.artifact_sha256,
        output_root=resolved_output,
        job_root=job_root,
        snapshot=snapshot,
        series=tuple(series),
        page_limit=page_limit,
        workers=workers,
        target_rps=target_rps,
        max_attempts=max_attempts,
        max_pages_per_symbol=max_pages,
        software_identity=software_identity,
        plan_payload=plan_payload,
        plan_sha256=plan_sha,
        required_free_bytes=required_free,
        planned_peak_memory_bytes=PLANNED_MEMORY_BYTES,
        existing_complete=existing_complete,
    )


def _fetch_page(
    plan: FundingBoundaryPlan,
    series: BoundarySeries,
    *,
    query_end_ms: int,
    client: FundingBoundaryClient,
    pacer: AdaptiveRatePacer,
) -> dict[str, object]:
    last_error: Exception | None = None
    for attempt in range(1, plan.max_attempts + 1):
        pacer.wait()
        try:
            try:
                items = client.funding_page(
                    symbol=series.symbol,
                    start_ms=series.scan_start_ms,
                    end_ms=query_end_ms,
                    category="linear",
                    limit=plan.page_limit,
                )
            finally:
                pacer.observe_client(client)
            return _page_payload(
                series,
                query_end_ms=query_end_ms,
                limit=plan.page_limit,
                attempts=attempt,
                items=items,
            )
        except TransportError as error:
            if error.failure_class == "regional-access-block":
                raise AdaptiveRateLimitAbort(
                    "Bybit public API is unavailable from the current region; resume only "
                    "from an officially supported network and region",
                    reason="regional-access-block",
                ) from error
            last_error = error
            if attempt < plan.max_attempts:
                time.sleep(min(4.0, 0.25 * (2 ** (attempt - 1))))
        except BybitPublicError as error:
            last_error = error
            if attempt < plan.max_attempts:
                time.sleep(min(4.0, 0.25 * (2 ** (attempt - 1))))
    raise FundingSourceBoundaryError(
        f"funding boundary page failed after {plan.max_attempts} attempts"
    ) from last_error


def execute_funding_source_boundary(
    plan: FundingBoundaryPlan,
    *,
    client_factory: Callable[[], FundingBoundaryClient],
    snapshot_provider: Callable[[], HostSnapshot],
    now_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
) -> CompletedFundingBoundary:
    """Scan public funding pages backward, resuming only from verified page receipts."""

    if plan.existing_complete:
        return verify_completed_funding_source_boundary(plan.job_root)
    fresh = snapshot_provider()
    _assert_host(plan.output_root, fresh, now_ms=now_ms())
    if (
        fresh.device_identity_sha256 != plan.snapshot.device_identity_sha256
        or fresh.memory_total_bytes != plan.snapshot.memory_total_bytes
        or fresh.volume_free_bytes < plan.required_free_bytes
        or fresh.memory_available_bytes < plan.planned_peak_memory_bytes
    ):
        raise FundingSourceBoundaryError("funding boundary host/resources changed after preflight")
    plan.job_root.mkdir(parents=True, exist_ok=True)
    if not (plan.job_root / "plan.json").exists():
        _publish_with_receipt(plan.job_root / "plan.json", plan.plan_payload)
    lock = plan.job_root / ".run-lock"
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise FundingSourceBoundaryError("funding boundary run is already active") from error
    pacer = AdaptiveRatePacer(plan.target_rps)

    def acquire(series: BoundarySeries) -> None:
        client = client_factory()
        entries, _timestamps, query_end, _attempts, terminal = _load_progress(
            plan.job_root,
            series,
            page_limit=plan.page_limit,
            max_attempts=plan.max_attempts,
            max_pages_per_symbol=plan.max_pages_per_symbol,
        )
        page_index = len(entries)
        while not terminal:
            if page_index >= plan.max_pages_per_symbol:
                raise FundingSourceBoundaryError("funding boundary exceeded per-symbol page bound")
            payload = _fetch_page(
                plan,
                series,
                query_end_ms=query_end,
                client=client,
                pacer=pacer,
            )
            page = _page_path(plan.job_root, series, page_index)
            _publish_with_receipt(page, payload)
            timestamps, terminal = _validate_page(
                payload,
                series,
                expected_end_ms=query_end,
                page_limit=plan.page_limit,
                max_attempts=plan.max_attempts,
            )
            if not terminal:
                query_end = timestamps[-1] - 1
            page_index += 1

    try:
        with ThreadPoolExecutor(max_workers=min(plan.workers, len(plan.series))) as executor:
            futures = [executor.submit(acquire, series) for series in plan.series]
            for future in as_completed(futures):
                future.result()
        results: list[dict[str, object]] = []
        pages: list[dict[str, object]] = []
        total_events = 0
        total_attempts = 0
        for series in plan.series:
            entries, timestamps, _end, attempts, terminal = _load_progress(
                plan.job_root,
                series,
                page_limit=plan.page_limit,
                max_attempts=plan.max_attempts,
                max_pages_per_symbol=plan.max_pages_per_symbol,
            )
            if not terminal or len(timestamps) < 2:
                raise FundingSourceBoundaryError(
                    "funding source boundary needs at least two observed settlements"
                )
            ordered = sorted(timestamps)
            total_events += len(ordered)
            total_attempts += attempts
            pages.extend(entries)
            results.append(
                {
                    "canonical_start_ms": ordered[1],
                    "event_count": len(ordered),
                    "first_observed_settlement_ms": ordered[0],
                    "instrument_id": series.instrument_id,
                    "page_count": len(entries),
                    "predecessor_settlement_ms": ordered[0],
                    "symbol": series.symbol,
                }
            )
        manifest: dict[str, object] = {
            "adaptive_throttling": pacer.summary(),
            "completed_at_ms": now_ms(),
            "contract": BOUNDARY_MANIFEST_CONTRACT,
            "event_count": total_events,
            "http_attempt_count": total_attempts,
            "page_count": len(pages),
            "pages": pages,
            "plan_sha256": plan.plan_sha256,
            "results": results,
            "source_policy": _SOURCE_POLICY,
            "status": "complete",
            "symbol_count": len(results),
        }
        manifest_path = plan.job_root / "manifest.json"
        manifest_sha = _publish_with_receipt(manifest_path, manifest)
        _atomic_write_new(
            plan.job_root / "completion-receipt.json",
            _receipt_payload(manifest_path.name, manifest_sha),
        )
    except AdaptiveRateLimitAbort:
        raise
    finally:
        lock.rmdir()
    return verify_completed_funding_source_boundary(plan.job_root)


def verify_completed_funding_source_boundary(job_root: Path) -> CompletedFundingBoundary:
    """Verify plan, every timestamp-only page, manifest, receipts, and exact allowlist."""

    root = job_root.resolve()
    if not root.is_dir() or root.is_symlink() or (root / ".run-lock").exists():
        raise FundingSourceBoundaryError("funding boundary root is missing, unsafe, or active")
    plan, plan_sha = _verify_artifact(root / "plan.json")
    series, page_limit, target_rps, max_attempts, max_pages = _verified_plan(plan)
    if root.name != f"{plan.get('discovery_id')}--{plan_sha[:16]}":
        raise FundingSourceBoundaryError("funding boundary root does not bind plan")
    manifest, manifest_sha = _verify_artifact(root / "manifest.json")
    completion = _load_json_object(root / "completion-receipt.json", canonical=True)
    if completion != _receipt_payload("manifest.json", manifest_sha):
        raise FundingSourceBoundaryError("funding boundary completion receipt is invalid")
    results: list[dict[str, object]] = []
    pages: list[dict[str, object]] = []
    total_events = 0
    total_attempts = 0
    expected_files = {
        "completion-receipt.json",
        "manifest.json",
        "manifest.receipt.json",
        "plan.json",
        "plan.receipt.json",
    }
    for item in series:
        entries, timestamps, _end, attempts, terminal = _load_progress(
            root,
            item,
            page_limit=page_limit,
            max_attempts=max_attempts,
            max_pages_per_symbol=max_pages,
        )
        if not terminal or len(timestamps) < 2:
            raise FundingSourceBoundaryError("funding boundary result is incomplete")
        ordered = sorted(timestamps)
        pages.extend(entries)
        total_events += len(ordered)
        total_attempts += attempts
        results.append(
            {
                "canonical_start_ms": ordered[1],
                "event_count": len(ordered),
                "first_observed_settlement_ms": ordered[0],
                "instrument_id": item.instrument_id,
                "page_count": len(entries),
                "predecessor_settlement_ms": ordered[0],
                "symbol": item.symbol,
            }
        )
        for entry in entries:
            name = cast(str, entry["artifact"])
            expected_files.update((name, f"{name[:-5]}.receipt.json"))
    try:
        adaptive_summary = verify_adaptive_rate_summary(
            manifest.get("adaptive_throttling"),
            configured_target_rps=target_rps,
            maximum_response_count=total_attempts,
        )
    except AdaptiveRateLimitError as error:
        raise FundingSourceBoundaryError(
            "funding boundary adaptive throttling evidence is invalid"
        ) from error
    completed_at_ms = manifest.get("completed_at_ms")
    if (
        set(manifest) != _MANIFEST_KEYS
        or manifest.get("contract") != BOUNDARY_MANIFEST_CONTRACT
        or manifest.get("status") != "complete"
        or manifest.get("plan_sha256") != plan_sha
        or manifest.get("symbol_count") != len(series)
        or manifest.get("page_count") != len(pages)
        or manifest.get("event_count") != total_events
        or manifest.get("http_attempt_count") != total_attempts
        or manifest.get("pages") != pages
        or manifest.get("results") != results
        or manifest.get("adaptive_throttling") != adaptive_summary
        or manifest.get("source_policy") != _SOURCE_POLICY
        or isinstance(completed_at_ms, bool)
        or not isinstance(completed_at_ms, int)
        or completed_at_ms < 0
    ):
        raise FundingSourceBoundaryError("funding boundary manifest facts do not verify")
    actual_files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual_files != expected_files or any(path.is_symlink() for path in root.rglob("*")):
        raise FundingSourceBoundaryError("funding boundary contains orphan or missing files")
    if {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir()} != {
        "pages"
    }:
        raise FundingSourceBoundaryError("funding boundary directory inventory is invalid")
    return CompletedFundingBoundary(
        job_root=root,
        manifest_path=root / "manifest.json",
        receipt_path=root / "completion-receipt.json",
        manifest_sha256=manifest_sha,
        plan_sha256=plan_sha,
        request_sha256=cast(str, plan["request_sha256"]),
        registry_sha256=cast(str, plan["registry_sha256"]),
        software_identity=cast(str, plan["software_identity"]),
        scan_start_ms=cast(int, cast(dict[str, object], plan["request"])["start_ms"]),
        scan_end_ms=cast(int, cast(dict[str, object], plan["request"])["end_ms"]),
        symbol_count=len(series),
        page_count=len(pages),
        event_count=total_events,
        http_attempt_count=total_attempts,
        adaptive_throttling=adaptive_summary,
        results=tuple(
            FundingBoundaryResult(
                canonical_start_ms=cast(int, item["canonical_start_ms"]),
                event_count=cast(int, item["event_count"]),
                first_observed_settlement_ms=cast(int, item["first_observed_settlement_ms"]),
                instrument_id=cast(int, item["instrument_id"]),
                page_count=cast(int, item["page_count"]),
                predecessor_settlement_ms=cast(int, item["predecessor_settlement_ms"]),
                symbol=cast(str, item["symbol"]),
            )
            for item in results
        ),
    )
