from __future__ import annotations

import json
from pathlib import Path

import grid_market_store.catalog as catalog_module
import pytest
from grid_contracts.canonical import canonical_sha256
from grid_contracts.market import DatasetType
from grid_data.catalog_selection_bundle import (
    BundleSourceSpec,
    CatalogSelectionBundleRequest,
    PreparedBundleSelection,
    PreparedCatalogSelectionBundle,
    build_catalog_selection_bundle_evidence,
    execute_catalog_selection_bundle,
)
from grid_data.evidence import publish_evidence, verify_evidence
from grid_market_store.catalog import (
    CatalogSelection,
    CatalogSelectionRequest,
    CatalogSnapshot,
    SelectedCatalogObject,
)
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

import benchmarks.current_universe_catalog_performance as performance_module
from benchmarks.current_universe_catalog_performance import (
    CurrentUniverseCatalogPerformanceError,
    build_current_universe_catalog_performance_evidence,
)

ROOT = Path(__file__).parents[2]
CATALOG_HASH = "a" * 64
CONSUMER = f"git:{'b' * 40}"
BUILDER = f"git:{'c' * 40}"
IMPLEMENTATION = f"git:{'d' * 40}"
JAN_START = 1_767_225_600_000
JAN_END = 1_769_903_940_000
GENERATED = "2026-08-14T20:00:00Z"


def _bundle_fixture(
    tmp_path: Path,
) -> tuple[PreparedCatalogSelectionBundle, CatalogSnapshot, Path]:
    request_payload = {
        "bundle_id": "bundle-performance",
        "catalog_content_sha256": CATALOG_HASH,
        "catalog_revision": 7,
        "consumer_software_identity": CONSUMER,
        "contract": "grid.canonical-catalog-selection-bundle-request/v1",
        "sources": [
            {
                "campaign_id": "campaign-private",
                "end_time_ms": JAN_END,
                "start_time_ms": JAN_START,
            }
        ],
    }
    request = CatalogSelectionBundleRequest(
        path=tmp_path / "request.json",
        payload=request_payload,
        bundle_id="bundle-performance",
        catalog_revision=7,
        catalog_content_sha256=CATALOG_HASH,
        consumer_software_identity=CONSUMER,
        sources=(BundleSourceSpec("campaign-private", JAN_START, JAN_END),),
    )
    snapshot = CatalogSnapshot(7, CATALOG_HASH, ())
    selections = []
    for sequence, (kind, dataset_type) in enumerate(
        (("trade", DatasetType.TRADE_KLINE_1M), ("mark", DatasetType.MARK_KLINE_1M))
    ):
        dataset_id = f"private-{kind}-dataset"
        partition_path = f"dataset={dataset_type.value}/schema=v1/year=2026/month=01/bucket=00"
        selection_request = CatalogSelectionRequest(
            catalog_revision=7,
            catalog_content_sha256=CATALOG_HASH,
            dataset_ids=(dataset_id,),
            dataset_type=dataset_type,
            start_time_ms=JAN_START,
            end_time_ms=JAN_END,
            instrument_ids=(8,),
            consumer_software_identity=CONSUMER,
        )
        selection = CatalogSelection(
            request=selection_request,
            snapshot=snapshot,
            objects=(
                SelectedCatalogObject(
                    dataset_id=dataset_id,
                    manifest_sha256="1" * 64,
                    object_key=f"datasets/{dataset_id}/{partition_path}/part.parquet",
                    file_sha256="2" * 64,
                    size_bytes=100 + sequence,
                    row_count=10 + sequence,
                    min_time_ms=JAN_START,
                    max_time_ms=JAN_END,
                    min_instrument_id=8,
                    max_instrument_id=8,
                    partition_path=partition_path,
                ),
            ),
            required_partitions=(partition_path,),
            selected_dataset_manifest_sha256=((dataset_id, "1" * 64),),
        )
        selections.append(
            PreparedBundleSelection(
                sequence=sequence,
                campaign_id="campaign-private",
                kind=kind,
                segment=1,
                request=selection_request,
                selection=selection,
            )
        )
    source_binding = {
        "campaign_id": "campaign-private",
        "campaign_manifest_sha256": "3" * 64,
        "campaign_plan_sha256": "4" * 64,
        "end_time_ms": JAN_END,
        "instrument_count": 1,
        "publication_manifest_sha256": "5" * 64,
        "publication_plan_sha256": "6" * 64,
        "selection_count": 2,
        "start_time_ms": JAN_START,
    }
    plan_payload = {
        "bundle_id": "bundle-performance",
        "bundle_request": request_payload,
        "bundle_request_sha256": canonical_sha256(request_payload),
        "catalog": {"content_sha256": CATALOG_HASH, "revision": 7},
        "contract": "grid.canonical-catalog-selection-bundle-plan/v1",
        "dataset_count": 2,
        "instrument_count": 1,
        "instrument_registry_sha256": "7" * 64,
        "selection_count": 2,
        "selection_policy": {
            "catalog_verified_once": True,
            "cross_source_key_space": "disjoint-instrument-minute-by-month-v1",
            "month_topology": "contiguous-equal-instrument-inventory-v1",
            "selector": "grid.canonical-dataset-selection-request/v1",
        },
        "selections": [
            {
                "campaign_id": item.campaign_id,
                "kind": item.kind,
                "request": catalog_module.selection_request_payload(item.request),
                "request_sha256": item.request.request_sha256,
                "segment": item.segment,
                "sequence": item.sequence,
            }
            for item in selections
        ],
        "source_bindings": [source_binding],
    }
    prepared = PreparedCatalogSelectionBundle(
        request=request,
        output_root=tmp_path / "bundle",
        plan_payload=plan_payload,
        plan_sha256=canonical_sha256(plan_payload),
        selections=tuple(selections),
        source_bindings=(source_binding,),
        instrument_count=1,
        dataset_count=2,
    )
    completed = execute_catalog_selection_bundle(prepared, generated_at_utc=GENERATED)
    public = build_catalog_selection_bundle_evidence(
        prepared,
        completed,
        generated_at_utc=GENERATED,
        software_identity=BUILDER,
    )
    public_path, _receipt = publish_evidence(tmp_path / "bundle-evidence.json", public)
    return prepared, snapshot, public_path


