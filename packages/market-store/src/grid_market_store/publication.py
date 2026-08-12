"""Fail-closed, receipt-last publication for one canonical candle partition."""

from __future__ import annotations

import hashlib
import json
import os
import re
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
    CANONICAL_LAYOUT_ID,
    COMPRESSION,
    COMPRESSION_LEVEL,
    TARGET_FILE_SIZE_BYTES,
    CanonicalCandleBatch,
    verify_canonical_candle_schema,
)

AUDIT_CONTRACT: Final = "grid.canonical-candle-audit/v1"
PUBLICATION_CONTRACT: Final = "grid.canonical-candle-publication/v1"
MIN_OPERATING_RESERVE_BYTES: Final = 8 * 1024**3
MAX_MEMORY_PERCENT: Final = 70
MAX_PREFLIGHT_AGE_MS: Final = 60_000
ROW_GROUP_ROWS: Final = 128_000
DATASET_ID_RE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_STORAGE_KINDS: Final = frozenset({"nvme", "ssd"})


class PublicationError(RuntimeError):
    """Publication cannot prove a safe, immutable transition."""


@dataclass(frozen=True, slots=True)
class CandleDatasetSpec:
    """Immutable dataset identity and upstream evidence bindings."""

    dataset_id: str
    semantic_version: str
    parent_dataset_ids: tuple[str, ...]
    source_evidence_sha256: tuple[str, ...]
    coverage_evidence_sha256: str
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
            self.capacity_evidence_sha256,
            self.build_config_sha256,
        ):
            if not SHA256_RE.fullmatch(value):
                raise PublicationError(
                    "evidence and configuration hashes must be lowercase SHA-256"
                )
        if self.coverage_evidence_sha256 not in self.source_evidence_sha256:
            raise PublicationError("coverage evidence must be included in source evidence")


@dataclass(frozen=True, slots=True)
class CapacityBudget:
    """Evidence-derived bytes that must coexist on the target volume."""

    active_and_building_bytes: int
    rest_staging_bytes: int
    operating_reserve_bytes: int = MIN_OPERATING_RESERVE_BYTES

    def __post_init__(self) -> None:
        if self.active_and_building_bytes < 0 or self.rest_staging_bytes < 0:
            raise PublicationError("capacity budget components cannot be negative")
        if self.operating_reserve_bytes < MIN_OPERATING_RESERVE_BYTES:
            raise PublicationError("operating reserve must be at least 8 GiB")


@dataclass(frozen=True, slots=True)
class HostSnapshot:
    """Fresh observation supplied by the public data application's system probe."""

    observed_at_ms: int
    memory_total_bytes: int
    memory_available_bytes: int
    storage_kind: str
    storage_device_id: str
    volume_root: Path
    volume_free_bytes: int

    def __post_init__(self) -> None:
        if self.observed_at_ms < 0:
            raise PublicationError("host snapshot timestamp cannot be negative")
        if (
            self.memory_total_bytes <= 0
            or not 0 <= self.memory_available_bytes <= self.memory_total_bytes
        ):
            raise PublicationError("host snapshot has invalid memory values")
        if self.storage_kind not in ALLOWED_STORAGE_KINDS:
            raise PublicationError("canonical writes require local NVMe or SSD storage")
        if not self.storage_device_id or self.storage_device_id.strip() != self.storage_device_id:
            raise PublicationError("storage device identity must be non-empty and trimmed")
        if self.volume_free_bytes < 0:
            raise PublicationError("volume free bytes cannot be negative")
        if not self.volume_root.is_absolute():
            raise PublicationError("volume_root must be absolute")

    @property
    def device_identity_sha256(self) -> str:
        return canonical_sha256(
            {
                "storage_device_id": self.storage_device_id,
                "storage_kind": self.storage_kind,
                "volume_root": str(self.volume_root.resolve()),
            }
        )


@dataclass(frozen=True, slots=True)
class PublicationPaths:
    store_root: Path
    building_root: Path
    dataset_root: Path


@dataclass(frozen=True, slots=True)
class PublicationPlan:
    """Machine-verifiable result of the no-mutation preflight."""

    spec: CandleDatasetSpec
    batch: CanonicalCandleBatch
    budget: CapacityBudget
    snapshot: HostSnapshot
    paths: PublicationPaths
    input_table_sha256: str
    request_sha256: str
    required_free_bytes: int
    planned_peak_memory_bytes: int
    existing_commit: bool


@dataclass(frozen=True, slots=True)
class PublishedDataset:
    dataset_root: Path
    manifest_path: Path
    audit_path: Path
    receipt_path: Path
    manifest: DatasetManifest
    receipt: CompletionReceipt


