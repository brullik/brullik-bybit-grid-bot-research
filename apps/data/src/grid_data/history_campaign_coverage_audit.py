"""GitHub-safe aggregate coverage audit for a canonical history campaign."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Final, cast

from grid_contracts.canonical import canonical_json_bytes, canonical_sha256

from grid_data.funding_acquisition import FundingAcquisitionError
from grid_data.funding_coverage_audit import build_completed_funding_coverage_audit
from grid_data.history_acquisition import HistoryAcquisitionError
from grid_data.history_campaign_publication import (
    CAMPAIGN_PUBLICATION_PLAN_CONTRACT,
    HistoryCampaignPublicationError,
    verify_completed_history_campaign_publication,
)
from grid_data.history_coverage_audit import build_completed_history_coverage_audit

CAMPAIGN_COVERAGE_AUDIT_CONTRACT: Final = "grid.history-campaign-coverage-audit/v1"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
_KINDS: Final = ("trade", "mark", "funding")


@dataclass(frozen=True, slots=True)
class HistoryCampaignCoverageAudit:
    payload: dict[str, object]
    passed: bool


def _object(path: Path) -> dict[str, object]:
    try:
        data = path.read_bytes()
        raw = json.loads(data)
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryCampaignPublicationError(f"cannot load verified artifact: {path}") from error
    if not isinstance(raw, dict) or canonical_json_bytes(raw) != data:
        raise HistoryCampaignPublicationError(f"artifact is not canonical JSON: {path}")
    return cast(dict[str, object], raw)


def _generated_at(value: str) -> str:
    if not value.endswith("Z"):
        raise HistoryCampaignPublicationError("generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise HistoryCampaignPublicationError("generated_at_utc is invalid") from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise HistoryCampaignPublicationError("generated_at_utc must be UTC")
    return value


def _integer(parent: dict[str, object], key: str) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HistoryCampaignPublicationError(f"child audit field is invalid: {key}")
    return value


def _reason_counts(payload: dict[str, object]) -> dict[str, int]:
    policy = payload.get("reason_policy")
    if not isinstance(policy, dict) or not isinstance(policy.get("observed_reason_counts"), dict):
        raise HistoryCampaignPublicationError("child audit reason policy is invalid")
    counts: dict[str, int] = {}
    for key, value in cast(dict[str, object], policy["observed_reason_counts"]).items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise HistoryCampaignPublicationError("child audit reason count is invalid")
        counts[key] = value
    return counts


def build_history_campaign_coverage_audit(
    publication_root: Path,
    source_campaign_root: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    store_root: Path,
    *,
    publisher_software_identity: str,
    audit_software_identity: str,
    generated_at_utc: str,
) -> HistoryCampaignCoverageAudit:
    """Audit all canonical children sequentially without changing child acceptance policy."""

    for name, identity in (
        ("publisher", publisher_software_identity),
        ("audit", audit_software_identity),
    ):
        if SOFTWARE_IDENTITY_RE.fullmatch(identity) is None:
            raise HistoryCampaignPublicationError(f"{name} identity must be git:<40 hex>")
    generated_at = _generated_at(generated_at_utc)
    completed = verify_completed_history_campaign_publication(
        publication_root,
        source_campaign_root,
    )
    plan = _object(completed.plan_path)
    if plan.get("contract") != CAMPAIGN_PUBLICATION_PLAN_CONTRACT:
        raise HistoryCampaignPublicationError("campaign audit requires the v1 publication plan")
    if plan.get("publisher_software_identity") != publisher_software_identity:
        raise HistoryCampaignPublicationError("campaign audit publisher identity differs")
    raw_jobs = plan.get("jobs")
    if not isinstance(raw_jobs, list) or len(raw_jobs) != completed.dataset_count:
        raise HistoryCampaignPublicationError("campaign audit job inventory differs")

    child_results: list[dict[str, object]] = []
    reason_counts: Counter[str] = Counter()
    by_kind: dict[str, dict[str, int]] = {
        kind: {"blocked_count": 0, "dataset_count": 0, "passed_count": 0, "row_count": 0}
        for kind in _KINDS
    }
    candle_quality = Counter[str]()
    funding_quality = Counter[str]()
    staging_root = source_campaign_root.resolve().parent.parent
    for sequence, raw_job in enumerate(cast(list[dict[str, object]], raw_jobs)):
        kind = raw_job.get("kind")
        relative = raw_job.get("source_job_root")
        if kind not in _KINDS or not isinstance(relative, str):
            raise HistoryCampaignPublicationError("campaign audit child identity is invalid")
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or "\\" in relative:
            raise HistoryCampaignPublicationError("campaign audit child root is unsafe")
        job_root = staging_root.joinpath(*path.parts)
        try:
            if kind == "funding":
                funding_audit = build_completed_funding_coverage_audit(
                    job_root,
                    instrument_registry_path,
                    capacity_evidence_path,
                    store_root,
                    publisher_software_identity=publisher_software_identity,
                    audit_software_identity=audit_software_identity,
                    generated_at_utc=generated_at,
                )
                child_payload = funding_audit.payload
                quality = cast(dict[str, object], child_payload["quality"])
                for key in (
                    "boundary_page_count",
                    "duplicate_key_count",
                    "empty_range_page_count",
                    "internal_interval_mismatch_count",
                    "interval_change_count",
                    "lifecycle_failure_count",
                    "observed_event_count",
                    "predecessor_interval_mismatch_count",
                    "range_page_count",
                    "unrequested_row_count",
                    "unexpected_timestamp_count",
                ):
                    funding_quality[key] += _integer(quality, key)
            else:
                candle_audit = build_completed_history_coverage_audit(
                    job_root,
                    instrument_registry_path,
                    capacity_evidence_path,
                    store_root,
                    publisher_software_identity=publisher_software_identity,
                    audit_software_identity=audit_software_identity,
                    generated_at_utc=generated_at,
                )
                child_payload = candle_audit.payload
                quality = cast(dict[str, object], child_payload["quality"])
                for key in (
                    "conflicting_key_count",
                    "duplicate_key_count",
                    "expected_minute_count",
                    "lifecycle_failure_count",
                    "missing_minute_count",
                    "observed_row_count",
                    "unrequested_row_count",
                    "unexpected_timestamp_count",
                ):
                    candle_quality[key] += _integer(quality, key)
                gap = child_payload.get("gap_evidence")
                if not isinstance(gap, dict):
                    raise HistoryCampaignPublicationError("candle child gap evidence is invalid")
                candle_quality["gap_range_count"] += _integer(gap, "gap_range_count")
        except (FundingAcquisitionError, HistoryAcquisitionError) as error:
            raise HistoryCampaignPublicationError(
                f"campaign coverage child {sequence} cannot be audited: {error}"
            ) from error
        status = child_payload.get("status")
        content_sha = child_payload.get("content_sha256")
        if status not in ("passed", "blocked") or not isinstance(content_sha, str):
            raise HistoryCampaignPublicationError("child coverage result is invalid")
        if content_sha != canonical_sha256(
            {key: value for key, value in child_payload.items() if key != "content_sha256"}
        ):
            raise HistoryCampaignPublicationError("child coverage content hash is invalid")
        reason_counts.update(_reason_counts(child_payload))
        summary = by_kind[kind]
        summary["dataset_count"] += 1
        summary[f"{status}_count"] += 1
        summary["row_count"] += _integer(raw_job, "row_count")
        child_results.append(
            {
                "audit_content_sha256": content_sha,
                "kind": kind,
                "sequence": sequence,
                "status": status,
            }
        )

    blocked_count = sum(item["blocked_count"] for item in by_kind.values())
    payload: dict[str, object] = {
        "audit_software_identity": audit_software_identity,
        "bindings": {
            "capacity_evidence_sha256": plan["capacity_evidence_sha256"],
            "instrument_registry_sha256": plan["instrument_evidence_sha256"],
            "publication_manifest_sha256": completed.manifest_sha256,
            "publication_plan_sha256": canonical_sha256(plan),
            "publisher_software_identity": publisher_software_identity,
            "source_campaign_manifest_sha256": plan["source_campaign_manifest_sha256"],
            "source_campaign_plan_sha256": plan["source_campaign_plan_sha256"],
        },
        "child_results": child_results,
        "contract": CAMPAIGN_COVERAGE_AUDIT_CONTRACT,
        "generated_at_utc": generated_at,
        "inventory": {
            "blocked_count": blocked_count,
            "by_kind": [
                {"kind": kind, **by_kind[kind]} for kind in _KINDS if by_kind[kind]["dataset_count"]
            ],
            "dataset_count": completed.dataset_count,
            "passed_count": completed.dataset_count - blocked_count,
            "row_count": completed.row_count,
        },
        "limitations": [
            "Child acceptance remains exactly ADR-0026 and ADR-0034; no gap or cadence reason "
            "is accepted by aggregation.",
            "Current registry lifecycle bounds do not prove a complete dated historical universe.",
            "Only child audit hashes and aggregate counts are public; full child diagnostics "
            "remain runtime data.",
            "This audit does not repair, compact, register, select, close Gate 2, or authorize "
            "private or live operations.",
        ],
        "quality": {
            "candle": dict(sorted(candle_quality.items())),
            "funding": dict(sorted(funding_quality.items())),
        },
        "reason_policy": {
            "accepted_reason_codes": [],
            "observed_reason_counts": dict(sorted(reason_counts.items())),
            "unaccepted_reason_codes": sorted(reason_counts),
            "unknown_reason_count": 0,
        },
        "status": "passed" if blocked_count == 0 else "blocked",
        "storage_policy": {
            "account_data_included": False,
            "dataset_or_instrument_identities_included": False,
            "market_values_included": False,
            "runtime_paths_included": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return HistoryCampaignCoverageAudit(payload=payload, passed=blocked_count == 0)