def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, object], PreparedCatalogSelectionBundle, Path]:
    prepared, snapshot, public_path = _bundle_fixture(tmp_path)
    store = tmp_path / "store"
    store.mkdir()
    catalog = store / "catalog.duckdb"
    catalog.write_bytes(b"immutable-catalog")
    calls = 0

    def select_many(
        _requests: tuple[CatalogSelectionRequest, ...], _store: Path, _catalog: Path
    ) -> tuple[CatalogSelection, ...]:
        nonlocal calls
        calls += 1
        return tuple(item.selection for item in prepared.selections)

    monkeypatch.setattr(performance_module, "select_catalog_ranges", select_many)
    monkeypatch.setattr(performance_module, "verify_catalog", lambda _store, _catalog: snapshot)
    monkeypatch.setattr(
        performance_module,
        "_metadata_fingerprint",
        lambda _store, _dataset_ids: "8" * 64,
    )
    output = tmp_path / "performance.json"
    payload = build_current_universe_catalog_performance_evidence(
        implementation_identity=IMPLEMENTATION,
        generated_at_utc=GENERATED,
        repo_root=ROOT,
        bundle_root=prepared.output_root,
        bundle_evidence_path=public_path,
        store_root=store,
        catalog_path=catalog,
        output_path=output,
    )
    assert calls == 2
    return payload, prepared, output


