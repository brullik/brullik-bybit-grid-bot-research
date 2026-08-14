"""GitHub-safe evidence for catalog registration and reproducible range selection."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_market_store.catalog import (
    CATALOG_REGISTRATION_CONTRACT,
    CATALOG_SCHEMA_VERSION,
    CATALOG_SELECTION_CONTRACT,
    CatalogRegistrationPlan,
    CatalogSelection,
    CatalogSnapshot,
    load_catalog_registration_request,
    selection_request_payload,
)

from grid_data.evidence import verify_evidence


class DatasetCatalogEvidenceError(RuntimeError):
    """Catalog evidence is missing, substituted, or not GitHub-safe."""


FULL_HISTORY_CATALOG_EVIDENCE_CONTRACT = "grid.phase2-full-history-catalog/v1"
_GIT_IDENTITY_RE = re.compile(r"^git:[0-9a-f]{40}$")
_PARTITION_RE = re.compile(
    r"^dataset=(trade_kline_1m|mark_kline_1m)/schema=v1/"
    r"year=([0-9]{4})/month=(0[1-9]|1[0-2])/bucket=(0[0-7])$"
)


def _generated_at(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DatasetCatalogEvidenceError("generated_at_utc must be ISO-8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DatasetCatalogEvidenceError("generated_at_utc must be timezone-aware")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _with_content_hash(payload: dict[str, object]) -> dict[str, object]:
    result = dict(payload)
    result["content_sha256"] = canonical_sha256(payload)
    return result


def build_catalog_registration_evidence(
    plan: CatalogRegistrationPlan,
    snapshot: CatalogSnapshot,
    *,
    generated_at_utc: str,
) -> dict[str, object]:
    """Build value-free proof that requested manifests are bound into one catalog snapshot."""

    registered = {item.dataset_id: item for item in snapshot.datasets}
    requested = []
    for dataset_id in plan.requested_dataset_ids:
        record = registered.get(dataset_id)
        if record is None:
            raise DatasetCatalogEvidenceError("registered dataset is absent from final catalog")
        requested.append(
            {
                "audit_report_count": len(record.audit_report_sha256),
                "conflict_count": record.conflict_count,
                "dataset_id": record.dataset_id,
                "dataset_type": record.dataset_type,
                "file_count": len(record.files),
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
                    "year": record.year,
                },
                "registered_revision": record.registered_revision,
                "row_count": record.row_count,
                "schema_version": record.schema_version,
                "semantic_version": record.semantic_version,
                "status": record.status,
                "total_size_bytes": record.total_size_bytes,
            }
        )
    payload: dict[str, object] = {
        "catalog": {
            "backend": "duckdb",
            "content_sha256": snapshot.content_sha256,
            "dataset_count": snapshot.dataset_count,
            "file_count": snapshot.file_count,
            "revision": snapshot.revision,
            "schema_version": CATALOG_SCHEMA_VERSION,
        },
        "datasets": requested,
        "evidence_schema": CATALOG_REGISTRATION_CONTRACT,
        "generated_at_utc": _generated_at(generated_at_utc),
        "limitations": [
            "The catalog is a rebuildable metadata index; verified dataset receipts remain "
            "authoritative.",
            "A not-assessed gap status is not historical completeness or Gate 2 acceptance.",
            "This evidence contains no market values, credentials, account data, host identity, "
            "or absolute paths.",
        ],
        "registration": {
            "requested_dataset_ids": list(plan.requested_dataset_ids),
            "software_identity": plan.software_identity,
        },
        "safety": {
            "absolute_paths_included": False,
            "account_data_included": False,
            "credentials_included": False,
            "market_values_included": False,
            "receipt_verified_inputs": True,
        },
        "status": "passed",
    }
    return _with_content_hash(payload)


def build_catalog_selection_evidence(
    selection: CatalogSelection,
    *,
    generated_at_utc: str,
) -> dict[str, object]:
    """Build a receipt-ready manifest of exact logical objects selected from a bound snapshot."""

    objects = [
        {
            "dataset_id": item.dataset_id,
            "file_sha256": item.file_sha256,
            "manifest_sha256": item.manifest_sha256,
            "max_instrument_id": item.max_instrument_id,
            "max_time_ms": item.max_time_ms,
            "min_instrument_id": item.min_instrument_id,
            "min_time_ms": item.min_time_ms,
            "object_key": item.object_key,
            "row_count": item.row_count,
            "size_bytes": item.size_bytes,
        }
        for item in selection.objects
    ]
    payload: dict[str, object] = {
        "catalog": {
            "content_sha256": selection.snapshot.content_sha256,
            "revision": selection.snapshot.revision,
            "schema_version": CATALOG_SCHEMA_VERSION,
        },
        "evidence_schema": CATALOG_SELECTION_CONTRACT,
        "generated_at_utc": _generated_at(generated_at_utc),
        "limitations": [
            "Selection proves deterministic partition/file pruning, not gap-free historical "
            "coverage.",
            "Every dataset and file hash is re-verified, but consumers must still enforce their "
            "PM-owned coverage policy.",
            "Object keys are canonical store-relative identities; no host or absolute path is "
            "included.",
        ],
        "objects": objects,
        "request": selection_request_payload(selection.request),
        "request_sha256": selection.request.request_sha256,
        "required_partitions": list(selection.required_partitions),
        "selected_dataset_manifests": [
            {"dataset_id": dataset_id, "manifest_sha256": manifest_sha256}
            for dataset_id, manifest_sha256 in selection.selected_dataset_manifest_sha256
        ],
        "selection": {
            "object_count": len(objects),
            "selected_row_inventory": sum(item.row_count for item in selection.objects),
            "selected_size_bytes": sum(item.size_bytes for item in selection.objects),
        },
        "safety": {
            "absolute_paths_included": False,
            "account_data_included": False,
            "credentials_included": False,
            "market_values_included": False,
            "receipt_verified_inputs": True,
        },
        "status": "passed",
    }
    return _with_content_hash(payload)


def _load_verified_payload(path: Path, expected_schema: str) -> dict[str, object]:
    if not verify_evidence(path):
        raise DatasetCatalogEvidenceError("catalog evidence receipt does not verify")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DatasetCatalogEvidenceError("catalog evidence is not valid JSON") from error
    if not isinstance(raw, dict) or raw.get("evidence_schema") != expected_schema:
        raise DatasetCatalogEvidenceError("catalog evidence schema does not match")
    content_hash = raw.get("content_sha256")
    hash_input = dict(raw)
    hash_input.pop("content_sha256", None)
    if content_hash != canonical_sha256(hash_input):
        raise DatasetCatalogEvidenceError("catalog evidence content hash does not verify")
    return cast(dict[str, object], raw)


def verify_catalog_registration_evidence(
    path: Path,
    plan: CatalogRegistrationPlan,
    snapshot: CatalogSnapshot,
) -> dict[str, object]:
    payload = _load_verified_payload(path, CATALOG_REGISTRATION_CONTRACT)
    generated = payload.get("generated_at_utc")
    if not isinstance(generated, str):
        raise DatasetCatalogEvidenceError("registration evidence timestamp is invalid")
    expected = build_catalog_registration_evidence(
        plan,
        snapshot,
        generated_at_utc=generated,
    )
    if payload != expected:
        raise DatasetCatalogEvidenceError("registration evidence conflicts with catalog state")
    return payload


def verify_catalog_selection_evidence(
    path: Path,
    selection: CatalogSelection,
) -> dict[str, object]:
    payload = _load_verified_payload(path, CATALOG_SELECTION_CONTRACT)
    generated = payload.get("generated_at_utc")
    if not isinstance(generated, str):
        raise DatasetCatalogEvidenceError("selection evidence timestamp is invalid")
    expected = build_catalog_selection_evidence(
        selection,
        generated_at_utc=generated,
    )
    if payload != expected:
        raise DatasetCatalogEvidenceError("selection evidence conflicts with catalog state")
    return payload


def _mapping(parent: dict[str, object], key: str) -> dict[str, object]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise DatasetCatalogEvidenceError(f"catalog aggregate field must be an object: {key}")
    return cast(dict[str, object], value)


def _array(parent: dict[str, object], key: str) -> list[object]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise DatasetCatalogEvidenceError(f"catalog aggregate field must be an array: {key}")
    return value


def _integer(parent: dict[str, object], key: str, *, minimum: int = 0) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise DatasetCatalogEvidenceError(f"catalog aggregate integer is invalid: {key}")
    return value


def _sha(parent: dict[str, object], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise DatasetCatalogEvidenceError(f"catalog aggregate SHA-256 is invalid: {key}")
    return value


def _text(parent: dict[str, object], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value or value.strip() != value:
        raise DatasetCatalogEvidenceError(f"catalog aggregate text is invalid: {key}")
    return value


def _selection_partitions(
    dataset_type: str,
    start_time_ms: int,
    end_time_ms: int,
    instrument_ids: list[int],
) -> set[str]:
    start = datetime.fromtimestamp(start_time_ms / 1000, tz=UTC)
    end = datetime.fromtimestamp(end_time_ms / 1000, tz=UTC)
    year, month = start.year, start.month
    months = []
    while (year, month) <= (end.year, end.month):
        months.append((year, month))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return {
        f"dataset={dataset_type}/schema=v1/year={year:04d}/month={month:02d}/bucket={bucket:02d}"
        for year, month in months
        for bucket in sorted({value % 8 for value in instrument_ids})
    }


def build_full_history_catalog_evidence(
    registration_request_path: Path,
    registration_path: Path,
    selection_paths: tuple[Path, ...],
    *,
    generated_at_utc: str,
    software_identity: str,
) -> dict[str, object]:
    """Project a verified full-history registration/selection chain without private identities."""

    if _GIT_IDENTITY_RE.fullmatch(software_identity) is None:
        raise DatasetCatalogEvidenceError("catalog evidence identity must be git:<40 hex>")
    generated_at = _generated_at(generated_at_utc)
    if len(selection_paths) != 4 or len({path.resolve() for path in selection_paths}) != 4:
        raise DatasetCatalogEvidenceError("full-history catalog evidence requires four selections")
    if not verify_evidence(registration_request_path):
        raise DatasetCatalogEvidenceError("catalog registration request receipt does not verify")
    registration_request = load_catalog_registration_request(registration_request_path)
    registration = _load_verified_payload(registration_path, CATALOG_REGISTRATION_CONTRACT)
    selections = tuple(
        (
            path.resolve(),
            _load_verified_payload(path, CATALOG_SELECTION_CONTRACT),
        )
        for path in selection_paths
    )

    catalog = _mapping(registration, "catalog")
    catalog_revision = _integer(catalog, "revision", minimum=1)
    catalog_content_sha256 = _sha(catalog, "content_sha256")
    registration_details = _mapping(registration, "registration")
    requested_ids = _array(registration_details, "requested_dataset_ids")
    if requested_ids != list(registration_request.dataset_ids):
        raise DatasetCatalogEvidenceError("registration request and evidence inventories differ")
    if registration_details.get("software_identity") != registration_request.software_identity:
        raise DatasetCatalogEvidenceError("registration request and evidence identities differ")

    raw_datasets = _array(registration, "datasets")
    dataset_by_id: dict[str, dict[str, object]] = {}
    manifest_by_id: dict[str, str] = {}
    partition_by_id: dict[str, str] = {}
    for value in raw_datasets:
        if not isinstance(value, dict):
            raise DatasetCatalogEvidenceError("registration dataset record must be an object")
        item = cast(dict[str, object], value)
        dataset_id = _text(item, "dataset_id")
        dataset_type = _text(item, "dataset_type")
        if dataset_type not in {"trade_kline_1m", "mark_kline_1m"}:
            raise DatasetCatalogEvidenceError("full-history catalog evidence is candle-only")
        if dataset_id in dataset_by_id:
            raise DatasetCatalogEvidenceError("registration dataset identities are duplicated")
        partition = _mapping(item, "partition")
        year = _integer(partition, "year", minimum=1970)
        month = _integer(partition, "month", minimum=1)
        bucket = _integer(partition, "bucket")
        if month > 12 or bucket > 7:
            raise DatasetCatalogEvidenceError("registration partition facts are invalid")
        dataset_by_id[dataset_id] = item
        manifest_by_id[dataset_id] = _sha(item, "manifest_sha256")
        partition_by_id[dataset_id] = (
            f"dataset={dataset_type}/schema=v1/year={year:04d}/"
            f"month={month:02d}/bucket={bucket:02d}"
        )
    if set(dataset_by_id) != set(registration_request.dataset_ids):
        raise DatasetCatalogEvidenceError("registration dataset details are incomplete")

    grouped: dict[str, list[dict[str, object]]] = {
        "trade_kline_1m": [],
        "mark_kline_1m": [],
    }
    selected_dataset_ids: set[str] = set()
    selected_manifest_by_id: dict[str, str] = {}
    selected_partitions: set[str] = set()
    selected_row_count = 0
    selected_size_bytes = 0
    selected_object_count = 0
    empty_object_count = 0
    selection_bindings: list[dict[str, object]] = []

    for path, selection in selections:
        selection_catalog = _mapping(selection, "catalog")
        if (
            _integer(selection_catalog, "revision", minimum=1) != catalog_revision
            or _sha(selection_catalog, "content_sha256") != catalog_content_sha256
        ):
            raise DatasetCatalogEvidenceError("selection binds a different catalog snapshot")
        request = _mapping(selection, "request")
        if _sha(selection, "request_sha256") != canonical_sha256(request):
            raise DatasetCatalogEvidenceError("selection request content hash differs")
        dataset_type = _text(request, "dataset_type")
        if dataset_type not in grouped:
            raise DatasetCatalogEvidenceError("full-history selection type is invalid")
        if (
            _integer(request, "catalog_revision", minimum=1) != catalog_revision
            or _sha(request, "catalog_content_sha256") != catalog_content_sha256
        ):
            raise DatasetCatalogEvidenceError("selection request catalog binding differs")
        start_time_ms = _integer(request, "start_time_ms")
        end_time_ms = _integer(request, "end_time_ms")
        if start_time_ms % 60_000 or end_time_ms % 60_000 or end_time_ms < start_time_ms:
            raise DatasetCatalogEvidenceError("selection request time bounds are invalid")
        instrument_filter = _mapping(request, "instrument_filter")
        raw_instrument_ids = _array(instrument_filter, "instrument_ids")
        if instrument_filter.get("mode") != "include" or not raw_instrument_ids:
            raise DatasetCatalogEvidenceError("full-history selection requires include mode")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 2**32 - 1
            for value in raw_instrument_ids
        ):
            raise DatasetCatalogEvidenceError("selection instrument inventory is invalid")
        if raw_instrument_ids != sorted(set(cast(list[int], raw_instrument_ids))):
            raise DatasetCatalogEvidenceError("selection instrument inventory is not canonical")
        request_dataset_ids = _array(request, "dataset_ids")
        if not request_dataset_ids or any(
            not isinstance(value, str) for value in request_dataset_ids
        ):
            raise DatasetCatalogEvidenceError("selection dataset inventory is invalid")
        typed_request_dataset_ids = cast(list[str], request_dataset_ids)
        if typed_request_dataset_ids != sorted(set(typed_request_dataset_ids)):
            raise DatasetCatalogEvidenceError("selection dataset inventory is not canonical")
        if any(
            value not in dataset_by_id or dataset_by_id[value].get("dataset_type") != dataset_type
            for value in typed_request_dataset_ids
        ):
            raise DatasetCatalogEvidenceError("selection names an unregistered dataset or type")
        overlap = selected_dataset_ids.intersection(typed_request_dataset_ids)
        if overlap:
            raise DatasetCatalogEvidenceError("full-history selections overlap dataset identity")
        selected_dataset_ids.update(typed_request_dataset_ids)

        raw_manifests = _array(selection, "selected_dataset_manifests")
        selection_manifest_ids: set[str] = set()
        for value in raw_manifests:
            if not isinstance(value, dict):
                raise DatasetCatalogEvidenceError("selected manifest binding must be an object")
            manifest = cast(dict[str, object], value)
            dataset_id = _text(manifest, "dataset_id")
            manifest_sha256 = _sha(manifest, "manifest_sha256")
            if (
                dataset_id in selection_manifest_ids
                or dataset_id not in typed_request_dataset_ids
                or manifest_by_id.get(dataset_id) != manifest_sha256
            ):
                raise DatasetCatalogEvidenceError("selected manifest binding differs")
            selection_manifest_ids.add(dataset_id)
            selected_manifest_by_id[dataset_id] = manifest_sha256
        if selection_manifest_ids != set(typed_request_dataset_ids):
            raise DatasetCatalogEvidenceError("selection manifest inventory is incomplete")

        required_partitions = _array(selection, "required_partitions")
        if any(not isinstance(value, str) for value in required_partitions):
            raise DatasetCatalogEvidenceError("selection required partition is invalid")
        typed_required_partitions = cast(list[str], required_partitions)
        partition_matches = tuple(
            _PARTITION_RE.fullmatch(value) for value in typed_required_partitions
        )
        if any(value is None for value in partition_matches):
            raise DatasetCatalogEvidenceError("selection required partition is invalid")
        if len(typed_required_partitions) != len(set(typed_required_partitions)):
            raise DatasetCatalogEvidenceError("selection required partitions are duplicated")
        expected_partitions = {partition_by_id[value] for value in typed_request_dataset_ids}
        request_partitions = _selection_partitions(
            dataset_type,
            start_time_ms,
            end_time_ms,
            cast(list[int], raw_instrument_ids),
        )
        if (
            set(typed_required_partitions) != expected_partitions
            or set(typed_required_partitions) != request_partitions
        ):
            raise DatasetCatalogEvidenceError("selection partition inventory differs")
        if selected_partitions.intersection(typed_required_partitions):
            raise DatasetCatalogEvidenceError("full-history selections overlap partition identity")
        selected_partitions.update(typed_required_partitions)

        objects = _array(selection, "objects")
        object_dataset_ids: set[str] = set()
        object_count_by_dataset: dict[str, int] = {}
        object_keys: set[str] = set()
        object_rows = 0
        object_bytes = 0
        selection_empty_objects = 0
        for value in objects:
            if not isinstance(value, dict):
                raise DatasetCatalogEvidenceError("selected object binding must be an object")
            item = cast(dict[str, object], value)
            dataset_id = _text(item, "dataset_id")
            if dataset_id not in typed_request_dataset_ids:
                raise DatasetCatalogEvidenceError("selected object is outside the request")
            if _sha(item, "manifest_sha256") != manifest_by_id[dataset_id]:
                raise DatasetCatalogEvidenceError("selected object manifest binding differs")
            _sha(item, "file_sha256")
            object_key = _text(item, "object_key")
            if object_key in object_keys:
                raise DatasetCatalogEvidenceError("selected object identities are duplicated")
            object_keys.add(object_key)
            object_dataset_ids.add(dataset_id)
            object_count_by_dataset[dataset_id] = object_count_by_dataset.get(dataset_id, 0) + 1
            row_count = _integer(item, "row_count")
            object_rows += row_count
            object_bytes += _integer(item, "size_bytes", minimum=1)
            selection_empty_objects += row_count == 0
        if object_dataset_ids != set(typed_request_dataset_ids):
            raise DatasetCatalogEvidenceError("selection object inventory is incomplete")
        if any(
            object_count_by_dataset[dataset_id]
            != _integer(dataset_by_id[dataset_id], "file_count", minimum=1)
            for dataset_id in typed_request_dataset_ids
        ):
            raise DatasetCatalogEvidenceError("selection file inventory differs from registration")
        selection_summary = _mapping(selection, "selection")
        if selection_summary != {
            "object_count": len(objects),
            "selected_row_inventory": object_rows,
            "selected_size_bytes": object_bytes,
        }:
            raise DatasetCatalogEvidenceError("selection aggregate facts differ")
        grouped[dataset_type].append(
            {
                "artifact_sha256": sha256_file(path),
                "bucket_count": len(
                    {cast(re.Match[str], value).group(4) for value in partition_matches}
                ),
                "content_sha256": _sha(selection, "content_sha256"),
                "dataset_count": len(typed_request_dataset_ids),
                "empty_object_count": selection_empty_objects,
                "end_time_ms": end_time_ms,
                "instrument_count": len(raw_instrument_ids),
                "month_count": len(
                    {
                        (cast(re.Match[str], value).group(2), cast(re.Match[str], value).group(3))
                        for value in partition_matches
                    }
                ),
                "object_count": len(objects),
                "request_sha256": _sha(selection, "request_sha256"),
                "row_count": object_rows,
                "size_bytes": object_bytes,
                "start_time_ms": start_time_ms,
            }
        )
        selected_row_count += object_rows
        selected_size_bytes += object_bytes
        selected_object_count += len(objects)
        empty_object_count += selection_empty_objects

    if selected_dataset_ids != set(dataset_by_id) or selected_manifest_by_id != manifest_by_id:
        raise DatasetCatalogEvidenceError("selection union does not equal the registration")
    if selected_partitions != set(partition_by_id.values()):
        raise DatasetCatalogEvidenceError("selection partition union does not equal registration")
    registration_row_count = sum(_integer(item, "row_count") for item in dataset_by_id.values())
    registration_size_bytes = sum(
        _integer(item, "total_size_bytes", minimum=1) for item in dataset_by_id.values()
    )
    registration_empty_count = sum(
        _integer(item, "row_count") == 0 for item in dataset_by_id.values()
    )
    if (
        selected_row_count != registration_row_count
        or selected_size_bytes != registration_size_bytes
        or empty_object_count != registration_empty_count
    ):
        raise DatasetCatalogEvidenceError("selection aggregate does not reconcile to registration")

    for dataset_type, segments in grouped.items():
        if len(segments) != 2:
            raise DatasetCatalogEvidenceError(f"{dataset_type} requires two topology segments")
        segments.sort(key=lambda item: cast(int, item["start_time_ms"]))
    trade_segments = grouped["trade_kline_1m"]
    mark_segments = grouped["mark_kline_1m"]
    for index in range(2):
        trade = trade_segments[index]
        mark = mark_segments[index]
        if any(
            trade[key] != mark[key]
            for key in (
                "bucket_count",
                "end_time_ms",
                "instrument_count",
                "month_count",
                "start_time_ms",
            )
        ):
            raise DatasetCatalogEvidenceError("trade/mark topology segments differ")
    if any(
        cast(int, segments[0]["end_time_ms"]) + 60_000 != cast(int, segments[1]["start_time_ms"])
        for segments in grouped.values()
    ):
        raise DatasetCatalogEvidenceError("selection topology segments are not contiguous")

    for dataset_type, segments in grouped.items():
        for index, segment in enumerate(segments, start=1):
            selection_bindings.append(
                {
                    "artifact_sha256": segment["artifact_sha256"],
                    "content_sha256": segment["content_sha256"],
                    "kind": "trade" if dataset_type == "trade_kline_1m" else "mark",
                    "request_sha256": segment["request_sha256"],
                    "segment": index,
                }
            )

    by_kind = []
    for dataset_type, kind in (("trade_kline_1m", "trade"), ("mark_kline_1m", "mark")):
        items = [
            item for item in dataset_by_id.values() if item.get("dataset_type") == dataset_type
        ]
        by_kind.append(
            {
                "dataset_count": len(items),
                "empty_dataset_count": sum(_integer(item, "row_count") == 0 for item in items),
                "kind": kind,
                "object_count": sum(
                    cast(int, segment["object_count"]) for segment in grouped[dataset_type]
                ),
                "row_count": sum(_integer(item, "row_count") for item in items),
                "size_bytes": sum(_integer(item, "total_size_bytes", minimum=1) for item in items),
            }
        )
    topology = []
    for index in range(2):
        paired = (trade_segments[index], mark_segments[index])
        topology.append(
            {
                "bucket_count": trade_segments[index]["bucket_count"],
                "dataset_count": sum(cast(int, item["dataset_count"]) for item in paired),
                "empty_dataset_count": sum(
                    cast(int, item["empty_object_count"]) for item in paired
                ),
                "instrument_count": trade_segments[index]["instrument_count"],
                "month_count": trade_segments[index]["month_count"],
                "object_count": sum(cast(int, item["object_count"]) for item in paired),
                "row_count": sum(cast(int, item["row_count"]) for item in paired),
                "segment": index + 1,
                "size_bytes": sum(cast(int, item["size_bytes"]) for item in paired),
            }
        )

    payload: dict[str, object] = {
        "bindings": {
            "registration": {
                "artifact_sha256": sha256_file(registration_path),
                "content_sha256": _sha(registration, "content_sha256"),
                "request_artifact_sha256": sha256_file(registration_request_path),
                "request_sha256": registration_request.request_sha256,
            },
            "selections": selection_bindings,
        },
        "catalog": {
            "content_sha256": catalog_content_sha256,
            "revision": catalog_revision,
            "schema_version": _integer(catalog, "schema_version", minimum=1),
        },
        "evidence_schema": FULL_HISTORY_CATALOG_EVIDENCE_CONTRACT,
        "generated_at_utc": generated_at,
        "inventory": {
            "by_kind": by_kind,
            "dataset_count": len(dataset_by_id),
            "empty_dataset_count": registration_empty_count,
            "object_count": selected_object_count,
            "required_partition_count": len(selected_partitions),
            "row_count": selected_row_count,
            "size_bytes": selected_size_bytes,
        },
        "limitations": [
            "Catalog registration and deterministic selection do not prove gap-free historical "
            "coverage.",
            "Topology segments preserve campaign partition presence but do not infer lifecycle "
            "metadata.",
            "Schema-only selected objects preserve source lineage and do not accept missing "
            "history.",
            "The DuckDB catalog remains a rebuildable index; canonical receipts remain "
            "authoritative.",
            "This evidence does not close Gate 2 or authorize research promotion or live "
            "execution.",
        ],
        "process": {
            "catalog_registration_receipt_verified": True,
            "evidence_builder_software_identity": software_identity,
            "registration_request_receipt_verified": True,
            "selection_receipts_verified": True,
            "selection_union_matches_registration": True,
        },
        "status": "verified-full-history-catalog-selection",
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_dataset_identities": False,
            "evidence_contains_instrument_identities": False,
            "evidence_contains_market_values": False,
            "evidence_contains_runtime_paths": False,
            "runtime_catalog_or_market_artifacts_committed_to_git": False,
        },
        "topology": topology,
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload
