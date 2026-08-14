from __future__ import annotations

import json
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
from grid_data.history_coverage_audit import build_completed_history_coverage_audit
from grid_data.history_publication import (
    preflight_completed_history_publication,
    publish_preflighted_history,
)
from grid_data.history_repair_execution import (
    execute_gap_repair,
    preflight_gap_repair_execution,
    verify_gap_repair_execution,
)
from grid_data.history_repair_plan import build_gap_repair_plan
from grid_data.history_repair_public_evidence import (
    build_candle_repair_execution_public_evidence,
    verify_candle_repair_execution_public_evidence,
)
from grid_data.history_repair_publication import (
    build_gap_replacement_evidence,
    preflight_repaired_history_publication,
    publish_preflighted_repair,
    verify_gap_replacement_evidence,
)
from grid_data.instrument_registry import build_instrument_registry
from grid_market_store import (
    MIN_OPERATING_RESERVE_BYTES,
    CapacityBudget,
    HostSnapshot,
    verify_committed_candle_dataset,
)
from jsonschema import Draft202012Validator, FormatChecker

JANUARY_1_2026_MS = 1_767_225_600_000
ACTIVE_BUILDING_BYTES = 90_000_000_000
PUBLISHER_IDENTITY = f"git:{'a' * 40}"
AUDITOR_IDENTITY = f"git:{'b' * 40}"
PLANNER_IDENTITY = f"git:{'c' * 40}"
EXECUTOR_IDENTITY = f"git:{'d' * 40}"
REPLACEMENT_IDENTITY = f"git:{'e' * 40}"
ROOT = Path(__file__).parents[2]


def _row(open_time_ms: object) -> tuple[str, ...]:
    return (
        str(open_time_ms),
        "100.00000001",
        "102",
        "99.5",
        "101",
        "10.5000",
        "1050.000000000001",
    )


class SparseOriginalClient:
    def kline_page(self, **kwargs: object) -> tuple[tuple[str, ...], ...]:
        return (_row(kwargs["end_ms"]), _row(kwargs["start_ms"]))


class TwoGapOriginalClient:
    def kline_page(self, **kwargs: object) -> tuple[tuple[str, ...], ...]:
        start_ms = int(str(kwargs["start_ms"]))
        end_ms = int(str(kwargs["end_ms"]))
        return (_row(end_ms), _row(start_ms + 2 * 60_000), _row(start_ms))


class ExactRepairClient:
    def kline_page(self, **kwargs: object) -> tuple[tuple[str, ...], ...]:
        return (_row(kwargs["start_ms"]),)


class EmptyRepairClient:
    def kline_page(self, **_kwargs: object) -> tuple[tuple[str, ...], ...]:
        return ()


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


def inventory_payload() -> dict[str, object]:
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
                "source_payload_sha256": "1" * 64,
                "source_symbol_id": 1,
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


