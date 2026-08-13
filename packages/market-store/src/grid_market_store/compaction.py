"""Immutable target-size compaction for canonical candle fragments."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, cast

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.compute as pc  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file
from grid_contracts.market import CompletionReceipt, DatasetManifest, DatasetStatus

from grid_market_store.physical import (
    CANONICAL_LAYOUT_ID,
    COMPRESSION,
    COMPRESSION_LEVEL,
    TARGET_FILE_SIZE_BYTES,
    CanonicalCandleBatch,
    verify_canonical_candle_schema,
)
from grid_market_store.publication import (
    COMPACTION_AUDIT_CONTRACT,
    COMPACTION_CALIBRATION_ALGORITHM,
    ROW_GROUP_ROWS,
    CandleDatasetSpec,
    CapacityBudget,
    HostSnapshot,
    PublicationError,
    PublicationPaths,
    PublishedDataset,
    _assert_fresh,
    _assert_resources,
    _assert_volume_contains,
    _file_stats,
    _fsync_file,
    _load_json_object,
    _logical_table_sha256,
    _parquet_facts,
    _paths,
    _target_classification,
    _write_exclusive,
    load_committed_candle_table,
    verify_committed_candle_dataset,
)

COMPACTION_PUBLICATION_CONTRACT: Final = "grid.canonical-candle-compaction-publication/v1"
CALIBRATION_MAX_ROWS: Final = 1_000_000


@dataclass(frozen=True, slots=True)
class CandleCompactionPlan:
    """Complete no-mutation plan for one month/bucket compaction transition."""

    spec: CandleDatasetSpec
    parents: tuple[PublishedDataset, ...]
    table: pa.Table
    partition_path: PurePosixPath
    budget: CapacityBudget
    snapshot: HostSnapshot
    paths: PublicationPaths
    parent_manifest_sha256: tuple[str, ...]
    input_table_sha256: str
    request_sha256: str
    input_file_count: int
    rows_per_file_target: int
    expected_output_file_count: int
    calibration_rows: int
    calibration_bytes: int
    required_free_bytes: int
    planned_peak_memory_bytes: int
    existing_commit: bool


def _strictly_sorted_unique(table: pa.Table) -> bool:
    if table.num_rows < 2:
        return True
    left_ids = table.column("instrument_id").slice(0, table.num_rows - 1)
    right_ids = table.column("instrument_id").slice(1, table.num_rows - 1)
    left_times = table.column("open_time_ms").slice(0, table.num_rows - 1)
    right_times = table.column("open_time_ms").slice(1, table.num_rows - 1)
    ordered = pc.or_(
        pc.greater(right_ids, left_ids),
        pc.and_(pc.equal(right_ids, left_ids), pc.greater(right_times, left_times)),
    )
    return pc.all(ordered).as_py() is True


def _calibrate_rows_per_file(table: pa.Table) -> tuple[int, int, int]:
    calibration_rows = min(table.num_rows, CALIBRATION_MAX_ROWS)
    sample = table.slice(0, calibration_rows)
    sink = pa.BufferOutputStream()
    pq.write_table(
        sample,
        sink,
        compression=COMPRESSION,
        compression_level=COMPRESSION_LEVEL,
        row_group_size=min(ROW_GROUP_ROWS, calibration_rows),
        use_dictionary=("category", "source_id", "ingestion_id"),
        write_statistics=True,
        data_page_version="2.0",
        write_page_index=True,
    )
    calibration_bytes = int(sink.getvalue().size)
    if calibration_bytes <= 0:
        raise PublicationError("compaction calibration produced no bytes")
    raw_rows_per_file = max(
        1,
        (TARGET_FILE_SIZE_BYTES * calibration_rows) // calibration_bytes,
    )
    rows_per_file = max(
        ROW_GROUP_ROWS,
        math.ceil(raw_rows_per_file / ROW_GROUP_ROWS) * ROW_GROUP_ROWS,
    )
    return rows_per_file, calibration_rows, calibration_bytes


def _compaction_resources(
    table_bytes: int,
    budget: CapacityBudget,
) -> tuple[int, int]:
    workspace = max(2 * TARGET_FILE_SIZE_BYTES, 2 * table_bytes)
    required_free = (
        budget.active_and_building_bytes
        + budget.rest_staging_bytes
        + budget.operating_reserve_bytes
        + workspace
    )
    planned_memory = 128 * 1024**2 + 6 * table_bytes
    return required_free, planned_memory


def _verify_parents(
    parent_dataset_roots: tuple[Path, ...],
    spec: CandleDatasetSpec,
) -> tuple[PublishedDataset, ...]:
    if not parent_dataset_roots:
        raise PublicationError("compaction requires at least one parent dataset")
    by_id: dict[str, PublishedDataset] = {}
    for root in parent_dataset_roots:
        published = verify_committed_candle_dataset(root)
        if published.manifest.dataset_id in by_id:
            raise PublicationError("compaction parent dataset identities must be unique")
        by_id[published.manifest.dataset_id] = published
    if tuple(by_id) != spec.parent_dataset_ids:
        raise PublicationError("compaction parent order must match the declared lineage")
    parents = tuple(by_id[dataset_id] for dataset_id in spec.parent_dataset_ids)
    if any(parent.manifest.dataset_id == spec.dataset_id for parent in parents):
        raise PublicationError("compaction output cannot be its own parent")
    parent_types = {parent.manifest.dataset_type for parent in parents}
    parent_schemas = {parent.manifest.schema_version for parent in parents}
    if len(parent_types) != 1 or len(parent_schemas) != 1:
        raise PublicationError("compaction parents must share one dataset type and schema")
    if any(parent.receipt.manifest_sha256 not in spec.source_evidence_sha256 for parent in parents):
        raise PublicationError("compaction source evidence does not bind every parent manifest")
    return parents


def _estimated_parent_table_bytes(parents: tuple[PublishedDataset, ...]) -> int:
    total = 0
    for parent in parents:
        for item in parent.manifest.files:
            parquet = pq.ParquetFile(parent.dataset_root / item.path)
            try:
                metadata = parquet.metadata
                total += sum(
                    metadata.row_group(index).total_byte_size
                    for index in range(metadata.num_row_groups)
                )
            finally:
                parquet.close()
    if total <= 0:
        raise PublicationError("compaction parents have no estimated uncompressed bytes")
    return total


def _load_parent_tables(parents: tuple[PublishedDataset, ...]) -> tuple[pa.Table, ...]:
    tables = []
    for parent in parents:
        files = [pq.read_table(parent.dataset_root / item.path) for item in parent.manifest.files]
        table = pa.concat_tables(files) if len(files) > 1 else files[0]
        verify_canonical_candle_schema(table.schema, parent.manifest.dataset_type)
        tables.append(table)
    if any(not table.schema.equals(tables[0].schema, check_metadata=True) for table in tables[1:]):
        raise PublicationError("compaction parent Arrow schemas differ")
    return tuple(tables)


def preflight_candle_compaction(
    store_root: Path,
    parent_dataset_roots: tuple[Path, ...],
    spec: CandleDatasetSpec,
    budget: CapacityBudget,
    snapshot: HostSnapshot,
    *,
    now_ms: int,
) -> CandleCompactionPlan:
    """Verify parents, logical union, resources, and identity without mutation."""

    parents = _verify_parents(parent_dataset_roots, spec)
    provisional_paths = _paths(store_root, spec, "0" * 64)
    _assert_fresh(snapshot, now_ms=now_ms)
    _assert_volume_contains(provisional_paths, snapshot)
    estimated_table_bytes = _estimated_parent_table_bytes(parents)
    estimated_required_free, estimated_peak_memory = _compaction_resources(
        estimated_table_bytes,
        budget,
    )
    _assert_resources(
        snapshot,
        required_free_bytes=estimated_required_free,
        planned_peak_memory_bytes=estimated_peak_memory,
    )
    tables = _load_parent_tables(parents)
    dataset_type = parents[0].manifest.dataset_type
    partition_paths = {
        PurePosixPath(item.path).parent for parent in parents for item in parent.manifest.files
    }
    if len(partition_paths) != 1:
        raise PublicationError("compaction parents must belong to one month/bucket partition")
    table = (
        pa.concat_tables(tables)
        .sort_by([("instrument_id", "ascending"), ("open_time_ms", "ascending")])
        .combine_chunks()
    )
    verify_canonical_candle_schema(table.schema, dataset_type)
    if not _strictly_sorted_unique(table):
        raise PublicationError("compaction parents contain duplicate or conflicting keys")
    input_file_count = sum(len(parent.manifest.files) for parent in parents)
    if input_file_count < 2:
        raise PublicationError("compaction requires at least two input fragments")
    rows_per_file, calibration_rows, calibration_bytes = _calibrate_rows_per_file(table)
    expected_output_files = math.ceil(table.num_rows / rows_per_file)
    if expected_output_files >= input_file_count:
        raise PublicationError("compaction would not reduce the input fragment count")
    input_hash = _logical_table_sha256(table)
    parent_hashes = tuple(parent.receipt.manifest_sha256 for parent in parents)
    request_hash = canonical_sha256(
        {
            "contract": COMPACTION_PUBLICATION_CONTRACT,
            "calibration_algorithm": COMPACTION_CALIBRATION_ALGORITHM,
            "input_table_sha256": input_hash,
            "parent_manifests": [
                {
                    "dataset_id": parent.manifest.dataset_id,
                    "manifest_sha256": parent.receipt.manifest_sha256,
                }
                for parent in parents
            ],
            "partition_path": next(iter(partition_paths)).as_posix(),
            "rows_per_file_target": rows_per_file,
            "spec": spec,
            "target_file_bytes": TARGET_FILE_SIZE_BYTES,
        }
    )
    paths = _paths(store_root, spec, request_hash)
    _assert_volume_contains(paths, snapshot)
    required_free, planned_memory = _compaction_resources(table.nbytes, budget)
    _assert_resources(
        snapshot,
        required_free_bytes=required_free,
        planned_peak_memory_bytes=planned_memory,
    )
    if paths.store_root.exists() and paths.store_root.is_symlink():
        raise PublicationError("market store cannot be a symlink")
    if paths.building_root.exists():
        raise PublicationError(f"stale building output detected: {paths.building_root}")
    existing = paths.dataset_root.exists()
    if existing:
        published = verify_compacted_candle_dataset(paths.dataset_root)
        audit = _load_json_object(published.audit_path)
        if (
            published.manifest.dataset_id != spec.dataset_id
            or published.manifest.parent_dataset_ids != spec.parent_dataset_ids
            or published.manifest.source_evidence_sha256 != spec.source_evidence_sha256
            or published.manifest.build_config_sha256 != spec.build_config_sha256
            or published.manifest.software_identity != spec.software_identity
            or audit.get("request_sha256") != request_hash
            or audit.get("input_table_sha256") != input_hash
        ):
            raise PublicationError(
                "compaction identity already exists with different content or evidence"
            )
    return CandleCompactionPlan(
        spec=spec,
        parents=parents,
        table=table,
        partition_path=next(iter(partition_paths)),
        budget=budget,
        snapshot=snapshot,
        paths=paths,
        parent_manifest_sha256=parent_hashes,
        input_table_sha256=input_hash,
        request_sha256=request_hash,
        input_file_count=input_file_count,
        rows_per_file_target=rows_per_file,
        expected_output_file_count=expected_output_files,
        calibration_rows=calibration_rows,
        calibration_bytes=calibration_bytes,
        required_free_bytes=required_free,
        planned_peak_memory_bytes=planned_memory,
        existing_commit=existing,
    )


def _parent_inventory(plan: CandleCompactionPlan) -> list[dict[str, object]]:
    return [
        {
            "dataset_id": parent.manifest.dataset_id,
            "manifest_sha256": parent.receipt.manifest_sha256,
        }
        for parent in plan.parents
    ]


def _verify_parents_unchanged(plan: CandleCompactionPlan) -> None:
    for parent, expected_hash in zip(
        plan.parents,
        plan.parent_manifest_sha256,
        strict=True,
    ):
        verified = verify_committed_candle_dataset(parent.dataset_root)
        if verified.receipt.manifest_sha256 != expected_hash:
            raise PublicationError("compaction parent changed after preflight")


def publish_compacted_candle_dataset(
    plan: CandleCompactionPlan,
    fresh_snapshot: HostSnapshot,
    *,
    committed_at_ms: int,
) -> PublishedDataset:
    """Write a new immutable child and its completion receipt last."""

    if plan.existing_commit:
        return verify_compacted_candle_dataset(plan.paths.dataset_root)
    _assert_fresh(fresh_snapshot, now_ms=committed_at_ms)
    _assert_volume_contains(plan.paths, fresh_snapshot)
    if (
        fresh_snapshot.device_identity_sha256 != plan.snapshot.device_identity_sha256
        or fresh_snapshot.memory_total_bytes != plan.snapshot.memory_total_bytes
    ):
        raise PublicationError("host or storage identity changed after compaction preflight")
    _assert_resources(
        fresh_snapshot,
        required_free_bytes=plan.required_free_bytes,
        planned_peak_memory_bytes=plan.planned_peak_memory_bytes,
    )
    _verify_parents_unchanged(plan)
    if plan.paths.dataset_root.exists():
        raise PublicationError("compaction dataset identity appeared after preflight")
    if plan.paths.building_root.exists():
        raise PublicationError("compaction building identity appeared after preflight")

    plan.paths.store_root.mkdir(parents=True, exist_ok=True)
    (plan.paths.store_root / ".building").mkdir(exist_ok=True)
    (plan.paths.store_root / "datasets").mkdir(exist_ok=True)
    plan.paths.building_root.mkdir()
    partition_root = plan.paths.building_root.joinpath(*plan.partition_path.parts)
    partition_root.mkdir(parents=True)
    files = []
    row_group_count = 0
    for index, offset in enumerate(range(0, plan.table.num_rows, plan.rows_per_file_target)):
        table = plan.table.slice(offset, plan.rows_per_file_target)
        temporary = partition_root / f"part-{index:05d}.parquet.tmp"
        pq.write_table(
            table,
            temporary,
            compression=COMPRESSION,
            compression_level=COMPRESSION_LEVEL,
            row_group_size=min(ROW_GROUP_ROWS, table.num_rows),
            use_dictionary=("category", "source_id", "ingestion_id"),
            write_statistics=True,
            data_page_version="2.0",
            write_page_index=True,
        )
        _fsync_file(temporary)
        digest = sha256_file(temporary)
        path = partition_root / f"part-{index:05d}-{digest}.parquet"
        os.replace(temporary, path)
        facts = _parquet_facts(
            path,
            plan.parents[0].manifest.dataset_type,
            expected_rows=table.num_rows,
        )
        row_group_count += facts.row_group_count
        batch = CanonicalCandleBatch(
            dataset_type=plan.parents[0].manifest.dataset_type,
            partition_path=plan.partition_path,
            table=table,
        )
        files.append(_file_stats(batch, plan.partition_path / path.name, path))
    if len(files) != plan.expected_output_file_count:
        raise PublicationError("compaction output file count differs from preflight")
    tail_count = int(files[-1].row_count < plan.rows_per_file_target)
    file_inventory = [
        {
            "classification": _target_classification(item.size_bytes),
            "is_tail": index == len(files) - 1 and bool(tail_count),
            "observed_bytes": item.size_bytes,
            "path": item.path,
            "row_count": item.row_count,
        }
        for index, item in enumerate(files)
    ]
    target_band_non_tail = sum(
        item["classification"] == "target-band" and item["is_tail"] is False
        for item in file_inventory
    )
    audit = {
        "audit_contract": COMPACTION_AUDIT_CONTRACT,
        "calibration": {
            "algorithm": COMPACTION_CALIBRATION_ALGORITHM,
            "maximum_sample_rows": CALIBRATION_MAX_ROWS,
            "sample_compressed_bytes": plan.calibration_bytes,
            "sample_row_count": plan.calibration_rows,
        },
        "capacity_evidence_sha256": plan.spec.capacity_evidence_sha256,
        "compaction": {
            "input_file_count": plan.input_file_count,
            "output_file_count": len(files),
            "output_total_bytes": sum(item.size_bytes for item in files),
            "rows_per_file_target": plan.rows_per_file_target,
            "tail_file_count": tail_count,
            "target_band_non_tail_file_count": target_band_non_tail,
            "target_file_bytes": TARGET_FILE_SIZE_BYTES,
        },
        "coverage_evidence_sha256": plan.spec.coverage_evidence_sha256,
        "dataset_id": plan.spec.dataset_id,
        "dataset_type": plan.parents[0].manifest.dataset_type,
        "files": file_inventory,
        "host_preflight": {
            "device_identity_sha256": plan.snapshot.device_identity_sha256,
            "memory_available_bytes": plan.snapshot.memory_available_bytes,
            "memory_total_bytes": plan.snapshot.memory_total_bytes,
            "observed_at_ms": plan.snapshot.observed_at_ms,
            "observed_free_bytes": plan.snapshot.volume_free_bytes,
            "planned_peak_memory_bytes": plan.planned_peak_memory_bytes,
            "required_free_bytes": plan.required_free_bytes,
            "storage_kind": plan.snapshot.storage_kind,
        },
        "input_table_sha256": plan.input_table_sha256,
        "layout_contract": CANONICAL_LAYOUT_ID,
        "output_table_sha256": plan.input_table_sha256,
        "parent_manifests": _parent_inventory(plan),
        "parquet": {
            "compression": COMPRESSION,
            "compression_level": COMPRESSION_LEVEL,
            "row_group_count": row_group_count,
            "row_group_rows": ROW_GROUP_ROWS,
        },
        "partition_path": plan.partition_path.as_posix(),
        "quality_checks": {
            "canonical_schema_verified": True,
            "file_hashes_recorded": True,
            "globally_sorted_unique_keys": True,
            "logical_table_sha256_preserved": True,
            "parent_datasets_unchanged": True,
            "parquet_footers_verified": True,
            "single_partition": True,
        },
        "request_sha256": plan.request_sha256,
    }
    audit_path = plan.paths.building_root / "audit.json"
    _write_exclusive(audit_path, canonical_json_bytes(audit))
    audit_sha = sha256_file(audit_path)
    times = cast(dict[str, int], pc.min_max(plan.table.column("open_time_ms")).as_py())
    manifest = DatasetManifest(
        dataset_id=plan.spec.dataset_id,
        dataset_type=plan.parents[0].manifest.dataset_type,
        schema_version=plan.spec.schema_version,
        semantic_version=plan.spec.semantic_version,
        status=DatasetStatus.COMPLETE,
        parent_dataset_ids=plan.spec.parent_dataset_ids,
        instrument_count=int(pc.count_distinct(plan.table.column("instrument_id")).as_py()),
        row_count=plan.table.num_rows,
        min_time_ms=times["min"],
        max_time_ms=times["max"],
        files=tuple(files),
        source_evidence_sha256=plan.spec.source_evidence_sha256,
        build_config_sha256=plan.spec.build_config_sha256,
        software_identity=plan.spec.software_identity,
        audit_report_sha256=(audit_sha,),
        committed_at_ms=committed_at_ms,
    )
    manifest_path = plan.paths.building_root / "manifest.json"
    _write_exclusive(manifest_path, canonical_json_bytes(manifest))
    receipt = CompletionReceipt(
        dataset_id=plan.spec.dataset_id,
        manifest_sha256=sha256_file(manifest_path),
        status=DatasetStatus.COMPLETE,
        committed_at_ms=committed_at_ms,
    )
    os.replace(plan.paths.building_root, plan.paths.dataset_root)
    receipt_tmp = plan.paths.dataset_root / ".completion-receipt.json.tmp"
    _write_exclusive(receipt_tmp, canonical_json_bytes(receipt))
    os.replace(receipt_tmp, plan.paths.dataset_root / "completion-receipt.json")
    return verify_compacted_candle_dataset(plan.paths.dataset_root)


def verify_compacted_candle_dataset(dataset_root: Path) -> PublishedDataset:
    """Verify compacted output plus exact logical equality with immutable parents."""

    published = verify_committed_candle_dataset(dataset_root)
    audit = _load_json_object(published.audit_path)
    if audit.get("audit_contract") != COMPACTION_AUDIT_CONTRACT:
        raise PublicationError("dataset is not a canonical compaction publication")
    parent_inventory = audit.get("parent_manifests")
    if not isinstance(parent_inventory, list):
        raise PublicationError("compaction parent inventory is missing")
    dataset_container = published.dataset_root.parent
    parent_tables = []
    input_file_count = 0
    for dataset_id, binding in zip(
        published.manifest.parent_dataset_ids,
        parent_inventory,
        strict=True,
    ):
        if not isinstance(binding, dict) or binding.get("dataset_id") != dataset_id:
            raise PublicationError("compaction parent binding is invalid")
        parent, table = load_committed_candle_table(dataset_container / dataset_id)
        if parent.receipt.manifest_sha256 != binding.get("manifest_sha256"):
            raise PublicationError("compaction parent manifest no longer matches")
        parent_tables.append(table)
        input_file_count += len(parent.manifest.files)
    compacted = pa.concat_tables(
        [pq.read_table(published.dataset_root / item.path) for item in published.manifest.files]
    ).combine_chunks()
    source = (
        pa.concat_tables(parent_tables)
        .sort_by([("instrument_id", "ascending"), ("open_time_ms", "ascending")])
        .combine_chunks()
    )
    if not _strictly_sorted_unique(source):
        raise PublicationError("compaction parent union is no longer unique")
    compaction_facts = audit.get("compaction")
    calibration = audit.get("calibration")
    calibrated = _calibrate_rows_per_file(source)
    if (
        not isinstance(compaction_facts, dict)
        or not isinstance(calibration, dict)
        or compaction_facts.get("input_file_count") != input_file_count
        or compaction_facts.get("rows_per_file_target") != calibrated[0]
        or calibration.get("sample_row_count") != calibrated[1]
        or calibration.get("sample_compressed_bytes") != calibrated[2]
        or _logical_table_sha256(source) != audit.get("input_table_sha256")
        or not source.equals(compacted, check_metadata=True)
    ):
        raise PublicationError("compaction output does not exactly preserve its parent union")
    return published
