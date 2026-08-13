"""Bounded, paced, receipt-resumable Bybit V5 funding-history acquisition."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from threading import local
from typing import Any, Final, Literal, Protocol, cast

from grid_bybit_public import BybitPublicError
from grid_bybit_public.transport import TransportError
from grid_contracts.canonical import (
    canonical_json_bytes,
    canonical_sha256,
    decimal_text,
    sha256_file,
)
from grid_contracts.market import MINUTE_MS, FundingEvent
from grid_market_store import (
    MAX_MEMORY_PERCENT,
    CanonicalFundingBatch,
    CapacityBudget,
    HostSnapshot,
    build_canonical_funding_batch,
    canonical_funding_partition_path,
)

from grid_data.public_rate_limit import (
    AdaptiveRateLimitAbort,
    AdaptiveRateLimitError,
    AdaptiveRatePacer,
    verify_adaptive_rate_summary,
)

Category = Literal["linear"]
PageScope = Literal["boundary", "range"]
FUNDING_PLAN_CONTRACT: Final = "grid.bybit-funding-history-plan/v1"
FUNDING_PAGE_CONTRACT: Final = "grid.bybit-funding-history-page/v1"
FUNDING_MANIFEST_CONTRACT: Final = "grid.bybit-funding-history-acquisition/v1"
RECEIPT_CONTRACT: Final = "grid.history-acquisition-receipt/v1"
MAX_WORKERS: Final = 32
MAX_TARGET_RPS: Final = 96
MAX_ATTEMPTS: Final = 5
MAX_HTTP_REQUESTS: Final = 100_000
MAX_SERIES: Final = 700
MAX_PAGE_LIMIT: Final = 200
MAX_PAGE_SPAN_MINUTES: Final = 7 * 24 * 60
DEFAULT_PAGE_SPAN_MINUTES: Final = MAX_PAGE_SPAN_MINUTES
MAX_PAGE_ARTIFACT_BYTES: Final = 128 * 1024
STAGING_METADATA_BYTES: Final = 64 * 1024**2
MAX_PREFLIGHT_AGE_MS: Final = 60_000
UINT32_MAX: Final = (1 << 32) - 1
JOB_ID_RE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")


class FundingAcquisitionError(RuntimeError):
    """A funding job cannot safely plan, resume, acquire, or verify."""


class FundingClient(Protocol):
    def funding_page(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        category: Category = "linear",
        limit: int = 200,
    ) -> tuple[Mapping[str, Any], ...]: ...


@dataclass(frozen=True, slots=True)
class FundingSeries:
    category: Category
    symbol: str
    instrument_id: int
    launch_time_ms: int
    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if self.category != "linear":
            raise FundingAcquisitionError("unsupported funding category")
        if not self.symbol or self.symbol != self.symbol.upper() or not self.symbol.isalnum():
            raise FundingAcquisitionError("symbol must be uppercase alphanumeric text")
        if (
            isinstance(self.instrument_id, bool)
            or not isinstance(self.instrument_id, int)
            or not 1 <= self.instrument_id <= UINT32_MAX
        ):
            raise FundingAcquisitionError("instrument_id must fit positive UInt32 storage")
        if (
            isinstance(self.launch_time_ms, bool)
            or not isinstance(self.launch_time_ms, int)
            or self.launch_time_ms < 0
        ):
            raise FundingAcquisitionError("launch_time_ms must be non-negative")
        if (
            isinstance(self.start_ms, bool)
            or isinstance(self.end_ms, bool)
            or not isinstance(self.start_ms, int)
            or not isinstance(self.end_ms, int)
            or self.start_ms <= self.launch_time_ms
            or self.end_ms < self.start_ms
            or self.start_ms % MINUTE_MS
            or self.end_ms % MINUTE_MS
        ):
            raise FundingAcquisitionError(
                "funding bounds must be aligned UTC minutes after instrument launch"
            )


@dataclass(frozen=True, slots=True)
class FundingJobSpec:
    job_id: str
    series: tuple[FundingSeries, ...]
    request_sha256: str
    instrument_evidence_sha256: str
    capacity_evidence_sha256: str
    page_span_minutes: int = DEFAULT_PAGE_SPAN_MINUTES
    page_limit: int = MAX_PAGE_LIMIT
    workers: int = 24
    target_rps: int = 10
    max_attempts: int = 3
    max_http_requests: int = MAX_HTTP_REQUESTS

    def __post_init__(self) -> None:
        if not JOB_ID_RE.fullmatch(self.job_id):
            raise FundingAcquisitionError("job_id must be a safe lowercase storage identity")
        if any(
            not SHA256_RE.fullmatch(value)
            for value in (
                self.request_sha256,
                self.instrument_evidence_sha256,
                self.capacity_evidence_sha256,
            )
        ):
            raise FundingAcquisitionError("funding job bindings must be lowercase SHA-256")
        if not 1 <= len(self.series) <= MAX_SERIES:
            raise FundingAcquisitionError(f"funding series count must be in [1, {MAX_SERIES}]")
        if self.series != tuple(sorted(self.series, key=lambda item: item.instrument_id)):
            raise FundingAcquisitionError("funding series must be sorted by instrument_id")
        instrument_ids = [item.instrument_id for item in self.series]
        symbols = [item.symbol for item in self.series]
        if len(instrument_ids) != len(set(instrument_ids)) or len(symbols) != len(set(symbols)):
            raise FundingAcquisitionError("funding series instruments and symbols must be unique")
        for name, value, maximum in (
            ("page_span_minutes", self.page_span_minutes, MAX_PAGE_SPAN_MINUTES),
            ("page_limit", self.page_limit, MAX_PAGE_LIMIT),
            ("workers", self.workers, MAX_WORKERS),
            ("target_rps", self.target_rps, MAX_TARGET_RPS),
            ("max_attempts", self.max_attempts, MAX_ATTEMPTS),
            ("max_http_requests", self.max_http_requests, MAX_HTTP_REQUESTS),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
                raise FundingAcquisitionError(f"{name} must be in [1, {maximum}]")
        first = self.series[0]
        expected_partition = canonical_funding_partition_path(
            instrument_id=first.instrument_id,
            funding_time_ms=first.start_ms,
        )
        for item in self.series:
            for timestamp in (item.start_ms, item.end_ms):
                partition = canonical_funding_partition_path(
                    instrument_id=item.instrument_id,
                    funding_time_ms=timestamp,
                )
                if partition != expected_partition:
                    raise FundingAcquisitionError(
                        "one funding job must fit one month/bucket partition"
                    )


@dataclass(frozen=True, slots=True)
class FundingPageTask:
    sequence: int
    scope: PageScope
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
class FundingJobPaths:
    staging_root: Path
    job_root: Path
    pages_root: Path
    plan_path: Path
    manifest_path: Path
    receipt_path: Path
    run_lock: Path


@dataclass(frozen=True, slots=True)
class FundingJobPlan:
    spec: FundingJobSpec
    budget: CapacityBudget
    snapshot: HostSnapshot
    paths: FundingJobPaths
    tasks: tuple[FundingPageTask, ...]
    pending_tasks: tuple[FundingPageTask, ...]
    plan_sha256: str
    required_free_bytes: int
    planned_peak_memory_bytes: int
    existing_complete: bool


@dataclass(frozen=True, slots=True)
class CompletedFundingJob:
    job_root: Path
    plan_path: Path
    manifest_path: Path
    receipt_path: Path
    manifest_sha256: str
    boundary_evidence_sha256: str
    page_count: int
    row_count: int


def _plan_tasks(spec: FundingJobSpec) -> tuple[FundingPageTask, ...]:
    tasks: list[FundingPageTask] = []
    page_span_ms = spec.page_span_minutes * MINUTE_MS
    for item in spec.series:
        tasks.append(
            FundingPageTask(
                sequence=len(tasks),
                scope="boundary",
                category=item.category,
                symbol=item.symbol,
                instrument_id=item.instrument_id,
                start_ms=item.launch_time_ms,
                end_ms=item.start_ms - 1,
                limit=1,
            )
        )
        page_start = item.start_ms
        while page_start <= item.end_ms:
            page_end = min(item.end_ms, page_start + page_span_ms - MINUTE_MS)
            tasks.append(
                FundingPageTask(
                    sequence=len(tasks),
                    scope="range",
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


def required_funding_staging_bytes(spec: FundingJobSpec) -> int:
    return STAGING_METADATA_BYTES + len(_plan_tasks(spec)) * MAX_PAGE_ARTIFACT_BYTES


def _plan_payload(
    spec: FundingJobSpec,
    tasks: Sequence[FundingPageTask],
    budget: CapacityBudget,
) -> dict[str, object]:
    return {
        "capacity_budget": budget,
        "contract": FUNDING_PLAN_CONTRACT,
        "spec": spec,
        "tasks": tuple(tasks),
    }


def _paths(staging_root: Path, spec: FundingJobSpec, plan_sha256: str) -> FundingJobPaths:
    root = staging_root.resolve()
    job_root = root / ".funding-landing" / f"{spec.job_id}--{plan_sha256[:16]}"
    return FundingJobPaths(
        staging_root=root,
        job_root=job_root,
        pages_root=job_root / "pages",
        plan_path=job_root / "plan.json",
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
        raise FundingAcquisitionError(f"refusing to replace funding artifact: {path}")
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
    _atomic_write_new(path, canonical_json_bytes(payload))
    digest = sha256_file(path)
    _atomic_write_new(
        path.with_suffix(".receipt.json"),
        canonical_json_bytes(_receipt_payload(path.name, digest)),
    )
    return digest


def _load_object(path: Path) -> dict[str, object]:
    try:
        data = path.read_bytes()
        raw = json.loads(data)
    except (OSError, json.JSONDecodeError) as error:
        raise FundingAcquisitionError(f"cannot load funding JSON: {path}") from error
    if not isinstance(raw, dict) or canonical_json_bytes(raw) != data:
        raise FundingAcquisitionError(f"funding JSON is not canonical: {path}")
    return cast(dict[str, object], raw)


def _verify_artifact(path: Path) -> tuple[dict[str, object], str]:
    receipt_path = path.with_suffix(".receipt.json")
    if not path.is_file() or not receipt_path.is_file():
        raise FundingAcquisitionError(f"artifact/receipt pair is incomplete: {path}")
    payload = _load_object(path)
    receipt = _load_object(receipt_path)
    digest = sha256_file(path)
    if receipt != _receipt_payload(path.name, digest):
        raise FundingAcquisitionError(f"artifact receipt does not verify: {path}")
    if path.parent.name == "pages" and path.stat().st_size > MAX_PAGE_ARTIFACT_BYTES:
        raise FundingAcquisitionError(f"staged funding page exceeds byte bound: {path}")
    return payload, digest


def _assert_fresh(snapshot: HostSnapshot, *, now_ms: int) -> None:
    age = now_ms - snapshot.observed_at_ms
    if age < 0 or age > MAX_PREFLIGHT_AGE_MS:
        raise FundingAcquisitionError("host snapshot must be fresh and not future-dated")


def _assert_target_volume(staging_root: Path, snapshot: HostSnapshot) -> None:
    resolved = staging_root.resolve()
    if not resolved.is_relative_to(snapshot.volume_root.resolve()):
        raise FundingAcquisitionError("staging root is outside the observed local volume")
    existing = resolved
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    if not existing.is_dir() or existing.is_symlink():
        raise FundingAcquisitionError(
            "funding staging requires an existing non-symlink directory ancestor"
        )


def _resource_requirements(
    task_count: int,
    pending_count: int,
    spec: FundingJobSpec,
    budget: CapacityBudget,
) -> tuple[int, int]:
    full_staging = STAGING_METADATA_BYTES + task_count * MAX_PAGE_ARTIFACT_BYTES
    if budget.rest_staging_bytes < full_staging:
        raise FundingAcquisitionError(
            f"funding staging budget must be at least {full_staging} bytes"
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
        raise FundingAcquisitionError("insufficient free space for bounded funding acquisition")
    if planned_peak_memory_bytes > snapshot.memory_available_bytes:
        raise FundingAcquisitionError("insufficient available memory for funding workers")
    if planned_peak_memory_bytes * 100 > snapshot.memory_total_bytes * MAX_MEMORY_PERCENT:
        raise FundingAcquisitionError("funding plan exceeds the 70% total-memory gate")


def _task_page_path(paths: FundingJobPaths, task: FundingPageTask) -> Path:
    return paths.pages_root / task.artifact_name


def _parse_rate(raw: object) -> str:
    if not isinstance(raw, str):
        raise FundingAcquisitionError("fundingRate must be exact decimal text")
    try:
        value = Decimal(raw)
    except InvalidOperation as error:
        raise FundingAcquisitionError("fundingRate must be exact decimal text") from error
    if not value.is_finite():
        raise FundingAcquisitionError("fundingRate must be finite")
    return decimal_text(value)


def _normalize_rows(
    task: FundingPageTask,
    items: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, object], ...]:
    normalized: list[dict[str, object]] = []
    for item in items:
        if item.get("symbol") != task.symbol:
            raise FundingAcquisitionError("funding response symbol does not match its task")
        raw_timestamp = item.get("fundingRateTimestamp")
        if not isinstance(raw_timestamp, str) or not raw_timestamp.isdigit():
            raise FundingAcquisitionError("fundingRateTimestamp must be integer text")
        timestamp = int(raw_timestamp)
        if timestamp < task.start_ms or timestamp > task.end_ms or timestamp % MINUTE_MS:
            raise FundingAcquisitionError("funding timestamp escapes its planned page")
        normalized.append(
            {
                "funding_rate": _parse_rate(item.get("fundingRate")),
                "funding_time_ms": timestamp,
            }
        )
    timestamps = [cast(int, row["funding_time_ms"]) for row in normalized]
    if timestamps != sorted(timestamps, reverse=True) or len(timestamps) != len(set(timestamps)):
        raise FundingAcquisitionError("funding page must be unique reverse chronological data")
    if task.scope == "boundary" and len(normalized) != 1:
        raise FundingAcquisitionError("funding boundary requires exactly one preceding settlement")
    if task.scope == "range" and len(normalized) >= task.limit:
        raise FundingAcquisitionError(
            "funding range page is saturated and cannot prove complete coverage"
        )
    return tuple(normalized)


def _page_payload(
    task: FundingPageTask,
    items: Sequence[Mapping[str, Any]],
    attempts: int,
) -> dict[str, object]:
    rows = _normalize_rows(task, items)
    return {
        "attempt_count": attempts,
        "category": task.category,
        "contract": FUNDING_PAGE_CONTRACT,
        "end_ms": task.end_ms,
        "instrument_id": task.instrument_id,
        "limit": task.limit,
        "row_count": len(rows),
        "rows": rows,
        "rows_sha256": canonical_sha256(rows),
        "scope": task.scope,
        "sequence": task.sequence,
        "start_ms": task.start_ms,
        "symbol": task.symbol,
    }


def _validate_page_payload(payload: Mapping[str, object], task: FundingPageTask) -> None:
    expected = {
        "category": task.category,
        "end_ms": task.end_ms,
        "instrument_id": task.instrument_id,
        "limit": task.limit,
        "scope": task.scope,
        "sequence": task.sequence,
        "start_ms": task.start_ms,
        "symbol": task.symbol,
    }
    if payload.get("contract") != FUNDING_PAGE_CONTRACT or any(
        payload.get(name) != value for name, value in expected.items()
    ):
        raise FundingAcquisitionError(f"staged funding page identity mismatch: {task.sequence}")
    attempts = payload.get("attempt_count")
    rows = payload.get("rows")
    if (
        not isinstance(attempts, int)
        or isinstance(attempts, bool)
        or not 1 <= attempts <= MAX_ATTEMPTS
    ):
        raise FundingAcquisitionError("staged funding page has invalid attempt count")
    if not isinstance(rows, list) or any(not isinstance(item, dict) for item in rows):
        raise FundingAcquisitionError("staged funding page rows must be objects")
    source_items = [
        {
            "fundingRate": item.get("funding_rate"),
            "fundingRateTimestamp": str(item.get("funding_time_ms")),
            "symbol": task.symbol,
        }
        for item in rows
    ]
    normalized = _normalize_rows(task, source_items)
    if (
        payload.get("rows_sha256") != canonical_sha256(normalized)
        or payload.get("row_count") != len(normalized)
        or canonical_json_bytes(rows) != canonical_json_bytes(normalized)
    ):
        raise FundingAcquisitionError("staged funding page row hash/count mismatch")


def _existing_state(
    paths: FundingJobPaths,
    plan_payload: Mapping[str, object],
    tasks: tuple[FundingPageTask, ...],
) -> tuple[tuple[FundingPageTask, ...], bool]:
    if not paths.job_root.exists():
        return tasks, False
    if not paths.job_root.is_dir() or paths.job_root.is_symlink() or paths.run_lock.exists():
        raise FundingAcquisitionError("funding job has an unsafe or stale run directory")
    observed_plan, _digest = _verify_artifact(paths.plan_path)
    if canonical_json_bytes(observed_plan) != canonical_json_bytes(plan_payload):
        raise FundingAcquisitionError("existing funding plan does not match requested plan")
    if paths.receipt_path.exists() or paths.manifest_path.exists():
        completed = verify_completed_funding_job(paths.job_root)
        return (), completed.page_count == len(tasks)
    pending: list[FundingPageTask] = []
    expected_page_files: set[str] = set()
    for task in tasks:
        page = _task_page_path(paths, task)
        receipt = page.with_suffix(".receipt.json")
        expected_page_files.update((page.name, receipt.name))
        if page.exists() != receipt.exists():
            raise FundingAcquisitionError(f"partial funding page detected: {task.sequence}")
        if not page.exists():
            pending.append(task)
            continue
        payload, _digest = _verify_artifact(page)
        _validate_page_payload(payload, task)
    actual_page_files = (
        {path.name for path in paths.pages_root.iterdir()} if paths.pages_root.exists() else set()
    )
    if not actual_page_files.issubset(expected_page_files):
        raise FundingAcquisitionError("funding pages directory contains orphan files")
    return tuple(pending), False


def preflight_funding_job(
    staging_root: Path,
    spec: FundingJobSpec,
    budget: CapacityBudget,
    snapshot: HostSnapshot,
    *,
    now_ms: int,
    closed_before_ms: int,
) -> FundingJobPlan:
    """Plan predecessor/range pages and inspect resume state without mutation."""

    if (
        isinstance(closed_before_ms, bool)
        or not isinstance(closed_before_ms, int)
        or closed_before_ms < 0
        or closed_before_ms % MINUTE_MS
    ):
        raise FundingAcquisitionError("closed_before_ms must be an aligned UTC minute")
    if any(item.end_ms >= closed_before_ms for item in spec.series):
        raise FundingAcquisitionError("funding jobs may acquire only closed settlement times")
    tasks = _plan_tasks(spec)
    if len(tasks) * spec.max_attempts > spec.max_http_requests:
        raise FundingAcquisitionError("full funding retry bound exceeds max_http_requests")
    plan_payload = _plan_payload(spec, tasks, budget)
    plan_sha = canonical_sha256(plan_payload)
    paths = _paths(staging_root, spec, plan_sha)
    _assert_fresh(snapshot, now_ms=now_ms)
    _assert_target_volume(paths.staging_root, snapshot)
    pending, complete = _existing_state(paths, plan_payload, tasks)
    if len(pending) * spec.max_attempts > spec.max_http_requests:
        raise FundingAcquisitionError("funding resume retry bound exceeds max_http_requests")
    required_free, planned_memory = _resource_requirements(len(tasks), len(pending), spec, budget)
    _assert_resources(
        snapshot,
        required_free_bytes=required_free,
        planned_peak_memory_bytes=planned_memory,
    )
    return FundingJobPlan(
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


def _fetch_page(
    task: FundingPageTask,
    *,
    client: FundingClient,
    pacer: AdaptiveRatePacer,
    max_attempts: int,
) -> dict[str, object]:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        pacer.wait()
        try:
            try:
                items = client.funding_page(
                    symbol=task.symbol,
                    start_ms=task.start_ms,
                    end_ms=task.end_ms,
                    category=task.category,
                    limit=task.limit,
                )
            finally:
                pacer.observe_client(client)
            payload = _page_payload(task, items, attempt)
            if len(canonical_json_bytes(payload)) > MAX_PAGE_ARTIFACT_BYTES:
                raise FundingAcquisitionError("staged funding page exceeds preflighted bound")
            return payload
        except (BybitPublicError, TransportError) as error:
            last_error = error
            if attempt < max_attempts:
                time.sleep(min(4.0, 0.25 * (2 ** (attempt - 1))))
    raise FundingAcquisitionError(
        f"funding page {task.sequence} failed after {max_attempts} attempts"
    ) from last_error


def _assert_execute_snapshot(
    plan: FundingJobPlan,
    snapshot: HostSnapshot,
    *,
    now_ms: int,
) -> None:
    _assert_fresh(snapshot, now_ms=now_ms)
    _assert_target_volume(plan.paths.staging_root, snapshot)
    if (
        snapshot.device_identity_sha256 != plan.snapshot.device_identity_sha256
        or snapshot.memory_total_bytes != plan.snapshot.memory_total_bytes
    ):
        raise FundingAcquisitionError("host or storage identity changed after funding preflight")
    _assert_resources(
        snapshot,
        required_free_bytes=plan.required_free_bytes,
        planned_peak_memory_bytes=plan.planned_peak_memory_bytes,
    )


def execute_funding_job(
    plan: FundingJobPlan,
    client_factory: Callable[[], FundingClient],
    snapshot_provider: Callable[[], HostSnapshot],
    *,
    now_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
) -> CompletedFundingJob:
    """Fetch missing pages and publish a completion receipt after final verification."""

    if plan.existing_complete:
        return verify_completed_funding_job(plan.paths.job_root)
    start_snapshot = snapshot_provider()
    start_now = now_ms()
    _assert_execute_snapshot(plan, start_snapshot, now_ms=start_now)
    plan.paths.pages_root.mkdir(parents=True, exist_ok=True)
    try:
        plan.paths.run_lock.mkdir()
    except FileExistsError as error:
        raise FundingAcquisitionError(
            "funding job already has an active or stale run lock"
        ) from error
    thread_state = local()
    pacer = AdaptiveRatePacer(plan.spec.target_rps)

    def acquire(task: FundingPageTask) -> tuple[int, str, int]:
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
        if not plan.paths.plan_path.exists():
            _publish_artifact(
                plan.paths.plan_path,
                _plan_payload(plan.spec, plan.tasks, plan.budget),
            )
        with ThreadPoolExecutor(max_workers=plan.spec.workers) as executor:
            futures = {executor.submit(acquire, task): task for task in plan.pending_tasks}
            for future in as_completed(futures):
                try:
                    future.result()
                except AdaptiveRateLimitAbort as error:
                    raise FundingAcquisitionError(
                        "funding acquisition stopped by the adaptive rate-limit policy"
                    ) from error
        finish_snapshot = snapshot_provider()
        finish_now = now_ms()
        _assert_execute_snapshot(plan, finish_snapshot, now_ms=finish_now)
        page_inventory: list[dict[str, object]] = []
        boundary_rows: list[dict[str, object]] = []
        event_rows = 0
        empty_range_pages = 0
        for task in plan.tasks:
            page = _task_page_path(plan.paths, task)
            payload, digest = _verify_artifact(page)
            _validate_page_payload(payload, task)
            row_count = cast(int, payload["row_count"])
            if task.scope == "boundary":
                row = cast(list[dict[str, object]], payload["rows"])[0]
                boundary_rows.append(
                    {
                        "artifact_sha256": digest,
                        "funding_time_ms": row["funding_time_ms"],
                        "instrument_id": task.instrument_id,
                    }
                )
            else:
                event_rows += row_count
                empty_range_pages += row_count == 0
            page_inventory.append(
                {
                    "artifact": f"pages/{page.name}",
                    "artifact_sha256": digest,
                    "attempt_count": payload["attempt_count"],
                    "end_ms": task.end_ms,
                    "ingestion_id": f"bybit-funding-page-sha256:{digest}",
                    "instrument_id": task.instrument_id,
                    "row_count": row_count,
                    "scope": task.scope,
                    "sequence": task.sequence,
                    "start_ms": task.start_ms,
                    "symbol": task.symbol,
                }
            )
        boundary_evidence_sha = canonical_sha256(boundary_rows)
        manifest: dict[str, object] = {
            "boundary_evidence_sha256": boundary_evidence_sha,
            "boundary_row_count": len(boundary_rows),
            "capacity_evidence_sha256": plan.spec.capacity_evidence_sha256,
            "completed_at_ms": finish_now,
            "contract": FUNDING_MANIFEST_CONTRACT,
            "empty_range_page_count": empty_range_pages,
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
            "row_count": event_rows,
            "source_policy": {
                "endpoint": "/v5/market/funding/history",
                "page_limit": plan.spec.page_limit,
                "page_span_minutes": plan.spec.page_span_minutes,
                "private_credentials_used": False,
                "saturated_range_pages_accepted": False,
            },
            "status": "complete",
        }
        _publish_artifact(plan.paths.manifest_path, manifest)
        manifest_digest = sha256_file(plan.paths.manifest_path)
        _atomic_write_new(
            plan.paths.receipt_path,
            canonical_json_bytes(_receipt_payload(plan.paths.manifest_path.name, manifest_digest)),
        )
    finally:
        plan.paths.run_lock.rmdir()
    return verify_completed_funding_job(plan.paths.job_root)


def _verified_spec(raw_spec: Mapping[str, object]) -> FundingJobSpec:
    raw_series = raw_spec.get("series")
    if not isinstance(raw_series, list) or any(not isinstance(item, dict) for item in raw_series):
        raise FundingAcquisitionError("funding plan series inventory is invalid")
    try:
        return FundingJobSpec(
            **{  # type: ignore[arg-type]
                **raw_spec,
                "series": tuple(FundingSeries(**item) for item in raw_series),
            }
        )
    except (TypeError, ValueError) as error:
        raise FundingAcquisitionError("funding plan spec is invalid") from error


def _funding_batch_from_verified_rows(
    boundary_by_instrument: Mapping[int, int],
    rows_by_instrument: Mapping[int, list[tuple[int, str, str]]],
    requested_instruments: set[int],
) -> CanonicalFundingBatch:
    logical: list[FundingEvent] = []
    for instrument_id in sorted(requested_instruments):
        observed = sorted(rows_by_instrument.get(instrument_id, []))
        if not observed:
            raise FundingAcquisitionError(
                "each requested funding series requires at least one returned event"
            )
        timestamps = [item[0] for item in observed]
        if len(timestamps) != len(set(timestamps)):
            raise FundingAcquisitionError("completed funding pages contain duplicate keys")
        previous = boundary_by_instrument.get(instrument_id)
        if previous is None:
            raise FundingAcquisitionError("funding series has no predecessor boundary")
        for timestamp, rate, ingestion_id in observed:
            delta = timestamp - previous
            if delta <= 0 or delta % MINUTE_MS:
                raise FundingAcquisitionError(
                    "funding interval cannot be derived from settlement chronology"
                )
            try:
                logical.append(
                    FundingEvent(
                        category="linear",
                        instrument_id=instrument_id,
                        funding_time_ms=timestamp,
                        funding_rate=Decimal(rate),
                        funding_interval_minutes=delta // MINUTE_MS,
                        source_id="bybit-v5-funding-history/v1",
                        ingestion_id=ingestion_id,
                        quality_flags=0,
                    )
                )
            except ValueError as error:
                raise FundingAcquisitionError(
                    "funding row violates the logical event contract"
                ) from error
            previous = timestamp
    try:
        return build_canonical_funding_batch(logical)
    except ValueError as error:
        raise FundingAcquisitionError(
            "completed funding pages do not form one canonical batch"
        ) from error


def _verify_completed_funding_job(
    job_root: Path,
    *,
    load_batch: bool,
) -> tuple[CompletedFundingJob, CanonicalFundingBatch | None]:
    """Verify once and optionally build the exact batch from those same verified page bytes."""

    root = job_root.resolve()
    if not root.is_dir() or root.is_symlink() or (root / ".run-lock").exists():
        raise FundingAcquisitionError("funding job root is missing, unsafe, or active")
    plan_path = root / "plan.json"
    plan_payload, plan_digest = _verify_artifact(plan_path)
    raw_tasks = plan_payload.get("tasks")
    raw_spec = plan_payload.get("spec")
    raw_budget = plan_payload.get("capacity_budget")
    if (
        plan_payload.get("contract") != FUNDING_PLAN_CONTRACT
        or not isinstance(raw_tasks, list)
        or not isinstance(raw_spec, dict)
        or not isinstance(raw_budget, dict)
    ):
        raise FundingAcquisitionError("unsupported or incomplete funding plan")
    verified_spec = _verified_spec(raw_spec)
    try:
        verified_budget = CapacityBudget(**raw_budget)
    except (TypeError, ValueError) as error:
        raise FundingAcquisitionError("funding plan capacity budget is invalid") from error
    expected_tasks = _plan_tasks(verified_spec)
    if raw_tasks != json.loads(canonical_json_bytes(expected_tasks)):
        raise FundingAcquisitionError("funding task inventory does not derive from plan spec")
    if verified_budget.rest_staging_bytes < required_funding_staging_bytes(verified_spec):
        raise FundingAcquisitionError("funding staging budget is below fixed page bound")
    if root.name != f"{verified_spec.job_id}--{plan_digest[:16]}":
        raise FundingAcquisitionError("funding directory does not bind its plan identity")
    manifest_path = root / "manifest.json"
    manifest, manifest_digest = _verify_artifact(manifest_path)
    receipt_path = root / "completion-receipt.json"
    if not receipt_path.is_file() or _load_object(receipt_path) != _receipt_payload(
        manifest_path.name, manifest_digest
    ):
        raise FundingAcquisitionError("funding completion receipt does not bind manifest")
    if (
        manifest.get("contract") != FUNDING_MANIFEST_CONTRACT
        or manifest.get("status") != "complete"
        or manifest.get("plan_sha256") != plan_digest
        or manifest.get("job_id") != verified_spec.job_id
        or manifest.get("request_sha256") != verified_spec.request_sha256
        or manifest.get("instrument_evidence_sha256") != verified_spec.instrument_evidence_sha256
        or manifest.get("capacity_evidence_sha256") != verified_spec.capacity_evidence_sha256
    ):
        raise FundingAcquisitionError("funding manifest identity does not bind plan")
    raw_pages = manifest.get("pages")
    if not isinstance(raw_pages, list) or len(raw_pages) != len(expected_tasks):
        raise FundingAcquisitionError("funding manifest page inventory is incomplete")
    total_events = 0
    total_attempts = 0
    empty_range_pages = 0
    boundary_rows: list[dict[str, object]] = []
    batch_boundaries: dict[int, int] | None = {} if load_batch else None
    batch_rows: dict[int, list[tuple[int, str, str]]] | None = {} if load_batch else None
    requested_instruments = (
        {series.instrument_id for series in verified_spec.series} if load_batch else None
    )
    expected_files = {
        "plan.json",
        "plan.receipt.json",
        "manifest.json",
        "manifest.receipt.json",
        "completion-receipt.json",
    }
    for sequence, (task, raw_page) in enumerate(zip(expected_tasks, raw_pages, strict=True)):
        if not isinstance(raw_page, dict) or task.sequence != sequence:
            raise FundingAcquisitionError("funding task/page sequence is not canonical")
        page = root / "pages" / task.artifact_name
        payload, digest = _verify_artifact(page)
        _validate_page_payload(payload, task)
        if (
            raw_page.get("artifact") != f"pages/{page.name}"
            or raw_page.get("artifact_sha256") != digest
            or raw_page.get("attempt_count") != payload.get("attempt_count")
            or raw_page.get("row_count") != payload.get("row_count")
            or raw_page.get("scope") != task.scope
            or raw_page.get("sequence") != sequence
            or raw_page.get("ingestion_id") != f"bybit-funding-page-sha256:{digest}"
        ):
            raise FundingAcquisitionError("funding manifest page facts do not verify")
        row_count = cast(int, payload["row_count"])
        total_attempts += cast(int, payload["attempt_count"])
        if task.scope == "boundary":
            row = cast(list[dict[str, object]], payload["rows"])[0]
            if batch_boundaries is not None:
                batch_boundaries[task.instrument_id] = cast(int, row["funding_time_ms"])
            boundary_rows.append(
                {
                    "artifact_sha256": digest,
                    "funding_time_ms": row["funding_time_ms"],
                    "instrument_id": task.instrument_id,
                }
            )
        else:
            total_events += row_count
            empty_range_pages += row_count == 0
            if batch_rows is not None:
                values = batch_rows.setdefault(task.instrument_id, [])
                values.extend(
                    (
                        cast(int, item["funding_time_ms"]),
                        cast(str, item["funding_rate"]),
                        f"bybit-funding-page-sha256:{digest}",
                    )
                    for item in cast(list[dict[str, object]], payload["rows"])
                )
        expected_files.update((f"pages/{page.name}", f"pages/{page.stem}.receipt.json"))
    boundary_sha = canonical_sha256(boundary_rows)
    expected_request_bound = {
        "actual_http_requests": total_attempts,
        "max_attempts_per_page": verified_spec.max_attempts,
        "max_http_requests_per_run": verified_spec.max_http_requests,
        "target_rps": verified_spec.target_rps,
        "workers": verified_spec.workers,
    }
    observed_request_bound = manifest.get("request_bound")
    if not isinstance(observed_request_bound, dict):
        raise FundingAcquisitionError("funding manifest request bound is invalid")
    adaptive_summary = observed_request_bound.get("adaptive_throttling")
    if adaptive_summary is not None:
        try:
            verify_adaptive_rate_summary(
                adaptive_summary,
                configured_target_rps=verified_spec.target_rps,
                maximum_response_count=total_attempts,
            )
        except AdaptiveRateLimitError as error:
            raise FundingAcquisitionError(
                "funding adaptive throttling summary is invalid"
            ) from error
        expected_request_bound["adaptive_throttling"] = adaptive_summary
    expected_source_policy = {
        "endpoint": "/v5/market/funding/history",
        "page_limit": verified_spec.page_limit,
        "page_span_minutes": verified_spec.page_span_minutes,
        "private_credentials_used": False,
        "saturated_range_pages_accepted": False,
    }
    host = manifest.get("host_preflight")
    if not isinstance(host, dict) or (
        not isinstance(host.get("device_identity_sha256"), str)
        or not SHA256_RE.fullmatch(cast(str, host["device_identity_sha256"]))
        or host.get("storage_kind") not in ("nvme", "ssd")
        or any(
            isinstance(host.get(name), bool)
            or not isinstance(host.get(name), int)
            or cast(int, host[name]) < 0
            for name in (
                "memory_total_bytes",
                "observed_at_ms",
                "observed_free_bytes",
                "planned_peak_memory_bytes",
                "required_free_bytes",
            )
        )
    ):
        raise FundingAcquisitionError("funding host preflight facts are invalid")
    if (
        manifest.get("page_count") != len(expected_tasks)
        or manifest.get("row_count") != total_events
        or manifest.get("boundary_row_count") != len(verified_spec.series)
        or manifest.get("boundary_evidence_sha256") != boundary_sha
        or manifest.get("empty_range_page_count") != empty_range_pages
        or observed_request_bound != expected_request_bound
        or total_attempts > verified_spec.max_http_requests
        or manifest.get("source_policy") != expected_source_policy
    ):
        raise FundingAcquisitionError("funding manifest aggregate facts do not verify")
    if any(path.is_symlink() for path in root.rglob("*")):
        raise FundingAcquisitionError("funding job cannot contain symlinks")
    actual_files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual_files != expected_files:
        raise FundingAcquisitionError("funding job contains orphan or missing files")
    actual_directories = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir()
    }
    if actual_directories != {"pages"}:
        raise FundingAcquisitionError("funding job contains orphan or missing directories")
    completed = CompletedFundingJob(
        job_root=root,
        plan_path=plan_path,
        manifest_path=manifest_path,
        receipt_path=receipt_path,
        manifest_sha256=manifest_digest,
        boundary_evidence_sha256=boundary_sha,
        page_count=len(expected_tasks),
        row_count=total_events,
    )

    batch: CanonicalFundingBatch | None = None
    if (
        batch_boundaries is not None
        and batch_rows is not None
        and requested_instruments is not None
    ):
        batch = _funding_batch_from_verified_rows(
            batch_boundaries,
            batch_rows,
            requested_instruments,
        )
    return completed, batch


def verify_completed_funding_job(job_root: Path) -> CompletedFundingJob:
    """Verify plan, all pages, manifest, completion receipt, and exact allowlist."""

    completed, _batch = _verify_completed_funding_job(job_root, load_batch=False)
    return completed


def load_verified_completed_funding_batch(
    job_root: Path,
) -> tuple[CompletedFundingJob, CanonicalFundingBatch]:
    """Verify and convert a completed funding job in one linear page read."""

    completed, batch = _verify_completed_funding_job(job_root, load_batch=True)
    if batch is None:  # pragma: no cover - guarded by load_batch=True
        raise FundingAcquisitionError("completed funding batch was not built")
    return completed, batch


def load_completed_funding_batch(job_root: Path) -> CanonicalFundingBatch:
    """Verify and convert one completed funding job into the exact Arrow batch."""

    _completed, batch = load_verified_completed_funding_batch(job_root)
    return batch
