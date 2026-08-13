"""GitHub-safe evidence for a verified public history Landing campaign."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Final, cast

from grid_contracts.canonical import canonical_sha256

from grid_data.history_campaign import (
    CAMPAIGN_MANIFEST_CONTRACT,
    CAMPAIGN_PLAN_CONTRACT,
    HistoryCampaignError,
    verify_completed_history_campaign,
)
from grid_data.public_rate_limit import (
    ADAPTIVE_RATE_POLICY,
    AdaptiveRateLimitError,
    verify_adaptive_rate_summary,
)

CAMPAIGN_EVIDENCE_CONTRACT: Final = "grid.phase2-public-history-campaign/v1"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
KIND_ORDER: Final = ("trade", "mark", "funding")
QUARANTINE_POLICY: Final = "exact-source-row-quarantine-v1"
QUARANTINE_REASONS: Final = (
    "close_outside_low_high",
    "low_exceeds_high",
    "open_outside_low_high",
)


def _object(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryCampaignError(
            f"verified campaign artifact cannot be loaded: {path.name}"
        ) from error
    if not isinstance(raw, dict):
        raise HistoryCampaignError(f"verified campaign artifact is not an object: {path.name}")
    return cast(dict[str, object], raw)


def _integer(parent: dict[str, object], key: str) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HistoryCampaignError(f"verified campaign field must be non-negative: {key}")
    return value


def _artifact_bytes(campaign_root: Path, plan: dict[str, object]) -> int:
    total = sum(path.stat().st_size for path in campaign_root.iterdir() if path.is_file())
    raw_jobs = plan.get("jobs")
    if not isinstance(raw_jobs, list):
        raise HistoryCampaignError("verified campaign plan has no job inventory")
    staging_root = campaign_root.parent.parent
    for raw_job in raw_jobs:
        if not isinstance(raw_job, dict) or not isinstance(raw_job.get("job_root"), str):
            raise HistoryCampaignError("verified campaign job root is invalid")
        relative = PurePosixPath(raw_job["job_root"])
        job_root = staging_root.joinpath(*relative.parts)
        total += sum(path.stat().st_size for path in job_root.rglob("*") if path.is_file())
    return total


def _child_manifests(campaign_root: Path, plan: dict[str, object]) -> list[dict[str, object]]:
    raw_jobs = plan.get("jobs")
    if not isinstance(raw_jobs, list):
        raise HistoryCampaignError("verified campaign plan has no job inventory")
    staging_root = campaign_root.parent.parent
    manifests: list[dict[str, object]] = []
    for raw_job in raw_jobs:
        if not isinstance(raw_job, dict) or not isinstance(raw_job.get("job_root"), str):
            raise HistoryCampaignError("verified campaign job root is invalid")
        relative = PurePosixPath(raw_job["job_root"])
        manifests.append(_object(staging_root.joinpath(*relative.parts) / "manifest.json"))
    return manifests


def _adaptive_summary(
    child_manifests: list[dict[str, object]],
    *,
    configured_target_rps: int,
    total_http_requests: int,
    require_complete: bool,
) -> dict[str, object] | None:
    verified: list[dict[str, object]] = []
    missing_count = 0
    completed_page_response_coverage_complete = True
    for manifest in child_manifests:
        request_bound = manifest.get("request_bound")
        if not isinstance(request_bound, dict):
            raise HistoryCampaignError("verified child manifest has no request bound")
        raw = request_bound.get("adaptive_throttling")
        if raw is None:
            missing_count += 1
            continue
        actual_http_requests = _integer(request_bound, "actual_http_requests")
        try:
            summary = verify_adaptive_rate_summary(
                raw,
                configured_target_rps=configured_target_rps,
                maximum_response_count=actual_http_requests,
            )
        except AdaptiveRateLimitError as error:
            raise HistoryCampaignError(
                "verified child adaptive throttling summary is invalid"
            ) from error
        verified.append(summary)
        page_count = _integer(manifest, "page_count")
        response_count = cast(int, summary["response_observation_count"])
        if response_count < page_count:
            completed_page_response_coverage_complete = False
    if missing_count == len(child_manifests):
        if require_complete:
            raise HistoryCampaignError("complete throttling evidence requires every child summary")
        return None
    if missing_count:
        raise HistoryCampaignError("campaign mixes legacy and adaptive child summaries")

    counter_fields = (
        "automatic_increase_count",
        "complete_header_observation_count",
        "cooldown_event_count",
        "header_absent_observation_count",
        "invalid_header_observation_count",
        "low_headroom_event_count",
        "rate_limit_event_count",
        "rate_reduction_count",
        "response_observation_count",
    )
    totals = {
        name: sum(cast(int, summary[name]) for summary in verified) for name in counter_fields
    }
    observed = totals["response_observation_count"]
    if observed > total_http_requests:
        raise HistoryCampaignError("adaptive observations exceed verified HTTP requests")
    attempts_without_response = total_http_requests - observed
    if require_complete and not completed_page_response_coverage_complete:
        raise HistoryCampaignError(
            "complete throttling evidence requires every completed page response to be observed"
        )
    return {
        **totals,
        "child_job_count": len(verified),
        "completed_page_response_coverage_complete": (completed_page_response_coverage_complete),
        "configured_target_rps": configured_target_rps,
        "maximum_child_final_effective_rps": max(
            cast(int, summary["final_effective_rps"]) for summary in verified
        ),
        "maximum_cooldown_ms": max(
            cast(int, summary["maximum_cooldown_ms"]) for summary in verified
        ),
        "minimum_child_effective_rps": min(
            cast(int, summary["minimum_effective_rps"]) for summary in verified
        ),
        "minimum_child_final_effective_rps": min(
            cast(int, summary["final_effective_rps"]) for summary in verified
        ),
        "policy": ADAPTIVE_RATE_POLICY,
        "response_observation_classification_complete": True,
        "transport_attempt_accounting_complete": True,
        "transport_attempt_count": total_http_requests,
        "transport_attempt_without_response_count": attempts_without_response,
    }


def _timing_summary(
    child_manifests: list[dict[str, object]], *, require_complete: bool
) -> dict[str, object] | None:
    starts: list[int] = []
    completions: list[int] = []
    elapsed: list[int] = []
    missing_count = 0
    for manifest in child_manifests:
        started = manifest.get("started_at_ms")
        completed = manifest.get("completed_at_ms")
        if started is None:
            missing_count += 1
            continue
        if (
            isinstance(started, bool)
            or not isinstance(started, int)
            or started < 0
            or isinstance(completed, bool)
            or not isinstance(completed, int)
            or completed < started
        ):
            raise HistoryCampaignError("verified child execution timestamps are invalid")
        starts.append(started)
        completions.append(completed)
        elapsed.append(completed - started)
    if missing_count == len(child_manifests):
        if require_complete:
            raise HistoryCampaignError("complete throttling evidence requires every child timing")
        return None
    if missing_count:
        raise HistoryCampaignError("campaign mixes timed and legacy child manifests")
    return {
        "campaign_completed_at_ms": max(completions),
        "campaign_elapsed_ms": max(completions) - min(starts),
        "campaign_started_at_ms": min(starts),
        "summed_child_elapsed_ms": sum(elapsed),
        "timed_child_count": len(starts),
    }


def _source_quality_summary(
    plan: dict[str, object],
    raw_jobs: list[dict[str, object]],
    child_manifests: list[dict[str, object]],
) -> dict[str, object]:
    raw_plan_jobs = plan.get("jobs")
    if not isinstance(raw_plan_jobs, list) or not (
        len(raw_plan_jobs) == len(raw_jobs) == len(child_manifests)
    ):
        raise HistoryCampaignError("campaign source-quality inventories differ")
    admitted_rows = 0
    source_rows = 0
    quarantined_rows = 0
    candle_job_count = 0
    reason_counts = {reason: 0 for reason in QUARANTINE_REASONS}
    quarantine_bindings: list[dict[str, object]] = []
    for raw_plan_job, raw_job, child in zip(raw_plan_jobs, raw_jobs, child_manifests, strict=True):
        if not isinstance(raw_plan_job, dict):
            raise HistoryCampaignError("campaign source-quality plan job is invalid")
        kind = raw_plan_job.get("kind")
        if kind == "funding":
            continue
        if kind not in ("trade", "mark") or raw_job.get("kind") != kind:
            raise HistoryCampaignError("campaign source-quality kind binding is invalid")
        candle_job_count += 1
        admitted = _integer(child, "row_count")
        raw_quality = child.get("source_quality")
        if raw_quality is None:
            admitted_rows += admitted
            source_rows += admitted
            continue
        expected_keys = {
            "admitted_row_count",
            "policy",
            "quarantined_row_count",
            "quarantined_rows_sha256",
            "reason_counts",
            "source_row_count",
        }
        if not isinstance(raw_quality, dict) or set(raw_quality) != expected_keys:
            raise HistoryCampaignError("campaign child source-quality fields are invalid")
        quarantined = _integer(raw_quality, "quarantined_row_count")
        source = _integer(raw_quality, "source_row_count")
        quality_admitted = _integer(raw_quality, "admitted_row_count")
        raw_reasons = raw_quality.get("reason_counts")
        quarantine_sha = raw_quality.get("quarantined_rows_sha256")
        if (
            raw_quality.get("policy") != QUARANTINE_POLICY
            or quality_admitted != admitted
            or source != admitted + quarantined
            or not isinstance(raw_reasons, dict)
            or set(raw_reasons) != set(QUARANTINE_REASONS)
            or not isinstance(quarantine_sha, str)
            or SHA256_RE.fullmatch(quarantine_sha) is None
        ):
            raise HistoryCampaignError("campaign child source-quality facts are invalid")
        verified_reasons = {reason: _integer(raw_reasons, reason) for reason in QUARANTINE_REASONS}
        if sum(verified_reasons.values()) != quarantined:
            raise HistoryCampaignError("campaign child quarantine reasons do not sum")
        admitted_rows += admitted
        source_rows += source
        quarantined_rows += quarantined
        for reason, count in verified_reasons.items():
            reason_counts[reason] += count
        if quarantined:
            job_manifest_sha = raw_job.get("job_manifest_sha256")
            if (
                not isinstance(job_manifest_sha, str)
                or SHA256_RE.fullmatch(job_manifest_sha) is None
            ):
                raise HistoryCampaignError("campaign child manifest binding is invalid")
            quarantine_bindings.append(
                {
                    "job_manifest_sha256": job_manifest_sha,
                    "quarantined_row_count": quarantined,
                    "quarantined_rows_sha256": quarantine_sha,
                }
            )
    return {
        "admitted_candle_row_count": admitted_rows,
        "candle_job_count": candle_job_count,
        "canonical_coverage_complete": quarantined_rows == 0,
        "policy": QUARANTINE_POLICY,
        "quarantine_binding_sha256": canonical_sha256(quarantine_bindings),
        "quarantined_row_count": quarantined_rows,
        "reason_counts": reason_counts,
        "source_candle_row_count": source_rows,
    }


def build_history_campaign_evidence(
    campaign_root: Path,
    *,
    generated_at_utc: str,
    software_identity: str,
    require_complete_throttling_evidence: bool = False,
) -> dict[str, object]:
    """Re-verify a campaign and project only public hashes, counts, and process facts."""

    if SOFTWARE_IDENTITY_RE.fullmatch(software_identity) is None:
        raise HistoryCampaignError("campaign evidence software identity must be git:<40 hex>")
    if not generated_at_utc.endswith("Z"):
        raise HistoryCampaignError("campaign evidence timestamp must use UTC Z notation")
    try:
        generated_at = datetime.fromisoformat(generated_at_utc.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise HistoryCampaignError("campaign evidence timestamp is invalid") from error
    offset = generated_at.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise HistoryCampaignError("campaign evidence timestamp must be UTC")
    completed = verify_completed_history_campaign(campaign_root)
    plan = _object(completed.plan_path)
    manifest = _object(completed.manifest_path)
    if plan.get("contract") != CAMPAIGN_PLAN_CONTRACT:
        raise HistoryCampaignError("campaign evidence requires the v1 verified plan")
    if manifest.get("contract") != CAMPAIGN_MANIFEST_CONTRACT:
        raise HistoryCampaignError("campaign evidence requires the v1 verified manifest")
    request = plan.get("campaign_request")
    raw_jobs = manifest.get("jobs")
    if not isinstance(request, dict) or not isinstance(raw_jobs, list):
        raise HistoryCampaignError("campaign evidence inputs are incomplete")
    raw_symbols = request.get("symbols")
    raw_kinds = request.get("kinds")
    if not isinstance(raw_symbols, list) or not isinstance(raw_kinds, list):
        raise HistoryCampaignError("campaign evidence scope is invalid")

    by_kind: dict[str, dict[str, int]] = defaultdict(
        lambda: {"http_request_count": 0, "job_count": 0, "page_count": 0, "row_count": 0}
    )
    months: set[str] = set()
    buckets: set[int] = set()
    for plan_job in cast(list[dict[str, object]], plan["jobs"]):
        month = plan_job.get("month")
        bucket = plan_job.get("bucket")
        if not isinstance(month, str) or isinstance(bucket, bool) or not isinstance(bucket, int):
            raise HistoryCampaignError("campaign plan month/bucket fact is invalid")
        months.add(month)
        buckets.add(bucket)
    for job in raw_jobs:
        if not isinstance(job, dict) or job.get("kind") not in ("trade", "mark", "funding"):
            raise HistoryCampaignError("campaign manifest kind fact is invalid")
        kind = cast(str, job["kind"])
        by_kind[kind]["http_request_count"] += _integer(job, "actual_http_requests")
        by_kind[kind]["job_count"] += 1
        by_kind[kind]["page_count"] += _integer(job, "page_count")
        by_kind[kind]["row_count"] += _integer(job, "row_count")

    source_policy = plan.get("source_policy")
    if not isinstance(source_policy, dict) or source_policy.get("tick_rows_requested") is not False:
        raise HistoryCampaignError("campaign evidence requires the no-tick public source policy")
    attempt_count = _integer(manifest, "http_request_count")
    page_count = _integer(manifest, "page_count")
    retry_count = attempt_count - page_count
    if retry_count < 0:
        raise HistoryCampaignError("campaign attempts cannot be lower than page count")
    kind_counts = Counter(cast(list[str], raw_kinds))
    if set(kind_counts) != set(by_kind) or any(count != 1 for count in kind_counts.values()):
        raise HistoryCampaignError("campaign request and completed kind inventories differ")
    configured_target_rps = _integer(request, "target_rps")
    child_manifests = _child_manifests(completed.campaign_root, plan)
    adaptive = _adaptive_summary(
        child_manifests,
        configured_target_rps=configured_target_rps,
        total_http_requests=attempt_count,
        require_complete=require_complete_throttling_evidence,
    )
    timing = _timing_summary(
        child_manifests,
        require_complete=require_complete_throttling_evidence,
    )

    requested_kinds = [kind for kind in KIND_ORDER if kind in kind_counts]
    payload: dict[str, object] = {
        "bindings": {
            "campaign_manifest_sha256": completed.manifest_sha256,
            "campaign_plan_sha256": canonical_sha256(plan),
            "campaign_request_sha256": plan["campaign_request_sha256"],
            "capacity_evidence_sha256": plan["capacity_evidence_sha256"],
            "instrument_registry_sha256": plan["instrument_evidence_sha256"],
        },
        "evidence_schema": CAMPAIGN_EVIDENCE_CONTRACT,
        "generated_at_utc": generated_at_utc,
        "landing": {
            "artifact_bytes": _artifact_bytes(completed.campaign_root, plan),
            "by_kind": [{"kind": kind, **by_kind[kind]} for kind in requested_kinds],
            "http_request_count": attempt_count,
            "job_count": completed.job_count,
            "page_count": page_count,
            "retry_count": retry_count,
            "row_count": completed.row_count,
        },
        "limitations": [
            "This proves retained public Landing responses, not canonical Parquet publication.",
            "Current registry lifecycle intersection is ex-post acquisition scope, not historical "
            "point-in-time strategy metadata.",
            "Source return does not independently prove that every venue candle or funding "
            "event exists.",
            "Quarantined source rows remain absent from canonical history and block complete "
            "coverage until separately reconciled.",
            "This evidence does not accept gaps or cadence changes, close Gate 2, or authorize "
            "private/live operations.",
        ],
        "process": {
            "aggregate_receipt_verified": True,
            "child_receipts_verified": True,
            "deterministic_resume_supported": True,
            "software_identity": software_identity,
        },
        "scope": {
            "bucket_count": len(buckets),
            "end_ms": request["end_ms"],
            "kind_count": len(raw_kinds),
            "month_count": len(months),
            "start_ms": request["start_ms"],
            "symbol_count": len(raw_symbols),
        },
        "source_policy": {
            "authentication": "none",
            "base_url": "https://api.bybit.com",
            "funding_endpoint": source_policy["funding"],
            "mark_endpoint": source_policy["mark"],
            "private_endpoints_called": False,
            "tick_rows_requested": False,
            "trade_endpoint": source_policy["trade"],
        },
        "source_quality": _source_quality_summary(
            plan,
            cast(list[dict[str, object]], raw_jobs),
            child_manifests,
        ),
        "status": "verified-public-landing-campaign",
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_market_values": False,
            "evidence_contains_runtime_paths": False,
            "runtime_market_artifacts_committed_to_git": False,
        },
    }
    if adaptive is not None:
        payload["adaptive_throttling"] = adaptive
    if timing is not None:
        payload["timing"] = timing
    payload["content_sha256"] = canonical_sha256(payload)
    return payload
