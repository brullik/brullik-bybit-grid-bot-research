"""Fail-closed discovery planning for isolated funding chronology gaps."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Final, cast

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.compute as pc  # type: ignore[import-untyped]
from grid_contracts.canonical import canonical_sha256, sha256_file

from grid_data.evidence import verify_evidence
from grid_data.funding_acquisition import FundingAcquisitionError, FundingSeries
from grid_data.funding_coverage_audit import (
    FUNDING_COVERAGE_AUDIT_CONTRACT,
    build_completed_funding_coverage_audit,
)
from grid_data.funding_publication import (
    SOFTWARE_IDENTITY_RE,
    load_verified_funding_publication_input,
)
from grid_data.funding_request import FUNDING_REQUEST_CONTRACT

FUNDING_REPAIR_PLAN_CONTRACT: Final = "grid.bybit-funding-repair-plan/v1"
MAX_REPAIR_TASKS: Final = 1_000
MAX_REPAIR_CANDIDATES: Final = 1_000
MAX_REPAIR_HTTP_REQUESTS: Final = 100_000
MAX_FUNDING_PAGE_LIMIT: Final = 200
MINUTE_MS: Final = 60_000


@dataclass(frozen=True, slots=True)
class FundingRepairPlan:
    payload: dict[str, object]
    task_count: int
    candidate_count: int
    planned_max_http_requests: int


@dataclass(frozen=True, slots=True)
class VerifiedFundingRepairPlan:
    path: Path
    artifact_sha256: str
    payload: dict[str, object]
    task_count: int
    candidate_count: int
    planned_max_http_requests: int


def _object(path: Path, *, name: str) -> tuple[Path, dict[str, object]]:
    resolved = path.resolve()
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FundingAcquisitionError(f"{name} cannot be loaded") from error
    if not isinstance(raw, dict):
        raise FundingAcquisitionError(f"{name} must be an object")
    return resolved, cast(dict[str, object], raw)


def _object_value(parent: dict[str, object], key: str) -> dict[str, object]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise FundingAcquisitionError(f"funding repair evidence {key} must be an object")
    return cast(dict[str, object], value)


def _integer(parent: dict[str, object], key: str, *, positive: bool = False) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise FundingAcquisitionError(
            f"funding repair evidence {key} must be a {qualifier} integer"
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


def _assert_only_discoverable_chronology(audit: dict[str, object]) -> int:
    if audit.get("contract") != FUNDING_COVERAGE_AUDIT_CONTRACT or audit.get("status") != "blocked":
        raise FundingAcquisitionError(
            "funding repair planning requires a blocked v1 funding coverage audit"
        )
    quality = _object_value(audit, "quality")
    interval_changes = _integer(quality, "interval_change_count", positive=True)
    expected_zero = (
        "conflicting_key_count",
        "duplicate_key_count",
        "empty_range_page_count",
        "internal_interval_mismatch_count",
        "lifecycle_failure_count",
        "predecessor_interval_mismatch_count",
        "unexpected_timestamp_count",
        "unrequested_row_count",
    )
    if quality.get("canonical_source_table_equal") is not True or any(
        _integer(quality, name) != 0 for name in expected_zero
    ):
        raise FundingAcquisitionError(
            "funding repair planning supports isolated chronology discovery only; "
            "other audit blockers remain"
        )
    reason_policy = _object_value(audit, "reason_policy")
    if (
        reason_policy.get("accepted_reason_codes") != []
        or reason_policy.get("unknown_reason_count") != 0
        or reason_policy.get("unaccepted_reason_codes") != ["unexplained_interval_change"]
        or reason_policy.get("observed_reason_counts")
        != {"unexplained_interval_change": interval_changes}
    ):
        raise FundingAcquisitionError(
            "blocked funding audit reason policy is not repair-discovery compatible"
        )
    anomaly_evidence = _object_value(audit, "chronology_anomaly_evidence")
    if _integer(anomaly_evidence, "anomaly_count") != interval_changes:
        raise FundingAcquisitionError(
            "funding anomaly inventory does not contain only interval changes"
        )
    return interval_changes


def _series_and_settings(
    plan_path: Path,
) -> tuple[tuple[FundingSeries, ...], dict[str, int]]:
    _path, plan = _object(plan_path, name="funding history plan")
    spec = _object_value(plan, "spec")
    raw_series = spec.get("series")
    if (
        not isinstance(raw_series, list)
        or not raw_series
        or any(not isinstance(item, dict) for item in raw_series)
    ):
        raise FundingAcquisitionError("funding history plan series inventory is invalid")
    try:
        series = tuple(
            FundingSeries(**cast(dict[str, object], item))  # type: ignore[arg-type]
            for item in raw_series
        )
    except (TypeError, FundingAcquisitionError) as error:
        raise FundingAcquisitionError("funding history plan series inventory is invalid") from error
    settings = {
        name: _integer(spec, name, positive=True)
        for name in (
            "page_span_minutes",
            "page_limit",
            "workers",
            "target_rps",
            "max_attempts",
        )
    }
    return series, settings


def _request_payload(
    *,
    job_id: str,
    symbol: str,
    start_ms: int,
    end_ms: int,
    candidate_count: int,
    settings: dict[str, int],
) -> tuple[dict[str, object], int]:
    range_minutes = ((end_ms - start_ms) // MINUTE_MS) + 1
    range_pages = (range_minutes + settings["page_span_minutes"] - 1) // settings[
        "page_span_minutes"
    ]
    page_count = 1 + range_pages
    max_http_requests = page_count * settings["max_attempts"]
    page_limit = max(settings["page_limit"], candidate_count + 1)
    if page_limit > MAX_FUNDING_PAGE_LIMIT:
        raise FundingAcquisitionError(
            "one funding repair candidate range cannot be enumerated below page saturation"
        )
    request: dict[str, object] = {
        "contract": FUNDING_REQUEST_CONTRACT,
        "job_id": job_id,
        "max_attempts": settings["max_attempts"],
        "max_http_requests": max_http_requests,
        "page_limit": page_limit,
        "page_span_minutes": settings["page_span_minutes"],
        "series": [{"end_ms": end_ms, "start_ms": start_ms, "symbol": symbol}],
        "target_rps": settings["target_rps"],
        "workers": settings["workers"],
    }
    return request, page_count


def _candidate_tasks(
    *,
    dataset_id: str,
    audit_sha256: str,
    series: tuple[FundingSeries, ...],
    settings: dict[str, int],
    table: pa.Table,
) -> tuple[list[dict[str, object]], int, int]:
    tasks: list[dict[str, object]] = []
    explained_change_count = 0
    total_http_requests = 0
    for item in series:
        mask = pc.equal(table.column("instrument_id"), item.instrument_id)
        raw_times = cast(
            list[int],
            pc.filter(table.column("funding_time_ms"), mask).to_pylist(),
        )
        raw_intervals = cast(
            list[int],
            pc.filter(table.column("funding_interval_minutes"), mask).to_pylist(),
        )
        pairs = sorted(zip(raw_times, raw_intervals, strict=True))
        times = [entry[0] for entry in pairs]
        intervals = [entry[1] for entry in pairs]
        changed_edges = {
            index
            for index, (left, right) in enumerate(pairwise(intervals), start=1)
            if left != right
        }
        candidate_indexes: list[int] = []
        for index in range(1, len(intervals) - 1):
            baseline = intervals[index - 1]
            observed = intervals[index]
            if (
                baseline == intervals[index + 1]
                and observed > baseline
                and observed % baseline == 0
            ):
                candidate_indexes.append(index)
        explained_edges = {edge for index in candidate_indexes for edge in (index, index + 1)}
        if explained_edges != changed_edges:
            raise FundingAcquisitionError(
                "funding chronology is not a complete set of isolated integer-multiple "
                "cadence sandwiches"
            )
        explained_change_count += len(explained_edges)
        for index in candidate_indexes:
            baseline = intervals[index - 1]
            observed = intervals[index]
            left_settlement = times[index - 1]
            right_settlement = times[index]
            expected = [
                left_settlement + offset * baseline * MINUTE_MS
                for offset in range(1, observed // baseline)
            ]
            if (
                not expected
                or expected[-1] >= right_settlement
                or expected[0] < item.start_ms
                or expected[-1] > item.end_ms
            ):
                raise FundingAcquisitionError(
                    "funding repair candidates escape the original requested range"
                )
            sequence = len(tasks)
            job_id = (
                f"funding-repair-{dataset_id.removeprefix('funding-')[:24]}-"
                f"{sequence:04d}-{audit_sha256[:8]}"
            )
            request, page_count = _request_payload(
                job_id=job_id,
                symbol=item.symbol,
                start_ms=expected[0],
                end_ms=expected[-1],
                candidate_count=len(expected),
                settings=settings,
            )
            task = {
                "candidate_settlement_count": len(expected),
                "candidate_settlement_times_ms": expected,
                "end_ms": expected[-1],
                "expected_interval_minutes": baseline,
                "instrument_id": item.instrument_id,
                "observed_gap_interval_minutes": observed,
                "page_count": page_count,
                "predecessor_settlement_ms": left_settlement,
                "request": request,
                "request_sha256": canonical_sha256(request),
                "sequence": sequence,
                "start_ms": expected[0],
                "symbol": item.symbol,
            }
            tasks.append(task)
            total_http_requests += page_count * settings["max_attempts"]
    return tasks, explained_change_count, total_http_requests


def build_funding_repair_plan(
    coverage_audit_path: Path,
    job_root: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    store_root: Path,
    *,
    generated_at_utc: str,
    planner_software_identity: str,
) -> FundingRepairPlan:
    """Plan bounded source discovery without accepting or repairing cadence anomalies."""

    if not SOFTWARE_IDENTITY_RE.fullmatch(planner_software_identity):
        raise FundingAcquisitionError(
            "planner_software_identity must be git:<40-character-lowercase-commit-sha>"
        )
    audit_path, stored_audit = _object(coverage_audit_path, name="funding coverage audit")
    if not verify_evidence(audit_path):
        raise FundingAcquisitionError("funding coverage audit receipt does not verify")
    bindings = _object_value(stored_audit, "bindings")
    publisher_identity = bindings.get("publisher_software_identity")
    audit_identity = stored_audit.get("audit_software_identity")
    audit_generated_at = stored_audit.get("generated_at_utc")
    if not all(
        isinstance(value, str) for value in (publisher_identity, audit_identity, audit_generated_at)
    ):
        raise FundingAcquisitionError("funding coverage audit identities are invalid")
    recomputed = build_completed_funding_coverage_audit(
        job_root,
        instrument_registry_path,
        capacity_evidence_path,
        store_root,
        publisher_software_identity=cast(str, publisher_identity),
        audit_software_identity=cast(str, audit_identity),
        generated_at_utc=cast(str, audit_generated_at),
    )
    if recomputed.payload != stored_audit:
        raise FundingAcquisitionError(
            "funding coverage audit no longer matches verified runtime inputs"
        )
    interval_change_count = _assert_only_discoverable_chronology(stored_audit)
    verified = load_verified_funding_publication_input(
        job_root,
        instrument_registry_path,
        capacity_evidence_path,
    )
    if verified.dataset_id != stored_audit.get("dataset_id"):
        raise FundingAcquisitionError("funding audit dataset identity does not match Landing")
    series, settings = _series_and_settings(verified.completed.plan_path)
    audit_sha = sha256_file(audit_path)
    tasks, explained_changes, total_requests = _candidate_tasks(
        dataset_id=verified.dataset_id,
        audit_sha256=audit_sha,
        series=series,
        settings=settings,
        table=verified.batch.table,
    )
    candidate_count = sum(
        _integer(task, "candidate_settlement_count", positive=True) for task in tasks
    )
    if explained_changes != interval_change_count:
        raise FundingAcquisitionError(
            "funding repair candidates do not explain every blocked interval transition"
        )
    if not 1 <= len(tasks) <= MAX_REPAIR_TASKS:
        raise FundingAcquisitionError(
            f"funding repair task count must be in [1, {MAX_REPAIR_TASKS}]"
        )
    if not 1 <= candidate_count <= MAX_REPAIR_CANDIDATES:
        raise FundingAcquisitionError(
            f"funding repair candidate count must be in [1, {MAX_REPAIR_CANDIDATES}]"
        )
    if total_requests > MAX_REPAIR_HTTP_REQUESTS:
        raise FundingAcquisitionError(
            f"funding repair plan exceeds {MAX_REPAIR_HTTP_REQUESTS} bounded HTTP attempts"
        )

    anomaly_evidence = _object_value(stored_audit, "chronology_anomaly_evidence")
    payload: dict[str, object] = {
        "bindings": {
            "canonical_manifest_sha256": bindings["canonical_manifest_sha256"],
            "chronology_anomaly_records_sha256": anomaly_evidence["anomaly_records_sha256"],
            "coverage_audit_artifact_sha256": audit_sha,
            "coverage_audit_content_sha256": stored_audit["content_sha256"],
            "funding_manifest_sha256": bindings["funding_manifest_sha256"],
        },
        "contract": FUNDING_REPAIR_PLAN_CONTRACT,
        "dataset_id": verified.dataset_id,
        "generated_at_utc": _generated_at(generated_at_utc),
        "inference_policy": {
            "audit_remains_blocked": True,
            "candidate_requires_exact_source_confirmation": True,
            "current_instrument_interval_used": False,
            "empty_source_windows_supported": False,
            "isolated_integer_multiple_sandwich_required": True,
            "schedule_change_accepted": False,
        },
        "limits": {
            "candidate_settlement_count": candidate_count,
            "explained_interval_change_count": explained_changes,
            "max_repair_candidates": MAX_REPAIR_CANDIDATES,
            "max_repair_http_requests": MAX_REPAIR_HTTP_REQUESTS,
            "max_repair_tasks": MAX_REPAIR_TASKS,
            "planned_max_http_requests": total_requests,
            "task_count": len(tasks),
        },
        "mutation_policy": {
            "canonical_dataset_mutated": False,
            "market_requests_executed": False,
            "repair_candidates_accepted": False,
            "standard_funding_requests_embedded_only": True,
        },
        "planner_software_identity": planner_software_identity,
        "status": "discovery-planned",
        "tasks": tasks,
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return FundingRepairPlan(
        payload=payload,
        task_count=len(tasks),
        candidate_count=candidate_count,
        planned_max_http_requests=total_requests,
    )


def verify_funding_repair_plan(
    repair_plan_path: Path,
    coverage_audit_path: Path,
    job_root: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    store_root: Path,
) -> VerifiedFundingRepairPlan:
    """Recompute one receipt-verified funding discovery plan from bound inputs."""

    plan_path, stored = _object(repair_plan_path, name="funding repair plan")
    if not verify_evidence(plan_path):
        raise FundingAcquisitionError("funding repair plan receipt does not verify")
    embedded_content_sha = stored.get("content_sha256")
    hash_input = dict(stored)
    hash_input.pop("content_sha256", None)
    if (
        stored.get("contract") != FUNDING_REPAIR_PLAN_CONTRACT
        or stored.get("status") != "discovery-planned"
        or not isinstance(embedded_content_sha, str)
        or embedded_content_sha != canonical_sha256(hash_input)
    ):
        raise FundingAcquisitionError("funding repair plan identity or content hash is invalid")
    planner_identity = stored.get("planner_software_identity")
    generated_at = stored.get("generated_at_utc")
    if not isinstance(planner_identity, str) or not isinstance(generated_at, str):
        raise FundingAcquisitionError("funding repair plan identities are invalid")
    recomputed = build_funding_repair_plan(
        coverage_audit_path,
        job_root,
        instrument_registry_path,
        capacity_evidence_path,
        store_root,
        generated_at_utc=generated_at,
        planner_software_identity=planner_identity,
    )
    if recomputed.payload != stored:
        raise FundingAcquisitionError(
            "funding repair plan no longer matches verified runtime inputs"
        )
    return VerifiedFundingRepairPlan(
        path=plan_path,
        artifact_sha256=sha256_file(plan_path),
        payload=stored,
        task_count=recomputed.task_count,
        candidate_count=recomputed.candidate_count,
        planned_max_http_requests=recomputed.planned_max_http_requests,
    )
