from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import grid_data.catalog_selection_bundle as bundle_module
import grid_market_store.catalog as catalog_module
import pytest
from grid_contracts.canonical import canonical_sha256
from grid_contracts.market import DatasetType
from grid_data.catalog_selection_bundle import (
    BUNDLE_EVIDENCE_CONTRACT,
    BUNDLE_REQUEST_CONTRACT,
    BundleSourceSpec,
    CatalogSelectionBundleError,
    CatalogSelectionBundleRequest,
    PreparedBundleSelection,
    PreparedCatalogSelectionBundle,
    _assert_cross_source_disjoint,
    build_catalog_selection_bundle_evidence,
    execute_catalog_selection_bundle,
    load_catalog_selection_bundle_request,
    preflight_catalog_selection_bundle,
)
from grid_market_store.catalog import (
    CatalogSelection,
    CatalogSelectionRequest,
    CatalogSnapshot,
    SelectedCatalogObject,
)
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).parents[2]
CATALOG_HASH = "a" * 64
CONSUMER = f"git:{'b' * 40}"
BUILDER = f"git:{'c' * 40}"
JAN_START = 1_767_225_600_000
JAN_END = 1_769_903_940_000
FEB_START = 1_769_904_000_000
FEB_END = 1_772_323_140_000


def _request_payload(*, sources: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "bundle_id": "bundle-one",
        "catalog_content_sha256": CATALOG_HASH,
        "catalog_revision": 7,
        "consumer_software_identity": CONSUMER,
        "contract": BUNDLE_REQUEST_CONTRACT,
        "sources": sources
        or [
            {
                "campaign_id": "campaign-one",
                "end_time_ms": FEB_END,
                "start_time_ms": JAN_START,
            }
        ],
    }


def test_bundle_request_is_closed_sorted_and_full_month_bounded(tmp_path: Path) -> None:
    path = tmp_path / "request.json"
    payload = _request_payload()
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_catalog_selection_bundle_request(path)

    assert loaded.bundle_id == "bundle-one"
    assert loaded.sources == (BundleSourceSpec("campaign-one", JAN_START, FEB_END),)
    schema = json.loads(
        (
            ROOT / "schemas/market/v1/canonical-catalog-selection-bundle-request.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(payload)

    payload["sources"] = [
        {"campaign_id": "campaign-one", "end_time_ms": FEB_END, "start_time_ms": JAN_START + 60_000}
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CatalogSelectionBundleError, match="month boundary"):
        load_catalog_selection_bundle_request(path)


def test_preflight_derives_two_topology_segments_and_verifies_catalog_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request_payload()), encoding="utf-8")
    campaign_root = tmp_path / "campaign"
    publication_root = tmp_path / "publication"
    campaign_root.mkdir()
    publication_root.mkdir()
    registry_hash = "d" * 64
    jobs = []
    publication_jobs = []
    sequence = 0
    for kind in ("trade", "mark"):
        for month, instrument_specs in (
            ("2026-01", (("AAAUSDT", 8),)),
            ("2026-02", (("AAAUSDT", 8), ("BBBUSDT", 9))),
        ):
            for symbol, instrument_id in instrument_specs:
                bucket = instrument_id % 8
                job_id = f"campaign-one-{kind}-{month}-b{bucket:02d}-{symbol.lower()}"
                jobs.append(
                    {
                        "bucket": bucket,
                        "job_id": job_id,
                        "kind": kind,
                        "month": month,
                        "request": {"series": [{"symbol": symbol}]},
                    }
                )
                publication_jobs.append(
                    {
                        "dataset_id": f"{kind}-bundle-{sequence:04d}",
                        "job_id": job_id,
                        "kind": kind,
                    }
                )
                sequence += 1
    campaign_plan = {
        "campaign_id": "campaign-one",
        "instrument_evidence_sha256": registry_hash,
        "jobs": jobs,
    }
    (campaign_root / "plan.json").write_text(json.dumps(campaign_plan), encoding="utf-8")
    (campaign_root / "manifest.json").write_text("{}", encoding="utf-8")
    (publication_root / "plan.json").write_text(
        json.dumps({"jobs": publication_jobs}), encoding="utf-8"
    )
    (publication_root / "manifest.json").write_text("{}", encoding="utf-8")

    snapshots = {
        "AAAUSDT": SimpleNamespace(instrument_id=8),
        "BBBUSDT": SimpleNamespace(instrument_id=9),
    }
    monkeypatch.setattr(
        bundle_module,
        "load_verified_instrument_registry",
        lambda _path: SimpleNamespace(artifact_sha256=registry_hash, by_symbol=lambda: snapshots),
    )
    monkeypatch.setattr(
        bundle_module,
        "verify_completed_history_campaign_publication",
        lambda _publication, _campaign: SimpleNamespace(manifest_sha256="e" * 64),
    )
    observed: list[CatalogSelectionRequest] = []

    def select_many(
        requests: tuple[CatalogSelectionRequest, ...], _store: Path, _catalog: Path
    ) -> tuple[CatalogSelection, ...]:
        observed.extend(requests)
        return cast(tuple[CatalogSelection, ...], tuple(object() for _item in requests))

    monkeypatch.setattr(bundle_module, "select_catalog_ranges", select_many)

    prepared = preflight_catalog_selection_bundle(
        request_path,
        campaign_roots=(campaign_root,),
        publication_roots=(publication_root,),
        instrument_registry_path=tmp_path / "registry.json",
        store_root=tmp_path / "store",
        catalog_path=tmp_path / "catalog.duckdb",
        output_root=tmp_path / "bundle",
    )

    assert len(observed) == 4
    assert [item.start_time_ms for item in observed] == [JAN_START, FEB_START, JAN_START, FEB_START]
    assert [item.instrument_ids for item in observed] == [(8,), (8, 9), (8,), (8, 9)]
    assert prepared.dataset_count == 6
    assert prepared.instrument_count == 2
    assert len(prepared.selections) == 4


def test_cross_source_overlap_is_rejected_at_instrument_month_key_space() -> None:
    monthly = {
        "source-a": {
            "trade": {"2026-01": (("trade-a",), (8, 9))},
            "mark": {"2026-01": (("mark-a",), (8, 9))},
        },
        "source-b": {
            "trade": {"2026-01": (("trade-b",), (9, 10))},
            "mark": {"2026-01": (("mark-b",), (9, 10))},
        },
    }

    with pytest.raises(CatalogSelectionBundleError, match="overlap canonical"):
        _assert_cross_source_disjoint(monthly)


def _prepared_bundle(tmp_path: Path) -> PreparedCatalogSelectionBundle:
    request_payload = _request_payload(
        sources=[
            {
                "campaign_id": "campaign-one",
                "end_time_ms": JAN_END,
                "start_time_ms": JAN_START,
            }
        ]
    )
    request = CatalogSelectionBundleRequest(
        path=tmp_path / "request.json",
        payload=request_payload,
        bundle_id="bundle-one",
        catalog_revision=7,
        catalog_content_sha256=CATALOG_HASH,
        consumer_software_identity=CONSUMER,
        sources=(BundleSourceSpec("campaign-one", JAN_START, JAN_END),),
    )
    snapshot = CatalogSnapshot(7, CATALOG_HASH, ())
    prepared_selections = []
    for sequence, (kind, dataset_type) in enumerate(
        (("trade", DatasetType.TRADE_KLINE_1M), ("mark", DatasetType.MARK_KLINE_1M))
    ):
        dataset_id = f"{kind}-bundle-dataset"
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
                    object_key=f"datasets/{dataset_id}/part.parquet",
                    file_sha256="2" * 64,
                    size_bytes=100 + sequence,
                    row_count=10 + sequence,
                    min_time_ms=JAN_START,
                    max_time_ms=JAN_END,
                    min_instrument_id=8,
                    max_instrument_id=8,
                    partition_path=(
                        f"dataset={dataset_type.value}/schema=v1/year=2026/month=01/bucket=00"
                    ),
                ),
            ),
            required_partitions=(
                f"dataset={dataset_type.value}/schema=v1/year=2026/month=01/bucket=00",
            ),
            selected_dataset_manifest_sha256=((dataset_id, "1" * 64),),
        )
        prepared_selections.append(
            PreparedBundleSelection(
                sequence=sequence,
                campaign_id="campaign-one",
                kind=kind,
                segment=1,
                request=selection_request,
                selection=selection,
            )
        )
    source_binding = {
        "campaign_id": "campaign-one",
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
        "bundle_id": "bundle-one",
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
            for item in prepared_selections
        ],
        "source_bindings": [source_binding],
    }
    return PreparedCatalogSelectionBundle(
        request=request,
        output_root=tmp_path / "bundle",
        plan_payload=plan_payload,
        plan_sha256=canonical_sha256(plan_payload),
        selections=tuple(prepared_selections),
        source_bindings=(source_binding,),
        instrument_count=1,
        dataset_count=2,
    )


def test_bundle_execute_resume_and_public_projection_are_receipt_bound_and_redacted(
    tmp_path: Path,
) -> None:
    prepared = _prepared_bundle(tmp_path)
    generated = "2026-08-14T18:00:00Z"

    completed = execute_catalog_selection_bundle(prepared, generated_at_utc=generated)
    repeated = execute_catalog_selection_bundle(prepared, generated_at_utc=generated)
    payload = build_catalog_selection_bundle_evidence(
        prepared,
        repeated,
        generated_at_utc=generated,
        software_identity=BUILDER,
    )

    assert completed == repeated
    assert payload["evidence_schema"] == BUNDLE_EVIDENCE_CONTRACT
    assert payload["inventory"] == {
        "by_kind": [
            {
                "dataset_count": 1,
                "kind": "trade",
                "object_count": 1,
                "row_count": 10,
                "selection_count": 1,
                "size_bytes": 100,
            },
            {
                "dataset_count": 1,
                "kind": "mark",
                "object_count": 1,
                "row_count": 11,
                "selection_count": 1,
                "size_bytes": 101,
            },
        ],
        "dataset_count": 2,
        "empty_object_count": 0,
        "instrument_count": 1,
        "object_count": 2,
        "row_count": 21,
        "selection_count": 2,
        "size_bytes": 201,
        "source_count": 1,
    }
    schema = json.loads(
        (ROOT / "schemas/evidence/v1/phase2-catalog-selection-bundle.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    market_schema_paths = (
        ROOT / "schemas/market/v1/canonical-catalog-selection-bundle-request.schema.json",
        ROOT / "schemas/market/v1/canonical-catalog-selection-bundle-plan.schema.json",
        ROOT / "schemas/market/v1/canonical-catalog-selection-bundle-manifest.schema.json",
        ROOT / "schemas/market/v1/canonical-dataset-selection-request.schema.json",
    )
    market_schemas = [json.loads(path.read_text(encoding="utf-8")) for path in market_schema_paths]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in market_schemas
    )
    registry = registry.with_resource(
        "https://github.com/brullik/brullik-bybit-grid-bot-research/schemas/market/v1/"
        "canonical-dataset-selection-request.schema.json",
        Resource.from_contents(market_schemas[3]),
    )
    Draft202012Validator(
        market_schemas[1], registry=registry, format_checker=FormatChecker()
    ).validate(json.loads(completed.plan_path.read_text(encoding="utf-8")))
    Draft202012Validator(
        market_schemas[2], registry=registry, format_checker=FormatChecker()
    ).validate(json.loads(completed.manifest_path.read_text(encoding="utf-8")))
    rendered = json.dumps(payload).lower()
    for forbidden in (
        "campaign-one",
        "trade-bundle-dataset",
        '"instrument_id":',
        '"dataset_id":',
        '"start_time_ms":',
        '"end_time_ms":',
        '"object_key":',
    ):
        assert forbidden not in rendered


def test_batch_selector_verifies_catalog_once(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = CatalogSnapshot(7, CATALOG_HASH, ())
    requests = tuple(
        CatalogSelectionRequest(
            catalog_revision=7,
            catalog_content_sha256=CATALOG_HASH,
            dataset_ids=(f"trade-bundle-{index}",),
            dataset_type=DatasetType.TRADE_KLINE_1M,
            start_time_ms=JAN_START,
            end_time_ms=JAN_END,
            instrument_ids=(8,),
            consumer_software_identity=CONSUMER,
        )
        for index in range(3)
    )
    calls = 0

    def verify(_store: Path, _catalog: Path) -> CatalogSnapshot:
        nonlocal calls
        calls += 1
        return snapshot

    monkeypatch.setattr(catalog_module, "verify_catalog", verify)
    monkeypatch.setattr(
        catalog_module,
        "_select_catalog_range_from_snapshot",
        lambda request, _store, selected_snapshot: cast(
            CatalogSelection, (request, selected_snapshot)
        ),
    )

    selected = catalog_module.select_catalog_ranges(requests, Path("store"), Path("catalog"))

    assert calls == 1
    assert len(selected) == 3
