from __future__ import annotations

import json
from pathlib import Path

import pytest
from grid_contracts.canonical import sha256_file
from grid_data.evidence import publish_evidence
from grid_data.funding_acquisition import FundingAcquisitionError
from grid_data.funding_repair_coverage_audit import (
    build_funding_repair_coverage_audit,
    verify_funding_repair_coverage_audit,
)
from grid_data.funding_repair_publication import (
    build_funding_repair_replacement_evidence,
    preflight_repaired_funding_publication,
    publish_preflighted_funding_repair,
)
from jsonschema import Draft202012Validator, FormatChecker

from tests.unit.test_funding_acquisition import snapshot
from tests.unit.test_funding_repair_publication import (
    REPLACEMENT_IDENTITY,
    _execution_fixture,
)

AUDITOR_IDENTITY = "git:" + "7" * 40
ROOT = Path(__file__).parents[2]


def _published_repair_fixture(tmp_path: Path):  # type: ignore[no-untyped-def]
    (
        _verified,
        execution_path,
        plan_path,
        original_audit,
        original_job,
        registry,
        capacity,
        store,
        repair_staging,
    ) = _execution_fixture(tmp_path)
    original_audit_before = sha256_file(original_audit)
    resolved = preflight_repaired_funding_publication(
        execution_path,
        plan_path,
        original_audit,
        original_job,
        registry,
        capacity,
        store,
        repair_staging,
        snapshot(tmp_path, observed_at_ms=4_000, free_bytes=120 * 1024**3),
        now_ms=4_001,
        software_identity=REPLACEMENT_IDENTITY,
    )
    published = publish_preflighted_funding_repair(
        resolved,
        lambda: snapshot(tmp_path, observed_at_ms=4_002, free_bytes=120 * 1024**3),
        lambda: 4_003,
    )
    replacement = build_funding_repair_replacement_evidence(
        resolved,
        published,
        generated_at_utc="2026-08-14T00:03:00Z",
    )
    replacement_path, _receipt = publish_evidence(
        tmp_path / "funding-repair-replacement.json",
        replacement,
    )
    return (
        execution_path,
        plan_path,
        original_audit,
        original_audit_before,
        original_job,
        registry,
        capacity,
        store,
        repair_staging,
        replacement_path,
        published,
    )


def test_post_publication_funding_repair_audit_passes_and_is_receipted(
    tmp_path: Path,
) -> None:
    (
        execution_path,
        plan_path,
        original_audit,
        original_audit_before,
        original_job,
        registry,
        capacity,
        store,
        repair_staging,
        replacement_path,
        published,
    ) = _published_repair_fixture(tmp_path)
    audit = build_funding_repair_coverage_audit(
        execution_path,
        plan_path,
        original_audit,
        original_job,
        registry,
        capacity,
        store,
        repair_staging,
        replacement_path,
        publisher_software_identity=REPLACEMENT_IDENTITY,
        audit_software_identity=AUDITOR_IDENTITY,
        generated_at_utc="2026-08-14T00:04:00Z",
    )
    assert audit.passed is True
    assert audit.payload["status"] == "passed"
    assert audit.payload["dataset_id"] == published.manifest.dataset_id
    assert audit.payload["quality"] == {
        "boundary_page_count": 1,
        "canonical_source_table_equal": True,
        "conflicting_key_count": 0,
        "duplicate_key_count": 0,
        "empty_range_page_count": 0,
        "internal_interval_mismatch_count": 0,
        "interval_change_count": 0,
        "lifecycle_failure_count": 0,
        "observed_event_count": 4,
        "predecessor_interval_mismatch_count": 0,
        "range_page_count": 1,
        "requested_window_minutes": 181,
        "source_range_enumeration_complete": True,
        "unrequested_row_count": 0,
        "unexpected_timestamp_count": 0,
    }
    assert audit.payload["reason_policy"]["observed_reason_counts"] == {}
    assert audit.payload["series"][0]["stable_observed_interval_minutes"] == 60
    assert audit.payload["chronology_anomaly_evidence"]["anomaly_count"] == 0
    assert audit.payload["storage_policy"]["github_commit_eligible"] is False
    assert sha256_file(original_audit) == original_audit_before

    schema = json.loads(
        (
            ROOT / "schemas/evidence/v1/canonical-funding-repair-coverage-audit.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(audit.payload)
    audit_path, _receipt = publish_evidence(
        tmp_path / "funding-repair-coverage-audit.json",
        audit.payload,
    )
    verified = verify_funding_repair_coverage_audit(
        audit_path,
        execution_path,
        plan_path,
        original_audit,
        original_job,
        registry,
        capacity,
        store,
        repair_staging,
        replacement_path,
    )
    assert verified.payload == audit.payload
    with pytest.raises(FundingAcquisitionError, match="publisher identity differs"):
        verify_funding_repair_coverage_audit(
            audit_path,
            execution_path,
            plan_path,
            original_audit,
            original_job,
            registry,
            capacity,
            store,
            repair_staging,
            replacement_path,
            expected_publisher_software_identity="git:" + "8" * 40,
        )


def test_funding_repair_audit_rejects_uncommitted_child(tmp_path: Path) -> None:
    (
        _verified,
        execution_path,
        plan_path,
        original_audit,
        original_job,
        registry,
        capacity,
        store,
        repair_staging,
    ) = _execution_fixture(tmp_path)
    with pytest.raises(FundingAcquisitionError, match="requires the exact committed repair child"):
        build_funding_repair_coverage_audit(
            execution_path,
            plan_path,
            original_audit,
            original_job,
            registry,
            capacity,
            store,
            repair_staging,
            tmp_path / "missing-replacement.json",
            publisher_software_identity=REPLACEMENT_IDENTITY,
            audit_software_identity=AUDITOR_IDENTITY,
            generated_at_utc="2026-08-14T00:04:00Z",
        )
