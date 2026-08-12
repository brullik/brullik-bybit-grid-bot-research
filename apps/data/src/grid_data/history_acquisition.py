"""Bounded, paced, receipt-resumable Bybit V5 one-minute page acquisition."""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from threading import Lock, local
from typing import Final, Literal, Protocol, cast

from grid_bybit_public import BybitPublicError
from grid_bybit_public.transport import TransportError
from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file
from grid_contracts.market import MINUTE_MS, Candle1m, DatasetType, MarkCandle1m
from grid_market_store import (
    MAX_MEMORY_PERCENT,
    CapacityBudget,
    HostSnapshot,
    build_canonical_candle_batch,
    canonical_partition_path,
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
    existing_complete: bool


@dataclass(frozen=True, slots=True)
class CompletedHistoryJob:
    job_root: Path
    plan_path: Path
    manifest_path: Path
    receipt_path: Path
    manifest_sha256: str
    page_count: int
    row_count: int


class _Pacer:
    def __init__(self, target_rps: int) -> None:
        self._interval_ns = math.ceil(1_000_000_000 / target_rps)
        self._next_ns = time.perf_counter_ns()
        self._lock = Lock()

    def wait(self) -> None:
        with self._lock:
            scheduled = self._next_ns
            self._next_ns += self._interval_ns
        delay = scheduled - time.perf_counter_ns()
        if delay > 0:
            time.sleep(delay / 1_000_000_000)


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


def _validate_page_payload(payload: Mapping[str, object], task: HistoryPageTask) -> None:
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
    _logical_rows(task, typed_rows, ingestion_id="history-page-verification")
    expected_rows_sha = canonical_sha256(rows)
    if payload.get("rows_sha256") != expected_rows_sha or payload.get("row_count") != len(rows):
        raise HistoryAcquisitionError("staged page row hash/count mismatch")


def _existing_state(
    paths: HistoryJobPaths,
    plan_payload: Mapping[str, object],
    tasks: tuple[HistoryPageTask, ...],
) -> tuple[tuple[HistoryPageTask, ...], bool]:
    if not paths.job_root.exists():
        return tasks, False
    if not paths.job_root.is_dir() or paths.job_root.is_symlink() or paths.run_lock.exists():
        raise HistoryAcquisitionError("acquisition job has an unsafe or stale run directory")
    observed_plan, _digest = _verify_artifact(paths.plan_path)
    if canonical_json_bytes(observed_plan) != canonical_json_bytes(plan_payload):
        raise HistoryAcquisitionError("existing acquisition plan does not match the requested plan")
    if paths.receipt_path.exists() or paths.manifest_path.exists():
        completed = verify_completed_history_job(paths.job_root)
        return (), completed.page_count == len(tasks)
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
    return tuple(pending), False


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
    pending, complete = _existing_state(paths, plan_payload, tasks)
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
        existing_complete=complete,
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
    expected_width = 7 if task.kind == "trade" else 5
    timestamps: list[int] = []
    logical: list[Candle1m | MarkCandle1m] = []
    source_id = "bybit-v5-kline/v1" if task.kind == "trade" else "bybit-v5-mark-kline/v1"
    for row in rows:
        if len(row) != expected_width or not row[0].isdigit():
            raise HistoryAcquisitionError("Bybit kline row has invalid width or timestamp")
        timestamp = int(row[0])
        if timestamp < task.start_ms or timestamp > task.end_ms or timestamp % MINUTE_MS:
            raise HistoryAcquisitionError("Bybit kline timestamp escapes its planned page")
        timestamps.append(timestamp)
        common = {
            "category": task.category,
            "instrument_id": task.instrument_id,
            "open_time_ms": timestamp,
            "open": _parse_decimal("open", row[1]),
            "high": _parse_decimal("high", row[2]),
            "low": _parse_decimal("low", row[3]),
            "close": _parse_decimal("close", row[4]),
            "source_id": source_id,
            "ingestion_id": ingestion_id,
            "quality_flags": 0,
        }
        try:
            if task.kind == "trade":
                logical.append(
                    Candle1m(
                        **common,  # type: ignore[arg-type]
                        volume=_parse_decimal("volume", row[5]),
                        turnover=_parse_decimal("turnover", row[6]),
                    )
                )
            else:
                logical.append(MarkCandle1m(**common))  # type: ignore[arg-type]
        except ValueError as error:
            raise HistoryAcquisitionError(
                "Bybit kline violates the logical candle contract"
            ) from error
    if timestamps != sorted(timestamps, reverse=True) or len(timestamps) != len(set(timestamps)):
        raise HistoryAcquisitionError("Bybit kline page must be unique reverse chronological data")
    return tuple(logical)


def _page_payload(
    task: HistoryPageTask, rows: Sequence[tuple[str, ...]], attempts: int
) -> dict[str, object]:
    _logical_rows(task, rows, ingestion_id="history-page-validation")
    serialized_rows = [list(row) for row in rows]
    return {
        "attempt_count": attempts,
        "category": task.category,
        "contract": HISTORY_PAGE_CONTRACT,
        "end_ms": task.end_ms,
        "instrument_id": task.instrument_id,
        "kind": task.kind,
        "limit": task.limit,
        "row_count": len(serialized_rows),
        "rows": serialized_rows,
        "rows_sha256": canonical_sha256(serialized_rows),
        "sequence": task.sequence,
        "start_ms": task.start_ms,
        "symbol": task.symbol,
    }


def _fetch_page(
    task: HistoryPageTask,
    *,
    client: KlineClient,
    pacer: _Pacer,
    max_attempts: int,
) -> dict[str, object]:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        pacer.wait()
        try:
            rows = client.kline_page(
                kind=task.kind,
                symbol=task.symbol,
                start_ms=task.start_ms,
                end_ms=task.end_ms,
                category=task.category,
                limit=task.limit,
            )
            payload = _page_payload(task, rows, attempt)
            if len(canonical_json_bytes(payload)) > MAX_PAGE_ARTIFACT_BYTES:
                raise HistoryAcquisitionError("staged page exceeds its preflighted byte bound")
            return payload
        except (BybitPublicError, TransportError) as error:
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
        return verify_completed_history_job(plan.paths.job_root)
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
    pacer = _Pacer(plan.spec.target_rps)

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
                future.result()
        finish_snapshot = snapshot_provider()
        finish_now = now_ms()
        _assert_execute_snapshot(plan, finish_snapshot, now_ms=finish_now)
        page_inventory: list[dict[str, object]] = []
        total_rows = 0
        empty_pages = 0
        for task in plan.tasks:
            page = _task_page_path(plan.paths, task)
            payload, digest = _verify_artifact(page)
            _validate_page_payload(payload, task)
            row_count = cast(int, payload["row_count"])
            total_rows += row_count
            empty_pages += row_count == 0
            page_inventory.append(
                {
                    "artifact": f"pages/{page.name}",
                    "artifact_sha256": digest,
                    "attempt_count": payload["attempt_count"],
                    "end_ms": task.end_ms,
                    "ingestion_id": f"bybit-page-sha256:{digest}",
                    "instrument_id": task.instrument_id,
                    "row_count": row_count,
                    "sequence": task.sequence,
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
                "max_attempts_per_page": plan.spec.max_attempts,
                "max_http_requests_per_run": plan.spec.max_http_requests,
                "target_rps": plan.spec.target_rps,
                "workers": plan.spec.workers,
            },
            "row_count": total_rows,
            "source_policy": {
                "mark": "/v5/market/mark-price-kline",
                "trade": "/v5/market/kline",
                "interval": "1",
                "tick_rows_requested": False,
            },
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
    return verify_completed_history_job(plan.paths.job_root)


def verify_completed_history_job(job_root: Path) -> CompletedHistoryJob:
    """Verify plan, page receipts, completion manifest, and the exact file allowlist."""

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
    raw_pages = manifest.get("pages")
    if not isinstance(raw_pages, list) or len(raw_pages) != len(raw_tasks):
        raise HistoryAcquisitionError("history manifest page inventory is incomplete")
    total_rows = 0
    total_attempts = 0
    empty_pages = 0
    expected_files = {
        "plan.json",
        "plan.receipt.json",
        "manifest.json",
        "manifest.receipt.json",
        "completion-receipt.json",
    }
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
        payload, digest = _verify_artifact(page)
        _validate_page_payload(payload, task)
        if (
            raw_page.get("artifact") != f"pages/{page.name}"
            or raw_page.get("artifact_sha256") != digest
            or raw_page.get("row_count") != payload.get("row_count")
            or raw_page.get("attempt_count") != payload.get("attempt_count")
            or raw_page.get("ingestion_id") != f"bybit-page-sha256:{digest}"
        ):
            raise HistoryAcquisitionError("history manifest page facts do not verify")
        total_rows += cast(int, payload["row_count"])
        total_attempts += cast(int, payload["attempt_count"])
        empty_pages += payload["row_count"] == 0
        expected_files.update((f"pages/{page.name}", f"pages/{page.stem}.receipt.json"))
    expected_request_bound = {
        "actual_http_requests": total_attempts,
        "max_attempts_per_page": verified_spec.max_attempts,
        "max_http_requests_per_run": verified_spec.max_http_requests,
        "target_rps": verified_spec.target_rps,
        "workers": verified_spec.workers,
    }
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
        or manifest.get("request_bound") != expected_request_bound
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
    return CompletedHistoryJob(
        job_root=root,
        plan_path=plan_path,
        manifest_path=manifest_path,
        receipt_path=receipt_path,
        manifest_sha256=manifest_digest,
        page_count=len(raw_tasks),
        row_count=total_rows,
    )


def load_completed_history_batch(job_root: Path):  # type: ignore[no-untyped-def]
    """Verify and convert one completed month/bucket job into the exact Arrow batch."""

    completed = verify_completed_history_job(job_root)
    plan = _load_object(completed.plan_path)
    raw_tasks = cast(list[dict[str, object]], plan["tasks"])
    rows: list[Candle1m | MarkCandle1m] = []
    dataset_type: DatasetType | None = None
    for raw_task in raw_tasks:
        task = HistoryPageTask(**raw_task)  # type: ignore[arg-type]
        page = completed.job_root / "pages" / task.artifact_name
        payload, digest = _verify_artifact(page)
        raw_rows = cast(list[list[str]], payload["rows"])
        rows.extend(
            _logical_rows(
                task,
                [tuple(item) for item in raw_rows],
                ingestion_id=f"bybit-page-sha256:{digest}",
            )
        )
        current_type = (
            DatasetType.TRADE_KLINE_1M if task.kind == "trade" else DatasetType.MARK_KLINE_1M
        )
        dataset_type = current_type if dataset_type is None else dataset_type
        if current_type is not dataset_type:
            raise HistoryAcquisitionError("completed history job mixes dataset types")
    if dataset_type is None:
        raise HistoryAcquisitionError("completed history job has no task dataset type")
    try:
        return build_canonical_candle_batch(rows, dataset_type)
    except ValueError as error:
        raise HistoryAcquisitionError("completed pages do not form one canonical batch") from error