def _table_sha256(table: pa.Table) -> str:
    """Hash exact Arrow buffers without converting the batch into Python rows."""

    digest = hashlib.sha256()
    schema = table.schema.serialize().to_pybytes()
    digest.update(len(schema).to_bytes(8, "big"))
    digest.update(schema)
    digest.update(table.num_rows.to_bytes(8, "big"))
    for column in table.columns:
        digest.update(column.num_chunks.to_bytes(4, "big"))
        for chunk in column.chunks:
            digest.update(len(chunk).to_bytes(8, "big"))
            for buffer in chunk.buffers():
                if buffer is None:
                    digest.update(b"\xff" * 8)
                else:
                    digest.update(buffer.size.to_bytes(8, "big"))
                    digest.update(memoryview(buffer))
    return digest.hexdigest()


def _paths(store_root: Path, spec: CandleDatasetSpec, request_sha256: str) -> PublicationPaths:
    resolved = store_root.resolve()
    return PublicationPaths(
        store_root=resolved,
        building_root=resolved / ".building" / f"{spec.dataset_id}--{request_sha256[:16]}",
        dataset_root=resolved / "datasets" / spec.dataset_id,
    )


def _assert_fresh(snapshot: HostSnapshot, *, now_ms: int) -> None:
    age = now_ms - snapshot.observed_at_ms
    if age < 0 or age > MAX_PREFLIGHT_AGE_MS:
        raise PublicationError("host snapshot must be fresh and not future-dated")


def _assert_volume_contains(paths: PublicationPaths, snapshot: HostSnapshot) -> None:
    volume_root = snapshot.volume_root.resolve()
    if not paths.store_root.is_relative_to(volume_root):
        raise PublicationError("market store is not on the observed storage volume")
    current = paths.store_root
    while not current.exists() and current != current.parent:
        current = current.parent
    if not current.exists() or not current.is_dir() or current.is_symlink():
        raise PublicationError("market-store ancestor must be an existing non-symlink directory")


def _required_resources(batch: CanonicalCandleBatch, budget: CapacityBudget) -> tuple[int, int]:
    write_workspace = max(2 * TARGET_FILE_SIZE_BYTES, 2 * batch.table.nbytes)
    required_free = (
        budget.active_and_building_bytes
        + budget.rest_staging_bytes
        + budget.operating_reserve_bytes
        + write_workspace
    )
    planned_memory = 64 * 1024**2 + 3 * batch.table.nbytes
    return required_free, planned_memory


def _assert_resources(
    snapshot: HostSnapshot,
    *,
    required_free_bytes: int,
    planned_peak_memory_bytes: int,
) -> None:
    if snapshot.volume_free_bytes < required_free_bytes:
        raise PublicationError(
            "insufficient free space: "
            f"need {required_free_bytes}, have {snapshot.volume_free_bytes}"
        )
    if planned_peak_memory_bytes > snapshot.memory_available_bytes:
        raise PublicationError("insufficient currently available memory for bounded write")
    if planned_peak_memory_bytes * 100 > snapshot.memory_total_bytes * MAX_MEMORY_PERCENT:
        raise PublicationError("bounded write would exceed the 70% total-memory gate")


def _request_sha256(spec: CandleDatasetSpec, batch: CanonicalCandleBatch, input_hash: str) -> str:
    return canonical_sha256(
        {
            "contract": PUBLICATION_CONTRACT,
            "dataset_type": batch.dataset_type,
            "input_table_sha256": input_hash,
            "partition_path": batch.partition_path.as_posix(),
            "spec": spec,
        }
    )


def preflight_candle_dataset(
    store_root: Path,
    spec: CandleDatasetSpec,
    batch: CanonicalCandleBatch,
    budget: CapacityBudget,
    snapshot: HostSnapshot,
    *,
    now_ms: int,
) -> PublicationPlan:
    """Validate identity, layout, host, capacity, and collisions without mutation."""

    if now_ms < 0:
        raise PublicationError("preflight time cannot be negative")
    verify_canonical_candle_schema(batch.table.schema, batch.dataset_type)
    input_hash = _table_sha256(batch.table)
    request_hash = _request_sha256(spec, batch, input_hash)
    paths = _paths(store_root, spec, request_hash)
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
        published = verify_committed_candle_dataset(paths.dataset_root)
        audit = _load_json_object(published.audit_path)
        if (
            published.manifest.dataset_id != spec.dataset_id
            or published.manifest.dataset_type is not batch.dataset_type
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
    return PublicationPlan(
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


def _write_exclusive(path: Path, payload: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _fsync_file(path: Path) -> None:
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def _target_classification(size_bytes: int) -> str:
    if size_bytes * 100 < TARGET_FILE_SIZE_BYTES * 80:
        return "tail-below-target"
    if size_bytes * 100 <= TARGET_FILE_SIZE_BYTES * 120:
        return "target-band"
    return "oversized-single-batch"


def _file_stats(
    batch: CanonicalCandleBatch, relative_path: PurePosixPath, path: Path
) -> DatasetFile:
    times = cast(dict[str, int], pc.min_max(batch.table.column("open_time_ms")).as_py())
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


def _build_audit(
    plan: PublicationPlan,
    dataset_file: DatasetFile,
    *,
    parquet_row_groups: int,
) -> dict[str, object]:
    return {
        "audit_contract": AUDIT_CONTRACT,
        "capacity_evidence_sha256": plan.spec.capacity_evidence_sha256,
        "coverage_evidence_sha256": plan.spec.coverage_evidence_sha256,
        "dataset_id": plan.spec.dataset_id,
        "dataset_type": plan.batch.dataset_type,
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
        "layout_contract": CANONICAL_LAYOUT_ID,
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
            "parquet_footer_verified": True,
            "single_partition": True,
            "sorted_unique_keys": True,
            "upstream_coverage_evidence_bound": True,
        },
        "request_sha256": plan.request_sha256,
    }


def publish_candle_dataset(
    plan: PublicationPlan,
    fresh_snapshot: HostSnapshot,
    *,
    committed_at_ms: int,
) -> PublishedDataset:
    """Publish atomically after a second fresh host check; write the receipt last."""

    if plan.existing_commit:
        return verify_committed_candle_dataset(plan.paths.dataset_root)
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
    parquet_file = pq.ParquetFile(parquet_path)
    try:
        verify_canonical_candle_schema(parquet_file.schema_arrow, plan.batch.dataset_type)
        if parquet_file.metadata.num_rows != plan.batch.table.num_rows:
            raise PublicationError("Parquet footer row count does not match the canonical batch")
        parquet_row_groups = parquet_file.metadata.num_row_groups
    finally:
        parquet_file.close()
    relative_parquet = plan.batch.partition_path / parquet_path.name
    dataset_file = _file_stats(plan.batch, relative_parquet, parquet_path)
    instrument_count = int(pc.count_distinct(plan.batch.table.column("instrument_id")).as_py())
    audit = _build_audit(
        plan,
        dataset_file,
        parquet_row_groups=parquet_row_groups,
    )
    audit_path = plan.paths.building_root / "audit.json"
    _write_exclusive(audit_path, canonical_json_bytes(audit))
    audit_sha = sha256_file(audit_path)
    manifest = DatasetManifest(
        dataset_id=plan.spec.dataset_id,
        dataset_type=plan.batch.dataset_type,
        schema_version=plan.spec.schema_version,
        semantic_version=plan.spec.semantic_version,
        status=DatasetStatus.COMPLETE,
        parent_dataset_ids=plan.spec.parent_dataset_ids,
        instrument_count=instrument_count,
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
    return verify_committed_candle_dataset(plan.paths.dataset_root)


def _load_json_object(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise PublicationError(f"cannot read canonical JSON: {path}") from error
    if not isinstance(raw, dict):
        raise PublicationError(f"canonical JSON must contain an object: {path}")
    return cast(dict[str, object], raw)


def _load_manifest(path: Path) -> DatasetManifest:
    raw = _load_json_object(path)
    try:
        files_raw = cast(list[dict[str, object]], raw["files"])
        manifest = DatasetManifest(
            dataset_id=cast(str, raw["dataset_id"]),
            dataset_type=DatasetType(cast(str, raw["dataset_type"])),
            schema_version=cast(str, raw["schema_version"]),
            semantic_version=cast(str, raw["semantic_version"]),
            status=DatasetStatus(cast(str, raw["status"])),
            parent_dataset_ids=tuple(cast(list[str], raw["parent_dataset_ids"])),
            instrument_count=cast(int, raw["instrument_count"]),
            row_count=cast(int, raw["row_count"]),
            min_time_ms=cast(int | None, raw["min_time_ms"]),
            max_time_ms=cast(int | None, raw["max_time_ms"]),
            files=tuple(DatasetFile(**item) for item in files_raw),  # type: ignore[arg-type]
            source_evidence_sha256=tuple(cast(list[str], raw["source_evidence_sha256"])),
            build_config_sha256=cast(str, raw["build_config_sha256"]),
            software_identity=cast(str, raw["software_identity"]),
            audit_report_sha256=tuple(cast(list[str], raw["audit_report_sha256"])),
            committed_at_ms=cast(int | None, raw["committed_at_ms"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise PublicationError("invalid dataset manifest") from error
    if canonical_json_bytes(manifest) != path.read_bytes():
        raise PublicationError("manifest is not canonical JSON")
    return manifest


def _load_receipt(path: Path) -> CompletionReceipt:
    raw = _load_json_object(path)
    try:
        receipt = CompletionReceipt(
            dataset_id=cast(str, raw["dataset_id"]),
            manifest_sha256=cast(str, raw["manifest_sha256"]),
            status=DatasetStatus(cast(str, raw["status"])),
            committed_at_ms=cast(int, raw["committed_at_ms"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise PublicationError("invalid completion receipt") from error
    if canonical_json_bytes(receipt) != path.read_bytes():
        raise PublicationError("completion receipt is not canonical JSON")
    return receipt


def _safe_dataset_file(dataset_root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    candidate = dataset_root.joinpath(*pure.parts).resolve()
    if not candidate.is_relative_to(dataset_root.resolve()) or candidate.is_symlink():
        raise PublicationError("manifest file escapes the immutable dataset root")
    return candidate


def verify_committed_candle_dataset(dataset_root: Path) -> PublishedDataset:
    """Verify receipt, canonical manifest, audit, file hashes, schema, and no orphans."""

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
    if root.name != manifest.dataset_id or not DATASET_ID_RE.fullmatch(manifest.dataset_id):
        raise PublicationError("dataset directory does not match its safe manifest identity")
    if (
        receipt.dataset_id != manifest.dataset_id
        or receipt.committed_at_ms != manifest.committed_at_ms
        or receipt.manifest_sha256 != sha256_file(manifest_path)
    ):
        raise PublicationError("completion receipt does not bind the manifest")
    if manifest.dataset_type not in (DatasetType.TRADE_KLINE_1M, DatasetType.MARK_KLINE_1M):
        raise PublicationError("publication verifier supports only canonical candle datasets")
    audit_sha = sha256_file(audit_path)
    if manifest.audit_report_sha256 != (audit_sha,):
        raise PublicationError("manifest does not bind the canonical audit")
    audit = _load_json_object(audit_path)
    if canonical_json_bytes(audit) != audit_path.read_bytes():
        raise PublicationError("audit is not canonical JSON")
    expected_quality_checks = {
        "canonical_schema_verified": True,
        "file_hash_recorded": True,
        "parquet_footer_verified": True,
        "single_partition": True,
        "sorted_unique_keys": True,
        "upstream_coverage_evidence_bound": True,
    }
    if (
        audit.get("audit_contract") != AUDIT_CONTRACT
        or audit.get("dataset_id") != manifest.dataset_id
        or audit.get("dataset_type") != manifest.dataset_type.value
        or audit.get("layout_contract") != CANONICAL_LAYOUT_ID
        or audit.get("quality_checks") != expected_quality_checks
    ):
        raise PublicationError("canonical audit identity does not match the manifest")
    expected_files = {"audit.json", "manifest.json", "completion-receipt.json"}
    expected_directories: set[str] = set()
    for item in manifest.files:
        path = _safe_dataset_file(root, item.path)
        if (
            not path.is_file()
            or path.stat().st_size != item.size_bytes
            or sha256_file(path) != item.sha256
        ):
            raise PublicationError(f"dataset file hash or size mismatch: {item.path}")
        parquet = pq.ParquetFile(path)
        try:
            verify_canonical_candle_schema(parquet.schema_arrow, manifest.dataset_type)
            if parquet.metadata.num_rows != item.row_count:
                raise PublicationError(f"dataset file row count mismatch: {item.path}")
        finally:
            parquet.close()
        expected_files.add(item.path)
        parent = PurePosixPath(item.path).parent
        while parent != PurePosixPath("."):
            expected_directories.add(parent.as_posix())
            parent = parent.parent
    actual_files = {path.relative_to(root).as_posix() for path in entries if path.is_file()}
    if actual_files != expected_files:
        raise PublicationError("committed dataset contains orphan or missing files")
    actual_directories = {path.relative_to(root).as_posix() for path in entries if path.is_dir()}
    if actual_directories != expected_directories:
        raise PublicationError("committed dataset contains orphan or missing directories")
    return PublishedDataset(
        dataset_root=root,
        manifest_path=manifest_path,
        audit_path=audit_path,
        receipt_path=receipt_path,
        manifest=manifest,
        receipt=receipt,
    )
