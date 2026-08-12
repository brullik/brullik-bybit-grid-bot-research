"""Sanitized GitHub-safe evidence for one verified Phase 2 public 1m pilot."""

from __future__ import annotations

import json
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Final, cast

import pyarrow.compute as pc  # type: ignore[import-untyped]
from grid_contracts.canonical import canonical_sha256
from grid_market_store import (
    CANONICAL_LAYOUT_ID,
    COMPRESSION,
    COMPRESSION_LEVEL,
    TARGET_FILE_SIZE_BYTES,
    PublishedDataset,
)

from grid_data.history_acquisition import HistoryAcquisitionError, HistorySeries
from grid_data.history_publication import ResolvedHistoryPublication

PILOT_EVIDENCE_CONTRACT: Final = "grid.phase2-public-1m-pilot/v1"
MINUTE_MS: Final = 60_000
MAX_PILOT_ROWS: Final = 1_000_000
MAX_PILOT_SERIES: Final = 16


def _object(path: Path, *, name: str) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryAcquisitionError(f"verified {name} cannot be loaded") from error
    if not isinstance(raw, dict):
        raise HistoryAcquisitionError(f"verified {name} must be an object")
    return cast(dict[str, object], raw)


def _object_value(parent: dict[str, object], key: str) -> dict[str, object]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise HistoryAcquisitionError(f"verified evidence field must be an object: {key}")
    return cast(dict[str, object], value)


def _integer(parent: dict[str, object], key: str) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HistoryAcquisitionError(f"verified evidence field must be non-negative: {key}")
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


