"""Measure the receipt-bound current-universe catalog bundle without mutation."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter_ns
from typing import Any, Final, cast

import duckdb
import psutil  # type: ignore[import-untyped]
import pyarrow as pa  # type: ignore[import-untyped]
from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file
from grid_data.evidence import preflight_evidence, publish_evidence, verify_evidence
from grid_market_store.catalog import (
    CatalogSelection,
    CatalogSelectionRequest,
    load_catalog_selection_request,
    select_catalog_ranges,
    verify_catalog,
)
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]
from referencing import Registry, Resource

EVIDENCE_CONTRACT: Final = "grid.phase2-current-universe-catalog-performance/v1"
BUNDLE_EVIDENCE_CONTRACT: Final = "grid.phase2-catalog-selection-bundle/v1"
BUNDLE_PLAN_CONTRACT: Final = "grid.canonical-catalog-selection-bundle-plan/v1"
BUNDLE_MANIFEST_CONTRACT: Final = "grid.canonical-catalog-selection-bundle-manifest/v1"
SELECTION_CONTRACT: Final = "grid.canonical-dataset-selection/v1"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
MAX_SELECTION_COUNT: Final = 512
MAX_DATASET_COUNT: Final = 10_000
MAX_OBJECT_COUNT: Final = 100_000
MAX_ROW_COUNT: Final = 20_000_000_000
MAX_SIZE_BYTES: Final = 2_000_000_000_000


class CurrentUniverseCatalogPerformanceError(RuntimeError):
    """The retained current-universe catalog benchmark failed closed."""


@dataclass(frozen=True, slots=True)
class _SelectionInput:
    expected_fingerprint_sha256: str
    expected_object_count: int
    expected_row_count: int
    expected_size_bytes: int
    kind: str
    request: CatalogSelectionRequest
    sequence: int


@dataclass(frozen=True, slots=True)
class _MeasuredSelection:
    fingerprint_sha256: str
    object_count: int
    row_count: int
    size_bytes: int


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CurrentUniverseCatalogPerformanceError(message)


def _mapping(parent: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise CurrentUniverseCatalogPerformanceError(f"evidence field must be an object: {key}")
    return cast(dict[str, Any], value)


def _array(parent: Mapping[str, Any], key: str) -> list[Any]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise CurrentUniverseCatalogPerformanceError(f"evidence field must be an array: {key}")
    return value


def _integer(
    parent: Mapping[str, Any], key: str, *, minimum: int = 0, maximum: int | None = None
) -> int:
    value = parent.get(key)
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or (maximum is not None and value > maximum)
    ):
        raise CurrentUniverseCatalogPerformanceError(f"evidence integer is invalid: {key}")
    return value


def _sha(parent: Mapping[str, Any], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise CurrentUniverseCatalogPerformanceError(f"evidence SHA-256 is invalid: {key}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CurrentUniverseCatalogPerformanceError(
            f"invalid JSON evidence: {path.name}"
        ) from error
    if not isinstance(value, dict):
        raise CurrentUniverseCatalogPerformanceError(
            f"JSON evidence must be an object: {path.name}"
        )
    return cast(dict[str, Any], value)


def _validate_payload(payload: Mapping[str, Any], schema_path: Path) -> None:
    try:
        schema = _load_json(schema_path)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    except Exception as error:
        raise CurrentUniverseCatalogPerformanceError(
            f"evidence schema does not verify: {schema_path.name}"
        ) from error


def _market_schema_registry(schema_root: Path) -> Registry:
    names = (
        "canonical-catalog-selection-bundle-request.schema.json",
        "canonical-catalog-selection-bundle-plan.schema.json",
        "canonical-catalog-selection-bundle-manifest.schema.json",
        "canonical-dataset-selection-request.schema.json",
    )
    resources: list[tuple[str, Resource[Any]]] = []
    canonical_base = "https://github.com/brullik/brullik-bybit-grid-bot-research/schemas/market/v1/"
    for name in names:
        schema = _load_json(schema_root / name)
        schema_id = schema.get("$id")
        if not isinstance(schema_id, str):
            raise CurrentUniverseCatalogPerformanceError(f"market schema has no $id: {name}")
        resource = Resource.from_contents(schema)
        resources.append((schema_id, resource))
        canonical_uri = f"{canonical_base}{name}"
        if canonical_uri != schema_id:
            resources.append((canonical_uri, resource))
    return Registry().with_resources(resources)


def _validate_market_payload(
    payload: Mapping[str, Any], *, schema_root: Path, schema_name: str, registry: Registry
) -> None:
    try:
        Draft202012Validator(
            _load_json(schema_root / schema_name),
            registry=registry,
            format_checker=FormatChecker(),
        ).validate(payload)
    except Exception as error:
        raise CurrentUniverseCatalogPerformanceError(
            f"evidence schema does not verify: {schema_name}"
        ) from error


def _load_receipt_bound(path: Path) -> dict[str, Any]:
    receipt = path.with_suffix(path.suffix + ".receipt.json")
    _require(
        path.is_file() and receipt.is_file() and not path.is_symlink() and not receipt.is_symlink(),
        f"evidence artifact/receipt pair is unsafe or missing: {path.name}",
    )
    if not verify_evidence(path):
        raise CurrentUniverseCatalogPerformanceError(
            f"evidence receipt does not verify: {path.name}"
        )
    return _load_json(path)


def _verify_content_hash(payload: Mapping[str, Any], *, label: str) -> None:
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256", None)
    _require(embedded_hash == canonical_sha256(hash_input), f"content hash differs: {label}")


def _verify_generated_at(generated_at_utc: str) -> None:
    _require(generated_at_utc.endswith("Z"), "generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(generated_at_utc.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise CurrentUniverseCatalogPerformanceError("generated_at_utc is invalid") from error
    offset = parsed.utcoffset()
    _require(offset is not None and offset.total_seconds() == 0, "generated_at_utc must be UTC")


def _selection_payload_fingerprint(payload: Mapping[str, Any]) -> str:
    objects = []
    for raw in _array(payload, "objects"):
        _require(isinstance(raw, dict), "selection object must be an object")
        item = cast(dict[str, Any], raw)
        objects.append(
            {
                "file_sha256": _sha(item, "file_sha256"),
                "manifest_sha256": _sha(item, "manifest_sha256"),
                "row_count": _integer(item, "row_count"),
                "size_bytes": _integer(item, "size_bytes"),
            }
        )
    manifests = []
    for raw in _array(payload, "selected_dataset_manifests"):
        _require(isinstance(raw, dict), "selected manifest must be an object")
        manifests.append(_sha(cast(dict[str, Any], raw), "manifest_sha256"))
    return canonical_sha256(
        {
            "objects": objects,
            "request_sha256": _sha(payload, "request_sha256"),
            "required_partition_count": len(_array(payload, "required_partitions")),
            "selected_manifest_sha256": manifests,
        }
    )


def _selection_runtime_fingerprint(selection: CatalogSelection) -> str:
    return canonical_sha256(
        {
            "objects": [
                {
                    "file_sha256": item.file_sha256,
                    "manifest_sha256": item.manifest_sha256,
                    "row_count": item.row_count,
                    "size_bytes": item.size_bytes,
                }
                for item in selection.objects
            ],
            "request_sha256": selection.request.request_sha256,
            "required_partition_count": len(selection.required_partitions),
            "selected_manifest_sha256": [
                manifest_sha256
                for _dataset_id, manifest_sha256 in selection.selected_dataset_manifest_sha256
            ],
        }
    )


def _metadata_fingerprint(store_root: Path, dataset_ids: Sequence[str]) -> str:
    root = store_root.resolve()
    dataset_namespace = (root / "datasets").resolve()
    entries: list[dict[str, object]] = []
    for dataset_id in sorted(set(dataset_ids)):
        _require(
            bool(dataset_id)
            and dataset_id not in {".", ".."}
            and "/" not in dataset_id
            and "\\" not in dataset_id,
            "selection contains an unsafe dataset identity",
        )
        unresolved_dataset_root = dataset_namespace / dataset_id
        _require(not unresolved_dataset_root.is_symlink(), "selected dataset root is a symlink")
        dataset_root = unresolved_dataset_root.resolve()
        try:
            dataset_root.relative_to(dataset_namespace)
        except ValueError as error:
            raise CurrentUniverseCatalogPerformanceError(
                "selection dataset resolves outside the market store"
            ) from error
        _require(dataset_root.is_dir(), "selected dataset directory is missing")
        for path in sorted(
            dataset_root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
        ):
            _require(not path.is_symlink(), "selected dataset contains a symbolic link")
            stat = path.stat()
            relative = path.relative_to(root).as_posix()
            if path.is_dir():
                entries.append({"kind": "directory", "path": relative})
            elif path.is_file():
                entries.append(
                    {
                        "kind": "file",
                        "modified_ns": stat.st_mtime_ns,
                        "path": relative,
                        "size_bytes": stat.st_size,
                    }
                )
            else:
                raise CurrentUniverseCatalogPerformanceError(
                    "selected dataset contains an unsafe path type"
                )
    return canonical_sha256(entries)


def _load_inputs(
    *,
    repo_root: Path,
    bundle_root: Path,
    bundle_evidence_path: Path,
) -> tuple[
    tuple[_SelectionInput, ...],
    tuple[str, ...],
    dict[str, Any],
    str,
]:
    schema_root = repo_root / "schemas"
    market_schema_root = schema_root / "market" / "v1"
    evidence_schema_root = schema_root / "evidence" / "v1"
    registry = _market_schema_registry(market_schema_root)

    plan_path = bundle_root / "plan.json"
    manifest_path = bundle_root / "manifest.json"
    plan = _load_receipt_bound(plan_path)
    manifest = _load_receipt_bound(manifest_path)
    bundle_evidence = _load_receipt_bound(bundle_evidence_path)
    _validate_market_payload(
        plan,
        schema_root=market_schema_root,
        schema_name="canonical-catalog-selection-bundle-plan.schema.json",
        registry=registry,
    )
    _validate_market_payload(
        manifest,
        schema_root=market_schema_root,
        schema_name="canonical-catalog-selection-bundle-manifest.schema.json",
        registry=registry,
    )
    _validate_payload(
        bundle_evidence,
        evidence_schema_root / "phase2-catalog-selection-bundle.schema.json",
    )
    _require(plan.get("contract") == BUNDLE_PLAN_CONTRACT, "bundle plan contract differs")
    _require(
        manifest.get("contract") == BUNDLE_MANIFEST_CONTRACT,
        "bundle manifest contract differs",
    )
    _require(
        bundle_evidence.get("evidence_schema") == BUNDLE_EVIDENCE_CONTRACT,
        "bundle evidence contract differs",
    )
    _verify_content_hash(bundle_evidence, label="bundle evidence")
    _require(manifest.get("status") == "complete", "bundle manifest is incomplete")
    _require(
        manifest.get("plan_sha256") == canonical_sha256(plan),
        "bundle manifest/plan binding differs",
    )
    public_bindings = _mapping(bundle_evidence, "bindings")
    _require(
        _sha(public_bindings, "bundle_manifest_artifact_sha256") == sha256_file(manifest_path),
        "public bundle manifest binding differs",
    )
    _require(
        _sha(public_bindings, "bundle_plan_sha256") == _sha(manifest, "plan_sha256"),
        "public bundle plan binding differs",
    )
    public_catalog = _mapping(bundle_evidence, "catalog")
    plan_catalog = _mapping(plan, "catalog")
    manifest_catalog = _mapping(manifest, "catalog")
    _require(
        public_catalog == plan_catalog == manifest_catalog,
        "bundle catalog bindings differ",
    )

    plan_selections = _array(plan, "selections")
    manifest_selections = _array(manifest, "selections")
    selection_count = _integer(manifest, "selection_count", minimum=1, maximum=MAX_SELECTION_COUNT)
    public_inventory = _mapping(bundle_evidence, "inventory")
    _require(
        selection_count
        == _integer(plan, "selection_count", minimum=1, maximum=MAX_SELECTION_COUNT)
        == _integer(public_inventory, "selection_count", minimum=1, maximum=MAX_SELECTION_COUNT)
        == len(plan_selections)
        == len(manifest_selections),
        "bundle selection counts differ",
    )
    plan_by_sequence: dict[int, dict[str, Any]] = {}
    manifest_by_sequence: dict[int, dict[str, Any]] = {}
    for raw in plan_selections:
        _require(isinstance(raw, dict), "bundle plan selection must be an object")
        item = cast(dict[str, Any], raw)
        sequence = _integer(item, "sequence", maximum=MAX_SELECTION_COUNT - 1)
        _require(sequence not in plan_by_sequence, "bundle plan repeats a selection sequence")
        plan_by_sequence[sequence] = item
    for raw in manifest_selections:
        _require(isinstance(raw, dict), "bundle manifest selection must be an object")
        item = cast(dict[str, Any], raw)
        sequence = _integer(item, "sequence", maximum=MAX_SELECTION_COUNT - 1)
        _require(
            sequence not in manifest_by_sequence,
            "bundle manifest repeats a selection sequence",
        )
        manifest_by_sequence[sequence] = item
    expected_sequences = set(range(selection_count))
    _require(
        set(plan_by_sequence) == set(manifest_by_sequence) == expected_sequences,
        "bundle selection sequences are not contiguous",
    )

    inputs: list[_SelectionInput] = []
    dataset_ids: list[str] = []
    by_kind = {
        "trade": {
            "dataset_count": 0,
            "object_count": 0,
            "row_count": 0,
            "selection_count": 0,
            "size_bytes": 0,
        },
        "mark": {
            "dataset_count": 0,
            "object_count": 0,
            "row_count": 0,
            "selection_count": 0,
            "size_bytes": 0,
        },
    }
    with TemporaryDirectory(prefix="grid-current-universe-catalog-performance-") as temporary:
        request_root = Path(temporary)
        for sequence in range(selection_count):
            plan_item = plan_by_sequence[sequence]
            manifest_item = manifest_by_sequence[sequence]
            _require(
                plan_item.get("campaign_id") == manifest_item.get("campaign_id")
                and plan_item.get("kind") == manifest_item.get("kind")
                and plan_item.get("segment") == manifest_item.get("segment"),
                "bundle plan/manifest selection identity differs",
            )
            kind = plan_item.get("kind")
            _require(kind in {"trade", "mark"}, "bundle selection kind is invalid")
            request_payload = _mapping(plan_item, "request")
            request_path = request_root / f"{sequence:04d}.json"
            request_path.write_bytes(canonical_json_bytes(request_payload) + b"\n")
            request = load_catalog_selection_request(request_path)
            _require(
                request.request_sha256
                == _sha(plan_item, "request_sha256")
                == _sha(manifest_item, "request_sha256"),
                "bundle selection request binding differs",
            )
            selection_path = bundle_root / "selections" / f"{sequence:04d}.json"
            payload = _load_receipt_bound(selection_path)
            _validate_payload(
                payload,
                evidence_schema_root / "canonical-dataset-selection.schema.json",
            )
            _require(
                payload.get("evidence_schema") == SELECTION_CONTRACT,
                "selection evidence contract differs",
            )
            _verify_content_hash(payload, label=f"selection {sequence}")
            _require(payload.get("request") == request_payload, "selection request differs")
            _require(
                _sha(payload, "request_sha256") == request.request_sha256,
                "selection request content hash differs",
            )
            _require(
                _sha(manifest_item, "artifact_sha256") == sha256_file(selection_path)
                and _sha(manifest_item, "content_sha256") == _sha(payload, "content_sha256"),
                "bundle selection artifact binding differs",
            )
            selection = _mapping(payload, "selection")
            object_count = _integer(selection, "object_count", maximum=MAX_OBJECT_COUNT)
            row_count = _integer(selection, "selected_row_inventory", maximum=MAX_ROW_COUNT)
            size_bytes = _integer(selection, "selected_size_bytes", maximum=MAX_SIZE_BYTES)
            selected_manifests = _array(payload, "selected_dataset_manifests")
            selected_ids = []
            for raw in selected_manifests:
                _require(isinstance(raw, dict), "selected manifest must be an object")
                dataset_id = cast(dict[str, Any], raw).get("dataset_id")
                _require(isinstance(dataset_id, str), "selected dataset identity is invalid")
                selected_ids.append(dataset_id)
            _require(
                tuple(selected_ids) == request.dataset_ids,
                "selection dataset inventory differs from its request",
            )
            dataset_count = len(request.dataset_ids)
            _require(
                dataset_count
                == _integer(manifest_item, "dataset_count", minimum=1, maximum=MAX_DATASET_COUNT)
                and object_count
                == _integer(manifest_item, "object_count", minimum=1, maximum=MAX_OBJECT_COUNT)
                and row_count == _integer(manifest_item, "row_count", maximum=MAX_ROW_COUNT)
                and size_bytes
                == _integer(manifest_item, "size_bytes", minimum=1, maximum=MAX_SIZE_BYTES),
                "bundle selection inventory differs",
            )
            inputs.append(
                _SelectionInput(
                    expected_fingerprint_sha256=_selection_payload_fingerprint(payload),
                    expected_object_count=object_count,
                    expected_row_count=row_count,
                    expected_size_bytes=size_bytes,
                    kind=cast(str, kind),
                    request=request,
                    sequence=sequence,
                )
            )
            dataset_ids.extend(request.dataset_ids)
            aggregate = by_kind[cast(str, kind)]
            aggregate["dataset_count"] += dataset_count
            aggregate["object_count"] += object_count
            aggregate["row_count"] += row_count
            aggregate["selection_count"] += 1
            aggregate["size_bytes"] += size_bytes

    _require(len(dataset_ids) == len(set(dataset_ids)), "bundle repeats dataset identities")
    _require(
        len(dataset_ids)
        == _integer(manifest, "dataset_count", minimum=1, maximum=MAX_DATASET_COUNT)
        == _integer(public_inventory, "dataset_count", minimum=1, maximum=MAX_DATASET_COUNT),
        "bundle dataset counts differ",
    )
    for key, maximum in (
        ("object_count", MAX_OBJECT_COUNT),
        ("row_count", MAX_ROW_COUNT),
        ("size_bytes", MAX_SIZE_BYTES),
    ):
        _require(
            sum(item[key] for item in by_kind.values())
            == _integer(manifest, key, minimum=int(key != "row_count"), maximum=maximum)
            == _integer(public_inventory, key, minimum=int(key != "row_count"), maximum=maximum),
            f"bundle aggregate differs: {key}",
        )
    public_by_kind = {
        cast(str, item.get("kind")): item
        for raw in _array(public_inventory, "by_kind")
        if isinstance(raw, dict)
        for item in [cast(dict[str, Any], raw)]
    }
    _require(set(public_by_kind) == {"trade", "mark"}, "public kind inventory differs")
    for kind in ("trade", "mark"):
        expected = by_kind[kind]
        public = public_by_kind[kind]
        _require(
            all(_integer(public, key) == value for key, value in expected.items()),
            f"public kind inventory differs: {kind}",
        )
    selection_chain_sha256 = canonical_sha256(
        [
            {
                "artifact_sha256": _sha(cast(dict[str, Any], raw), "artifact_sha256"),
                "content_sha256": _sha(cast(dict[str, Any], raw), "content_sha256"),
                "request_sha256": _sha(cast(dict[str, Any], raw), "request_sha256"),
            }
            for raw in manifest_selections
            if isinstance(raw, dict)
        ]
    )
    _require(
        selection_chain_sha256 == _sha(public_bindings, "selection_chain_sha256"),
        "public selection chain differs",
    )
    return (
        tuple(inputs),
        tuple(dataset_ids),
        bundle_evidence,
        selection_chain_sha256,
    )


def _measure_pass(
    inputs: Sequence[_SelectionInput], store_root: Path, catalog_path: Path
) -> tuple[int, tuple[_MeasuredSelection, ...]]:
    started = perf_counter_ns()
    selections = select_catalog_ranges(
        tuple(item.request for item in inputs), store_root, catalog_path
    )
    elapsed_ns = max(1, perf_counter_ns() - started)
    _require(len(selections) == len(inputs), "batch selector returned an incomplete result")
    measured = []
    for item, selection in zip(inputs, selections, strict=True):
        fingerprint = _selection_runtime_fingerprint(selection)
        object_count = len(selection.objects)
        row_count = sum(value.row_count for value in selection.objects)
        size_bytes = sum(value.size_bytes for value in selection.objects)
        _require(
            selection.snapshot.revision == item.request.catalog_revision
            and selection.snapshot.content_sha256 == item.request.catalog_content_sha256,
            "runtime selection catalog binding differs",
        )
        _require(fingerprint == item.expected_fingerprint_sha256, "runtime selection differs")
        _require(
            object_count == item.expected_object_count
            and row_count == item.expected_row_count
            and size_bytes == item.expected_size_bytes,
            "runtime selection inventory differs",
        )
        measured.append(
            _MeasuredSelection(
                fingerprint_sha256=fingerprint,
                object_count=object_count,
                row_count=row_count,
                size_bytes=size_bytes,
            )
        )
    return elapsed_ns, tuple(measured)


def build_current_universe_catalog_performance_evidence(
    *,
    implementation_identity: str,
    generated_at_utc: str,
    repo_root: Path,
    bundle_root: Path,
    bundle_evidence_path: Path,
    store_root: Path,
    catalog_path: Path,
    output_path: Path,
) -> dict[str, object]:
    """Measure two full receipt-verifying bundle selections against the retained catalog."""

    _require(
        SOFTWARE_IDENTITY_RE.fullmatch(implementation_identity) is not None,
        "implementation identity must be git:<40 lowercase hex>",
    )
    _verify_generated_at(generated_at_utc)
    resolved_output, _resolved_receipt = preflight_evidence(output_path)
    _require(repo_root.is_dir() and not repo_root.is_symlink(), "repository root is unsafe")
    _require(bundle_root.is_dir() and not bundle_root.is_symlink(), "bundle root is unsafe")
    _require(store_root.is_dir() and not store_root.is_symlink(), "market store is unsafe")
    _require(
        catalog_path.is_file() and not catalog_path.is_symlink(),
        "catalog is unsafe or missing",
    )
    root = repo_root.resolve()
    bundle = bundle_root.resolve()
    store = store_root.resolve()
    catalog = catalog_path.resolve()
    _require(
        not resolved_output.is_relative_to(store) and not resolved_output.is_relative_to(bundle),
        "evidence output must stay outside retained store and private bundle",
    )

    inputs, dataset_ids, bundle_evidence, selection_chain_sha256 = _load_inputs(
        repo_root=root,
        bundle_root=bundle,
        bundle_evidence_path=bundle_evidence_path.resolve(),
    )
    catalog_binding = _mapping(bundle_evidence, "catalog")
    expected_revision = _integer(catalog_binding, "revision", minimum=1)
    expected_content_sha256 = _sha(catalog_binding, "content_sha256")
    catalog_sha256_before = sha256_file(catalog)
    metadata_before = _metadata_fingerprint(store, dataset_ids)
    first_elapsed_ns, first = _measure_pass(inputs, store, catalog)
    repeat_elapsed_ns, repeated = _measure_pass(inputs, store, catalog)
    final_snapshot = verify_catalog(store, catalog)
    catalog_sha256_after = sha256_file(catalog)
    metadata_after = _metadata_fingerprint(store, dataset_ids)
    _require(
        final_snapshot.revision == expected_revision
        and final_snapshot.content_sha256 == expected_content_sha256,
        "post-measurement catalog binding differs",
    )
    _require(first == repeated, "immediate repeat selection differs")
    _require(
        catalog_sha256_before == catalog_sha256_after and metadata_before == metadata_after,
        "catalog selection mutated retained state",
    )

    row_count = sum(item.expected_row_count for item in inputs)
    object_count = sum(item.expected_object_count for item in inputs)
    size_bytes = sum(item.expected_size_bytes for item in inputs)
    _require(row_count > 0, "current-universe performance bundle has no measured rows")
    selection_fingerprint_sha256 = canonical_sha256(
        [
            {
                "fingerprint_sha256": item.fingerprint_sha256,
                "object_count": item.object_count,
                "row_count": item.row_count,
                "size_bytes": item.size_bytes,
            }
            for item in first
        ]
    )
    inventory = _mapping(bundle_evidence, "inventory")
    payload: dict[str, object] = {
        "assurances": {
            "catalog_and_dataset_state_preserved": True,
            "network_request_performed": False,
            "private_or_live_capability_used": False,
            "production_bundle_selector_exercised": True,
            "retained_market_store_accessed_read_only": True,
            "selection_receipts_verified": True,
        },
        "bindings": {
            "bundle_evidence_artifact_sha256": sha256_file(bundle_evidence_path.resolve()),
            "bundle_evidence_content_sha256": _sha(bundle_evidence, "content_sha256"),
            "bundle_manifest_artifact_sha256": sha256_file(bundle / "manifest.json"),
            "catalog_content_sha256": expected_content_sha256,
            "catalog_revision": expected_revision,
            "implementation_identity": implementation_identity,
            "selection_chain_sha256": selection_chain_sha256,
        },
        "configuration": {
            "catalog_snapshot_verifications_per_pass": 1,
            "selection_count": len(inputs),
            "selection_pass_count": 2,
        },
        "content_sha256": "",
        "correctness": {
            "catalog_verified_after_measurement": True,
            "dataset_count": len(dataset_ids),
            "deterministic_repeat_equal": True,
            "object_count": object_count,
            "row_count": row_count,
            "selection_fingerprint_sha256": selection_fingerprint_sha256,
            "size_bytes": size_bytes,
            "source_count": _integer(inventory, "source_count", minimum=1, maximum=16),
            "state_fingerprint_equal_before_after": True,
        },
        "environment": {
            "cache_state": "uncontrolled-first-then-immediate-repeat",
            "duckdb_version": duckdb.__version__,
            "logical_cpu_count": os.cpu_count() or 1,
            "memory_total_bytes": int(psutil.virtual_memory().total),
            "platform_machine": platform.machine() or "unknown",
            "platform_system": platform.system() or "unknown",
            "pyarrow_version": pa.__version__,
            "python_version": platform.python_version(),
        },
        "evidence_schema": EVIDENCE_CONTRACT,
        "generated_at_utc": generated_at_utc,
        "limitations": [
            "The measurement covers catalog selection, not acquisition or publication wall time.",
            "The first pass has uncontrolled host cache state; the second is an immediate repeat.",
            "Measured timings do not define or qualify the owner-reviewed Gate 2 envelope.",
            "This evidence does not accept coverage, lifecycle, cadence, repair, or Phase 3.",
        ],
        "measurement": {
            "first_pass_rows_per_second": max(1, row_count * 1_000_000_000 // first_elapsed_ns),
            "first_pass_wall_elapsed_ns": first_elapsed_ns,
            "repeat_pass_rows_per_second": max(1, row_count * 1_000_000_000 // repeat_elapsed_ns),
            "repeat_pass_wall_elapsed_ns": repeat_elapsed_ns,
        },
        "status": "measured-current-universe-catalog-selection",
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_dataset_or_instrument_identities": False,
            "evidence_contains_market_values": False,
            "evidence_contains_request_time_bounds": False,
            "evidence_contains_runtime_paths": False,
            "runtime_catalog_or_market_artifacts_committed_to_git": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    _validate_payload(
        payload,
        root
        / "schemas"
        / "evidence"
        / "v1"
        / "phase2-current-universe-catalog-performance.schema.json",
    )
    publish_evidence(output_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation-identity", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--bundle-evidence", type=Path, required=True)
    parser.add_argument("--store-root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_current_universe_catalog_performance_evidence(
        implementation_identity=args.implementation_identity,
        generated_at_utc=datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        repo_root=args.repo_root,
        bundle_root=args.bundle_root,
        bundle_evidence_path=args.bundle_evidence,
        store_root=args.store_root,
        catalog_path=args.catalog,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "artifact": str(args.output),
                "first_pass_rows_per_second": cast(dict[str, Any], payload["measurement"])[
                    "first_pass_rows_per_second"
                ],
                "receipt": str(args.output.with_suffix(args.output.suffix + ".receipt.json")),
                "status": payload["status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