def test_current_universe_catalog_performance_is_receipt_bound_and_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload, _prepared, output = _run(tmp_path, monkeypatch)

    assert payload["status"] == "measured-current-universe-catalog-selection"
    assert payload["configuration"] == {
        "catalog_snapshot_verifications_per_pass": 1,
        "selection_count": 2,
        "selection_pass_count": 2,
    }
    assert payload["correctness"]["row_count"] == 21  # type: ignore[index]
    assert verify_evidence(output)
    schema = json.loads(
        (
            ROOT / "schemas/evidence/v1/phase2-current-universe-catalog-performance.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    rendered = json.dumps(payload).lower()
    for forbidden in (
        "campaign-private",
        "private-trade-dataset",
        "private-mark-dataset",
        '"instrument_id":',
        '"dataset_id":',
        '"start_time_ms":',
        '"end_time_ms":',
        '"object_key":',
    ):
        assert forbidden not in rendered


def test_current_universe_catalog_performance_rejects_bundle_receipt_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared, snapshot, public_path = _bundle_fixture(tmp_path)
    plan_path = prepared.output_root / "plan.json"
    plan_path.write_text("{}", encoding="utf-8")
    store = tmp_path / "store"
    store.mkdir()
    catalog = store / "catalog.duckdb"
    catalog.write_bytes(b"immutable-catalog")
    monkeypatch.setattr(performance_module, "verify_catalog", lambda _store, _catalog: snapshot)

    with pytest.raises(CurrentUniverseCatalogPerformanceError, match="receipt does not verify"):
        build_current_universe_catalog_performance_evidence(
            implementation_identity=IMPLEMENTATION,
            generated_at_utc=GENERATED,
            repo_root=ROOT,
            bundle_root=prepared.output_root,
            bundle_evidence_path=public_path,
            store_root=store,
            catalog_path=catalog,
            output_path=tmp_path / "performance.json",
        )


def test_current_universe_catalog_performance_rejects_retained_state_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared, snapshot, public_path = _bundle_fixture(tmp_path)
    store = tmp_path / "store"
    store.mkdir()
    catalog = store / "catalog.duckdb"
    catalog.write_bytes(b"immutable-catalog")
    monkeypatch.setattr(
        performance_module,
        "select_catalog_ranges",
        lambda _requests, _store, _catalog: tuple(item.selection for item in prepared.selections),
    )
    monkeypatch.setattr(performance_module, "verify_catalog", lambda _store, _catalog: snapshot)
    fingerprints = iter(("8" * 64, "9" * 64))
    monkeypatch.setattr(
        performance_module,
        "_metadata_fingerprint",
        lambda _store, _dataset_ids: next(fingerprints),
    )

    with pytest.raises(CurrentUniverseCatalogPerformanceError, match="mutated retained state"):
        build_current_universe_catalog_performance_evidence(
            implementation_identity=IMPLEMENTATION,
            generated_at_utc=GENERATED,
            repo_root=ROOT,
            bundle_root=prepared.output_root,
            bundle_evidence_path=public_path,
            store_root=store,
            catalog_path=catalog,
            output_path=tmp_path / "performance.json",
        )


def test_current_universe_catalog_performance_rejects_output_inside_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared, snapshot, public_path = _bundle_fixture(tmp_path)
    store = tmp_path / "store"
    store.mkdir()
    catalog = store / "catalog.duckdb"
    catalog.write_bytes(b"immutable-catalog")
    monkeypatch.setattr(performance_module, "verify_catalog", lambda _store, _catalog: snapshot)

    with pytest.raises(CurrentUniverseCatalogPerformanceError, match="outside retained store"):
        build_current_universe_catalog_performance_evidence(
            implementation_identity=IMPLEMENTATION,
            generated_at_utc=GENERATED,
            repo_root=ROOT,
            bundle_root=prepared.output_root,
            bundle_evidence_path=public_path,
            store_root=store,
            catalog_path=catalog,
            output_path=store / "performance.json",
        )
