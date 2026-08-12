from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest
from grid_contracts.market import Candle1m, DatasetStatus, DatasetType
from grid_market_store import (
    MIN_OPERATING_RESERVE_BYTES,
    CandleDatasetSpec,
    CapacityBudget,
    HostSnapshot,
    PublicationError,
    build_canonical_candle_batch,
    preflight_candle_dataset,
    publish_candle_dataset,
    verify_committed_candle_dataset,
)
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[2]


def candle(**overrides: object) -> Candle1m:
    values: dict[str, object] = {
        "category": "linear",
        "instrument_id": 9,
        "open_time_ms": 1_767_225_600_000,
        "open": Decimal("100.00000001"),
        "high": Decimal("102"),
        "low": Decimal("99.5"),
        "close": Decimal("101"),
        "volume": Decimal("10.5000"),
        "turnover": Decimal("1050.000000000001"),
        "source_id": "bybit-v5-kline",
        "ingestion_id": "fixture-run",
        "quality_flags": 0,
    }
    values.update(overrides)
    return Candle1m(**values)  # type: ignore[arg-type]


def spec() -> CandleDatasetSpec:
    return CandleDatasetSpec(
        dataset_id="trade-fixture-2026-01-b01",
        semantic_version="1.0.0",
        parent_dataset_ids=("instrument-snapshot-fixture",),
        source_evidence_sha256=("a" * 64, "b" * 64),
        coverage_evidence_sha256="b" * 64,
        capacity_evidence_sha256="d" * 64,
        build_config_sha256="c" * 64,
        software_identity="test-suite@1",
    )


def budget() -> CapacityBudget:
    return CapacityBudget(
        active_and_building_bytes=0,
        rest_staging_bytes=32 * 1024**2,
        operating_reserve_bytes=MIN_OPERATING_RESERVE_BYTES,
    )


def snapshot(
    volume_root: Path,
    *,
    observed_at_ms: int = 1_000,
    free_bytes: int = 20 * 1024**3,
    device_id: str = "fixture-nvme",
) -> HostSnapshot:
    return HostSnapshot(
        observed_at_ms=observed_at_ms,
        memory_total_bytes=16 * 1024**3,
        memory_available_bytes=8 * 1024**3,
        storage_kind="nvme",
        storage_device_id=device_id,
        volume_root=volume_root.resolve(),
        volume_free_bytes=free_bytes,
    )


def batch(*rows: Candle1m):  # type: ignore[no-untyped-def]
    values = rows or (candle(), candle(open_time_ms=1_767_225_660_000))
    return build_canonical_candle_batch(values, DatasetType.TRADE_KLINE_1M)


def plan(tmp_path: Path):  # type: ignore[no-untyped-def]
    store = tmp_path / "market-store"
    result = preflight_candle_dataset(
        store,
        spec(),
        batch(),
        budget(),
        snapshot(tmp_path),
        now_ms=1_001,
    )
    return store, result


def test_preflight_is_no_mutation_and_publication_writes_receipt_last_contract(
    tmp_path: Path,
) -> None:
    store, publication_plan = plan(tmp_path)
    assert not store.exists()

    published = publish_candle_dataset(
        publication_plan,
        snapshot(tmp_path, observed_at_ms=1_002),
        committed_at_ms=1_003,
    )

    assert published.manifest.status is DatasetStatus.COMPLETE
    assert published.manifest.row_count == 2
    assert published.manifest.instrument_count == 1
    assert published.receipt.manifest_sha256
    assert published.receipt_path.is_file()
    manifest_schema = json.loads(
        (ROOT / "schemas" / "dataset" / "v1" / "manifest.schema.json").read_text(encoding="utf-8")
    )
    receipt_schema = json.loads(
        (ROOT / "schemas" / "dataset" / "v1" / "completion-receipt.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(manifest_schema).validate(
        json.loads(published.manifest_path.read_text(encoding="utf-8"))
    )
    Draft202012Validator(receipt_schema).validate(
        json.loads(published.receipt_path.read_text(encoding="utf-8"))
    )
    assert not publication_plan.paths.building_root.exists()
    assert list((store / ".building").iterdir()) == []
    parquet_path = published.dataset_root / published.manifest.files[0].path
    parquet = pq.ParquetFile(parquet_path)
    try:
        assert parquet.metadata.num_rows == 2
        assert parquet.metadata.row_group(0).column(0).compression == "ZSTD"
        assert parquet.schema_arrow.metadata[b"grid.compression_level"] == b"3"
    finally:
        parquet.close()
    audit = json.loads(published.audit_path.read_text(encoding="utf-8"))
    assert audit["file_target"]["classification"] == "tail-below-target"
    assert audit["quality_checks"] == {
        "canonical_schema_verified": True,
        "file_hash_recorded": True,
        "parquet_footer_verified": True,
        "single_partition": True,
        "sorted_unique_keys": True,
        "upstream_coverage_evidence_bound": True,
    }


def test_same_request_is_idempotent_but_changed_content_is_rejected(tmp_path: Path) -> None:
    store, first_plan = plan(tmp_path)
    first = publish_candle_dataset(
        first_plan,
        snapshot(tmp_path, observed_at_ms=1_002),
        committed_at_ms=1_003,
    )
    rerun = preflight_candle_dataset(
        store,
        spec(),
        batch(),
        budget(),
        snapshot(tmp_path, observed_at_ms=1_004),
        now_ms=1_005,
    )
    assert rerun.existing_commit is True
    second = publish_candle_dataset(
        rerun,
        snapshot(tmp_path, observed_at_ms=1_006),
        committed_at_ms=1_007,
    )
    assert second.receipt == first.receipt

    changed = batch(candle(close=Decimal("100.5")))
    with pytest.raises(PublicationError, match="different content"):
        preflight_candle_dataset(
            store,
            spec(),
            changed,
            budget(),
            snapshot(tmp_path, observed_at_ms=1_008),
            now_ms=1_009,
        )


def test_preflight_rejects_capacity_before_creating_store(tmp_path: Path) -> None:
    store = tmp_path / "market-store"
    with pytest.raises(PublicationError, match="insufficient free space"):
        preflight_candle_dataset(
            store,
            spec(),
            batch(),
            budget(),
            snapshot(tmp_path, free_bytes=1024),
            now_ms=1_001,
        )
    assert not store.exists()


def test_preflight_rejects_stale_or_future_host_observation(tmp_path: Path) -> None:
    store = tmp_path / "market-store"
    with pytest.raises(PublicationError, match="fresh"):
        preflight_candle_dataset(
            store,
            spec(),
            batch(),
            budget(),
            snapshot(tmp_path, observed_at_ms=0),
            now_ms=60_001,
        )
    with pytest.raises(PublicationError, match="future-dated"):
        preflight_candle_dataset(
            store,
            spec(),
            batch(),
            budget(),
            snapshot(tmp_path, observed_at_ms=2_000),
            now_ms=1_999,
        )
    assert not store.exists()


def test_publish_rechecks_free_space_and_device_before_mutation(tmp_path: Path) -> None:
    store, publication_plan = plan(tmp_path)
    with pytest.raises(PublicationError, match="insufficient free space"):
        publish_candle_dataset(
            publication_plan,
            snapshot(tmp_path, observed_at_ms=1_002, free_bytes=1024),
            committed_at_ms=1_003,
        )
    assert not store.exists()

    with pytest.raises(PublicationError, match="identity changed"):
        publish_candle_dataset(
            publication_plan,
            snapshot(tmp_path, observed_at_ms=1_002, device_id="other-nvme"),
            committed_at_ms=1_003,
        )
    assert not store.exists()


def test_stale_building_output_is_detected_without_deletion(tmp_path: Path) -> None:
    store, publication_plan = plan(tmp_path)
    publication_plan.paths.building_root.mkdir(parents=True)
    marker = publication_plan.paths.building_root / "partial"
    marker.write_text("keep for repair evidence", encoding="utf-8")

    with pytest.raises(PublicationError, match="stale building"):
        preflight_candle_dataset(
            store,
            spec(),
            batch(),
            budget(),
            snapshot(tmp_path, observed_at_ms=1_004),
            now_ms=1_005,
        )
    assert marker.read_text(encoding="utf-8") == "keep for repair evidence"


def test_receipt_failure_leaves_uncommitted_dataset_detectable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _store, publication_plan = plan(tmp_path)
    real_replace = os.replace

    def fail_receipt(source: str | Path, target: str | Path) -> None:
        if Path(target).name == "completion-receipt.json":
            raise OSError("injected receipt failure")
        real_replace(source, target)

    monkeypatch.setattr("grid_market_store.publication.os.replace", fail_receipt)
    with pytest.raises(OSError, match="injected receipt"):
        publish_candle_dataset(
            publication_plan,
            snapshot(tmp_path, observed_at_ms=1_002),
            committed_at_ms=1_003,
        )
    assert publication_plan.paths.dataset_root.is_dir()
    assert not (publication_plan.paths.dataset_root / "completion-receipt.json").exists()
    with pytest.raises(PublicationError, match="no completion receipt"):
        verify_committed_candle_dataset(publication_plan.paths.dataset_root)


def test_verifier_detects_tamper_and_orphans(tmp_path: Path) -> None:
    _store, publication_plan = plan(tmp_path)
    published = publish_candle_dataset(
        publication_plan,
        snapshot(tmp_path, observed_at_ms=1_002),
        committed_at_ms=1_003,
    )
    orphan = published.dataset_root / "unexpected.txt"
    orphan.write_text("orphan", encoding="utf-8")
    with pytest.raises(PublicationError, match="orphan"):
        verify_committed_candle_dataset(published.dataset_root)
    orphan.unlink()

    parquet_path = published.dataset_root / published.manifest.files[0].path
    with parquet_path.open("ab") as stream:
        stream.write(b"tamper")
    with pytest.raises(PublicationError, match="hash or size"):
        verify_committed_candle_dataset(published.dataset_root)


def test_storage_and_identity_contracts_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(PublicationError, match="NVMe or SSD"):
        HostSnapshot(
            observed_at_ms=1,
            memory_total_bytes=16 * 1024**3,
            memory_available_bytes=8 * 1024**3,
            storage_kind="hdd",
            storage_device_id="fixture-hdd",
            volume_root=tmp_path,
            volume_free_bytes=20 * 1024**3,
        )
    with pytest.raises(PublicationError, match="safe lowercase"):
        CandleDatasetSpec(
            dataset_id="../escape",
            semantic_version="1.0.0",
            parent_dataset_ids=(),
            source_evidence_sha256=("a" * 64,),
            coverage_evidence_sha256="a" * 64,
            capacity_evidence_sha256="d" * 64,
            build_config_sha256="b" * 64,
            software_identity="test-suite@1",
        )
    with pytest.raises(PublicationError, match="coverage evidence"):
        CandleDatasetSpec(
            dataset_id="valid-dataset",
            semantic_version="1.0.0",
            parent_dataset_ids=(),
            source_evidence_sha256=("a" * 64,),
            coverage_evidence_sha256="c" * 64,
            capacity_evidence_sha256="d" * 64,
            build_config_sha256="b" * 64,
            software_identity="test-suite@1",
        )