def blocked_repair_inputs(
    tmp_path: Path,
    *,
    end_ms: int = JANUARY_1_2026_MS + 2 * 60_000,
    original_client_factory: type[SparseOriginalClient]
    | type[TwoGapOriginalClient] = SparseOriginalClient,
) -> tuple[Path, Path, Path, Path, Path, Path]:
    registry = build_instrument_registry(inventory_payload(), inventory_artifact_sha256="a" * 64)
    registry_path, _ = publish_evidence(tmp_path / "registry.json", registry)
    capacity_path, _ = publish_evidence(tmp_path / "capacity.json", capacity_payload())
    spec = HistoryJobSpec(
        job_id="trade-2026-01-b01-repair-fixture",
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
    acquisition = preflight_history_job(
        tmp_path / "history",
        spec,
        budget,
        snapshot(tmp_path, observed_at_ms=1_000),
        now_ms=1_001,
        closed_before_ms=end_ms + 60_000,
    )
    completed = execute_history_job(
        acquisition,
        original_client_factory,
        lambda: snapshot(tmp_path, observed_at_ms=1_002),
        now_ms=lambda: 1_003,
    )
    store_root = tmp_path / "market-store"
    parent_plan = preflight_completed_history_publication(
        store_root,
        completed.job_root,
        registry_path,
        capacity_path,
        snapshot(tmp_path, observed_at_ms=2_000),
        now_ms=2_001,
        software_identity=PUBLISHER_IDENTITY,
    )
    publish_preflighted_history(
        parent_plan,
        lambda: snapshot(tmp_path, observed_at_ms=2_002),
        lambda: 2_003,
    )
    audit = build_completed_history_coverage_audit(
        completed.job_root,
        registry_path,
        capacity_path,
        store_root,
        publisher_software_identity=PUBLISHER_IDENTITY,
        audit_software_identity=AUDITOR_IDENTITY,
        generated_at_utc="2026-08-12T20:03:32Z",
    )
    assert audit.passed is False
    audit_path, _ = publish_evidence(tmp_path / "blocked-audit.json", audit.payload)
    repair_plan = build_gap_repair_plan(
        audit_path,
        completed.job_root,
        registry_path,
        capacity_path,
        store_root,
        generated_at_utc="2026-08-12T20:04:00Z",
        planner_software_identity=PLANNER_IDENTITY,
    )
    plan_path, _ = publish_evidence(tmp_path / "repair-plan.json", repair_plan.payload)
    return (
        completed.job_root,
        registry_path,
        capacity_path,
        store_root,
        audit_path,
        plan_path,
    )


def execute_repair_fixture(
    tmp_path: Path,
    *,
    client_factory: type[ExactRepairClient] | type[EmptyRepairClient],
):
    job_root, registry, capacity, store, audit, repair_plan = blocked_repair_inputs(tmp_path)
    repair_staging = tmp_path / "repair-history"
    preflight = preflight_gap_repair_execution(
        repair_plan,
        audit,
        job_root,
        registry,
        capacity,
        store,
        repair_staging,
        snapshot(tmp_path, observed_at_ms=3_000),
        now_ms=3_001,
        closed_before_ms=JANUARY_1_2026_MS + 3 * 60_000,
        executor_software_identity=EXECUTOR_IDENTITY,
    )
    assert not repair_staging.exists()
    result = execute_gap_repair(
        preflight,
        client_factory,
        lambda: snapshot(tmp_path, observed_at_ms=3_002),
        generated_at_utc="2026-08-12T20:05:00Z",
        executor_software_identity=EXECUTOR_IDENTITY,
        now_ms=lambda: 3_003,
    )
    execution_path, _ = publish_evidence(tmp_path / "repair-execution.json", result.payload)
    return (
        result,
        execution_path,
        repair_plan,
        audit,
        job_root,
        registry,
        capacity,
        store,
        repair_staging,
    )


def test_repair_execution_and_replacement_are_receipted_exact_and_idempotent(
    tmp_path: Path,
) -> None:
    (
        result,
        execution_path,
        repair_plan,
        audit,
        job_root,
        registry,
        capacity,
        store,
        repair_staging,
    ) = execute_repair_fixture(tmp_path, client_factory=ExactRepairClient)
    assert result.passed is True
    assert result.payload["status"] == "passed"
    execution_schema = json.loads(
        (ROOT / "schemas/evidence/v1/bybit-1m-gap-repair-execution.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(execution_schema, format_checker=FormatChecker()).validate(result.payload)
    verified_execution = verify_gap_repair_execution(
        execution_path,
        repair_plan,
        audit,
        job_root,
        registry,
        capacity,
        store,
        repair_staging,
    )
    assert verified_execution.passed is True

    parent_id = str(result.payload["dataset_id"])
    parent = verify_committed_candle_dataset(store / "datasets" / parent_id)
    parent_manifest_before = sha256_file(parent.manifest_path)
    parent_file_before = sha256_file(parent.dataset_root / parent.manifest.files[0].path)
    resolved = preflight_repaired_history_publication(
        execution_path,
        repair_plan,
        audit,
        job_root,
        registry,
        capacity,
        store,
        repair_staging,
        snapshot(tmp_path, observed_at_ms=4_000),
        now_ms=4_001,
        software_identity=REPLACEMENT_IDENTITY,
    )
    assert resolved.plan.existing_commit is False
    assert resolved.parent_row_count == 2
    assert resolved.repaired_row_count == 1
    assert resolved.expected_minute_count == 3
    published = publish_preflighted_repair(
        resolved,
        lambda: snapshot(tmp_path, observed_at_ms=4_002),
        lambda: 4_003,
    )
    assert published.manifest.parent_dataset_ids == (parent_id,)
    assert published.manifest.row_count == 3
    assert published.manifest.dataset_id != parent_id
    assert sha256_file(parent.manifest_path) == parent_manifest_before
    assert sha256_file(parent.dataset_root / parent.manifest.files[0].path) == parent_file_before

    replacement_payload = build_gap_replacement_evidence(
        resolved,
        published,
        generated_at_utc="2026-08-12T20:06:00Z",
    )
    replacement_path, _ = publish_evidence(
        tmp_path / "repair-replacement.json", replacement_payload
    )
    replacement_schema = json.loads(
        (ROOT / "schemas/evidence/v1/canonical-1m-gap-replacement.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(replacement_schema, format_checker=FormatChecker()).validate(
        replacement_payload
    )
    assert (
        verify_gap_replacement_evidence(
            replacement_path,
            resolved,
            published,
        )
        == replacement_payload
    )

    rerun = preflight_repaired_history_publication(
        execution_path,
        repair_plan,
        audit,
        job_root,
        registry,
        capacity,
        store,
        repair_staging,
        snapshot(tmp_path, observed_at_ms=5_000),
        now_ms=5_001,
        software_identity=REPLACEMENT_IDENTITY,
    )
    assert rerun.plan.existing_commit is True
    same = publish_preflighted_repair(
        rerun,
        lambda: snapshot(tmp_path, observed_at_ms=5_002),
        lambda: 5_003,
    )
    assert same.receipt.manifest_sha256 == published.receipt.manifest_sha256


def test_empty_repair_execution_is_preserved_as_blocked_and_cannot_publish(
    tmp_path: Path,
) -> None:
    (
        result,
        execution_path,
        repair_plan,
        audit,
        job_root,
        registry,
        capacity,
        store,
        repair_staging,
    ) = execute_repair_fixture(tmp_path, client_factory=EmptyRepairClient)
    assert result.passed is False
    assert result.payload["status"] == "blocked"
    assert result.payload["limits"] == {
        "actual_http_requests": 1,
        "missing_minute_count": 1,
        "observed_row_count": 0,
        "planned_max_http_requests": 1,
        "task_count": 1,
        "total_missing_minutes": 1,
    }
    with pytest.raises(HistoryAcquisitionError, match="requires a passed repair execution"):
        preflight_repaired_history_publication(
            execution_path,
            repair_plan,
            audit,
            job_root,
            registry,
            capacity,
            store,
            repair_staging,
            snapshot(tmp_path, observed_at_ms=4_000),
            now_ms=4_001,
            software_identity=REPLACEMENT_IDENTITY,
        )


@pytest.mark.parametrize(
    ("client_factory", "expected_status", "expected_classification"),
    [
        (ExactRepairClient, "passed", "exact-gap-repair-completed"),
        (EmptyRepairClient, "blocked", "source-gap-remains"),
    ],
)
def test_repair_execution_public_projection_is_receipted_and_identifier_free(
    tmp_path: Path,
    client_factory: type[ExactRepairClient] | type[EmptyRepairClient],
    expected_status: str,
    expected_classification: str,
) -> None:
    (
        result,
        execution_path,
        repair_plan,
        audit,
        job_root,
        registry,
        capacity,
        store,
        repair_staging,
    ) = execute_repair_fixture(tmp_path, client_factory=client_factory)
    verified = verify_gap_repair_execution(
        execution_path,
        repair_plan,
        audit,
        job_root,
        registry,
        capacity,
        store,
        repair_staging,
    )
    payload = build_candle_repair_execution_public_evidence(
        verified,
        generated_at_utc="2026-08-14T10:00:00Z",
    )
    schema = json.loads(
        (ROOT / "schemas/evidence/v1/bybit-1m-gap-repair-execution-public.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    rendered = json.dumps(payload, sort_keys=True)
    private_task = result.payload["tasks"][0]
    assert "AAAUSDT" not in rendered
    assert str(private_task["start_ms"]) not in rendered
    assert '"instrument_id"' not in rendered
    assert '"dataset_id"' not in rendered
    assert "tasks" not in payload
    assert payload["status"] == expected_status
    assert payload["outcome"]["classification"] == expected_classification
    assert payload["storage_policy"]["github_commit_eligible"] is True

    public_path, _ = publish_evidence(tmp_path / "repair-execution-public.json", payload)
    assert verify_candle_repair_execution_public_evidence(public_path, verified) == payload


def test_repair_execution_rejects_a_substituted_plan_before_landing_mutation(
    tmp_path: Path,
) -> None:
    job_root, registry, capacity, store, audit, repair_plan = blocked_repair_inputs(tmp_path)
    plan_payload = json.loads(repair_plan.read_text(encoding="utf-8"))
    plan_payload["planner_software_identity"] = f"git:{'f' * 40}"
    substituted, _ = publish_evidence(tmp_path / "substituted-plan.json", plan_payload)
    repair_staging = tmp_path / "repair-history"
    with pytest.raises(HistoryAcquisitionError, match="content hash is invalid"):
        preflight_gap_repair_execution(
            substituted,
            audit,
            job_root,
            registry,
            capacity,
            store,
            repair_staging,
            snapshot(tmp_path, observed_at_ms=3_000),
            now_ms=3_001,
            closed_before_ms=JANUARY_1_2026_MS + 3 * 60_000,
            executor_software_identity=EXECUTOR_IDENTITY,
        )
    assert not repair_staging.exists()


def test_repair_preflight_reserves_all_remaining_gap_jobs(tmp_path: Path) -> None:
    job_root, registry, capacity, store, audit, repair_plan = blocked_repair_inputs(
        tmp_path,
        end_ms=JANUARY_1_2026_MS + 4 * 60_000,
        original_client_factory=TwoGapOriginalClient,
    )
    repair_staging = tmp_path / "repair-history"
    per_task_staging = STAGING_METADATA_BYTES + MAX_PAGE_ARTIFACT_BYTES
    expected_required = ACTIVE_BUILDING_BYTES + MIN_OPERATING_RESERVE_BYTES + 2 * per_task_staging
    with pytest.raises(HistoryAcquisitionError, match="complete remaining repair plan"):
        preflight_gap_repair_execution(
            repair_plan,
            audit,
            job_root,
            registry,
            capacity,
            store,
            repair_staging,
            snapshot(
                tmp_path,
                observed_at_ms=3_000,
                free_bytes=expected_required - 1,
            ),
            now_ms=3_001,
            closed_before_ms=JANUARY_1_2026_MS + 5 * 60_000,
            executor_software_identity=EXECUTOR_IDENTITY,
        )
    assert not repair_staging.exists()

    preflight = preflight_gap_repair_execution(
        repair_plan,
        audit,
        job_root,
        registry,
        capacity,
        store,
        repair_staging,
        snapshot(tmp_path, observed_at_ms=3_000),
        now_ms=3_001,
        closed_before_ms=JANUARY_1_2026_MS + 5 * 60_000,
        executor_software_identity=EXECUTOR_IDENTITY,
    )
    assert len(preflight.task_plans) == 2
    assert preflight.required_free_bytes == expected_required
    assert all(
        task_plan.budget.rest_staging_bytes == 2 * per_task_staging
        for task_plan in preflight.task_plans
    )
