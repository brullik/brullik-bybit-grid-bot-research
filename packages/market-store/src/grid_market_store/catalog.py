"""Receipt-verified DuckDB catalog and deterministic canonical range selection."""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from heapq import merge
from itertools import pairwise
from pathlib import Path, PurePosixPath
from typing import Any, Final, cast

import duckdb
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from grid_contracts.canonical import canonical_sha256
from grid_contracts.market import DatasetFile, DatasetManifest, DatasetStatus, DatasetType

from grid_market_store.funding_publication import verify_committed_funding_dataset
from grid_market_store.physical import BUCKET_COUNT, stable_bucket
from grid_market_store.publication import (
    DATASET_ID_RE,
    SHA256_RE,
    PublicationError,
    PublishedDataset,
    verify_committed_candle_dataset,
)

CATALOG_CONTRACT: Final = "grid.canonical-dataset-catalog/v1"
CATALOG_REGISTRATION_CONTRACT: Final = "grid.canonical-dataset-catalog-registration/v1"
CATALOG_REGISTRATION_REQUEST_CONTRACT: Final = (
    "grid.canonical-dataset-catalog-registration-request/v1"
)
CATALOG_SELECTION_REQUEST_CONTRACT: Final = "grid.canonical-dataset-selection-request/v1"
CATALOG_SELECTION_CONTRACT: Final = "grid.canonical-dataset-selection/v1"
CATALOG_SCHEMA_VERSION: Final = 1
EXACT_KEY_BATCH_ROWS: Final = 4_096
MAX_EXACT_KEY_STREAMS: Final = 128
MAX_CATALOG_DATASETS_PER_REQUEST: Final = 10_000
GIT_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
PARTITION_RE: Final = re.compile(
    r"^dataset=(trade_kline_1m|mark_kline_1m|funding_event)/schema=(v1)/"
    r"year=([0-9]{4})/month=(0[1-9]|1[0-2])/bucket=(0[0-7])$"
)
SUPPORTED_DATASET_TYPES: Final = frozenset(
    {
        DatasetType.TRADE_KLINE_1M,
        DatasetType.MARK_KLINE_1M,
        DatasetType.FUNDING_EVENT,
    }
)


class CatalogError(RuntimeError):
    """Catalog state cannot prove a safe registration or selection."""


@dataclass(frozen=True, slots=True)
class CatalogFileRecord:
    ordinal: int
    dataset_relative_path: str
    object_key: str
    sha256: str
    size_bytes: int
    row_count: int
    min_time_ms: int
    max_time_ms: int
    min_instrument_id: int
    max_instrument_id: int
    first_instrument_id: int
    first_time_ms: int
    last_instrument_id: int
    last_time_ms: int


@dataclass(frozen=True, slots=True)
class CatalogDatasetRecord:
    dataset_id: str
    dataset_type: DatasetType
    schema_version: str
    semantic_version: str
    status: DatasetStatus
    parent_dataset_ids: tuple[str, ...]
    instrument_count: int
    row_count: int
    min_time_ms: int
    max_time_ms: int
    files: tuple[CatalogFileRecord, ...]
    source_evidence_sha256: tuple[str, ...]
    audit_report_sha256: tuple[str, ...]
    build_config_sha256: str
    software_identity: str
    manifest_sha256: str
    receipt_object_key: str
    partition_path: str
    year: int
    month: int
    bucket: int
    gap_status: str = "not-assessed-by-dataset-receipt"
    gap_count: int | None = None
    conflict_count: int = 0
    registered_revision: int | None = None
    registered_at_ms: int | None = None
    registration_software_identity: str | None = None

    @property
    def total_size_bytes(self) -> int:
        return sum(item.size_bytes for item in self.files)


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    revision: int
    content_sha256: str
    datasets: tuple[CatalogDatasetRecord, ...]

    @property
    def dataset_count(self) -> int:
        return len(self.datasets)

    @property
    def file_count(self) -> int:
        return sum(len(item.files) for item in self.datasets)


@dataclass(frozen=True, slots=True)
class CatalogRegistrationPlan:
    store_root: Path
    catalog_path: Path
    building_path: Path
    lock_path: Path
    requested_dataset_ids: tuple[str, ...]
    records: tuple[CatalogDatasetRecord, ...]
    new_dataset_ids: tuple[str, ...]
    before: CatalogSnapshot
    software_identity: str

    @property
    def existing_registration(self) -> bool:
        return not self.new_dataset_ids


@dataclass(frozen=True, slots=True)
class CatalogRegistrationRequest:
    dataset_ids: tuple[str, ...]
    software_identity: str

    def __post_init__(self) -> None:
        _validate_dataset_ids(self.dataset_ids)
        if not GIT_IDENTITY_RE.fullmatch(self.software_identity):
            raise CatalogError("registration software identity must be an immutable git SHA")

    @property
    def request_sha256(self) -> str:
        return canonical_sha256(catalog_registration_request_payload(self))


@dataclass(frozen=True, slots=True)
class CatalogSelectionRequest:
    catalog_revision: int
    catalog_content_sha256: str
    dataset_ids: tuple[str, ...]
    dataset_type: DatasetType
    start_time_ms: int
    end_time_ms: int
    instrument_ids: tuple[int, ...] | None
    consumer_software_identity: str

    def __post_init__(self) -> None:
        if self.catalog_revision <= 0:
            raise CatalogError("selection catalog_revision must be positive")
        if not SHA256_RE.fullmatch(self.catalog_content_sha256):
            raise CatalogError("selection catalog digest must be lowercase SHA-256")
        _validate_dataset_ids(self.dataset_ids)
        if self.dataset_type not in SUPPORTED_DATASET_TYPES:
            raise CatalogError("selection requires one supported canonical dataset type")
        if (
            isinstance(self.start_time_ms, bool)
            or isinstance(self.end_time_ms, bool)
            or self.start_time_ms < 0
            or self.end_time_ms < self.start_time_ms
            or self.start_time_ms % 60_000
            or self.end_time_ms % 60_000
        ):
            raise CatalogError(
                "selection range must be inclusive, non-negative, and minute-aligned"
            )
        if self.instrument_ids is not None:
            if not self.instrument_ids:
                raise CatalogError("include-mode instrument_ids must not be empty")
            if tuple(sorted(self.instrument_ids)) != self.instrument_ids:
                raise CatalogError("selection instrument_ids must be sorted")
            if len(self.instrument_ids) != len(set(self.instrument_ids)):
                raise CatalogError("selection instrument_ids must be unique")
            for instrument_id in self.instrument_ids:
                try:
                    stable_bucket(instrument_id)
                except ValueError as error:
                    raise CatalogError("selection instrument IDs must fit UInt32") from error
        if not GIT_IDENTITY_RE.fullmatch(self.consumer_software_identity):
            raise CatalogError("consumer software identity must be an immutable git SHA")

    @property
    def request_sha256(self) -> str:
        return canonical_sha256(selection_request_payload(self))


