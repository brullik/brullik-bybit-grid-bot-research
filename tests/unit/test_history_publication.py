from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pytest
from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file
from grid_data.evidence import publish_evidence
from grid_data.history_acquisition import (
    MAX_PAGE_ARTIFACT_BYTES,
    STAGING_METADATA_BYTES,
    HistoryAcquisitionError,
    HistoryJobSpec,
    HistorySeries,
    execute_history_job,
    load_completed_history_batch,
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
from grid_data.history_repair_plan import build_gap_repair_plan
from grid_data.history_request import resolve_history_request
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
PLANNER_SOFTWARE_IDENTITY = f"git:{'c' * 40}"


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


class QuarantinedPageClient:
    def kline_page(self, **kwargs: object) -> tuple[tuple[str, ...], ...]:
        def row(open_time_ms: object, open_price: str) -> tuple[str, ...]:
            return (
                str(open_time_ms),
                open_price,
                "102",
                "99.5",
                "101",
                "10.5000",
                "1050.000000000001",
            )

        return (
            row(kwargs["end_ms"], "100.00000001"),
            row(kwargs["start_ms"], "103"),
        )


class AllQuarantinedPageClient:
    def kline_page(self, **kwargs: object) -> tuple[tuple[str, ...], ...]:
        return (
            (
                str(kwargs["start_ms"]),
                "103",
                "102",
                "99.5",
                "101",
                "10.5000",
                "1050.000000000001",
            ),
        )


class OverScaleVolumePageClient:
    def kline_page(self, **kwargs: object) -> tuple[tuple[str, ...], ...]:
        return (
            (
                str(kwargs["start_ms"]),
                "100.00000001",
                "102",
                "99.5",
                "101",
                "10.50001",
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


def completed_inputs(
    tmp_path: Path,
    *,
    end_ms: int = JANUARY_1_2026_MS,
    client_factory: (
        type[OnePageClient]
        | type[SparsePageClient]
        | type[QuarantinedPageClient]
        | type[AllQuarantinedPageClient]
        | type[OverScaleVolumePageClient]
    ) = OnePageClient,
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


def test_canonical_coverage_audit_separates_quarantine_from_repairable_gap(
    tmp_path: Path,
) -> None:
    job_root, registry_path, capacity_path = completed_inputs(
        tmp_path,
        end_ms=JANUARY_1_2026_MS + 60_000,
        client_factory=QuarantinedPageClient,
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
        generated_at_utc="2026-08-13T22:00:00Z",
    )

    assert audit.passed is False
    assert audit.payload["reason_policy"] == {
        "accepted_reason_codes": [],
        "observed_reason_counts": {"quarantined_source_row": 1},
        "unaccepted_reason_codes": ["quarantined_source_row"],
        "unknown_reason_count": 0,
    }
    gap_evidence = audit.payload["gap_evidence"]
    assert isinstance(gap_evidence, dict)
    assert gap_evidence["sample_ranges"] == [
        {
            "end_ms": JANUARY_1_2026_MS,
            "instrument_id": 1,
            "minute_count": 1,
            "start_ms": JANUARY_1_2026_MS,
        }
    ]
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

    audit_path, _ = publish_evidence(tmp_path / "quarantined-audit.json", audit.payload)
    with pytest.raises(HistoryAcquisitionError, match="not repair-plan compatible"):
        build_gap_repair_plan(
            audit_path,
            job_root,
            registry_path,
            capacity_path,
            store_root,
            generated_at_utc="2026-08-13T22:01:00Z",
            planner_software_identity=PLANNER_SOFTWARE_IDENTITY,
        )


def test_all_quarantined_source_partition_publishes_empty_and_stays_blocked(
    tmp_path: Path,
) -> None:
    job_root, registry_path, capacity_path = completed_inputs(
        tmp_path,
        client_factory=AllQuarantinedPageClient,
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
    assert resolved.completed_history.row_count == 0
    assert resolved.completed_history.quarantined_row_count == 1
    assert resolved.plan.batch.table.num_rows == 0

    published = publish_preflighted_history(
        resolved,
        lambda: snapshot(tmp_path, observed_at_ms=2_002),
        lambda: 2_003,
    )
    assert published.manifest.row_count == 0

    audit = build_completed_history_coverage_audit(
        job_root,
        registry_path,
        capacity_path,
        store_root,
        publisher_software_identity=SOFTWARE_IDENTITY,
        audit_software_identity=AUDIT_SOFTWARE_IDENTITY,
        generated_at_utc="2026-08-14T05:30:00Z",
    )
    assert audit.passed is False
    assert audit.payload["reason_policy"] == {
        "accepted_reason_codes": [],
        "observed_reason_counts": {"quarantined_source_row": 1},
        "unaccepted_reason_codes": ["quarantined_source_row"],
        "unknown_reason_count": 0,
    }
    assert audit.payload["quality"]["observed_row_count"] == 0
    assert audit.payload["quality"]["missing_minute_count"] == 1


def test_over_scale_volume_is_bound_excluded_and_not_repairable(tmp_path: Path) -> None:
    job_root, registry_path, capacity_path = completed_inputs(
        tmp_path,
        client_factory=OverScaleVolumePageClient,
    )
    with pytest.raises(HistoryAcquisitionError, match="do not form one canonical batch"):
        load_completed_history_batch(job_root)
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

    admission = resolved.canonical_admission
    assert admission.source_row_count == 1
    assert admission.admitted_row_count == 0
    assert admission.excluded_row_count == 1
    assert admission.reason_counts == {"volume_exceeds_canonical_scale": 1}
    assert len(admission.excluded_rows_sha256) == 64
    assert resolved.plan.batch.table.num_rows == 0
    assert resolved.plan.spec.source_evidence_sha256[-1] == admission.excluded_rows_sha256

    published = publish_preflighted_history(
        resolved,
        lambda: snapshot(tmp_path, observed_at_ms=2_002),
        lambda: 2_003,
    )
    assert published.manifest.row_count == 0

    audit = build_completed_history_coverage_audit(
        job_root,
        registry_path,
        capacity_path,
        store_root,
        publisher_software_identity=SOFTWARE_IDENTITY,
        audit_software_identity=AUDIT_SOFTWARE_IDENTITY,
        generated_at_utc="2026-08-14T06:00:00Z",
    )
    assert audit.passed is False
    assert audit.payload["reason_policy"] == {
        "accepted_reason_codes": [],
        "observed_reason_counts": {"canonical_representation_overflow": 1},
        "unaccepted_reason_codes": ["canonical_representation_overflow"],
        "unknown_reason_count": 0,
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

    audit_path, _ = publish_evidence(tmp_path / "representation-audit.json", audit.payload)
    with pytest.raises(HistoryAcquisitionError, match="not repair-plan compatible"):
        build_gap_repair_plan(
            audit_path,
            job_root,
            registry_path,
            capacity_path,
            store_root,
            generated_at_utc="2026-08-14T06:01:00Z",
            planner_software_identity=PLANNER_SOFTWARE_IDENTITY,
        )


def test_canonical_coverage_audit_does_not_double_count_quarantined_missing_minute(
    tmp_path: Path,
) -> None:
    job_root, registry_path, capacity_path = completed_inputs(
        tmp_path,
        end_ms=JANUARY_1_2026_MS + 2 * 60_000,
        client_factory=QuarantinedPageClient,
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
        generated_at_utc="2026-08-13T22:02:00Z",
    )

    assert audit.payload["reason_policy"] == {
        "accepted_reason_codes": [],
        "observed_reason_counts": {
            "quarantined_source_row": 1,
            "rest_returned_no_data": 1,
        },
        "unaccepted_reason_codes": [
            "quarantined_source_row",
            "rest_returned_no_data",
        ],
        "unknown_reason_count": 0,
    }
    quality = audit.payload["quality"]
    assert isinstance(quality, dict)
    assert quality["missing_minute_count"] == 2


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


def test_gap_repair_plan_embeds_exact_standard_history_request(tmp_path: Path) -> None:
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
    audit_path, _ = publish_evidence(tmp_path / "blocked-audit.json", audit.payload)

    plan = build_gap_repair_plan(
        audit_path,
        job_root,
        registry_path,
        capacity_path,
        store_root,
        generated_at_utc="2026-08-12T20:04:00Z",
        planner_software_identity=PLANNER_SOFTWARE_IDENTITY,
    )

    assert plan.task_count == 1
    assert plan.planned_max_http_requests == 1
    assert plan.payload["planner_software_identity"] == PLANNER_SOFTWARE_IDENTITY
    tasks = plan.payload["tasks"]
    assert isinstance(tasks, list)
    task = tasks[0]
    assert isinstance(task, dict)
    assert task["minute_count"] == 1
    request = task["request"]
    assert isinstance(request, dict)
    assert request == {
        "contract": "grid.bybit-1m-history-request/v1",
        "job_id": request["job_id"],
        "kind": "trade",
        "max_attempts": 1,
        "max_http_requests": 1,
        "page_limit": 1000,
        "series": [
            {
                "end_ms": JANUARY_1_2026_MS + 60_000,
                "start_ms": JANUARY_1_2026_MS + 60_000,
                "symbol": "AAAUSDT",
            }
        ],
        "target_rps": 96,
        "workers": 1,
    }
    schema = json.loads(
        (
            Path(__file__).parents[2]
            / "schemas"
            / "evidence"
            / "v1"
            / "bybit-1m-gap-repair-plan.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(plan.payload)
    hash_input = dict(plan.payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == canonical_sha256(hash_input)
    repair_request_path = tmp_path / "repair-request.json"
    repair_request_path.write_bytes(canonical_json_bytes(request) + b"\n")
    resolved_repair = resolve_history_request(
        repair_request_path,
        instrument_registry_path=registry_path,
        capacity_evidence_path=capacity_path,
    )
    assert resolved_repair.request_sha256 == task["request_sha256"]
    assert resolved_repair.spec.series[0].start_ms == JANUARY_1_2026_MS + 60_000


def test_gap_repair_plan_rejects_passing_audit(tmp_path: Path) -> None:
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
    audit_path, _ = publish_evidence(tmp_path / "passing-audit.json", audit.payload)

    with pytest.raises(HistoryAcquisitionError, match="requires a blocked"):
        build_gap_repair_plan(
            audit_path,
            job_root,
            registry_path,
            capacity_path,
            store_root,
            generated_at_utc="2026-08-12T20:04:00Z",
            planner_software_identity=PLANNER_SOFTWARE_IDENTITY,
        )


def test_gap_repair_plan_requires_full_git_identity(tmp_path: Path) -> None:
    with pytest.raises(HistoryAcquisitionError, match="planner_software_identity"):
        build_gap_repair_plan(
            tmp_path / "not-read.json",
            tmp_path / "not-read-job",
            tmp_path / "not-read-registry.json",
            tmp_path / "not-read-capacity.json",
            tmp_path / "not-read-store",
            generated_at_utc="2026-08-12T20:04:00Z",
            planner_software_identity="worktree:uncommitted",
        )
