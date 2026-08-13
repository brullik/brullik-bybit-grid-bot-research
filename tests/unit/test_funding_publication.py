from __future__ import annotations

from pathlib import Path

from grid_data.funding_acquisition import execute_funding_job, preflight_funding_job
from grid_data.funding_publication import (
    load_verified_funding_publication_input,
    preflight_completed_funding_publication,
    publish_preflighted_funding,
)
from grid_data.funding_request import resolve_funding_request
from grid_data.history_request import closed_before_now_ms
from grid_market_store import verify_committed_funding_dataset

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