@dataclass(frozen=True, slots=True)
class SelectedCatalogObject:
    dataset_id: str
    manifest_sha256: str
    object_key: str
    file_sha256: str
    size_bytes: int
    row_count: int
    min_time_ms: int
    max_time_ms: int
    min_instrument_id: int
    max_instrument_id: int
    partition_path: str


@dataclass(frozen=True, slots=True)
class CatalogSelection:
    request: CatalogSelectionRequest
    snapshot: CatalogSnapshot
    objects: tuple[SelectedCatalogObject, ...]
    required_partitions: tuple[str, ...]
    selected_dataset_manifest_sha256: tuple[tuple[str, str], ...]


def _validate_catalog_record(record: CatalogDatasetRecord) -> None:
    if not DATASET_ID_RE.fullmatch(record.dataset_id):
        raise CatalogError("catalog contains an unsafe dataset ID")
    if (
        record.dataset_type not in SUPPORTED_DATASET_TYPES
        or record.status is not DatasetStatus.COMPLETE
    ):
        raise CatalogError("catalog contains an unsupported or incomplete dataset")
    if (
        not SHA256_RE.fullmatch(record.manifest_sha256)
        or not SHA256_RE.fullmatch(record.build_config_sha256)
        or not record.source_evidence_sha256
        or not record.audit_report_sha256
        or any(
            not isinstance(value, str) or not SHA256_RE.fullmatch(value)
            for value in (*record.source_evidence_sha256, *record.audit_report_sha256)
        )
    ):
        raise CatalogError("catalog contains an invalid manifest, build, or evidence digest")
    if (
        len(record.parent_dataset_ids) != len(set(record.parent_dataset_ids))
        or record.dataset_id in record.parent_dataset_ids
        or any(not DATASET_ID_RE.fullmatch(value) for value in record.parent_dataset_ids)
    ):
        raise CatalogError("catalog contains invalid parent lineage")
    if (
        record.instrument_count <= 0
        or record.row_count <= 0
        or record.min_time_ms < 0
        or record.min_time_ms > record.max_time_ms
        or not record.files
        or sum(item.row_count for item in record.files) != record.row_count
        or tuple(item.ordinal for item in record.files) != tuple(range(len(record.files)))
    ):
        raise CatalogError("catalog contains invalid dataset or file aggregate facts")
    match = PARTITION_RE.fullmatch(record.partition_path)
    if (
        match is None
        or match.group(1) != record.dataset_type.value
        or match.group(2) != record.schema_version
        or (int(match.group(3)), int(match.group(4)), int(match.group(5)))
        != (record.year, record.month, record.bucket)
    ):
        raise CatalogError("catalog contains invalid canonical partition facts")
    if record.receipt_object_key != f"datasets/{record.dataset_id}/completion-receipt.json":
        raise CatalogError("catalog contains an invalid receipt object key")
    for item in record.files:
        parsed = PurePosixPath(item.dataset_relative_path)
        expected_key = f"datasets/{record.dataset_id}/{item.dataset_relative_path}"
        if (
            parsed.is_absolute()
            or ".." in parsed.parts
            or parsed.as_posix() != item.dataset_relative_path
            or PurePosixPath(item.dataset_relative_path).parent.as_posix() != record.partition_path
            or item.object_key != expected_key
            or not SHA256_RE.fullmatch(item.sha256)
            or item.size_bytes <= 0
            or item.row_count <= 0
            or item.min_time_ms < 0
            or item.min_time_ms > item.max_time_ms
            or item.min_instrument_id <= 0
            or item.min_instrument_id > item.max_instrument_id
            or (item.first_instrument_id, item.first_time_ms)
            > (item.last_instrument_id, item.last_time_ms)
        ):
            raise CatalogError("catalog contains an invalid file/object binding")
    registration_values = (
        record.registered_revision,
        record.registered_at_ms,
        record.registration_software_identity,
    )
    if any(value is None for value in registration_values) and not all(
        value is None for value in registration_values
    ):
        raise CatalogError("catalog registration fields are partially populated")
    if record.registered_revision is not None and (
        record.registered_revision <= 0
        or record.registered_at_ms is None
        or record.registered_at_ms < 0
        or record.registration_software_identity is None
        or not GIT_IDENTITY_RE.fullmatch(record.registration_software_identity)
    ):
        raise CatalogError("catalog registration identity or revision is invalid")
    if (
        record.gap_status != "not-assessed-by-dataset-receipt"
        or record.gap_count is not None
        or record.conflict_count != 0
    ):
        raise CatalogError("catalog gap/conflict summary exceeds dataset-receipt evidence")


def _validate_dataset_ids(dataset_ids: tuple[str, ...]) -> None:
    if not dataset_ids:
        raise CatalogError("at least one dataset ID is required")
    if len(dataset_ids) > MAX_CATALOG_DATASETS_PER_REQUEST:
        raise CatalogError(
            f"catalog request dataset count exceeds {MAX_CATALOG_DATASETS_PER_REQUEST}"
        )
    if tuple(sorted(dataset_ids)) != dataset_ids:
        raise CatalogError("dataset IDs must be sorted")
    if len(dataset_ids) != len(set(dataset_ids)):
        raise CatalogError("dataset IDs must be unique")
    if any(not DATASET_ID_RE.fullmatch(value) for value in dataset_ids):
        raise CatalogError("dataset IDs must be safe lowercase storage identities")


def catalog_registration_request_payload(
    request: CatalogRegistrationRequest,
) -> dict[str, object]:
    """Render the closed, file-backed registration request contract."""

    return {
        "dataset_ids": list(request.dataset_ids),
        "request_schema": CATALOG_REGISTRATION_REQUEST_CONTRACT,
        "software_identity": request.software_identity,
    }


def load_catalog_registration_request(path: Path) -> CatalogRegistrationRequest:
    """Parse a bounded registration request without coercion or implicit defaults."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CatalogError("catalog registration request is not valid JSON") from error
    if not isinstance(raw, dict) or set(raw) != {
        "dataset_ids",
        "request_schema",
        "software_identity",
    }:
        raise CatalogError(
            "catalog registration request fields do not match the closed v1 contract"
        )
    if raw["request_schema"] != CATALOG_REGISTRATION_REQUEST_CONTRACT:
        raise CatalogError("unsupported catalog registration request contract")
    dataset_ids = raw["dataset_ids"]
    software_identity = raw["software_identity"]
    if not isinstance(dataset_ids, list) or not all(
        isinstance(value, str) for value in dataset_ids
    ):
        raise CatalogError("registration dataset_ids must be an array of strings")
    if not isinstance(software_identity, str):
        raise CatalogError("registration software_identity must be a string")
    return CatalogRegistrationRequest(
        dataset_ids=tuple(cast(list[str], dataset_ids)),
        software_identity=software_identity,
    )


def _safe_catalog_paths(store_root: Path, catalog_path: Path) -> tuple[Path, Path, Path, Path]:
    root = store_root.resolve()
    if not root.is_dir() or root.is_symlink():
        raise CatalogError("market-store root must be an existing non-symlink directory")
    catalog = catalog_path.resolve()
    if not catalog.is_relative_to(root):
        raise CatalogError("catalog must be stored inside the market-store root")
    if catalog.suffix != ".duckdb":
        raise CatalogError("catalog path must use the .duckdb suffix")
    current = catalog.parent
    while current != root:
        if current.exists() and (not current.is_dir() or current.is_symlink()):
            raise CatalogError("catalog ancestors must be non-symlink directories")
        current = current.parent
    if catalog.exists() and (not catalog.is_file() or catalog.is_symlink()):
        raise CatalogError("catalog must be a regular non-symlink file")
    building = catalog.with_name(f".{catalog.name}.building")
    lock = catalog.with_name(f".{catalog.name}.lock")
    if building.exists():
        raise CatalogError("stale catalog building output detected")
    if lock.exists():
        raise CatalogError("concurrent or stale catalog write lock detected")
    return root, catalog, building, lock


def _partition_facts(manifest: DatasetManifest) -> tuple[str, int, int, int]:
    parents = {PurePosixPath(item.path).parent.as_posix() for item in manifest.files}
    if len(parents) != 1:
        raise CatalogError("cataloged dataset must have one canonical partition")
    partition_path = next(iter(parents))
    match = PARTITION_RE.fullmatch(partition_path)
    if match is None:
        raise CatalogError("dataset partition path is not the accepted v1 month/bucket layout")
    if match.group(1) != manifest.dataset_type.value or match.group(2) != manifest.schema_version:
        raise CatalogError("dataset partition type/schema conflicts with its manifest")
    return partition_path, int(match.group(3)), int(match.group(4)), int(match.group(5))


def _file_record(
    published: PublishedDataset,
    item: DatasetFile,
    *,
    ordinal: int,
) -> CatalogFileRecord:
    if (
        item.row_count <= 0
        or item.min_time_ms is None
        or item.max_time_ms is None
        or item.min_instrument_id is None
        or item.max_instrument_id is None
    ):
        raise CatalogError("canonical files require non-empty key statistics")
    time_column = (
        "funding_time_ms"
        if published.manifest.dataset_type is DatasetType.FUNDING_EVENT
        else "open_time_ms"
    )
    keys = pq.read_table(
        published.dataset_root / item.path,
        columns=["instrument_id", time_column],
    )
    if keys.num_rows != item.row_count:
        raise CatalogError("catalog key read conflicts with the verified manifest")
    first_instrument_id = cast(int, keys.column("instrument_id")[0].as_py())
    first_time_ms = cast(int, keys.column(time_column)[0].as_py())
    last_instrument_id = cast(int, keys.column("instrument_id")[-1].as_py())
    last_time_ms = cast(int, keys.column(time_column)[-1].as_py())
    return CatalogFileRecord(
        ordinal=ordinal,
        dataset_relative_path=item.path,
        object_key=f"datasets/{published.manifest.dataset_id}/{item.path}",
        sha256=item.sha256,
        size_bytes=item.size_bytes,
        row_count=item.row_count,
        min_time_ms=item.min_time_ms,
        max_time_ms=item.max_time_ms,
        min_instrument_id=item.min_instrument_id,
        max_instrument_id=item.max_instrument_id,
        first_instrument_id=first_instrument_id,
        first_time_ms=first_time_ms,
        last_instrument_id=last_instrument_id,
        last_time_ms=last_time_ms,
    )


def _record_from_store(store_root: Path, dataset_id: str) -> CatalogDatasetRecord:
    dataset_root = store_root / "datasets" / dataset_id
    try:
        published = verify_committed_candle_dataset(dataset_root)
    except (OSError, PublicationError):
        try:
            published = verify_committed_funding_dataset(dataset_root)
        except (OSError, PublicationError) as error:
            raise CatalogError(
                "canonical dataset receipt or file binding does not verify"
            ) from error
    manifest = published.manifest
    if manifest.dataset_id != dataset_id:
        raise CatalogError("dataset directory identity conflicts with its manifest")
    if (
        manifest.status is not DatasetStatus.COMPLETE
        or manifest.dataset_type not in SUPPORTED_DATASET_TYPES
    ):
        raise CatalogError("catalog v1 accepts only complete canonical datasets")
    if manifest.min_time_ms is None or manifest.max_time_ms is None:
        raise CatalogError("canonical manifest requires time bounds")
    partition_path, year, month, bucket = _partition_facts(manifest)
    files = tuple(
        _file_record(published, item, ordinal=index) for index, item in enumerate(manifest.files)
    )
    record = CatalogDatasetRecord(
        dataset_id=manifest.dataset_id,
        dataset_type=manifest.dataset_type,
        schema_version=manifest.schema_version,
        semantic_version=manifest.semantic_version,
        status=manifest.status,
        parent_dataset_ids=manifest.parent_dataset_ids,
        instrument_count=manifest.instrument_count,
        row_count=manifest.row_count,
        min_time_ms=manifest.min_time_ms,
        max_time_ms=manifest.max_time_ms,
        files=files,
        source_evidence_sha256=manifest.source_evidence_sha256,
        audit_report_sha256=manifest.audit_report_sha256,
        build_config_sha256=manifest.build_config_sha256,
        software_identity=manifest.software_identity,
        manifest_sha256=published.receipt.manifest_sha256,
        receipt_object_key=f"datasets/{dataset_id}/completion-receipt.json",
        partition_path=partition_path,
        year=year,
        month=month,
        bucket=bucket,
    )
    _validate_catalog_record(record)
    return record


def _functional_record_payload(record: CatalogDatasetRecord) -> dict[str, object]:
    return {
        "audit_report_sha256": list(record.audit_report_sha256),
        "build_config_sha256": record.build_config_sha256,
        "conflict_count": record.conflict_count,
        "dataset_id": record.dataset_id,
        "dataset_type": record.dataset_type,
        "files": [
            {
                "dataset_relative_path": item.dataset_relative_path,
                "file_sha256": item.sha256,
                "first_key": [item.first_instrument_id, item.first_time_ms],
                "last_key": [item.last_instrument_id, item.last_time_ms],
                "max_instrument_id": item.max_instrument_id,
                "max_time_ms": item.max_time_ms,
                "min_instrument_id": item.min_instrument_id,
                "min_time_ms": item.min_time_ms,
                "object_key": item.object_key,
                "ordinal": item.ordinal,
                "row_count": item.row_count,
                "size_bytes": item.size_bytes,
            }
            for item in record.files
        ],
        "gap_count": record.gap_count,
        "gap_status": record.gap_status,
        "instrument_count": record.instrument_count,
        "manifest_sha256": record.manifest_sha256,
        "max_time_ms": record.max_time_ms,
        "min_time_ms": record.min_time_ms,
        "parent_dataset_ids": list(record.parent_dataset_ids),
        "partition": {
            "bucket": record.bucket,
            "month": record.month,
            "path": record.partition_path,
            "year": record.year,
        },
        "receipt_object_key": record.receipt_object_key,
        "row_count": record.row_count,
        "schema_version": record.schema_version,
        "semantic_version": record.semantic_version,
        "software_identity": record.software_identity,
        "source_evidence_sha256": list(record.source_evidence_sha256),
        "status": record.status,
        "total_size_bytes": record.total_size_bytes,
    }


def _catalog_payload(
    revision: int,
    datasets: tuple[CatalogDatasetRecord, ...],
) -> dict[str, object]:
    return {
        "catalog_contract": CATALOG_CONTRACT,
        "datasets": [
            {
                **_functional_record_payload(item),
                "registered_at_ms": item.registered_at_ms,
                "registered_revision": item.registered_revision,
                "registration_software_identity": item.registration_software_identity,
            }
            for item in datasets
        ],
        "revision": revision,
        "schema_version": CATALOG_SCHEMA_VERSION,
    }


def _empty_snapshot() -> CatalogSnapshot:
    payload = _catalog_payload(0, ())
    return CatalogSnapshot(revision=0, content_sha256=canonical_sha256(payload), datasets=())


def _create_schema(connection: Any) -> None:
    connection.execute(
        """
        CREATE TABLE catalog_state (
            singleton INTEGER PRIMARY KEY,
            catalog_contract VARCHAR NOT NULL,
            schema_version INTEGER NOT NULL,
            revision BIGINT NOT NULL,
            content_sha256 VARCHAR NOT NULL
        );
        CREATE TABLE datasets (
            dataset_id VARCHAR PRIMARY KEY,
            dataset_type VARCHAR NOT NULL,
            schema_version VARCHAR NOT NULL,
            semantic_version VARCHAR NOT NULL,
            status VARCHAR NOT NULL,
            instrument_count BIGINT NOT NULL,
            row_count BIGINT NOT NULL,
            min_time_ms BIGINT NOT NULL,
            max_time_ms BIGINT NOT NULL,
            source_evidence_sha256_json VARCHAR NOT NULL,
            audit_report_sha256_json VARCHAR NOT NULL,
            build_config_sha256 VARCHAR NOT NULL,
            software_identity VARCHAR NOT NULL,
            manifest_sha256 VARCHAR NOT NULL UNIQUE,
            receipt_object_key VARCHAR NOT NULL UNIQUE,
            partition_path VARCHAR NOT NULL,
            partition_year INTEGER NOT NULL,
            partition_month INTEGER NOT NULL,
            partition_bucket INTEGER NOT NULL,
            gap_status VARCHAR NOT NULL,
            gap_count BIGINT,
            conflict_count BIGINT NOT NULL,
            registered_revision BIGINT NOT NULL,
            registered_at_ms BIGINT NOT NULL,
            registration_software_identity VARCHAR NOT NULL
        );
        CREATE TABLE dataset_parents (
            dataset_id VARCHAR NOT NULL,
            ordinal INTEGER NOT NULL,
            parent_dataset_id VARCHAR NOT NULL,
            PRIMARY KEY (dataset_id, ordinal),
            UNIQUE (dataset_id, parent_dataset_id)
        );
        CREATE TABLE dataset_files (
            dataset_id VARCHAR NOT NULL,
            ordinal INTEGER NOT NULL,
            dataset_relative_path VARCHAR NOT NULL,
            object_key VARCHAR NOT NULL UNIQUE,
            file_sha256 VARCHAR NOT NULL,
            size_bytes BIGINT NOT NULL,
            row_count BIGINT NOT NULL,
            min_time_ms BIGINT NOT NULL,
            max_time_ms BIGINT NOT NULL,
            min_instrument_id BIGINT NOT NULL,
            max_instrument_id BIGINT NOT NULL,
            first_instrument_id BIGINT NOT NULL,
            first_time_ms BIGINT NOT NULL,
            last_instrument_id BIGINT NOT NULL,
            last_time_ms BIGINT NOT NULL,
            PRIMARY KEY (dataset_id, ordinal),
            UNIQUE (dataset_id, dataset_relative_path)
        );
        CREATE TABLE registration_events (
            revision BIGINT PRIMARY KEY,
            previous_content_sha256 VARCHAR NOT NULL,
            content_sha256 VARCHAR NOT NULL,
            dataset_ids_json VARCHAR NOT NULL,
            registered_at_ms BIGINT NOT NULL,
            software_identity VARCHAR NOT NULL
        );
        """
    )
    empty = _empty_snapshot()
    connection.execute(
        "INSERT INTO catalog_state VALUES (?, ?, ?, ?, ?)",
        [1, CATALOG_CONTRACT, CATALOG_SCHEMA_VERSION, 0, empty.content_sha256],
    )


def _read_catalog_datasets(connection: Any) -> tuple[CatalogDatasetRecord, ...]:
    dataset_rows = connection.execute(
        """
        SELECT dataset_id, dataset_type, schema_version, semantic_version, status,
               instrument_count, row_count, min_time_ms, max_time_ms,
               source_evidence_sha256_json, audit_report_sha256_json,
               build_config_sha256, software_identity, manifest_sha256,
               receipt_object_key, partition_path, partition_year, partition_month,
               partition_bucket, gap_status, gap_count, conflict_count,
               registered_revision, registered_at_ms, registration_software_identity
        FROM datasets ORDER BY dataset_id
        """
    ).fetchall()
    records = []
    for row in dataset_rows:
        dataset_id = cast(str, row[0])
        parents = tuple(
            cast(str, item[0])
            for item in connection.execute(
                "SELECT parent_dataset_id FROM dataset_parents "
                "WHERE dataset_id = ? ORDER BY ordinal",
                [dataset_id],
            ).fetchall()
        )
        files = tuple(
            CatalogFileRecord(
                ordinal=cast(int, item[0]),
                dataset_relative_path=cast(str, item[1]),
                object_key=cast(str, item[2]),
                sha256=cast(str, item[3]),
                size_bytes=cast(int, item[4]),
                row_count=cast(int, item[5]),
                min_time_ms=cast(int, item[6]),
                max_time_ms=cast(int, item[7]),
                min_instrument_id=cast(int, item[8]),
                max_instrument_id=cast(int, item[9]),
                first_instrument_id=cast(int, item[10]),
                first_time_ms=cast(int, item[11]),
                last_instrument_id=cast(int, item[12]),
                last_time_ms=cast(int, item[13]),
            )
            for item in connection.execute(
                """
                SELECT ordinal, dataset_relative_path, object_key, file_sha256,
                       size_bytes, row_count, min_time_ms, max_time_ms,
                       min_instrument_id, max_instrument_id, first_instrument_id,
                       first_time_ms, last_instrument_id, last_time_ms
                FROM dataset_files WHERE dataset_id = ? ORDER BY ordinal
                """,
                [dataset_id],
            ).fetchall()
        )
        try:
            dataset_type = DatasetType(cast(str, row[1]))
            status = DatasetStatus(cast(str, row[4]))
            raw_source_hashes = json.loads(cast(str, row[9]))
            raw_audit_hashes = json.loads(cast(str, row[10]))
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            raise CatalogError("catalog contains invalid enum or JSON metadata") from error
        if not isinstance(raw_source_hashes, list) or not isinstance(raw_audit_hashes, list):
            raise CatalogError("catalog evidence digest inventories must be arrays")
        record = CatalogDatasetRecord(
            dataset_id=dataset_id,
            dataset_type=dataset_type,
            schema_version=cast(str, row[2]),
            semantic_version=cast(str, row[3]),
            status=status,
            parent_dataset_ids=parents,
            instrument_count=cast(int, row[5]),
            row_count=cast(int, row[6]),
            min_time_ms=cast(int, row[7]),
            max_time_ms=cast(int, row[8]),
            files=files,
            source_evidence_sha256=tuple(raw_source_hashes),
            audit_report_sha256=tuple(raw_audit_hashes),
            build_config_sha256=cast(str, row[11]),
            software_identity=cast(str, row[12]),
            manifest_sha256=cast(str, row[13]),
            receipt_object_key=cast(str, row[14]),
            partition_path=cast(str, row[15]),
            year=cast(int, row[16]),
            month=cast(int, row[17]),
            bucket=cast(int, row[18]),
            gap_status=cast(str, row[19]),
            gap_count=cast(int | None, row[20]),
            conflict_count=cast(int, row[21]),
            registered_revision=cast(int, row[22]),
            registered_at_ms=cast(int, row[23]),
            registration_software_identity=cast(str, row[24]),
        )
        _validate_catalog_record(record)
        records.append(record)
    return tuple(records)


def _load_snapshot(connection: Any) -> CatalogSnapshot:
    state_rows = connection.execute(
        "SELECT catalog_contract, schema_version, revision, content_sha256 "
        "FROM catalog_state WHERE singleton = 1"
    ).fetchall()
    if len(state_rows) != 1:
        raise CatalogError("catalog state row is missing or duplicated")
    contract, schema_version, revision, stored_hash = state_rows[0]
    if contract != CATALOG_CONTRACT or schema_version != CATALOG_SCHEMA_VERSION:
        raise CatalogError("unsupported catalog contract or schema version")
    datasets = _read_catalog_datasets(connection)
    _assert_lineage_complete_and_acyclic(datasets, ())
    if any(
        item.registered_revision is None or item.registered_revision > cast(int, revision)
        for item in datasets
    ):
        raise CatalogError("catalog dataset registration revision is outside catalog state")
    computed_hash = canonical_sha256(_catalog_payload(cast(int, revision), datasets))
    if stored_hash != computed_hash or not SHA256_RE.fullmatch(cast(str, stored_hash)):
        raise CatalogError("catalog logical content digest does not verify")
    events = connection.execute(
        "SELECT revision, previous_content_sha256, content_sha256, dataset_ids_json, "
        "registered_at_ms, software_identity "
        "FROM registration_events ORDER BY revision"
    ).fetchall()
    previous_hash = _empty_snapshot().content_sha256
    for expected_revision, event in enumerate(events, start=1):
        if event[0] != expected_revision or event[1] != previous_hash:
            raise CatalogError("catalog registration event chain is invalid")
        if not SHA256_RE.fullmatch(cast(str, event[2])):
            raise CatalogError("catalog registration event digest is invalid")
        try:
            event_dataset_ids = json.loads(cast(str, event[3]))
        except (TypeError, json.JSONDecodeError) as error:
            raise CatalogError("catalog registration event dataset inventory is invalid") from error
        expected_dataset_ids = sorted(
            item.dataset_id for item in datasets if item.registered_revision == expected_revision
        )
        if (
            event_dataset_ids != expected_dataset_ids
            or not event_dataset_ids
            or isinstance(event[4], bool)
            or not isinstance(event[4], int)
            or event[4] < 0
            or not isinstance(event[5], str)
            or not GIT_IDENTITY_RE.fullmatch(event[5])
            or any(
                item.registered_at_ms != event[4] or item.registration_software_identity != event[5]
                for item in datasets
                if item.registered_revision == expected_revision
            )
        ):
            raise CatalogError("catalog registration event does not match registered datasets")
        previous_hash = cast(str, event[2])
    if cast(int, revision) != len(events) or previous_hash != stored_hash:
        raise CatalogError("catalog revision does not match its registration chain")
    return CatalogSnapshot(
        revision=cast(int, revision),
        content_sha256=cast(str, stored_hash),
        datasets=datasets,
    )


def _verify_catalog_path(catalog: Path) -> CatalogSnapshot:
    connection = duckdb.connect(str(catalog), read_only=True)
    try:
        return _load_snapshot(connection)
    except duckdb.Error as error:
        raise CatalogError("catalog database cannot be verified") from error
    finally:
        connection.close()


def verify_catalog(store_root: Path, catalog_path: Path) -> CatalogSnapshot:
    """Verify the logical catalog digest and its registration chain without mutation."""

    _root, catalog, _building, _lock = _safe_catalog_paths(store_root, catalog_path)
    if not catalog.is_file():
        raise CatalogError("catalog does not exist")
    return _verify_catalog_path(catalog)


def _record_binding(record: CatalogDatasetRecord) -> str:
    return canonical_sha256(_functional_record_payload(record))


def _assert_lineage_complete_and_acyclic(
    existing: tuple[CatalogDatasetRecord, ...],
    requested: tuple[CatalogDatasetRecord, ...],
) -> None:
    records = {item.dataset_id: item for item in (*existing, *requested)}
    for record in records.values():
        missing = sorted(set(record.parent_dataset_ids) - records.keys())
        if missing:
            raise CatalogError(
                "catalog registration requires parent datasets first or in the same batch: "
                f"{missing}"
            )
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(dataset_id: str) -> None:
        if dataset_id in visiting:
            raise CatalogError("catalog dataset lineage contains a cycle")
        if dataset_id in visited:
            return
        visiting.add(dataset_id)
        record = records[dataset_id]
        for parent_id in record.parent_dataset_ids:
            if parent_id in records:
                visit(parent_id)
        visiting.remove(dataset_id)
        visited.add(dataset_id)

    for dataset_id in sorted(records):
        visit(dataset_id)


def preflight_catalog_registration(
    dataset_ids: tuple[str, ...],
    store_root: Path,
    catalog_path: Path,
    *,
    software_identity: str,
) -> CatalogRegistrationPlan:
    """Verify datasets, lineage, catalog state, and write paths without mutation."""

    normalized_ids = tuple(sorted(dataset_ids))
    if len(normalized_ids) != len(set(normalized_ids)):
        raise CatalogError("dataset IDs must be unique")
    _validate_dataset_ids(normalized_ids)
    if not GIT_IDENTITY_RE.fullmatch(software_identity):
        raise CatalogError("registration software identity must be an immutable git SHA")
    root, catalog, building, lock = _safe_catalog_paths(store_root, catalog_path)
    before = verify_catalog(root, catalog) if catalog.exists() else _empty_snapshot()
    records = tuple(_record_from_store(root, dataset_id) for dataset_id in normalized_ids)
    existing = {item.dataset_id: item for item in before.datasets}
    for record in records:
        old = existing.get(record.dataset_id)
        if old is not None and _record_binding(old) != _record_binding(record):
            raise CatalogError("catalog dataset binding conflicts with the verified store")
    _assert_lineage_complete_and_acyclic(before.datasets, records)
    new_ids = tuple(item.dataset_id for item in records if item.dataset_id not in existing)
    return CatalogRegistrationPlan(
        store_root=root,
        catalog_path=catalog,
        building_path=building,
        lock_path=lock,
        requested_dataset_ids=normalized_ids,
        records=records,
        new_dataset_ids=new_ids,
        before=before,
        software_identity=software_identity,
    )


def _insert_record(
    connection: Any,
    record: CatalogDatasetRecord,
    *,
    revision: int,
    registered_at_ms: int,
    software_identity: str,
) -> None:
    connection.execute(
        """
        INSERT INTO datasets VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        [
            record.dataset_id,
            record.dataset_type.value,
            record.schema_version,
            record.semantic_version,
            record.status.value,
            record.instrument_count,
            record.row_count,
            record.min_time_ms,
            record.max_time_ms,
            json.dumps(list(record.source_evidence_sha256), separators=(",", ":")),
            json.dumps(list(record.audit_report_sha256), separators=(",", ":")),
            record.build_config_sha256,
            record.software_identity,
            record.manifest_sha256,
            record.receipt_object_key,
            record.partition_path,
            record.year,
            record.month,
            record.bucket,
            record.gap_status,
            record.gap_count,
            record.conflict_count,
            revision,
            registered_at_ms,
            software_identity,
        ],
    )
    for ordinal, parent_id in enumerate(record.parent_dataset_ids):
        connection.execute(
            "INSERT INTO dataset_parents VALUES (?, ?, ?)",
            [record.dataset_id, ordinal, parent_id],
        )
    for item in record.files:
        connection.execute(
            "INSERT INTO dataset_files VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                record.dataset_id,
                item.ordinal,
                item.dataset_relative_path,
                item.object_key,
                item.sha256,
                item.size_bytes,
                item.row_count,
                item.min_time_ms,
                item.max_time_ms,
                item.min_instrument_id,
                item.max_instrument_id,
                item.first_instrument_id,
                item.first_time_ms,
                item.last_instrument_id,
                item.last_time_ms,
            ],
        )


def register_catalog_datasets(
    plan: CatalogRegistrationPlan,
    *,
    registered_at_ms: int,
) -> CatalogSnapshot:
    """Atomically replace the metadata index after a locked DuckDB transaction."""

    if registered_at_ms < 0:
        raise CatalogError("registration timestamp must be non-negative")
    current_records = tuple(
        _record_from_store(plan.store_root, dataset_id) for dataset_id in plan.requested_dataset_ids
    )
    if tuple(map(_record_binding, current_records)) != tuple(map(_record_binding, plan.records)):
        raise CatalogError("dataset changed after catalog registration preflight")
    if plan.existing_registration:
        return verify_catalog(plan.store_root, plan.catalog_path)
    plan.catalog_path.parent.mkdir(parents=True, exist_ok=True)
    lock_descriptor: int | None = None
    owns_lock = False
    owns_building = False
    try:
        lock_descriptor = os.open(plan.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        owns_lock = True
        os.write(lock_descriptor, b"grid-catalog-write-lock-v1\n")
        os.fsync(lock_descriptor)
        os.close(lock_descriptor)
        lock_descriptor = None
        if plan.building_path.exists():
            raise CatalogError("stale catalog building output detected after lock acquisition")
        if plan.catalog_path.exists():
            shutil.copy2(plan.catalog_path, plan.building_path)
        owns_building = True
        connection = duckdb.connect(str(plan.building_path))
        try:
            if not plan.catalog_path.exists():
                _create_schema(connection)
            starting = _load_snapshot(connection)
            if (
                starting.revision != plan.before.revision
                or starting.content_sha256 != plan.before.content_sha256
            ):
                raise CatalogError("catalog changed after registration preflight")
            new_revision = starting.revision + 1
            connection.execute("BEGIN TRANSACTION")
            try:
                for record in plan.records:
                    if record.dataset_id in plan.new_dataset_ids:
                        _insert_record(
                            connection,
                            record,
                            revision=new_revision,
                            registered_at_ms=registered_at_ms,
                            software_identity=plan.software_identity,
                        )
                connection.execute(
                    "UPDATE catalog_state SET revision = ?, content_sha256 = ? WHERE singleton = 1",
                    [new_revision, "0" * 64],
                )
                datasets = _read_catalog_datasets(connection)
                content_hash = canonical_sha256(_catalog_payload(new_revision, datasets))
                connection.execute(
                    "UPDATE catalog_state SET content_sha256 = ? WHERE singleton = 1",
                    [content_hash],
                )
                connection.execute(
                    "INSERT INTO registration_events VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        new_revision,
                        starting.content_sha256,
                        content_hash,
                        json.dumps(list(plan.new_dataset_ids), separators=(",", ":")),
                        registered_at_ms,
                        plan.software_identity,
                    ],
                )
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            after = _load_snapshot(connection)
            connection.execute("CHECKPOINT")
        except duckdb.Error as error:
            raise CatalogError("catalog transaction failed") from error
        finally:
            connection.close()
        with plan.building_path.open("r+b") as stream:
            os.fsync(stream.fileno())
        os.replace(plan.building_path, plan.catalog_path)
        verified = _verify_catalog_path(plan.catalog_path)
        if verified != after:
            raise CatalogError("atomically published catalog does not verify")
        return verified
    except FileExistsError as error:
        raise CatalogError("concurrent or stale catalog write lock detected") from error
    finally:
        if lock_descriptor is not None:
            os.close(lock_descriptor)
        if owns_building:
            plan.building_path.unlink(missing_ok=True)
        if owns_lock:
            plan.lock_path.unlink(missing_ok=True)


def selection_request_payload(request: CatalogSelectionRequest) -> dict[str, object]:
    instrument_filter: dict[str, object]
    if request.instrument_ids is None:
        instrument_filter = {"mode": "all"}
    else:
        instrument_filter = {
            "instrument_ids": list(request.instrument_ids),
            "mode": "include",
        }
    return {
        "catalog_content_sha256": request.catalog_content_sha256,
        "catalog_revision": request.catalog_revision,
        "consumer_software_identity": request.consumer_software_identity,
        "dataset_ids": list(request.dataset_ids),
        "dataset_type": request.dataset_type,
        "end_time_ms": request.end_time_ms,
        "instrument_filter": instrument_filter,
        "request_schema": CATALOG_SELECTION_REQUEST_CONTRACT,
        "start_time_ms": request.start_time_ms,
    }


def load_catalog_selection_request(path: Path) -> CatalogSelectionRequest:
    """Parse the closed v1 request shape without coercion or implicit defaults."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CatalogError("selection request is not valid JSON") from error
    if not isinstance(raw, dict) or set(raw) != {
        "catalog_content_sha256",
        "catalog_revision",
        "consumer_software_identity",
        "dataset_ids",
        "dataset_type",
        "end_time_ms",
        "instrument_filter",
        "request_schema",
        "start_time_ms",
    }:
        raise CatalogError("selection request fields do not match the closed v1 contract")
    if raw["request_schema"] != CATALOG_SELECTION_REQUEST_CONTRACT:
        raise CatalogError("unsupported selection request contract")
    dataset_ids_raw = raw["dataset_ids"]
    instrument_filter = raw["instrument_filter"]
    if not isinstance(dataset_ids_raw, list) or not all(
        isinstance(value, str) for value in dataset_ids_raw
    ):
        raise CatalogError("selection dataset_ids must be an array of strings")
    if not isinstance(instrument_filter, dict):
        raise CatalogError("selection instrument_filter must be an object")
    mode = instrument_filter.get("mode")
    instrument_ids: tuple[int, ...] | None
    if mode == "all" and set(instrument_filter) == {"mode"}:
        instrument_ids = None
    elif mode == "include" and set(instrument_filter) == {"instrument_ids", "mode"}:
        raw_ids = instrument_filter.get("instrument_ids")
        if not isinstance(raw_ids, list) or not all(
            isinstance(value, int) and not isinstance(value, bool) for value in raw_ids
        ):
            raise CatalogError("include-mode instrument_ids must be exact integers")
        instrument_ids = tuple(raw_ids)
    else:
        raise CatalogError("selection instrument_filter mode or fields are invalid")
    exact_int_fields = ("catalog_revision", "start_time_ms", "end_time_ms")
    if any(
        isinstance(raw[name], bool) or not isinstance(raw[name], int) for name in exact_int_fields
    ):
        raise CatalogError("selection revision and timestamps must be exact integers")
    exact_string_fields = (
        "catalog_content_sha256",
        "consumer_software_identity",
        "dataset_type",
    )
    if any(not isinstance(raw[name], str) for name in exact_string_fields):
        raise CatalogError("selection identity fields must be strings")
    try:
        dataset_type = DatasetType(cast(str, raw["dataset_type"]))
    except ValueError as error:
        raise CatalogError("selection dataset type is unknown") from error
    return CatalogSelectionRequest(
        catalog_revision=cast(int, raw["catalog_revision"]),
        catalog_content_sha256=cast(str, raw["catalog_content_sha256"]),
        dataset_ids=tuple(cast(list[str], dataset_ids_raw)),
        dataset_type=dataset_type,
        start_time_ms=cast(int, raw["start_time_ms"]),
        end_time_ms=cast(int, raw["end_time_ms"]),
        instrument_ids=instrument_ids,
        consumer_software_identity=cast(str, raw["consumer_software_identity"]),
    )


def _month_keys(start_time_ms: int, end_time_ms: int) -> tuple[tuple[int, int], ...]:
    start = datetime.fromtimestamp(start_time_ms / 1000, tz=UTC)
    end = datetime.fromtimestamp(end_time_ms / 1000, tz=UTC)
    year, month = start.year, start.month
    result = []
    while (year, month) <= (end.year, end.month):
        result.append((year, month))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return tuple(result)


def _required_partitions(request: CatalogSelectionRequest) -> tuple[str, ...]:
    buckets = (
        tuple(range(BUCKET_COUNT))
        if request.instrument_ids is None
        else tuple(sorted({stable_bucket(value) for value in request.instrument_ids}))
    )
    return tuple(
        f"dataset={request.dataset_type.value}/schema=v1/year={year:04d}/"
        f"month={month:02d}/bucket={bucket:02d}"
        for year, month in _month_keys(request.start_time_ms, request.end_time_ms)
        for bucket in buckets
    )


def _is_ancestor(
    candidate: str,
    dataset_id: str,
    records: dict[str, CatalogDatasetRecord],
) -> bool:
    pending = list(records[dataset_id].parent_dataset_ids)
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current == candidate:
            return True
        if current in visited:
            continue
        visited.add(current)
        if current in records:
            pending.extend(records[current].parent_dataset_ids)
    return False


def _iter_file_keys(
    path: Path,
    *,
    time_column: str,
) -> Iterator[tuple[int, int]]:
    """Yield one verified canonical file's exact keys with bounded batch memory."""

    previous: tuple[int, int] | None = None
    try:
        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(
            batch_size=EXACT_KEY_BATCH_ROWS,
            columns=["instrument_id", time_column],
            use_threads=False,
        ):
            instrument_ids = batch.column(0)
            timestamps = batch.column(1)
            for index in range(batch.num_rows):
                instrument_id = instrument_ids[index].as_py()
                timestamp_ms = timestamps[index].as_py()
                if (
                    isinstance(instrument_id, bool)
                    or not isinstance(instrument_id, int)
                    or isinstance(timestamp_ms, bool)
                    or not isinstance(timestamp_ms, int)
                ):
                    raise CatalogError("canonical file key columns must contain exact integers")
                key = (instrument_id, timestamp_ms)
                if previous is not None and key <= previous:
                    raise CatalogError("canonical file keys are not strictly sorted and unique")
                previous = key
                yield key
    except CatalogError:
        raise
    except (OSError, TypeError, ValueError) as error:
        raise CatalogError("canonical file keys cannot be streamed for exact admission") from error


def _assert_selected_keys_disjoint(
    store_root: Path,
    dataset_type: DatasetType,
    selected_files: list[tuple[CatalogDatasetRecord, CatalogFileRecord]],
) -> None:
    """Resolve ambiguous file bounds by merging exact sorted keys per partition."""

    time_column = "funding_time_ms" if dataset_type is DatasetType.FUNDING_EVENT else "open_time_ms"
    by_partition: dict[str, list[tuple[CatalogDatasetRecord, CatalogFileRecord]]] = {}
    for record, item in selected_files:
        by_partition.setdefault(record.partition_path, []).append((record, item))

    for partition_files in by_partition.values():
        ordered = sorted(
            partition_files,
            key=lambda value: (
                value[1].first_instrument_id,
                value[1].first_time_ms,
                value[0].dataset_id,
                value[1].ordinal,
            ),
        )
        if all(
            (left_file.last_instrument_id, left_file.last_time_ms)
            < (right_file.first_instrument_id, right_file.first_time_ms)
            for (_left_record, left_file), (_right_record, right_file) in pairwise(ordered)
        ):
            continue
        if len(ordered) > MAX_EXACT_KEY_STREAMS:
            raise CatalogError(
                "ambiguous canonical fragment count exceeds the exact-key admission bound; "
                "compact the partition before selection"
            )

        streams = [
            _iter_file_keys(
                store_root / "datasets" / record.dataset_id / item.dataset_relative_path,
                time_column=time_column,
            )
            for record, item in ordered
        ]
        previous: tuple[int, int] | None = None
        for key in merge(*streams):
            if key == previous:
                raise CatalogError(
                    "selected canonical objects contain duplicate or conflicting exact keys"
                )
            previous = key


