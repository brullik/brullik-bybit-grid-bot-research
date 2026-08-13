"""Immutable canonical replacement from a passed one-minute gap repair execution."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from pathlib import Path, PurePosixPath
from typing import Final, cast

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.compute as pc  # type: ignore[import-untyped]
from grid_contracts.canonical import canonical_sha256
from grid_contracts.market import MINUTE_MS, DatasetType
from grid_market_store import (
    CANONICAL_LAYOUT_ID,
    CandleDatasetSpec,
    CanonicalCandleBatch,
    CapacityBudget,
    HostSnapshot,
    PublicationError,
    PublicationPlan,
    PublishedDataset,
    load_committed_candle_table,
    preflight_candle_dataset,
    publish_candle_dataset,
)

from grid_data.evidence import verify_evidence
from grid_data.history_acquisition import (
    HistoryAcquisitionError,
    HistorySeries,
    load_completed_history_batch,
)
from grid_data.history_publication import SOFTWARE_IDENTITY_RE
from grid_data.history_repair_execution import (
    VerifiedRepairExecution,
    verify_gap_repair_execution,
)
from grid_data.history_request import load_verified_capacity_evidence
from grid_data.instrument_registry import load_verified_instrument_registry

REPAIR_PUBLICATION_CONTRACT: Final = "grid.canonical-1m-gap-replacement-publication/v1"
REPAIR_REPLACEMENT_EVIDENCE_CONTRACT: Final = "grid.canonical-1m-gap-replacement/v1"


@dataclass(frozen=True, slots=True)
class ResolvedRepairPublication:
    verified_execution: VerifiedRepairExecution
    parent: PublishedDataset
    plan: PublicationPlan
    expected_minute_count: int
    parent_row_count: int
    repaired_row_count: int
    registry_sha256: str


def _object(path: Path, *, name: str) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryAcquisitionError(f"{name} cannot be loaded") from error
    if not isinstance(raw, dict):
        raise HistoryAcquisitionError(f"{name} must be an object")
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


def _series(job_root: Path) -> tuple[HistorySeries, ...]:
    plan = _object(job_root.resolve() / "plan.json", name="original history plan")
    raw_spec = plan.get("spec")
    if not isinstance(raw_spec, dict) or not isinstance(raw_spec.get("series"), list):
        raise HistoryAcquisitionError("original history plan has no series inventory")
    try:
        return tuple(HistorySeries(**item) for item in raw_spec["series"])
    except (TypeError, AttributeError) as error:
        raise HistoryAcquisitionError("original history series inventory is invalid") from error


def _repair_budget(execution: VerifiedRepairExecution) -> CapacityBudget:
    budgets: list[CapacityBudget] = []
    for completed in execution.completed_jobs:
        plan = _object(completed.plan_path, name="repair history plan")
        raw = plan.get("capacity_budget")
        if not isinstance(raw, dict):
            raise HistoryAcquisitionError("repair history plan has no capacity budget")
        try:
            budgets.append(CapacityBudget(**raw))
        except (TypeError, PublicationError) as error:
            raise HistoryAcquisitionError("repair history capacity budget is invalid") from error
    if not budgets or any(item != budgets[0] for item in budgets[1:]):
        raise HistoryAcquisitionError("repair history jobs do not share one aggregate budget")
    return budgets[0]


def _assert_exact_requested_coverage(
    table: pa.Table,
    series: tuple[HistorySeries, ...],
) -> int:
    expected_total = 0
    observed_total = 0
    for item in series:
        mask = pc.equal(table.column("instrument_id"), item.instrument_id)
        times = cast(list[int], pc.filter(table.column("open_time_ms"), mask).to_pylist())
        expected = ((item.end_ms - item.start_ms) // MINUTE_MS) + 1
        if (
            len(times) != expected
            or not times
            or times[0] != item.start_ms
            or times[-1] != item.end_ms
            or any(right - left != MINUTE_MS for left, right in pairwise(times))
        ):
            raise HistoryAcquisitionError(
                "replacement table does not exactly cover every requested minute"
            )
        expected_total += expected
        observed_total += len(times)
    if observed_total != expected_total or table.num_rows != expected_total:
        raise HistoryAcquisitionError("replacement table contains unrequested rows")
    return expected_total


def _combined_batch(
    execution: VerifiedRepairExecution,
    parent_table: pa.Table,
    parent: PublishedDataset,
    original_series: tuple[HistorySeries, ...],
) -> tuple[CanonicalCandleBatch, int]:
    repair_tables: list[pa.Table] = []
    partition_path = PurePosixPath(parent.manifest.files[0].path).parent
    for completed in execution.completed_jobs:
        batch = load_completed_history_batch(completed.job_root)
        if batch.dataset_type is not parent.manifest.dataset_type:
            raise HistoryAcquisitionError("repair dataset type differs from its canonical parent")
        if batch.partition_path != partition_path:
            raise HistoryAcquisitionError("repair Landing does not match the parent partition")
        if not batch.table.schema.equals(parent_table.schema, check_metadata=True):
            raise HistoryAcquisitionError("repair and parent canonical schemas differ")
        repair_tables.append(batch.table)
    combined = pa.concat_tables([parent_table, *repair_tables]).sort_by(
        [("instrument_id", "ascending"), ("open_time_ms", "ascending")]
    )
    if combined.num_rows > 1:
        left_ids = combined.column("instrument_id").slice(0, combined.num_rows - 1)
        right_ids = combined.column("instrument_id").slice(1, combined.num_rows - 1)
        left_times = combined.column("open_time_ms").slice(0, combined.num_rows - 1)
        right_times = combined.column("open_time_ms").slice(1, combined.num_rows - 1)
        strictly_ordered = pc.or_(
            pc.greater(right_ids, left_ids),
            pc.and_(pc.equal(right_ids, left_ids), pc.greater(right_times, left_times)),
        )
        if pc.all(strictly_ordered).as_py() is not True:
            raise HistoryAcquisitionError("repair overlaps or duplicates a canonical parent key")
    expected = _assert_exact_requested_coverage(combined, original_series)
    return (
        CanonicalCandleBatch(
            dataset_type=parent.manifest.dataset_type,
            partition_path=partition_path,
            table=combined,
        ),
        expected,
    )


def _dataset_id(dataset_type: DatasetType, identity_sha256: str) -> str:
    prefix = "trade-1m" if dataset_type is DatasetType.TRADE_KLINE_1M else "mark-1m"
    return f"{prefix}-repair-{identity_sha256[:24]}"


def preflight_repaired_history_publication(
    execution_path: Path,
    repair_plan_path: Path,
    coverage_audit_path: Path,
    original_job_root: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    store_root: Path,
    repair_staging_root: Path,
    snapshot: HostSnapshot,
    *,
    now_ms: int,
    software_identity: str,
) -> ResolvedRepairPublication:
    """Verify exact gap closure and preflight a new child dataset without mutation."""

    if not SOFTWARE_IDENTITY_RE.fullmatch(software_identity):
        raise HistoryAcquisitionError(
            "software_identity must be git:<40-character-lowercase-commit-sha>"
        )
    execution = verify_gap_repair_execution(
        execution_path,
        repair_plan_path,
        coverage_audit_path,
        original_job_root,
        instrument_registry_path,
        capacity_evidence_path,
        store_root,
        repair_staging_root,
    )
    if not execution.passed:
        raise HistoryAcquisitionError("replacement publication requires a passed repair execution")
    parent_id = cast(str, execution.verified_plan.payload["dataset_id"])
    parent, parent_table = load_committed_candle_table(
        store_root.resolve() / "datasets" / parent_id
    )
    bindings = cast(dict[str, object], execution.payload["bindings"])
    if parent.receipt.manifest_sha256 != bindings.get("canonical_parent_manifest_sha256"):
        raise HistoryAcquisitionError("canonical parent manifest no longer matches repair evidence")
    registry = load_verified_instrument_registry(instrument_registry_path)
    _capacity_path, _capacity, capacity_sha = load_verified_capacity_evidence(
        capacity_evidence_path
    )
    batch, expected_count = _combined_batch(
        execution,
        parent_table,
        parent,
        _series(original_job_root),
    )
    repaired_count = sum(item.row_count for item in execution.completed_jobs)
    limits = cast(dict[str, object], execution.payload["limits"])
    if (
        repaired_count != limits.get("total_missing_minutes")
        or batch.table.num_rows != parent.manifest.row_count + repaired_count
    ):
        raise HistoryAcquisitionError("replacement row accounting does not close the repair plan")
    identity_hash = canonical_sha256(
        {
            "contract": REPAIR_PUBLICATION_CONTRACT,
            "parent_dataset_id": parent.manifest.dataset_id,
            "parent_manifest_sha256": parent.receipt.manifest_sha256,
            "repair_execution_artifact_sha256": execution.artifact_sha256,
            "repair_plan_artifact_sha256": execution.verified_plan.artifact_sha256,
        }
    )
    dataset_id = _dataset_id(parent.manifest.dataset_type, identity_hash)
    build_config_sha = canonical_sha256(
        {
            "canonical_layout": CANONICAL_LAYOUT_ID,
            "contract": REPAIR_PUBLICATION_CONTRACT,
            "dataset_id": dataset_id,
            "parent_dataset_id": parent.manifest.dataset_id,
            "parent_manifest_sha256": parent.receipt.manifest_sha256,
            "repair_execution_artifact_sha256": execution.artifact_sha256,
            "repair_plan_artifact_sha256": execution.verified_plan.artifact_sha256,
            "semantic_version": "1.0.0",
            "software_identity": software_identity,
        }
    )
    source_digests = tuple(
        dict.fromkeys(
            (
                execution.artifact_sha256,
                execution.verified_plan.artifact_sha256,
                parent.receipt.manifest_sha256,
                *(completed.manifest_sha256 for completed in execution.completed_jobs),
                registry.artifact_sha256,
            )
        )
    )
    spec = CandleDatasetSpec(
        dataset_id=dataset_id,
        semantic_version="1.0.0",
        parent_dataset_ids=(parent.manifest.dataset_id,),
        source_evidence_sha256=source_digests,
        coverage_evidence_sha256=execution.artifact_sha256,
        capacity_evidence_sha256=capacity_sha,
        build_config_sha256=build_config_sha,
        software_identity=software_identity,
    )
    publication_plan = preflight_candle_dataset(
        store_root,
        spec,
        batch,
        _repair_budget(execution),
        snapshot,
        now_ms=now_ms,
    )
    return ResolvedRepairPublication(
        verified_execution=execution,
        parent=parent,
        plan=publication_plan,
        expected_minute_count=expected_count,
        parent_row_count=parent.manifest.row_count,
        repaired_row_count=repaired_count,
        registry_sha256=registry.artifact_sha256,
    )


def publish_preflighted_repair(
    resolved: ResolvedRepairPublication,
    snapshot_provider: Callable[[], HostSnapshot],
    now_ms: Callable[[], int],
) -> PublishedDataset:
    """Repeat the host observation and atomically publish the immutable child dataset."""

    fresh_snapshot = snapshot_provider()
    committed_at_ms = now_ms()
    return publish_candle_dataset(
        resolved.plan,
        fresh_snapshot,
        committed_at_ms=committed_at_ms,
    )


def build_gap_replacement_evidence(
    resolved: ResolvedRepairPublication,
    published: PublishedDataset,
    *,
    generated_at_utc: str,
) -> dict[str, object]:
    """Build a bounded proof of exact coverage and immutable parent lineage."""

    if published.manifest.dataset_id != resolved.plan.spec.dataset_id:
        raise HistoryAcquisitionError("published replacement identity differs from preflight")
    if published.manifest.parent_dataset_ids != (resolved.parent.manifest.dataset_id,):
        raise HistoryAcquisitionError("published replacement does not preserve parent lineage")
    execution = resolved.verified_execution
    payload: dict[str, object] = {
        "bindings": {
            "capacity_evidence_sha256": resolved.plan.spec.capacity_evidence_sha256,
            "instrument_registry_sha256": resolved.registry_sha256,
            "parent_manifest_sha256": resolved.parent.receipt.manifest_sha256,
            "repair_execution_artifact_sha256": execution.artifact_sha256,
            "repair_plan_artifact_sha256": execution.verified_plan.artifact_sha256,
            "replacement_manifest_sha256": published.receipt.manifest_sha256,
        },
        "contract": REPAIR_REPLACEMENT_EVIDENCE_CONTRACT,
        "coverage": {
            "conflicting_key_count": 0,
            "duplicate_key_count": 0,
            "exact_requested_coverage": True,
            "expected_minute_count": resolved.expected_minute_count,
            "parent_row_count": resolved.parent_row_count,
            "repaired_row_count": resolved.repaired_row_count,
            "replacement_row_count": published.manifest.row_count,
            "unrequested_row_count": 0,
        },
        "generated_at_utc": _generated_at(generated_at_utc),
        "lineage": {
            "parent_dataset_id": resolved.parent.manifest.dataset_id,
            "parent_dataset_mutated": False,
            "parent_ids_in_manifest": list(published.manifest.parent_dataset_ids),
            "replacement_dataset_id": published.manifest.dataset_id,
        },
        "limitations": [
            "Coverage is proven only for the original bounded requested series.",
            "This replacement does not accept an absence reason or close Gate 2.",
            "Catalog registration and compaction remain separate transitions.",
        ],
        "replacement_software_identity": published.manifest.software_identity,
        "status": "passed",
        "storage_policy": {
            "account_data_included": False,
            "market_values_included": False,
            "runtime_paths_included": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def verify_gap_replacement_evidence(
    evidence_path: Path,
    resolved: ResolvedRepairPublication,
    published: PublishedDataset,
) -> dict[str, object]:
    """Verify and deterministically rebuild a committed replacement proof."""

    path = evidence_path.resolve()
    if not verify_evidence(path):
        raise HistoryAcquisitionError("gap replacement evidence receipt does not verify")
    stored = _object(path, name="gap replacement evidence")
    embedded_content_sha = stored.get("content_sha256")
    hash_input = dict(stored)
    hash_input.pop("content_sha256", None)
    generated_at = stored.get("generated_at_utc")
    if (
        stored.get("contract") != REPAIR_REPLACEMENT_EVIDENCE_CONTRACT
        or stored.get("status") != "passed"
        or not isinstance(generated_at, str)
        or not isinstance(embedded_content_sha, str)
        or embedded_content_sha != canonical_sha256(hash_input)
    ):
        raise HistoryAcquisitionError(
            "gap replacement evidence identity or content hash is invalid"
        )
    recomputed = build_gap_replacement_evidence(
        resolved,
        published,
        generated_at_utc=generated_at,
    )
    if recomputed != stored:
        raise HistoryAcquisitionError("gap replacement evidence no longer matches runtime inputs")
    return stored
