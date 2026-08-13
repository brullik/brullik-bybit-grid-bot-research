"""Fail-closed source-parity and chronology audit for canonical funding data."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Final, cast

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.compute as pc  # type: ignore[import-untyped]
from grid_contracts.canonical import canonical_sha256
from grid_market_store import (
    PublishedDataset,
    load_committed_funding_table,
    verify_committed_funding_dataset,
)

from grid_data.funding_acquisition import FundingAcquisitionError, FundingSeries
from grid_data.funding_publication import (
    SOFTWARE_IDENTITY_RE,
    VerifiedFundingPublicationInput,
    funding_publication_spec,
    load_verified_funding_publication_input,
)

FUNDING_COVERAGE_AUDIT_CONTRACT: Final = "grid.canonical-funding-coverage-audit/v1"
MINUTE_MS: Final = 60_000
MAX_SERIES: Final = 700


@dataclass(frozen=True, slots=True)
class FundingCoverageAudit:
    payload: dict[str, object]
    passed: bool
    anomaly_records: tuple[dict[str, object], ...]


def _object(path: Path, *, name: str) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FundingAcquisitionError(f"verified {name} cannot be loaded") from error
    if not isinstance(raw, dict):
        raise FundingAcquisitionError(f"verified {name} must be an object")
    return cast(dict[str, object], raw)


def _array(parent: dict[str, object], key: str) -> list[object]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise FundingAcquisitionError(f"verified audit field must be an array: {key}")
    return cast(list[object], value)


def _integer(parent: dict[str, object], key: str) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FundingAcquisitionError(f"verified audit field must be non-negative: {key}")
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


def _series(plan: dict[str, object]) -> tuple[FundingSeries, ...]:
    raw_spec = plan.get("spec")
    if not isinstance(raw_spec, dict) or not isinstance(raw_spec.get("series"), list):
        raise FundingAcquisitionError("verified funding plan has no series inventory")
    raw_series = cast(list[object], raw_spec["series"])
    if not 1 <= len(raw_series) <= MAX_SERIES or any(
        not isinstance(item, dict) for item in raw_series
    ):
        raise FundingAcquisitionError("verified funding series inventory is invalid")
    try:
        return tuple(
            FundingSeries(**cast(dict[str, object], item))  # type: ignore[arg-type]
            for item in raw_series
        )
    except TypeError as error:
        raise FundingAcquisitionError("verified funding series inventory is invalid") from error


def _page_inventory(manifest: dict[str, object]) -> tuple[dict[str, object], ...]:
    result: list[dict[str, object]] = []
    for item in _array(manifest, "pages"):
        if not isinstance(item, dict):
            raise FundingAcquisitionError("verified funding page inventory is invalid")
        result.append(cast(dict[str, object], item))
    return tuple(result)


def _boundary_timestamp(job_root: Path, page: dict[str, object]) -> int:
    sequence = _integer(page, "sequence")
    payload = _object(
        job_root / "pages" / f"{sequence:08d}.json",
        name="funding boundary page",
    )
    rows = _array(payload, "rows")
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise FundingAcquisitionError("verified funding boundary must contain one row")
    return _integer(cast(dict[str, object], rows[0]), "funding_time_ms")


def _range_tiling(
    pages: list[dict[str, object]],
    series: FundingSeries,
) -> tuple[int, int]:
    ordered = sorted(pages, key=lambda item: _integer(item, "start_ms"))
    if not ordered:
        raise FundingAcquisitionError("funding audit requires at least one range page per series")
    cursor = series.start_ms
    window_minutes = 0
    empty_pages = 0
    for page in ordered:
        start_ms = _integer(page, "start_ms")
        end_ms = _integer(page, "end_ms")
        if start_ms != cursor or end_ms < start_ms or end_ms > series.end_ms:
            raise FundingAcquisitionError("funding range pages do not tile the requested window")
        window_minutes += ((end_ms - start_ms) // MINUTE_MS) + 1
        empty_pages += _integer(page, "row_count") == 0
        cursor = end_ms + MINUTE_MS
    if cursor != series.end_ms + MINUTE_MS:
        raise FundingAcquisitionError("funding range pages do not cover the requested end")
    return window_minutes, empty_pages


def _verify_publication_identity(
    verified: VerifiedFundingPublicationInput,
    published: PublishedDataset,
    *,
    publisher_software_identity: str,
) -> None:
    expected = funding_publication_spec(
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
        raise FundingAcquisitionError(
            "canonical manifest does not match verified funding publication identity"
        )
    audit = _object(published.audit_path, name="canonical funding audit")
    if (
        audit.get("capacity_evidence_sha256") != expected.capacity_evidence_sha256
        or audit.get("coverage_evidence_sha256") != expected.coverage_evidence_sha256
        or audit.get("boundary_evidence_sha256") != expected.boundary_evidence_sha256
    ):
        raise FundingAcquisitionError(
            "canonical funding audit does not match upstream evidence bindings"
        )


def _reason_policy(counts: dict[str, int]) -> dict[str, object]:
    observed = {key: value for key, value in sorted(counts.items()) if value}
    return {
        "accepted_reason_codes": [],
        "observed_reason_counts": observed,
        "unaccepted_reason_codes": sorted(observed),
        "unknown_reason_count": 0,
    }


def _build_funding_coverage_audit(
    verified: VerifiedFundingPublicationInput,
    committed: PublishedDataset,
    source_table: pa.Table,
    *,
    contract: str,
    bindings: dict[str, object],
    limitations: list[str],
    storage_policy: dict[str, object],
    audit_software_identity: str,
    generated_at_utc: str,
) -> FundingCoverageAudit:
    """Apply the shared exact chronology audit to one verified source-table projection."""

    if not SOFTWARE_IDENTITY_RE.fullmatch(audit_software_identity):
        raise FundingAcquisitionError(
            "audit_software_identity must be git:<40-character-lowercase-commit-sha>"
        )
    canonical = load_committed_funding_table(committed.dataset_root)
    source_parity = canonical.equals(source_table, check_metadata=True)
    plan = _object(verified.completed.plan_path, name="funding plan")
    manifest = _object(verified.completed.manifest_path, name="funding manifest")
    pages = _page_inventory(manifest)
    source_policy = manifest.get("source_policy")
    if not isinstance(source_policy, dict) or (
        source_policy.get("endpoint") != "/v5/market/funding/history"
        or source_policy.get("private_credentials_used") is not False
        or source_policy.get("saturated_range_pages_accepted") is not False
    ):
        raise FundingAcquisitionError("funding audit requires public unsaturated source policy")

    registry_by_id = {snapshot.instrument_id: snapshot for snapshot in verified.registry.snapshots}
    summaries: list[dict[str, object]] = []
    anomalies: list[dict[str, object]] = []
    observed_total = 0
    requested_window_total = 0
    range_page_total = 0
    boundary_page_total = 0
    empty_page_total = 0
    duplicate_total = 0
    unexpected_total = 0
    boundary_mismatch_total = 0
    internal_mismatch_total = 0
    interval_change_total = 0
    lifecycle_failure_total = 0
    expected_ids: set[int] = set()

    for series in _series(plan):
        expected_ids.add(series.instrument_id)
        series_pages = [
            item for item in pages if _integer(item, "instrument_id") == series.instrument_id
        ]
        boundary_pages = [item for item in series_pages if item.get("scope") == "boundary"]
        range_pages = [item for item in series_pages if item.get("scope") == "range"]
        if len(boundary_pages) != 1 or len(boundary_pages) + len(range_pages) != len(series_pages):
            raise FundingAcquisitionError("funding page scopes do not match requested series")
        window_minutes, empty_pages = _range_tiling(range_pages, series)
        boundary_time = _boundary_timestamp(verified.completed.job_root, boundary_pages[0])

        mask = pc.equal(canonical.column("instrument_id"), series.instrument_id)
        raw_times = cast(
            list[int],
            pc.filter(canonical.column("funding_time_ms"), mask).to_pylist(),
        )
        raw_intervals = cast(
            list[int],
            pc.filter(canonical.column("funding_interval_minutes"), mask).to_pylist(),
        )
        if len(raw_times) != len(raw_intervals):
            raise FundingAcquisitionError("canonical funding time/interval columns differ")
        pairs = sorted(zip(raw_times, raw_intervals, strict=True))
        times = [item[0] for item in pairs]
        intervals = [item[1] for item in pairs]
        unique_times = set(times)
        duplicates = len(times) - len(unique_times)
        unexpected = sum(not series.start_ms <= value <= series.end_ms for value in unique_times)
        boundary_mismatches = int(
            not times
            or boundary_time >= times[0]
            or intervals[0] * MINUTE_MS != times[0] - boundary_time
        )
        internal_mismatches = sum(
            interval * MINUTE_MS != right - left
            for (left, right), interval in zip(
                pairwise(times),
                intervals[1:],
                strict=True,
            )
        )
        interval_changes = sum(left != right for left, right in pairwise(intervals))
        histogram = [
            {"event_count": count, "interval_minutes": interval}
            for interval, count in sorted(Counter(intervals).items())
        ]
        snapshot = registry_by_id.get(series.instrument_id)
        if snapshot is None:
            raise FundingAcquisitionError("audited funding instrument is absent from registry")
        within_lifecycle = series.start_ms >= snapshot.launch_time_ms and (
            snapshot.delivery_time_ms is None or series.end_ms <= snapshot.delivery_time_ms
        )

        for page in range_pages:
            if _integer(page, "row_count") == 0:
                anomalies.append(
                    {
                        "end_ms": _integer(page, "end_ms"),
                        "instrument_id": series.instrument_id,
                        "reason": "source_window_returned_no_event",
                        "start_ms": _integer(page, "start_ms"),
                    }
                )
        if boundary_mismatches:
            anomalies.append(
                {
                    "instrument_id": series.instrument_id,
                    "reason": "predecessor_interval_mismatch",
                }
            )
        for index, ((left, right), interval) in enumerate(
            zip(pairwise(times), intervals[1:], strict=True),
            start=1,
        ):
            if interval * MINUTE_MS != right - left:
                anomalies.append(
                    {
                        "index": index,
                        "instrument_id": series.instrument_id,
                        "reason": "internal_interval_mismatch",
                    }
                )
        for index, (left, right) in enumerate(pairwise(intervals), start=1):
            if left != right:
                anomalies.append(
                    {
                        "index": index,
                        "instrument_id": series.instrument_id,
                        "reason": "unexplained_interval_change",
                    }
                )

        summaries.append(
            {
                "boundary_page_count": len(boundary_pages),
                "duplicate_key_count": duplicates,
                "empty_range_page_count": empty_pages,
                "end_ms": series.end_ms,
                "instrument_id": series.instrument_id,
                "internal_interval_mismatch_count": internal_mismatches,
                "interval_change_count": interval_changes,
                "interval_histogram": histogram,
                "observed_event_count": len(times),
                "predecessor_interval_mismatch_count": boundary_mismatches,
                "range_page_count": len(range_pages),
                "requested_window_minutes": window_minutes,
                "stable_observed_interval_minutes": intervals[0]
                if len(set(intervals)) == 1
                else None,
                "start_ms": series.start_ms,
                "symbol": series.symbol,
                "unexpected_timestamp_count": unexpected,
                "within_registry_lifecycle_bounds": within_lifecycle,
            }
        )
        observed_total += len(times)
        requested_window_total += window_minutes
        range_page_total += len(range_pages)
        boundary_page_total += len(boundary_pages)
        empty_page_total += empty_pages
        duplicate_total += duplicates
        unexpected_total += unexpected
        boundary_mismatch_total += boundary_mismatches
        internal_mismatch_total += internal_mismatches
        interval_change_total += interval_changes
        lifecycle_failure_total += int(not within_lifecycle)

    observed_identifiers = cast(list[int], canonical.column("instrument_id").to_pylist())
    observed_ids = set(observed_identifiers)
    unrequested_rows = sum(identifier not in expected_ids for identifier in observed_identifiers)
    reason_counts = {
        "canonical_source_mismatch": int(not source_parity),
        "duplicate_canonical_key": duplicate_total,
        "internal_interval_mismatch": internal_mismatch_total,
        "predecessor_interval_mismatch": boundary_mismatch_total,
        "registry_lifecycle_failure": lifecycle_failure_total,
        "source_window_returned_no_event": empty_page_total,
        "unexpected_settlement_timestamp": unexpected_total,
        "unexplained_interval_change": interval_change_total,
        "unrequested_instrument_row": unrequested_rows,
    }
    passed = bool(
        source_parity
        and observed_ids == expected_ids
        and observed_total == canonical.num_rows
        and unrequested_rows == 0
        and duplicate_total == 0
        and unexpected_total == 0
        and boundary_mismatch_total == 0
        and internal_mismatch_total == 0
        and interval_change_total == 0
        and empty_page_total == 0
        and lifecycle_failure_total == 0
    )
    payload: dict[str, object] = {
        "audit_software_identity": audit_software_identity,
        "bindings": bindings,
        "chronology_anomaly_evidence": {
            "anomaly_count": len(anomalies),
            "anomaly_records_sha256": canonical_sha256(anomalies),
        },
        "contract": contract,
        "coverage_basis": {
            "current_instrument_interval_used": False,
            "empty_range_windows_accepted": False,
            "endpoint": "/v5/market/funding/history",
            "historical_interval_evidence": "predecessor-and-adjacent-settlements",
            "interval_changes_accepted_without_dated_evidence": False,
            "range_pages_have_explicit_bounds": True,
            "saturated_range_pages_accepted": False,
        },
        "dataset_id": committed.manifest.dataset_id,
        "dataset_type": committed.manifest.dataset_type.value,
        "generated_at_utc": _generated_at(generated_at_utc),
        "limitations": limitations,
        "quality": {
            "boundary_page_count": boundary_page_total,
            "canonical_source_table_equal": source_parity,
            "conflicting_key_count": 0,
            "duplicate_key_count": duplicate_total,
            "empty_range_page_count": empty_page_total,
            "internal_interval_mismatch_count": internal_mismatch_total,
            "interval_change_count": interval_change_total,
            "lifecycle_failure_count": lifecycle_failure_total,
            "observed_event_count": observed_total,
            "predecessor_interval_mismatch_count": boundary_mismatch_total,
            "range_page_count": range_page_total,
            "requested_window_minutes": requested_window_total,
            "source_range_enumeration_complete": passed,
            "unrequested_row_count": unrequested_rows,
            "unexpected_timestamp_count": unexpected_total,
        },
        "reason_policy": _reason_policy(reason_counts),
        "series": summaries,
        "status": "passed" if passed else "blocked",
        "storage_policy": storage_policy,
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return FundingCoverageAudit(
        payload=payload,
        passed=passed,
        anomaly_records=tuple(anomalies),
    )


def build_verified_funding_coverage_audit(
    verified: VerifiedFundingPublicationInput,
    committed: PublishedDataset,
    source_table: pa.Table,
    *,
    contract: str,
    bindings: dict[str, object],
    limitations: list[str],
    storage_policy: dict[str, object],
    audit_software_identity: str,
    generated_at_utc: str,
) -> FundingCoverageAudit:
    """Audit a separately verified funding publication/source projection."""

    return _build_funding_coverage_audit(
        verified,
        committed,
        source_table,
        contract=contract,
        bindings=bindings,
        limitations=limitations,
        storage_policy=storage_policy,
        audit_software_identity=audit_software_identity,
        generated_at_utc=generated_at_utc,
    )


def build_completed_funding_coverage_audit(
    job_root: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    store_root: Path,
    *,
    publisher_software_identity: str,
    audit_software_identity: str,
    generated_at_utc: str,
) -> FundingCoverageAudit:
    """Audit exact source parity and stable source chronology without current interval metadata."""

    verified = load_verified_funding_publication_input(
        job_root,
        instrument_registry_path,
        capacity_evidence_path,
    )
    dataset_root = store_root.resolve() / "datasets" / verified.dataset_id
    committed = verify_committed_funding_dataset(dataset_root)
    _verify_publication_identity(
        verified,
        committed,
        publisher_software_identity=publisher_software_identity,
    )
    return _build_funding_coverage_audit(
        verified,
        committed,
        verified.batch.table,
        contract=FUNDING_COVERAGE_AUDIT_CONTRACT,
        bindings={
            "boundary_evidence_sha256": verified.completed.boundary_evidence_sha256,
            "canonical_manifest_sha256": committed.receipt.manifest_sha256,
            "capacity_evidence_sha256": verified.capacity_evidence_sha256,
            "funding_manifest_sha256": verified.completed.manifest_sha256,
            "instrument_registry_sha256": verified.registry.artifact_sha256,
            "publisher_software_identity": committed.manifest.software_identity,
        },
        limitations=[
            "Coverage is evaluated only inside explicitly requested source windows.",
            "Unsaturated endpoint enumeration proves the retained Bybit source response, not an "
            "independently sourced exchange ledger.",
            "Any empty source window or observed cadence change remains blocked until dated "
            "evidence or a separately accepted policy explains it.",
            "Current instrument fundingInterval metadata is not used as historical evidence.",
            "This audit does not repair, compact, catalog, accept Gate 2, or authorize private or "
            "live operations.",
        ],
        storage_policy={
            "account_data_included": False,
            "funding_rates_included": False,
            "observed_settlement_timestamps_included": False,
            "runtime_paths_included": False,
        },
        audit_software_identity=audit_software_identity,
        generated_at_utc=generated_at_utc,
    )
