from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from grid_contracts.market import Candle1m, DatasetType, FundingEvent
from grid_data.dataset_catalog import (
    build_catalog_registration_evidence,
    build_catalog_selection_evidence,
    verify_catalog_registration_evidence,
    verify_catalog_selection_evidence,
)
from grid_data.evidence import publish_evidence
from grid_market_store import (
    MIN_OPERATING_RESERVE_BYTES,
    CandleDatasetSpec,
    CapacityBudget,
    FundingDatasetSpec,
    HostSnapshot,
    build_canonical_candle_batch,
    build_canonical_funding_batch,
    preflight_candle_dataset,
    preflight_funding_dataset,
    publish_candle_dataset,
    publish_funding_dataset,
)
from grid_market_store.catalog import (
    CATALOG_SELECTION_REQUEST_CONTRACT,
    CatalogError,
    CatalogSelectionRequest,
    load_catalog_selection_request,
    preflight_catalog_registration,
    register_catalog_datasets,
    select_catalog_range,
    selection_request_payload,
    verify_catalog,
)
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[2]
JANUARY_1_2026_MS = 1_767_225_600_000
REGISTRAR = f"git:{'a' * 40}"
CONSUMER = f"git:{'b' * 40}"


def snapshot(root: Path, *, observed_at_ms: int) -> HostSnapshot:
    return HostSnapshot(
        observed_at_ms=observed_at_ms,
        memory_total_bytes=16 * 1024**3,
        memory_available_bytes=8 * 1024**3,
        storage_kind="nvme",
        storage_device_id="fixture-nvme",
        volume_root=root.resolve(),
        volume_free_bytes=200 * 1024**3,
    )


def candle(open_time_ms: int, *, instrument_id: int = 9) -> Candle1m:
    return Candle1m(
        category="linear",
        instrument_id=instrument_id,
        open_time_ms=open_time_ms,
        open=Decimal("100"),
        high=Decimal("102"),
        low=Decimal("99"),
        close=Decimal("101"),
        volume=Decimal("10"),
        turnover=Decimal("1000"),
        source_id="bybit-v5-kline",
        ingestion_id=f"fixture-{instrument_id}-{open_time_ms}",
    )


def publish_dataset(
    tmp_path: Path,
    store: Path,
    dataset_id: str,
    *,
    minutes: tuple[int, ...],
    parent_dataset_ids: tuple[str, ...] = (),
    instrument_id: int = 9,
    instrument_ids: tuple[int, ...] | None = None,
) -> None:
    digest = f"{len(dataset_id):064x}"
    selected_instrument_ids = (instrument_id,) if instrument_ids is None else instrument_ids
    batch = build_canonical_candle_batch(
        tuple(
            candle(JANUARY_1_2026_MS + minute * 60_000, instrument_id=selected_instrument_id)
            for selected_instrument_id in selected_instrument_ids
            for minute in minutes
        ),
        DatasetType.TRADE_KLINE_1M,
    )
    plan = preflight_candle_dataset(
        store,
        CandleDatasetSpec(
            dataset_id=dataset_id,
            semantic_version="1.0.0",
            parent_dataset_ids=parent_dataset_ids,
            source_evidence_sha256=(digest,),
            coverage_evidence_sha256=digest,
            capacity_evidence_sha256="d" * 64,
            build_config_sha256="e" * 64,
            software_identity="fixture-publisher@1",
        ),
        batch,
        CapacityBudget(
            active_and_building_bytes=0,
            rest_staging_bytes=0,
            operating_reserve_bytes=MIN_OPERATING_RESERVE_BYTES,
        ),
        snapshot(tmp_path, observed_at_ms=1_000 + minutes[0]),
        now_ms=1_001 + minutes[0],
    )
    publish_candle_dataset(
        plan,
        snapshot(tmp_path, observed_at_ms=1_002 + minutes[0]),
        committed_at_ms=1_003 + minutes[0],
    )


def publish_funding_dataset_fixture(
    tmp_path: Path,
    store: Path,
    dataset_id: str,
    *,
    event_offsets_minutes: tuple[int, ...] = (0, 480),
    instrument_ids: tuple[int, ...] = (9,),
) -> None:
    coverage = "8" * 64
    boundary = "9" * 64
    batch = build_canonical_funding_batch(
        tuple(
            FundingEvent(
                category="linear",
                instrument_id=instrument_id,
                funding_time_ms=JANUARY_1_2026_MS + offset_minutes * 60_000,
                funding_rate=Decimal("0.0001"),
                funding_interval_minutes=480,
                source_id="bybit-v5-funding-history",
                ingestion_id=f"funding-fixture-{instrument_id}-{offset_minutes}",
            )
            for instrument_id in instrument_ids
            for offset_minutes in event_offsets_minutes
        )
    )
    plan = preflight_funding_dataset(
        store,
        FundingDatasetSpec(
            dataset_id=dataset_id,
            semantic_version="1.0.0",
            parent_dataset_ids=(),
            source_evidence_sha256=(coverage, boundary),
            coverage_evidence_sha256=coverage,
            boundary_evidence_sha256=boundary,
            capacity_evidence_sha256="d" * 64,
            build_config_sha256="e" * 64,
            software_identity="fixture-funding-publisher@1",
        ),
        batch,
        CapacityBudget(
            active_and_building_bytes=0,
            rest_staging_bytes=0,
            operating_reserve_bytes=MIN_OPERATING_RESERVE_BYTES,
        ),
        snapshot(tmp_path, observed_at_ms=1_000),
        now_ms=1_001,
    )
    publish_funding_dataset(
        plan,
        snapshot(tmp_path, observed_at_ms=1_002),
        committed_at_ms=1_003,
    )


def test_catalog_registers_and_selects_funding_without_mixing_dataset_types(
    tmp_path: Path,
) -> None:
    store = tmp_path / "market-store"
    funding_id = "funding-january-bucket01"
    candle_id = "trade-january-bucket01"
    publish_funding_dataset_fixture(tmp_path, store, funding_id)
    publish_dataset(tmp_path, store, candle_id, minutes=(0,), instrument_id=9)
    catalog = store / "catalog" / "canonical.duckdb"
    plan = preflight_catalog_registration(
        tuple(sorted((funding_id, candle_id))),
        store,
        catalog,
        software_identity=REGISTRAR,
    )
    registered = register_catalog_datasets(plan, registered_at_ms=2_000)
    by_id = {item.dataset_id: item for item in registered.datasets}
    assert by_id[funding_id].dataset_type is DatasetType.FUNDING_EVENT
    assert by_id[funding_id].partition_path == (
        "dataset=funding_event/schema=v1/year=2026/month=01/bucket=01"
    )

    registration_evidence = build_catalog_registration_evidence(
        plan,
        registered,
        generated_at_utc="2026-08-13T10:00:00Z",
    )
    registration_schema = json.loads(
        (
            ROOT
            / "schemas"
            / "evidence"
            / "v1"
            / "canonical-dataset-catalog-registration.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(
        registration_schema,
        format_checker=FormatChecker(),
    ).validate(registration_evidence)

    request = CatalogSelectionRequest(
        catalog_revision=registered.revision,
        catalog_content_sha256=registered.content_sha256,
        dataset_ids=(funding_id,),
        dataset_type=DatasetType.FUNDING_EVENT,
        start_time_ms=JANUARY_1_2026_MS,
        end_time_ms=JANUARY_1_2026_MS + 480 * 60_000,
        instrument_ids=(9,),
        consumer_software_identity=CONSUMER,
    )
    request_schema = json.loads(
        (
            ROOT / "schemas" / "market" / "v1" / "canonical-dataset-selection-request.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(request_schema).validate(selection_request_payload(request))
    selection = select_catalog_range(request, store, catalog)
    assert len(selection.objects) == 1
    assert "/dataset=funding_event/" in selection.objects[0].object_key
    selection_evidence = build_catalog_selection_evidence(
        selection,
        generated_at_utc="2026-08-13T10:01:00Z",
    )
    selection_schema = json.loads(
        (
            ROOT / "schemas" / "evidence" / "v1" / "canonical-dataset-selection.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(
        selection_schema,
        format_checker=FormatChecker(),
    ).validate(selection_evidence)

    mixed = CatalogSelectionRequest(
        catalog_revision=registered.revision,
        catalog_content_sha256=registered.content_sha256,
        dataset_ids=tuple(sorted((funding_id, candle_id))),
        dataset_type=DatasetType.FUNDING_EVENT,
        start_time_ms=JANUARY_1_2026_MS,
        end_time_ms=JANUARY_1_2026_MS,
        instrument_ids=(9,),
        consumer_software_identity=CONSUMER,
    )
    with pytest.raises(CatalogError, match="share the requested dataset type"):
        select_catalog_range(mixed, store, catalog)


def test_catalog_registration_and_selection_are_receipt_bound_and_idempotent(
    tmp_path: Path,
) -> None:
    store = tmp_path / "market-store"
    dataset_id = "trade-january-bucket01"
    publish_dataset(tmp_path, store, dataset_id, minutes=(0, 1, 2))
    catalog = store / "catalog" / "canonical.duckdb"
    plan = preflight_catalog_registration(
        (dataset_id,),
        store,
        catalog,
        software_identity=REGISTRAR,
    )
    assert plan.before.revision == 0
    assert plan.new_dataset_ids == (dataset_id,)
    assert not catalog.exists()

    registered = register_catalog_datasets(plan, registered_at_ms=2_000)
    assert registered.revision == 1
    assert registered.dataset_count == 1
    assert registered.file_count == 1
    assert verify_catalog(store, catalog) == registered

    registration_evidence = build_catalog_registration_evidence(
        plan,
        registered,
        generated_at_utc="2026-08-13T10:00:00Z",
    )
    registration_schema = json.loads(
        (
            ROOT
            / "schemas"
            / "evidence"
            / "v1"
            / "canonical-dataset-catalog-registration.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(
        registration_schema,
        format_checker=FormatChecker(),
    ).validate(registration_evidence)
    rendered = json.dumps(registration_evidence).lower()
    assert "c:\\" not in rendered
    assert '"open"' not in rendered
    registration_path, _ = publish_evidence(
        tmp_path / "catalog-registration.json",
        registration_evidence,
    )

    rerun = preflight_catalog_registration(
        (dataset_id,),
        store,
        catalog,
        software_identity=REGISTRAR,
    )
    assert rerun.existing_registration
    assert register_catalog_datasets(rerun, registered_at_ms=9_999) == registered
    assert (
        verify_catalog_registration_evidence(
            registration_path,
            rerun,
            registered,
        )
        == registration_evidence
    )

    request = CatalogSelectionRequest(
        catalog_revision=registered.revision,
        catalog_content_sha256=registered.content_sha256,
        dataset_ids=(dataset_id,),
        dataset_type=DatasetType.TRADE_KLINE_1M,
        start_time_ms=JANUARY_1_2026_MS,
        end_time_ms=JANUARY_1_2026_MS + 2 * 60_000,
        instrument_ids=(9,),
        consumer_software_identity=CONSUMER,
    )
    request_schema = json.loads(
        (
            ROOT / "schemas" / "market" / "v1" / "canonical-dataset-selection-request.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(request_schema).validate(selection_request_payload(request))
    selection = select_catalog_range(request, store, catalog)
    assert len(selection.objects) == 1
    assert selection.objects[0].object_key.startswith(f"datasets/{dataset_id}/")

    selection_evidence = build_catalog_selection_evidence(
        selection,
        generated_at_utc="2026-08-13T10:01:00Z",
    )
    selection_schema = json.loads(
        (
            ROOT / "schemas" / "evidence" / "v1" / "canonical-dataset-selection.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(
        selection_schema,
        format_checker=FormatChecker(),
    ).validate(selection_evidence)
    selection_path, _ = publish_evidence(
        tmp_path / "catalog-selection.json",
        selection_evidence,
    )
    assert (
        verify_catalog_selection_evidence(
            selection_path,
            selection,
        )
        == selection_evidence
    )


def test_catalog_requires_complete_registered_parent_lineage(tmp_path: Path) -> None:
    store = tmp_path / "market-store"
    parent_id = "trade-parent-fragment"
    child_id = "trade-child-fragment"
    publish_dataset(tmp_path, store, parent_id, minutes=(0,))
    publish_dataset(
        tmp_path,
        store,
        child_id,
        minutes=(1,),
        parent_dataset_ids=(parent_id,),
    )
    catalog = store / "catalog" / "canonical.duckdb"
    with pytest.raises(CatalogError, match="requires parent datasets"):
        preflight_catalog_registration(
            (child_id,),
            store,
            catalog,
            software_identity=REGISTRAR,
        )
    assert not catalog.exists()

    plan = preflight_catalog_registration(
        (child_id, parent_id),
        store,
        catalog,
        software_identity=REGISTRAR,
    )
    snapshot_after = register_catalog_datasets(plan, registered_at_ms=2_000)
    request = CatalogSelectionRequest(
        catalog_revision=snapshot_after.revision,
        catalog_content_sha256=snapshot_after.content_sha256,
        dataset_ids=tuple(sorted((child_id, parent_id))),
        dataset_type=DatasetType.TRADE_KLINE_1M,
        start_time_ms=JANUARY_1_2026_MS,
        end_time_ms=JANUARY_1_2026_MS + 60_000,
        instrument_ids=(9,),
        consumer_software_identity=CONSUMER,
    )
    with pytest.raises(CatalogError, match="ancestor and its child"):
        select_catalog_range(request, store, catalog)


def test_incremental_registration_preserves_prior_snapshot_and_selects_disjoint_fragments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("grid_market_store.catalog.EXACT_KEY_BATCH_ROWS", 1)
    store = tmp_path / "market-store"
    first_id = "trade-incremental-first"
    second_id = "trade-incremental-second"
    publish_dataset(tmp_path, store, first_id, minutes=(0, 1), instrument_ids=(9, 17))
    catalog = store / "catalog" / "canonical.duckdb"
    first_plan = preflight_catalog_registration(
        (first_id,),
        store,
        catalog,
        software_identity=REGISTRAR,
    )
    first = register_catalog_datasets(first_plan, registered_at_ms=2_000)

    publish_dataset(tmp_path, store, second_id, minutes=(2, 3), instrument_ids=(9, 17))
    second_plan = preflight_catalog_registration(
        (second_id,),
        store,
        catalog,
        software_identity=REGISTRAR,
    )
    assert second_plan.before == first
    second = register_catalog_datasets(second_plan, registered_at_ms=3_000)
    assert second.revision == 2
    assert second.dataset_count == 2
    assert second.content_sha256 != first.content_sha256
    assert {item.dataset_id for item in second.datasets} == {first_id, second_id}

    request = CatalogSelectionRequest(
        catalog_revision=second.revision,
        catalog_content_sha256=second.content_sha256,
        dataset_ids=tuple(sorted((first_id, second_id))),
        dataset_type=DatasetType.TRADE_KLINE_1M,
        start_time_ms=JANUARY_1_2026_MS,
        end_time_ms=JANUARY_1_2026_MS + 3 * 60_000,
        instrument_ids=(9,),
        consumer_software_identity=CONSUMER,
    )
    selection = select_catalog_range(request, store, catalog)
    assert len(selection.objects) == 2
    assert [item.dataset_id for item in selection.objects] == [first_id, second_id]


def test_incremental_selection_keeps_the_strict_bounds_metadata_fast_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = tmp_path / "market-store"
    first_id = "trade-incremental-fast-first"
    second_id = "trade-incremental-fast-second"
    publish_dataset(tmp_path, store, first_id, minutes=(0, 1))
    publish_dataset(tmp_path, store, second_id, minutes=(2, 3))
    catalog = store / "catalog" / "canonical.duckdb"
    plan = preflight_catalog_registration(
        (first_id, second_id),
        store,
        catalog,
        software_identity=REGISTRAR,
    )
    snapshot_after = register_catalog_datasets(plan, registered_at_ms=2_000)

    def fail_exact_stream(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("strict bounds must not stream Parquet keys")

    monkeypatch.setattr("grid_market_store.catalog._iter_file_keys", fail_exact_stream)
    request = CatalogSelectionRequest(
        catalog_revision=snapshot_after.revision,
        catalog_content_sha256=snapshot_after.content_sha256,
        dataset_ids=tuple(sorted((first_id, second_id))),
        dataset_type=DatasetType.TRADE_KLINE_1M,
        start_time_ms=JANUARY_1_2026_MS,
        end_time_ms=JANUARY_1_2026_MS + 3 * 60_000,
        instrument_ids=(9,),
        consumer_software_identity=CONSUMER,
    )
    selection = select_catalog_range(request, store, catalog)
    assert len(selection.objects) == 2


def test_incremental_selection_rejects_exact_duplicate_keys_across_fragments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("grid_market_store.catalog.EXACT_KEY_BATCH_ROWS", 1)
    store = tmp_path / "market-store"
    first_id = "trade-incremental-duplicate-first"
    second_id = "trade-incremental-duplicate-second"
    publish_dataset(tmp_path, store, first_id, minutes=(0, 1), instrument_ids=(9, 17))
    publish_dataset(tmp_path, store, second_id, minutes=(1, 2), instrument_ids=(9, 17))
    catalog = store / "catalog" / "canonical.duckdb"
    plan = preflight_catalog_registration(
        (first_id, second_id),
        store,
        catalog,
        software_identity=REGISTRAR,
    )
    snapshot_after = register_catalog_datasets(plan, registered_at_ms=2_000)
    request = CatalogSelectionRequest(
        catalog_revision=snapshot_after.revision,
        catalog_content_sha256=snapshot_after.content_sha256,
        dataset_ids=tuple(sorted((first_id, second_id))),
        dataset_type=DatasetType.TRADE_KLINE_1M,
        start_time_ms=JANUARY_1_2026_MS,
        end_time_ms=JANUARY_1_2026_MS + 2 * 60_000,
        instrument_ids=(9, 17),
        consumer_software_identity=CONSUMER,
    )
    with pytest.raises(CatalogError, match="duplicate or conflicting exact keys"):
        select_catalog_range(request, store, catalog)


def test_incremental_selection_fails_closed_above_the_exact_stream_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("grid_market_store.catalog.MAX_EXACT_KEY_STREAMS", 1)
    store = tmp_path / "market-store"
    first_id = "trade-incremental-bound-first"
    second_id = "trade-incremental-bound-second"
    publish_dataset(tmp_path, store, first_id, minutes=(0, 1), instrument_ids=(9, 17))
    publish_dataset(tmp_path, store, second_id, minutes=(2, 3), instrument_ids=(9, 17))
    catalog = store / "catalog" / "canonical.duckdb"
    plan = preflight_catalog_registration(
        (first_id, second_id),
        store,
        catalog,
        software_identity=REGISTRAR,
    )
    snapshot_after = register_catalog_datasets(plan, registered_at_ms=2_000)
    request = CatalogSelectionRequest(
        catalog_revision=snapshot_after.revision,
        catalog_content_sha256=snapshot_after.content_sha256,
        dataset_ids=tuple(sorted((first_id, second_id))),
        dataset_type=DatasetType.TRADE_KLINE_1M,
        start_time_ms=JANUARY_1_2026_MS,
        end_time_ms=JANUARY_1_2026_MS + 3 * 60_000,
        instrument_ids=(9, 17),
        consumer_software_identity=CONSUMER,
    )
    with pytest.raises(CatalogError, match="exact-key admission bound"):
        select_catalog_range(request, store, catalog)


def test_incremental_funding_selection_streams_the_funding_timestamp_key(
    tmp_path: Path,
) -> None:
    store = tmp_path / "market-store"
    first_id = "funding-incremental-first"
    second_id = "funding-incremental-second"
    publish_funding_dataset_fixture(
        tmp_path,
        store,
        first_id,
        event_offsets_minutes=(0, 480),
        instrument_ids=(9, 17),
    )
    publish_funding_dataset_fixture(
        tmp_path,
        store,
        second_id,
        event_offsets_minutes=(960, 1_440),
        instrument_ids=(9, 17),
    )
    catalog = store / "catalog" / "canonical.duckdb"
    plan = preflight_catalog_registration(
        (first_id, second_id),
        store,
        catalog,
        software_identity=REGISTRAR,
    )
    snapshot_after = register_catalog_datasets(plan, registered_at_ms=2_000)
    request = CatalogSelectionRequest(
        catalog_revision=snapshot_after.revision,
        catalog_content_sha256=snapshot_after.content_sha256,
        dataset_ids=tuple(sorted((first_id, second_id))),
        dataset_type=DatasetType.FUNDING_EVENT,
        start_time_ms=JANUARY_1_2026_MS,
        end_time_ms=JANUARY_1_2026_MS + 1_440 * 60_000,
        instrument_ids=(9, 17),
        consumer_software_identity=CONSUMER,
    )
    selection = select_catalog_range(request, store, catalog)
    assert len(selection.objects) == 2


def test_catalog_registration_rejects_duplicate_ids_and_cleans_failed_atomic_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = tmp_path / "market-store"
    dataset_id = "trade-atomic-fragment"
    publish_dataset(tmp_path, store, dataset_id, minutes=(0,))
    catalog = store / "catalog" / "canonical.duckdb"
    with pytest.raises(CatalogError, match="unique"):
        preflight_catalog_registration(
            (dataset_id, dataset_id),
            store,
            catalog,
            software_identity=REGISTRAR,
        )
    plan = preflight_catalog_registration(
        (dataset_id,),
        store,
        catalog,
        software_identity=REGISTRAR,
    )

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("fixture replace failure")

    monkeypatch.setattr("grid_market_store.catalog.os.replace", fail_replace)
    with pytest.raises(OSError, match="fixture replace failure"):
        register_catalog_datasets(plan, registered_at_ms=2_000)
    assert not catalog.exists()
    assert not plan.building_path.exists()
    assert not plan.lock_path.exists()


def test_catalog_writer_never_removes_a_lock_it_does_not_own(tmp_path: Path) -> None:
    store = tmp_path / "market-store"
    dataset_id = "trade-lock-fragment"
    publish_dataset(tmp_path, store, dataset_id, minutes=(0,))
    catalog = store / "catalog" / "canonical.duckdb"
    plan = preflight_catalog_registration(
        (dataset_id,),
        store,
        catalog,
        software_identity=REGISTRAR,
    )
    plan.lock_path.parent.mkdir(parents=True, exist_ok=True)
    plan.lock_path.write_text("other-writer\n", encoding="utf-8")
    with pytest.raises(CatalogError, match="write lock"):
        register_catalog_datasets(plan, registered_at_ms=2_000)
    assert plan.lock_path.read_text(encoding="utf-8") == "other-writer\n"
    assert not plan.building_path.exists()


def test_selection_rejects_snapshot_substitution_missing_partition_and_unsafe_request(
    tmp_path: Path,
) -> None:
    store = tmp_path / "market-store"
    dataset_id = "trade-selection-fragment"
    publish_dataset(tmp_path, store, dataset_id, minutes=(0,))
    catalog = store / "catalog" / "canonical.duckdb"
    plan = preflight_catalog_registration(
        (dataset_id,),
        store,
        catalog,
        software_identity=REGISTRAR,
    )
    registered = register_catalog_datasets(plan, registered_at_ms=2_000)
    substituted = CatalogSelectionRequest(
        catalog_revision=registered.revision,
        catalog_content_sha256="f" * 64,
        dataset_ids=(dataset_id,),
        dataset_type=DatasetType.TRADE_KLINE_1M,
        start_time_ms=JANUARY_1_2026_MS,
        end_time_ms=JANUARY_1_2026_MS,
        instrument_ids=(9,),
        consumer_software_identity=CONSUMER,
    )
    with pytest.raises(CatalogError, match="does not bind"):
        select_catalog_range(substituted, store, catalog)

    missing_bucket = CatalogSelectionRequest(
        catalog_revision=registered.revision,
        catalog_content_sha256=registered.content_sha256,
        dataset_ids=(dataset_id,),
        dataset_type=DatasetType.TRADE_KLINE_1M,
        start_time_ms=JANUARY_1_2026_MS,
        end_time_ms=JANUARY_1_2026_MS,
        instrument_ids=(10,),
        consumer_software_identity=CONSUMER,
    )
    with pytest.raises(CatalogError, match="missing required"):
        select_catalog_range(missing_bucket, store, catalog)

    request_path = tmp_path / "unsafe-request.json"
    request_path.write_text(
        json.dumps(
            {
                "catalog_content_sha256": registered.content_sha256,
                "catalog_revision": registered.revision,
                "consumer_software_identity": CONSUMER,
                "dataset_ids": [dataset_id],
                "dataset_type": "trade_kline_1m",
                "end_time_ms": JANUARY_1_2026_MS,
                "instrument_filter": {"instrument_ids": [9], "mode": "include"},
                "request_schema": CATALOG_SELECTION_REQUEST_CONTRACT,
                "start_time_ms": JANUARY_1_2026_MS,
                "unexpected": True,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CatalogError, match="closed v1"):
        load_catalog_selection_request(request_path)


def test_selection_rejects_registered_file_substitution(tmp_path: Path) -> None:
    store = tmp_path / "market-store"
    dataset_id = "trade-tamper-fragment"
    publish_dataset(tmp_path, store, dataset_id, minutes=(0,))
    catalog = store / "catalog" / "canonical.duckdb"
    plan = preflight_catalog_registration(
        (dataset_id,),
        store,
        catalog,
        software_identity=REGISTRAR,
    )
    registered = register_catalog_datasets(plan, registered_at_ms=2_000)
    request = CatalogSelectionRequest(
        catalog_revision=registered.revision,
        catalog_content_sha256=registered.content_sha256,
        dataset_ids=(dataset_id,),
        dataset_type=DatasetType.TRADE_KLINE_1M,
        start_time_ms=JANUARY_1_2026_MS,
        end_time_ms=JANUARY_1_2026_MS,
        instrument_ids=(9,),
        consumer_software_identity=CONSUMER,
    )
    object_path = store / registered.datasets[0].files[0].object_key
    with object_path.open("r+b") as stream:
        stream.seek(0)
        stream.write(b"X")
    with pytest.raises(CatalogError, match="does not verify"):
        select_catalog_range(request, store, catalog)
