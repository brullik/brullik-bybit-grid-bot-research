"""Fail-closed, receipt-last publication for one canonical funding partition."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, cast

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.compute as pc  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file
from grid_contracts.market import (
    CompletionReceipt,
    DatasetFile,
    DatasetManifest,
    DatasetStatus,
    DatasetType,
)

from grid_market_store.physical import (
    COMPRESSION,
    COMPRESSION_LEVEL,
    FUNDING_CANONICAL_LAYOUT_ID,
    TARGET_FILE_SIZE_BYTES,
    CanonicalFundingBatch,
    canonical_funding_partition_path,
    verify_canonical_funding_schema,
)
from grid_market_store.publication import (
    DATASET_ID_RE,
    ROW_GROUP_ROWS,
    SHA256_RE,
    CapacityBudget,
    HostSnapshot,
    PublicationError,
    PublicationPaths,
    PublishedDataset,
    _assert_fresh,
    _assert_resources,
    _assert_volume_contains,
    _fsync_file,
    _load_json_object,
    _load_manifest,
    _load_receipt,
    _safe_dataset_file,
    _table_sha256,
    _target_classification,
    _write_exclusive,
)

FUNDING_AUDIT_CONTRACT: Final = "grid.canonical-funding-audit/v1"
FUNDING_PUBLICATION_CONTRACT: Final = "grid.canonical-funding-publication/v1"


@dataclass(frozen=True, slots=True)
class FundingDatasetSpec:
    """Immutable funding identity and explicit boundary/source evidence bindings."""

    dataset_id: str
    semantic_version: str
    parent_dataset_ids: tuple[str, ...]
    source_evidence_sha256: tuple[str, ...]
    coverage_evidence_sha256: str
    boundary_evidence_sha256: str
    capacity_evidence_sha256: str
    build_config_sha256: str
    software_identity: str
    schema_version: str = "v1"

    def __post_init__(self) -> None:
        if not DATASET_ID_RE.fullmatch(self.dataset_id):
            raise PublicationError("dataset_id must be a safe lowercase storage identity")
        for name in ("schema_version", "semantic_version", "software_identity"):
            value = getattr(self, name)
            if not value or value.strip() != value:
                raise PublicationError(f"{name} must be non-empty and trimmed")
        if len(self.parent_dataset_ids) != len(set(self.parent_dataset_ids)):
            raise PublicationError("parent_dataset_ids must be unique")
        if any(not value or value.strip() != value for value in self.parent_dataset_ids):
            raise PublicationError("parent dataset identities must be non-empty and trimmed")
        if not self.source_evidence_sha256:
            raise PublicationError("at least one source evidence digest is required")
        if len(self.source_evidence_sha256) != len(set(self.source_evidence_sha256)):
            raise PublicationError("source evidence digests must be unique")
        for value in (
            *self.source_evidence_sha256,
            self.coverage_evidence_sha256,
            self.boundary_evidence_sha256,
            self.capacity_evidence_sha256,
            self.build_config_sha256,
        ):
            if not SHA256_RE.fullmatch(value):
                raise PublicationError(
                    "evidence and configuration hashes must be lowercase SHA-256"
                )
        for name in ("coverage_evidence_sha256", "boundary_evidence_sha256"):
            if getattr(self, name) not in self.source_evidence_sha256:
                raise PublicationError(f"{name} must be included in source evidence")


@dataclass(frozen=True, slots=True)
class FundingPublicationPlan:
    """Machine-verifiable result of the no-mutation funding preflight."""

    spec: FundingDatasetSpec
    batch: CanonicalFundingBatch
    budget: CapacityBudget
    snapshot: HostSnapshot
    paths: PublicationPaths
    input_table_sha256: str
    request_sha256: str
    required_free_bytes: int
    planned_peak_memory_bytes: int
    existing_commit: bool


@dataclass(frozen=True, slots=True)
class _FundingParquetFacts:
    row_count: int
    row_group_count: int
    instrument_count: int
    min_time_ms: int
    max_time_ms: int
    min_instrument_id: int
    max_instrument_id: int
    instrument_ids: frozenset[int]
    partition_path: str


def _required_resources(
    batch: CanonicalFundingBatch,
    budget: CapacityBudget,
) -> tuple[int, int]:
    write_workspace = max(2 * TARGET_FILE_SIZE_BYTES, 2 * batch.table.nbytes)
    required_free = (
        budget.active_and_building_bytes
        + budget.rest_staging_bytes
        + budget.operating_reserve_bytes
        + write_workspace
    )
    planned_memory = 64 * 1024**2 + 3 * batch.table.nbytes
    return required_free, planned_memory


def _funding_paths(
    store_root: Path,
    spec: FundingDatasetSpec,
    request_sha256: str,
) -> PublicationPaths:
    resolved = store_root.resolve()
    return PublicationPaths(
        store_root=resolved,
        building_root=resolved / ".building" / f"{spec.dataset_id}--{request_sha256[:16]}",
        dataset_root=resolved / "datasets" / spec.dataset_id,
    )


def _request_sha256(
    spec: FundingDatasetSpec,
    batch: CanonicalFundingBatch,
    input_hash: str,
) -> str:
    return canonical_sha256(
        {
            "contract": FUNDING_PUBLICATION_CONTRACT,
            "dataset_type": DatasetType.FUNDING_EVENT,
            "input_table_sha256": input_hash,
            "partition_path": batch.partition_path.as_posix(),
            "spec": spec,
        }
    )


def preflight_funding_dataset(
    store_root: Path,
    spec: FundingDatasetSpec,
    batch: CanonicalFundingBatch,
    budget: CapacityBudget,
    snapshot: HostSnapshot,
    *,
    now_ms: int,
) -> FundingPublicationPlan:
    """Validate funding identity, layout, host, capacity, and collisions without mutation."""

    if now_ms < 0:
        raise PublicationError("preflight time cannot be negative")
    verify_canonical_funding_schema(batch.table.schema)
    input_hash = _table_sha256(batch.table)
    request_hash = _request_sha256(spec, batch, input_hash)
    paths = _funding_paths(store_root, spec, request_hash)
    _assert_fresh(snapshot, now_ms=now_ms)
    _assert_volume_contains(paths, snapshot)
    required_free, planned_memory = _required_resources(batch, budget)
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
        published = verify_committed_funding_dataset(paths.dataset_root)
        audit = _load_json_object(published.audit_path)
        if (
            published.manifest.dataset_id != spec.dataset_id
            or published.manifest.dataset_type is not DatasetType.FUNDING_EVENT
            or published.manifest.schema_version != spec.schema_version
            or published.manifest.semantic_version != spec.semantic_version
            or published.manifest.parent_dataset_ids != spec.parent_dataset_ids
            or published.manifest.source_evidence_sha256 != spec.source_evidence_sha256
            or published.manifest.build_config_sha256 != spec.build_config_sha256
            or published.manifest.software_identity != spec.software_identity
            or audit.get("request_sha256") != request_hash
            or audit.get("input_table_sha256") != input_hash
        ):
            raise PublicationError(
                "dataset identity already exists with different content or evidence"
            )
    return FundingPublicationPlan(
        spec=spec,
        batch=batch,
        budget=budget,
        snapshot=snapshot,
        paths=paths,
        input_table_sha256=input_hash,
        request_sha256=request_hash,
        required_free_bytes=required_free,
        planned_peak_memory_bytes=planned_memory,
        existing_commit=existing,
    )


def _funding_file_stats(
    batch: CanonicalFundingBatch,
    relative_path: PurePosixPath,
    path: Path,
) -> DatasetFile:
    times = cast(dict[str, int], pc.min_max(batch.table.column("funding_time_ms")).as_py())
    instruments = cast(dict[str, int], pc.min_max(batch.table.column("instrument_id")).as_py())
    return DatasetFile(
        path=relative_path.as_posix(),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
        row_count=batch.table.num_rows,
        min_time_ms=times["min"],
        max_time_ms=times["max"],
        min_instrument_id=instruments["min"],
        max_instrument_id=instruments["max"],
    )


def _funding_parquet_facts(
    path: Path,
    *,
    expected_rows: int,
) -> _FundingParquetFacts:
    parquet = pq.ParquetFile(path)
    try:
        verify_canonical_funding_schema(parquet.schema_arrow)
        metadata = parquet.metadata
        if metadata.num_rows != expected_rows:
            raise PublicationError("Parquet footer row count does not match its inventory")
        for row_group_index in range(metadata.num_row_groups):
            row_group = metadata.row_group(row_group_index)
            for column_index in range(row_group.num_columns):
                if row_group.column(column_index).compression.lower() != COMPRESSION:
                    raise PublicationError("Parquet footer compression does not match ZSTD-3")
        row_group_count = metadata.num_row_groups
    finally:
        parquet.close()
    keys = pq.read_table(
        path,
        columns=["instrument_id", "funding_time_ms", "funding_interval_minutes"],
    )
    instrument_ids = cast(list[int], keys.column("instrument_id").to_pylist())
    funding_times = cast(list[int], keys.column("funding_time_ms").to_pylist())
    funding_intervals = cast(list[int], keys.column("funding_interval_minutes").to_pylist())
    if any(timestamp < 0 or timestamp % 60_000 for timestamp in funding_times):
        raise PublicationError("Parquet funding timestamps are not exact UTC minutes")
    if any(interval <= 0 for interval in funding_intervals):
        raise PublicationError("Parquet funding intervals must be positive")
    for index in range(1, keys.num_rows):
        previous_key = (instrument_ids[index - 1], funding_times[index - 1])
        current_key = (instrument_ids[index], funding_times[index])
        if current_key <= previous_key:
            raise PublicationError("Parquet funding keys are not strictly sorted and unique")
        if instrument_ids[index] == instrument_ids[index - 1] and (
            funding_times[index] - funding_times[index - 1] != funding_intervals[index] * 60_000
        ):
            raise PublicationError(
                "Parquet funding interval does not match the previous settlement"
            )
    times = cast(dict[str, int], pc.min_max(keys.column("funding_time_ms")).as_py())
    instruments = cast(dict[str, int], pc.min_max(keys.column("instrument_id")).as_py())
    unique_instruments = frozenset(instrument_ids)
    partition_paths = {
        canonical_funding_partition_path(
            instrument_id=instrument_id,
            funding_time_ms=funding_time_ms,
        ).as_posix()
        for instrument_id, funding_time_ms in zip(
            instrument_ids,
            funding_times,
            strict=True,
        )
    }
    if len(partition_paths) != 1:
        raise PublicationError("Parquet funding rows do not fit one month/bucket partition")
    return _FundingParquetFacts(
        row_count=keys.num_rows,
        row_group_count=row_group_count,
        instrument_count=len(unique_instruments),
        min_time_ms=times["min"],
        max_time_ms=times["max"],
        min_instrument_id=instruments["min"],
        max_instrument_id=instruments["max"],
        instrument_ids=unique_instruments,
        partition_path=next(iter(partition_paths)),
    )


def _build_audit(
    plan: FundingPublicationPlan,
    dataset_file: DatasetFile,
    *,
    parquet_row_groups: int,
) -> dict[str, object]:
    return {
        "audit_contract": FUNDING_AUDIT_CONTRACT,
        "boundary_evidence_sha256": plan.spec.boundary_evidence_sha256,
        "capacity_evidence_sha256": plan.spec.capacity_evidence_sha256,
        "coverage_evidence_sha256": plan.spec.coverage_evidence_sha256,
        "dataset_id": plan.spec.dataset_id,
        "dataset_type": DatasetType.FUNDING_EVENT,
        "file_target": {
            "classification": _target_classification(dataset_file.size_bytes),
            "observed_bytes": dataset_file.size_bytes,
            "target_bytes": TARGET_FILE_SIZE_BYTES,
        },
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
        "layout_contract": FUNDING_CANONICAL_LAYOUT_ID,
        "parquet": {
            "compression": COMPRESSION,
            "compression_level": COMPRESSION_LEVEL,
            "row_group_count": parquet_row_groups,
            "row_group_rows": ROW_GROUP_ROWS,
        },
        "partition_path": plan.batch.partition_path.as_posix(),
        "quality_checks": {
            "canonical_schema_verified": True,
            "file_hash_recorded": True,
            "funding_timestamps_minute_aligned": True,
            "internal_interval_deltas_verified": True,
            "parquet_footer_verified": True,
            "single_partition": True,
            "sorted_unique_keys": True,
            "upstream_boundary_interval_evidence_bound": True,
            "upstream_coverage_evidence_bound": True,
        },
        "request_sha256": plan.request_sha256,
    }


def publish_funding_dataset(
    plan: FundingPublicationPlan,
    fresh_snapshot: HostSnapshot,
    *,
    committed_at_ms: int,
) -> PublishedDataset:
    """Publish funding atomically after a second host check; write the receipt last."""

    if plan.existing_commit:
        return verify_committed_funding_dataset(plan.paths.dataset_root)
    _assert_fresh(fresh_snapshot, now_ms=committed_at_ms)
    _assert_volume_contains(plan.paths, fresh_snapshot)
    if (
        fresh_snapshot.device_identity_sha256 != plan.snapshot.device_identity_sha256
        or fresh_snapshot.memory_total_bytes != plan.snapshot.memory_total_bytes
    ):
        raise PublicationError("host or storage identity changed after preflight")
    _assert_resources(
        fresh_snapshot,
        required_free_bytes=plan.required_free_bytes,
        planned_peak_memory_bytes=plan.planned_peak_memory_bytes,
    )
    if plan.paths.dataset_root.exists():
        raise PublicationError("dataset identity appeared after preflight")
    if plan.paths.building_root.exists():
        raise PublicationError("building identity appeared after preflight")

    plan.paths.store_root.mkdir(parents=True, exist_ok=True)
    (plan.paths.store_root / ".building").mkdir(exist_ok=True)
    (plan.paths.store_root / "datasets").mkdir(exist_ok=True)
    plan.paths.building_root.mkdir()
    partition_root = plan.paths.building_root.joinpath(*plan.batch.partition_path.parts)
    partition_root.mkdir(parents=True)
    temporary_parquet = partition_root / "part.parquet.tmp"
    pq.write_table(
        plan.batch.table,
        temporary_parquet,
        compression=COMPRESSION,
        compression_level=COMPRESSION_LEVEL,
        row_group_size=min(ROW_GROUP_ROWS, plan.batch.table.num_rows),
        use_dictionary=("category", "source_id", "ingestion_id"),
        write_statistics=True,
        data_page_version="2.0",
        write_page_index=True,
    )
    _fsync_file(temporary_parquet)
    parquet_sha = sha256_file(temporary_parquet)
    parquet_path = partition_root / f"part-{parquet_sha}.parquet"
    os.replace(temporary_parquet, parquet_path)
    facts = _funding_parquet_facts(
        parquet_path,
        expected_rows=plan.batch.table.num_rows,
    )
    relative_parquet = plan.batch.partition_path / parquet_path.name
    dataset_file = _funding_file_stats(plan.batch, relative_parquet, parquet_path)
    audit = _build_audit(plan, dataset_file, parquet_row_groups=facts.row_group_count)
    audit_path = plan.paths.building_root / "audit.json"
    _write_exclusive(audit_path, canonical_json_bytes(audit))
    audit_sha = sha256_file(audit_path)
    manifest = DatasetManifest(
        dataset_id=plan.spec.dataset_id,
        dataset_type=DatasetType.FUNDING_EVENT,
        schema_version=plan.spec.schema_version,
        semantic_version=plan.spec.semantic_version,
        status=DatasetStatus.COMPLETE,
        parent_dataset_ids=plan.spec.parent_dataset_ids,
        instrument_count=facts.instrument_count,
        row_count=dataset_file.row_count,
        min_time_ms=dataset_file.min_time_ms,
        max_time_ms=dataset_file.max_time_ms,
        files=(dataset_file,),
        source_evidence_sha256=plan.spec.source_evidence_sha256,
        build_config_sha256=plan.spec.build_config_sha256,
        software_identity=plan.spec.software_identity,
        audit_report_sha256=(audit_sha,),
        committed_at_ms=committed_at_ms,
    )
    manifest_path = plan.paths.building_root / "manifest.json"
    _write_exclusive(manifest_path, canonical_json_bytes(manifest))
    manifest_sha = sha256_file(manifest_path)
    receipt = CompletionReceipt(
        dataset_id=plan.spec.dataset_id,
        manifest_sha256=manifest_sha,
        status=DatasetStatus.COMPLETE,
        committed_at_ms=committed_at_ms,
    )
    os.replace(plan.paths.building_root, plan.paths.dataset_root)
    receipt_path = plan.paths.dataset_root / "completion-receipt.json"
    receipt_tmp = plan.paths.dataset_root / ".completion-receipt.json.tmp"
    _write_exclusive(receipt_tmp, canonical_json_bytes(receipt))
    os.replace(receipt_tmp, receipt_path)
    return verify_committed_funding_dataset(plan.paths.dataset_root)


def verify_committed_funding_dataset(dataset_root: Path) -> PublishedDataset:
    """Verify a receipt-committed funding dataset, exact files, schema, and audit."""

    root = dataset_root.resolve()
    if not root.is_dir() or root.is_symlink():
        raise PublicationError("committed dataset root is missing or unsafe")
    entries = tuple(root.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise PublicationError("committed dataset cannot contain symlinks")
    manifest_path = root / "manifest.json"
    audit_path = root / "audit.json"
    receipt_path = root / "completion-receipt.json"
    if not receipt_path.is_file():
        raise PublicationError("dataset has no completion receipt and is not committed")
    manifest = _load_manifest(manifest_path)
    receipt = _load_receipt(receipt_path)
    if (
        root.name != manifest.dataset_id
        or receipt.dataset_id != manifest.dataset_id
        or receipt.committed_at_ms != manifest.committed_at_ms
        or receipt.manifest_sha256 != sha256_file(manifest_path)
    ):
        raise PublicationError("completion receipt does not bind the manifest")
    if manifest.dataset_type is not DatasetType.FUNDING_EVENT:
        raise PublicationError("funding verifier requires a funding_event dataset")
    if len(manifest.files) != 1:
        raise PublicationError("bounded funding publication requires exactly one Parquet file")
    audit_sha = sha256_file(audit_path)
    if manifest.audit_report_sha256 != (audit_sha,):
        raise PublicationError("manifest does not bind the canonical funding audit")
    audit = _load_json_object(audit_path)
    if canonical_json_bytes(audit) != audit_path.read_bytes():
        raise PublicationError("funding audit is not canonical JSON")
    expected_quality_checks = {
        "canonical_schema_verified": True,
        "file_hash_recorded": True,
        "funding_timestamps_minute_aligned": True,
        "internal_interval_deltas_verified": True,
        "parquet_footer_verified": True,
        "single_partition": True,
        "sorted_unique_keys": True,
        "upstream_boundary_interval_evidence_bound": True,
        "upstream_coverage_evidence_bound": True,
    }
    if (
        audit.get("audit_contract") != FUNDING_AUDIT_CONTRACT
        or audit.get("dataset_id") != manifest.dataset_id
        or audit.get("dataset_type") != DatasetType.FUNDING_EVENT.value
        or audit.get("layout_contract") != FUNDING_CANONICAL_LAYOUT_ID
        or audit.get("quality_checks") != expected_quality_checks
    ):
        raise PublicationError("canonical funding audit identity does not match the manifest")
    item = manifest.files[0]
    path = _safe_dataset_file(root, item.path)
    if (
        not path.is_file()
        or path.stat().st_size != item.size_bytes
        or sha256_file(path) != item.sha256
    ):
        raise PublicationError(f"dataset file hash or size mismatch: {item.path}")
    facts = _funding_parquet_facts(path, expected_rows=item.row_count)
    if (
        item.min_time_ms != facts.min_time_ms
        or item.max_time_ms != facts.max_time_ms
        or item.min_instrument_id != facts.min_instrument_id
        or item.max_instrument_id != facts.max_instrument_id
    ):
        raise PublicationError("funding dataset file key statistics mismatch")
    parent = PurePosixPath(item.path).parent
    partition_path = parent.as_posix()
    if partition_path != facts.partition_path:
        raise PublicationError("funding file path does not match its canonical keys")
    expected_directories: set[str] = set()
    while parent != PurePosixPath("."):
        expected_directories.add(parent.as_posix())
        parent = parent.parent
    expected_files = {
        "audit.json",
        "manifest.json",
        "completion-receipt.json",
        item.path,
    }
    actual_files = {path.relative_to(root).as_posix() for path in entries if path.is_file()}
    actual_directories = {path.relative_to(root).as_posix() for path in entries if path.is_dir()}
    if actual_files != expected_files or actual_directories != expected_directories:
        raise PublicationError("committed funding dataset contains orphan or missing paths")
    if (
        manifest.row_count != facts.row_count
        or manifest.instrument_count != facts.instrument_count
        or manifest.min_time_ms != facts.min_time_ms
        or manifest.max_time_ms != facts.max_time_ms
    ):
        raise PublicationError("funding manifest statistics do not match Parquet")
    expected_file_target = {
        "classification": _target_classification(item.size_bytes),
        "observed_bytes": item.size_bytes,
        "target_bytes": TARGET_FILE_SIZE_BYTES,
    }
    expected_parquet = {
        "compression": COMPRESSION,
        "compression_level": COMPRESSION_LEVEL,
        "row_group_count": facts.row_group_count,
        "row_group_rows": ROW_GROUP_ROWS,
    }
    digest_fields = (
        audit.get("boundary_evidence_sha256"),
        audit.get("capacity_evidence_sha256"),
        audit.get("coverage_evidence_sha256"),
        audit.get("input_table_sha256"),
        audit.get("request_sha256"),
    )
    if (
        audit.get("file_target") != expected_file_target
        or audit.get("parquet") != expected_parquet
        or audit.get("partition_path") != partition_path
        or audit.get("coverage_evidence_sha256") not in manifest.source_evidence_sha256
        or audit.get("boundary_evidence_sha256") not in manifest.source_evidence_sha256
        or any(
            not isinstance(value, str) or not SHA256_RE.fullmatch(value) for value in digest_fields
        )
    ):
        raise PublicationError("canonical funding audit facts do not match Parquet or manifest")
    return PublishedDataset(
        dataset_root=root,
        manifest_path=manifest_path,
        audit_path=audit_path,
        receipt_path=receipt_path,
        manifest=manifest,
        receipt=receipt,
    )


def load_committed_funding_table(dataset_root: Path) -> pa.Table:
    """Verify one committed funding dataset before loading its exact Arrow table."""

    published = verify_committed_funding_dataset(dataset_root)
    table = pq.read_table(
        published.dataset_root / published.manifest.files[0].path,
    )
    verify_canonical_funding_schema(table.schema)
    return table
