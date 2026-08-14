"""Measure retained full-history catalog selection without repeating acquisition or mutation."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter_ns
from typing import Any, Final, cast

import duckdb
import psutil  # type: ignore[import-untyped]
import pyarrow as pa  # type: ignore[import-untyped]
from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_data.evidence import preflight_evidence, publish_evidence, verify_evidence
from grid_market_store.catalog import (
    CatalogSelection,
    CatalogSelectionRequest,
    load_catalog_selection_request,
    select_catalog_range,
    selection_request_payload,
    verify_catalog,
)
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

EVIDENCE_CONTRACT: Final = "grid.phase2-full-history-catalog-performance/v1"
FULL_HISTORY_CATALOG_CONTRACT: Final = "grid.phase2-full-history-catalog/v1"
CATALOG_SELECTION_CONTRACT: Final = "grid.canonical-dataset-selection/v1"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
REQUEST_COUNT: Final = 4
CONCURRENCY: Final = 4
MAX_OBJECT_COUNT: Final = 5_000
MAX_ROW_COUNT: Final = 10_000_000_000
MAX_SIZE_BYTES: Final = 1_000_000_000_000


class FullHistoryCatalogPerformanceError(RuntimeError):
    """The retained full-history catalog benchmark failed closed."""


@dataclass(frozen=True, slots=True)
class _SelectionInput:
    expected_fingerprint_sha256: str
    expected_object_count: int
    expected_row_count: int
    expected_size_bytes: int
    kind: str
    request: CatalogSelectionRequest
    segment: int


@dataclass(frozen=True, slots=True)
class _MeasuredSelection:
    elapsed_ns: int
    fingerprint_sha256: str
    kind: str
    object_count: int
    row_count: int
    segment: int
    size_bytes: int


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FullHistoryCatalogPerformanceError(message)


def _mapping(parent: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise FullHistoryCatalogPerformanceError(f"evidence field must be an object: {key}")
    return cast(dict[str, Any], value)


def _array(parent: Mapping[str, Any], key: str) -> list[Any]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise FullHistoryCatalogPerformanceError(f"evidence field must be an array: {key}")
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
        raise FullHistoryCatalogPerformanceError(f"evidence integer is invalid: {key}")
    return value


def _sha(parent: Mapping[str, Any], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise FullHistoryCatalogPerformanceError(f"evidence SHA-256 is invalid: {key}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FullHistoryCatalogPerformanceError(f"invalid JSON evidence: {path.name}") from error
    if not isinstance(value, dict):
        raise FullHistoryCatalogPerformanceError(f"JSON evidence must be an object: {path.name}")
    return cast(dict[str, Any], value)


def _load_verified_evidence(path: Path, *, schema_path: Path, contract: str) -> dict[str, Any]:
    if not verify_evidence(path):
        raise FullHistoryCatalogPerformanceError(f"evidence receipt does not verify: {path.name}")
    payload = _load_json(path)
    contract_key = "contract" if "contract" in payload else "evidence_schema"
    _require(payload.get(contract_key) == contract, f"evidence contract differs: {path.name}")
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256", None)
    _require(
        embedded_hash == canonical_sha256(hash_input),
        f"evidence content hash does not verify: {path.name}",
    )
    try:
        Draft202012Validator(_load_json(schema_path), format_checker=FormatChecker()).validate(
            payload
        )
    except Exception as error:
        raise FullHistoryCatalogPerformanceError(
            f"evidence schema does not verify: {path.name}"
        ) from error
    return payload


def _verify_generated_at(generated_at_utc: str) -> None:
    _require(generated_at_utc.endswith("Z"), "generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(generated_at_utc.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise FullHistoryCatalogPerformanceError("generated_at_utc is invalid") from error
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
    entries: list[dict[str, object]] = []
    for dataset_id in sorted(set(dataset_ids)):
        _require(
            bool(dataset_id)
            and dataset_id not in {".", ".."}
            and "/" not in dataset_id
            and "\\" not in dataset_id,
            "selection contains an unsafe dataset identity",
        )
        dataset_root = (root / "datasets" / dataset_id).resolve()
        try:
            dataset_root.relative_to(root / "datasets")
        except ValueError as error:
            raise FullHistoryCatalogPerformanceError(
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
                raise FullHistoryCatalogPerformanceError(
                    "selected dataset contains an unsafe path type"
                )
    return canonical_sha256(entries)


def _load_selection_inputs(
    *,
    request_paths: Sequence[Path],
    selection_paths: Sequence[Path],
    catalog_result: Mapping[str, Any],
    schema_root: Path,
) -> tuple[tuple[_SelectionInput, ...], tuple[str, ...]]:
    _require(
        len(request_paths) == REQUEST_COUNT and len(selection_paths) == REQUEST_COUNT,
        "full-history benchmark requires exactly four requests and four selections",
    )
    _require(
        len({path.resolve() for path in request_paths}) == REQUEST_COUNT
        and len({path.resolve() for path in selection_paths}) == REQUEST_COUNT,
        "full-history benchmark input paths must be unique",
    )
    public_bindings = {
        _sha(cast(dict[str, Any], value), "request_sha256"): cast(dict[str, Any], value)
        for value in _array(_mapping(catalog_result, "bindings"), "selections")
        if isinstance(value, dict)
    }
    _require(len(public_bindings) == REQUEST_COUNT, "public selection bindings are incomplete")

    inputs: list[_SelectionInput] = []
    dataset_ids: list[str] = []
    for request_path, selection_path in zip(request_paths, selection_paths, strict=True):
        request = load_catalog_selection_request(request_path)
        payload = _load_verified_evidence(
            selection_path,
            schema_path=schema_root / "canonical-dataset-selection.schema.json",
            contract=CATALOG_SELECTION_CONTRACT,
        )
        expected_request_payload = selection_request_payload(request)
        _require(payload.get("request") == expected_request_payload, "request/evidence differs")
        _require(
            payload.get("request_sha256") == request.request_sha256,
            "request/evidence content hash differs",
        )
        binding = public_bindings.get(request.request_sha256)
        if binding is None:
            raise FullHistoryCatalogPerformanceError(
                "selection request is absent from public catalog result"
            )
        _require(
            _sha(binding, "artifact_sha256") == sha256_file(selection_path.resolve())
            and _sha(binding, "content_sha256") == _sha(payload, "content_sha256"),
            "private selection differs from its public binding",
        )
        kind = binding.get("kind")
        segment = binding.get("segment")
        if not isinstance(kind, str) or kind not in {"trade", "mark"}:
            raise FullHistoryCatalogPerformanceError("public selection kind is invalid")
        if not isinstance(segment, int) or isinstance(segment, bool) or segment not in {1, 2}:
            raise FullHistoryCatalogPerformanceError("public selection segment is invalid")
        selection = _mapping(payload, "selection")
        inputs.append(
            _SelectionInput(
                expected_fingerprint_sha256=_selection_payload_fingerprint(payload),
                expected_object_count=_integer(selection, "object_count", maximum=MAX_OBJECT_COUNT),
                expected_row_count=_integer(
                    selection, "selected_row_inventory", maximum=MAX_ROW_COUNT
                ),
                expected_size_bytes=_integer(
                    selection, "selected_size_bytes", maximum=MAX_SIZE_BYTES
                ),
                kind=kind,
                request=request,
                segment=segment,
            )
        )
        for raw in _array(payload, "selected_dataset_manifests"):
            _require(isinstance(raw, dict), "selected manifest must be an object")
            dataset_id = cast(dict[str, Any], raw).get("dataset_id")
            if not isinstance(dataset_id, str):
                raise FullHistoryCatalogPerformanceError("selected dataset identity is invalid")
            dataset_ids.append(dataset_id)

    inputs.sort(key=lambda item: (item.kind, item.segment))
    _require(
        [(item.kind, item.segment) for item in inputs]
        == [("mark", 1), ("mark", 2), ("trade", 1), ("trade", 2)],
        "full-history benchmark topology is incomplete",
    )
    _require(len(set(dataset_ids)) == len(dataset_ids), "selection dataset inventories overlap")
    return tuple(inputs), tuple(dataset_ids)


def _measure_one(item: _SelectionInput, store_root: Path, catalog_path: Path) -> _MeasuredSelection:
    started = perf_counter_ns()
    selection = select_catalog_range(item.request, store_root, catalog_path)
    elapsed_ns = max(1, perf_counter_ns() - started)
    fingerprint = _selection_runtime_fingerprint(selection)
    object_count = len(selection.objects)
    row_count = sum(value.row_count for value in selection.objects)
    size_bytes = sum(value.size_bytes for value in selection.objects)
    _require(
        selection.snapshot.revision == item.request.catalog_revision
        and selection.snapshot.content_sha256 == item.request.catalog_content_sha256,
        "runtime selection catalog binding differs",
    )
    _require(fingerprint == item.expected_fingerprint_sha256, "runtime selection result differs")
    _require(
        object_count == item.expected_object_count
        and row_count == item.expected_row_count
        and size_bytes == item.expected_size_bytes,
        "runtime selection inventory differs",
    )
    return _MeasuredSelection(
        elapsed_ns=elapsed_ns,
        fingerprint_sha256=fingerprint,
        kind=item.kind,
        object_count=object_count,
        row_count=row_count,
        segment=item.segment,
        size_bytes=size_bytes,
    )


def _measure_pass(
    inputs: Sequence[_SelectionInput], store_root: Path, catalog_path: Path
) -> tuple[int, tuple[_MeasuredSelection, ...]]:
    started = perf_counter_ns()
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        results = tuple(
            executor.map(
                lambda item: _measure_one(item, store_root, catalog_path),
                inputs,
            )
        )
    return max(1, perf_counter_ns() - started), results


def build_full_history_catalog_performance_evidence(
    *,
    implementation_identity: str,
    generated_at_utc: str,
    repo_root: Path,
    catalog_result_path: Path,
    request_paths: Sequence[Path],
    selection_paths: Sequence[Path],
    store_root: Path,
    catalog_path: Path,
) -> dict[str, Any]:
    """Measure two complete read-only passes over the retained four-selection topology."""

    _require(
        SOFTWARE_IDENTITY_RE.fullmatch(implementation_identity) is not None,
        "implementation identity must be git:<40-character-lowercase-commit-sha>",
    )
    _verify_generated_at(generated_at_utc)
    repo_root = repo_root.resolve()
    store_root = store_root.resolve()
    catalog_path = catalog_path.resolve()
    _require(store_root.is_dir(), "market store is missing")
    _require(catalog_path.is_file(), "catalog file is missing")
    try:
        catalog_path.relative_to(store_root)
    except ValueError as error:
        raise FullHistoryCatalogPerformanceError(
            "catalog must be inside the market store"
        ) from error

    schema_root = repo_root / "schemas" / "evidence" / "v1"
    catalog_result = _load_verified_evidence(
        catalog_result_path,
        schema_path=schema_root / "phase2-full-history-catalog.schema.json",
        contract=FULL_HISTORY_CATALOG_CONTRACT,
    )
    inventory = _mapping(catalog_result, "inventory")
    dataset_count = _integer(inventory, "dataset_count", maximum=MAX_OBJECT_COUNT)
    object_count = _integer(inventory, "object_count", maximum=MAX_OBJECT_COUNT)
    row_count = _integer(inventory, "row_count", maximum=MAX_ROW_COUNT)
    size_bytes = _integer(inventory, "size_bytes", maximum=MAX_SIZE_BYTES)
    _require(dataset_count == object_count, "full-history catalog dataset/object count differs")
    _require(
        _mapping(catalog_result, "process").get("selection_union_matches_registration") is True,
        "public full-history selection union is not verified",
    )
    inputs, dataset_ids = _load_selection_inputs(
        request_paths=request_paths,
        selection_paths=selection_paths,
        catalog_result=catalog_result,
        schema_root=schema_root,
    )
    _require(len(dataset_ids) == dataset_count, "private/public dataset inventory count differs")
    _require(
        sum(item.expected_object_count for item in inputs) == object_count
        and sum(item.expected_row_count for item in inputs) == row_count
        and sum(item.expected_size_bytes for item in inputs) == size_bytes,
        "private/public selection inventory differs",
    )

    before_catalog_sha256 = sha256_file(catalog_path)
    before_metadata_sha256 = _metadata_fingerprint(store_root, dataset_ids)
    first_wall_ns, first = _measure_pass(inputs, store_root, catalog_path)
    repeat_wall_ns, repeated = _measure_pass(inputs, store_root, catalog_path)
    after_catalog_sha256 = sha256_file(catalog_path)
    after_metadata_sha256 = _metadata_fingerprint(store_root, dataset_ids)
    post_snapshot = verify_catalog(store_root, catalog_path)
    public_catalog = _mapping(catalog_result, "catalog")

    _require(
        [item.fingerprint_sha256 for item in first]
        == [item.fingerprint_sha256 for item in repeated],
        "immediate repeat selection differs",
    )
    _require(
        before_catalog_sha256 == after_catalog_sha256
        and before_metadata_sha256 == after_metadata_sha256,
        "catalog selection mutated retained state",
    )
    _require(
        post_snapshot.revision == _integer(public_catalog, "revision", minimum=1)
        and post_snapshot.content_sha256 == _sha(public_catalog, "content_sha256"),
        "post-measurement catalog verification differs from public evidence",
    )
    selection_fingerprint = canonical_sha256(
        [
            {
                "fingerprint_sha256": item.fingerprint_sha256,
                "kind": item.kind,
                "segment": item.segment,
            }
            for item in first
        ]
    )
    source_bindings = _mapping(catalog_result, "bindings")
    selection_chain_sha256 = canonical_sha256(_array(source_bindings, "selections"))
    first_worker_sum_ns = sum(item.elapsed_ns for item in first)
    repeat_worker_sum_ns = sum(item.elapsed_ns for item in repeated)

    payload: dict[str, Any] = {
        "assurances": {
            "catalog_and_dataset_state_preserved": True,
            "network_request_performed": False,
            "private_or_live_capability_used": False,
            "production_catalog_selector_exercised": True,
            "retained_market_store_accessed_read_only": True,
            "selection_receipts_verified": True,
        },
        "bindings": {
            "catalog_content_sha256": post_snapshot.content_sha256,
            "catalog_result_artifact_sha256": sha256_file(catalog_result_path.resolve()),
            "catalog_result_content_sha256": _sha(catalog_result, "content_sha256"),
            "catalog_revision": post_snapshot.revision,
            "implementation_identity": implementation_identity,
            "selection_chain_sha256": selection_chain_sha256,
        },
        "configuration": {
            "concurrency": CONCURRENCY,
            "request_count": REQUEST_COUNT,
            "selection_pass_count": 2,
        },
        "correctness": {
            "catalog_verified_after_measurement": True,
            "deterministic_repeat_equal": True,
            "selected_dataset_count": dataset_count,
            "selected_object_count": object_count,
            "selected_row_count": row_count,
            "selected_size_bytes": size_bytes,
            "selection_fingerprint_sha256": selection_fingerprint,
            "state_fingerprint_equal_before_after": True,
            "topology_segment_count": len(_array(catalog_result, "topology")),
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
            "The measurement covers the retained five-instrument candle campaign, not a future "
            "700-instrument corpus.",
            "The first pass has uncontrolled host cache state; the second is an immediate repeat.",
            "This component measurement does not define or qualify the owner-reviewed full-history "
            "end-to-end performance envelope.",
            "This evidence does not accept coverage or lifecycle reasons, close Gate 2, authorize "
            "Phase 3, or enable live execution.",
        ],
        "measurement": {
            "first_pass_rows_per_second": max(1, row_count * 1_000_000_000 // first_wall_ns),
            "first_pass_wall_elapsed_ns": first_wall_ns,
            "first_pass_worker_elapsed_sum_ns": first_worker_sum_ns,
            "repeat_pass_rows_per_second": max(1, row_count * 1_000_000_000 // repeat_wall_ns),
            "repeat_pass_wall_elapsed_ns": repeat_wall_ns,
            "repeat_pass_worker_elapsed_sum_ns": repeat_worker_sum_ns,
        },
        "status": "measured-full-history-catalog-selection",
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_dataset_or_instrument_identities": False,
            "evidence_contains_market_values": False,
            "evidence_contains_request_time_bounds": False,
            "evidence_contains_runtime_paths": False,
            "runtime_catalog_or_market_artifacts_committed_to_git": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    try:
        Draft202012Validator(
            _load_json(
                repo_root
                / "schemas"
                / "evidence"
                / "v1"
                / "phase2-full-history-catalog-performance.schema.json"
            ),
            format_checker=FormatChecker(),
        ).validate(payload)
    except Exception as error:
        raise FullHistoryCatalogPerformanceError(
            "full-history catalog performance evidence does not match its schema"
        ) from error
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation-identity", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--catalog-result", type=Path, required=True)
    parser.add_argument("--selection-request", action="append", type=Path, required=True)
    parser.add_argument("--selection-evidence", action="append", type=Path, required=True)
    parser.add_argument("--store-root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output, _receipt = preflight_evidence(args.output)
    payload = build_full_history_catalog_performance_evidence(
        implementation_identity=args.implementation_identity,
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        repo_root=args.repo_root,
        catalog_result_path=args.catalog_result,
        request_paths=args.selection_request,
        selection_paths=args.selection_evidence,
        store_root=args.store_root,
        catalog_path=args.catalog,
    )
    artifact, receipt = publish_evidence(output, payload)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "first_pass_wall_elapsed_ns": payload["measurement"]["first_pass_wall_elapsed_ns"],
                "receipt": str(receipt),
                "status": payload["status"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
