"""GitHub-safe aggregate evidence for verified funding source boundaries."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Final, cast

from grid_contracts.canonical import canonical_sha256

from grid_data.funding_source_boundary import (
    FundingSourceBoundaryError,
    verify_completed_funding_source_boundary,
)

BOUNDARY_EVIDENCE_CONTRACT: Final = "grid.phase2-funding-source-boundary/v1"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")


def _generated_at(value: str) -> str:
    if not value.endswith("Z"):
        raise FundingSourceBoundaryError("funding boundary evidence timestamp must use UTC Z")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise FundingSourceBoundaryError(
            "funding boundary evidence timestamp is invalid"
        ) from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise FundingSourceBoundaryError("funding boundary evidence timestamp must be UTC")
    return value


def build_funding_source_boundary_evidence(
    job_root: Path,
    *,
    generated_at_utc: str,
    software_identity: str,
) -> dict[str, object]:
    """Re-verify private runtime pages and emit only aggregate public-safe facts."""

    if SOFTWARE_IDENTITY_RE.fullmatch(software_identity) is None:
        raise FundingSourceBoundaryError(
            "funding boundary evidence software identity must be git:<40 hex>"
        )
    completed = verify_completed_funding_source_boundary(job_root)
    adaptive = completed.adaptive_throttling
    response_count = cast(int, adaptive["response_observation_count"])
    if response_count < completed.page_count:
        raise FundingSourceBoundaryError(
            "funding boundary evidence requires every completed page response to be observed"
        )
    retry_count = completed.http_attempt_count - completed.page_count
    attempts_without_response = completed.http_attempt_count - response_count
    if retry_count < 0 or attempts_without_response < 0:
        raise FundingSourceBoundaryError("funding boundary attempt evidence is inconsistent")

    payload: dict[str, object] = {
        "adaptive_throttling": {
            **adaptive,
            "completed_page_response_coverage_complete": True,
            "transport_attempt_accounting_complete": True,
            "transport_attempt_count": completed.http_attempt_count,
            "transport_attempt_without_response_count": attempts_without_response,
        },
        "bindings": {
            "boundary_manifest_sha256": completed.manifest_sha256,
            "boundary_plan_sha256": completed.plan_sha256,
            "boundary_request_sha256": completed.request_sha256,
            "instrument_registry_sha256": completed.registry_sha256,
        },
        "evidence_schema": BOUNDARY_EVIDENCE_CONTRACT,
        "generated_at_utc": _generated_at(generated_at_utc),
        "landing": {
            "event_count": completed.event_count,
            "http_attempt_count": completed.http_attempt_count,
            "page_count": completed.page_count,
            "retry_count": retry_count,
        },
        "limitations": [
            "This proves source-returned public funding settlement boundaries, not complete "
            "venue history.",
            "Registry lifecycle bounds are ex-post acquisition scope, not historical "
            "point-in-time strategy metadata.",
            "This evidence does not accept source gaps or historical funding cadence changes.",
            "This evidence does not publish canonical data, close Gate 2, or authorize "
            "private/live operations.",
        ],
        "process": {
            "aggregate_receipt_verified": True,
            "deterministic_resume_supported": True,
            "discovery_software_identity": completed.software_identity,
            "evidence_software_identity": software_identity,
            "page_receipts_verified": True,
        },
        "result": {
            "canonical_start_proven_count": completed.symbol_count,
            "predecessor_proven_count": completed.symbol_count,
        },
        "scope": {
            "end_ms": completed.scan_end_ms,
            "start_ms": completed.scan_start_ms,
            "symbol_count": completed.symbol_count,
        },
        "source_policy": {
            "authentication": "none",
            "base_url": "https://api.bybit.com",
            "endpoint": "/v5/market/funding/history",
            "private_endpoints_called": False,
            "retained_source_fields": ["fundingRateTimestamp"],
            "source_rates_validated_not_retained": True,
        },
        "status": "verified-public-funding-source-boundary",
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_funding_rates": False,
            "evidence_contains_instrument_identifiers": False,
            "evidence_contains_observed_settlement_timestamps": False,
            "evidence_contains_runtime_paths": False,
            "runtime_market_artifacts_committed_to_git": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload
