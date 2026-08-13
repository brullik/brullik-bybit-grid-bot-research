"""Receipt-bound execution of a verified funding repair discovery plan."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, cast

from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_market_store import MAX_MEMORY_PERCENT, CapacityBudget, HostSnapshot

from grid_data.evidence import verify_evidence
from grid_data.funding_acquisition import (
    MAX_PAGE_ARTIFACT_BYTES,
    STAGING_METADATA_BYTES,
    CompletedFundingJob,
    FundingAcquisitionError,
    FundingClient,
    FundingJobPlan,
    execute_funding_job,
    load_completed_funding_batch,
    preflight_funding_job,
    verify_completed_funding_job,
)
from grid_data.funding_publication import SOFTWARE_IDENTITY_RE
from grid_data.funding_repair_plan import (
    VerifiedFundingRepairPlan,
    verify_funding_repair_plan,
)
from grid_data.funding_request import resolve_funding_request_payload

FUNDING_REPAIR_EXECUTION_CONTRACT: Final = "grid.bybit-funding-repair-execution/v1"
MAX_PREFLIGHT_AGE_MS: Final = 60_000


@dataclass(frozen=True, slots=True)
class FundingRepairExecutionPreflight:
    verified_plan: VerifiedFundingRepairPlan
    task_plans: tuple[FundingJobPlan, ...]
    executor_software_identity: str
    instrument_registry_sha256: str
    capacity_evidence_sha256: str
    snapshot: HostSnapshot
    required_free_bytes: int
    planned_peak_memory_bytes: int
    existing_complete_count: int


@dataclass(frozen=True, slots=True)
class FundingRepairExecutionResult:
    payload: dict[str, object]
    passed: bool
    completed_jobs: tuple[CompletedFundingJob, ...]


@dataclass(frozen=True, slots=True)
class VerifiedFundingRepairExecution:
    path: Path
    artifact_sha256: str
    payload: dict[str, object]
    passed: bool
    completed_jobs: tuple[CompletedFundingJob, ...]
    verified_plan: VerifiedFundingRepairPlan


def _object(path: Path, *, name: str) -> tuple[Path, dict[str, object]]:
    resolved = path.resolve()
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FundingAcquisitionError(f"{name} cannot be loaded") from error
    if not isinstance(raw, dict):
        raise FundingAcquisitionError(f"{name} must be an object")
    return resolved, cast(dict[str, object], raw)


def _integer(parent: dict[str, object], key: str, *, positive: bool = False) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise FundingAcquisitionError(
            f"funding repair execution {key} must be a {qualifier} integer"
        )
    return value


def _generated_at(value: str) -> str:
    if not value.endswith("Z"):
        raise FundingAcquisitionError("generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise FundingAcquisitionError("generated_at_utc is invalid") from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise FundingAcquisitionError("generated_at_utc must be UTC")
    return value


def _raw_tasks(plan: VerifiedFundingRepairPlan) -> list[dict[str, object]]:
    value = plan.payload.get("tasks")
    if not isinstance(value, list) or len(value) != plan.task_count:
        raise FundingAcquisitionError("funding repair plan task inventory is invalid")
    if any(not isinstance(item, dict) for item in value):
        raise FundingAcquisitionError("funding repair plan tasks must be objects")
    return cast(list[dict[str, object]], value)


def _candidate_times(task: dict[str, object]) -> list[int]:
    raw = task.get("candidate_settlement_times_ms")
    expected_count = _integer(task, "candidate_settlement_count", positive=True)
    if (
        not isinstance(raw, list)
        or len(raw) != expected_count
        or any(isinstance(item, bool) or not isinstance(item, int) for item in raw)
    ):
        raise FundingAcquisitionError("funding repair candidate timestamps are invalid")
    values = cast(list[int], raw)
    if values != sorted(set(values)) or any(value < 0 or value % 60_000 for value in values):
        raise FundingAcquisitionError("funding repair candidate timestamps are not canonical")
    if values[0] != task.get("start_ms") or values[-1] != task.get("end_ms"):
        raise FundingAcquisitionError("funding repair candidate bounds do not match task")
    return values


def _assert_aggregate_resources(
    snapshot: HostSnapshot,
    *,
    required_free_bytes: int,
    planned_peak_memory_bytes: int,
) -> None:
    if snapshot.volume_free_bytes < required_free_bytes:
        raise FundingAcquisitionError(
            "insufficient free space for the complete remaining funding repair plan"
        )
    if planned_peak_memory_bytes > snapshot.memory_available_bytes:
        raise FundingAcquisitionError("insufficient available memory for funding repair execution")
    if planned_peak_memory_bytes * 100 > snapshot.memory_total_bytes * MAX_MEMORY_PERCENT:
        raise FundingAcquisitionError("funding repair execution exceeds the 70% total-memory gate")


def _assert_execute_snapshot(
    preflight: FundingRepairExecutionPreflight,
    snapshot: HostSnapshot,
    *,
    now_ms: int,
) -> None:
    age = now_ms - snapshot.observed_at_ms
    if age < 0 or age > MAX_PREFLIGHT_AGE_MS:
        raise FundingAcquisitionError("funding repair execution host snapshot must be fresh")
    if (
        snapshot.device_identity_sha256 != preflight.snapshot.device_identity_sha256
        or snapshot.memory_total_bytes != preflight.snapshot.memory_total_bytes
    ):
        raise FundingAcquisitionError(
            "host or storage identity changed after funding repair preflight"
        )
    _assert_aggregate_resources(
        snapshot,
        required_free_bytes=preflight.required_free_bytes,
        planned_peak_memory_bytes=preflight.planned_peak_memory_bytes,
    )


def preflight_funding_repair_execution(
    repair_plan_path: Path,
    coverage_audit_path: Path,
    original_job_root: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    store_root: Path,
    repair_staging_root: Path,
    snapshot: HostSnapshot,
    *,
    now_ms: int,
    closed_before_ms: int,
    executor_software_identity: str,
) -> FundingRepairExecutionPreflight:
    """Preflight every embedded public request and one aggregate staging bound."""

    if not SOFTWARE_IDENTITY_RE.fullmatch(executor_software_identity):
        raise FundingAcquisitionError(
            "executor_software_identity must be git:<40-character-lowercase-commit-sha>"
        )
    verified = verify_funding_repair_plan(
        repair_plan_path,
        coverage_audit_path,
        original_job_root,
        instrument_registry_path,
        capacity_evidence_path,
        store_root,
    )
    resolved_requests = []
    for sequence, task in enumerate(_raw_tasks(verified)):
        if _integer(task, "sequence") != sequence:
            raise FundingAcquisitionError("funding repair task sequence is not canonical")
        request = task.get("request")
        symbol = task.get("symbol")
        predecessor = _integer(task, "predecessor_settlement_ms")
        _candidate_times(task)
        if not isinstance(request, dict) or not isinstance(symbol, str):
            raise FundingAcquisitionError("funding repair task has no embedded request identity")
        resolved = resolve_funding_request_payload(
            cast(dict[str, object], request),
            source_path=verified.path,
            instrument_registry_path=instrument_registry_path,
            capacity_evidence_path=capacity_evidence_path,
            predecessor_by_symbol={symbol: predecessor},
        )
        if resolved.request_sha256 != task.get("request_sha256"):
            raise FundingAcquisitionError("embedded funding repair request hash does not verify")
        if (
            len(resolved.spec.series) != 1
            or resolved.spec.series[0].instrument_id != task.get("instrument_id")
            or resolved.spec.series[0].predecessor_settlement_ms != predecessor
        ):
            raise FundingAcquisitionError(
                "embedded funding repair request does not resolve to its planned series"
            )
        resolved_requests.append(resolved)

    active_values = {item.budget.active_and_building_bytes for item in resolved_requests}
    reserve_values = {item.budget.operating_reserve_bytes for item in resolved_requests}
    if len(active_values) != 1 or len(reserve_values) != 1:
        raise FundingAcquisitionError("funding repair requests do not share one capacity policy")
    aggregate_budget = CapacityBudget(
        active_and_building_bytes=next(iter(active_values)),
        rest_staging_bytes=sum(item.budget.rest_staging_bytes for item in resolved_requests),
        operating_reserve_bytes=next(iter(reserve_values)),
    )
    task_plans = tuple(
        preflight_funding_job(
            repair_staging_root,
            item.spec,
            aggregate_budget,
            snapshot,
            now_ms=now_ms,
            closed_before_ms=closed_before_ms,
        )
        for item in resolved_requests
    )
    job_roots = [item.paths.job_root for item in task_plans]
    if len(job_roots) != len(set(job_roots)):
        raise FundingAcquisitionError(
            "funding repair tasks resolve to duplicate Landing identities"
        )
    registry_hashes = {item.registry.artifact_sha256 for item in resolved_requests}
    capacity_hashes = {item.capacity_artifact_sha256 for item in resolved_requests}
    if len(registry_hashes) != 1 or len(capacity_hashes) != 1:
        raise FundingAcquisitionError("funding repair tasks do not share one evidence identity")
    remaining_staging_bytes = sum(
        0
        if item.existing_complete
        else STAGING_METADATA_BYTES + len(item.pending_tasks) * MAX_PAGE_ARTIFACT_BYTES
        for item in task_plans
    )
    required_free_bytes = (
        aggregate_budget.active_and_building_bytes
        + aggregate_budget.operating_reserve_bytes
        + remaining_staging_bytes
    )
    planned_peak_memory_bytes = max(item.planned_peak_memory_bytes for item in task_plans)
    _assert_aggregate_resources(
        snapshot,
        required_free_bytes=required_free_bytes,
        planned_peak_memory_bytes=planned_peak_memory_bytes,
    )
    return FundingRepairExecutionPreflight(
        verified_plan=verified,
        task_plans=task_plans,
        executor_software_identity=executor_software_identity,
        instrument_registry_sha256=next(iter(registry_hashes)),
        capacity_evidence_sha256=next(iter(capacity_hashes)),
        snapshot=snapshot,
        required_free_bytes=required_free_bytes,
        planned_peak_memory_bytes=planned_peak_memory_bytes,
        existing_complete_count=sum(item.existing_complete for item in task_plans),
    )


def _task_result(
    task: dict[str, object],
    completed: CompletedFundingJob,
    *,
    instrument_registry_sha256: str,
    capacity_evidence_sha256: str,
) -> tuple[dict[str, object], bool]:
    sequence = _integer(task, "sequence")
    instrument_id = _integer(task, "instrument_id", positive=True)
    predecessor = _integer(task, "predecessor_settlement_ms")
    expected_times = _candidate_times(task)
    request = task.get("request")
    if not isinstance(request, dict):
        raise FundingAcquisitionError("funding repair task has no embedded request")
    funding_plan = _object(completed.plan_path, name="funding repair Landing plan")[1]
    raw_spec = funding_plan.get("spec")
    if not isinstance(raw_spec, dict):
        raise FundingAcquisitionError("funding repair Landing plan has no spec")
    raw_series = raw_spec.get("series")
    if (
        not isinstance(raw_series, list)
        or len(raw_series) != 1
        or not isinstance(raw_series[0], dict)
    ):
        raise FundingAcquisitionError("funding repair Landing plan series is invalid")
    series = cast(dict[str, object], raw_series[0])
    requested_series = request.get("series")
    if (
        not isinstance(requested_series, list)
        or len(requested_series) != 1
        or not isinstance(requested_series[0], dict)
    ):
        raise FundingAcquisitionError("embedded funding repair request series is invalid")
    request_series = cast(dict[str, object], requested_series[0])
    expected_series_facts = {
        "category": "linear",
        "end_ms": request_series.get("end_ms"),
        "instrument_id": instrument_id,
        "predecessor_settlement_ms": predecessor,
        "start_ms": request_series.get("start_ms"),
        "symbol": task.get("symbol"),
    }
    if any(series.get(key) != value for key, value in expected_series_facts.items()):
        raise FundingAcquisitionError(
            "funding repair Landing series does not match its embedded request"
        )
    expected_spec_facts = {
        "capacity_evidence_sha256": capacity_evidence_sha256,
        "instrument_evidence_sha256": instrument_registry_sha256,
        "job_id": request.get("job_id"),
        "max_attempts": request.get("max_attempts"),
        "max_http_requests": request.get("max_http_requests"),
        "page_limit": request.get("page_limit"),
        "page_span_minutes": request.get("page_span_minutes"),
        "request_sha256": task.get("request_sha256"),
        "target_rps": request.get("target_rps"),
        "workers": request.get("workers"),
    }
    if any(raw_spec.get(key) != value for key, value in expected_spec_facts.items()):
        raise FundingAcquisitionError(
            "funding repair Landing plan does not match its embedded request"
        )
    manifest = _object(completed.manifest_path, name="funding repair Landing manifest")[1]
    request_bound = manifest.get("request_bound")
    if not isinstance(request_bound, dict):
        raise FundingAcquisitionError("funding repair manifest has no request bound")
    actual_requests = _integer(cast(dict[str, object], request_bound), "actual_http_requests")
    observed_times: list[int] = []
    if completed.row_count:
        batch = load_completed_funding_batch(completed.job_root)
        identifiers = batch.table.column("instrument_id").to_pylist()
        if any(value != instrument_id for value in identifiers):
            raise FundingAcquisitionError("funding repair Landing has an unexpected instrument")
        observed_times = cast(list[int], batch.table.column("funding_time_ms").to_pylist())
    if len(observed_times) != completed.row_count or observed_times != sorted(set(observed_times)):
        raise FundingAcquisitionError("funding repair Landing timestamp inventory is inconsistent")
    expected_set = set(expected_times)
    observed_set = set(observed_times)
    missing_count = len(expected_set - observed_set)
    unexpected_count = len(observed_set - expected_set)
    exact_confirmation = observed_times == expected_times
    result: dict[str, object] = {
        "actual_http_requests": actual_requests,
        "candidate_settlement_count": len(expected_times),
        "end_ms": expected_times[-1],
        "exact_source_confirmation": exact_confirmation,
        "funding_manifest_sha256": completed.manifest_sha256,
        "funding_plan_sha256": sha256_file(completed.plan_path),
        "instrument_id": instrument_id,
        "job_directory": completed.job_root.name,
        "missing_candidate_count": missing_count,
        "observed_event_count": completed.row_count,
        "page_count": completed.page_count,
        "request_sha256": task.get("request_sha256"),
        "sequence": sequence,
        "start_ms": expected_times[0],
        "status": "passed" if exact_confirmation else "blocked",
        "symbol": task.get("symbol"),
        "unexpected_event_count": unexpected_count,
    }
    return result, exact_confirmation


def build_funding_repair_execution_evidence(
    verified_plan: VerifiedFundingRepairPlan,
    completed_jobs: tuple[CompletedFundingJob, ...],
    *,
    generated_at_utc: str,
    executor_software_identity: str,
    instrument_registry_sha256: str,
    capacity_evidence_sha256: str,
) -> FundingRepairExecutionResult:
    """Build private rate-free evidence from all completed standard funding jobs."""

    if not SOFTWARE_IDENTITY_RE.fullmatch(executor_software_identity):
        raise FundingAcquisitionError(
            "executor_software_identity must be git:<40-character-lowercase-commit-sha>"
        )
    tasks = _raw_tasks(verified_plan)
    if len(completed_jobs) != len(tasks):
        raise FundingAcquisitionError(
            "funding repair execution does not contain every planned task"
        )
    task_results: list[dict[str, object]] = []
    task_passes: list[bool] = []
    for task, completed in zip(tasks, completed_jobs, strict=True):
        result, passed = _task_result(
            task,
            completed,
            instrument_registry_sha256=instrument_registry_sha256,
            capacity_evidence_sha256=capacity_evidence_sha256,
        )
        task_results.append(result)
        task_passes.append(passed)
    actual_requests = sum(cast(int, item["actual_http_requests"]) for item in task_results)
    observed_events = sum(cast(int, item["observed_event_count"]) for item in task_results)
    missing_candidates = sum(cast(int, item["missing_candidate_count"]) for item in task_results)
    unexpected_events = sum(cast(int, item["unexpected_event_count"]) for item in task_results)
    bindings = cast(dict[str, object], verified_plan.payload["bindings"])
    limits = cast(dict[str, object], verified_plan.payload["limits"])
    planned_requests = _integer(limits, "planned_max_http_requests", positive=True)
    planned_candidates = _integer(limits, "candidate_settlement_count", positive=True)
    if actual_requests > planned_requests:
        raise FundingAcquisitionError("funding repair execution exceeds its request bound")
    if observed_events != planned_candidates - missing_candidates + unexpected_events:
        raise FundingAcquisitionError(
            "funding repair execution does not account for every observed settlement"
        )
    passed = all(task_passes) and missing_candidates == 0 and unexpected_events == 0
    payload: dict[str, object] = {
        "bindings": {
            "canonical_parent_manifest_sha256": bindings["canonical_manifest_sha256"],
            "capacity_evidence_sha256": capacity_evidence_sha256,
            "chronology_anomaly_records_sha256": bindings["chronology_anomaly_records_sha256"],
            "coverage_audit_artifact_sha256": bindings["coverage_audit_artifact_sha256"],
            "coverage_audit_content_sha256": bindings["coverage_audit_content_sha256"],
            "instrument_registry_sha256": instrument_registry_sha256,
            "original_funding_manifest_sha256": bindings["funding_manifest_sha256"],
            "repair_plan_artifact_sha256": verified_plan.artifact_sha256,
            "repair_plan_content_sha256": verified_plan.payload["content_sha256"],
        },
        "contract": FUNDING_REPAIR_EXECUTION_CONTRACT,
        "dataset_id": verified_plan.payload["dataset_id"],
        "executor_software_identity": executor_software_identity,
        "generated_at_utc": _generated_at(generated_at_utc),
        "limits": {
            "actual_http_requests": actual_requests,
            "candidate_settlement_count": planned_candidates,
            "missing_candidate_count": missing_candidates,
            "observed_event_count": observed_events,
            "planned_max_http_requests": planned_requests,
            "task_count": len(task_results),
            "unexpected_event_count": unexpected_events,
        },
        "limitations": [
            "Execution covers only candidate settlements in the bound private repair plan.",
            "A source-confirmed candidate does not accept a historical schedule change.",
            "A passed execution does not mutate or supersede the canonical parent dataset.",
            "Immutable repair-child publication and post-publication coverage remain separate.",
        ],
        "mutation_policy": {
            "canonical_parent_mutated": False,
            "market_requests_receipt_verified": True,
            "repair_child_published": False,
            "schedule_change_accepted": False,
        },
        "status": "passed" if passed else "blocked",
        "storage_policy": {
            "account_data_included": False,
            "credentials_included": False,
            "github_commit_eligible": False,
            "market_values_included": False,
            "private_runtime_artifact": True,
            "runtime_paths_included": False,
        },
        "tasks": task_results,
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return FundingRepairExecutionResult(
        payload=payload,
        passed=passed,
        completed_jobs=completed_jobs,
    )


def execute_funding_repair(
    preflight: FundingRepairExecutionPreflight,
    client_factory: Callable[[], FundingClient],
    snapshot_provider: Callable[[], HostSnapshot],
    *,
    generated_at_utc: str,
    executor_software_identity: str,
    now_ms: Callable[[], int],
) -> FundingRepairExecutionResult:
    """Execute standard funding jobs sequentially and retain receipt-based resume."""

    if not SOFTWARE_IDENTITY_RE.fullmatch(executor_software_identity):
        raise FundingAcquisitionError(
            "executor_software_identity must be git:<40-character-lowercase-commit-sha>"
        )
    if executor_software_identity != preflight.executor_software_identity:
        raise FundingAcquisitionError("funding repair executor identity changed after preflight")
    _generated_at(generated_at_utc)
    execution_snapshot = snapshot_provider()
    execution_now = now_ms()
    _assert_execute_snapshot(preflight, execution_snapshot, now_ms=execution_now)
    completed = tuple(
        execute_funding_job(
            task_plan,
            client_factory,
            snapshot_provider,
            now_ms=now_ms,
        )
        for task_plan in preflight.task_plans
    )
    return build_funding_repair_execution_evidence(
        preflight.verified_plan,
        completed,
        generated_at_utc=generated_at_utc,
        executor_software_identity=executor_software_identity,
        instrument_registry_sha256=preflight.instrument_registry_sha256,
        capacity_evidence_sha256=preflight.capacity_evidence_sha256,
    )


def verify_funding_repair_execution(
    execution_path: Path,
    repair_plan_path: Path,
    coverage_audit_path: Path,
    original_job_root: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    store_root: Path,
    repair_staging_root: Path,
) -> VerifiedFundingRepairExecution:
    """Rebuild execution evidence from the verified plan and funding Landing jobs."""

    resolved_execution, stored = _object(execution_path, name="funding repair execution")
    if not verify_evidence(resolved_execution):
        raise FundingAcquisitionError("funding repair execution receipt does not verify")
    embedded_content_sha = stored.get("content_sha256")
    hash_input = dict(stored)
    hash_input.pop("content_sha256", None)
    if (
        stored.get("contract") != FUNDING_REPAIR_EXECUTION_CONTRACT
        or stored.get("status") not in ("passed", "blocked")
        or not isinstance(embedded_content_sha, str)
        or embedded_content_sha != canonical_sha256(hash_input)
    ):
        raise FundingAcquisitionError(
            "funding repair execution identity or content hash is invalid"
        )
    verified_plan = verify_funding_repair_plan(
        repair_plan_path,
        coverage_audit_path,
        original_job_root,
        instrument_registry_path,
        capacity_evidence_path,
        store_root,
    )
    raw_results = stored.get("tasks")
    if not isinstance(raw_results, list) or len(raw_results) != verified_plan.task_count:
        raise FundingAcquisitionError("funding repair execution task inventory is invalid")
    staging_root = repair_staging_root.resolve()
    completed_jobs: list[CompletedFundingJob] = []
    for sequence, raw_result in enumerate(raw_results):
        if not isinstance(raw_result, dict) or raw_result.get("sequence") != sequence:
            raise FundingAcquisitionError("funding repair execution sequence is invalid")
        directory = raw_result.get("job_directory")
        if (
            not isinstance(directory, str)
            or not directory
            or Path(directory).name != directory
            or "/" in directory
            or "\\" in directory
        ):
            raise FundingAcquisitionError("funding repair execution job identity is unsafe")
        job_root = (staging_root / ".funding-landing" / directory).resolve()
        if not job_root.is_relative_to(staging_root):
            raise FundingAcquisitionError("funding repair execution job escapes staging root")
        completed_jobs.append(verify_completed_funding_job(job_root))
    executor_identity = stored.get("executor_software_identity")
    generated_at = stored.get("generated_at_utc")
    if not isinstance(executor_identity, str) or not isinstance(generated_at, str):
        raise FundingAcquisitionError("funding repair execution identities are invalid")
    recomputed = build_funding_repair_execution_evidence(
        verified_plan,
        tuple(completed_jobs),
        generated_at_utc=generated_at,
        executor_software_identity=executor_identity,
        instrument_registry_sha256=sha256_file(Path(instrument_registry_path).resolve()),
        capacity_evidence_sha256=sha256_file(Path(capacity_evidence_path).resolve()),
    )
    if recomputed.payload != stored:
        raise FundingAcquisitionError(
            "funding repair execution no longer matches verified plan and Landing inputs"
        )
    return VerifiedFundingRepairExecution(
        path=resolved_execution,
        artifact_sha256=sha256_file(resolved_execution),
        payload=stored,
        passed=recomputed.passed,
        completed_jobs=tuple(completed_jobs),
        verified_plan=verified_plan,
    )
