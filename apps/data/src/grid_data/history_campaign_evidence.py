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

CAMPAIGN_EVIDENCE_CONTRACT: Final = "grid.phase2-public-history-campaign/v1"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")


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


def build_history_campaign_evidence(
    campaign_root: Path,
    *,
    generated_at_utc: str,
    software_identity: str,
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
            "by_kind": [{"kind": kind, **by_kind[kind]} for kind in ("trade", "mark", "funding")],
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
        "status": "verified-public-landing-campaign",
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_market_values": False,
            "evidence_contains_runtime_paths": False,
            "runtime_market_artifacts_committed_to_git": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload
