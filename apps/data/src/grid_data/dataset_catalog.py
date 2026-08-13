"""GitHub-safe evidence for catalog registration and reproducible range selection."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from grid_contracts.canonical import canonical_sha256
from grid_market_store.catalog import (
    CATALOG_REGISTRATION_CONTRACT,
    CATALOG_SCHEMA_VERSION,
    CATALOG_SELECTION_CONTRACT,
    CatalogRegistrationPlan,
    CatalogSelection,
    CatalogSnapshot,
    selection_request_payload,
)

from grid_data.evidence import verify_evidence


class DatasetCatalogEvidenceError(RuntimeError):
    """Catalog evidence is missing, substituted, or not GitHub-safe."""


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
