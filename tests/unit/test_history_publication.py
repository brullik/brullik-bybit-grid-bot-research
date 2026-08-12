from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
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
from grid_data.history_coverage_audit import build_completed_history_coverage_audit
from grid_data.history_pilot_evidence import build_history_pilot_evidence
from grid_data.history_publication import (
    HISTORY_PUBLICATION_CONTRACT,
    history_publication_spec,
    load_verified_history_publication_input,
    preflight_completed_history_publication,
    publish_preflighted_history,
)
from grid_data.instrument_registry import build_instrument_registry
from grid_market_store import (
    MIN_OPERATING_RESERVE_BYTES,
    CanonicalCandleBatch,
    CapacityBudget,
    HostSnapshot,
    preflight_candle_dataset,
    publish_candle_dataset,
)
from jsonschema import Draft202012Validator, FormatChecker

JANUARY_1_2026_MS = 1_767_225_600_000
ACTIVE_BUILDING_BYTES = 90_000_000_000
SOFTWARE_IDENTITY = f"git:{'a' * 40}"
AUDIT_SOFTWARE_IDENTITY = f"git:{'b' * 40}"


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


class SparsePageClient:
    def kline_page(self, **kwargs: object) -> tuple[tuple[str, ...], ...]:
        def row(open_time_ms: object) -> tuple[str, ...]:
            return (
                str(open_time_ms),
                "100.00000001",
                "102",
                "99.5",
                "101",
                "10.5000",
                "1050.000000000001",
            )

        return (row(kwargs["end_ms"]), row(kwargs["start_ms"]))


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


