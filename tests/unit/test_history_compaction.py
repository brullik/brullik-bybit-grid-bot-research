from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest
from grid_contracts.market import Candle1m, DatasetType
from grid_data.evidence import publish_evidence
from grid_data.history_compaction import (
    HistoryCompactionError,
    build_compaction_evidence,
    preflight_history_compaction,
    publish_preflighted_compaction,
    verify_compaction_evidence,
)
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
    verify_compacted_candle_dataset,
)
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[2]
JANUARY_1_2026_MS = 1_767_225_600_000
ACTIVE_BUILDING_BYTES = 90_000_000_000
SOFTWARE_IDENTITY = f"git:{'f' * 40}"


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


def candle(open_time_ms: int) -> Candle1m:
    return Candle1m(
        category="linear",
        instrument_id=9,
        open_time_ms=open_time_ms,
        open=Decimal("100.00000001"),
        high=Decimal("102"),
        low=Decimal("99.5"),
        close=Decimal("101"),
        volume=Decimal("10.5000"),
        turnover=Decimal("1050.000000000001"),
        source_id="bybit-v5-kline",
        ingestion_id=f"fixture-{open_time_ms}",
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


def publish_parent(
    tmp_path: Path,
    store: Path,
    *,
    index: int,
    open_time_ms: int,
) -> str:
    digest = f"{index + 1:064x}"
    dataset_id = f"trade-fragment-{index:02d}"
    batch = build_canonical_candle_batch(
        (candle(open_time_ms),),
        DatasetType.TRADE_KLINE_1M,
    )
    plan = preflight_candle_dataset(
        store,
        CandleDatasetSpec(
            dataset_id=dataset_id,
            semantic_version="1.0.0",
            parent_dataset_ids=(),
            source_evidence_sha256=(digest,),
            coverage_evidence_sha256=digest,
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
    publish_candle_dataset(
        plan,
        snapshot(tmp_path, observed_at_ms=1_002 + index * 10),
        committed_at_ms=1_003 + index * 10,
    )
    return dataset_id


def compaction_inputs(
    tmp_path: Path,
    *,
    parent_count: int = 8,
    duplicate_last: bool = False,
) -> tuple[Path, Path, tuple[str, ...]]:
    store = tmp_path / "market-store"
    dataset_ids = []
    for index in range(parent_count):
        minute = 0 if duplicate_last and index == parent_count - 1 else index
        dataset_ids.append(
            publish_parent(
                tmp_path,
                store,
                index=index,
                open_time_ms=JANUARY_1_2026_MS + minute * 60_000,
            )
        )
    capacity, _ = publish_evidence(tmp_path / "capacity.json", capacity_payload())
    return store, capacity, tuple(dataset_ids)


def test_compaction_publishes_multi_file_child_with_one_explicit_tail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample_bytes_for_three_rows = 44_739_242
    monkeypatch.setattr("grid_market_store.publication.ROW_GROUP_ROWS", 1)
    monkeypatch.setattr("grid_market_store.compaction.ROW_GROUP_ROWS", 1)
    monkeypatch.setattr(
        "grid_market_store.compaction._calibrate_rows_per_file",
        lambda table: (3, table.num_rows, sample_bytes_for_three_rows),
    )
    store, capacity, dataset_ids = compaction_inputs(tmp_path)
    parent_hashes = {
        dataset_id: verify_committed_candle_dataset(
            store / "datasets" / dataset_id
        ).receipt.manifest_sha256
        for dataset_id in dataset_ids
    }
    resolved = preflight_history_compaction(
        tuple(reversed(dataset_ids)),
        capacity,
        store,
        snapshot(tmp_path, observed_at_ms=2_000),
        now_ms=2_001,
        software_identity=SOFTWARE_IDENTITY,
    )
    assert resolved.plan.input_file_count == 8
    assert resolved.plan.expected_output_file_count == 3
    assert resolved.plan.rows_per_file_target == 3
    assert not resolved.plan.paths.dataset_root.exists()

    published = publish_preflighted_compaction(
        resolved,
        lambda: snapshot(tmp_path, observed_at_ms=2_002),
        lambda: 2_003,
    )
    verified = verify_compacted_candle_dataset(published.dataset_root)
    assert [item.row_count for item in verified.manifest.files] == [3, 3, 2]
    assert verified.manifest.parent_dataset_ids == tuple(sorted(dataset_ids))
    audit = json.loads(verified.audit_path.read_text(encoding="utf-8"))
    assert audit["compaction"]["input_file_count"] == 8
    assert audit["compaction"]["output_file_count"] == 3
    assert audit["compaction"]["tail_file_count"] == 1
    assert [item["is_tail"] for item in audit["files"]] == [False, False, True]
    for dataset_id, manifest_hash in parent_hashes.items():
        parent = verify_committed_candle_dataset(store / "datasets" / dataset_id)
        assert parent.receipt.manifest_sha256 == manifest_hash

    evidence = build_compaction_evidence(
        resolved,
        verified,
        generated_at_utc="2026-08-13T08:00:00Z",
    )
    schema = json.loads(
        (ROOT / "schemas" / "evidence" / "v1" / "canonical-1m-compaction.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(evidence)
    rendered = json.dumps(evidence).lower()
    assert "c:\\" not in rendered
    assert '"open"' not in rendered
    evidence_path, _ = publish_evidence(tmp_path / "compaction.json", evidence)
    assert verify_compaction_evidence(evidence_path, resolved, verified) == evidence

    rerun = preflight_history_compaction(
        dataset_ids,
        capacity,
        store,
        snapshot(tmp_path, observed_at_ms=2_010),
        now_ms=2_011,
        software_identity=SOFTWARE_IDENTITY,
    )
    assert rerun.plan.existing_commit is True
    repeated = publish_preflighted_compaction(
        rerun,
        lambda: snapshot(tmp_path, observed_at_ms=2_012),
        lambda: 2_013,
    )
    assert repeated.receipt.manifest_sha256 == verified.receipt.manifest_sha256


def test_compaction_rejects_duplicate_parent_keys_before_output_mutation(
    tmp_path: Path,
) -> None:
    store, capacity, dataset_ids = compaction_inputs(
        tmp_path,
        parent_count=2,
        duplicate_last=True,
    )
    with pytest.raises(PublicationError, match="duplicate or conflicting"):
        preflight_history_compaction(
            dataset_ids,
            capacity,
            store,
            snapshot(tmp_path, observed_at_ms=2_000),
            now_ms=2_001,
            software_identity=SOFTWARE_IDENTITY,
        )
    assert {path.name for path in (store / "datasets").iterdir()} == set(dataset_ids)


def test_compaction_requires_fragment_reduction_and_fresh_capacity(
    tmp_path: Path,
) -> None:
    store, capacity, dataset_ids = compaction_inputs(tmp_path, parent_count=1)
    with pytest.raises(PublicationError, match="at least two input fragments"):
        preflight_history_compaction(
            dataset_ids,
            capacity,
            store,
            snapshot(tmp_path, observed_at_ms=2_000),
            now_ms=2_001,
            software_identity=SOFTWARE_IDENTITY,
        )

    second = publish_parent(
        tmp_path,
        store,
        index=1,
        open_time_ms=JANUARY_1_2026_MS + 60_000,
    )
    with pytest.raises(PublicationError, match="insufficient free space"):
        preflight_history_compaction(
            (dataset_ids[0], second),
            capacity,
            store,
            snapshot(tmp_path, observed_at_ms=2_010, free_bytes=1),
            now_ms=2_011,
            software_identity=SOFTWARE_IDENTITY,
        )
    assert {path.name for path in (store / "datasets").iterdir()} == {
        dataset_ids[0],
        second,
    }


def test_compaction_rejects_parent_change_after_preflight(
    tmp_path: Path,
) -> None:
    store, capacity, dataset_ids = compaction_inputs(tmp_path, parent_count=2)
    resolved = preflight_history_compaction(
        dataset_ids,
        capacity,
        store,
        snapshot(tmp_path, observed_at_ms=2_000),
        now_ms=2_001,
        software_identity=SOFTWARE_IDENTITY,
    )
    parent = verify_committed_candle_dataset(store / "datasets" / dataset_ids[0])
    parquet = parent.dataset_root / parent.manifest.files[0].path
    with parquet.open("ab") as stream:
        stream.write(b"tamper")
    with pytest.raises(PublicationError, match="hash or size"):
        publish_preflighted_compaction(
            resolved,
            lambda: snapshot(tmp_path, observed_at_ms=2_002),
            lambda: 2_003,
        )
    assert not resolved.plan.paths.dataset_root.exists()


def test_compaction_receipt_failure_leaves_uncommitted_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, capacity, dataset_ids = compaction_inputs(tmp_path, parent_count=2)
    resolved = preflight_history_compaction(
        dataset_ids,
        capacity,
        store,
        snapshot(tmp_path, observed_at_ms=2_000),
        now_ms=2_001,
        software_identity=SOFTWARE_IDENTITY,
    )
    real_replace = os.replace

    def fail_receipt(source: Path, target: Path) -> None:
        if Path(target).name == "completion-receipt.json":
            raise OSError("injected compaction receipt failure")
        real_replace(source, target)

    monkeypatch.setattr("grid_market_store.compaction.os.replace", fail_receipt)
    with pytest.raises(OSError, match="injected compaction receipt"):
        publish_preflighted_compaction(
            resolved,
            lambda: snapshot(tmp_path, observed_at_ms=2_002),
            lambda: 2_003,
        )
    assert resolved.plan.paths.dataset_root.is_dir()
    assert not (resolved.plan.paths.dataset_root / "completion-receipt.json").exists()
    with pytest.raises(PublicationError, match="no completion receipt"):
        verify_committed_candle_dataset(resolved.plan.paths.dataset_root)


def test_compaction_rejects_unsafe_or_duplicate_dataset_id_arguments(tmp_path: Path) -> None:
    with pytest.raises(HistoryCompactionError, match="unsafe"):
        preflight_history_compaction(
            ("../escape",),
            tmp_path / "missing-capacity.json",
            tmp_path / "store",
            snapshot(tmp_path, observed_at_ms=2_000),
            now_ms=2_001,
            software_identity=SOFTWARE_IDENTITY,
        )
    with pytest.raises(HistoryCompactionError, match="unique"):
        preflight_history_compaction(
            ("same-id", "same-id"),
            tmp_path / "missing-capacity.json",
            tmp_path / "store",
            snapshot(tmp_path, observed_at_ms=2_000),
            now_ms=2_001,
            software_identity=SOFTWARE_IDENTITY,
        )
