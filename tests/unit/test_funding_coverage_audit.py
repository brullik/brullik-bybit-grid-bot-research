from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from grid_contracts.canonical import canonical_sha256
from grid_data.funding_acquisition import (
    FundingAcquisitionError,
    execute_funding_job,
    preflight_funding_job,
)
from grid_data.funding_coverage_audit import build_completed_funding_coverage_audit
from grid_data.funding_publication import (
    preflight_completed_funding_publication,
    publish_preflighted_funding,
)
from grid_data.funding_request import resolve_funding_request
from grid_data.history_request import closed_before_now_ms
from jsonschema import Draft202012Validator, FormatChecker

from tests.unit.test_funding_acquisition import FakeFundingClient, snapshot
from tests.unit.test_funding_publication import SOFTWARE_IDENTITY, completed_job
from tests.unit.test_funding_request import evidence_files, request_payload, write_request

JANUARY_1_2026_MS = 1_767_225_600_000
AUDIT_IDENTITY = "git:" + "2" * 40
ROOT = Path(__file__).parents[2]


def publish_completed(  # type: ignore[no-untyped-def]
    tmp_path: Path,
    completed,
    registry: Path,
    capacity: Path,
):
    store = tmp_path / "market-store"
    plan = preflight_completed_funding_publication(
        store,
        completed.job_root,
        registry,
        capacity,
        snapshot(tmp_path, observed_at_ms=2_000, free_bytes=120 * 1024**3),
        now_ms=2_001,
        software_identity=SOFTWARE_IDENTITY,
    )
    publish_preflighted_funding(
        plan,
        lambda: snapshot(tmp_path, observed_at_ms=2_002, free_bytes=120 * 1024**3),
        lambda: 2_003,
    )
    return store


def test_funding_coverage_audit_passes_stable_source_chronology(tmp_path: Path) -> None:
    completed, registry, capacity = completed_job(tmp_path)
    store = publish_completed(tmp_path, completed, registry, capacity)
    audit = build_completed_funding_coverage_audit(
        completed.job_root,
        registry,
        capacity,
        store,
        publisher_software_identity=SOFTWARE_IDENTITY,
        audit_software_identity=AUDIT_IDENTITY,
        generated_at_utc="2026-08-13T12:00:00Z",
    )
    schema = json.loads(
        (
            ROOT / "schemas" / "evidence" / "v1" / "canonical-funding-coverage-audit.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(audit.payload)
    content = dict(audit.payload)
    embedded_hash = content.pop("content_sha256")
    assert embedded_hash == canonical_sha256(content)
    assert audit.passed is True
    assert audit.anomaly_records == ()
    assert audit.payload["status"] == "passed"
    assert audit.payload["quality"] == {
        "boundary_page_count": 2,
        "canonical_source_table_equal": True,
        "conflicting_key_count": 0,
        "duplicate_key_count": 0,
        "empty_range_page_count": 0,
        "internal_interval_mismatch_count": 0,
        "interval_change_count": 0,
        "lifecycle_failure_count": 0,
        "observed_event_count": 2,
        "predecessor_interval_mismatch_count": 0,
        "range_page_count": 2,
        "requested_window_minutes": 4,
        "source_range_enumeration_complete": True,
        "unrequested_row_count": 0,
        "unexpected_timestamp_count": 0,
    }
    assert audit.payload["reason_policy"] == {
        "accepted_reason_codes": [],
        "observed_reason_counts": {},
        "unaccepted_reason_codes": [],
        "unknown_reason_count": 0,
    }
    assert [item["stable_observed_interval_minutes"] for item in audit.payload["series"]] == [
        60,
        60,
    ]
    rendered = json.dumps(audit.payload)
    assert str(tmp_path) not in rendered
    assert "0.0001000" not in rendered
    assert '"fundingRate"' not in rendered
    assert '"funding_rate":' not in rendered


class MissingSettlementClient(FakeFundingClient):
    def funding_page(self, **kwargs: Any) -> tuple[dict[str, str], ...]:
        rows = super().funding_page(**kwargs)
        if kwargs["limit"] == 1:
            return rows
        omitted = kwargs["start_ms"] + 60 * 60_000
        return tuple(row for row in rows if int(row["fundingRateTimestamp"]) != omitted)


class EmptyFirstRangeClient(FakeFundingClient):
    def funding_page(self, **kwargs: Any) -> tuple[dict[str, str], ...]:
        if kwargs["limit"] != 1 and kwargs["start_ms"] == JANUARY_1_2026_MS:
            return ()
        return super().funding_page(**kwargs)


def test_funding_coverage_audit_blocks_unexplained_observed_cadence_change(
    tmp_path: Path,
) -> None:
    registry, capacity = evidence_files(tmp_path)
    request = request_payload(
        job_id="funding-2026-01-b01-cadence-change",
        series=[
            {
                "symbol": "AAAUSDT",
                "start_ms": JANUARY_1_2026_MS,
                "end_ms": JANUARY_1_2026_MS + 180 * 60_000,
            }
        ],
        page_span_minutes=240,
        page_limit=5,
        max_http_requests=4,
    )
    resolved = resolve_funding_request(
        write_request(tmp_path, request),
        instrument_registry_path=registry,
        capacity_evidence_path=capacity,
    )
    plan = preflight_funding_job(
        tmp_path / "history",
        resolved.spec,
        resolved.budget,
        snapshot(tmp_path, free_bytes=120 * 1024**3),
        now_ms=1_001,
        closed_before_ms=closed_before_now_ms(JANUARY_1_2026_MS + 181 * 60_000),
    )
    completed = execute_funding_job(
        plan,
        MissingSettlementClient,
        lambda: snapshot(tmp_path, observed_at_ms=1_001, free_bytes=120 * 1024**3),
        now_ms=lambda: 1_002,
    )
    store = publish_completed(tmp_path, completed, registry, capacity)
    audit = build_completed_funding_coverage_audit(
        completed.job_root,
        registry,
        capacity,
        store,
        publisher_software_identity=SOFTWARE_IDENTITY,
        audit_software_identity=AUDIT_IDENTITY,
        generated_at_utc="2026-08-13T12:00:00Z",
    )

    assert audit.passed is False
    assert audit.payload["status"] == "blocked"
    assert audit.payload["quality"]["interval_change_count"] == 2
    assert audit.payload["quality"]["source_range_enumeration_complete"] is False
    assert audit.payload["reason_policy"]["observed_reason_counts"] == {
        "unexplained_interval_change": 2
    }
    assert audit.payload["reason_policy"]["accepted_reason_codes"] == []
    assert audit.payload["coverage_basis"]["current_instrument_interval_used"] is False
    assert len(audit.anomaly_records) == 2


def test_funding_coverage_audit_blocks_unexplained_empty_source_window(
    tmp_path: Path,
) -> None:
    registry, capacity = evidence_files(tmp_path)
    request = request_payload(
        job_id="funding-2026-01-b01-empty-window",
        series=[
            {
                "symbol": "AAAUSDT",
                "start_ms": JANUARY_1_2026_MS,
                "end_ms": JANUARY_1_2026_MS + 180 * 60_000,
            }
        ],
        page_span_minutes=120,
        page_limit=5,
        max_http_requests=6,
    )
    resolved = resolve_funding_request(
        write_request(tmp_path, request),
        instrument_registry_path=registry,
        capacity_evidence_path=capacity,
    )
    plan = preflight_funding_job(
        tmp_path / "history",
        resolved.spec,
        resolved.budget,
        snapshot(tmp_path, free_bytes=120 * 1024**3),
        now_ms=1_001,
        closed_before_ms=closed_before_now_ms(JANUARY_1_2026_MS + 181 * 60_000),
    )
    completed = execute_funding_job(
        plan,
        EmptyFirstRangeClient,
        lambda: snapshot(tmp_path, observed_at_ms=1_001, free_bytes=120 * 1024**3),
        now_ms=lambda: 1_002,
    )
    store = publish_completed(tmp_path, completed, registry, capacity)
    audit = build_completed_funding_coverage_audit(
        completed.job_root,
        registry,
        capacity,
        store,
        publisher_software_identity=SOFTWARE_IDENTITY,
        audit_software_identity=AUDIT_IDENTITY,
        generated_at_utc="2026-08-13T12:00:00Z",
    )

    assert audit.passed is False
    assert audit.payload["quality"]["empty_range_page_count"] == 1
    assert audit.payload["reason_policy"]["observed_reason_counts"] == {
        "source_window_returned_no_event": 1,
        "unexplained_interval_change": 1,
    }
    assert audit.payload["reason_policy"]["accepted_reason_codes"] == []
    assert any(
        item["reason"] == "source_window_returned_no_event" for item in audit.anomaly_records
    )


def test_funding_coverage_audit_rejects_non_git_auditor_identity(tmp_path: Path) -> None:
    completed, registry, capacity = completed_job(tmp_path)
    store = publish_completed(tmp_path, completed, registry, capacity)
    with pytest.raises(FundingAcquisitionError, match="audit_software_identity"):
        build_completed_funding_coverage_audit(
            completed.job_root,
            registry,
            capacity,
            store,
            publisher_software_identity=SOFTWARE_IDENTITY,
            audit_software_identity="worktree:dirty",
            generated_at_utc="2026-08-13T12:00:00Z",
        )
