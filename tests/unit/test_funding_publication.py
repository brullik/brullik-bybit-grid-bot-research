from __future__ import annotations

import json
from pathlib import Path

import pytest
from grid_contracts.canonical import canonical_sha256
from grid_data.funding_acquisition import (
    FundingAcquisitionError,
    execute_funding_job,
    preflight_funding_job,
)
from grid_data.funding_pilot_evidence import build_funding_pilot_evidence
from grid_data.funding_publication import (
    load_verified_funding_publication_input,
    preflight_completed_funding_publication,
    publish_preflighted_funding,
)
from grid_data.funding_request import resolve_funding_request
from grid_data.history_request import closed_before_now_ms
from grid_market_store import verify_committed_funding_dataset
from jsonschema import Draft202012Validator, FormatChecker

from tests.unit.test_funding_acquisition import FakeFundingClient, snapshot
from tests.unit.test_funding_request import evidence_files, request_payload, write_request

JANUARY_1_2026_MS = 1_767_225_600_000
SOFTWARE_IDENTITY = "git:" + "1" * 40


def completed_job(tmp_path: Path):  # type: ignore[no-untyped-def]
    registry, capacity = evidence_files(tmp_path)
    resolved = resolve_funding_request(
        write_request(tmp_path, request_payload()),
        instrument_registry_path=registry,
        capacity_evidence_path=capacity,
    )
    staging_root = tmp_path / "history"
    host = snapshot(tmp_path, free_bytes=120 * 1024**3)
    plan = preflight_funding_job(
        staging_root,
        resolved.spec,
        resolved.budget,
        host,
        now_ms=1_001,
        closed_before_ms=closed_before_now_ms(JANUARY_1_2026_MS + 120_000),
    )
    completed = execute_funding_job(
        plan,
        FakeFundingClient,
        lambda: snapshot(tmp_path, observed_at_ms=1_001, free_bytes=120 * 1024**3),
        now_ms=lambda: 1_002,
    )
    return completed, registry, capacity


def test_completed_funding_publication_binds_boundary_and_is_idempotent(
    tmp_path: Path,
) -> None:
    completed, registry, capacity = completed_job(tmp_path)
    verified = load_verified_funding_publication_input(
        completed.job_root,
        registry,
        capacity,
    )
    assert verified.completed.boundary_evidence_sha256
    assert verified.batch.table.num_rows == 2
    assert verified.dataset_id == f"funding-{completed.manifest_sha256[:24]}"

    store = tmp_path / "market-store"
    first = preflight_completed_funding_publication(
        store,
        completed.job_root,
        registry,
        capacity,
        snapshot(tmp_path, observed_at_ms=1_003, free_bytes=120 * 1024**3),
        now_ms=1_004,
        software_identity=SOFTWARE_IDENTITY,
    )
    assert not store.exists()
    assert first.plan.spec.boundary_evidence_sha256 == completed.boundary_evidence_sha256
    published = publish_preflighted_funding(
        first,
        lambda: snapshot(tmp_path, observed_at_ms=1_005, free_bytes=120 * 1024**3),
        lambda: 1_006,
    )
    assert published.manifest.row_count == 2
    assert published.manifest.source_evidence_sha256 == (
        completed.manifest_sha256,
        verified.registry.artifact_sha256,
        completed.boundary_evidence_sha256,
    )
    verify_committed_funding_dataset(published.dataset_root)

    rerun = preflight_completed_funding_publication(
        store,
        completed.job_root,
        registry,
        capacity,
        snapshot(tmp_path, observed_at_ms=1_007, free_bytes=120 * 1024**3),
        now_ms=1_008,
        software_identity=SOFTWARE_IDENTITY,
    )
    assert rerun.plan.existing_commit is True


def test_verified_funding_publication_builds_sanitized_pilot_evidence(tmp_path: Path) -> None:
    completed, registry, capacity = completed_job(tmp_path)
    store = tmp_path / "market-store"
    initial = preflight_completed_funding_publication(
        store,
        completed.job_root,
        registry,
        capacity,
        snapshot(tmp_path, observed_at_ms=2_000, free_bytes=120 * 1024**3),
        now_ms=2_001,
        software_identity=SOFTWARE_IDENTITY,
    )
    published = publish_preflighted_funding(
        initial,
        lambda: snapshot(tmp_path, observed_at_ms=2_002, free_bytes=120 * 1024**3),
        lambda: 2_003,
    )
    with pytest.raises(FundingAcquisitionError, match="existing immutable commit"):
        build_funding_pilot_evidence(
            initial,
            published,
            generated_at_utc="2026-08-13T12:00:00Z",
        )

    rerun = preflight_completed_funding_publication(
        store,
        completed.job_root,
        registry,
        capacity,
        snapshot(tmp_path, observed_at_ms=3_000, free_bytes=120 * 1024**3),
        now_ms=3_001,
        software_identity=SOFTWARE_IDENTITY,
    )
    assert rerun.plan.existing_commit is True
    payload = build_funding_pilot_evidence(
        rerun,
        verify_committed_funding_dataset(published.dataset_root),
        generated_at_utc="2026-08-13T12:00:00Z",
    )
    schema = json.loads(
        (
            Path(__file__).parents[2]
            / "schemas"
            / "evidence"
            / "v1"
            / "phase2-public-funding-pilot.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    embedded_hash = payload.pop("content_sha256")
    assert embedded_hash == canonical_sha256(payload)
    assert payload["scope"] == {
        "category": "linear",
        "observed_event_count": 2,
        "requested_window_minutes": 4,
        "series": [
            {
                "end_ms": JANUARY_1_2026_MS + 60_000,
                "instrument_id": 1,
                "observed_event_count": 1,
                "predecessor_bound": True,
                "requested_window_minutes": 2,
                "start_ms": JANUARY_1_2026_MS,
                "symbol": "AAAUSDT",
            },
            {
                "end_ms": JANUARY_1_2026_MS + 60_000,
                "instrument_id": 9,
                "observed_event_count": 1,
                "predecessor_bound": True,
                "requested_window_minutes": 2,
                "start_ms": JANUARY_1_2026_MS,
                "symbol": "BBBUSDT",
            },
        ],
    }
    rendered = json.dumps(payload)
    assert str(tmp_path) not in rendered
    assert "0.0001000" not in rendered
    assert "-0.0002000" not in rendered
    assert '"fundingRate"' not in rendered
    assert '"funding_rate":' not in rendered
