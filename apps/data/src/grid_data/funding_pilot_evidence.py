"""Sanitized GitHub-safe evidence for one verified public funding pilot."""

from __future__ import annotations

import json
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Final, cast

import pyarrow.compute as pc  # type: ignore[import-untyped]
from grid_contracts.canonical import canonical_sha256
from grid_market_store import (
    BUCKET_COUNT,
    COMPRESSION,
    COMPRESSION_LEVEL,
    FUNDING_CANONICAL_LAYOUT_ID,
    FUNDING_EXACT_PHYSICAL_CONTRACT,
    FUNDING_RATE_SCALE,
    TARGET_FILE_SIZE_BYTES,
    PublishedDataset,
    canonical_funding_schema,
    load_committed_funding_table,
)

from grid_data.funding_acquisition import (
    FundingAcquisitionError,
    FundingSeries,
)
from grid_data.funding_publication import ResolvedFundingPublication

FUNDING_PILOT_EVIDENCE_CONTRACT: Final = "grid.phase2-public-funding-pilot/v1"
MINUTE_MS: Final = 60_000
MAX_PILOT_EVENTS: Final = 1_000_000
MAX_PILOT_SERIES: Final = 16
MAX_PILOT_WINDOW_MINUTES: Final = 1_000_000


def _object(path: Path, *, name: str) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FundingAcquisitionError(f"verified {name} cannot be loaded") from error
    if not isinstance(raw, dict):
        raise FundingAcquisitionError(f"verified {name} must be an object")
    return cast(dict[str, object], raw)


def _object_value(parent: dict[str, object], key: str) -> dict[str, object]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise FundingAcquisitionError(f"verified evidence field must be an object: {key}")
    return cast(dict[str, object], value)


def _array(parent: dict[str, object], key: str) -> list[object]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise FundingAcquisitionError(f"verified evidence field must be an array: {key}")
    return cast(list[object], value)


def _integer(parent: dict[str, object], key: str) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FundingAcquisitionError(f"verified evidence field must be non-negative: {key}")
    return value


