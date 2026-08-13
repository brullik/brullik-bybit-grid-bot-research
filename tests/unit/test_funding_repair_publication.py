from __future__ import annotations

import json
from pathlib import Path

import pytest
from grid_contracts.canonical import sha256_file
from grid_data.evidence import publish_evidence
from grid_data.funding_acquisition import FundingAcquisitionError
from grid_data.funding_repair_execution import (
    execute_funding_repair,
    verify_funding_repair_execution,
)
from grid_data.funding_repair_publication import (
    build_funding_repair_execution_public_evidence,
    build_funding_repair_replacement_evidence,
    preflight_repaired_funding_publication,
    publish_preflighted_funding_repair,
    verify_funding_repair_execution_public_evidence,
    verify_funding_repair_replacement_evidence,
)
from grid_market_store import load_committed_funding_table, verify_committed_funding_dataset
from jsonschema import Draft202012Validator, FormatChecker

from tests.unit.test_funding_acquisition import FakeFundingClient, snapshot
from tests.unit.test_funding_repair_execution import (
    EXECUTOR_IDENTITY,
    EmptyCandidateClient,
    preflight_execution,
)

REPLACEMENT_IDENTITY = "git:" + "6" * 40
ROOT = Path(__file__).parents[2]


def _execution_fixture(
    tmp_path: Path,
    client_factory: type[FakeFundingClient] | type[EmptyCandidateClient] = FakeFundingClient,
):  # type: ignore[no-untyped-def]
    (
        audit,
        original_job,
        registry,
        capacity,
        store,
        plan_path,
        repair_staging,
        preflight,
    ) = preflight_execution(tmp_path)
    result = execute_funding_repair(
        preflight,
        client_factory,
        lambda: snapshot(tmp_path, observed_at_ms=3_001, free_bytes=120 * 1024**3),
        generated_at_utc="2026-08-14T00:01:00Z",
        executor_software_identity=EXECUTOR_IDENTITY,
        now_ms=lambda: 3_002,
    )
    execution_path, _receipt = publish_evidence(
        tmp_path / "funding-repair-execution.json", result.payload
    )
    verified = verify_funding_repair_execution(
        execution_path,
        plan_path,
        audit,
        original_job,
        registry,
        capacity,
        store,
        repair_staging,
    )
    return (
        verified,
        execution_path,
        plan_path,
        audit,
        original_job,
        registry,
        capacity,
        store,
        repair_staging,
    )


def test_public_execution_projection_is_receipted_and_identifier_free(tmp_path: Path) -> None:
    verified, *_ = _execution_fixture(tmp_path)
    payload = build_funding_repair_execution_public_evidence(
        verified,
        generated_at_utc="2026-08-14T00:02:00Z",
    )
    schema = json.loads(
        (ROOT / "schemas/evidence/v1/bybit-funding-repair-execution-public.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    text = json.dumps(payload, sort_keys=True)
    private_task = verified.payload["tasks"][0]
    assert "AAAUSDT" not in text
    assert str(private_task["start_ms"]) not in text
    assert '"instrument_id":' not in text
    assert "job_directory" not in text
    assert "tasks" not in payload
    assert "dataset_id" not in payload
    assert payload["status"] == "passed"
    assert payload["storage_policy"]["github_commit_eligible"] is True

    evidence_path, _receipt = publish_evidence(
        tmp_path / "funding-repair-execution-public.json", payload
    )
    assert verify_funding_repair_execution_public_evidence(evidence_path, verified) == payload


def test_funding_repair_publication_is_exact_immutable_and_idempotent(tmp_path: Path) -> None:
    (
        verified,
        execution_path,
        plan_path,
        audit,
        original_job,
        registry,
        capacity,
        store,
        repair_staging,
    ) = _execution_fixture(tmp_path)
    parent_id = str(verified.payload["dataset_id"])
    parent = verify_committed_funding_dataset(store / "datasets" / parent_id)
    parent_manifest_before = sha256_file(parent.manifest_path)
    parent_file_before = sha256_file(parent.dataset_root / parent.manifest.files[0].path)

    resolved = preflight_repaired_funding_publication(
        execution_path,
        plan_path,
        audit,
        original_job,
        registry,
        capacity,
        store,
        repair_staging,
        snapshot(tmp_path, observed_at_ms=4_000, free_bytes=120 * 1024**3),
        now_ms=4_001,
        software_identity=REPLACEMENT_IDENTITY,
    )
    assert resolved.plan.existing_commit is False
    assert resolved.parent_row_count == 3
    assert resolved.repaired_row_count == 1
    assert resolved.restated_interval_count == 1
    assert not resolved.plan.paths.dataset_root.exists()

    published = publish_preflighted_funding_repair(
        resolved,
        lambda: snapshot(tmp_path, observed_at_ms=4_002, free_bytes=120 * 1024**3),
        lambda: 4_003,
    )
    assert published.manifest.parent_dataset_ids == (parent_id,)
    assert published.manifest.row_count == 4
    assert published.manifest.dataset_id != parent_id
    child = load_committed_funding_table(published.dataset_root)
    assert child.column("funding_interval_minutes").to_pylist() == [60, 60, 60, 60]
    assert sha256_file(parent.manifest_path) == parent_manifest_before
    assert sha256_file(parent.dataset_root / parent.manifest.files[0].path) == parent_file_before

    payload = build_funding_repair_replacement_evidence(
        resolved,
        published,
        generated_at_utc="2026-08-14T00:03:00Z",
    )
    schema = json.loads(
        (ROOT / "schemas/evidence/v1/canonical-funding-repair-replacement.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    evidence_path, _receipt = publish_evidence(
        tmp_path / "funding-repair-replacement.json", payload
    )
    assert (
        verify_funding_repair_replacement_evidence(
            evidence_path,
            resolved,
            published,
        )
        == payload
    )

    replay = preflight_repaired_funding_publication(
        execution_path,
        plan_path,
        audit,
        original_job,
        registry,
        capacity,
        store,
        repair_staging,
        snapshot(tmp_path, observed_at_ms=5_000, free_bytes=120 * 1024**3),
        now_ms=5_001,
        software_identity=REPLACEMENT_IDENTITY,
    )
    assert replay.plan.existing_commit is True
    same = publish_preflighted_funding_repair(
        replay,
        lambda: snapshot(tmp_path, observed_at_ms=5_002, free_bytes=120 * 1024**3),
        lambda: 5_003,
    )
    assert same.receipt.manifest_sha256 == published.receipt.manifest_sha256


def test_blocked_funding_repair_execution_cannot_publish(tmp_path: Path) -> None:
    (
        verified,
        execution_path,
        plan_path,
        audit,
        original_job,
        registry,
        capacity,
        store,
        repair_staging,
    ) = _execution_fixture(tmp_path, EmptyCandidateClient)
    assert verified.passed is False
    with pytest.raises(FundingAcquisitionError, match="requires a passed repair execution"):
        preflight_repaired_funding_publication(
            execution_path,
            plan_path,
            audit,
            original_job,
            registry,
            capacity,
            store,
            repair_staging,
            snapshot(tmp_path, observed_at_ms=4_000, free_bytes=120 * 1024**3),
            now_ms=4_001,
            software_identity=REPLACEMENT_IDENTITY,
        )
