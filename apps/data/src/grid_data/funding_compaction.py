"""Evidence-bound immutable compaction for canonical funding fragments."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Final, cast

import pyarrow as pa  # type: ignore[import-untyped]
from grid_contracts.canonical import canonical_sha256
from grid_market_store import (
    FUNDING_CANONICAL_LAYOUT_ID,
    TARGET_FILE_SIZE_BYTES,
    CanonicalFundingBatch,
    CapacityBudget,
    FundingDatasetSpec,
    FundingPublicationPlan,
    HostSnapshot,
    PublishedDataset,
    load_committed_funding_table,
    logical_table_sha256,
    preflight_funding_dataset,
    publish_funding_dataset,
    verify_committed_funding_dataset,
)

from grid_data.evidence import verify_evidence
from grid_data.funding_publication import SOFTWARE_IDENTITY_RE
from grid_data.history_acquisition import HistoryAcquisitionError
from grid_data.history_request import (
    active_and_building_bytes_from_capacity,
    load_verified_capacity_evidence,
)

FUNDING_COMPACTION_EVIDENCE_CONTRACT: Final = "grid.canonical-funding-compaction/v1"
FUNDING_COMPACTION_BUILD_CONTRACT: Final = "grid.canonical-funding-compaction-publication/v1"
DATASET_ID_RE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
MINUTE_MS: Final = 60_000


class FundingCompactionError(RuntimeError):
    """Canonical funding fragments cannot be compacted safely."""


@dataclass(frozen=True, slots=True)
class ResolvedFundingCompaction:
    capacity_evidence_sha256: str
    parents: tuple[PublishedDataset, ...]
    parent_manifest_sha256: tuple[str, ...]
    input_file_count: int
    input_table_sha256: str
    plan: FundingPublicationPlan


def _object(path: Path, *, name: str) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FundingCompactionError(f"{name} cannot be loaded") from error
    if not isinstance(raw, dict):
        raise FundingCompactionError(f"{name} must be an object")
    return cast(dict[str, object], raw)


def _generated_at(value: str) -> str:
    if not value.endswith("Z"):
        raise FundingCompactionError("generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise FundingCompactionError("generated_at_utc is invalid") from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise FundingCompactionError("generated_at_utc must be UTC")
    return value


def _parent_bindings(parents: tuple[PublishedDataset, ...]) -> list[dict[str, str]]:
    return [
        {
            "dataset_id": parent.manifest.dataset_id,
            "manifest_sha256": parent.receipt.manifest_sha256,
        }
        for parent in parents
    ]


def _validate_union(table: pa.Table) -> None:
    identifiers = cast(list[int], table.column("instrument_id").to_pylist())
    timestamps = cast(list[int], table.column("funding_time_ms").to_pylist())
    intervals = cast(list[int], table.column("funding_interval_minutes").to_pylist())
    for index in range(1, table.num_rows):
        previous_key = (identifiers[index - 1], timestamps[index - 1])
        current_key = (identifiers[index], timestamps[index])
        if current_key <= previous_key:
            raise FundingCompactionError(
                "funding compaction parents contain duplicate or conflicting keys"
            )
        if identifiers[index] == identifiers[index - 1] and (
            timestamps[index] - timestamps[index - 1] != intervals[index] * MINUTE_MS
        ):
            raise FundingCompactionError(
                "funding compaction parent union has an unresolved settlement interval"
            )


def _load_parent_union(
    parents: tuple[PublishedDataset, ...],
) -> tuple[CanonicalFundingBatch, str]:
    tables = tuple(load_committed_funding_table(parent.dataset_root) for parent in parents)
    if any(not table.schema.equals(tables[0].schema, check_metadata=True) for table in tables[1:]):
        raise FundingCompactionError("funding compaction parent Arrow schemas differ")
    partition_paths = {
        PurePosixPath(item.path).parent for parent in parents for item in parent.manifest.files
    }
    if len(partition_paths) != 1:
        raise FundingCompactionError(
            "funding compaction parents must belong to one month/bucket partition"
        )
    table = (
        pa.concat_tables(tables)
        .sort_by([("instrument_id", "ascending"), ("funding_time_ms", "ascending")])
        .combine_chunks()
    )
    _validate_union(table)
    batch = CanonicalFundingBatch(
        partition_path=next(iter(partition_paths)),
        table=table,
    )
    return batch, logical_table_sha256(table)


def preflight_funding_compaction(
    dataset_ids: tuple[str, ...],
    capacity_evidence_path: Path,
    store_root: Path,
    snapshot: HostSnapshot,
    *,
    now_ms: int,
    software_identity: str,
) -> ResolvedFundingCompaction:
    """Verify parents and plan one receipt-last funding child without mutation."""

    if not SOFTWARE_IDENTITY_RE.fullmatch(software_identity):
        raise FundingCompactionError(
            "software_identity must be git:<40-character-lowercase-commit-sha>"
        )
    if len(dataset_ids) < 2 or len(dataset_ids) != len(set(dataset_ids)):
        raise FundingCompactionError(
            "funding compaction requires at least two unique dataset identities"
        )
    ordered_ids = tuple(sorted(dataset_ids))
    if any(not DATASET_ID_RE.fullmatch(dataset_id) for dataset_id in ordered_ids):
        raise FundingCompactionError("funding compaction dataset identity is unsafe")
    store = store_root.resolve()
    parents = tuple(
        verify_committed_funding_dataset(store / "datasets" / dataset_id)
        for dataset_id in ordered_ids
    )
    input_file_count = sum(len(parent.manifest.files) for parent in parents)
    if input_file_count < 2:
        raise FundingCompactionError("funding compaction requires at least two input fragments")
    batch, input_hash = _load_parent_union(parents)
    bindings = _parent_bindings(parents)
    parent_union_evidence = canonical_sha256(
        {
            "contract": FUNDING_COMPACTION_BUILD_CONTRACT,
            "input_table_sha256": input_hash,
            "parent_manifests": bindings,
        }
    )
    identity_sha = canonical_sha256(
        {
            "canonical_layout": FUNDING_CANONICAL_LAYOUT_ID,
            "contract": FUNDING_COMPACTION_BUILD_CONTRACT,
            "parent_manifests": bindings,
            "software_identity": software_identity,
            "target_file_bytes": TARGET_FILE_SIZE_BYTES,
        }
    )
    dataset_id = f"funding-compact-{identity_sha[:24]}"
    build_config_sha = canonical_sha256(
        {
            "canonical_layout": FUNDING_CANONICAL_LAYOUT_ID,
            "contract": FUNDING_COMPACTION_BUILD_CONTRACT,
            "dataset_id": dataset_id,
            "parent_manifests": bindings,
            "semantic_version": "1.0.0",
            "software_identity": software_identity,
            "target_file_bytes": TARGET_FILE_SIZE_BYTES,
        }
    )
    try:
        _capacity_path, capacity, capacity_sha = load_verified_capacity_evidence(
            capacity_evidence_path
        )
        active_bytes = active_and_building_bytes_from_capacity(capacity)
    except HistoryAcquisitionError as error:
        raise FundingCompactionError(str(error)) from error
    source_evidence = tuple(
        dict.fromkeys(
            (
                parent_union_evidence,
                *(parent.receipt.manifest_sha256 for parent in parents),
            )
        )
    )
    plan = preflight_funding_dataset(
        store,
        FundingDatasetSpec(
            dataset_id=dataset_id,
            semantic_version="1.0.0",
            parent_dataset_ids=ordered_ids,
            source_evidence_sha256=source_evidence,
            coverage_evidence_sha256=parent_union_evidence,
            boundary_evidence_sha256=parent_union_evidence,
            capacity_evidence_sha256=capacity_sha,
            build_config_sha256=build_config_sha,
            software_identity=software_identity,
        ),
        batch,
        CapacityBudget(active_and_building_bytes=active_bytes, rest_staging_bytes=0),
        snapshot,
        now_ms=now_ms,
    )
    return ResolvedFundingCompaction(
        capacity_evidence_sha256=capacity_sha,
        parents=parents,
        parent_manifest_sha256=tuple(parent.receipt.manifest_sha256 for parent in parents),
        input_file_count=input_file_count,
        input_table_sha256=input_hash,
        plan=plan,
    )


def _verify_parents_unchanged(resolved: ResolvedFundingCompaction) -> None:
    for parent, expected_hash in zip(
        resolved.parents,
        resolved.parent_manifest_sha256,
        strict=True,
    ):
        verified = verify_committed_funding_dataset(parent.dataset_root)
        if verified.receipt.manifest_sha256 != expected_hash:
            raise FundingCompactionError("funding compaction parent changed after preflight")


def _verify_output(
    resolved: ResolvedFundingCompaction,
    published: PublishedDataset,
) -> PublishedDataset:
    verified = verify_committed_funding_dataset(published.dataset_root)
    _verify_parents_unchanged(resolved)
    if (
        verified.receipt.manifest_sha256 != published.receipt.manifest_sha256
        or verified.manifest.dataset_id != resolved.plan.spec.dataset_id
        or verified.manifest.parent_dataset_ids != resolved.plan.spec.parent_dataset_ids
        or verified.manifest.source_evidence_sha256 != resolved.plan.spec.source_evidence_sha256
        or len(verified.manifest.files) != 1
    ):
        raise FundingCompactionError("funding compaction output differs from its preflight")
    output = load_committed_funding_table(verified.dataset_root).combine_chunks()
    if logical_table_sha256(output) != resolved.input_table_sha256 or not output.equals(
        resolved.plan.batch.table, check_metadata=True
    ):
        raise FundingCompactionError(
            "funding compaction output does not exactly preserve its parent union"
        )
    return verified


def publish_preflighted_funding_compaction(
    resolved: ResolvedFundingCompaction,
    snapshot_provider: Callable[[], HostSnapshot],
    now_ms: Callable[[], int],
) -> PublishedDataset:
    """Reverify parents, then invoke the receipt-last funding publication primitive."""

    _verify_parents_unchanged(resolved)
    published = publish_funding_dataset(
        resolved.plan,
        snapshot_provider(),
        committed_at_ms=now_ms(),
    )
    return _verify_output(resolved, published)


def build_funding_compaction_evidence(
    resolved: ResolvedFundingCompaction,
    published: PublishedDataset,
    *,
    generated_at_utc: str,
) -> dict[str, object]:
    """Build a GitHub-safe proof of exact immutable funding compaction."""

    verified = _verify_output(resolved, published)
    item = verified.manifest.files[0]
    audit = _object(verified.audit_path, name="funding compaction audit")
    file_target = audit.get("file_target")
    if not isinstance(file_target, dict):
        raise FundingCompactionError("funding compaction audit has no file-target facts")
    payload: dict[str, object] = {
        "bindings": {
            "capacity_evidence_sha256": resolved.capacity_evidence_sha256,
            "compacted_manifest_sha256": verified.receipt.manifest_sha256,
            "input_table_sha256": resolved.input_table_sha256,
            "output_table_sha256": logical_table_sha256(
                load_committed_funding_table(verified.dataset_root).combine_chunks()
            ),
            "parent_manifests": _parent_bindings(resolved.parents),
        },
        "compaction": {
            "conflicting_key_count": 0,
            "duplicate_key_count": 0,
            "input_file_count": resolved.input_file_count,
            "logical_table_equal": True,
            "output_file_count": 1,
            "output_total_bytes": item.size_bytes,
            "row_count": verified.manifest.row_count,
        },
        "compaction_software_identity": verified.manifest.software_identity,
        "contract": FUNDING_COMPACTION_EVIDENCE_CONTRACT,
        "file_target": file_target,
        "generated_at_utc": _generated_at(generated_at_utc),
        "limitations": [
            "Compaction proves only the supplied immutable funding month/bucket parent union.",
            "Funding chronology acceptance remains a separate receipt-bound coverage audit.",
            "This transition does not register a catalog entry, delete a parent, or close Gate 2.",
        ],
        "lineage": {
            "compacted_dataset_id": verified.manifest.dataset_id,
            "parent_dataset_ids": list(verified.manifest.parent_dataset_ids),
            "parent_datasets_mutated": False,
        },
        "status": "passed",
        "storage_policy": {
            "account_data_included": False,
            "market_values_included": False,
            "runtime_paths_included": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def verify_funding_compaction_evidence(
    evidence_path: Path,
    resolved: ResolvedFundingCompaction,
    published: PublishedDataset,
) -> dict[str, object]:
    """Verify the receipt and rebuild the value-free funding compaction proof."""

    path = evidence_path.resolve()
    if not verify_evidence(path):
        raise FundingCompactionError("funding compaction evidence receipt does not verify")
    stored = _object(path, name="funding compaction evidence")
    embedded_hash = stored.get("content_sha256")
    hash_input = dict(stored)
    hash_input.pop("content_sha256", None)
    generated_at = stored.get("generated_at_utc")
    if (
        stored.get("contract") != FUNDING_COMPACTION_EVIDENCE_CONTRACT
        or stored.get("status") != "passed"
        or not isinstance(generated_at, str)
        or not isinstance(embedded_hash, str)
        or embedded_hash != canonical_sha256(hash_input)
    ):
        raise FundingCompactionError(
            "funding compaction evidence identity or content hash is invalid"
        )
    recomputed = build_funding_compaction_evidence(
        resolved,
        published,
        generated_at_utc=generated_at,
    )
    if recomputed != stored:
        raise FundingCompactionError("funding compaction evidence no longer matches runtime inputs")
    return stored
