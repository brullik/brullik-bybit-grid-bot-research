"""Fail-closed source-parity and requested-range audit for canonical 1m datasets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, cast

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.compute as pc  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from grid_contracts.canonical import canonical_sha256
from grid_market_store import PublishedDataset, verify_committed_candle_dataset

from grid_data.history_acquisition import HistoryAcquisitionError, HistorySeries
from grid_data.history_publication import (
    SOFTWARE_IDENTITY_RE,
    VerifiedHistoryPublicationInput,
    history_publication_spec,
    load_verified_history_publication_input,
)

COVERAGE_AUDIT_CONTRACT: Final = "grid.canonical-1m-coverage-audit/v1"
MINUTE_MS: Final = 60_000
MAX_GAP_EXAMPLES: Final = 20


@dataclass(frozen=True, slots=True)
class CoverageAudit:
    payload: dict[str, object]
    passed: bool
    gap_ranges: tuple[dict[str, object], ...]


def _object(path: Path, *, name: str) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryAcquisitionError(f"verified {name} cannot be loaded") from error
    if not isinstance(raw, dict):
        raise HistoryAcquisitionError(f"verified {name} must be an object")
    return cast(dict[str, object], raw)


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


def _series(plan: dict[str, object]) -> tuple[HistorySeries, ...]:
    raw_spec = plan.get("spec")
    if not isinstance(raw_spec, dict) or not isinstance(raw_spec.get("series"), list):
        raise HistoryAcquisitionError("verified history plan has no series inventory")
    try:
        return tuple(HistorySeries(**item) for item in raw_spec["series"])
    except (TypeError, AttributeError) as error:
        raise HistoryAcquisitionError("verified history series inventory is invalid") from error


def _gap_ranges(
    times: list[int],
    *,
    start_ms: int,
    end_ms: int,
) -> list[dict[str, int]]:
    gaps: list[dict[str, int]] = []
    cursor = start_ms
    for observed in times:
        if observed < start_ms or observed > end_ms:
            continue
        if observed > cursor:
            gap_end = observed - MINUTE_MS
            gaps.append(
                {
                    "end_ms": gap_end,
                    "minute_count": ((gap_end - cursor) // MINUTE_MS) + 1,
                    "start_ms": cursor,
                }
            )
        cursor = max(cursor, observed + MINUTE_MS)
    if cursor <= end_ms:
        gaps.append(
            {
                "end_ms": end_ms,
                "minute_count": ((end_ms - cursor) // MINUTE_MS) + 1,
                "start_ms": cursor,
            }
        )
    return gaps


def _canonical_table(published: PublishedDataset) -> pa.Table:
    tables = [
        pq.read_table(published.dataset_root / item.path) for item in published.manifest.files
    ]
    if not tables:
        raise HistoryAcquisitionError("canonical dataset has no Parquet tables")
    return pa.concat_tables(tables) if len(tables) > 1 else tables[0]


def _verify_publication_identity(
    verified: VerifiedHistoryPublicationInput,
    published: PublishedDataset,
    *,
    publisher_software_identity: str,
) -> None:
    expected = history_publication_spec(
        verified,
        software_identity=publisher_software_identity,
    )
    manifest = published.manifest
    if (
        manifest.dataset_id != expected.dataset_id
        or manifest.semantic_version != expected.semantic_version
        or manifest.parent_dataset_ids != expected.parent_dataset_ids
        or manifest.source_evidence_sha256 != expected.source_evidence_sha256
        or manifest.build_config_sha256 != expected.build_config_sha256
        or manifest.software_identity != expected.software_identity
    ):
        raise HistoryAcquisitionError(
            "canonical manifest does not match the verified history publication identity"
        )
    audit = _object(published.audit_path, name="canonical audit")
    if (
        audit.get("capacity_evidence_sha256") != expected.capacity_evidence_sha256
        or audit.get("coverage_evidence_sha256") != expected.coverage_evidence_sha256
    ):
        raise HistoryAcquisitionError("canonical audit does not match upstream evidence bindings")


def build_completed_history_coverage_audit(
    job_root: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    store_root: Path,
    *,
    publisher_software_identity: str,
    audit_software_identity: str,
    generated_at_utc: str,
) -> CoverageAudit:
    """Audit exact source parity and requested 1m coverage without mutating market storage."""

    if not SOFTWARE_IDENTITY_RE.fullmatch(audit_software_identity):
        raise HistoryAcquisitionError(
            "audit_software_identity must be git:<40-character-lowercase-commit-sha>"
        )
    verified = load_verified_history_publication_input(
        job_root,
        instrument_registry_path,
        capacity_evidence_path,
    )
    dataset_root = store_root.resolve() / "datasets" / verified.dataset_id
    published = verify_committed_candle_dataset(dataset_root)
    _verify_publication_identity(
        verified,
        published,
        publisher_software_identity=publisher_software_identity,
    )
    canonical = _canonical_table(published)
    source_parity = canonical.equals(verified.batch.table)
    plan = _object(verified.completed_history.plan_path, name="history plan")
    registry_by_id = {
        snapshot.instrument_id: snapshot for snapshot in verified.instrument_registry.snapshots
    }

    summaries: list[dict[str, object]] = []
    all_ranges: list[dict[str, object]] = []
    expected_total = 0
    observed_total = 0
    missing_total = 0
    duplicate_total = 0
    unexpected_total = 0
    for series in _series(plan):
        mask = pc.equal(canonical.column("instrument_id"), series.instrument_id)
        raw_times = cast(list[int], pc.filter(canonical.column("open_time_ms"), mask).to_pylist())
        times = sorted(raw_times)
        unique_times = sorted(set(times))
        in_range = [value for value in unique_times if series.start_ms <= value <= series.end_ms]
        expected = ((series.end_ms - series.start_ms) // MINUTE_MS) + 1
        gaps = _gap_ranges(in_range, start_ms=series.start_ms, end_ms=series.end_ms)
        missing = sum(item["minute_count"] for item in gaps)
        duplicates = len(times) - len(unique_times)
        unexpected = len(unique_times) - len(in_range)
        snapshot = registry_by_id.get(series.instrument_id)
        if snapshot is None:
            raise HistoryAcquisitionError("audited instrument is absent from verified registry")
        within_lifecycle = series.start_ms >= snapshot.launch_time_ms and (
            snapshot.delivery_time_ms is None or series.end_ms <= snapshot.delivery_time_ms
        )
        ranges_with_identity: list[dict[str, object]] = [
            {"instrument_id": series.instrument_id, **item} for item in gaps
        ]
        all_ranges.extend(ranges_with_identity)
        summaries.append(
            {
                "duplicate_key_count": duplicates,
                "end_ms": series.end_ms,
                "expected_minute_count": expected,
                "gap_range_count": len(gaps),
                "instrument_id": series.instrument_id,
                "missing_minute_count": missing,
                "observed_row_count": len(times),
                "start_ms": series.start_ms,
                "symbol": series.symbol,
                "unexpected_timestamp_count": unexpected,
                "within_registry_lifecycle_bounds": within_lifecycle,
            }
        )
        expected_total += expected
        observed_total += len(times)
        missing_total += missing
        duplicate_total += duplicates
        unexpected_total += unexpected

    gap_examples = all_ranges[:MAX_GAP_EXAMPLES]
    unrequested_rows = canonical.num_rows - observed_total
    lifecycle_failures = sum(
        not cast(bool, item["within_registry_lifecycle_bounds"]) for item in summaries
    )
    passed = bool(
        source_parity
        and observed_total == canonical.num_rows == expected_total
        and missing_total == 0
        and duplicate_total == 0
        and unexpected_total == 0
        and unrequested_rows == 0
        and lifecycle_failures == 0
    )
    payload: dict[str, object] = {
        "audit_software_identity": audit_software_identity,
        "bindings": {
            "canonical_manifest_sha256": published.receipt.manifest_sha256,
            "capacity_evidence_sha256": verified.capacity_evidence_sha256,
            "history_manifest_sha256": verified.completed_history.manifest_sha256,
            "instrument_registry_sha256": verified.instrument_registry.artifact_sha256,
            "publisher_software_identity": published.manifest.software_identity,
        },
        "contract": COVERAGE_AUDIT_CONTRACT,
        "dataset_id": published.manifest.dataset_id,
        "dataset_type": published.manifest.dataset_type.value,
        "generated_at_utc": _generated_at(generated_at_utc),
        "gap_evidence": {
            "gap_range_count": len(all_ranges),
            "gap_ranges_sha256": canonical_sha256(all_ranges),
            "sample_limit": MAX_GAP_EXAMPLES,
            "sample_ranges": gap_examples,
            "sample_truncated": len(all_ranges) > MAX_GAP_EXAMPLES,
        },
        "limitations": [
            "Coverage is evaluated only inside the explicitly requested series ranges.",
            "Current registry lifecycle bounds do not prove a complete dated historical universe.",
            "REST-returned gaps remain unaccepted and block completion until a separate policy "
            "or repair resolves them.",
            "This audit does not repair data, compact files, register a catalog entry, or close "
            "Gate 2.",
        ],
        "quality": {
            "canonical_source_table_equal": source_parity,
            "conflicting_key_count": 0,
            "duplicate_key_count": duplicate_total,
            "expected_minute_count": expected_total,
            "lifecycle_failure_count": lifecycle_failures,
            "missing_minute_count": missing_total,
            "observed_row_count": observed_total,
            "unrequested_row_count": unrequested_rows,
            "unexpected_timestamp_count": unexpected_total,
        },
        "reason_policy": {
            "accepted_reason_codes": [],
            "observed_reason_counts": (
                {"rest_returned_no_data": missing_total} if missing_total else {}
            ),
            "unaccepted_reason_codes": ["rest_returned_no_data"] if missing_total else [],
            "unknown_reason_count": 0,
        },
        "series": summaries,
        "status": "passed" if passed else "blocked",
        "storage_policy": {
            "account_data_included": False,
            "market_values_included": False,
            "runtime_paths_included": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return CoverageAudit(payload=payload, passed=passed, gap_ranges=tuple(all_ranges))