def select_catalog_range(
    request: CatalogSelectionRequest,
    store_root: Path,
    catalog_path: Path,
) -> CatalogSelection:
    """Resolve an explicit catalog snapshot to hash-bound store-relative objects."""

    snapshot = verify_catalog(store_root, catalog_path)
    if (
        snapshot.revision != request.catalog_revision
        or snapshot.content_sha256 != request.catalog_content_sha256
    ):
        raise CatalogError("selection request does not bind the current catalog snapshot")
    records = {item.dataset_id: item for item in snapshot.datasets}
    missing = sorted(set(request.dataset_ids) - records.keys())
    if missing:
        raise CatalogError(f"selection datasets are not registered: {missing}")
    selected_records = tuple(records[value] for value in request.dataset_ids)
    if any(item.dataset_type is not request.dataset_type for item in selected_records):
        raise CatalogError("selection datasets do not share the requested dataset type")
    for record in selected_records:
        verified = _record_from_store(store_root.resolve(), record.dataset_id)
        if _record_binding(verified) != _record_binding(record):
            raise CatalogError("selected dataset no longer matches its catalog binding")
    for index, left in enumerate(request.dataset_ids):
        for right in request.dataset_ids[index + 1 :]:
            if _is_ancestor(left, right, records) or _is_ancestor(right, left, records):
                raise CatalogError("selection cannot contain both an ancestor and its child")
    required_partitions = _required_partitions(request)
    observed_partitions = {item.partition_path for item in selected_records}
    missing_partitions = sorted(set(required_partitions) - observed_partitions)
    if missing_partitions:
        raise CatalogError(
            f"selection is missing required month/bucket partitions: {missing_partitions}"
        )
    requested_ids = request.instrument_ids
    selected_files: list[tuple[CatalogDatasetRecord, CatalogFileRecord]] = []
    for record in selected_records:
        if record.partition_path not in required_partitions:
            continue
        for item in record.files:
            if item.max_time_ms < request.start_time_ms or item.min_time_ms > request.end_time_ms:
                continue
            if requested_ids is not None and not any(
                stable_bucket(instrument_id) == record.bucket
                and item.min_instrument_id <= instrument_id <= item.max_instrument_id
                for instrument_id in requested_ids
            ):
                continue
            selected_files.append((record, item))
    if not selected_files:
        raise CatalogError("selection resolved no canonical objects")
    sorted_files = sorted(
        selected_files,
        key=lambda value: (
            value[0].partition_path,
            value[1].first_instrument_id,
            value[1].first_time_ms,
            value[0].dataset_id,
            value[1].ordinal,
        ),
    )
    _assert_selected_keys_disjoint(store_root.resolve(), request.dataset_type, sorted_files)
    objects = tuple(
        SelectedCatalogObject(
            dataset_id=record.dataset_id,
            manifest_sha256=record.manifest_sha256,
            object_key=item.object_key,
            file_sha256=item.sha256,
            size_bytes=item.size_bytes,
            row_count=item.row_count,
            min_time_ms=item.min_time_ms,
            max_time_ms=item.max_time_ms,
            min_instrument_id=item.min_instrument_id,
            max_instrument_id=item.max_instrument_id,
            partition_path=record.partition_path,
        )
        for record, item in sorted_files
    )
    return CatalogSelection(
        request=request,
        snapshot=snapshot,
        objects=objects,
        required_partitions=required_partitions,
        selected_dataset_manifest_sha256=tuple(
            (item.dataset_id, item.manifest_sha256) for item in selected_records
        ),
    )