def _verified_series(
    plan: dict[str, object],
    resolved: ResolvedHistoryPublication,
) -> tuple[list[dict[str, object]], int]:
    raw_spec = _object_value(plan, "spec")
    raw_series = raw_spec.get("series")
    if not isinstance(raw_series, list) or not 1 <= len(raw_series) <= MAX_PILOT_SERIES:
        raise HistoryAcquisitionError("pilot series count is outside the bounded evidence contract")
    table = resolved.plan.batch.table
    if not 1 <= table.num_rows <= MAX_PILOT_ROWS:
        raise HistoryAcquisitionError("pilot row count is outside the bounded evidence contract")
    summaries: list[dict[str, object]] = []
    expected_total = 0
    for item in raw_series:
        if not isinstance(item, dict):
            raise HistoryAcquisitionError("verified pilot series entry must be an object")
        try:
            series = HistorySeries(**item)
        except TypeError as error:
            raise HistoryAcquisitionError("verified pilot series entry is invalid") from error
        expected = ((series.end_ms - series.start_ms) // MINUTE_MS) + 1
        mask = pc.equal(table.column("instrument_id"), series.instrument_id)
        times = cast(list[int], pc.filter(table.column("open_time_ms"), mask).to_pylist())
        if (
            len(times) != expected
            or not times
            or times[0] != series.start_ms
            or times[-1] != series.end_ms
            or any(right - left != MINUTE_MS for left, right in pairwise(times))
        ):
            raise HistoryAcquisitionError(
                f"pilot series is not complete at exact 1m intervals: {series.symbol}"
            )
        summaries.append(
            {
                "end_ms": series.end_ms,
                "instrument_id": series.instrument_id,
                "requested_minute_count": expected,
                "start_ms": series.start_ms,
                "symbol": series.symbol,
            }
        )
        expected_total += expected
    if expected_total != table.num_rows:
        raise HistoryAcquisitionError("pilot batch contains rows outside requested series")
    return sorted(summaries, key=lambda value: cast(int, value["instrument_id"])), expected_total


def build_history_pilot_evidence(
    resolved: ResolvedHistoryPublication,
    published: PublishedDataset,
    *,
    generated_at_utc: str,
) -> dict[str, object]:
    """Build a receipt-ready summary with hashes and counts, never candle market values."""

    if not resolved.plan.existing_commit:
        raise HistoryAcquisitionError("pilot evidence requires an existing immutable commit")
    if published.dataset_root != resolved.plan.paths.dataset_root:
        raise HistoryAcquisitionError("verified canonical dataset does not match publication plan")
    if published.manifest.dataset_id != resolved.plan.spec.dataset_id:
        raise HistoryAcquisitionError("canonical manifest does not match publication identity")
    if published.manifest.software_identity != resolved.plan.spec.software_identity:
        raise HistoryAcquisitionError("canonical manifest software identity does not match")
    if published.manifest.source_evidence_sha256 != resolved.plan.spec.source_evidence_sha256:
        raise HistoryAcquisitionError("canonical manifest source evidence does not match")
    if published.manifest.build_config_sha256 != resolved.plan.spec.build_config_sha256:
        raise HistoryAcquisitionError("canonical build configuration does not match")

    history_manifest = _object(
        resolved.completed_history.manifest_path,
        name="history manifest",
    )
    history_plan = _object(resolved.completed_history.plan_path, name="history plan")
    audit = _object(published.audit_path, name="canonical audit")
    series, requested_minutes = _verified_series(history_plan, resolved)
    request_bound = _object_value(history_manifest, "request_bound")
    source_policy = _object_value(history_manifest, "source_policy")
    if source_policy.get("tick_rows_requested") is not False:
        raise HistoryAcquisitionError("pilot evidence requires a no-tick source policy")
    if (
        audit.get("layout_contract") != CANONICAL_LAYOUT_ID
        or audit.get("capacity_evidence_sha256") != resolved.capacity_evidence_sha256
        or audit.get("coverage_evidence_sha256") != resolved.completed_history.manifest_sha256
        or audit.get("input_table_sha256") != resolved.plan.input_table_sha256
        or audit.get("request_sha256") != resolved.plan.request_sha256
    ):
        raise HistoryAcquisitionError("canonical audit does not preserve pilot evidence bindings")
    if _integer(history_manifest, "row_count") != requested_minutes:
        raise HistoryAcquisitionError("Landing row count does not prove exact requested coverage")
    if published.manifest.row_count != requested_minutes:
        raise HistoryAcquisitionError("canonical row count does not preserve requested coverage")

    payload: dict[str, object] = {
        "bindings": {
            "build_config_sha256": published.manifest.build_config_sha256,
            "capacity_evidence_sha256": resolved.capacity_evidence_sha256,
            "coverage_evidence_sha256": resolved.completed_history.manifest_sha256,
            "instrument_registry_sha256": resolved.instrument_registry.artifact_sha256,
            "input_table_sha256": resolved.plan.input_table_sha256,
        },
        "canonical": {
            "dataset_id": published.manifest.dataset_id,
            "dataset_type": published.manifest.dataset_type.value,
            "file_count": len(published.manifest.files),
            "instrument_count": published.manifest.instrument_count,
            "manifest_sha256": published.receipt.manifest_sha256,
            "max_time_ms": published.manifest.max_time_ms,
            "min_time_ms": published.manifest.min_time_ms,
            "parquet_bytes": sum(item.size_bytes for item in published.manifest.files),
            "row_count": published.manifest.row_count,
            "schema_version": published.manifest.schema_version,
            "semantic_version": published.manifest.semantic_version,
        },
        "evidence_schema": PILOT_EVIDENCE_CONTRACT,
        "generated_at_utc": _generated_at(generated_at_utc),
        "landing": {
            "actual_http_requests": _integer(request_bound, "actual_http_requests"),
            "contract": history_manifest.get("contract"),
            "empty_page_count": _integer(history_manifest, "empty_page_count"),
            "manifest_sha256": resolved.completed_history.manifest_sha256,
            "page_count": resolved.completed_history.page_count,
            "request_sha256": history_manifest.get("request_sha256"),
            "returned_row_count": resolved.completed_history.row_count,
            "target_rps": _integer(request_bound, "target_rps"),
            "workers": _integer(request_bound, "workers"),
        },
        "limitations": [
            f"This is a bounded {len(series)}-series, {requested_minutes}-minute pilot and is "
            "not a full-history campaign.",
            "Exact coverage applies only to the requested series ranges; lifecycle discovery "
            "and gap reason classification remain pending.",
            "One tail Parquet file does not qualify target-file attainment or compaction behavior.",
            "This evidence does not close Gate 2 or authorize any private or live operation.",
        ],
        "publication": {
            "existing_commit_verified": True,
            "layout_contract": CANONICAL_LAYOUT_ID,
            "parquet_compression": COMPRESSION,
            "parquet_compression_level": COMPRESSION_LEVEL,
            "software_identity": published.manifest.software_identity,
            "target_file_size_bytes": TARGET_FILE_SIZE_BYTES,
        },
        "scope": {
            "category": "linear",
            "exact_requested_coverage": True,
            "interval_minutes": 1,
            "requested_minute_count": requested_minutes,
            "series": series,
        },
        "source_policy": {
            "authentication": "none",
            "base_url": "https://api.bybit.com",
            "endpoint": source_policy.get("trade")
            if published.manifest.dataset_type.value == "trade_kline_1m"
            else source_policy.get("mark"),
            "private_endpoints_called": False,
            "tick_rows_requested": False,
        },
        "status": "verified-canonical-publication",
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_market_values": False,
            "runtime_market_artifacts_committed_to_git": False,
            "runtime_market_dataset_receipt_verified": True,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload
