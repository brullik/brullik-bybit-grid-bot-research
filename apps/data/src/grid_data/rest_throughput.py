"""Bounded, paced Bybit V5 1m REST throughput evidence."""

from __future__ import annotations

import math
import os
import platform
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from threading import Event, Lock, local
from typing import Any, Literal, Protocol

from grid_bybit_public import BybitPublicError
from grid_bybit_public.transport import TransportError
from grid_contracts.canonical import canonical_sha256
from grid_contracts.market import MINUTE_MS

KlineKind = Literal["trade", "mark"]

OFFICIAL_IP_REQUESTS = 600
OFFICIAL_IP_WINDOW_SECONDS = 5
OFFICIAL_IP_RATE_RPS = OFFICIAL_IP_REQUESTS // OFFICIAL_IP_WINDOW_SECONDS
BENCHMARK_RATE_CEILING_RPS = 96
MAX_WORKERS = 32
MAX_PROFILES = 8
MAX_REQUESTS = 2_000
MAX_SAMPLE_SIZE = 16
PAGE_LIMIT = 1_000
SNAPSHOT_LAG_MINUTES = 10
TARGET_ATTAINMENT_THRESHOLD = Decimal("0.85")
DEFAULT_STAGE_SECONDS = Decimal("4")
DEFAULT_COOLDOWN_SECONDS = Decimal("5.25")


@dataclass(frozen=True, slots=True)
class ThroughputProfile:
    workers: int
    target_rps: int


DEFAULT_PROFILES: tuple[ThroughputProfile, ...] = (
    ThroughputProfile(workers=1, target_rps=1),
    ThroughputProfile(workers=4, target_rps=5),
    ThroughputProfile(workers=8, target_rps=10),
    ThroughputProfile(workers=16, target_rps=20),
    ThroughputProfile(workers=24, target_rps=30),
    ThroughputProfile(workers=32, target_rps=40),
)


@dataclass(frozen=True, slots=True)
class _Target:
    symbol: str
    launch_time_ms: int


@dataclass(frozen=True, slots=True)
class _RequestTask:
    sequence: int
    kind: KlineKind
    symbol: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True, slots=True)
class _Observation:
    sequence: int
    attempted: bool
    elapsed_ns: int | None
    row_count: int
    response_sha256: str | None
    error_code: str | None


class KlineClient(Protocol):
    def kline_page(
        self,
        *,
        kind: KlineKind,
        symbol: str,
        start_ms: int,
        end_ms: int,
        category: Literal["linear", "inverse"] = "linear",
        limit: int = 1000,
    ) -> tuple[tuple[str, ...], ...]: ...


class _Pacer:
    """Reserve globally spaced launch slots; never launch faster than target_rps."""

    def __init__(self, target_rps: int) -> None:
        self._interval_ns = math.ceil(1_000_000_000 / target_rps)
        self._next_ns = time.perf_counter_ns()
        self._lock = Lock()

    def wait(self) -> None:
        with self._lock:
            scheduled_ns = self._next_ns
            self._next_ns += self._interval_ns
        delay_ns = scheduled_ns - time.perf_counter_ns()
        if delay_ns > 0:
            time.sleep(delay_ns / 1_000_000_000)


def parse_profiles(raw: str) -> tuple[ThroughputProfile, ...]:
    """Parse WORKERS:RPS pairs while preserving their declared stage order."""
    profiles: list[ThroughputProfile] = []
    for item in raw.split(","):
        parts = item.strip().split(":")
        if len(parts) != 2:
            raise ValueError("profiles must be comma-separated WORKERS:RPS pairs")
        try:
            workers, target_rps = (int(part) for part in parts)
        except ValueError as error:
            raise ValueError("profile workers and RPS must be integers") from error
        profiles.append(ThroughputProfile(workers=workers, target_rps=target_rps))
    result = tuple(profiles)
    _validate_profiles(result)
    return result


def build_rest_throughput_evidence(
    client_factory: Callable[[], KlineClient],
    inventory: Mapping[str, Any],
    source_assessment: Mapping[str, Any],
    *,
    command: str,
    base_url: str,
    inventory_artifact: str,
    inventory_artifact_sha256: str,
    source_assessment_artifact: str,
    source_assessment_artifact_sha256: str,
    workstation_artifact: str,
    workstation_artifact_sha256: str,
    workstation_captured_at_utc: str,
    profiles: Sequence[ThroughputProfile] = DEFAULT_PROFILES,
    stage_seconds: Decimal = DEFAULT_STAGE_SECONDS,
    cooldown_seconds: Decimal = DEFAULT_COOLDOWN_SECONDS,
    sample_size: int = 8,
    max_requests: int = 1_000,
) -> dict[str, Any]:
    """Measure paced 1m kline-page throughput and retain no response values."""
    normalized_profiles = tuple(profiles)
    _validate_inputs(
        normalized_profiles,
        stage_seconds=stage_seconds,
        cooldown_seconds=cooldown_seconds,
        sample_size=sample_size,
        max_requests=max_requests,
        base_url=base_url,
    )
    request_counts = tuple(
        _stage_request_count(profile, stage_seconds) for profile in normalized_profiles
    )
    planned_request_count = sum(request_counts)
    if planned_request_count > max_requests:
        raise ValueError(
            "planned REST throughput requests exceed max_requests: "
            f"{planned_request_count} > {max_requests}"
        )
    bootstrap_requests = _validate_source_assessment(
        source_assessment,
        inventory_artifact_sha256=inventory_artifact_sha256,
    )
    snapshot_ms = _inventory_snapshot_ms(inventory)
    benchmark_end_ms = (snapshot_ms - SNAPSHOT_LAG_MINUTES * MINUTE_MS) // MINUTE_MS * MINUTE_MS
    max_pages_per_series = math.ceil(planned_request_count / (2 * sample_size)) + 1
    targets, eligible_count = _select_targets(
        inventory,
        sample_size=sample_size,
        benchmark_end_ms=benchmark_end_ms,
        max_pages_per_series=max_pages_per_series,
    )
    stages = _plan_stages(
        normalized_profiles,
        request_counts,
        targets,
        benchmark_end_ms=benchmark_end_ms,
    )
    if sum(len(tasks) for _profile, tasks in stages) != planned_request_count:
        raise RuntimeError("internal request plan count mismatch")

    profile_results: list[dict[str, Any]] = []
    for index, (profile, tasks) in enumerate(stages):
        result = _execute_stage(client_factory, profile, tasks)
        profile_results.append(result)
        if result["status"] == "failed":
            break
        if index + 1 < len(stages) and cooldown_seconds > 0:
            time.sleep(float(cooldown_seconds))

    actual_request_count = sum(int(item["actual_request_count"]) for item in profile_results)
    if actual_request_count > planned_request_count or actual_request_count > max_requests:
        raise RuntimeError("actual request count exceeded its preflighted bound")
    passing_profiles = [item for item in profile_results if item["status"] == "passed"]
    recommendation = _recommendation(passing_profiles)
    projections = _bootstrap_projections(bootstrap_requests, recommendation)
    status = (
        "bounded-benchmark-complete"
        if len(profile_results) == len(stages)
        and all(item["status"] != "failed" for item in profile_results)
        else "bounded-benchmark-partial"
    )
    payload: dict[str, Any] = {
        "command": command,
        "content_sha256": "",
        "evidence_schema": "grid.bybit-rest-throughput/v1",
        "fetched_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "inventory_source": {
            "artifact": inventory_artifact,
            "artifact_sha256": inventory_artifact_sha256,
            "evidence_schema": inventory["evidence_schema"],
            "fetched_at_utc": inventory["fetched_at_utc"],
            "inventory_status": inventory.get("inventory_status"),
        },
        "source_assessment": {
            "artifact": source_assessment_artifact,
            "artifact_sha256": source_assessment_artifact_sha256,
            "evidence_schema": source_assessment["evidence_schema"],
            "fetched_at_utc": source_assessment["fetched_at_utc"],
        },
        "workstation_source": {
            "artifact": workstation_artifact,
            "artifact_sha256": workstation_artifact_sha256,
            "captured_at_utc": workstation_captured_at_utc,
        },
        "runtime": {
            "logical_cpu_count": os.cpu_count(),
            "platform_machine": platform.machine(),
            "platform_system": platform.system(),
            "python_version": platform.python_version(),
        },
        "official_limit": {
            "benchmark_ceiling_requests_per_second": BENCHMARK_RATE_CEILING_RPS,
            "default_http_ip_requests": OFFICIAL_IP_REQUESTS,
            "default_http_ip_window_seconds": OFFICIAL_IP_WINDOW_SECONDS,
            "implied_default_http_ip_requests_per_second": OFFICIAL_IP_RATE_RPS,
            "minimum_headroom_percent": 20,
            "source": "https://bybit-exchange.github.io/docs/v5/rate-limit",
        },
        "source_policy": {
            "mark_price_1m": "/v5/market/mark-price-kline",
            "trade_price_1m": "/v5/market/kline",
        },
        "selection": {
            "algorithm": "oldest-current-trading-usdt-linear-perpetual-v1",
            "benchmark_end_ms": benchmark_end_ms,
            "eligible_count": eligible_count,
            "requested_sample_size": sample_size,
            "symbols": [target.symbol for target in targets],
        },
        "workload": {
            "base_url": base_url,
            "cooldown_seconds": _decimal_text(cooldown_seconds),
            "dataset_mix": {
                "mark_price_1m": sum(
                    task.kind == "mark" for _profile, tasks in stages for task in tasks
                ),
                "trade_price_1m": sum(
                    task.kind == "trade" for _profile, tasks in stages for task in tasks
                ),
            },
            "kline_page_limit": PAGE_LIMIT,
            "page_minutes": PAGE_LIMIT,
            "stage_seconds": _decimal_text(stage_seconds),
            "transport_max_attempts": 1,
        },
        "request_audit": {
            "actual_request_count": actual_request_count,
            "executed_profile_count": len(profile_results),
            "max_requests": max_requests,
            "planned_profile_count": len(stages),
            "planned_request_count": planned_request_count,
        },
        "storage_policy": {
            "market_rows_persisted": False,
            "market_values_persisted": False,
            "response_content_hashes_persisted": True,
            "tick_rows_requested": False,
        },
        "profiles": profile_results,
        "recommendation": recommendation,
        "bootstrap_request_only_projection": projections,
        "limitations": [
            (
                "This is a short, paced measurement from one host and network route; it is not "
                "a service-level guarantee or a license to run at the official IP limit."
            ),
            (
                "The benchmark ceiling retains at least 20% headroom below the documented "
                "600 requests per five-second IP limit and stops the sweep after the first "
                "endpoint or page-validation failure."
            ),
            (
                "Only full 1,000-row trade-price and mark-price 1m pages are measured. Funding "
                "is below one percent of the bound current bootstrap request mix and is excluded "
                "from this throughput workload."
            ),
            (
                "Rows are validated and hashed in memory; only aggregate counts, timings, and "
                "hashes are persisted. No market values or tick rows are retained."
            ),
            (
                "Request-only bootstrap projections exclude retries, gaps, staging, validation, "
                "canonical writes, compaction, and Bybit or network variability."
            ),
            "This evidence does not authorize Phase 2 or close Gate 1.",
        ],
        "status": status,
    }
    hash_input = dict(payload)
    hash_input.pop("content_sha256")
    payload["content_sha256"] = canonical_sha256(hash_input)
    return payload