def completed_inputs(
    tmp_path: Path,
    *,
    end_ms: int = JANUARY_1_2026_MS,
    client_factory: type[OnePageClient] | type[SparsePageClient] = OnePageClient,
) -> tuple[Path, Path, Path]:
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
                end_ms=end_ms,
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
        closed_before_ms=end_ms + 60_000,
    )
    completed = execute_history_job(
        history_plan,
        client_factory,
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


def test_verified_publication_builds_sanitized_pilot_evidence(tmp_path: Path) -> None:
    job_root, registry_path, capacity_path = completed_inputs(tmp_path)
    store_root = tmp_path / "market-store"
    initial = preflight_completed_history_publication(
        store_root,
        job_root,
        registry_path,
        capacity_path,
        snapshot(tmp_path, observed_at_ms=2_000),
        now_ms=2_001,
        software_identity=SOFTWARE_IDENTITY,
    )
    with pytest.raises(HistoryAcquisitionError, match="existing immutable commit"):
        build_history_pilot_evidence(
            initial,
            publish_preflighted_history(
                initial,
                lambda: snapshot(tmp_path, observed_at_ms=2_002),
                lambda: 2_003,
            ),
            generated_at_utc="2026-08-12T19:51:08Z",
        )

    rerun = preflight_completed_history_publication(
        store_root,
        job_root,
        registry_path,
        capacity_path,
        snapshot(tmp_path, observed_at_ms=3_000),
        now_ms=3_001,
        software_identity=SOFTWARE_IDENTITY,
    )
    published = publish_preflighted_history(
        rerun,
        lambda: snapshot(tmp_path, observed_at_ms=3_002),
        lambda: 3_003,
    )
    payload = build_history_pilot_evidence(
        rerun,
        published,
        generated_at_utc="2026-08-12T19:51:08Z",
    )
    schema = json.loads(
        (
            Path(__file__).parents[2]
            / "schemas"
            / "evidence"
            / "v1"
            / "phase2-public-1m-pilot.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    embedded_hash = payload.pop("content_sha256")
    assert embedded_hash == canonical_sha256(payload)
    assert payload["scope"] == {
        "category": "linear",
        "exact_requested_coverage": True,
        "interval_minutes": 1,
        "requested_minute_count": 1,
        "series": [
            {
                "end_ms": JANUARY_1_2026_MS,
                "instrument_id": 1,
                "requested_minute_count": 1,
                "start_ms": JANUARY_1_2026_MS,
                "symbol": "AAAUSDT",
            }
        ],
    }
    rendered = json.dumps(payload)
    assert str(tmp_path) not in rendered
    assert "100.00000001" not in rendered


def test_canonical_coverage_audit_passes_exact_source_parity(tmp_path: Path) -> None:
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
    publish_preflighted_history(
        resolved,
        lambda: snapshot(tmp_path, observed_at_ms=2_002),
        lambda: 2_003,
    )

    audit = build_completed_history_coverage_audit(
        job_root,
        registry_path,
        capacity_path,
        store_root,
        publisher_software_identity=SOFTWARE_IDENTITY,
        audit_software_identity=AUDIT_SOFTWARE_IDENTITY,
        generated_at_utc="2026-08-12T20:03:32Z",
    )

    assert audit.passed is True
    assert audit.payload["status"] == "passed"
    assert audit.payload["quality"] == {
        "canonical_source_table_equal": True,
        "conflicting_key_count": 0,
        "duplicate_key_count": 0,
        "expected_minute_count": 1,
        "lifecycle_failure_count": 0,
        "missing_minute_count": 0,
        "observed_row_count": 1,
        "unrequested_row_count": 0,
        "unexpected_timestamp_count": 0,
    }
    schema = json.loads(
        (
            Path(__file__).parents[2]
            / "schemas"
            / "evidence"
            / "v1"
            / "canonical-1m-coverage-audit.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(audit.payload)


def test_canonical_coverage_audit_blocks_rest_returned_gap(tmp_path: Path) -> None:
    job_root, registry_path, capacity_path = completed_inputs(
        tmp_path,
        end_ms=JANUARY_1_2026_MS + 2 * 60_000,
        client_factory=SparsePageClient,
    )
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
    publish_preflighted_history(
        resolved,
        lambda: snapshot(tmp_path, observed_at_ms=2_002),
        lambda: 2_003,
    )

    audit = build_completed_history_coverage_audit(
        job_root,
        registry_path,
        capacity_path,
        store_root,
        publisher_software_identity=SOFTWARE_IDENTITY,
        audit_software_identity=AUDIT_SOFTWARE_IDENTITY,
        generated_at_utc="2026-08-12T20:03:32Z",
    )

    assert audit.passed is False
    assert audit.payload["status"] == "blocked"
    assert audit.payload["reason_policy"] == {
        "accepted_reason_codes": [],
        "observed_reason_counts": {"rest_returned_no_data": 1},
        "unaccepted_reason_codes": ["rest_returned_no_data"],
        "unknown_reason_count": 0,
    }
    gap_evidence = audit.payload["gap_evidence"]
    assert isinstance(gap_evidence, dict)
    assert gap_evidence["sample_ranges"] == [
        {
            "end_ms": JANUARY_1_2026_MS + 60_000,
            "instrument_id": 1,
            "minute_count": 1,
            "start_ms": JANUARY_1_2026_MS + 60_000,
        }
    ]


def test_canonical_coverage_audit_blocks_source_value_mismatch(tmp_path: Path) -> None:
    job_root, registry_path, capacity_path = completed_inputs(tmp_path)
    store_root = tmp_path / "market-store"
    verified = load_verified_history_publication_input(
        job_root,
        registry_path,
        capacity_path,
    )
    close_index = verified.batch.table.schema.get_field_index("close")
    changed_table = verified.batch.table.set_column(
        close_index,
        verified.batch.table.schema.field(close_index),
        pa.array([10_050_000_000], type=pa.int64()),
    )
    changed_batch = CanonicalCandleBatch(
        dataset_type=verified.batch.dataset_type,
        partition_path=verified.batch.partition_path,
        table=changed_table,
    )
    plan = preflight_candle_dataset(
        store_root,
        history_publication_spec(verified, software_identity=SOFTWARE_IDENTITY),
        changed_batch,
        verified.budget,
        snapshot(tmp_path, observed_at_ms=2_000),
        now_ms=2_001,
    )
    publish_candle_dataset(
        plan,
        snapshot(tmp_path, observed_at_ms=2_002),
        committed_at_ms=2_003,
    )

    audit = build_completed_history_coverage_audit(
        job_root,
        registry_path,
        capacity_path,
        store_root,
        publisher_software_identity=SOFTWARE_IDENTITY,
        audit_software_identity=AUDIT_SOFTWARE_IDENTITY,
        generated_at_utc="2026-08-12T20:03:32Z",
    )

    assert audit.passed is False
    quality = audit.payload["quality"]
    assert isinstance(quality, dict)
    assert quality["canonical_source_table_equal"] is False
