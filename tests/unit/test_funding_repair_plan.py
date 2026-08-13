from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from grid_contracts.canonical import canonical_sha256
from grid_data.evidence import publish_evidence
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
from grid_data.funding_repair_plan import (
    build_funding_repair_plan,
    verify_funding_repair_plan,
)
from grid_data.funding_request import resolve_funding_request
from grid_data.history_request import closed_before_now_ms
from jsonschema import Draft202012Validator, FormatChecker

from tests.unit.test_funding_acquisition import FakeFundingClient, snapshot
from tests.unit.test_funding_publication import SOFTWARE_IDENTITY
from tests.unit.test_funding_request import evidence_files, request_payload, write_request

JANUARY_1_2026_MS = 1_767_225_600_000
AUDIT_IDENTITY = "git:" + "2" * 40
PLANNER_IDENTITY = "git:" + "3" * 40
ROOT = Path(__file__).parents[2]


class MissingSettlementClient(FakeFundingClient):
    def funding_page(self, **kwargs: Any) -> tuple[dict[str, str], ...]:
        rows = super().funding_page(**kwargs)
        if kwargs["limit"] == 1:
            return rows
        omitted = kwargs["start_ms"] + 60 * 60_000
        return tuple(row for row in rows if int(row["fundingRateTimestamp"]) != omitted)


class TrailingUnexplainedChangeClient(FakeFundingClient):
    def funding_page(self, **kwargs: Any) -> tuple[dict[str, str], ...]:
        rows = super().funding_page(**kwargs)
        if kwargs["limit"] == 1:
            return rows
        omitted = kwargs["start_ms"] + 120 * 60_000
        return tuple(row for row in rows if int(row["fundingRateTimestamp"]) != omitted)


class EmptyFirstRangeClient(FakeFundingClient):
    def funding_page(self, **kwargs: Any) -> tuple[dict[str, str], ...]:
        if kwargs["limit"] != 1 and kwargs["start_ms"] == JANUARY_1_2026_MS:
            return ()
        return super().funding_page(**kwargs)


def blocked_audit_fixture(
    tmp_path: Path,
    *,
    client_factory: type[FakeFundingClient] = MissingSettlementClient,
    page_span_minutes: int = 240,
) -> tuple[Path, Path, Path, Path, Path]:
    registry, capacity = evidence_files(tmp_path)
    request = request_payload(
        job_id="funding-2026-01-b01-repair-plan",
        series=[
            {
                "symbol": "AAAUSDT",
                "start_ms": JANUARY_1_2026_MS,
                "end_ms": JANUARY_1_2026_MS + 180 * 60_000,
            }
        ],
        page_span_minutes=page_span_minutes,
        page_limit=5,
        max_http_requests=6,
    )
    resolved = resolve_funding_request(
        write_request(tmp_path, request),
        instrument_registry_path=registry,
        capacity_evidence_path=capacity,
    )
    landing_root = tmp_path / "history"
    preflight = preflight_funding_job(
        landing_root,
        resolved.spec,
        resolved.budget,
        snapshot(tmp_path, free_bytes=120 * 1024**3),
        now_ms=1_001,
        closed_before_ms=closed_before_now_ms(JANUARY_1_2026_MS + 181 * 60_000),
    )
    completed = execute_funding_job(
        preflight,
        client_factory,
        lambda: snapshot(tmp_path, observed_at_ms=1_001, free_bytes=120 * 1024**3),
        now_ms=lambda: 1_002,
    )
    store = tmp_path / "market-store"
    publication = preflight_completed_funding_publication(
        store,
        completed.job_root,
        registry,
        capacity,
        snapshot(tmp_path, observed_at_ms=2_000, free_bytes=120 * 1024**3),
        now_ms=2_001,
        software_identity=SOFTWARE_IDENTITY,
    )
    publish_preflighted_funding(
        publication,
        lambda: snapshot(tmp_path, observed_at_ms=2_002, free_bytes=120 * 1024**3),
        lambda: 2_003,
    )
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
    audit_path, _receipt = publish_evidence(tmp_path / "funding-audit.json", audit.payload)
    return audit_path, completed.job_root, registry, capacity, store


