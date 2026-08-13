"""Receipt-bound execution of a verified bounded one-minute gap repair plan."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, cast

from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_market_store import CapacityBudget, HostSnapshot

from grid_data.evidence import verify_evidence
from grid_data.history_acquisition import (
    CompletedHistoryJob,
    HistoryAcquisitionError,
    HistoryJobPlan,
    KlineClient,
    execute_history_job,
    load_completed_history_batch,
    preflight_history_job,
    verify_completed_history_job,
)
from grid_data.history_publication import SOFTWARE_IDENTITY_RE
from grid_data.history_repair_plan import VerifiedRepairPlan, verify_gap_repair_plan
from grid_data.history_request import resolve_history_request_payload

REPAIR_EXECUTION_CONTRACT: Final = "grid.bybit-1m-gap-repair-execution/v1"


@dataclass(frozen=True, slots=True)
class RepairExecutionPreflight:
    verified_plan: VerifiedRepairPlan
    task_plans: tuple[HistoryJobPlan, ...]
    executor_software_identity: str
    instrument_registry_sha256: str
    capacity_evidence_sha256: str
    required_free_bytes: int
    planned_peak_memory_bytes: int
    existing_complete_count: int


@dataclass(frozen=True, slots=True)
class RepairExecutionResult:
    payload: dict[str, object]
    passed: bool
    completed_jobs: tuple[CompletedHistoryJob, ...]


@dataclass(frozen=True, slots=True)
class VerifiedRepairExecution:
    path: Path
    artifact_sha256: str
    payload: dict[str, object]
    passed: bool
    completed_jobs: tuple[CompletedHistoryJob, ...]
    verified_plan: VerifiedRepairPlan


def _object(path: Path, *, name: str) -> tuple[Path, dict[str, object]]:
    resolved = path.resolve()
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryAcquisitionError(f"{name} cannot be loaded") from error
    if not isinstance(raw, dict):
        raise HistoryAcquisitionError(f"{name} must be an object")
    return resolved, cast(dict[str, object], raw)


def _integer(parent: dict[str, object], key: str, *, positive: bool = False) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise HistoryAcquisitionError(f"repair execution {key} must be {qualifier} integer")
    return value


def _generated_at(value: str) -> str:
    if not value.endswith("Z"):
        raise HistoryAcquisitionError("generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise HistoryAcquisitionError("generated_at_utc is invalid") from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise HistoryAcquisitionError("generated_at_utc must be UTC")
    return value


def _raw_tasks(plan: VerifiedRepairPlan) -> list[dict[str, object]]:
    value = plan.payload.get("tasks")
    if not isinstance(value, list) or len(value) != plan.task_count:
        raise HistoryAcquisitionError("gap repair plan task inventory is invalid")
    if any(not isinstance(item, dict) for item in value):
        raise HistoryAcquisitionError("gap repair plan tasks must be objects")
    return cast(list[dict[str, object]], value)


def preflight_gap_repair_execution(
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
) -> RepairExecutionPreflight:
    """Preflight every embedded request and the aggregate staging bound without mutation."""

    if not SOFTWARE_IDENTITY_RE.fullmatch(executor_software_identity):
        raise HistoryAcquisitionError(
            "executor_software_identity must be git:<40-character-lowercase-commit-sha>"
        )
    verified = verify_gap_repair_plan(
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
            raise HistoryAcquisitionError("gap repair task sequence is not canonical")
        request = task.get("request")
        if not isinstance(request, dict):
            raise HistoryAcquisitionError("gap repair task has no embedded request")
        resolved = resolve_history_request_payload(
            cast(dict[str, object], request),
            source_path=verified.path,
            instrument_registry_path=instrument_registry_path,
            capacity_evidence_path=capacity_evidence_path,
        )
        if resolved.request_sha256 != task.get("request_sha256"):
            raise HistoryAcquisitionError("embedded repair request hash does not verify")
        resolved_requests.append(resolved)

    active_values = {item.budget.active_and_building_bytes for item in resolved_requests}
    reserve_values = {item.budget.operating_reserve_bytes for item in resolved_requests}
    if len(active_values) != 1 or len(reserve_values) != 1:
        raise HistoryAcquisitionError("repair requests do not share one capacity policy")
    aggregate_budget = CapacityBudget(
        active_and_building_bytes=next(iter(active_values)),
        rest_staging_bytes=sum(item.budget.rest_staging_bytes for item in resolved_requests),
        operating_reserve_bytes=next(iter(reserve_values)),
    )
    task_plans = tuple(
        preflight_history_job(
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
        raise HistoryAcquisitionError("repair tasks resolve to duplicate Landing identities")
    registry_hashes = {item.registry.artifact_sha256 for item in resolved_requests}
    capacity_hashes = {item.capacity_artifact_sha256 for item in resolved_requests}
    if len(registry_hashes) != 1 or len(capacity_hashes) != 1:
        raise HistoryAcquisitionError("repair tasks do not share one evidence identity")
    return RepairExecutionPreflight(
        verified_plan=verified,
        task_plans=task_plans,
        executor_software_identity=executor_software_identity,
        instrument_registry_sha256=next(iter(registry_hashes)),
        capacity_evidence_sha256=next(iter(capacity_hashes)),
        required_free_bytes=max(item.required_free_bytes for item in task_plans),
        planned_peak_memory_bytes=max(item.planned_peak_memory_bytes for item in task_plans),
        existing_complete_count=sum(item.existing_complete for item in task_plans),
    )


def _load_manifest(completed: CompletedHistoryJob) -> dict[str, object]:
    _path, manifest = _object(completed.manifest_path, name="repair history manifest")
    return manifest


def _task_result(
    task: dict[str, object],
    completed: CompletedHistoryJob,
    *,
    instrument_registry_sha256: str,
    capacity_evidence_sha256: str,
) -> tuple[dict[str, object], bool]:
    sequence = _integer(task, "sequence")
    instrument_id = _integer(task, "instrument_id", positive=True)
    start_ms = _integer(task, "start_ms")
    end_ms = _integer(task, "end_ms")
    expected_minutes = _integer(task, "minute_count", positive=True)
    request = task.get("request")
    if not isinstance(request, dict):
        raise HistoryAcquisitionError("repair task has no embedded request")
    history_plan = _object(completed.plan_path, name="repair history plan")[1]
    raw_spec = history_plan.get("spec")
    if not isinstance(raw_spec, dict):
        raise HistoryAcquisitionError("repair history plan has no spec")
    expected_series = [
        {
            "category": "linear",
            "end_ms": end_ms,
            "instrument_id": instrument_id,
            "kind": request.get("kind"),
            "start_ms": start_ms,
            "symbol": task.get("symbol"),
        }
    ]
    expected_spec_facts = {
        "capacity_evidence_sha256": capacity_evidence_sha256,
        "instrument_evidence_sha256": instrument_registry_sha256,
        "job_id": request.get("job_id"),
        "max_attempts": request.get("max_attempts"),
        "max_http_requests": request.get("max_http_requests"),
        "page_limit": request.get("page_limit"),
        "request_sha256": task.get("request_sha256"),
        "series": expected_series,
        "target_rps": request.get("target_rps"),
        "workers": request.get("workers"),
    }
    if any(raw_spec.get(key) != value for key, value in expected_spec_facts.items()):
        raise HistoryAcquisitionError("repair Landing plan does not match its embedded request")
    manifest = _load_manifest(completed)
    request_bound = manifest.get("request_bound")
    if not isinstance(request_bound, dict):
        raise HistoryAcquisitionError("repair history manifest has no request bound")
    actual_requests = _integer(cast(dict[str, object], request_bound), "actual_http_requests")
    observed_times: list[int] = []
    if completed.row_count:
        batch = load_completed_history_batch(completed.job_root)
        identifiers = batch.table.column("instrument_id").to_pylist()
        if any(value != instrument_id for value in identifiers):
            raise HistoryAcquisitionError("repair Landing contains an unexpected instrument")
        observed_times = cast(list[int], batch.table.column("open_time_ms").to_pylist())
    expected_times = list(range(start_ms, end_ms + 1, 60_000))
    exact_coverage = observed_times == expected_times
    missing_minutes = len(set(expected_times) - set(observed_times))
    if len(observed_times) != completed.row_count or len(set(observed_times)) != len(
        observed_times
    ):
        raise HistoryAcquisitionError("repair Landing timestamp inventory is inconsistent")
    result: dict[str, object] = {
        "actual_http_requests": actual_requests,
        "end_ms": end_ms,
        "exact_gap_coverage": exact_coverage,
        "history_manifest_sha256": completed.manifest_sha256,
        "history_plan_sha256": sha256_file(completed.plan_path),
        "instrument_id": instrument_id,
        "job_directory": completed.job_root.name,
        "minute_count": expected_minutes,
        "missing_minute_count": missing_minutes,
        "observed_row_count": completed.row_count,
        "page_count": completed.page_count,
        "request_sha256": task.get("request_sha256"),
        "sequence": sequence,
        "start_ms": start_ms,
        "status": "passed" if exact_coverage else "blocked",
        "symbol": task.get("symbol"),
    }
    return result, exact_coverage


def build_gap_repair_execution_evidence(
    verified_plan: VerifiedRepairPlan,
    completed_jobs: tuple[CompletedHistoryJob, ...],
    *,
    generated_at_utc: str,
    executor_software_identity: str,
    instrument_registry_sha256: str,
    capacity_evidence_sha256: str,
) -> RepairExecutionResult:
    """Build bounded value-free evidence for completed standard Landing repair jobs."""

    if not SOFTWARE_IDENTITY_RE.fullmatch(executor_software_identity):
        raise HistoryAcquisitionError(
            "executor_software_identity must be git:<40-character-lowercase-commit-sha>"
        )
    tasks = _raw_tasks(verified_plan)
    if len(completed_jobs) != len(tasks):
        raise HistoryAcquisitionError("repair execution does not contain every planned task")
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
    observed_rows = sum(cast(int, item["observed_row_count"]) for item in task_results)
    missing_minutes = sum(cast(int, item["missing_minute_count"]) for item in task_results)
    passed = all(task_passes) and missing_minutes == 0
    bindings = cast(dict[str, object], verified_plan.payload["bindings"])
    limits = cast(dict[str, object], verified_plan.payload["limits"])
    planned_requests = _integer(limits, "planned_max_http_requests", positive=True)
    planned_minutes = _integer(limits, "total_missing_minutes", positive=True)
    if actual_requests > planned_requests:
        raise HistoryAcquisitionError("repair execution exceeds its planned request bound")
    if observed_rows + missing_minutes != planned_minutes:
        raise HistoryAcquisitionError("repair execution does not account for every planned minute")
    payload: dict[str, object] = {
        "bindings": {
            "canonical_parent_manifest_sha256": bindings["canonical_manifest_sha256"],
            "capacity_evidence_sha256": capacity_evidence_sha256,
            "coverage_audit_artifact_sha256": bindings["coverage_audit_artifact_sha256"],
            "coverage_audit_content_sha256": bindings["coverage_audit_content_sha256"],
            "original_history_manifest_sha256": bindings["history_manifest_sha256"],
            "instrument_registry_sha256": instrument_registry_sha256,
            "repair_plan_artifact_sha256": verified_plan.artifact_sha256,
            "repair_plan_content_sha256": verified_plan.payload["content_sha256"],
        },
        "contract": REPAIR_EXECUTION_CONTRACT,
        "dataset_id": verified_plan.payload["dataset_id"],
        "executor_software_identity": executor_software_identity,
        "generated_at_utc": _generated_at(generated_at_utc),
        "limits": {
            "actual_http_requests": actual_requests,
            "missing_minute_count": missing_minutes,
            "observed_row_count": observed_rows,
            "planned_max_http_requests": planned_requests,
            "task_count": len(task_results),
            "total_missing_minutes": planned_minutes,
        },
        "limitations": [
            "Execution evidence covers only gaps in the bound repair plan.",
            "A passed execution does not mutate or supersede the committed parent dataset.",
            "Replacement publication and a post-publication coverage proof remain separate.",
        ],
        "mutation_policy": {
            "market_requests_executed": True,
            "parent_dataset_mutated": False,
            "replacement_dataset_published": False,
        },
        "status": "passed" if passed else "blocked",
        "storage_policy": {
            "account_data_included": False,
            "market_values_included": False,
            "runtime_paths_included": False,
        },
        "tasks": task_results,
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return RepairExecutionResult(
        payload=payload,
        passed=passed,
        completed_jobs=completed_jobs,
    )


def execute_gap_repair(
    preflight: RepairExecutionPreflight,
    client_factory: Callable[[], KlineClient],
    snapshot_provider: Callable[[], HostSnapshot],
    *,
    generated_at_utc: str,
    executor_software_identity: str,
    now_ms: Callable[[], int],
) -> RepairExecutionResult:
    """Execute each standard job sequentially and preserve receipt-based resume semantics."""

    if not SOFTWARE_IDENTITY_RE.fullmatch(executor_software_identity):
        raise HistoryAcquisitionError(
            "executor_software_identity must be git:<40-character-lowercase-commit-sha>"
        )
    if executor_software_identity != preflight.executor_software_identity:
        raise HistoryAcquisitionError("executor software identity changed after preflight")
    _generated_at(generated_at_utc)
    completed = tuple(
        execute_history_job(
            task_plan,
            client_factory,
            snapshot_provider,
            now_ms=now_ms,
        )
        for task_plan in preflight.task_plans
    )
    return build_gap_repair_execution_evidence(
        preflight.verified_plan,
        completed,
        generated_at_utc=generated_at_utc,
        executor_software_identity=executor_software_identity,
        instrument_registry_sha256=preflight.instrument_registry_sha256,
        capacity_evidence_sha256=preflight.capacity_evidence_sha256,
    )


def verify_gap_repair_execution(
    execution_path: Path,
    repair_plan_path: Path,
    coverage_audit_path: Path,
    original_job_root: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    store_root: Path,
    repair_staging_root: Path,
) -> VerifiedRepairExecution:
    """Rebuild execution evidence from verified plan inputs and completed Landing jobs."""

    resolved_execution, stored = _object(execution_path, name="gap repair execution")
    if not verify_evidence(resolved_execution):
        raise HistoryAcquisitionError("gap repair execution receipt does not verify")
    embedded_content_sha = stored.get("content_sha256")
    hash_input = dict(stored)
    hash_input.pop("content_sha256", None)
    if (
        stored.get("contract") != REPAIR_EXECUTION_CONTRACT
        or stored.get("status") not in ("passed", "blocked")
        or not isinstance(embedded_content_sha, str)
        or embedded_content_sha != canonical_sha256(hash_input)
    ):
        raise HistoryAcquisitionError("gap repair execution identity or content hash is invalid")
    verified_plan = verify_gap_repair_plan(
        repair_plan_path,
        coverage_audit_path,
        original_job_root,
        instrument_registry_path,
        capacity_evidence_path,
        store_root,
    )
    raw_results = stored.get("tasks")
    if not isinstance(raw_results, list) or len(raw_results) != verified_plan.task_count:
        raise HistoryAcquisitionError("gap repair execution task inventory is invalid")
    staging_root = repair_staging_root.resolve()
    completed_jobs: list[CompletedHistoryJob] = []
    for sequence, raw_result in enumerate(raw_results):
        if not isinstance(raw_result, dict) or raw_result.get("sequence") != sequence:
            raise HistoryAcquisitionError("gap repair execution sequence is invalid")
        directory = raw_result.get("job_directory")
        if (
            not isinstance(directory, str)
            or not directory
            or Path(directory).name != directory
            or "/" in directory
            or "\\" in directory
        ):
            raise HistoryAcquisitionError("gap repair execution job identity is unsafe")
        job_root = (staging_root / ".landing" / directory).resolve()
        if not job_root.is_relative_to(staging_root):
            raise HistoryAcquisitionError("gap repair execution job escapes staging root")
        completed_jobs.append(verify_completed_history_job(job_root))
    executor_identity = stored.get("executor_software_identity")
    generated_at = stored.get("generated_at_utc")
    if not isinstance(executor_identity, str) or not isinstance(generated_at, str):
        raise HistoryAcquisitionError("gap repair execution identities are invalid")
    recomputed = build_gap_repair_execution_evidence(
        verified_plan,
        tuple(completed_jobs),
        generated_at_utc=generated_at,
        executor_software_identity=executor_identity,
        instrument_registry_sha256=sha256_file(Path(instrument_registry_path).resolve()),
        capacity_evidence_sha256=sha256_file(Path(capacity_evidence_path).resolve()),
    )
    if recomputed.payload != stored:
        raise HistoryAcquisitionError(
            "gap repair execution no longer matches verified plan and Landing inputs"
        )
    return VerifiedRepairExecution(
        path=resolved_execution,
        artifact_sha256=sha256_file(resolved_execution),
        payload=stored,
        passed=recomputed.passed,
        completed_jobs=tuple(completed_jobs),
        verified_plan=verified_plan,
    )
