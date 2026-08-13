"""Deterministic, no-market-mutation repair planning from blocked coverage evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, cast

from grid_contracts.canonical import canonical_sha256, sha256_file

from grid_data.evidence import verify_evidence
from grid_data.history_acquisition import HistoryAcquisitionError
from grid_data.history_coverage_audit import (
    COVERAGE_AUDIT_CONTRACT,
    build_completed_history_coverage_audit,
)
from grid_data.history_publication import SOFTWARE_IDENTITY_RE
from grid_data.history_request import HISTORY_REQUEST_CONTRACT

REPAIR_PLAN_CONTRACT: Final = "grid.bybit-1m-gap-repair-plan/v1"
MAX_REPAIR_TASKS: Final = 1_000
MAX_REPAIR_HTTP_REQUESTS: Final = 100_000
MINUTE_MS: Final = 60_000


@dataclass(frozen=True, slots=True)
class RepairPlan:
    payload: dict[str, object]
    task_count: int
    planned_max_http_requests: int


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
        raise HistoryAcquisitionError(f"repair evidence {key} must be {qualifier} integer")
    return value


def _object_value(parent: dict[str, object], key: str) -> dict[str, object]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise HistoryAcquisitionError(f"repair evidence {key} must be an object")
    return cast(dict[str, object], value)


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


def _assert_only_repairable_gaps(audit: dict[str, object]) -> int:
    if audit.get("contract") != COVERAGE_AUDIT_CONTRACT or audit.get("status") != "blocked":
        raise HistoryAcquisitionError("repair planning requires a blocked v1 coverage audit")
    quality = _object_value(audit, "quality")
    missing = _integer(quality, "missing_minute_count", positive=True)
    expected_zero = (
        "conflicting_key_count",
        "duplicate_key_count",
        "lifecycle_failure_count",
        "unexpected_timestamp_count",
        "unrequested_row_count",
    )
    if quality.get("canonical_source_table_equal") is not True or any(
        _integer(quality, name) != 0 for name in expected_zero
    ):
        raise HistoryAcquisitionError(
            "repair planning supports missing minutes only; other audit blockers remain"
        )
    reason_policy = _object_value(audit, "reason_policy")
    if (
        reason_policy.get("accepted_reason_codes") != []
        or reason_policy.get("unknown_reason_count") != 0
        or reason_policy.get("unaccepted_reason_codes") != ["rest_returned_no_data"]
        or reason_policy.get("observed_reason_counts") != {"rest_returned_no_data": missing}
    ):
        raise HistoryAcquisitionError("blocked audit reason policy is not repair-plan compatible")
    return missing


def _request_payload(
    *,
    job_id: str,
    kind: str,
    symbol: str,
    start_ms: int,
    end_ms: int,
    page_limit: int,
    workers: int,
    target_rps: int,
    max_attempts: int,
) -> tuple[dict[str, object], int]:
    minute_count = ((end_ms - start_ms) // MINUTE_MS) + 1
    page_count = (minute_count + page_limit - 1) // page_limit
    max_http_requests = page_count * max_attempts
    request: dict[str, object] = {
        "contract": HISTORY_REQUEST_CONTRACT,
        "job_id": job_id,
        "kind": kind,
        "max_attempts": max_attempts,
        "max_http_requests": max_http_requests,
        "page_limit": page_limit,
        "series": [{"end_ms": end_ms, "start_ms": start_ms, "symbol": symbol}],
        "target_rps": target_rps,
        "workers": workers,
    }
    return request, page_count


def build_gap_repair_plan(
    coverage_audit_path: Path,
    job_root: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    store_root: Path,
    *,
    generated_at_utc: str,
    planner_software_identity: str,
) -> RepairPlan:
    """Recompute a blocked audit and produce bounded standard requests for each exact gap."""

    if not SOFTWARE_IDENTITY_RE.fullmatch(planner_software_identity):
        raise HistoryAcquisitionError(
            "planner_software_identity must be git:<40-character-lowercase-commit-sha>"
        )
    audit_path, stored_audit = _object(coverage_audit_path, name="coverage audit")
    if not verify_evidence(audit_path):
        raise HistoryAcquisitionError("coverage audit receipt does not verify")
    publisher_identity = _object_value(stored_audit, "bindings").get("publisher_software_identity")
    audit_identity = stored_audit.get("audit_software_identity")
    audit_generated_at = stored_audit.get("generated_at_utc")
    if not all(
        isinstance(value, str) for value in (publisher_identity, audit_identity, audit_generated_at)
    ):
        raise HistoryAcquisitionError("coverage audit identities are invalid")
    recomputed = build_completed_history_coverage_audit(
        job_root,
        instrument_registry_path,
        capacity_evidence_path,
        store_root,
        publisher_software_identity=cast(str, publisher_identity),
        audit_software_identity=cast(str, audit_identity),
        generated_at_utc=cast(str, audit_generated_at),
    )
    if recomputed.payload != stored_audit:
        raise HistoryAcquisitionError("coverage audit no longer matches verified runtime inputs")
    missing_minutes = _assert_only_repairable_gaps(stored_audit)
    if not 1 <= len(recomputed.gap_ranges) <= MAX_REPAIR_TASKS:
        raise HistoryAcquisitionError(
            f"repair gap count must be in [1, {MAX_REPAIR_TASKS}] for one bounded plan"
        )

    history_plan_path = Path(job_root).resolve() / "plan.json"
    _history_plan_path, history_plan = _object(history_plan_path, name="history plan")
    raw_spec = _object_value(history_plan, "spec")
    raw_series = raw_spec.get("series")
    if not isinstance(raw_series, list) or not raw_series or not isinstance(raw_series[0], dict):
        raise HistoryAcquisitionError("history plan series inventory is invalid")
    kind = raw_series[0].get("kind")
    if kind not in ("trade", "mark"):
        raise HistoryAcquisitionError("history plan kind is invalid")
    page_limit = _integer(raw_spec, "page_limit", positive=True)
    workers = _integer(raw_spec, "workers", positive=True)
    target_rps = _integer(raw_spec, "target_rps", positive=True)
    max_attempts = _integer(raw_spec, "max_attempts", positive=True)
    series_by_id = {
        cast(int, item["instrument_id"]): cast(str, item["symbol"])
        for item in cast(list[dict[str, object]], raw_series)
    }
    audit_sha = sha256_file(audit_path)
    dataset_id = cast(str, stored_audit["dataset_id"])
    tasks: list[dict[str, object]] = []
    total_requests = 0
    total_minutes = 0
    for sequence, gap in enumerate(recomputed.gap_ranges):
        instrument_id = _integer(gap, "instrument_id", positive=True)
        start_ms = _integer(gap, "start_ms")
        end_ms = _integer(gap, "end_ms")
        minute_count = _integer(gap, "minute_count", positive=True)
        symbol = series_by_id.get(instrument_id)
        if symbol is None:
            raise HistoryAcquisitionError("gap instrument is absent from original history plan")
        job_id = f"repair-{dataset_id[:32]}-{sequence:04d}-{audit_sha[:8]}"
        request, page_count = _request_payload(
            job_id=job_id,
            kind=kind,
            symbol=symbol,
            start_ms=start_ms,
            end_ms=end_ms,
            page_limit=page_limit,
            workers=workers,
            target_rps=target_rps,
            max_attempts=max_attempts,
        )
        tasks.append(
            {
                "end_ms": end_ms,
                "instrument_id": instrument_id,
                "minute_count": minute_count,
                "page_count": page_count,
                "request": request,
                "request_sha256": canonical_sha256(request),
                "sequence": sequence,
                "start_ms": start_ms,
                "symbol": symbol,
            }
        )
        total_requests += page_count * max_attempts
        total_minutes += minute_count
    if total_minutes != missing_minutes:
        raise HistoryAcquisitionError("repair tasks do not account for every missing minute")
    if total_requests > MAX_REPAIR_HTTP_REQUESTS:
        raise HistoryAcquisitionError(
            f"repair plan exceeds {MAX_REPAIR_HTTP_REQUESTS} bounded HTTP attempts"
        )

    payload: dict[str, object] = {
        "bindings": {
            "canonical_manifest_sha256": _object_value(stored_audit, "bindings")[
                "canonical_manifest_sha256"
            ],
            "coverage_audit_artifact_sha256": audit_sha,
            "coverage_audit_content_sha256": stored_audit["content_sha256"],
            "history_manifest_sha256": _object_value(stored_audit, "bindings")[
                "history_manifest_sha256"
            ],
        },
        "contract": REPAIR_PLAN_CONTRACT,
        "dataset_id": dataset_id,
        "generated_at_utc": _generated_at(generated_at_utc),
        "limits": {
            "max_repair_http_requests": MAX_REPAIR_HTTP_REQUESTS,
            "max_repair_tasks": MAX_REPAIR_TASKS,
            "planned_max_http_requests": total_requests,
            "task_count": len(tasks),
            "total_missing_minutes": total_minutes,
        },
        "mutation_policy": {
            "canonical_dataset_mutated": False,
            "market_requests_executed": False,
            "repair_requests_embedded_only": True,
        },
        "planner_software_identity": planner_software_identity,
        "status": "planned",
        "tasks": tasks,
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return RepairPlan(
        payload=payload,
        task_count=len(tasks),
        planned_max_http_requests=total_requests,
    )