def test_funding_repair_plan_embeds_bounded_exact_discovery_request(tmp_path: Path) -> None:
    audit, job_root, registry, capacity, store = blocked_audit_fixture(tmp_path)
    plan = build_funding_repair_plan(
        audit,
        job_root,
        registry,
        capacity,
        store,
        generated_at_utc="2026-08-14T00:00:00Z",
        planner_software_identity=PLANNER_IDENTITY,
    )

    schema = json.loads(
        (ROOT / "schemas" / "evidence" / "v1" / "bybit-funding-repair-plan.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(plan.payload)
    content = dict(plan.payload)
    embedded_hash = content.pop("content_sha256")
    assert embedded_hash == canonical_sha256(content)
    assert plan.task_count == 1
    assert plan.candidate_count == 1
    assert plan.planned_max_http_requests == 4
    assert plan.payload["status"] == "discovery-planned"
    assert plan.payload["inference_policy"] == {
        "audit_remains_blocked": True,
        "candidate_requires_exact_source_confirmation": True,
        "current_instrument_interval_used": False,
        "empty_source_windows_supported": False,
        "isolated_integer_multiple_sandwich_required": True,
        "schedule_change_accepted": False,
    }
    task = cast(list[dict[str, Any]], plan.payload["tasks"])[0]
    expected = JANUARY_1_2026_MS + 60 * 60_000
    assert task["candidate_settlement_times_ms"] == [expected]
    assert task["expected_interval_minutes"] == 60
    assert task["observed_gap_interval_minutes"] == 120
    assert task["predecessor_settlement_ms"] == JANUARY_1_2026_MS
    assert task["request"]["series"] == [
        {"end_ms": expected, "start_ms": expected, "symbol": "AAAUSDT"}
    ]
    assert task["request"]["max_http_requests"] == 4
    assert task["request"]["page_limit"] == 5
    mutation_policy = cast(dict[str, object], plan.payload["mutation_policy"])
    assert mutation_policy["market_requests_executed"] is False
    assert mutation_policy["repair_candidates_accepted"] is False

    plan_path, _receipt = publish_evidence(tmp_path / "funding-repair-plan.json", plan.payload)
    verified = verify_funding_repair_plan(
        plan_path,
        audit,
        job_root,
        registry,
        capacity,
        store,
    )
    assert verified.payload == plan.payload
    assert verified.candidate_count == 1


def test_funding_repair_plan_rejects_unbracketed_interval_change(tmp_path: Path) -> None:
    audit, job_root, registry, capacity, store = blocked_audit_fixture(
        tmp_path,
        client_factory=TrailingUnexplainedChangeClient,
    )
    with pytest.raises(FundingAcquisitionError, match="cadence sandwiches"):
        build_funding_repair_plan(
            audit,
            job_root,
            registry,
            capacity,
            store,
            generated_at_utc="2026-08-14T00:00:00Z",
            planner_software_identity=PLANNER_IDENTITY,
        )


def test_funding_repair_plan_rejects_empty_source_window(tmp_path: Path) -> None:
    audit, job_root, registry, capacity, store = blocked_audit_fixture(
        tmp_path,
        client_factory=EmptyFirstRangeClient,
        page_span_minutes=120,
    )
    with pytest.raises(FundingAcquisitionError, match="other audit blockers remain"):
        build_funding_repair_plan(
            audit,
            job_root,
            registry,
            capacity,
            store,
            generated_at_utc="2026-08-14T00:00:00Z",
            planner_software_identity=PLANNER_IDENTITY,
        )


def test_funding_repair_plan_rejects_non_git_identity_before_mutation(tmp_path: Path) -> None:
    audit, job_root, registry, capacity, store = blocked_audit_fixture(tmp_path)
    with pytest.raises(FundingAcquisitionError, match="planner_software_identity"):
        build_funding_repair_plan(
            audit,
            job_root,
            registry,
            capacity,
            store,
            generated_at_utc="2026-08-14T00:00:00Z",
            planner_software_identity="worktree:dirty",
        )
