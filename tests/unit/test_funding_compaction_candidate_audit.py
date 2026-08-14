from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from grid_contracts.canonical import canonical_sha256
from grid_contracts.market import FundingEvent
from grid_data.evidence import publish_evidence
from grid_data.funding_compaction_candidate_audit import (
    FundingCompactionCandidateAuditError,
    build_funding_compaction_candidate_audit,
    build_funding_compaction_candidate_evidence,
    verify_funding_compaction_candidate_audit,
    verify_funding_compaction_candidate_evidence,
)
from grid_market_store import (
    MIN_OPERATING_RESERVE_BYTES,
    CapacityBudget,
    FundingDatasetSpec,
    HostSnapshot,
    build_canonical_funding_batch,
    preflight_funding_dataset,
    publish_funding_dataset,
)
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[2]
JANUARY_1_2026_MS = 1_767_225_600_000
SOFTWARE_IDENTITY = f"git:{'8' * 40}"


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


def publish_parent(
    tmp_path: Path,
    store: Path,
    *,
    index: int,
    timestamp: int,
    interval_minutes: int = 480,
) -> str:
    dataset_id = f"funding-candidate-fragment-{index:02d}"
    digest = f"{index + 1:064x}"
    batch = build_canonical_funding_batch(
        (
            FundingEvent(
                category="linear",
                instrument_id=9,
                funding_time_ms=timestamp,
                funding_rate=Decimal("0.0001"),
                funding_interval_minutes=interval_minutes,
                source_id="bybit-v5-funding-history/v1",
                ingestion_id=f"fixture-{index}",
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


def test_candidate_audit_classifies_every_same_partition_pair(tmp_path: Path) -> None:
    store = tmp_path / "market-store"
    for index, timestamp in enumerate(
        (
            JANUARY_1_2026_MS,
            JANUARY_1_2026_MS + 480 * 60_000,
            JANUARY_1_2026_MS + 960 * 60_000,
        )
    ):
        publish_parent(tmp_path, store, index=index, timestamp=timestamp)

    audit = build_funding_compaction_candidate_audit(
        store,
        auditor_software_identity=SOFTWARE_IDENTITY,
        generated_at_utc="2026-08-14T01:00:00Z",
    )

    assert audit["dataset_count"] == 3
    assert audit["partition_count"] == 1
    assert audit["multi_parent_partition_count"] == 1
    assert audit["pair_count"] == 3
    assert audit["classification_counts"] == {
        "duplicate-or-conflicting-keys": 0,
        "eligible": 2,
        "schema-mismatch": 0,
        "unresolved-settlement-interval": 1,
    }
    assert audit["status"] == "eligible-candidates-observed"


def test_no_candidate_evidence_is_sanitized_receipted_and_reproducible(
    tmp_path: Path,
) -> None:
    store = tmp_path / "market-store"
    first_id = publish_parent(
        tmp_path,
        store,
        index=0,
        timestamp=JANUARY_1_2026_MS,
    )
    second_id = publish_parent(
        tmp_path,
        store,
        index=1,
        timestamp=JANUARY_1_2026_MS,
    )
    audit = build_funding_compaction_candidate_audit(
        store,
        auditor_software_identity=SOFTWARE_IDENTITY,
        generated_at_utc="2026-08-14T01:01:00Z",
    )
    audit_path, _ = publish_evidence(tmp_path / "private-audit.json", audit)

    assert audit["status"] == "no-eligible-candidates"
    assert audit["classification_counts"] == {
        "duplicate-or-conflicting-keys": 1,
        "eligible": 0,
        "schema-mismatch": 0,
        "unresolved-settlement-interval": 0,
    }
    assert verify_funding_compaction_candidate_audit(audit_path, store) == audit

    evidence = build_funding_compaction_candidate_evidence(
        audit_path,
        store,
        publisher_software_identity=SOFTWARE_IDENTITY,
    )
    schema = json.loads(
        (
            ROOT
            / "schemas"
            / "evidence"
            / "v1"
            / "phase2-funding-compaction-candidate-audit.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(evidence)
    without_hash = dict(evidence)
    content_hash = without_hash.pop("content_sha256")
    assert content_hash == canonical_sha256(without_hash)
    assert evidence["status"] == "verified-no-eligible-funding-compaction-candidates"
    rendered = json.dumps(evidence).lower()
    assert first_id not in rendered
    assert second_id not in rendered
    assert "year=" not in rendered
    assert "0.0001" not in rendered
    assert "c:\\" not in rendered

    evidence_path, _ = publish_evidence(tmp_path / "public-evidence.json", evidence)
    assert (
        verify_funding_compaction_candidate_evidence(evidence_path, audit_path, store) == evidence
    )


def test_candidate_audit_fails_closed_on_inventory_change_or_incomplete_dataset(
    tmp_path: Path,
) -> None:
    store = tmp_path / "market-store"
    publish_parent(tmp_path, store, index=0, timestamp=JANUARY_1_2026_MS)
    publish_parent(tmp_path, store, index=1, timestamp=JANUARY_1_2026_MS)
    audit = build_funding_compaction_candidate_audit(
        store,
        auditor_software_identity=SOFTWARE_IDENTITY,
        generated_at_utc="2026-08-14T01:02:00Z",
    )
    audit_path, _ = publish_evidence(tmp_path / "private-audit.json", audit)

    publish_parent(
        tmp_path,
        store,
        index=2,
        timestamp=JANUARY_1_2026_MS + 480 * 60_000,
    )
    with pytest.raises(FundingCompactionCandidateAuditError, match="no longer matches"):
        verify_funding_compaction_candidate_audit(audit_path, store)

    invalid_store = tmp_path / "invalid-store" / "datasets" / "funding-incomplete"
    invalid_store.mkdir(parents=True)
    with pytest.raises(FundingCompactionCandidateAuditError, match="invalid or incomplete"):
        build_funding_compaction_candidate_audit(
            invalid_store.parents[1],
            auditor_software_identity=SOFTWARE_IDENTITY,
            generated_at_utc="2026-08-14T01:03:00Z",
        )
