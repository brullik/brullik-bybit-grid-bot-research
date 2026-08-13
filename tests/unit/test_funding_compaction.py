from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from grid_contracts.market import FundingEvent
from grid_data.evidence import publish_evidence
from grid_data.funding_compaction import (
    FundingCompactionError,
    build_funding_compaction_evidence,
    preflight_funding_compaction,
    publish_preflighted_funding_compaction,
    verify_funding_compaction_evidence,
)
from grid_market_store import (
    MIN_OPERATING_RESERVE_BYTES,
    CapacityBudget,
    FundingDatasetSpec,
    HostSnapshot,
    build_canonical_funding_batch,
    load_committed_funding_table,
    preflight_funding_dataset,
    publish_funding_dataset,
    verify_committed_funding_dataset,
)
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[2]
JANUARY_1_2026_MS = 1_767_225_600_000
ACTIVE_BUILDING_BYTES = 90_000_000_000
SOFTWARE_IDENTITY = f"git:{'9' * 40}"


def snapshot(
    root: Path,
    *,
    observed_at_ms: int,
    free_bytes: int = 200 * 1024**3,
) -> HostSnapshot:
    return HostSnapshot(
        observed_at_ms=observed_at_ms,
        memory_total_bytes=16 * 1024**3,
        memory_available_bytes=8 * 1024**3,
        storage_kind="nvme",
        storage_device_id="fixture-nvme",
        volume_root=root.resolve(),
        volume_free_bytes=free_bytes,
    )


def capacity_payload() -> dict[str, object]:
    return {
        "disk_headroom": {
            "scenarios": [
                {
                    "id": "full-rebuild-active-plus-building",
                    "required_bytes": ACTIVE_BUILDING_BYTES,
                }
            ]
        },
        "evidence_schema": "grid.current-universe-capacity/v1",
        "layout_projections": [
            {
                "layout": {
                    "bucket_count": 8,
                    "compression": "zstd",
                    "compression_level": 3,
                    "numeric_representation": "hybrid_int64_decimal",
                    "target_file_mb": 16,
                }
            }
        ],
    }


def funding_event(
    *,
    timestamp: int,
    interval_minutes: int = 480,
    instrument_id: int = 9,
) -> FundingEvent:
    return FundingEvent(
        category="linear",
        instrument_id=instrument_id,
        funding_time_ms=timestamp,
        funding_rate=Decimal("0.0001"),
        funding_interval_minutes=interval_minutes,
        source_id="bybit-v5-funding-history/v1",
        ingestion_id=f"fixture-{instrument_id}-{timestamp}",
    )


def publish_parent(
    tmp_path: Path,
    store: Path,
    *,
    index: int,
    timestamp: int,
    interval_minutes: int = 480,
    instrument_id: int = 9,
) -> str:
    dataset_id = f"funding-fragment-{index:02d}"
    digest = f"{index + 1:064x}"
    batch = build_canonical_funding_batch(
        (
            funding_event(
                timestamp=timestamp,
                interval_minutes=interval_minutes,
                instrument_id=instrument_id,
            ),
        )
    )
    plan = preflight_funding_dataset(
        store,
        FundingDatasetSpec(
            dataset_id=dataset_id,
            semantic_version="1.0.0",
            parent_dataset_ids=(),
            source_evidence_sha256=(digest,),
            coverage_evidence_sha256=digest,
            boundary_evidence_sha256=digest,
            capacity_evidence_sha256="d" * 64,
            build_config_sha256=f"{index + 101:064x}",
            software_identity="test-suite@1",
        ),
        batch,
        CapacityBudget(
            active_and_building_bytes=0,
            rest_staging_bytes=0,
            operating_reserve_bytes=MIN_OPERATING_RESERVE_BYTES,
        ),
        snapshot(tmp_path, observed_at_ms=1_000 + index * 10),
        now_ms=1_001 + index * 10,
    )
    publish_funding_dataset(
        plan,
        snapshot(tmp_path, observed_at_ms=1_002 + index * 10),
        committed_at_ms=1_003 + index * 10,
    )
    return dataset_id


def compaction_inputs(
    tmp_path: Path,
    *,
    timestamps: tuple[int, ...] = (
        JANUARY_1_2026_MS,
        JANUARY_1_2026_MS + 480 * 60_000,
        JANUARY_1_2026_MS + 960 * 60_000,
    ),
    intervals: tuple[int, ...] | None = None,
    instrument_ids: tuple[int, ...] | None = None,
) -> tuple[Path, Path, tuple[str, ...]]:
    store = tmp_path / "market-store"
    resolved_intervals = intervals or tuple(480 for _ in timestamps)
    resolved_instruments = instrument_ids or tuple(9 for _ in timestamps)
    dataset_ids = tuple(
        publish_parent(
            tmp_path,
            store,
            index=index,
            timestamp=timestamp,
            interval_minutes=resolved_intervals[index],
            instrument_id=resolved_instruments[index],
        )
        for index, timestamp in enumerate(timestamps)
    )
    capacity, _ = publish_evidence(tmp_path / "capacity.json", capacity_payload())
    return store, capacity, dataset_ids


def test_funding_compaction_preserves_exact_union_and_parent_lineage(
    tmp_path: Path,
) -> None:
    store, capacity, dataset_ids = compaction_inputs(tmp_path)
    parent_hashes = {
        dataset_id: verify_committed_funding_dataset(
            store / "datasets" / dataset_id
        ).receipt.manifest_sha256
        for dataset_id in dataset_ids
    }
    resolved = preflight_funding_compaction(
        tuple(reversed(dataset_ids)),
        capacity,
        store,
        snapshot(tmp_path, observed_at_ms=2_000),
        now_ms=2_001,
        software_identity=SOFTWARE_IDENTITY,
    )
    assert resolved.input_file_count == 3
    assert resolved.plan.spec.parent_dataset_ids == tuple(sorted(dataset_ids))
    assert not resolved.plan.paths.dataset_root.exists()

    published = publish_preflighted_funding_compaction(
        resolved,
        lambda: snapshot(tmp_path, observed_at_ms=2_002),
        lambda: 2_003,
    )
    verified = verify_committed_funding_dataset(published.dataset_root)
    assert verified.manifest.row_count == 3
    assert len(verified.manifest.files) == 1
    assert verified.manifest.parent_dataset_ids == tuple(sorted(dataset_ids))
    assert load_committed_funding_table(verified.dataset_root).equals(
        resolved.plan.batch.table,
        check_metadata=True,
    )
    for dataset_id, manifest_hash in parent_hashes.items():
        parent = verify_committed_funding_dataset(store / "datasets" / dataset_id)
        assert parent.receipt.manifest_sha256 == manifest_hash

    evidence = build_funding_compaction_evidence(
        resolved,
        verified,
        generated_at_utc="2026-08-13T21:00:00Z",
    )
    schema = json.loads(
        (
            ROOT / "schemas" / "evidence" / "v1" / "canonical-funding-compaction.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(evidence)
    bindings = evidence["bindings"]
    assert isinstance(bindings, dict)
    assert bindings["input_table_sha256"] == bindings["output_table_sha256"]
    rendered = json.dumps(evidence).lower()
    assert "c:\\" not in rendered
    assert '"funding_rate"' not in rendered
    assert "0.0001" not in rendered
    evidence_path, _ = publish_evidence(tmp_path / "funding-compaction.json", evidence)
    assert verify_funding_compaction_evidence(evidence_path, resolved, verified) == evidence

    rerun = preflight_funding_compaction(
        dataset_ids,
        capacity,
        store,
        snapshot(tmp_path, observed_at_ms=2_010),
        now_ms=2_011,
        software_identity=SOFTWARE_IDENTITY,
    )
    assert rerun.plan.existing_commit is True
    repeated = publish_preflighted_funding_compaction(
        rerun,
        lambda: snapshot(tmp_path, observed_at_ms=2_012),
        lambda: 2_013,
    )
    assert repeated.receipt.manifest_sha256 == verified.receipt.manifest_sha256


def test_funding_compaction_rejects_duplicate_and_unresolved_interval(
    tmp_path: Path,
) -> None:
    store, capacity, duplicate_ids = compaction_inputs(
        tmp_path / "duplicate",
        timestamps=(JANUARY_1_2026_MS, JANUARY_1_2026_MS),
    )
    with pytest.raises(FundingCompactionError, match="duplicate or conflicting"):
        preflight_funding_compaction(
            duplicate_ids,
            capacity,
            store,
            snapshot(tmp_path, observed_at_ms=2_000),
            now_ms=2_001,
            software_identity=SOFTWARE_IDENTITY,
        )

    store, capacity, interval_ids = compaction_inputs(
        tmp_path / "interval",
        timestamps=(JANUARY_1_2026_MS, JANUARY_1_2026_MS + 480 * 60_000),
        intervals=(480, 240),
    )
    with pytest.raises(FundingCompactionError, match="unresolved settlement interval"):
        preflight_funding_compaction(
            interval_ids,
            capacity,
            store,
            snapshot(tmp_path, observed_at_ms=2_010),
            now_ms=2_011,
            software_identity=SOFTWARE_IDENTITY,
        )


def test_funding_compaction_rejects_partition_mix_and_unsafe_inventory(
    tmp_path: Path,
) -> None:
    store, capacity, dataset_ids = compaction_inputs(
        tmp_path / "partition",
        timestamps=(JANUARY_1_2026_MS, JANUARY_1_2026_MS + 32 * 24 * 60 * 60_000),
    )
    with pytest.raises(FundingCompactionError, match="one month/bucket partition"):
        preflight_funding_compaction(
            dataset_ids,
            capacity,
            store,
            snapshot(tmp_path, observed_at_ms=2_000),
            now_ms=2_001,
            software_identity=SOFTWARE_IDENTITY,
        )
    with pytest.raises(FundingCompactionError, match="at least two unique"):
        preflight_funding_compaction(
            ("same", "same"),
            capacity,
            store,
            snapshot(tmp_path, observed_at_ms=2_010),
            now_ms=2_011,
            software_identity=SOFTWARE_IDENTITY,
        )
    with pytest.raises(FundingCompactionError, match="unsafe"):
        preflight_funding_compaction(
            ("../escape", "safe-parent"),
            capacity,
            store,
            snapshot(tmp_path, observed_at_ms=2_020),
            now_ms=2_021,
            software_identity=SOFTWARE_IDENTITY,
        )


def test_funding_compaction_reverifies_parent_before_publication(tmp_path: Path) -> None:
    store, capacity, dataset_ids = compaction_inputs(
        tmp_path,
        timestamps=(JANUARY_1_2026_MS, JANUARY_1_2026_MS + 480 * 60_000),
    )
    resolved = preflight_funding_compaction(
        dataset_ids,
        capacity,
        store,
        snapshot(tmp_path, observed_at_ms=2_000),
        now_ms=2_001,
        software_identity=SOFTWARE_IDENTITY,
    )
    parent = verify_committed_funding_dataset(store / "datasets" / dataset_ids[0])
    parquet = parent.dataset_root / parent.manifest.files[0].path
    with parquet.open("ab") as stream:
        stream.write(b"tamper")
    with pytest.raises(RuntimeError, match="hash or size"):
        publish_preflighted_funding_compaction(
            resolved,
            lambda: snapshot(tmp_path, observed_at_ms=2_002),
            lambda: 2_003,
        )
    assert not resolved.plan.paths.dataset_root.exists()
