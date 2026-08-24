"""Private partition and GitHub-safe evidence for terminal funding boundaries."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Final

from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file

from grid_data.evidence import verify_evidence
from grid_data.funding_source_boundary import (
    FundingSourceBoundaryError,
    VerifiedTerminalFundingBoundary,
    verify_terminal_funding_source_boundary,
)

TERMINAL_PARTITION_CONTRACT: Final = "grid.bybit-funding-source-boundary-terminal-partition/v1"
TERMINAL_EVIDENCE_CONTRACT: Final = "grid.phase2-funding-source-boundary-terminal-partition/v1"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")


def _generated_at(value: str) -> str:
    if not value.endswith("Z"):
        raise FundingSourceBoundaryError("terminal funding evidence timestamp must use UTC Z")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise FundingSourceBoundaryError(
            "terminal funding evidence timestamp is invalid"
        ) from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise FundingSourceBoundaryError("terminal funding evidence timestamp must be UTC")
    return value


def _software_identity(value: str) -> str:
    if SOFTWARE_IDENTITY_RE.fullmatch(value) is None:
        raise FundingSourceBoundaryError(
            "terminal funding evidence software identity must be git:<40 hex>"
        )
    return value


def _partition_payload(
    verified: VerifiedTerminalFundingBoundary,
    *,
    generated_at_utc: str,
    software_identity: str,
) -> dict[str, object]:
    insufficient_count = (
        verified.terminal_insufficient_one_count + verified.terminal_insufficient_zero_count
    )
    if insufficient_count == 0:
        raise FundingSourceBoundaryError(
            "terminal partition requires at least one predecessor-insufficient series"
        )
    series = [
        {
            "canonical_start_ms": item.canonical_start_ms,
            "classification": item.classification,
            "event_count": item.event_count,
            "first_observed_settlement_ms": item.first_observed_settlement_ms,
            "instrument_id": item.instrument_id,
            "page_count": item.page_count,
            "symbol": item.symbol,
        }
        for item in verified.results
    ]
    payload: dict[str, object] = {
        "bindings": {
            "boundary_page_chain_sha256": verified.page_chain_sha256,
            "boundary_plan_sha256": verified.plan_sha256,
            "boundary_request_sha256": verified.request_sha256,
            "instrument_registry_sha256": verified.registry_sha256,
        },
        "contract": TERMINAL_PARTITION_CONTRACT,
        "generated_at_utc": _generated_at(generated_at_utc),
        "process": {
            "all_series_terminal": True,
            "discovery_software_identity": verified.software_identity,
            "page_receipts_verified": True,
            "partition_software_identity": _software_identity(software_identity),
        },
        "result": {
            "event_count": verified.event_count,
            "http_attempt_count": verified.http_attempt_count,
            "page_count": verified.page_count,
            "predecessor_proven_count": verified.predecessor_proven_count,
            "terminal_insufficient_one_count": verified.terminal_insufficient_one_count,
            "terminal_insufficient_zero_count": verified.terminal_insufficient_zero_count,
        },
        "scope": {
            "end_ms": verified.scan_end_ms,
            "start_ms": verified.scan_start_ms,
            "symbol_count": verified.symbol_count,
        },
        "series": series,
        "status": "terminal-partition-complete",
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def build_terminal_funding_boundary_partition(
    job_root: Path,
    *,
    generated_at_utc: str,
    software_identity: str,
) -> dict[str, object]:
    """Re-verify an incomplete v1 root and build its private terminal partition."""

    return _partition_payload(
        verify_terminal_funding_source_boundary(job_root),
        generated_at_utc=generated_at_utc,
        software_identity=software_identity,
    )


def _load_verified_partition(path: Path) -> dict[str, object]:
    resolved = path.resolve()
    if not verify_evidence(resolved):
        raise FundingSourceBoundaryError("terminal funding partition receipt is invalid")
    try:
        raw = resolved.read_bytes()
        loaded = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        raise FundingSourceBoundaryError("terminal funding partition is invalid JSON") from error
    if not isinstance(loaded, dict):
        raise FundingSourceBoundaryError("terminal funding partition must be an object")
    payload = dict(loaded)
    content_hash = payload.pop("content_sha256", None)
    if content_hash != canonical_sha256(payload):
        raise FundingSourceBoundaryError("terminal funding partition content hash is invalid")
    payload["content_sha256"] = content_hash
    if raw != canonical_json_bytes(payload) + b"\n":
        raise FundingSourceBoundaryError("terminal funding partition is not canonical JSON")
    return payload


def verify_terminal_funding_boundary_partition(
    partition_path: Path,
    job_root: Path,
) -> dict[str, object]:
    """Verify a private partition receipt and reproduce it from the terminal page chain."""

    partition = _load_verified_partition(partition_path)
    process = partition.get("process")
    if not isinstance(process, dict):
        raise FundingSourceBoundaryError("terminal funding partition process is invalid")
    expected = build_terminal_funding_boundary_partition(
        job_root,
        generated_at_utc=str(partition.get("generated_at_utc")),
        software_identity=str(process.get("partition_software_identity")),
    )
    if partition != expected:
        raise FundingSourceBoundaryError("terminal funding partition does not reproduce")
    return partition


def build_terminal_funding_boundary_evidence(
    partition_path: Path,
    job_root: Path,
    *,
    generated_at_utc: str,
    software_identity: str,
) -> dict[str, object]:
    """Rebuild the private partition and emit only aggregate GitHub-safe facts."""

    partition = verify_terminal_funding_boundary_partition(partition_path, job_root)
    process = partition["process"]
    assert isinstance(process, dict)
    bindings = partition["bindings"]
    result = partition["result"]
    scope = partition["scope"]
    assert isinstance(bindings, dict)
    assert isinstance(result, dict)
    assert isinstance(scope, dict)
    payload: dict[str, object] = {
        "assurances": {
            "all_series_terminal": True,
            "automatic_gate_acceptance_performed": False,
            "network_request_performed": False,
            "page_receipts_verified": True,
            "phase3_authorized": False,
            "private_or_live_capability_used": False,
        },
        "bindings": {
            **bindings,
            "terminal_partition_artifact_sha256": sha256_file(partition_path.resolve()),
            "terminal_partition_content_sha256": partition["content_sha256"],
        },
        "evidence_schema": TERMINAL_EVIDENCE_CONTRACT,
        "generated_at_utc": _generated_at(generated_at_utc),
        "limitations": [
            "Terminal source absence is negative evidence, not complete funding coverage.",
            "Only predecessor-proven series may enter a later derived acquisition request.",
            "Observed settlement identities and timestamps remain in the private partition.",
            "This evidence cannot close Gate 2 or authorize Phase 3 or live operations.",
        ],
        "process": {
            "discovery_software_identity": process["discovery_software_identity"],
            "evidence_software_identity": _software_identity(software_identity),
            "partition_software_identity": process["partition_software_identity"],
            "private_partition_reproduced": True,
        },
        "result": {
            **result,
            "funding_coverage_complete": False,
        },
        "scope": scope,
        "source_policy": {
            "authentication": "none",
            "base_url": "https://api.bybit.com",
            "endpoint": "/v5/market/funding/history",
            "private_endpoints_called": False,
            "retained_source_fields": ["fundingRateTimestamp"],
            "source_rates_validated_not_retained": True,
        },
        "status": "verified-terminal-funding-source-partition",
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
