"""GitHub-safe evidence for a verified canonical history campaign publication."""

from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Final, cast

from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file

from grid_data.history_acquisition import (
    CANONICAL_ADMISSION_POLICY,
    CANONICAL_ADMISSION_REASONS,
)
from grid_data.history_campaign_publication import (
    CAMPAIGN_PUBLICATION_MANIFEST_CONTRACT,
    CAMPAIGN_PUBLICATION_PLAN_CONTRACT,
    HistoryCampaignPublicationError,
    verify_completed_history_campaign_publication,
)

CAMPAIGN_PUBLICATION_EVIDENCE_CONTRACT: Final = "grid.phase2-history-campaign-publication/v1"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
_KIND_ORDER: Final = ("trade", "mark", "funding")


def _object(path: Path) -> dict[str, object]:
    try:
        data = path.read_bytes()
        raw = json.loads(data)
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryCampaignPublicationError(
            f"verified publication artifact cannot be loaded: {path.name}"
        ) from error
    if not isinstance(raw, dict) or canonical_json_bytes(raw) != data:
        raise HistoryCampaignPublicationError(
            f"verified publication artifact is not canonical JSON: {path.name}"
        )
    return cast(dict[str, object], raw)


def _integer(parent: dict[str, object], key: str, *, minimum: int = 0) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise HistoryCampaignPublicationError(f"verified publication field is invalid: {key}")
    return value


def _sha(parent: dict[str, object], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise HistoryCampaignPublicationError(f"verified publication SHA-256 is invalid: {key}")
    return value


def _generated_at(value: str) -> None:
    if not value.endswith("Z"):
        raise HistoryCampaignPublicationError("evidence timestamp must use UTC Z notation")
    try:
        generated_at = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise HistoryCampaignPublicationError("evidence timestamp is invalid") from error
    offset = generated_at.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise HistoryCampaignPublicationError("evidence timestamp must be UTC")


def build_history_campaign_publication_evidence(
    publication_root: Path,
    source_campaign_root: Path,
    *,
    generated_at_utc: str,
    software_identity: str,
) -> dict[str, object]:
    """Re-verify publication lineage and project only aggregate, value-free facts."""

    if SOFTWARE_IDENTITY_RE.fullmatch(software_identity) is None:
        raise HistoryCampaignPublicationError(
            "publication evidence software identity must be git:<40 hex>"
        )
    _generated_at(generated_at_utc)
    verification_started_ns = time.perf_counter_ns()
    completed = verify_completed_history_campaign_publication(
        publication_root,
        source_campaign_root,
    )
    verification_elapsed_ms = max(
        1,
        (time.perf_counter_ns() - verification_started_ns + 999_999) // 1_000_000,
    )
    publication_plan = _object(completed.plan_path)
    publication_manifest = _object(completed.manifest_path)
    source_plan = _object(source_campaign_root.resolve() / "plan.json")
    if publication_plan.get("contract") != CAMPAIGN_PUBLICATION_PLAN_CONTRACT:
        raise HistoryCampaignPublicationError("evidence requires the v1 publication plan")
    if publication_manifest.get("contract") != CAMPAIGN_PUBLICATION_MANIFEST_CONTRACT:
        raise HistoryCampaignPublicationError("evidence requires the v1 publication manifest")
    if sha256_file(completed.manifest_path) != completed.manifest_sha256:
        raise HistoryCampaignPublicationError("publication manifest changed after verification")
    publication_plan_sha = canonical_sha256(publication_plan)
    if publication_manifest.get("publication_plan_sha256") != publication_plan_sha:
        raise HistoryCampaignPublicationError("publication plan changed after verification")
    source_plan_sha = canonical_sha256(source_plan)
    if publication_plan.get("source_campaign_plan_sha256") != source_plan_sha:
        raise HistoryCampaignPublicationError("source campaign plan changed after verification")

    raw_jobs = publication_plan.get("jobs")
    raw_datasets = publication_manifest.get("datasets")
    source_request = source_plan.get("campaign_request")
    source_jobs = source_plan.get("jobs")
    source_policy = source_plan.get("source_policy")
    if not all(
        isinstance(value, list) for value in (raw_jobs, raw_datasets, source_jobs)
    ) or not isinstance(source_request, dict):
        raise HistoryCampaignPublicationError("publication evidence inputs are incomplete")
    if not isinstance(source_policy, dict) or source_policy.get("tick_rows_requested") is not False:
        raise HistoryCampaignPublicationError("publication evidence requires no-tick source policy")
    publisher_identity = publication_plan.get("publisher_software_identity")
    if (
        not isinstance(publisher_identity, str)
        or SOFTWARE_IDENTITY_RE.fullmatch(publisher_identity) is None
    ):
        raise HistoryCampaignPublicationError("publication publisher identity is invalid")

    by_kind: dict[str, dict[str, int]] = defaultdict(
        lambda: {"dataset_count": 0, "file_count": 0, "parquet_bytes": 0, "row_count": 0}
    )
    required_free_bytes: list[int] = []
    planned_peak_memory_bytes: list[int] = []
    candle_source_rows = 0
    candle_admitted_rows = 0
    canonical_excluded_rows = 0
    canonical_reason_counts = {reason: 0 for reason in CANONICAL_ADMISSION_REASONS}
    for raw_job, raw_dataset in zip(
        cast(list[dict[str, object]], raw_jobs),
        cast(list[dict[str, object]], raw_datasets),
        strict=True,
    ):
        kind = raw_job.get("kind")
        if kind not in _KIND_ORDER or raw_dataset.get("kind") != kind:
            raise HistoryCampaignPublicationError("publication evidence kind is invalid")
        kind = cast(str, kind)
        by_kind[kind]["dataset_count"] += 1
        by_kind[kind]["file_count"] += _integer(raw_dataset, "file_count", minimum=1)
        by_kind[kind]["parquet_bytes"] += _integer(raw_dataset, "parquet_bytes", minimum=1)
        dataset_rows = _integer(raw_dataset, "row_count")
        by_kind[kind]["row_count"] += dataset_rows
        if kind != "funding":
            candle_admitted_rows += dataset_rows
            raw_admission = raw_job.get("canonical_admission")
            if raw_admission is None:
                candle_source_rows += dataset_rows
            else:
                if (
                    not isinstance(raw_admission, dict)
                    or raw_dataset.get("canonical_admission") != raw_admission
                    or raw_dataset.get("source_row_count") != raw_job.get("source_row_count")
                    or raw_admission.get("policy") != CANONICAL_ADMISSION_POLICY
                ):
                    raise HistoryCampaignPublicationError(
                        "publication evidence canonical admission differs"
                    )
                source_rows = _integer(raw_admission, "source_row_count", minimum=1)
                admitted_rows = _integer(raw_admission, "admitted_row_count")
                excluded_rows = _integer(raw_admission, "excluded_row_count", minimum=1)
                raw_reasons = raw_admission.get("reason_counts")
                if (
                    admitted_rows != dataset_rows
                    or source_rows != admitted_rows + excluded_rows
                    or raw_job.get("source_row_count") != source_rows
                    or not isinstance(raw_reasons, dict)
                    or set(raw_reasons) != set(CANONICAL_ADMISSION_REASONS)
                ):
                    raise HistoryCampaignPublicationError(
                        "publication evidence canonical admission counts differ"
                    )
                candle_source_rows += source_rows
                canonical_excluded_rows += excluded_rows
                for reason in CANONICAL_ADMISSION_REASONS:
                    canonical_reason_counts[reason] += _integer(raw_reasons, reason)
        required_free_bytes.append(_integer(raw_job, "required_free_bytes", minimum=1))
        planned_peak_memory_bytes.append(_integer(raw_job, "planned_peak_memory_bytes", minimum=1))
    if not required_free_bytes:
        raise HistoryCampaignPublicationError("publication evidence has no datasets")

    months: set[str] = set()
    buckets: set[int] = set()
    for raw_source_job in cast(list[dict[str, object]], source_jobs):
        month = raw_source_job.get("month")
        bucket = raw_source_job.get("bucket")
        if not isinstance(month, str) or isinstance(bucket, bool) or not isinstance(bucket, int):
            raise HistoryCampaignPublicationError("source campaign scope is invalid")
        months.add(month)
        buckets.add(bucket)
    raw_symbols = source_request.get("symbols")
    raw_kinds = source_request.get("kinds")
    if not isinstance(raw_symbols, list) or not isinstance(raw_kinds, list):
        raise HistoryCampaignPublicationError("source campaign request scope is invalid")
    if set(cast(list[str], raw_kinds)) != set(by_kind):
        raise HistoryCampaignPublicationError("publication and source kind inventories differ")

    canonical_payload: dict[str, object] = {
        "by_kind": [{"kind": kind, **by_kind[kind]} for kind in _KIND_ORDER if kind in by_kind],
        "dataset_count": completed.dataset_count,
        "file_count": completed.file_count,
        "parquet_bytes": completed.parquet_bytes,
        "row_count": completed.row_count,
    }
    if canonical_excluded_rows:
        if sum(canonical_reason_counts.values()) != canonical_excluded_rows:
            raise HistoryCampaignPublicationError(
                "publication evidence canonical admission reasons differ"
            )
        canonical_payload["admission"] = {
            "admitted_row_count": candle_admitted_rows,
            "excluded_row_count": canonical_excluded_rows,
            "policy": CANONICAL_ADMISSION_POLICY,
            "reason_counts": canonical_reason_counts,
            "source_row_count": candle_source_rows,
        }

    payload: dict[str, object] = {
        "bindings": {
            "capacity_evidence_sha256": _sha(publication_plan, "capacity_evidence_sha256"),
            "instrument_registry_sha256": _sha(publication_plan, "instrument_evidence_sha256"),
            "publication_manifest_sha256": completed.manifest_sha256,
            "publication_plan_sha256": publication_plan_sha,
            "source_campaign_manifest_sha256": _sha(
                publication_plan, "source_campaign_manifest_sha256"
            ),
            "source_campaign_plan_sha256": source_plan_sha,
            "source_campaign_request_sha256": _sha(source_plan, "campaign_request_sha256"),
        },
        "canonical": canonical_payload,
        "evidence_schema": CAMPAIGN_PUBLICATION_EVIDENCE_CONTRACT,
        "generated_at_utc": generated_at_utc,
        "limitations": [
            "Canonical publication and lineage verification do not prove gap-free or complete "
            "historical coverage.",
            "Current registry lifecycle intersection is ex-post acquisition scope, not "
            "point-in-time strategy metadata.",
            "This evidence does not register datasets in the research catalog or select them "
            "for a strategy release.",
            "Hashes cannot reconstruct market rows; the verified runtime artifacts require a "
            "separate retention and backup policy.",
            *(
                [
                    "Canonical representation exclusions remain unaccepted and keep coverage "
                    "blocked pending a reviewed physical-contract or source-policy decision."
                ]
                if canonical_excluded_rows
                else []
            ),
            "This evidence does not close Gate 2 or authorize private endpoints, orders, bots, "
            "transfers, or live execution.",
        ],
        "process": {
            "canonical_child_receipts_verified": True,
            "deterministic_resume_supported": True,
            "evidence_builder_software_identity": software_identity,
            "initial_source_semantic_admission_required": True,
            "max_concurrent_writers": 1,
            "publication_aggregate_receipt_verified": True,
            "publisher_software_identity": publisher_identity,
            "source_aggregate_receipt_verified": True,
            "source_child_receipts_verified": True,
            "source_reverification_mode": "receipt-integrity-without-row-decode-v1",
        },
        "resource_bounds": {
            "maximum_child_planned_peak_memory_bytes": max(planned_peak_memory_bytes),
            "maximum_child_required_free_bytes": max(required_free_bytes),
        },
        "scope": {
            "bucket_count": len(buckets),
            "end_ms": source_request["end_ms"],
            "kind_count": len(raw_kinds),
            "month_count": len(months),
            "start_ms": source_request["start_ms"],
            "symbol_count": len(raw_symbols),
        },
        "status": "verified-canonical-history-campaign-publication",
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_instrument_identities": False,
            "evidence_contains_market_values": False,
            "evidence_contains_runtime_paths": False,
            "runtime_market_artifacts_committed_to_git": False,
        },
        "verification": {
            "completed_publication_verification_elapsed_ms": verification_elapsed_ms,
            "source_reverification_mode": "receipt-integrity-without-row-decode-v1",
        },
    }
    if sum(item["dataset_count"] for item in by_kind.values()) != completed.dataset_count:
        raise HistoryCampaignPublicationError("publication evidence dataset total differs")
    if sum(item["row_count"] for item in by_kind.values()) != completed.row_count:
        raise HistoryCampaignPublicationError("publication evidence row total differs")
    if sum(item["file_count"] for item in by_kind.values()) != completed.file_count:
        raise HistoryCampaignPublicationError("publication evidence file total differs")
    if sum(item["parquet_bytes"] for item in by_kind.values()) != completed.parquet_bytes:
        raise HistoryCampaignPublicationError("publication evidence byte total differs")
    payload["content_sha256"] = canonical_sha256(payload)
    return payload