def _validate_inputs(
    profiles: tuple[ThroughputProfile, ...],
    *,
    stage_seconds: Decimal,
    cooldown_seconds: Decimal,
    sample_size: int,
    max_requests: int,
    base_url: str,
) -> None:
    _validate_profiles(profiles)
    if not Decimal("0.1") <= stage_seconds <= Decimal("10"):
        raise ValueError("stage_seconds must be in [0.1, 10]")
    if not Decimal("0") <= cooldown_seconds <= Decimal("10"):
        raise ValueError("cooldown_seconds must be in [0, 10]")
    if not 1 <= sample_size <= MAX_SAMPLE_SIZE:
        raise ValueError(f"sample_size must be in [1, {MAX_SAMPLE_SIZE}]")
    if not 1 <= max_requests <= MAX_REQUESTS:
        raise ValueError(f"max_requests must be in [1, {MAX_REQUESTS}]")
    if base_url != "https://api.bybit.com":
        raise ValueError("REST throughput evidence permits only https://api.bybit.com")


def _validate_profiles(profiles: tuple[ThroughputProfile, ...]) -> None:
    if not 1 <= len(profiles) <= MAX_PROFILES:
        raise ValueError(f"profile count must be in [1, {MAX_PROFILES}]")
    previous_workers = 0
    previous_rps = 0
    for profile in profiles:
        if not 1 <= profile.workers <= MAX_WORKERS:
            raise ValueError(f"profile workers must be in [1, {MAX_WORKERS}]")
        if not 1 <= profile.target_rps <= BENCHMARK_RATE_CEILING_RPS:
            raise ValueError(f"profile RPS must be in [1, {BENCHMARK_RATE_CEILING_RPS}]")
        if profile.workers < previous_workers or profile.target_rps <= previous_rps:
            raise ValueError("profile workers must be nondecreasing and RPS strictly increasing")
        previous_workers = profile.workers
        previous_rps = profile.target_rps


def _stage_request_count(profile: ThroughputProfile, stage_seconds: Decimal) -> int:
    return int(
        (Decimal(profile.target_rps) * stage_seconds).to_integral_value(rounding=ROUND_CEILING)
    )


def _inventory_snapshot_ms(inventory: Mapping[str, Any]) -> int:
    if inventory.get("evidence_schema") != "grid.bybit-public-inventory/v1":
        raise ValueError("unsupported instrument inventory evidence")
    raw = inventory.get("fetched_at_utc")
    if not isinstance(raw, str) or not raw.endswith("Z"):
        raise ValueError("inventory fetched_at_utc must be UTC text")
    try:
        value = datetime.fromisoformat(raw.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise ValueError("inventory fetched_at_utc is invalid") from error
    if value.tzinfo != UTC:
        raise ValueError("inventory fetched_at_utc must resolve to UTC")
    return int(value.timestamp() * 1_000)


def _validate_source_assessment(
    source: Mapping[str, Any], *, inventory_artifact_sha256: str
) -> dict[str, int]:
    if source.get("evidence_schema") != "grid.bybit-history-source-assessment/v2":
        raise ValueError("throughput evidence requires the 1m-only v2 source assessment")
    inventory_source = source.get("inventory_source")
    estimate = source.get("inventory_backfill_estimate")
    if not isinstance(inventory_source, Mapping) or not isinstance(estimate, Mapping):
        raise ValueError("source assessment is missing bound inventory estimates")
    if inventory_source.get("artifact_sha256") != inventory_artifact_sha256:
        raise ValueError("source assessment is not bound to the supplied inventory")
    combined = estimate.get("combined_requests")
    if not isinstance(combined, Mapping):
        raise ValueError("source assessment has no combined request estimates")
    names = ("current_funding_intervals", "conservative_60m_funding_interval")
    result: dict[str, int] = {}
    for name in names:
        value = combined.get(name)
        if not isinstance(value, int) or value <= 0:
            raise ValueError("source assessment combined request estimates must be positive")
        result[name] = value
    return result


def _select_targets(
    inventory: Mapping[str, Any],
    *,
    sample_size: int,
    benchmark_end_ms: int,
    max_pages_per_series: int,
) -> tuple[tuple[_Target, ...], int]:
    raw_records = inventory.get("records")
    if not isinstance(raw_records, list):
        raise ValueError("instrument inventory records must be a list")
    earliest_required_ms = benchmark_end_ms - (max_pages_per_series * PAGE_LIMIT - 1) * MINUTE_MS
    symbols: set[str] = set()
    candidates: list[_Target] = []
    for raw in raw_records:
        if not isinstance(raw, Mapping):
            raise ValueError("instrument inventory records must be objects")
        if not (
            raw.get("contract_type") == "LinearPerpetual"
            and raw.get("quote_coin") == "USDT"
            and raw.get("settle_coin") == "USDT"
        ):
            continue
        symbol = raw.get("symbol")
        if not isinstance(symbol, str) or not symbol or symbol in symbols:
            raise ValueError("inventory USDT perpetual symbols must be unique non-empty text")
        symbols.add(symbol)
        launch_time_ms = raw.get("launch_time_ms")
        if (
            raw.get("status") == "Trading"
            and isinstance(launch_time_ms, int)
            and 0 <= launch_time_ms <= earliest_required_ms
        ):
            candidates.append(_Target(symbol=symbol, launch_time_ms=launch_time_ms))
    candidates.sort(key=lambda item: (item.launch_time_ms, item.symbol))
    if len(candidates) < sample_size:
        raise ValueError("inventory has too few mature Trading USDT perpetuals")
    return tuple(candidates[:sample_size]), len(candidates)


def _plan_stages(
    profiles: tuple[ThroughputProfile, ...],
    request_counts: tuple[int, ...],
    targets: tuple[_Target, ...],
    *,
    benchmark_end_ms: int,
) -> tuple[tuple[ThroughputProfile, tuple[_RequestTask, ...]], ...]:
    counters: Counter[tuple[KlineKind, str]] = Counter()
    sequence = 0
    stages: list[tuple[ThroughputProfile, tuple[_RequestTask, ...]]] = []
    for profile, request_count in zip(profiles, request_counts, strict=True):
        tasks: list[_RequestTask] = []
        for _ in range(request_count):
            kind: KlineKind = "trade" if sequence % 2 == 0 else "mark"
            target = targets[(sequence // 2) % len(targets)]
            key = (kind, target.symbol)
            page_number = counters[key]
            counters[key] += 1
            end_ms = benchmark_end_ms - page_number * PAGE_LIMIT * MINUTE_MS
            start_ms = end_ms - (PAGE_LIMIT - 1) * MINUTE_MS
            if start_ms < target.launch_time_ms:
                raise ValueError("planned throughput page predates instrument launch")
            tasks.append(
                _RequestTask(
                    sequence=sequence,
                    kind=kind,
                    symbol=target.symbol,
                    start_ms=start_ms,
                    end_ms=end_ms,
                )
            )
            sequence += 1
        stages.append((profile, tuple(tasks)))
    return tuple(stages)


def _execute_stage(
    client_factory: Callable[[], KlineClient],
    profile: ThroughputProfile,
    tasks: tuple[_RequestTask, ...],
) -> dict[str, Any]:
    stop = Event()
    pacer = _Pacer(profile.target_rps)
    thread_state = local()

    def execute(task: _RequestTask) -> _Observation:
        if stop.is_set():
            return _Observation(task.sequence, False, None, 0, None, "skipped-after-error")
        pacer.wait()
        if stop.is_set():
            return _Observation(task.sequence, False, None, 0, None, "skipped-after-error")
        client = getattr(thread_state, "client", None)
        if client is None:
            client = client_factory()
            thread_state.client = client
        started_ns = time.perf_counter_ns()
        try:
            rows = client.kline_page(
                kind=task.kind,
                symbol=task.symbol,
                start_ms=task.start_ms,
                end_ms=task.end_ms,
                limit=PAGE_LIMIT,
            )
            _validate_full_page(rows, task)
            digest = canonical_sha256([list(row) for row in rows])
            return _Observation(
                task.sequence,
                True,
                time.perf_counter_ns() - started_ns,
                len(rows),
                digest,
                None,
            )
        except Exception as error:
            stop.set()
            return _Observation(
                task.sequence,
                True,
                time.perf_counter_ns() - started_ns,
                0,
                None,
                _error_code(error),
            )

    wall_started_ns = time.perf_counter_ns()
    with ThreadPoolExecutor(max_workers=profile.workers) as executor:
        observations = tuple(executor.map(execute, tasks))
    wall_elapsed_ns = max(1, time.perf_counter_ns() - wall_started_ns)
    attempted = tuple(item for item in observations if item.attempted)
    successful = tuple(item for item in attempted if item.error_code is None)
    errors = Counter(item.error_code for item in attempted if item.error_code is not None)
    latency_ns = sorted(item.elapsed_ns for item in attempted if item.elapsed_ns is not None)
    actual_request_count = len(attempted)
    observed_rps = Decimal(actual_request_count) * Decimal(1_000_000_000) / Decimal(wall_elapsed_ns)
    target_attainment = observed_rps / Decimal(profile.target_rps)
    failed = bool(actual_request_count != len(tasks) or errors or len(successful) != len(tasks))
    status = (
        "failed"
        if failed
        else "passed"
        if target_attainment >= TARGET_ATTAINMENT_THRESHOLD
        else "under-target"
    )
    return {
        "workers": profile.workers,
        "target_requests_per_second": profile.target_rps,
        "planned_request_count": len(tasks),
        "actual_request_count": actual_request_count,
        "success_count": len(successful),
        "error_count": sum(errors.values()),
        "full_page_count": len(successful),
        "row_count": sum(item.row_count for item in successful),
        "wall_duration_seconds": _seconds_text(wall_elapsed_ns),
        "observed_requests_per_second": _metric_text(observed_rps),
        "target_attainment_ratio": _metric_text(target_attainment),
        "observed_rows_per_second": _metric_text(observed_rps * PAGE_LIMIT),
        "latency_ms": _latency_summary(latency_ns),
        "response_hash_aggregate": canonical_sha256(
            [
                {"sequence": item.sequence, "sha256": item.response_sha256}
                for item in sorted(successful, key=lambda value: value.sequence)
            ]
        ),
        "error_counts": dict(sorted((str(key), value) for key, value in errors.items())),
        "status": status,
    }


def _validate_full_page(rows: tuple[tuple[str, ...], ...], task: _RequestTask) -> None:
    if len(rows) != PAGE_LIMIT:
        raise ValueError("short-kline-page")
    try:
        timestamps = [int(row[0]) for row in rows]
    except (IndexError, ValueError) as error:
        raise ValueError("invalid-kline-timestamp") from error
    expected = list(range(task.end_ms, task.start_ms - 1, -MINUTE_MS))
    if timestamps != expected:
        raise ValueError("non-contiguous-kline-page")


def _error_code(error: Exception) -> str:
    if isinstance(error, TransportError):
        text = str(error)
        if "HTTP error 403" in text:
            return "http-403-rate-limit"
        if "HTTP error 429" in text:
            return "http-429-rate-limit"
        return "transport-error"
    if isinstance(error, BybitPublicError):
        if "retCode=10006" in str(error):
            return "bybit-rate-limit-10006"
        return "bybit-public-error"
    if isinstance(error, ValueError):
        return (
            str(error)
            if str(error)
            in {
                "invalid-kline-timestamp",
                "non-contiguous-kline-page",
                "short-kline-page",
            }
            else "page-validation-error"
        )
    return "unexpected-error"


def _latency_summary(values_ns: Sequence[int]) -> dict[str, str] | None:
    if not values_ns:
        return None
    ordered = sorted(values_ns)
    return {
        "min": _milliseconds_text(ordered[0]),
        "p50": _milliseconds_text(_nearest_rank(ordered, 50)),
        "p95": _milliseconds_text(_nearest_rank(ordered, 95)),
        "p99": _milliseconds_text(_nearest_rank(ordered, 99)),
        "max": _milliseconds_text(ordered[-1]),
    }


def _nearest_rank(values: Sequence[int], percentile: int) -> int:
    index = max(0, math.ceil(percentile * len(values) / 100) - 1)
    return values[index]


def _recommendation(passing_profiles: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    if not passing_profiles:
        return None
    selected = passing_profiles[-1]
    return {
        "candidate_workers": selected["workers"],
        "candidate_target_requests_per_second": selected["target_requests_per_second"],
        "observed_requests_per_second": selected["observed_requests_per_second"],
        "basis": (
            "highest error-free profile with full 1,000-row pages and at least 85% target "
            "attainment; candidate only, not a Gate 1 or Phase 2 approval"
        ),
    }


def _bootstrap_projections(
    bootstrap_requests: Mapping[str, int], recommendation: Mapping[str, Any] | None
) -> dict[str, dict[str, Any]] | None:
    if recommendation is None:
        return None
    observed_rps = Decimal(str(recommendation["observed_requests_per_second"]))
    if observed_rps <= 0:
        return None
    result: dict[str, dict[str, Any]] = {}
    for name, request_count in sorted(bootstrap_requests.items()):
        seconds = int(
            (Decimal(request_count) / observed_rps).to_integral_value(rounding=ROUND_CEILING)
        )
        result[name] = {
            "request_count": request_count,
            "request_only_seconds": seconds,
            "request_only_hours": _metric_text(Decimal(seconds) / Decimal(3_600)),
        }
    return result


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _metric_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def _seconds_text(nanoseconds: int) -> str:
    return _metric_text(Decimal(nanoseconds) / Decimal(1_000_000_000))


def _milliseconds_text(nanoseconds: int) -> str:
    value = Decimal(nanoseconds) / Decimal(1_000_000)
    return format(value.quantize(Decimal("0.001")), "f")


def default_profile_text() -> str:
    return ",".join(f"{profile.workers}:{profile.target_rps}" for profile in DEFAULT_PROFILES)
