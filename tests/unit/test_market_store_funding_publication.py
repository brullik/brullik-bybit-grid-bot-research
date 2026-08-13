from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]
import pytest
from grid_contracts.market import DatasetStatus, FundingEvent
from grid_market_store import (
    MIN_OPERATING_RESERVE_BYTES,
    CapacityBudget,
    FundingDatasetSpec,
    HostSnapshot,
    PublicationError,
    build_canonical_funding_batch,
    load_committed_funding_table,
    preflight_funding_dataset,
    publish_funding_dataset,
    verify_committed_funding_dataset,
)
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[2]


def funding_event(**overrides: object) -> FundingEvent:
    values: dict[str, object] = {
        "category": "linear",
        "instrument_id": 9,
        "funding_time_ms": 1_767_225_600_000,
        "funding_rate": Decimal("0.0001"),
        "funding_interval_minutes": 480,
        "source_id": "bybit-v5-funding-history/v1",
        "ingestion_id": "fixture-run",
        "quality_flags": 0,
    }
    values.update(overrides)
    return FundingEvent(**values)  # type: ignore[arg-type]


def spec() -> FundingDatasetSpec:
    return FundingDatasetSpec(
        dataset_id="funding-fixture-2026-01-b01",
        semantic_version="1.0.0",
        parent_dataset_ids=("instrument-snapshot-fixture",),
        source_evidence_sha256=("a" * 64, "b" * 64, "e" * 64),
        coverage_evidence_sha256="b" * 64,
        boundary_evidence_sha256="e" * 64,
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


def batch(*rows: FundingEvent):  # type: ignore[no-untyped-def]
    values = rows or (
        funding_event(),
        funding_event(funding_time_ms=1_767_254_400_000, funding_rate=Decimal("-0.0002")),
    )
    return build_canonical_funding_batch(values)


def plan(tmp_path: Path):  # type: ignore[no-untyped-def]
    store = tmp_path / "market-store"
    result = preflight_funding_dataset(
        store,
        spec(),
        batch(),
        budget(),
        snapshot(tmp_path),
        now_ms=1_001,
    )
    return store, result


def test_funding_publication_is_receipt_last_exact_and_verifiable(tmp_path: Path) -> None:
    store, publication_plan = plan(tmp_path)
    assert not store.exists()

    published = publish_funding_dataset(
        publication_plan,
        snapshot(tmp_path, observed_at_ms=1_002),
        committed_at_ms=1_003,
    )

    assert published.manifest.status is DatasetStatus.COMPLETE
    assert published.manifest.row_count == 2
    assert published.manifest.instrument_count == 1
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
    table = load_committed_funding_table(published.dataset_root)
    assert table.schema.field("funding_rate").type == pa.decimal128(38, 18)
    assert table.column("funding_rate").to_pylist() == [
        Decimal("0.000100000000000000"),
        Decimal("-0.000200000000000000"),
    ]
    audit = json.loads(published.audit_path.read_text(encoding="utf-8"))
    assert audit["quality_checks"]["internal_interval_deltas_verified"] is True
    assert audit["quality_checks"]["upstream_boundary_interval_evidence_bound"] is True


def test_funding_publication_is_idempotent_and_rejects_changed_content(tmp_path: Path) -> None:
    store, first_plan = plan(tmp_path)
    first = publish_funding_dataset(
        first_plan,
        snapshot(tmp_path, observed_at_ms=1_002),
        committed_at_ms=1_003,
    )
    rerun = preflight_funding_dataset(
        store,
        spec(),
        batch(),
        budget(),
        snapshot(tmp_path, observed_at_ms=1_004),
        now_ms=1_005,
    )
    assert rerun.existing_commit is True
    second = publish_funding_dataset(
        rerun,
        snapshot(tmp_path, observed_at_ms=1_006),
        committed_at_ms=1_007,
    )
    assert second.receipt == first.receipt

    with pytest.raises(PublicationError, match="different content"):
        preflight_funding_dataset(
            store,
            spec(),
            batch(
                funding_event(funding_rate=Decimal("0.0003")),
                funding_event(funding_time_ms=1_767_254_400_000),
            ),
            budget(),
            snapshot(tmp_path, observed_at_ms=1_008),
            now_ms=1_009,
        )


def test_funding_spec_requires_explicit_boundary_evidence_membership() -> None:
    values = {
        "dataset_id": "funding-fixture-2026-01-b01",
        "semantic_version": "1.0.0",
        "parent_dataset_ids": (),
        "source_evidence_sha256": ("a" * 64,),
        "coverage_evidence_sha256": "a" * 64,
        "boundary_evidence_sha256": "b" * 64,
        "capacity_evidence_sha256": "c" * 64,
        "build_config_sha256": "d" * 64,
        "software_identity": "test-suite@1",
    }
    with pytest.raises(PublicationError, match="boundary_evidence_sha256"):
        FundingDatasetSpec(**values)  # type: ignore[arg-type]


def test_funding_preflight_detects_stale_building_without_deleting_it(
    tmp_path: Path,
) -> None:
    store, publication_plan = plan(tmp_path)
    publication_plan.paths.building_root.mkdir(parents=True)
    marker = publication_plan.paths.building_root / "partial"
    marker.write_text("keep for repair evidence", encoding="utf-8")

    with pytest.raises(PublicationError, match="stale building"):
        preflight_funding_dataset(
            store,
            spec(),
            batch(),
            budget(),
            snapshot(tmp_path, observed_at_ms=1_004),
            now_ms=1_005,
        )
    assert marker.read_text(encoding="utf-8") == "keep for repair evidence"


def test_funding_receipt_failure_and_tamper_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _store, publication_plan = plan(tmp_path)
    real_replace = os.replace

    def fail_receipt(source: str | Path, target: str | Path) -> None:
        if Path(target).name == "completion-receipt.json":
            raise OSError("injected receipt failure")
        real_replace(source, target)

    monkeypatch.setattr("grid_market_store.funding_publication.os.replace", fail_receipt)
    with pytest.raises(OSError, match="injected receipt"):
        publish_funding_dataset(
            publication_plan,
            snapshot(tmp_path, observed_at_ms=1_002),
            committed_at_ms=1_003,
        )
    assert publication_plan.paths.dataset_root.is_dir()
    with pytest.raises(PublicationError, match="no completion receipt"):
        verify_committed_funding_dataset(publication_plan.paths.dataset_root)


def test_funding_verifier_detects_orphans_and_parquet_tamper(tmp_path: Path) -> None:
    _store, publication_plan = plan(tmp_path)
    published = publish_funding_dataset(
        publication_plan,
        snapshot(tmp_path, observed_at_ms=1_002),
        committed_at_ms=1_003,
    )
    orphan = published.dataset_root / "unexpected.txt"
    orphan.write_text("orphan", encoding="utf-8")
    with pytest.raises(PublicationError, match="orphan"):
        verify_committed_funding_dataset(published.dataset_root)
    orphan.unlink()

    parquet_path = published.dataset_root / published.manifest.files[0].path
    with parquet_path.open("ab") as stream:
        stream.write(b"tamper")
    with pytest.raises(PublicationError, match="hash or size"):
        verify_committed_funding_dataset(published.dataset_root)
