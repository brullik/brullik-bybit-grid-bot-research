"""Bounded, paced, receipt-resumable Bybit V5 one-minute page acquisition."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from pathlib import Path
from threading import local
from typing import Final, Literal, Protocol, cast

from grid_bybit_public import BybitPublicError
from grid_bybit_public.transport import TransportError
from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file
from grid_contracts.market import MINUTE_MS, Candle1m, DatasetType, MarkCandle1m
from grid_market_store import (
    MAX_MEMORY_PERCENT,
    VOLUME_SCALE,
    CanonicalCandleBatch,
    CapacityBudget,
    HostSnapshot,
    build_empty_canonical_candle_batch,
    build_preordered_canonical_candle_batch,
    canonical_partition_path,
)

from grid_data.public_rate_limit import (
    AdaptiveRateLimitAbort,
    AdaptiveRateLimitError,
    AdaptiveRatePacer,
    verify_adaptive_rate_summary,
)

KlineKind = Literal["trade", "mark"]
Category = Literal["linear"]
HISTORY_PLAN_CONTRACT: Final = "grid.bybit-1m-history-plan/v1"
HISTORY_PAGE_CONTRACT: Final = "grid.bybit-1m-history-page/v1"
HISTORY_MANIFEST_CONTRACT: Final = "grid.bybit-1m-history-acquisition/v1"
RECEIPT_CONTRACT: Final = "grid.history-acquisition-receipt/v1"
MAX_WORKERS: Final = 32
MAX_TARGET_RPS: Final = 96
MAX_ATTEMPTS: Final = 5
MAX_HTTP_REQUESTS: Final = 100_000
MAX_SERIES: Final = 700
MAX_PAGE_ARTIFACT_BYTES: Final = 512 * 1024
STAGING_METADATA_BYTES: Final = 64 * 1024**2
MAX_PREFLIGHT_AGE_MS: Final = 60_000
UINT32_MAX: Final = (1 << 32) - 1
JOB_ID_RE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
QUARANTINE_POLICY: Final = "exact-source-row-quarantine-v1"
QUARANTINE_REASONS: Final = (
    "close_outside_low_high",
    "low_exceeds_high",
    "open_outside_low_high",
)
CANONICAL_ADMISSION_POLICY: Final = "canonical-candle-representation-admission-v1"
CANONICAL_ADMISSION_REASONS: Final = ("volume_exceeds_canonical_scale",)


class HistoryAcquisitionError(RuntimeError):
    """A history job cannot safely plan, resume, acquire, or verify."""


class KlineClient(Protocol):
    def kline_page(
        self,
        *,
        kind: KlineKind,
        symbol: str,
        start_ms: int,
        end_ms: int,
        category: Category = "linear",
        limit: int = 1000,
    ) -> tuple[tuple[str, ...], ...]: ...


@dataclass(frozen=True, slots=True)
class HistorySeries:
    kind: KlineKind
    category: Category
    symbol: str
    instrument_id: int
    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if self.kind not in ("trade", "mark") or self.category != "linear":
            raise HistoryAcquisitionError("unsupported kline kind or category")
        if not self.symbol or self.symbol != self.symbol.upper() or not self.symbol.isalnum():
            raise HistoryAcquisitionError("symbol must be uppercase alphanumeric text")
        if (
            isinstance(self.instrument_id, bool)
            or not isinstance(self.instrument_id, int)
            or not 1 <= self.instrument_id <= UINT32_MAX
        ):
            raise HistoryAcquisitionError("instrument_id must fit positive UInt32 storage")
        if (
            isinstance(self.start_ms, bool)
            or isinstance(self.end_ms, bool)
            or not isinstance(self.start_ms, int)
            or not isinstance(self.end_ms, int)
            or self.start_ms < 0
            or self.end_ms < self.start_ms
            or self.start_ms % MINUTE_MS
            or self.end_ms % MINUTE_MS
        ):
            raise HistoryAcquisitionError("history bounds must be aligned inclusive UTC minutes")

    @property
    def dataset_type(self) -> DatasetType:
        return DatasetType.TRADE_KLINE_1M if self.kind == "trade" else DatasetType.MARK_KLINE_1M


@dataclass(frozen=True, slots=True)
class HistoryJobSpec:
    job_id: str
    series: tuple[HistorySeries, ...]
    request_sha256: str
    instrument_evidence_sha256: str
    capacity_evidence_sha256: str
    page_limit: int = 1000
    workers: int = 24
    target_rps: int = 10
    max_attempts: int = 3
    max_http_requests: int = MAX_HTTP_REQUESTS

    def __post_init__(self) -> None:
        if not JOB_ID_RE.fullmatch(self.job_id):
            raise HistoryAcquisitionError("job_id must be a safe lowercase storage identity")
        if any(
            not SHA256_RE.fullmatch(value)
            for value in (
                self.request_sha256,
                self.instrument_evidence_sha256,
                self.capacity_evidence_sha256,
            )
        ):
            raise HistoryAcquisitionError("history job evidence bindings must be lowercase SHA-256")
        if not 1 <= len(self.series) <= MAX_SERIES:
            raise HistoryAcquisitionError(f"history series count must be in [1, {MAX_SERIES}]")
        if self.series != tuple(sorted(self.series, key=lambda item: item.instrument_id)):
            raise HistoryAcquisitionError("history series must be sorted by instrument_id")
        instrument_ids = [item.instrument_id for item in self.series]
        symbols = [item.symbol for item in self.series]
        if len(instrument_ids) != len(set(instrument_ids)) or len(symbols) != len(set(symbols)):
            raise HistoryAcquisitionError("history series instruments and symbols must be unique")
        if (
            isinstance(self.page_limit, bool)
            or not isinstance(self.page_limit, int)
            or not 1 <= self.page_limit <= 1000
        ):
            raise HistoryAcquisitionError("page_limit must be in [1, 1000]")
        if (
            isinstance(self.workers, bool)
            or not isinstance(self.workers, int)
            or not 1 <= self.workers <= MAX_WORKERS
        ):
            raise HistoryAcquisitionError(f"workers must be in [1, {MAX_WORKERS}]")
        if (
            isinstance(self.target_rps, bool)
            or not isinstance(self.target_rps, int)
            or not 1 <= self.target_rps <= MAX_TARGET_RPS
        ):
            raise HistoryAcquisitionError(f"target_rps must be in [1, {MAX_TARGET_RPS}]")
        if (
            isinstance(self.max_attempts, bool)
            or not isinstance(self.max_attempts, int)
            or not 1 <= self.max_attempts <= MAX_ATTEMPTS
        ):
            raise HistoryAcquisitionError(f"max_attempts must be in [1, {MAX_ATTEMPTS}]")
        if (
            isinstance(self.max_http_requests, bool)
            or not isinstance(self.max_http_requests, int)
            or not 1 <= self.max_http_requests <= MAX_HTTP_REQUESTS
        ):
            raise HistoryAcquisitionError(f"max_http_requests must be in [1, {MAX_HTTP_REQUESTS}]")
        first = self.series[0]
        expected_partition = canonical_partition_path(
            first.dataset_type,
            instrument_id=first.instrument_id,
            open_time_ms=first.start_ms,
        )
        for item in self.series:
            for timestamp in (item.start_ms, item.end_ms):
                partition = canonical_partition_path(
                    item.dataset_type,
                    instrument_id=item.instrument_id,
                    open_time_ms=timestamp,
                )
                if partition != expected_partition:
                    raise HistoryAcquisitionError(
                        "one acquisition job must fit one dataset/month/bucket partition"
                    )


@dataclass(frozen=True, slots=True)
class HistoryPageTask:
    sequence: int
    kind: KlineKind
    category: Category
    symbol: str
    instrument_id: int
    start_ms: int
    end_ms: int
    limit: int

    @property
    def artifact_name(self) -> str:
        return f"{self.sequence:08d}.json"


@dataclass(frozen=True, slots=True)
class HistoryJobPaths:
    staging_root: Path
    job_root: Path
    pages_root: Path
    plan_path: Path
    plan_receipt_path: Path
    manifest_path: Path
    receipt_path: Path
    run_lock: Path


@dataclass(frozen=True, slots=True)
class HistoryJobPlan:
    spec: HistoryJobSpec
    budget: CapacityBudget
    snapshot: HostSnapshot
    paths: HistoryJobPaths
    tasks: tuple[HistoryPageTask, ...]
    pending_tasks: tuple[HistoryPageTask, ...]
    plan_sha256: str
    required_free_bytes: int
    planned_peak_memory_bytes: int
    existing_completed: CompletedHistoryJob | None

    @property
    def existing_complete(self) -> bool:
        return self.existing_completed is not None


@dataclass(frozen=True, slots=True)
class CompletedHistoryJob:
    job_root: Path
    plan_path: Path
    manifest_path: Path
    receipt_path: Path
    manifest_sha256: str
    page_count: int
    row_count: int
    quarantined_row_count: int
    quarantined_source_keys: tuple[tuple[int, int], ...] | None


@dataclass(frozen=True, slots=True)
class CanonicalCandleAdmission:
    policy: str
    source_row_count: int
    admitted_row_count: int
    excluded_row_count: int
    excluded_rows_sha256: str
    reason_counts: dict[str, int]
    excluded_source_keys: tuple[tuple[int, int], ...]

    def public_payload(self) -> dict[str, object]:
        return {
            "admitted_row_count": self.admitted_row_count,
            "excluded_row_count": self.excluded_row_count,
            "excluded_rows_sha256": self.excluded_rows_sha256,
            "policy": self.policy,
            "reason_counts": dict(self.reason_counts),
            "source_row_count": self.source_row_count,
        }


@dataclass(frozen=True, slots=True)
class PageSourceQuality:
    source_row_count: int
    quarantined_row_count: int
    quarantined_rows_sha256: str
    reason_counts: dict[str, int]


def _plan_tasks(spec: HistoryJobSpec) -> tuple[HistoryPageTask, ...]:
    tasks: list[HistoryPageTask] = []
    page_span = spec.page_limit * MINUTE_MS
    for item in spec.series:
        page_start = item.start_ms
        while page_start <= item.end_ms:
            page_end = min(item.end_ms, page_start + page_span - MINUTE_MS)
            tasks.append(
                HistoryPageTask(
                    sequence=len(tasks),
                    kind=item.kind,
                    category=item.category,
                    symbol=item.symbol,
                    instrument_id=item.instrument_id,
                    start_ms=page_start,
                    end_ms=page_end,
                    limit=spec.page_limit,
                )
            )
            page_start = page_end + MINUTE_MS
    return tuple(tasks)


def required_rest_staging_bytes(spec: HistoryJobSpec) -> int:
    """Return the complete, deterministic Landing byte bound for one request."""

    return STAGING_METADATA_BYTES + len(_plan_tasks(spec)) * MAX_PAGE_ARTIFACT_BYTES


def _plan_payload(
    spec: HistoryJobSpec,
    tasks: Sequence[HistoryPageTask],
    budget: CapacityBudget,
) -> dict[str, object]:
    return {
        "capacity_budget": budget,
        "contract": HISTORY_PLAN_CONTRACT,
        "spec": spec,
        "tasks": tuple(tasks),
    }


def _paths(staging_root: Path, spec: HistoryJobSpec, plan_sha256: str) -> HistoryJobPaths:
    root = staging_root.resolve()
    job_root = root / ".landing" / f"{spec.job_id}--{plan_sha256[:16]}"
    return HistoryJobPaths(
        staging_root=root,
        job_root=job_root,
        pages_root=job_root / "pages",
        plan_path=job_root / "plan.json",
        plan_receipt_path=job_root / "plan.receipt.json",
        manifest_path=job_root / "manifest.json",
        receipt_path=job_root / "completion-receipt.json",
        run_lock=job_root / ".run-lock",
    )


def _receipt_payload(artifact_name: str, artifact_sha256: str) -> dict[str, object]:
    return {
        "artifact": artifact_name,
        "artifact_sha256": artifact_sha256,
        "contract": RECEIPT_CONTRACT,
        "status": "complete",
    }


def _atomic_write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise HistoryAcquisitionError(f"refusing to replace acquisition artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".building",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _publish_artifact(path: Path, payload: Mapping[str, object]) -> str:
    data = canonical_json_bytes(payload)
    _atomic_write_new(path, data)
    digest = sha256_file(path)
    receipt = path.with_suffix(".receipt.json")
    _atomic_write_new(receipt, canonical_json_bytes(_receipt_payload(path.name, digest)))
    return digest


def _load_object(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryAcquisitionError(f"cannot load acquisition JSON: {path}") from error
    if not isinstance(raw, dict) or canonical_json_bytes(raw) != path.read_bytes():
        raise HistoryAcquisitionError(f"acquisition JSON is not a canonical object: {path}")
    return cast(dict[str, object], raw)


def _verify_artifact(path: Path) -> tuple[dict[str, object], str]:
    receipt_path = path.with_suffix(".receipt.json")
    if not path.is_file() or not receipt_path.is_file():
        raise HistoryAcquisitionError(f"artifact/receipt pair is incomplete: {path}")
    payload = _load_object(path)
    receipt = _load_object(receipt_path)
    digest = sha256_file(path)
    if receipt != _receipt_payload(path.name, digest):
        raise HistoryAcquisitionError(f"artifact receipt does not verify: {path}")
    if path.parent.name == "pages" and path.stat().st_size > MAX_PAGE_ARTIFACT_BYTES:
        raise HistoryAcquisitionError(f"staged page exceeds its byte bound: {path}")
    return payload, digest


def _verify_artifact_digest(path: Path) -> str:
    """Verify immutable artifact bytes against the canonical receipt without decoding payload."""

    receipt_path = path.with_suffix(".receipt.json")
    if not path.is_file() or not receipt_path.is_file():
        raise HistoryAcquisitionError(f"artifact/receipt pair is incomplete: {path}")
    receipt = _load_object(receipt_path)
    digest = sha256_file(path)
    if receipt != _receipt_payload(path.name, digest):
        raise HistoryAcquisitionError(f"artifact receipt does not verify: {path}")
    if path.parent.name == "pages" and path.stat().st_size > MAX_PAGE_ARTIFACT_BYTES:
        raise HistoryAcquisitionError("staged page exceeds its fixed artifact byte bound")
    return digest


def _assert_fresh(snapshot: HostSnapshot, *, now_ms: int) -> None:
    age = now_ms - snapshot.observed_at_ms
    if age < 0 or age > MAX_PREFLIGHT_AGE_MS:
        raise HistoryAcquisitionError("host snapshot must be fresh and not future-dated")


def _assert_target_volume(staging_root: Path, snapshot: HostSnapshot) -> None:
    resolved = staging_root.resolve()
    if not resolved.is_relative_to(snapshot.volume_root.resolve()):
        raise HistoryAcquisitionError("staging root is outside the observed local volume")
    existing = resolved
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    if not existing.is_dir() or existing.is_symlink():
        raise HistoryAcquisitionError("staging requires an existing non-symlink directory ancestor")


def _resource_requirements(
    task_count: int,
    pending_count: int,
    spec: HistoryJobSpec,
    budget: CapacityBudget,
) -> tuple[int, int]:
    full_staging = STAGING_METADATA_BYTES + task_count * MAX_PAGE_ARTIFACT_BYTES
    if budget.rest_staging_bytes < full_staging:
        raise HistoryAcquisitionError(
            f"REST staging budget must be at least {full_staging} bytes for this plan"
        )
    remaining_staging = STAGING_METADATA_BYTES + pending_count * MAX_PAGE_ARTIFACT_BYTES
    required_free = (
        budget.active_and_building_bytes + budget.operating_reserve_bytes + remaining_staging
    )
    planned_memory = 128 * 1024**2 + spec.workers * MAX_PAGE_ARTIFACT_BYTES
    return required_free, planned_memory


def _assert_resources(
    snapshot: HostSnapshot,
    *,
    required_free_bytes: int,
    planned_peak_memory_bytes: int,
) -> None:
    if snapshot.volume_free_bytes < required_free_bytes:
        raise HistoryAcquisitionError(
            "insufficient free space for active/building data, bounded REST staging, and reserve"
        )
    if planned_peak_memory_bytes > snapshot.memory_available_bytes:
        raise HistoryAcquisitionError("insufficient available memory for acquisition workers")
    if planned_peak_memory_bytes * 100 > snapshot.memory_total_bytes * MAX_MEMORY_PERCENT:
        raise HistoryAcquisitionError("acquisition plan exceeds the 70% total-memory gate")


def _task_page_path(paths: HistoryJobPaths, task: HistoryPageTask) -> Path:
    return paths.pages_root / task.artifact_name


def _validate_page_payload_rows(
    payload: Mapping[str, object],
    task: HistoryPageTask,
    *,
    ingestion_id: str,
) -> tuple[PageSourceQuality, tuple[Candle1m | MarkCandle1m, ...]]:
    expected = {
        "category": task.category,
        "end_ms": task.end_ms,
        "instrument_id": task.instrument_id,
        "kind": task.kind,
        "limit": task.limit,
        "sequence": task.sequence,
        "start_ms": task.start_ms,
        "symbol": task.symbol,
    }
    if payload.get("contract") != HISTORY_PAGE_CONTRACT or any(
        payload.get(name) != value for name, value in expected.items()
    ):
        raise HistoryAcquisitionError(f"staged page identity mismatch: {task.sequence}")
    attempts = payload.get("attempt_count")
    rows = payload.get("rows")
    if not isinstance(attempts, int) or not 1 <= attempts <= MAX_ATTEMPTS:
        raise HistoryAcquisitionError("staged page has invalid attempt count")
    if not isinstance(rows, list):
        raise HistoryAcquisitionError("staged page rows must be an array")
    typed_rows: list[tuple[str, ...]] = []
    for row in rows:
        if not isinstance(row, list) or any(not isinstance(value, str) for value in row):
            raise HistoryAcquisitionError("staged page rows must contain string arrays")
        typed_rows.append(tuple(row))
    extension_names = {
        "quarantined_row_count",
        "quarantined_rows",
        "quarantined_rows_sha256",
        "source_row_count",
    }
    present_extensions = extension_names.intersection(payload)
    if present_extensions and present_extensions != extension_names:
        raise HistoryAcquisitionError("staged page quarantine extension is incomplete")
    if present_extensions:
        raw_quarantined = payload.get("quarantined_rows")
        source_row_count = payload.get("source_row_count")
        quarantined_row_count = payload.get("quarantined_row_count")
        quarantined_rows_sha256 = payload.get("quarantined_rows_sha256")
        if (
            not isinstance(raw_quarantined, list)
            or isinstance(source_row_count, bool)
            or not isinstance(source_row_count, int)
            or isinstance(quarantined_row_count, bool)
            or not isinstance(quarantined_row_count, int)
            or not isinstance(quarantined_rows_sha256, str)
            or SHA256_RE.fullmatch(quarantined_rows_sha256) is None
            or source_row_count != len(rows) + len(raw_quarantined)
            or quarantined_row_count != len(raw_quarantined)
            or not 0 <= source_row_count <= task.limit
            or canonical_sha256(raw_quarantined) != quarantined_rows_sha256
        ):
            raise HistoryAcquisitionError("staged page quarantine count/hash is invalid")
        source_rows: list[tuple[str, ...] | None] = [None] * source_row_count
        for raw_entry in raw_quarantined:
            if not isinstance(raw_entry, dict) or set(raw_entry) != {
                "reason",
                "row",
                "source_index",
                "source_row_sha256",
            }:
                raise HistoryAcquisitionError("staged page quarantine entry is invalid")
            source_index = raw_entry.get("source_index")
            raw_row = raw_entry.get("row")
            reason = raw_entry.get("reason")
            source_row_sha256 = raw_entry.get("source_row_sha256")
            if (
                isinstance(source_index, bool)
                or not isinstance(source_index, int)
                or not 0 <= source_index < source_row_count
                or source_rows[source_index] is not None
                or not isinstance(raw_row, list)
                or any(not isinstance(value, str) for value in raw_row)
                or reason not in QUARANTINE_REASONS
                or not isinstance(source_row_sha256, str)
                or source_row_sha256 != canonical_sha256(raw_row)
            ):
                raise HistoryAcquisitionError("staged page quarantine entry is invalid")
            source_rows[source_index] = tuple(raw_row)
        admitted = iter(typed_rows)
        for index, source_row in enumerate(source_rows):
            if source_row is None:
                source_rows[index] = next(admitted)
        try:
            next(admitted)
        except StopIteration:
            pass
        else:  # pragma: no cover - guarded by source_row_count arithmetic
            raise HistoryAcquisitionError("staged page admitted row inventory is invalid")
        verified_rows, verified_quarantine, logical_rows = _partition_source_rows(
            task,
            cast(list[tuple[str, ...]], source_rows),
            ingestion_id=ingestion_id,
        )
        if [list(row) for row in verified_rows] != rows or verified_quarantine != raw_quarantined:
            raise HistoryAcquisitionError("staged page quarantine classification does not verify")
        reason_counts = {
            reason: sum(entry["reason"] == reason for entry in verified_quarantine)
            for reason in QUARANTINE_REASONS
        }
        quality = PageSourceQuality(
            source_row_count=source_row_count,
            quarantined_row_count=quarantined_row_count,
            quarantined_rows_sha256=quarantined_rows_sha256,
            reason_counts=reason_counts,
        )
    else:
        if len(rows) > task.limit:
            raise HistoryAcquisitionError("staged page exceeds its requested row limit")
        logical_rows = _logical_rows(task, typed_rows, ingestion_id=ingestion_id)
        quality = PageSourceQuality(
            source_row_count=len(rows),
            quarantined_row_count=0,
            quarantined_rows_sha256=canonical_sha256([]),
            reason_counts={reason: 0 for reason in QUARANTINE_REASONS},
        )
    expected_rows_sha = canonical_sha256(rows)
    if payload.get("rows_sha256") != expected_rows_sha or payload.get("row_count") != len(rows):
        raise HistoryAcquisitionError("staged page row hash/count mismatch")
    return quality, logical_rows


def _validate_page_payload(
    payload: Mapping[str, object], task: HistoryPageTask
) -> PageSourceQuality:
    quality, _logical = _validate_page_payload_rows(
        payload,
        task,
        ingestion_id="history-page-verification",
    )
    return quality


def _existing_state(
    paths: HistoryJobPaths,
    plan_payload: Mapping[str, object],
    tasks: tuple[HistoryPageTask, ...],
) -> tuple[tuple[HistoryPageTask, ...], CompletedHistoryJob | None]:
    if not paths.job_root.exists():
        return tasks, None
    if not paths.job_root.is_dir() or paths.job_root.is_symlink() or paths.run_lock.exists():
        raise HistoryAcquisitionError("acquisition job has an unsafe or stale run directory")
    observed_plan, _digest = _verify_artifact(paths.plan_path)
    if canonical_json_bytes(observed_plan) != canonical_json_bytes(plan_payload):
        raise HistoryAcquisitionError("existing acquisition plan does not match the requested plan")
    if paths.receipt_path.exists() or paths.manifest_path.exists():
        completed = verify_completed_history_job_integrity(paths.job_root)
        if completed.page_count != len(tasks):
            raise HistoryAcquisitionError(
                "completed acquisition page count differs from deterministic plan"
            )
        return (), completed
    pending: list[HistoryPageTask] = []
    expected_page_files: set[str] = set()
    for task in tasks:
        page = _task_page_path(paths, task)
        receipt = page.with_suffix(".receipt.json")
        expected_page_files.update((page.name, receipt.name))
        if page.exists() != receipt.exists():
            raise HistoryAcquisitionError(f"partial staged page detected: {task.sequence}")
        if not page.exists():
            pending.append(task)
            continue
        payload, _page_digest = _verify_artifact(page)
        _validate_page_payload(payload, task)
    actual_page_files = (
        {path.name for path in paths.pages_root.iterdir()} if paths.pages_root.exists() else set()
    )
    if not actual_page_files.issubset(expected_page_files):
        raise HistoryAcquisitionError("acquisition pages directory contains orphan files")
    return tuple(pending), None


def preflight_history_job(
    staging_root: Path,
    spec: HistoryJobSpec,
    budget: CapacityBudget,
    snapshot: HostSnapshot,
    *,
    now_ms: int,
    closed_before_ms: int,
) -> HistoryJobPlan:
    """Plan fixed non-overlapping pages and inspect resume state without mutation."""

    if (
        isinstance(closed_before_ms, bool)
        or not isinstance(closed_before_ms, int)
        or closed_before_ms < 0
        or closed_before_ms % MINUTE_MS
    ):
        raise HistoryAcquisitionError("closed_before_ms must be an aligned UTC minute")
    if any(item.end_ms >= closed_before_ms for item in spec.series):
        raise HistoryAcquisitionError("history jobs may acquire only closed one-minute candles")
    tasks = _plan_tasks(spec)
    if len(tasks) * spec.max_attempts > spec.max_http_requests:
        raise HistoryAcquisitionError("full plan retry bound exceeds max_http_requests")
    plan_payload = _plan_payload(spec, tasks, budget)
    plan_sha = canonical_sha256(plan_payload)
    paths = _paths(staging_root, spec, plan_sha)
    _assert_fresh(snapshot, now_ms=now_ms)
    _assert_target_volume(paths.staging_root, snapshot)
    pending, existing_completed = _existing_state(paths, plan_payload, tasks)
    if len(pending) * spec.max_attempts > spec.max_http_requests:
        raise HistoryAcquisitionError("resume retry bound exceeds max_http_requests")
    required_free, planned_memory = _resource_requirements(
        len(tasks),
        len(pending),
        spec,
        budget,
    )
    _assert_resources(
        snapshot,
        required_free_bytes=required_free,
        planned_peak_memory_bytes=planned_memory,
    )
    return HistoryJobPlan(
        spec=spec,
        budget=budget,
        snapshot=snapshot,
        paths=paths,
        tasks=tasks,
        pending_tasks=pending,
        plan_sha256=plan_sha,
        required_free_bytes=required_free,
        planned_peak_memory_bytes=planned_memory,
        existing_completed=existing_completed,
    )


def _parse_decimal(name: str, raw: str) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as error:
        raise HistoryAcquisitionError(f"{name} is not exact decimal text") from error
    if not value.is_finite():
        raise HistoryAcquisitionError(f"{name} must be finite")
    return value


def _logical_rows(
    task: HistoryPageTask,
    rows: Sequence[tuple[str, ...]],
    *,
    ingestion_id: str,
) -> tuple[Candle1m | MarkCandle1m, ...]:
    timestamps: list[int] = []
    logical: list[Candle1m | MarkCandle1m] = []
    for row in rows:
        timestamp, parsed, quarantine_reason = _parse_source_row(
            task,
            row,
            ingestion_id=ingestion_id,
        )
        timestamps.append(timestamp)
        if quarantine_reason is not None or parsed is None:
            raise HistoryAcquisitionError("Bybit kline violates the logical candle contract")
        logical.append(parsed)
    _assert_reverse_chronological(timestamps)
    return tuple(logical)


def _parse_source_row(
    task: HistoryPageTask,
    row: tuple[str, ...],
    *,
    ingestion_id: str,
) -> tuple[int, Candle1m | MarkCandle1m | None, str | None]:
    expected_width = 7 if task.kind == "trade" else 5
    if len(row) != expected_width or not row[0].isdigit():
        raise HistoryAcquisitionError("Bybit kline row has invalid width or timestamp")
    timestamp = int(row[0])
    if timestamp < task.start_ms or timestamp > task.end_ms or timestamp % MINUTE_MS:
        raise HistoryAcquisitionError("Bybit kline timestamp escapes its planned page")
    prices = {
        "open": _parse_decimal("open", row[1]),
        "high": _parse_decimal("high", row[2]),
        "low": _parse_decimal("low", row[3]),
        "close": _parse_decimal("close", row[4]),
    }
    if any(value <= 0 for value in prices.values()):
        raise HistoryAcquisitionError("Bybit kline violates the logical candle contract")
    reason: str | None = None
    if prices["low"] > prices["high"]:
        reason = "low_exceeds_high"
    elif not prices["low"] <= prices["open"] <= prices["high"]:
        reason = "open_outside_low_high"
    elif not prices["low"] <= prices["close"] <= prices["high"]:
        reason = "close_outside_low_high"
    volume: Decimal | None = None
    turnover: Decimal | None = None
    if task.kind == "trade":
        volume = _parse_decimal("volume", row[5])
        turnover = _parse_decimal("turnover", row[6])
        if volume < 0 or turnover < 0:
            raise HistoryAcquisitionError("Bybit kline violates the logical candle contract")
    if reason is not None:
        return timestamp, None, reason
    common = {
        "category": task.category,
        "instrument_id": task.instrument_id,
        "open_time_ms": timestamp,
        **prices,
        "source_id": ("bybit-v5-kline/v1" if task.kind == "trade" else "bybit-v5-mark-kline/v1"),
        "ingestion_id": ingestion_id,
        "quality_flags": 0,
    }
    try:
        logical: Candle1m | MarkCandle1m
        if task.kind == "trade":
            assert volume is not None and turnover is not None
            logical = Candle1m(
                **common,  # type: ignore[arg-type]
                volume=volume,
                turnover=turnover,
            )
        else:
            logical = MarkCandle1m(**common)  # type: ignore[arg-type]
    except ValueError as error:
        raise HistoryAcquisitionError("Bybit kline violates the logical candle contract") from error
    return timestamp, logical, None


def _assert_reverse_chronological(timestamps: Sequence[int]) -> None:
    if any(newer <= older for newer, older in pairwise(timestamps)):
        raise HistoryAcquisitionError("Bybit kline page must be unique reverse chronological data")


def _partition_source_rows(
    task: HistoryPageTask,
    rows: Sequence[tuple[str, ...]],
    *,
    ingestion_id: str,
) -> tuple[
    tuple[tuple[str, ...], ...],
    list[dict[str, object]],
    tuple[Candle1m | MarkCandle1m, ...],
]:
    """Admit exact logical rows and retain only recognized OHLC anomalies verbatim."""

    timestamps: list[int] = []
    admitted: list[tuple[str, ...]] = []
    quarantined: list[dict[str, object]] = []
    logical: list[Candle1m | MarkCandle1m] = []
    for source_index, row in enumerate(rows):
        timestamp, parsed, reason = _parse_source_row(
            task,
            row,
            ingestion_id=ingestion_id,
        )
        timestamps.append(timestamp)
        if reason is None:
            assert parsed is not None
            admitted.append(row)
            logical.append(parsed)
        else:
            serialized = list(row)
            quarantined.append(
                {
                    "reason": reason,
                    "row": serialized,
                    "source_index": source_index,
                    "source_row_sha256": canonical_sha256(serialized),
                }
            )
    _assert_reverse_chronological(timestamps)
    return tuple(admitted), quarantined, tuple(logical)


def _page_payload(
    task: HistoryPageTask, rows: Sequence[tuple[str, ...]], attempts: int
) -> dict[str, object]:
    admitted, quarantined, _logical = _partition_source_rows(
        task,
        rows,
        ingestion_id="history-page-validation",
    )
    serialized_rows = [list(row) for row in admitted]
    return {
        "attempt_count": attempts,
        "category": task.category,
        "contract": HISTORY_PAGE_CONTRACT,
        "end_ms": task.end_ms,
        "instrument_id": task.instrument_id,
        "kind": task.kind,
        "limit": task.limit,
        "quarantined_row_count": len(quarantined),
        "quarantined_rows": quarantined,
        "quarantined_rows_sha256": canonical_sha256(quarantined),
        "row_count": len(serialized_rows),
        "rows": serialized_rows,
        "rows_sha256": canonical_sha256(serialized_rows),
        "sequence": task.sequence,
        "source_row_count": len(rows),
        "start_ms": task.start_ms,
        "symbol": task.symbol,
    }


def _fetch_page(
    task: HistoryPageTask,
    *,
    client: KlineClient,
    pacer: AdaptiveRatePacer,
    max_attempts: int,
) -> dict[str, object]:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        pacer.wait()
        try:
            try:
                rows = client.kline_page(
                    kind=task.kind,
                    symbol=task.symbol,
                    start_ms=task.start_ms,
                    end_ms=task.end_ms,
                    category=task.category,
                    limit=task.limit,
                )
            finally:
                pacer.observe_client(client)
            payload = _page_payload(task, rows, attempt)
            if len(canonical_json_bytes(payload)) > MAX_PAGE_ARTIFACT_BYTES:
                raise HistoryAcquisitionError("staged page exceeds its preflighted byte bound")
            return payload
        except TransportError as error:
            if error.failure_class == "regional-access-block":
                raise AdaptiveRateLimitAbort(
                    "Bybit public API is unavailable from the current region; resume only "
                    "from an officially supported network and region",
                    reason="regional-access-block",
                ) from error
            last_error = error
            if attempt < max_attempts:
                time.sleep(min(4.0, 0.25 * (2 ** (attempt - 1))))
        except BybitPublicError as error:
            last_error = error
            if attempt < max_attempts:
                time.sleep(min(4.0, 0.25 * (2 ** (attempt - 1))))
    raise HistoryAcquisitionError(
        f"history page {task.sequence} failed after {max_attempts} attempts"
    ) from last_error


def _assert_execute_snapshot(plan: HistoryJobPlan, snapshot: HostSnapshot, *, now_ms: int) -> None:
    _assert_fresh(snapshot, now_ms=now_ms)
    _assert_target_volume(plan.paths.staging_root, snapshot)
    if (
        snapshot.device_identity_sha256 != plan.snapshot.device_identity_sha256
        or snapshot.memory_total_bytes != plan.snapshot.memory_total_bytes
    ):
        raise HistoryAcquisitionError(
            "host or storage identity changed after acquisition preflight"
        )
    _assert_resources(
        snapshot,
        required_free_bytes=plan.required_free_bytes,
        planned_peak_memory_bytes=plan.planned_peak_memory_bytes,
    )


def _publish_plan_if_new(plan: HistoryJobPlan) -> None:
    if plan.paths.plan_path.exists():
        return
    _publish_artifact(
        plan.paths.plan_path,
        _plan_payload(plan.spec, plan.tasks, plan.budget),
    )


def execute_history_job(
    plan: HistoryJobPlan,
    client_factory: Callable[[], KlineClient],
    snapshot_provider: Callable[[], HostSnapshot],
    *,
    now_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
) -> CompletedHistoryJob:
    """Fetch only missing fixed pages and publish the job receipt after final verification."""

    if plan.existing_complete:
        return verify_completed_history_job_integrity(plan.paths.job_root)
    start_snapshot = snapshot_provider()
    start_now = now_ms()
    _assert_execute_snapshot(plan, start_snapshot, now_ms=start_now)
    plan.paths.pages_root.mkdir(parents=True, exist_ok=True)
    try:
        plan.paths.run_lock.mkdir()
    except FileExistsError as error:
        raise HistoryAcquisitionError(
            "acquisition job already has an active or stale run lock"
        ) from error
    thread_state = local()
    pacer = AdaptiveRatePacer(plan.spec.target_rps)

    def acquire(task: HistoryPageTask) -> tuple[int, str, int]:
        client = getattr(thread_state, "client", None)
        if client is None:
            client = client_factory()
            thread_state.client = client
        payload = _fetch_page(
            task,
            client=client,
            pacer=pacer,
            max_attempts=plan.spec.max_attempts,
        )
        page = _task_page_path(plan.paths, task)
        digest = _publish_artifact(page, payload)
        return task.sequence, digest, cast(int, payload["row_count"])

    try:
        _publish_plan_if_new(plan)
        with ThreadPoolExecutor(max_workers=plan.spec.workers) as executor:
            futures = {executor.submit(acquire, task): task for task in plan.pending_tasks}
            for future in as_completed(futures):
                try:
                    future.result()
                except AdaptiveRateLimitAbort as error:
                    if error.reason == "regional-access-block":
                        raise HistoryAcquisitionError(
                            "history acquisition stopped because Bybit public API is unavailable "
                            "from the current region; resume only from an officially supported "
                            "network and region"
                        ) from error
                    raise HistoryAcquisitionError(
                        "history acquisition stopped by the adaptive rate-limit policy"
                    ) from error
        finish_snapshot = snapshot_provider()
        finish_now = now_ms()
        _assert_execute_snapshot(plan, finish_snapshot, now_ms=finish_now)
        page_inventory: list[dict[str, object]] = []
        quarantine_bindings: list[dict[str, object]] = []
        quarantined_source_keys: list[tuple[int, int]] = []
        quarantine_reason_counts = {reason: 0 for reason in QUARANTINE_REASONS}
        total_rows = 0
        total_source_rows = 0
        total_quarantined_rows = 0
        empty_pages = 0
        for task in plan.tasks:
            page = _task_page_path(plan.paths, task)
            payload, digest = _verify_artifact(page)
            quality = _validate_page_payload(payload, task)
            row_count = cast(int, payload["row_count"])
            total_rows += row_count
            total_source_rows += quality.source_row_count
            total_quarantined_rows += quality.quarantined_row_count
            for reason, count in quality.reason_counts.items():
                quarantine_reason_counts[reason] += count
            empty_pages += row_count == 0
            if quality.quarantined_row_count:
                raw_quarantined_rows = payload.get("quarantined_rows")
                if not isinstance(raw_quarantined_rows, list):  # pragma: no cover - validated
                    raise HistoryAcquisitionError("staged page quarantine rows are invalid")
                for raw_entry in raw_quarantined_rows:
                    if not isinstance(raw_entry, dict):  # pragma: no cover - validated
                        raise HistoryAcquisitionError("staged page quarantine entry is invalid")
                    raw_row = raw_entry.get("row")
                    if not isinstance(raw_row, list):  # pragma: no cover - validated
                        raise HistoryAcquisitionError("staged quarantined source row is invalid")
                    quarantined_source_keys.append((task.instrument_id, int(cast(str, raw_row[0]))))
                quarantine_bindings.append(
                    {
                        "page_artifact_sha256": digest,
                        "quarantined_row_count": quality.quarantined_row_count,
                        "quarantined_rows_sha256": quality.quarantined_rows_sha256,
                    }
                )
            page_inventory.append(
                {
                    "artifact": f"pages/{page.name}",
                    "artifact_sha256": digest,
                    "attempt_count": payload["attempt_count"],
                    "end_ms": task.end_ms,
                    "ingestion_id": f"bybit-page-sha256:{digest}",
                    "instrument_id": task.instrument_id,
                    "quarantine_reason_counts": quality.reason_counts,
                    "quarantined_row_count": quality.quarantined_row_count,
                    "quarantined_rows_sha256": quality.quarantined_rows_sha256,
                    "row_count": row_count,
                    "sequence": task.sequence,
                    "source_row_count": quality.source_row_count,
                    "start_ms": task.start_ms,
                    "symbol": task.symbol,
                }
            )
        manifest: dict[str, object] = {
            "capacity_evidence_sha256": plan.spec.capacity_evidence_sha256,
            "completed_at_ms": finish_now,
            "contract": HISTORY_MANIFEST_CONTRACT,
            "empty_page_count": empty_pages,
            "host_preflight": {
                "device_identity_sha256": plan.snapshot.device_identity_sha256,
                "memory_total_bytes": plan.snapshot.memory_total_bytes,
                "observed_at_ms": plan.snapshot.observed_at_ms,
                "observed_free_bytes": plan.snapshot.volume_free_bytes,
                "planned_peak_memory_bytes": plan.planned_peak_memory_bytes,
                "required_free_bytes": plan.required_free_bytes,
                "storage_kind": plan.snapshot.storage_kind,
            },
            "instrument_evidence_sha256": plan.spec.instrument_evidence_sha256,
            "job_id": plan.spec.job_id,
            "page_count": len(plan.tasks),
            "pages": page_inventory,
            "plan_sha256": plan.plan_sha256,
            "request_sha256": plan.spec.request_sha256,
            "request_bound": {
                "actual_http_requests": sum(
                    cast(int, item["attempt_count"]) for item in page_inventory
                ),
                "adaptive_throttling": pacer.summary(),
                "max_attempts_per_page": plan.spec.max_attempts,
                "max_http_requests_per_run": plan.spec.max_http_requests,
                "target_rps": plan.spec.target_rps,
                "workers": plan.spec.workers,
            },
            "row_count": total_rows,
            "source_quality": {
                "admitted_row_count": total_rows,
                "policy": QUARANTINE_POLICY,
                "quarantined_row_count": total_quarantined_rows,
                "quarantined_rows_sha256": canonical_sha256(quarantine_bindings),
                "reason_counts": quarantine_reason_counts,
                "source_row_count": total_source_rows,
            },
            "source_policy": {
                "mark": "/v5/market/mark-price-kline",
                "trade": "/v5/market/kline",
                "interval": "1",
                "tick_rows_requested": False,
            },
            "started_at_ms": start_now,
            "status": "complete",
        }
        _publish_artifact(plan.paths.manifest_path, manifest)
        manifest_digest = sha256_file(plan.paths.manifest_path)
        _atomic_write_new(
            plan.paths.receipt_path,
            canonical_json_bytes(
                {
                    "artifact": plan.paths.manifest_path.name,
                    "artifact_sha256": manifest_digest,
                    "contract": RECEIPT_CONTRACT,
                    "status": "complete",
                }
            ),
        )
    finally:
        plan.paths.run_lock.rmdir()
    # Every page was semantically admitted immediately above before the receipt-last commit.
    # Reverify the immutable chain and allowlist here without decoding the same market rows twice.
    completed = verify_completed_history_job_integrity(plan.paths.job_root)
    if len(quarantined_source_keys) != completed.quarantined_row_count:
        raise HistoryAcquisitionError("completed quarantine key inventory changed after admission")
    return replace(completed, quarantined_source_keys=tuple(quarantined_source_keys))


def _verify_completed_history_job(
    job_root: Path,
    *,
    load_batch: bool,
    verify_page_semantics: bool = True,
    admit_canonical_representation: bool = False,
) -> tuple[
    CompletedHistoryJob,
    CanonicalCandleBatch | None,
    CanonicalCandleAdmission | None,
]:
    """Verify once and optionally build the exact batch from those same verified page bytes."""

    root = job_root.resolve()
    if not root.is_dir() or root.is_symlink() or (root / ".run-lock").exists():
        raise HistoryAcquisitionError("history job root is missing, unsafe, or active")
    plan_path = root / "plan.json"
    plan_payload, plan_digest = _verify_artifact(plan_path)
    if plan_payload.get("contract") != HISTORY_PLAN_CONTRACT:
        raise HistoryAcquisitionError("unsupported history plan contract")
    raw_tasks = plan_payload.get("tasks")
    raw_spec = plan_payload.get("spec")
    raw_budget = plan_payload.get("capacity_budget")
    if (
        not isinstance(raw_tasks, list)
        or not isinstance(raw_spec, dict)
        or not isinstance(raw_budget, dict)
    ):
        raise HistoryAcquisitionError("history plan has no spec/task inventory")
    try:
        raw_series = raw_spec.get("series")
        if not isinstance(raw_series, list):
            raise TypeError("series is not an array")
        verified_spec = HistoryJobSpec(
            **{
                **raw_spec,
                "series": tuple(HistorySeries(**item) for item in raw_series),
            }
        )
        verified_budget = CapacityBudget(**raw_budget)
    except (TypeError, ValueError) as error:
        raise HistoryAcquisitionError("history plan spec or capacity budget is invalid") from error
    expected_tasks = _plan_tasks(verified_spec)
    if raw_tasks != json.loads(canonical_json_bytes(expected_tasks)):
        raise HistoryAcquisitionError("history task inventory does not derive from the plan spec")
    if verified_budget.rest_staging_bytes < required_rest_staging_bytes(verified_spec):
        raise HistoryAcquisitionError("history plan staging budget is below its fixed page bound")
    job_id = raw_spec.get("job_id")
    if (
        not isinstance(job_id, str)
        or not JOB_ID_RE.fullmatch(job_id)
        or root.name != f"{job_id}--{plan_digest[:16]}"
    ):
        raise HistoryAcquisitionError("history job directory does not bind its safe plan identity")
    manifest_path = root / "manifest.json"
    manifest, manifest_digest = _verify_artifact(manifest_path)
    receipt_path = root / "completion-receipt.json"
    if not receipt_path.is_file():
        raise HistoryAcquisitionError("history job has no completion receipt")
    completion_receipt = _load_object(receipt_path)
    expected_completion = {
        "artifact": manifest_path.name,
        "artifact_sha256": manifest_digest,
        "contract": RECEIPT_CONTRACT,
        "status": "complete",
    }
    if completion_receipt != expected_completion:
        raise HistoryAcquisitionError("history completion receipt does not bind the manifest")
    if (
        manifest.get("contract") != HISTORY_MANIFEST_CONTRACT
        or manifest.get("status") != "complete"
        or manifest.get("plan_sha256") != plan_digest
        or manifest.get("job_id") != job_id
        or manifest.get("request_sha256") != raw_spec.get("request_sha256")
        or manifest.get("instrument_evidence_sha256") != raw_spec.get("instrument_evidence_sha256")
        or manifest.get("capacity_evidence_sha256") != raw_spec.get("capacity_evidence_sha256")
    ):
        raise HistoryAcquisitionError("history manifest identity does not bind the plan")
    started_at_ms = manifest.get("started_at_ms")
    completed_at_ms = manifest.get("completed_at_ms")
    if (
        isinstance(completed_at_ms, bool)
        or not isinstance(completed_at_ms, int)
        or completed_at_ms < 0
        or (
            started_at_ms is not None
            and (
                isinstance(started_at_ms, bool)
                or not isinstance(started_at_ms, int)
                or started_at_ms < 0
                or started_at_ms > completed_at_ms
            )
        )
    ):
        raise HistoryAcquisitionError("history manifest execution timestamps are invalid")
    raw_pages = manifest.get("pages")
    if not isinstance(raw_pages, list) or len(raw_pages) != len(raw_tasks):
        raise HistoryAcquisitionError("history manifest page inventory is incomplete")
    total_rows = 0
    total_source_rows = 0
    total_quarantined_rows = 0
    quarantined_source_keys: list[tuple[int, int]] | None = [] if verify_page_semantics else None
    quarantine_bindings: list[dict[str, object]] = []
    quarantine_reason_counts = {reason: 0 for reason in QUARANTINE_REASONS}
    total_attempts = 0
    empty_pages = 0
    if load_batch and not verify_page_semantics:
        raise HistoryAcquisitionError("history batch loading requires semantic page verification")
    if admit_canonical_representation and not load_batch:
        raise HistoryAcquisitionError("canonical admission requires history batch loading")
    preordered_logical_rows: list[Candle1m | MarkCandle1m] | None = [] if load_batch else None
    loaded_logical_row_count = 0
    excluded_bindings: list[dict[str, object]] = []
    excluded_source_keys: list[tuple[int, int]] = []
    admission_reason_counts = {reason: 0 for reason in CANONICAL_ADMISSION_REASONS}
    batch_dataset_type: DatasetType | None = None
    expected_files = {
        "plan.json",
        "plan.receipt.json",
        "manifest.json",
        "manifest.receipt.json",
        "completion-receipt.json",
    }
    manifest_source_quality = manifest.get("source_quality")
    has_source_quality = manifest_source_quality is not None
    for sequence, (raw_task, raw_page) in enumerate(zip(raw_tasks, raw_pages, strict=True)):
        if not isinstance(raw_task, dict) or not isinstance(raw_page, dict):
            raise HistoryAcquisitionError("history task/page inventory entries must be objects")
        try:
            task = HistoryPageTask(**raw_task)
        except TypeError as error:
            raise HistoryAcquisitionError("history task inventory is invalid") from error
        if task.sequence != sequence or raw_page.get("sequence") != sequence:
            raise HistoryAcquisitionError("history task/page sequence is not canonical")
        page = root / "pages" / task.artifact_name
        payload: dict[str, object] | None
        page_logical_rows: tuple[Candle1m | MarkCandle1m, ...] = ()
        if verify_page_semantics:
            payload, digest = _verify_artifact(page)
            page_quality, page_logical_rows = _validate_page_payload_rows(
                payload,
                task,
                ingestion_id=(
                    f"bybit-page-sha256:{digest}"
                    if preordered_logical_rows is not None
                    else "history-page-verification"
                ),
            )
            row_count = cast(int, payload["row_count"])
            attempt_count = cast(int, payload["attempt_count"])
        else:
            payload = None
            digest = _verify_artifact_digest(page)
            raw_row_count = raw_page.get("row_count")
            raw_attempt_count = raw_page.get("attempt_count")
            if (
                isinstance(raw_row_count, bool)
                or not isinstance(raw_row_count, int)
                or not 0 <= raw_row_count <= task.limit
                or isinstance(raw_attempt_count, bool)
                or not isinstance(raw_attempt_count, int)
                or not 1 <= raw_attempt_count <= verified_spec.max_attempts
            ):
                raise HistoryAcquisitionError("history manifest page counts are invalid")
            row_count = raw_row_count
            attempt_count = raw_attempt_count
            if has_source_quality:
                raw_source_count = raw_page.get("source_row_count")
                raw_quarantined_count = raw_page.get("quarantined_row_count")
                raw_quarantined_sha = raw_page.get("quarantined_rows_sha256")
                raw_reason_counts = raw_page.get("quarantine_reason_counts")
                if (
                    isinstance(raw_source_count, bool)
                    or not isinstance(raw_source_count, int)
                    or isinstance(raw_quarantined_count, bool)
                    or not isinstance(raw_quarantined_count, int)
                    or raw_source_count != row_count + raw_quarantined_count
                    or not 0 <= raw_source_count <= task.limit
                    or not isinstance(raw_quarantined_sha, str)
                    or SHA256_RE.fullmatch(raw_quarantined_sha) is None
                    or not isinstance(raw_reason_counts, dict)
                    or set(raw_reason_counts) != set(QUARANTINE_REASONS)
                    or any(
                        isinstance(raw_reason_counts[reason], bool)
                        or not isinstance(raw_reason_counts[reason], int)
                        or raw_reason_counts[reason] < 0
                        for reason in QUARANTINE_REASONS
                    )
                    or sum(cast(int, raw_reason_counts[reason]) for reason in QUARANTINE_REASONS)
                    != raw_quarantined_count
                ):
                    raise HistoryAcquisitionError(
                        "history manifest page quarantine facts are invalid"
                    )
                page_quality = PageSourceQuality(
                    source_row_count=raw_source_count,
                    quarantined_row_count=raw_quarantined_count,
                    quarantined_rows_sha256=raw_quarantined_sha,
                    reason_counts={
                        reason: cast(int, raw_reason_counts[reason])
                        for reason in QUARANTINE_REASONS
                    },
                )
            else:
                page_quality = PageSourceQuality(
                    source_row_count=row_count,
                    quarantined_row_count=0,
                    quarantined_rows_sha256=canonical_sha256([]),
                    reason_counts={reason: 0 for reason in QUARANTINE_REASONS},
                )
        if preordered_logical_rows is not None:
            preordered_logical_rows.extend(reversed(page_logical_rows))
            loaded_logical_row_count += len(page_logical_rows)
            if admit_canonical_representation:
                for row in page_logical_rows:
                    admission_reason: str | None = None
                    if isinstance(row, Candle1m):
                        scaled_volume = row.volume.scaleb(VOLUME_SCALE)
                        if scaled_volume != scaled_volume.to_integral_value():
                            admission_reason = "volume_exceeds_canonical_scale"
                    if admission_reason is None:
                        continue
                    admission_reason_counts[admission_reason] += 1
                    excluded_source_keys.append((row.instrument_id, row.open_time_ms))
                    excluded_bindings.append(
                        {
                            "instrument_id": row.instrument_id,
                            "open_time_ms": row.open_time_ms,
                            "reason": admission_reason,
                            "source_row_sha256": canonical_sha256(row),
                        }
                    )
            current_type = (
                DatasetType.TRADE_KLINE_1M if task.kind == "trade" else DatasetType.MARK_KLINE_1M
            )
            batch_dataset_type = current_type if batch_dataset_type is None else batch_dataset_type
            if current_type is not batch_dataset_type:
                raise HistoryAcquisitionError("completed history job mixes dataset types")
        if quarantined_source_keys is not None:
            assert payload is not None
            raw_quarantined_rows = payload.get("quarantined_rows", [])
            assert isinstance(raw_quarantined_rows, list)
            for raw_entry in raw_quarantined_rows:
                assert isinstance(raw_entry, dict)
                raw_row = raw_entry["row"]
                assert isinstance(raw_row, list)
                quarantined_source_keys.append((task.instrument_id, int(cast(str, raw_row[0]))))
        if not has_source_quality and page_quality.quarantined_row_count:
            raise HistoryAcquisitionError(
                "legacy history manifest cannot omit observed quarantine facts"
            )
        expected_page_fields = {
            "artifact",
            "artifact_sha256",
            "attempt_count",
            "end_ms",
            "ingestion_id",
            "instrument_id",
            "row_count",
            "sequence",
            "start_ms",
            "symbol",
        }
        if has_source_quality:
            expected_page_fields.update(
                {
                    "quarantine_reason_counts",
                    "quarantined_row_count",
                    "quarantined_rows_sha256",
                    "source_row_count",
                }
            )
        if (
            set(raw_page) != expected_page_fields
            or raw_page.get("artifact") != f"pages/{page.name}"
            or raw_page.get("artifact_sha256") != digest
            or raw_page.get("row_count") != row_count
            or raw_page.get("attempt_count") != attempt_count
            or raw_page.get("end_ms") != task.end_ms
            or raw_page.get("instrument_id") != task.instrument_id
            or raw_page.get("ingestion_id") != f"bybit-page-sha256:{digest}"
            or raw_page.get("start_ms") != task.start_ms
            or raw_page.get("symbol") != task.symbol
            or (
                has_source_quality
                and (
                    raw_page.get("source_row_count") != page_quality.source_row_count
                    or raw_page.get("quarantined_row_count") != page_quality.quarantined_row_count
                    or raw_page.get("quarantined_rows_sha256")
                    != page_quality.quarantined_rows_sha256
                    or raw_page.get("quarantine_reason_counts") != page_quality.reason_counts
                )
            )
        ):
            raise HistoryAcquisitionError("history manifest page facts do not verify")
        total_rows += row_count
        total_source_rows += page_quality.source_row_count
        total_quarantined_rows += page_quality.quarantined_row_count
        for reason, count in page_quality.reason_counts.items():
            quarantine_reason_counts[reason] += count
        if page_quality.quarantined_row_count:
            quarantine_bindings.append(
                {
                    "page_artifact_sha256": digest,
                    "quarantined_row_count": page_quality.quarantined_row_count,
                    "quarantined_rows_sha256": page_quality.quarantined_rows_sha256,
                }
            )
        total_attempts += attempt_count
        empty_pages += row_count == 0
        expected_files.update((f"pages/{page.name}", f"pages/{page.stem}.receipt.json"))
    expected_request_bound = {
        "actual_http_requests": total_attempts,
        "max_attempts_per_page": verified_spec.max_attempts,
        "max_http_requests_per_run": verified_spec.max_http_requests,
        "target_rps": verified_spec.target_rps,
        "workers": verified_spec.workers,
    }
    observed_request_bound = manifest.get("request_bound")
    if not isinstance(observed_request_bound, dict):
        raise HistoryAcquisitionError("history manifest request bound is invalid")
    adaptive_summary = observed_request_bound.get("adaptive_throttling")
    if adaptive_summary is not None:
        try:
            verify_adaptive_rate_summary(
                adaptive_summary,
                configured_target_rps=verified_spec.target_rps,
                maximum_response_count=total_attempts,
            )
        except AdaptiveRateLimitError as error:
            raise HistoryAcquisitionError(
                "history adaptive throttling summary is invalid"
            ) from error
        expected_request_bound["adaptive_throttling"] = adaptive_summary
    host_preflight = manifest.get("host_preflight")
    if not isinstance(host_preflight, dict) or (
        not isinstance(host_preflight.get("device_identity_sha256"), str)
        or not SHA256_RE.fullmatch(cast(str, host_preflight["device_identity_sha256"]))
        or host_preflight.get("storage_kind") not in ("nvme", "ssd")
        or any(
            isinstance(host_preflight.get(name), bool)
            or not isinstance(host_preflight.get(name), int)
            or cast(int, host_preflight[name]) < 0
            for name in (
                "memory_total_bytes",
                "observed_at_ms",
                "observed_free_bytes",
                "planned_peak_memory_bytes",
                "required_free_bytes",
            )
        )
    ):
        raise HistoryAcquisitionError("history manifest host preflight facts are invalid")
    if (
        manifest.get("page_count") != len(raw_tasks)
        or manifest.get("row_count") != total_rows
        or manifest.get("empty_page_count") != empty_pages
        or observed_request_bound != expected_request_bound
        or total_attempts > verified_spec.max_http_requests
        or manifest.get("source_policy")
        != {
            "interval": "1",
            "mark": "/v5/market/mark-price-kline",
            "tick_rows_requested": False,
            "trade": "/v5/market/kline",
        }
    ):
        raise HistoryAcquisitionError("history manifest aggregate counts do not verify")
    expected_source_quality = {
        "admitted_row_count": total_rows,
        "policy": QUARANTINE_POLICY,
        "quarantined_row_count": total_quarantined_rows,
        "quarantined_rows_sha256": canonical_sha256(quarantine_bindings),
        "reason_counts": quarantine_reason_counts,
        "source_row_count": total_source_rows,
    }
    if has_source_quality and manifest_source_quality != expected_source_quality:
        raise HistoryAcquisitionError("history manifest source-quality facts do not verify")
    if (
        quarantined_source_keys is not None
        and len(quarantined_source_keys) != total_quarantined_rows
    ):
        raise HistoryAcquisitionError("history quarantine source-key accounting does not verify")
    if any(path.is_symlink() for path in root.rglob("*")):
        raise HistoryAcquisitionError("history job cannot contain symlinks")
    actual_files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual_files != expected_files:
        raise HistoryAcquisitionError("history job contains orphan or missing files")
    actual_directories = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir()
    }
    if actual_directories != {"pages"}:
        raise HistoryAcquisitionError("history job contains orphan or missing directories")
    completed = CompletedHistoryJob(
        job_root=root,
        plan_path=plan_path,
        manifest_path=manifest_path,
        receipt_path=receipt_path,
        manifest_sha256=manifest_digest,
        page_count=len(raw_tasks),
        row_count=total_rows,
        quarantined_row_count=total_quarantined_rows,
        quarantined_source_keys=(
            tuple(quarantined_source_keys) if quarantined_source_keys is not None else None
        ),
    )

    batch: CanonicalCandleBatch | None = None
    canonical_admission: CanonicalCandleAdmission | None = None
    if preordered_logical_rows is not None:
        if batch_dataset_type is None:
            raise HistoryAcquisitionError("completed history job has no task dataset type")
        admitted_rows = preordered_logical_rows
        if admit_canonical_representation:
            if excluded_source_keys:
                excluded_key_set = set(excluded_source_keys)
                admitted_rows = [
                    row
                    for row in preordered_logical_rows
                    if (row.instrument_id, row.open_time_ms) not in excluded_key_set
                ]
            canonical_admission = CanonicalCandleAdmission(
                policy=CANONICAL_ADMISSION_POLICY,
                source_row_count=loaded_logical_row_count,
                admitted_row_count=loaded_logical_row_count - len(excluded_bindings),
                excluded_row_count=len(excluded_bindings),
                excluded_rows_sha256=canonical_sha256(excluded_bindings),
                reason_counts=admission_reason_counts,
                excluded_source_keys=tuple(excluded_source_keys),
            )
        try:
            if admitted_rows:
                batch = build_preordered_canonical_candle_batch(
                    admitted_rows,
                    batch_dataset_type,
                )
            else:
                first_series = verified_spec.series[0]
                batch = build_empty_canonical_candle_batch(
                    batch_dataset_type,
                    instrument_id=first_series.instrument_id,
                    open_time_ms=first_series.start_ms,
                )
        except ValueError as error:
            raise HistoryAcquisitionError(
                "completed pages do not form one canonical batch"
            ) from error
    return completed, batch, canonical_admission


def verify_completed_history_job(job_root: Path) -> CompletedHistoryJob:
    """Verify plan, page receipts, completion manifest, and the exact file allowlist."""

    completed, _batch, _admission = _verify_completed_history_job(job_root, load_batch=False)
    return completed


def verify_completed_history_job_integrity(job_root: Path) -> CompletedHistoryJob:
    """Verify the immutable receipt/hash chain and manifest facts without row decoding."""

    completed, _batch, _admission = _verify_completed_history_job(
        job_root,
        load_batch=False,
        verify_page_semantics=False,
    )
    return completed


def load_verified_completed_history_batch(
    job_root: Path,
) -> tuple[CompletedHistoryJob, CanonicalCandleBatch]:
    """Verify and convert a completed job in one linear page read."""

    completed, batch, _admission = _verify_completed_history_job(job_root, load_batch=True)
    if batch is None:  # pragma: no cover - guarded by load_batch=True
        raise HistoryAcquisitionError("completed history batch was not built")
    return completed, batch


def load_verified_completed_history_publication_batch(
    job_root: Path,
) -> tuple[CompletedHistoryJob, CanonicalCandleBatch, CanonicalCandleAdmission]:
    """Verify Landing and return its canonical-admitted batch plus exclusion evidence."""

    completed, batch, admission = _verify_completed_history_job(
        job_root,
        load_batch=True,
        admit_canonical_representation=True,
    )
    if batch is None or admission is None:  # pragma: no cover - guarded by load_batch=True
        raise HistoryAcquisitionError("completed history publication batch was not built")
    return completed, batch, admission


def load_completed_history_batch(job_root: Path) -> CanonicalCandleBatch:
    """Verify and convert one completed month/bucket job into the exact Arrow batch."""

    _completed, batch = load_verified_completed_history_batch(job_root)
    return batch
