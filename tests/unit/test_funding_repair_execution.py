from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from grid_contracts.canonical import canonical_sha256
from grid_data.evidence import publish_evidence
from grid_data.funding_acquisition import FundingAcquisitionError
from grid_data.funding_repair_execution import (
    execute_funding_repair,
    preflight_funding_repair_execution,
    verify_funding_repair_execution,
)
from grid_data.funding_repair_plan import build_funding_repair_plan
from jsonschema import Draft202012Validator, FormatChecker

from tests.unit.test_funding_acquisition import FakeFundingClient, snapshot
from tests.unit.test_funding_repair_plan import (
    JANUARY_1_2026_MS,
    PLANNER_IDENTITY,
    blocked_audit_fixture,
)

EXECUTOR_IDENTITY = "git:" + "4" * 40
ROOT = Path(__file__).parents[2]


class EmptyCandidateClient(FakeFundingClient):
    def funding_page(self, **kwargs: Any) -> tuple[dict[str, str], ...]:
        if kwargs["limit"] != 1:
            return ()
        return super().funding_page(**kwargs)


def repair_inputs(tmp_path: Path):  # type: ignore[no-untyped-def]
    audit, original_job, registry, capacity, store = blocked_audit_fixture(tmp_path)
    plan = build_funding_repair_plan(
        audit,
        original_job,
        registry,
        capacity,
        store,
        generated_at_utc="2026-08-14T00:00:00Z",
        planner_software_identity=PLANNER_IDENTITY,
    )
    plan_path, _receipt = publish_evidence(tmp_path / "funding-repair-plan.json", plan.payload)
    return audit, original_job, registry, capacity, store, plan_path


def preflight_execution(tmp_path: Path):  # type: ignore[no-untyped-def]
    audit, original_job, registry, capacity, store, plan_path = repair_inputs(tmp_path)
    repair_staging = tmp_path / "funding-repair-history"
    preflight = preflight_funding_repair_execution(
        plan_path,
        audit,
        original_job,
        registry,
        capacity,
        store,
        repair_staging,
        snapshot(tmp_path, observed_at_ms=3_000, free_bytes=120 * 1024**3),
        now_ms=3_001,
        closed_before_ms=JANUARY_1_2026_MS + 181 * 60_000,
        executor_software_identity=EXECUTOR_IDENTITY,
    )
    return (
        audit,
        original_job,
        registry,
        capacity,
        store,
        plan_path,
        repair_staging,
        preflight,
    )


def test_funding_repair_execution_is_exact_receipted_and_idempotent(tmp_path: Path) -> None:
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
    assert not repair_staging.exists()
    assert preflight.existing_complete_count == 0
    assert len(preflight.task_plans) == 1
    assert preflight.verified_plan.candidate_count == 1

    result = execute_funding_repair(
        preflight,
        FakeFundingClient,
        lambda: snapshot(tmp_path, observed_at_ms=3_001, free_bytes=120 * 1024**3),
        generated_at_utc="2026-08-14T00:01:00Z",
        executor_software_identity=EXECUTOR_IDENTITY,
        now_ms=lambda: 3_002,
    )
    schema = json.loads(
        (
            ROOT / "schemas" / "evidence" / "v1" / "bybit-funding-repair-execution.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(result.payload)
    content = dict(result.payload)
    embedded_hash = content.pop("content_sha256")
    assert embedded_hash == canonical_sha256(content)
    assert result.passed is True
    assert result.payload["status"] == "passed"
    assert result.payload["limits"] == {
        "actual_http_requests": 2,
        "candidate_settlement_count": 1,
        "missing_candidate_count": 0,
        "observed_event_count": 1,
        "planned_max_http_requests": 4,
        "task_count": 1,
        "unexpected_event_count": 0,
    }
    task = result.payload["tasks"][0]
    assert task["exact_source_confirmation"] is True
    assert task["observed_event_count"] == 1
    assert "funding_rate" not in json.dumps(result.payload)

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
    assert verified.passed is True
    assert verified.payload == result.payload

    replay = preflight_funding_repair_execution(
        plan_path,
        audit,
        original_job,
        registry,
        capacity,
        store,
        repair_staging,
        snapshot(tmp_path, observed_at_ms=3_003, free_bytes=120 * 1024**3),
        now_ms=3_004,
        closed_before_ms=JANUARY_1_2026_MS + 181 * 60_000,
        executor_software_identity=EXECUTOR_IDENTITY,
    )
    assert replay.existing_complete_count == 1
    replay_result = execute_funding_repair(
        replay,
        lambda: pytest.fail("idempotent replay must not make a public request"),
        lambda: snapshot(tmp_path, observed_at_ms=3_004, free_bytes=120 * 1024**3),
        generated_at_utc="2026-08-14T00:01:00Z",
        executor_software_identity=EXECUTOR_IDENTITY,
        now_ms=lambda: 3_005,
    )
    assert replay_result.payload == result.payload


def test_missing_candidate_is_preserved_as_blocked(tmp_path: Path) -> None:
    (
        _audit,
        _original_job,
        _registry,
        _capacity,
        _store,
        _plan_path,
        _repair_staging,
        preflight,
    ) = preflight_execution(tmp_path)
    result = execute_funding_repair(
        preflight,
        EmptyCandidateClient,
        lambda: snapshot(tmp_path, observed_at_ms=3_001, free_bytes=120 * 1024**3),
        generated_at_utc="2026-08-14T00:01:00Z",
        executor_software_identity=EXECUTOR_IDENTITY,
        now_ms=lambda: 3_002,
    )
    assert result.passed is False
    assert result.payload["status"] == "blocked"
    assert result.payload["limits"]["missing_candidate_count"] == 1
    assert result.payload["limits"]["observed_event_count"] == 0
    assert result.payload["tasks"][0]["exact_source_confirmation"] is False


def test_funding_repair_execution_rejects_identity_change_before_requests(tmp_path: Path) -> None:
    *_, preflight = preflight_execution(tmp_path)
    with pytest.raises(FundingAcquisitionError, match="identity changed"):
        execute_funding_repair(
            preflight,
            lambda: pytest.fail("identity failure must precede public requests"),
            lambda: snapshot(tmp_path, observed_at_ms=3_001, free_bytes=120 * 1024**3),
            generated_at_utc="2026-08-14T00:01:00Z",
            executor_software_identity="git:" + "5" * 40,
            now_ms=lambda: 3_002,
        )