def _string(parent: dict[str, object], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value:
        raise FundingAcquisitionError(f"verified evidence field must be non-empty text: {key}")
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


def _boundary_times(
    funding_manifest: dict[str, object],
    resolved: ResolvedFundingPublication,
) -> dict[int, int]:
    result: dict[int, int] = {}
    for raw_page in _array(funding_manifest, "pages"):
        if not isinstance(raw_page, dict):
            raise FundingAcquisitionError("verified funding page inventory is invalid")
        page = cast(dict[str, object], raw_page)
        if page.get("scope") != "boundary":
            continue
        sequence = _integer(page, "sequence")
        instrument_id = _integer(page, "instrument_id")
        payload = _object(
            resolved.verified.completed.job_root / "pages" / f"{sequence:08d}.json",
            name="funding boundary page",
        )
        rows = _array(payload, "rows")
        if len(rows) != 1 or not isinstance(rows[0], dict):
            raise FundingAcquisitionError("verified funding boundary must contain one row")
        timestamp = _integer(cast(dict[str, object], rows[0]), "funding_time_ms")
        if instrument_id in result:
            raise FundingAcquisitionError("funding pilot has duplicate boundary evidence")
        result[instrument_id] = timestamp
    return result


def _verified_series(
    funding_plan: dict[str, object],
    funding_manifest: dict[str, object],
    resolved: ResolvedFundingPublication,
) -> tuple[list[dict[str, object]], int, int]:
    raw_spec = _object_value(funding_plan, "spec")
    raw_series = _array(raw_spec, "series")
    if not 1 <= len(raw_series) <= MAX_PILOT_SERIES:
        raise FundingAcquisitionError("pilot series count is outside the bounded evidence contract")
    table = resolved.plan.batch.table
    if not 1 <= table.num_rows <= MAX_PILOT_EVENTS:
        raise FundingAcquisitionError("pilot event count is outside the bounded evidence contract")
    boundary_times = _boundary_times(funding_manifest, resolved)
    summaries: list[dict[str, object]] = []
    total_events = 0
    total_window_minutes = 0
    expected_ids: set[int] = set()
    for item in raw_series:
        if not isinstance(item, dict):
            raise FundingAcquisitionError("verified pilot series entry must be an object")
        try:
            series = FundingSeries(**item)
        except TypeError as error:
            raise FundingAcquisitionError("verified pilot series entry is invalid") from error
        expected_ids.add(series.instrument_id)
        mask = pc.equal(table.column("instrument_id"), series.instrument_id)
        times = cast(
            list[int],
            pc.filter(table.column("funding_time_ms"), mask).to_pylist(),
        )
        intervals = cast(
            list[int],
            pc.filter(table.column("funding_interval_minutes"), mask).to_pylist(),
        )
        boundary = boundary_times.get(series.instrument_id)
        if (
            not times
            or len(times) != len(intervals)
            or boundary is None
            or times != sorted(set(times))
            or times[0] < series.start_ms
            or times[-1] > series.end_ms
            or boundary >= times[0]
            or any(value <= 0 for value in intervals)
            or intervals[0] * MINUTE_MS != times[0] - boundary
            or any(
                interval * MINUTE_MS != right - left
                for (left, right), interval in zip(
                    pairwise(times),
                    intervals[1:],
                    strict=True,
                )
            )
        ):
            raise FundingAcquisitionError(
                "pilot settlement intervals do not derive from predecessor evidence: "
                f"{series.symbol}"
            )
        requested_window_minutes = ((series.end_ms - series.start_ms) // MINUTE_MS) + 1
        summaries.append(
            {
                "end_ms": series.end_ms,
                "instrument_id": series.instrument_id,
                "observed_event_count": len(times),
                "predecessor_bound": True,
                "requested_window_minutes": requested_window_minutes,
                "start_ms": series.start_ms,
                "symbol": series.symbol,
            }
        )
        total_events += len(times)
        total_window_minutes += requested_window_minutes
    observed_ids = set(cast(list[int], table.column("instrument_id").to_pylist()))
    if observed_ids != expected_ids or total_events != table.num_rows:
        raise FundingAcquisitionError("pilot batch contains events outside requested series")
    if set(boundary_times) != expected_ids:
        raise FundingAcquisitionError("pilot boundary inventory differs from requested series")
    if total_window_minutes > MAX_PILOT_WINDOW_MINUTES:
        raise FundingAcquisitionError(
            "pilot requested window is outside the bounded evidence contract"
        )
    return (
        sorted(summaries, key=lambda value: cast(int, value["instrument_id"])),
        total_events,
        total_window_minutes,
    )


def build_funding_pilot_evidence(
    resolved: ResolvedFundingPublication,
    published: PublishedDataset,
    *,
    generated_at_utc: str,
) -> dict[str, object]:
    """Build a receipt-ready summary with no funding rates or observed settlement times."""

    if not resolved.plan.existing_commit:
        raise FundingAcquisitionError("pilot evidence requires an existing immutable commit")
    if published.dataset_root != resolved.plan.paths.dataset_root:
        raise FundingAcquisitionError("verified canonical dataset does not match publication plan")
    if published.manifest.dataset_id != resolved.plan.spec.dataset_id:
        raise FundingAcquisitionError("canonical manifest does not match publication identity")
    if published.manifest.software_identity != resolved.plan.spec.software_identity:
        raise FundingAcquisitionError("canonical manifest software identity does not match")
    if published.manifest.source_evidence_sha256 != resolved.plan.spec.source_evidence_sha256:
        raise FundingAcquisitionError("canonical manifest source evidence does not match")
    if published.manifest.build_config_sha256 != resolved.plan.spec.build_config_sha256:
        raise FundingAcquisitionError("canonical build configuration does not match")

    committed = load_committed_funding_table(published.dataset_root)
    if not resolved.plan.batch.table.equals(committed, check_metadata=True):
        raise FundingAcquisitionError("canonical funding table differs from verified Landing")

    funding_manifest = _object(
        resolved.verified.completed.manifest_path,
        name="funding manifest",
    )
    funding_plan = _object(resolved.verified.completed.plan_path, name="funding plan")
    audit = _object(published.audit_path, name="canonical funding audit")
    series, observed_events, requested_window_minutes = _verified_series(
        funding_plan,
        funding_manifest,
        resolved,
    )
    request_bound = _object_value(funding_manifest, "request_bound")
    source_policy = _object_value(funding_manifest, "source_policy")
    pages = _array(funding_manifest, "pages")
    page_objects: list[dict[str, object]] = []
    for item in pages:
        if not isinstance(item, dict):
            raise FundingAcquisitionError("verified funding page inventory is invalid")
        page_objects.append(cast(dict[str, object], item))
    boundary_page_count = sum(item.get("scope") == "boundary" for item in page_objects)
    range_page_count = sum(item.get("scope") == "range" for item in page_objects)
    actual_http_requests = sum(_integer(item, "attempt_count") for item in page_objects)
    max_attempt_count = max(_integer(item, "attempt_count") for item in page_objects)
    if (
        source_policy.get("endpoint") != "/v5/market/funding/history"
        or source_policy.get("private_credentials_used") is not False
        or source_policy.get("saturated_range_pages_accepted") is not False
        or boundary_page_count != len(series)
        or boundary_page_count + range_page_count != len(page_objects)
        or actual_http_requests != _integer(request_bound, "actual_http_requests")
        or _integer(funding_manifest, "row_count") != observed_events
        or published.manifest.row_count != observed_events
    ):
        raise FundingAcquisitionError("funding Landing facts do not preserve pilot bindings")

    parquet = _object_value(audit, "parquet")
    file_target = _object_value(audit, "file_target")
    if (
        audit.get("layout_contract") != FUNDING_CANONICAL_LAYOUT_ID
        or audit.get("capacity_evidence_sha256") != resolved.verified.capacity_evidence_sha256
        or audit.get("coverage_evidence_sha256") != resolved.verified.completed.manifest_sha256
        or audit.get("boundary_evidence_sha256")
        != resolved.verified.completed.boundary_evidence_sha256
        or audit.get("input_table_sha256") != resolved.plan.input_table_sha256
        or audit.get("request_sha256") != resolved.plan.request_sha256
    ):
        raise FundingAcquisitionError("canonical audit does not preserve funding pilot bindings")

    payload: dict[str, object] = {
        "bindings": {
            "boundary_evidence_sha256": resolved.verified.completed.boundary_evidence_sha256,
            "build_config_sha256": published.manifest.build_config_sha256,
            "canonical_manifest_sha256": published.receipt.manifest_sha256,
            "canonical_request_sha256": resolved.plan.request_sha256,
            "capacity_evidence_sha256": resolved.verified.capacity_evidence_sha256,
            "funding_manifest_sha256": resolved.verified.completed.manifest_sha256,
            "funding_plan_sha256": _string(funding_manifest, "plan_sha256"),
            "funding_request_sha256": _string(funding_manifest, "request_sha256"),
            "input_table_sha256": resolved.plan.input_table_sha256,
            "instrument_registry_sha256": resolved.verified.registry.artifact_sha256,
        },
        "canonical": {
            "bucket_count": BUCKET_COUNT,
            "dataset_id": published.manifest.dataset_id,
            "dataset_type": published.manifest.dataset_type.value,
            "file_count": len(published.manifest.files),
            "funding_rate_arrow_type": str(canonical_funding_schema().field("funding_rate").type),
            "funding_rate_scale": FUNDING_RATE_SCALE,
            "instrument_count": published.manifest.instrument_count,
            "manifest_sha256": published.receipt.manifest_sha256,
            "parquet_bytes": sum(item.size_bytes for item in published.manifest.files),
            "row_count": published.manifest.row_count,
            "row_group_count": _integer(parquet, "row_group_count"),
            "schema_version": published.manifest.schema_version,
            "semantic_version": published.manifest.semantic_version,
            "single_file_classification": _string(file_target, "classification"),
        },
        "evidence_schema": FUNDING_PILOT_EVIDENCE_CONTRACT,
        "generated_at_utc": _generated_at(generated_at_utc),
        "limitations": [
            f"This is a bounded {len(series)}-series, {requested_window_minutes}-minute-window "
            "pilot and is not a full funding-history campaign.",
            "Observed funding events are source returns inside the requested windows; this proof "
            "does not establish complete historical settlement chronology.",
            "Historical lifecycle coverage, funding gap classification, repair, compaction, and "
            "catalog selection remain pending.",
            "One small tail Parquet file does not qualify target-file attainment or scale "
            "behavior.",
            "This evidence does not close Gate 2 or authorize any private or live operation.",
        ],
        "publication": {
            "existing_commit_verified": True,
            "exact_physical_contract": FUNDING_EXACT_PHYSICAL_CONTRACT,
            "layout_contract": FUNDING_CANONICAL_LAYOUT_ID,
            "parquet_compression": COMPRESSION,
            "parquet_compression_level": COMPRESSION_LEVEL,
            "software_identity": published.manifest.software_identity,
            "target_file_size_bytes": TARGET_FILE_SIZE_BYTES,
        },
        "quality": {
            "canonical_receipt_verified": True,
            "exact_landing_canonical_table_equality": True,
            "funding_rates_exact_decimal128": True,
            "internal_intervals_recomputed": True,
            "predecessor_intervals_recomputed": True,
            "sorted_unique_keys_verified": True,
        },
        "scope": {
            "category": "linear",
            "observed_event_count": observed_events,
            "requested_window_minutes": requested_window_minutes,
            "series": series,
        },
        "source": {
            "actual_http_requests": actual_http_requests,
            "authentication": "none",
            "base_url": "https://api.bybit.com",
            "boundary_page_count": boundary_page_count,
            "endpoint": source_policy["endpoint"],
            "max_attempt_count_observed": max_attempt_count,
            "max_attempts_per_page": _integer(request_bound, "max_attempts_per_page"),
            "page_count": len(page_objects),
            "page_limit": _integer(source_policy, "page_limit"),
            "page_span_minutes": _integer(source_policy, "page_span_minutes"),
            "private_endpoints_called": False,
            "range_page_count": range_page_count,
            "saturated_range_pages_accepted": False,
            "target_rps": _integer(request_bound, "target_rps"),
            "workers": _integer(request_bound, "workers"),
        },
        "status": "verified-canonical-funding-publication",
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_funding_rates": False,
            "evidence_contains_local_paths": False,
            "evidence_contains_observed_settlement_timestamps": False,
            "runtime_market_artifacts_committed_to_git": False,
            "runtime_market_dataset_receipt_verified": True,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload
