from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from grid_contracts.canonical import canonical_sha256
from grid_data.dataset_catalog import build_full_history_catalog_evidence
from grid_data.evidence import publish_evidence
from grid_market_store.catalog import (
    CatalogRegistrationRequest,
    CatalogSelectionRequest,
    catalog_registration_request_payload,
    selection_request_payload,
)
from jsonschema import Draft202012Validator, FormatChecker

from benchmarks.full_history_catalog_performance import (
    FullHistoryCatalogPerformanceError,
    build_full_history_catalog_performance_evidence,
)

ROOT = Path(__file__).parents[2]
IMPLEMENTATION_IDENTITY = f"git:{'d' * 40}"
CONSUMER_IDENTITY = f"git:{'e' * 40}"
REGISTRAR_IDENTITY = f"git:{'f' * 40}"
JANUARY_START_MS = 1_767_225_600_000
JANUARY_END_MS = 1_769_903_940_000
FEBRUARY_START_MS = JANUARY_END_MS + 60_000
FEBRUARY_END_MS = 1_772_323_140_000


def _with_content_hash(payload: dict[str, object]) -> dict[str, object]:
    result = dict(payload)
    result["content_sha256"] = canonical_sha256(payload)
    return result


def _fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, object], dict[str, object]]:
    store = tmp_path / "market-store"
    catalog = store / "catalog" / "canonical.duckdb"
    catalog.parent.mkdir(parents=True)
    catalog.write_bytes(b"read-only-catalog-fixture")
    catalog_content_sha256 = "c" * 64
    dataset_specs = (
        ("mark-early-b00", "mark_kline_1m", 1, 0, 101),
        ("mark-late-b00", "mark_kline_1m", 2, 10, 201),
        ("trade-early-b00", "trade_kline_1m", 1, 0, 111),
        ("trade-late-b00", "trade_kline_1m", 2, 10, 211),
    )
    dataset_ids = tuple(item[0] for item in dataset_specs)
    manifest_by_id = {
        dataset_id: f"{index + 1:064x}"
        for index, (dataset_id, _dataset_type, _month, _rows, _size) in enumerate(dataset_specs)
    }
    file_by_id = {
        dataset_id: f"{index + 101:064x}"
        for index, (dataset_id, _dataset_type, _month, _rows, _size) in enumerate(dataset_specs)
    }
    for dataset_id in dataset_ids:
        root = store / "datasets" / dataset_id
        root.mkdir(parents=True)
        (root / "completion-receipt.json").write_text(dataset_id, encoding="utf-8")

    registration_request = CatalogRegistrationRequest(dataset_ids, REGISTRAR_IDENTITY)
    registration_request_path, _ = publish_evidence(
        tmp_path / "registration-request.json",
        catalog_registration_request_payload(registration_request),
    )
    registration_payload = _with_content_hash(
        {
            "catalog": {
                "content_sha256": catalog_content_sha256,
                "revision": 5,
                "schema_version": 1,
            },
            "datasets": [
                {
                    "dataset_id": dataset_id,
                    "dataset_type": dataset_type,
                    "file_count": 1,
                    "manifest_sha256": manifest_by_id[dataset_id],
                    "partition": {"bucket": 0, "month": month, "year": 2026},
                    "row_count": rows,
                    "total_size_bytes": size,
                }
                for dataset_id, dataset_type, month, rows, size in dataset_specs
            ],
            "evidence_schema": "grid.canonical-dataset-catalog-registration/v1",
            "registration": {
                "requested_dataset_ids": list(dataset_ids),
                "software_identity": REGISTRAR_IDENTITY,
            },
        }
    )
    registration_path, _ = publish_evidence(tmp_path / "registration.json", registration_payload)

    request_paths: list[Path] = []
    selection_paths: list[Path] = []
    fake_selection_by_request: dict[str, SimpleNamespace] = {}
    for dataset_id, dataset_type, month, rows, size in dataset_specs:
        is_early = "early" in dataset_id
        start_ms = JANUARY_START_MS if is_early else FEBRUARY_START_MS
        end_ms = JANUARY_END_MS if is_early else FEBRUARY_END_MS
        request = CatalogSelectionRequest(
            catalog_revision=5,
            catalog_content_sha256=catalog_content_sha256,
            dataset_ids=(dataset_id,),
            dataset_type=dataset_type,
            start_time_ms=start_ms,
            end_time_ms=end_ms,
            instrument_ids=(8,),
            consumer_software_identity=CONSUMER_IDENTITY,
        )
        request_path = tmp_path / f"{dataset_id}-request.json"
        request_path.write_text(json.dumps(selection_request_payload(request)), encoding="utf-8")
        request_paths.append(request_path)
        partition = f"dataset={dataset_type}/schema=v1/year=2026/month={month:02d}/bucket=00"
        bounds: dict[str, int | None]
        if rows == 0:
            bounds = {
                "max_instrument_id": None,
                "max_time_ms": None,
                "min_instrument_id": None,
                "min_time_ms": None,
            }
        else:
            bounds = {
                "max_instrument_id": 8,
                "max_time_ms": start_ms + 9 * 60_000,
                "min_instrument_id": 8,
                "min_time_ms": start_ms,
            }
        object_record: dict[str, object] = {
            "dataset_id": dataset_id,
            "file_sha256": file_by_id[dataset_id],
            "manifest_sha256": manifest_by_id[dataset_id],
            **bounds,
            "object_key": (
                f"datasets/{dataset_id}/{partition}/part-{file_by_id[dataset_id]}.parquet"
            ),
            "row_count": rows,
            "size_bytes": size,
        }
        selection_payload = _with_content_hash(
            {
                "catalog": {
                    "content_sha256": catalog_content_sha256,
                    "revision": 5,
                    "schema_version": 1,
                },
                "evidence_schema": "grid.canonical-dataset-selection/v1",
                "generated_at_utc": "2026-08-14T13:00:00Z",
                "limitations": ["one", "two", "three"],
                "objects": [object_record],
                "request": selection_request_payload(request),
                "request_sha256": request.request_sha256,
                "required_partitions": [partition],
                "selected_dataset_manifests": [
                    {
                        "dataset_id": dataset_id,
                        "manifest_sha256": manifest_by_id[dataset_id],
                    }
                ],
                "selection": {
                    "object_count": 1,
                    "selected_row_inventory": rows,
                    "selected_size_bytes": size,
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
        )
        selection_path, _ = publish_evidence(
            tmp_path / f"{dataset_id}-selection.json", selection_payload
        )
        selection_paths.append(selection_path)
        runtime_object = SimpleNamespace(
            file_sha256=file_by_id[dataset_id],
            manifest_sha256=manifest_by_id[dataset_id],
            row_count=rows,
            size_bytes=size,
        )
        fake_selection_by_request[request.request_sha256] = SimpleNamespace(
            objects=(runtime_object,),
            request=request,
            required_partitions=(partition,),
            selected_dataset_manifest_sha256=((dataset_id, manifest_by_id[dataset_id]),),
            snapshot=SimpleNamespace(revision=5, content_sha256=catalog_content_sha256),
        )

    public_payload = build_full_history_catalog_evidence(
        registration_request_path,
        registration_path,
        tuple(selection_paths),
        generated_at_utc="2026-08-14T13:01:00Z",
        software_identity=CONSUMER_IDENTITY,
    )
    public_path, _ = publish_evidence(tmp_path / "full-history-catalog.json", public_payload)
    calls: list[str] = []

    def fake_select(request, _store, _catalog):  # type: ignore[no-untyped-def]
        calls.append(request.request_sha256)
        return fake_selection_by_request[request.request_sha256]

    monkeypatch.setattr(
        "benchmarks.full_history_catalog_performance.select_catalog_range", fake_select
    )
    monkeypatch.setattr(
        "benchmarks.full_history_catalog_performance.verify_catalog",
        lambda _store, _catalog: SimpleNamespace(revision=5, content_sha256=catalog_content_sha256),
    )
    arguments: dict[str, object] = {
        "catalog_path": catalog,
        "catalog_result_path": public_path,
        "generated_at_utc": "2026-08-14T13:02:00Z",
        "implementation_identity": IMPLEMENTATION_IDENTITY,
        "repo_root": ROOT,
        "request_paths": request_paths,
        "selection_paths": selection_paths,
        "store_root": store,
    }
    return arguments, {"calls": calls, "dataset_ids": list(dataset_ids)}


def test_full_history_catalog_performance_is_read_only_bound_and_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    arguments, observed = _fixture(tmp_path, monkeypatch)

    payload = build_full_history_catalog_performance_evidence(**arguments)  # type: ignore[arg-type]
    schema = json.loads(
        (
            ROOT / "schemas/evidence/v1/phase2-full-history-catalog-performance.schema.json"
        ).read_text(encoding="utf-8")
    )

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == canonical_sha256(hash_input)
    assert payload["status"] == "measured-full-history-catalog-selection"
    assert payload["correctness"] == {
        "catalog_verified_after_measurement": True,
        "deterministic_repeat_equal": True,
        "selected_dataset_count": 4,
        "selected_object_count": 4,
        "selected_row_count": 20,
        "selected_size_bytes": 624,
        "selection_fingerprint_sha256": payload["correctness"]["selection_fingerprint_sha256"],
        "state_fingerprint_equal_before_after": True,
        "topology_segment_count": 2,
    }
    assert len(observed["calls"]) == 8
    assert payload["measurement"]["first_pass_wall_elapsed_ns"] > 0
    assert payload["measurement"]["repeat_pass_wall_elapsed_ns"] > 0
    rendered = json.dumps(payload).lower()
    assert all(dataset_id not in rendered for dataset_id in observed["dataset_ids"])
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        '"symbol"',
        '"instrument_id"',
        '"dataset_id"',
        '"object_key"',
        '"runtime_path"',
        '"start_time_ms"',
        '"end_time_ms"',
        '"open"',
        '"volume"',
    ):
        assert forbidden not in rendered


def test_full_history_catalog_performance_rejects_publicly_unbound_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    arguments, _observed = _fixture(tmp_path, monkeypatch)
    selection_path = arguments["selection_paths"][0]  # type: ignore[index]
    payload = json.loads(selection_path.read_text(encoding="utf-8"))
    payload["generated_at_utc"] = "2026-08-14T13:03:00Z"
    payload.pop("content_sha256")
    payload["content_sha256"] = canonical_sha256(payload)
    publish_evidence(selection_path, payload, force=True)

    with pytest.raises(FullHistoryCatalogPerformanceError, match="public binding"):
        build_full_history_catalog_performance_evidence(**arguments)  # type: ignore[arg-type]


def test_full_history_catalog_performance_rejects_incomplete_topology(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    arguments, _observed = _fixture(tmp_path, monkeypatch)
    arguments["request_paths"] = arguments["request_paths"][:3]  # type: ignore[index]

    with pytest.raises(FullHistoryCatalogPerformanceError, match="exactly four"):
        build_full_history_catalog_performance_evidence(**arguments)  # type: ignore[arg-type]
