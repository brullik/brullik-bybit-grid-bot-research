from __future__ import annotations

from pathlib import Path

import pytest
from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_data.evidence import publish_evidence
from grid_data.history_acquisition import (
    MAX_PAGE_ARTIFACT_BYTES,
    STAGING_METADATA_BYTES,
    HistoryAcquisitionError,
    HistoryJobSpec,
    HistorySeries,
    execute_history_job,
    preflight_history_job,
)
from grid_data.history_publication import (
    HISTORY_PUBLICATION_CONTRACT,
    preflight_completed_history_publication,
    publish_preflighted_history,
)
from grid_data.instrument_registry import build_instrument_registry
from grid_market_store import MIN_OPERATING_RESERVE_BYTES, CapacityBudget, HostSnapshot

JANUARY_1_2026_MS = 1_767_225_600_000
ACTIVE_BUILDING_BYTES = 90_000_000_000
SOFTWARE_IDENTITY = f"git:{'a' * 40}"


class OnePageClient:
    def kline_page(self, **kwargs: object) -> tuple[tuple[str, ...], ...]:
        return (
            (
                str(kwargs["start_ms"]),
                "100.00000001",
                "102",
                "99.5",
                "101",
                "10.5000",
                "1050.000000000001",
            ),
        )


def snapshot(root: Path, *, observed_at_ms: int = 1_000) -> HostSnapshot:
    return HostSnapshot(
        observed_at_ms=observed_at_ms,
        memory_total_bytes=16 * 1024**3,
        memory_available_bytes=8 * 1024**3,
        storage_kind="nvme",
        storage_device_id="fixture-nvme",
        volume_root=root.resolve(),
        volume_free_bytes=200 * 1024**3,
    )


def inventory_payload(source_symbol_id: int = 1) -> dict[str, object]:
    inventory: dict[str, object] = {
        "evidence_schema": "grid.bybit-public-inventory/v1",
        "fetched_at_utc": "2026-08-12T12:36:49Z",
        "inventory_status": "partial",
        "records": [
            {
                "base_coin": "AAA",
                "contract_type": "LinearPerpetual",
                "delivery_time_ms": 0,
                "funding_interval_minutes": 480,
                "launch_time_ms": 1_600_000_000_000,
                "max_leverage": "100",
                "max_order_quantity": "1000000",
                "min_leverage": "1",
                "min_order_quantity": "0.001",
                "quantity_step": "0.001",
                "quote_coin": "USDT",
                "settle_coin": "USDT",
                "source_payload_sha256": f"{source_symbol_id:064x}",
                "source_symbol_id": source_symbol_id,
                "status": "Trading",
                "symbol": "AAAUSDT",
                "tick_size": "0.0001",
            }
        ],
    }
    inventory["content_sha256"] = canonical_sha256(inventory)
    return inventory


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


def completed_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    registry_payload = build_instrument_registry(
        inventory_payload(), inventory_artifact_sha256="a" * 64
    )
    registry_path, _ = publish_evidence(tmp_path / "registry.json", registry_payload)
    capacity_path, _ = publish_evidence(tmp_path / "capacity.json", capacity_payload())
    spec = HistoryJobSpec(
        job_id="trade-2026-01-b01-publication",
        series=(
            HistorySeries(
                kind="trade",
                category="linear",
                symbol="AAAUSDT",
                instrument_id=1,
                start_ms=JANUARY_1_2026_MS,
                end_ms=JANUARY_1_2026_MS,
            ),
        ),
        request_sha256="c" * 64,
        instrument_evidence_sha256=sha256_file(registry_path),
        capacity_evidence_sha256=sha256_file(capacity_path),
        workers=1,
        target_rps=96,
        max_attempts=1,
        max_http_requests=1,
    )
    budget = CapacityBudget(
        active_and_building_bytes=ACTIVE_BUILDING_BYTES,
        rest_staging_bytes=STAGING_METADATA_BYTES + MAX_PAGE_ARTIFACT_BYTES,
        operating_reserve_bytes=MIN_OPERATING_RESERVE_BYTES,
    )
    history_plan = preflight_history_job(
        tmp_path / "history",
        spec,
        budget,
        snapshot(tmp_path),
        now_ms=1_001,
        closed_before_ms=JANUARY_1_2026_MS + 60_000,
    )
    completed = execute_history_job(
        history_plan,
        OnePageClient,
        lambda: snapshot(tmp_path, observed_at_ms=1_002),
        now_ms=lambda: 1_003,
    )
    return completed.job_root, registry_path, capacity_path


def test_landing_preflight_publishes_canonical_dataset_and_reruns_idempotently(
    tmp_path: Path,
) -> None:
    job_root, registry_path, capacity_path = completed_inputs(tmp_path)
    store_root = tmp_path / "market-store"
    resolved = preflight_completed_history_publication(
        store_root,
        job_root,
        registry_path,
        capacity_path,
        snapshot(tmp_path, observed_at_ms=2_000),
        now_ms=2_001,
        software_identity=SOFTWARE_IDENTITY,
    )

    assert not store_root.exists()
    assert resolved.plan.spec.dataset_id.startswith("trade-1m-")
    assert resolved.plan.spec.coverage_evidence_sha256 == (
        resolved.completed_history.manifest_sha256
    )
    assert resolved.plan.spec.build_config_sha256 == canonical_sha256(
        {
            "canonical_layout": "grid.canonical-candle-layout/v1",
            "contract": HISTORY_PUBLICATION_CONTRACT,
            "dataset_id": resolved.plan.spec.dataset_id,
            "history_manifest_sha256": resolved.completed_history.manifest_sha256,
            "semantic_version": "1.0.0",
            "software_identity": SOFTWARE_IDENTITY,
        }
    )
    events: list[str] = []

    def fresh_snapshot() -> HostSnapshot:
        events.append("snapshot")
        return snapshot(tmp_path, observed_at_ms=2_002)

    def current_time() -> int:
        events.append("now")
        return 2_003

    published = publish_preflighted_history(resolved, fresh_snapshot, current_time)
    assert events == ["snapshot", "now"]
    assert published.manifest.row_count == 1
    assert published.manifest.instrument_count == 1
    assert published.receipt_path.is_file()

    rerun = preflight_completed_history_publication(
        store_root,
        job_root,
        registry_path,
        capacity_path,
        snapshot(tmp_path, observed_at_ms=3_000),
        now_ms=3_001,
        software_identity=SOFTWARE_IDENTITY,
    )
    assert rerun.plan.existing_commit is True
    same = publish_preflighted_history(
        rerun,
        lambda: snapshot(tmp_path, observed_at_ms=3_002),
        lambda: 3_003,
    )
    assert same.receipt.manifest_sha256 == published.receipt.manifest_sha256


def test_publication_rejects_different_registry_or_capacity_binding(tmp_path: Path) -> None:
    job_root, registry_path, capacity_path = completed_inputs(tmp_path)
    wrong_registry_payload = build_instrument_registry(
        inventory_payload(source_symbol_id=9), inventory_artifact_sha256="d" * 64
    )
    wrong_registry, _ = publish_evidence(tmp_path / "wrong-registry.json", wrong_registry_payload)
    with pytest.raises(HistoryAcquisitionError, match="supplied registry"):
        preflight_completed_history_publication(
            tmp_path / "store",
            job_root,
            wrong_registry,
            capacity_path,
            snapshot(tmp_path, observed_at_ms=2_000),
            now_ms=2_001,
            software_identity=SOFTWARE_IDENTITY,
        )

    wrong_capacity = capacity_payload()
    wrong_capacity["extra"] = "changes-artifact-hash"
    wrong_capacity_path, _ = publish_evidence(tmp_path / "wrong-capacity.json", wrong_capacity)
    with pytest.raises(HistoryAcquisitionError, match="capacity evidence"):
        preflight_completed_history_publication(
            tmp_path / "store",
            job_root,
            registry_path,
            wrong_capacity_path,
            snapshot(tmp_path, observed_at_ms=2_000),
            now_ms=2_001,
            software_identity=SOFTWARE_IDENTITY,
        )


def test_publication_requires_immutable_git_commit_identity(tmp_path: Path) -> None:
    job_root, registry_path, capacity_path = completed_inputs(tmp_path)

    with pytest.raises(HistoryAcquisitionError, match="40-character-lowercase-commit-sha"):
        preflight_completed_history_publication(
            tmp_path / "store",
            job_root,
            registry_path,
            capacity_path,
            snapshot(tmp_path, observed_at_ms=2_000),
            now_ms=2_001,
            software_identity="worktree:uncommitted",
        )
