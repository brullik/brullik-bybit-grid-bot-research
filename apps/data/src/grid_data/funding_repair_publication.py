"""Immutable funding repair publication and GitHub-safe aggregate evidence."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Final, cast

import pyarrow as pa  # type: ignore[import-untyped]
from grid_contracts.canonical import canonical_sha256
from grid_market_store import (
    FUNDING_CANONICAL_LAYOUT_ID,
    CanonicalFundingBatch,
    CapacityBudget,
    FundingDatasetSpec,
    FundingPublicationPlan,
    HostSnapshot,
    PublicationError,
    PublishedDataset,
    load_committed_funding_table,
    preflight_funding_dataset,
    publish_funding_dataset,
    verify_committed_funding_dataset,
)

from grid_data.evidence import verify_evidence
from grid_data.funding_acquisition import (
    FundingAcquisitionError,
    load_completed_funding_batch,
)
from grid_data.funding_publication import SOFTWARE_IDENTITY_RE
from grid_data.funding_repair_execution import (
    VerifiedFundingRepairExecution,
    verify_funding_repair_execution,
)
from grid_data.history_acquisition import HistoryAcquisitionError
from grid_data.history_request import load_verified_capacity_evidence
from grid_data.instrument_registry import load_verified_instrument_registry

FUNDING_REPAIR_PUBLICATION_CONTRACT: Final = "grid.canonical-funding-repair-publication/v1"
FUNDING_REPAIR_REPLACEMENT_EVIDENCE_CONTRACT: Final = "grid.canonical-funding-repair-replacement/v1"
FUNDING_REPAIR_EXECUTION_PUBLIC_CONTRACT: Final = "grid.bybit-funding-repair-execution-public/v1"
MINUTE_MS: Final = 60_000


@dataclass(frozen=True, slots=True)
class ResolvedFundingRepairPublication:
    verified_execution: VerifiedFundingRepairExecution
    parent: PublishedDataset
    plan: FundingPublicationPlan
    parent_row_count: int
    repaired_row_count: int
    restated_interval_count: int
    registry_sha256: str


def _object(path: Path, *, name: str) -> dict[str, object]:
    try:
        raw = json.loads(path.resolve().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FundingAcquisitionError(f"{name} cannot be loaded") from error
    if not isinstance(raw, dict):
        raise FundingAcquisitionError(f"{name} must be an object")
    return cast(dict[str, object], raw)


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


def _repair_budget(execution: VerifiedFundingRepairExecution) -> CapacityBudget:
    budgets: list[CapacityBudget] = []
    for completed in execution.completed_jobs:
        plan = _object(completed.plan_path, name="funding repair Landing plan")
        raw = plan.get("capacity_budget")
        if not isinstance(raw, dict):
            raise FundingAcquisitionError("funding repair Landing plan has no capacity budget")
        try:
            budgets.append(CapacityBudget(**raw))
        except (TypeError, PublicationError) as error:
            raise FundingAcquisitionError(
                "funding repair Landing capacity budget is invalid"
            ) from error
    if not budgets or any(item != budgets[0] for item in budgets[1:]):
        raise FundingAcquisitionError("funding repair jobs do not share one aggregate budget")
    return budgets[0]


def _combined_batch(
    execution: VerifiedFundingRepairExecution,
    parent: PublishedDataset,
    parent_table: pa.Table,
) -> tuple[CanonicalFundingBatch, int]:
    partition_path = PurePosixPath(parent.manifest.files[0].path).parent
    repair_tables: list[pa.Table] = []
    for completed in execution.completed_jobs:
        batch = load_completed_funding_batch(completed.job_root)
        if batch.partition_path != partition_path:
            raise FundingAcquisitionError(
                "funding repair Landing does not match the parent partition"
            )
        if not batch.table.schema.equals(parent_table.schema, check_metadata=True):
            raise FundingAcquisitionError("funding repair and parent schemas differ")
        repair_tables.append(batch.table)

    combined = pa.concat_tables([parent_table, *repair_tables]).sort_by(
        [("instrument_id", "ascending"), ("funding_time_ms", "ascending")]
    )
    identifiers = cast(list[int], combined.column("instrument_id").to_pylist())
    times = cast(list[int], combined.column("funding_time_ms").to_pylist())
    keys = list(zip(identifiers, times, strict=True))
    if len(keys) != len(set(keys)):
        raise FundingAcquisitionError("funding repair overlaps a canonical parent key")
    if combined.num_rows != parent_table.num_rows + sum(table.num_rows for table in repair_tables):
        raise FundingAcquisitionError("funding repair row accounting is inconsistent")

    parent_keys = list(
        zip(
            cast(list[int], parent_table.column("instrument_id").to_pylist()),
            cast(list[int], parent_table.column("funding_time_ms").to_pylist()),
            strict=True,
        )
    )
    parent_intervals = dict(
        zip(
            parent_keys,
            cast(list[int], parent_table.column("funding_interval_minutes").to_pylist()),
            strict=True,
        )
    )
    source_intervals = cast(list[int], combined.column("funding_interval_minutes").to_pylist())
    rebuilt_intervals: list[int] = []
    restated = 0
    previous_by_instrument: dict[int, int] = {}
    for key, source_interval in zip(keys, source_intervals, strict=True):
        instrument_id, funding_time_ms = key
        previous = previous_by_instrument.get(instrument_id)
        if previous is None:
            if key not in parent_intervals:
                raise FundingAcquisitionError(
                    "funding repair cannot introduce an unverified partition boundary"
                )
            interval = source_interval
        else:
            delta = funding_time_ms - previous
            if delta <= 0 or delta % MINUTE_MS:
                raise FundingAcquisitionError(
                    "funding repair settlement chronology is not exact whole minutes"
                )
            interval = delta // MINUTE_MS
        if key in parent_intervals and parent_intervals[key] != interval:
            restated += 1
        rebuilt_intervals.append(interval)
        previous_by_instrument[instrument_id] = funding_time_ms

    interval_index = combined.schema.get_field_index("funding_interval_minutes")
    rebuilt = combined.set_column(
        interval_index,
        combined.schema.field(interval_index),
        pa.array(rebuilt_intervals, type=pa.uint32()),
    )
    return CanonicalFundingBatch(partition_path=partition_path, table=rebuilt), restated


def _dataset_id(identity_sha256: str) -> str:
    return f"funding-repair-{identity_sha256[:24]}"


def preflight_repaired_funding_publication(
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
) -> ResolvedFundingRepairPublication:
    """Verify exact source confirmation and preflight one immutable repair child."""

    if not SOFTWARE_IDENTITY_RE.fullmatch(software_identity):
        raise FundingAcquisitionError(
            "software_identity must be git:<40-character-lowercase-commit-sha>"
        )
    execution = verify_funding_repair_execution(
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
        raise FundingAcquisitionError(
            "funding replacement publication requires a passed repair execution"
        )
    parent_id = execution.payload.get("dataset_id")
    if not isinstance(parent_id, str):
        raise FundingAcquisitionError("funding repair execution has no parent identity")
    parent = verify_committed_funding_dataset(store_root.resolve() / "datasets" / parent_id)
    parent_table = load_committed_funding_table(parent.dataset_root)
    bindings = cast(dict[str, object], execution.payload["bindings"])
    if parent.receipt.manifest_sha256 != bindings.get("canonical_parent_manifest_sha256"):
        raise FundingAcquisitionError("canonical funding parent no longer matches repair evidence")
    registry = load_verified_instrument_registry(instrument_registry_path)
    try:
        _capacity_path, _capacity, capacity_sha = load_verified_capacity_evidence(
            capacity_evidence_path
        )
    except HistoryAcquisitionError as error:
        raise FundingAcquisitionError(str(error)) from error
    batch, restated_count = _combined_batch(execution, parent, parent_table)
    repaired_count = sum(item.row_count for item in execution.completed_jobs)
    limits = cast(dict[str, object], execution.payload["limits"])
    if (
        repaired_count != limits.get("candidate_settlement_count")
        or batch.table.num_rows != parent.manifest.row_count + repaired_count
        or not 1 <= restated_count <= repaired_count
    ):
        raise FundingAcquisitionError(
            "funding replacement row accounting does not close the repair plan"
        )
    parent_audit = _object(parent.audit_path, name="canonical funding parent audit")
    boundary_sha = parent_audit.get("boundary_evidence_sha256")
    if not isinstance(boundary_sha, str):
        raise FundingAcquisitionError("canonical funding parent has no boundary evidence")
    identity_hash = canonical_sha256(
        {
            "contract": FUNDING_REPAIR_PUBLICATION_CONTRACT,
            "parent_dataset_id": parent.manifest.dataset_id,
            "parent_manifest_sha256": parent.receipt.manifest_sha256,
            "repair_execution_artifact_sha256": execution.artifact_sha256,
            "repair_plan_artifact_sha256": execution.verified_plan.artifact_sha256,
        }
    )
    dataset_id = _dataset_id(identity_hash)
    build_config_sha = canonical_sha256(
        {
            "canonical_layout": FUNDING_CANONICAL_LAYOUT_ID,
            "contract": FUNDING_REPAIR_PUBLICATION_CONTRACT,
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
                boundary_sha,
            )
        )
    )
    spec = FundingDatasetSpec(
        dataset_id=dataset_id,
        semantic_version="1.0.0",
        parent_dataset_ids=(parent.manifest.dataset_id,),
        source_evidence_sha256=source_digests,
        coverage_evidence_sha256=execution.artifact_sha256,
        boundary_evidence_sha256=boundary_sha,
        capacity_evidence_sha256=capacity_sha,
        build_config_sha256=build_config_sha,
        software_identity=software_identity,
    )
    plan = preflight_funding_dataset(
        store_root,
        spec,
        batch,
        _repair_budget(execution),
        snapshot,
        now_ms=now_ms,
    )
    return ResolvedFundingRepairPublication(
        verified_execution=execution,
        parent=parent,
        plan=plan,
        parent_row_count=parent.manifest.row_count,
        repaired_row_count=repaired_count,
        restated_interval_count=restated_count,
        registry_sha256=registry.artifact_sha256,
    )


def publish_preflighted_funding_repair(
    resolved: ResolvedFundingRepairPublication,
    snapshot_provider: Callable[[], HostSnapshot],
    now_ms: Callable[[], int],
) -> PublishedDataset:
    """Repeat the host observation and publish the immutable repair child receipt-last."""

    return publish_funding_dataset(
        resolved.plan,
        snapshot_provider(),
        committed_at_ms=now_ms(),
    )


def build_funding_repair_execution_public_evidence(
    execution: VerifiedFundingRepairExecution,
    *,
    generated_at_utc: str,
) -> dict[str, object]:
    """Project private repair execution into identifier- and value-free aggregate evidence."""

    bindings = cast(dict[str, object], execution.payload["bindings"])
    limits = cast(dict[str, object], execution.payload["limits"])
    payload: dict[str, object] = {
        "bindings": {
            "canonical_parent_manifest_sha256": bindings["canonical_parent_manifest_sha256"],
            "capacity_evidence_sha256": bindings["capacity_evidence_sha256"],
            "chronology_anomaly_records_sha256": bindings["chronology_anomaly_records_sha256"],
            "coverage_audit_artifact_sha256": bindings["coverage_audit_artifact_sha256"],
            "instrument_registry_sha256": bindings["instrument_registry_sha256"],
            "private_execution_artifact_sha256": execution.artifact_sha256,
            "repair_plan_artifact_sha256": bindings["repair_plan_artifact_sha256"],
        },
        "contract": FUNDING_REPAIR_EXECUTION_PUBLIC_CONTRACT,
        "execution_software_identity": execution.payload["executor_software_identity"],
        "generated_at_utc": _generated_at(generated_at_utc),
        "limits": dict(limits),
        "limitations": [
            "Evidence covers only the bound private repair discovery plan.",
            "Source confirmation does not accept a historical funding schedule change.",
            "Canonical publication and post-publication chronology audit remain separate.",
        ],
        "status": execution.payload["status"],
        "storage_policy": {
            "account_data_included": False,
            "credentials_included": False,
            "github_commit_eligible": True,
            "instrument_identifiers_included": False,
            "market_values_included": False,
            "runtime_paths_included": False,
            "settlement_timestamps_included": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def verify_funding_repair_execution_public_evidence(
    evidence_path: Path,
    execution: VerifiedFundingRepairExecution,
) -> dict[str, object]:
    """Verify and rebuild a committed GitHub-safe execution projection."""

    path = evidence_path.resolve()
    if not verify_evidence(path):
        raise FundingAcquisitionError(
            "funding repair public execution evidence receipt does not verify"
        )
    stored = _object(path, name="funding repair public execution evidence")
    embedded = stored.get("content_sha256")
    hash_input = dict(stored)
    hash_input.pop("content_sha256", None)
    generated_at = stored.get("generated_at_utc")
    if (
        stored.get("contract") != FUNDING_REPAIR_EXECUTION_PUBLIC_CONTRACT
        or stored.get("status") not in ("passed", "blocked")
        or not isinstance(generated_at, str)
        or not isinstance(embedded, str)
        or embedded != canonical_sha256(hash_input)
    ):
        raise FundingAcquisitionError(
            "funding repair public execution evidence identity is invalid"
        )
    recomputed = build_funding_repair_execution_public_evidence(
        execution,
        generated_at_utc=generated_at,
    )
    if recomputed != stored:
        raise FundingAcquisitionError(
            "funding repair public execution evidence no longer matches runtime inputs"
        )
    return stored


def build_funding_repair_replacement_evidence(
    resolved: ResolvedFundingRepairPublication,
    published: PublishedDataset,
    *,
    generated_at_utc: str,
) -> dict[str, object]:
    """Build a value-free proof of exact repair publication and immutable lineage."""

    if published.manifest.dataset_id != resolved.plan.spec.dataset_id:
        raise FundingAcquisitionError("published funding repair identity differs from preflight")
    if published.manifest.parent_dataset_ids != (resolved.parent.manifest.dataset_id,):
        raise FundingAcquisitionError("funding repair child does not preserve parent lineage")
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
        "chronology": {
            "duplicate_key_count": 0,
            "exact_source_confirmation": True,
            "inserted_settlement_count": resolved.repaired_row_count,
            "restated_interval_count": resolved.restated_interval_count,
            "unexpected_key_count": 0,
        },
        "contract": FUNDING_REPAIR_REPLACEMENT_EVIDENCE_CONTRACT,
        "generated_at_utc": _generated_at(generated_at_utc),
        "lineage": {
            "parent_dataset_id": resolved.parent.manifest.dataset_id,
            "parent_dataset_mutated": False,
            "parent_ids_in_manifest": list(published.manifest.parent_dataset_ids),
            "replacement_dataset_id": published.manifest.dataset_id,
        },
        "limitations": [
            "The original blocked coverage audit remains immutable.",
            "Publication does not accept a historical funding schedule change or close Gate 2.",
            "A separate post-publication coverage audit and catalog transition remain required.",
        ],
        "replacement_software_identity": published.manifest.software_identity,
        "row_accounting": {
            "parent_row_count": resolved.parent_row_count,
            "repaired_row_count": resolved.repaired_row_count,
            "replacement_row_count": published.manifest.row_count,
        },
        "status": "passed",
        "storage_policy": {
            "account_data_included": False,
            "instrument_identifiers_included": False,
            "market_values_included": False,
            "runtime_paths_included": False,
            "settlement_timestamps_included": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def verify_funding_repair_replacement_evidence(
    evidence_path: Path,
    resolved: ResolvedFundingRepairPublication,
    published: PublishedDataset,
) -> dict[str, object]:
    """Verify and rebuild a committed immutable funding replacement proof."""

    path = evidence_path.resolve()
    if not verify_evidence(path):
        raise FundingAcquisitionError("funding repair replacement evidence receipt does not verify")
    stored = _object(path, name="funding repair replacement evidence")
    embedded = stored.get("content_sha256")
    hash_input = dict(stored)
    hash_input.pop("content_sha256", None)
    generated_at = stored.get("generated_at_utc")
    if (
        stored.get("contract") != FUNDING_REPAIR_REPLACEMENT_EVIDENCE_CONTRACT
        or stored.get("status") != "passed"
        or not isinstance(generated_at, str)
        or not isinstance(embedded, str)
        or embedded != canonical_sha256(hash_input)
    ):
        raise FundingAcquisitionError("funding repair replacement evidence identity is invalid")
    recomputed = build_funding_repair_replacement_evidence(
        resolved,
        published,
        generated_at_utc=generated_at,
    )
    if recomputed != stored:
        raise FundingAcquisitionError(
            "funding repair replacement evidence no longer matches runtime inputs"
        )
    return stored
