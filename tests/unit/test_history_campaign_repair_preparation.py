from __future__ import annotations

import json
from pathlib import Path

import grid_data.history_campaign_coverage_audit as campaign_coverage
import grid_data.history_campaign_repair_preparation as campaign_repairs
import pytest
from grid_contracts.canonical import canonical_sha256
from grid_data.cli import parser as command_parser
from grid_data.evidence import publish_evidence
from grid_data.funding_coverage_audit import FundingCoverageAudit
from grid_data.history_campaign_coverage_audit import build_history_campaign_coverage_audit
from grid_data.history_campaign_repair_preparation import (
    HistoryCampaignRepairPreparationError,
    prepare_history_campaign_repairs,
    verify_completed_history_campaign_repair_preparation,
)
from grid_data.history_coverage_audit import CoverageAudit
from jsonschema import Draft202012Validator, FormatChecker

from tests.unit.test_history_campaign import (
    JANUARY_31_2026_2358_MS,
    inventory_record,
    request_payload,
)
from tests.unit.test_history_campaign import execute as execute_source_campaign
from tests.unit.test_history_campaign import preflight as preflight_source_campaign
from tests.unit.test_history_campaign_publication import (
    LeadingGapKlineClient,
    PublishingFundingClient,
    completed_source_campaign,
    execute_publication,
    preflight_publication,
)

ROOT = Path(__file__).parents[2]
PUBLISHER_IDENTITY = "git:" + "7" * 40
AUDITOR_IDENTITY = "git:" + "9" * 40
PLANNER_IDENTITY = "git:" + "c" * 40


def _published_gap_campaign(tmp_path: Path):  # type: ignore[no-untyped-def]
    source_plan = preflight_source_campaign(
        tmp_path,
        request=request_payload(
            kinds=["trade"],
            symbols=["AAAUSDT"],
            start_ms=JANUARY_31_2026_2358_MS,
            end_ms=JANUARY_31_2026_2358_MS + 3 * 60_000,
        ),
        records=[
            inventory_record(
                "AAAUSDT",
                1,
                launch_time_ms=JANUARY_31_2026_2358_MS,
            )
        ],
    )
    source = execute_source_campaign(
        source_plan,
        LeadingGapKlineClient(),
        PublishingFundingClient(),
    )
    publication_plan = preflight_publication(tmp_path, source.campaign_root)
    completed = execute_publication(publication_plan)
    return source, publication_plan, completed


def _aggregate_audit(
    tmp_path: Path,
    source,
    publication_plan,
    completed,
) -> Path:  # type: ignore[no-untyped-def]
    aggregate = build_history_campaign_coverage_audit(
        completed.publication_root,
        source.campaign_root,
        tmp_path / "registry.json",
        tmp_path / "capacity.json",
        publication_plan.store_root,
        publisher_software_identity=PUBLISHER_IDENTITY,
        audit_software_identity=AUDITOR_IDENTITY,
        generated_at_utc="2026-08-15T05:00:00Z",
    )
    assert aggregate.passed is False
    aggregate_path, _ = publish_evidence(tmp_path / "aggregate-coverage.json", aggregate.payload)
    return aggregate_path


def _prepare(
    tmp_path: Path,
    source,
    publication_plan,
    completed,
    aggregate_path: Path,
):  # type: ignore[no-untyped-def]
    return prepare_history_campaign_repairs(
        completed.publication_root,
        source.campaign_root,
        aggregate_path,
        tmp_path / "registry.json",
        tmp_path / "capacity.json",
        publication_plan.store_root,
        tmp_path / "reports" / "private" / "campaign-repairs",
        generated_at_utc="2026-08-15T05:01:00Z",
        planner_software_identity=PLANNER_IDENTITY,
    )


def _schema(name: str) -> dict[str, object]:
    return json.loads((ROOT / "schemas" / "market" / "v1" / name).read_text(encoding="utf-8"))


def test_preparation_recomputes_only_blocked_candles_and_resumes_from_receipts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, publication_plan, completed = _published_gap_campaign(tmp_path)
    aggregate_path = _aggregate_audit(tmp_path, source, publication_plan, completed)
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    assert [item["status"] for item in aggregate["child_results"]] == ["blocked", "passed"]

    original = campaign_repairs.build_completed_history_coverage_audit
    recomputed_sequences = 0

    def counted(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal recomputed_sequences
        recomputed_sequences += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(campaign_repairs, "build_completed_history_coverage_audit", counted)
    prepared = _prepare(tmp_path, source, publication_plan, completed, aggregate_path)

    assert recomputed_sequences == 1
    assert prepared.existing_complete is False
    assert prepared.status == "complete-repair-plans-prepared"
    assert prepared.dataset_count == 2
    assert prepared.blocked_candle_count == 1
    assert prepared.eligible_candle_count == 1
    assert prepared.ineligible_candle_count == 0
    assert prepared.repair_plan_count == prepared.task_count == 1
    root = prepared.preparation_root
    request = json.loads((root / "request.json").read_text(encoding="utf-8"))
    manifest = json.loads(prepared.manifest_path.read_text(encoding="utf-8"))
    child_root = root / "children" / "000000"
    child = json.loads((child_root / "result.json").read_text(encoding="utf-8"))
    plan = json.loads((child_root / "repair-plan.json").read_text(encoding="utf-8"))
    Draft202012Validator(
        _schema("history-campaign-repair-preparation-request.schema.json"),
        format_checker=FormatChecker(),
    ).validate(request)
    Draft202012Validator(
        _schema("history-campaign-repair-preparation-child.schema.json"),
        format_checker=FormatChecker(),
    ).validate(child)
    Draft202012Validator(
        _schema("history-campaign-repair-preparation.schema.json"),
        format_checker=FormatChecker(),
    ).validate(manifest)
    repair_schema = json.loads(
        (ROOT / "schemas" / "evidence" / "v1" / "bybit-1m-gap-repair-plan.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(repair_schema, format_checker=FormatChecker()).validate(plan)
    assert request["policy"] == campaign_repairs.PREPARATION_POLICY
    assert manifest["inventory"]["passed_count"] == 1
    assert manifest["inventory"]["total_missing_minute_count"] == 1
    assert manifest["inventory"]["planned_max_http_requests"] == 1
    assert "AAAUSDT" not in json.dumps(manifest)

    monkeypatch.setattr(
        campaign_repairs,
        "build_completed_history_coverage_audit",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("completed checkpoint repeated a semantic child audit")
        ),
    )
    resumed = _prepare(tmp_path, source, publication_plan, completed, aggregate_path)
    assert resumed.existing_complete is True
    assert resumed.manifest_sha256 == prepared.manifest_sha256
    verified = verify_completed_history_campaign_repair_preparation(
        completed.publication_root,
        source.campaign_root,
        aggregate_path,
        tmp_path / "registry.json",
        tmp_path / "capacity.json",
        publication_plan.store_root,
        root,
    )
    assert verified.existing_complete is True

    child["task_count"] = 2
    (child_root / "result.json").write_text(json.dumps(child), encoding="utf-8")
    with pytest.raises(HistoryCampaignRepairPreparationError, match="receipt does not verify"):
        verify_completed_history_campaign_repair_preparation(
            completed.publication_root,
            source.campaign_root,
            aggregate_path,
            tmp_path / "registry.json",
            tmp_path / "capacity.json",
            publication_plan.store_root,
            root,
        )


def test_preparation_preserves_ineligible_reason_without_writing_repair_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, publication_plan, completed = _published_gap_campaign(tmp_path)
    original = campaign_coverage.build_completed_history_coverage_audit

    def quarantined(*args, **kwargs):  # type: ignore[no-untyped-def]
        audit = original(*args, **kwargs)
        if audit.passed:
            return audit
        payload = dict(audit.payload)
        missing = payload["quality"]["missing_minute_count"]  # type: ignore[index]
        payload["reason_policy"] = {
            "accepted_reason_codes": [],
            "observed_reason_counts": {"quarantined_source_row": missing},
            "unaccepted_reason_codes": ["quarantined_source_row"],
            "unknown_reason_count": 0,
        }
        payload["content_sha256"] = canonical_sha256(
            {key: value for key, value in payload.items() if key != "content_sha256"}
        )
        return CoverageAudit(payload=payload, passed=False, gap_ranges=audit.gap_ranges)

    monkeypatch.setattr(
        campaign_coverage,
        "build_completed_history_coverage_audit",
        quarantined,
    )
    aggregate_path = _aggregate_audit(tmp_path, source, publication_plan, completed)
    monkeypatch.setattr(
        campaign_repairs,
        "build_completed_history_coverage_audit",
        quarantined,
    )
    prepared = _prepare(tmp_path, source, publication_plan, completed, aggregate_path)

    assert prepared.status == "complete-with-ineligible-candle-children"
    assert prepared.eligible_candle_count == 0
    assert prepared.ineligible_candle_count == 1
    child_root = prepared.preparation_root / "children" / "000000"
    result = json.loads((child_root / "result.json").read_text(encoding="utf-8"))
    assert result["classification"] == "reason-policy-incompatible"
    assert result["repair_plan_artifact_sha256"] is None
    assert not (child_root / "repair-plan.json").exists()


def test_preparation_delegates_blocked_funding_without_recomputing_candles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = completed_source_campaign(tmp_path)
    publication_plan = preflight_publication(tmp_path, source.campaign_root)
    completed = execute_publication(publication_plan)
    original = campaign_coverage.build_completed_funding_coverage_audit

    def blocked_funding(*args, **kwargs):  # type: ignore[no-untyped-def]
        audit = original(*args, **kwargs)
        payload = dict(audit.payload)
        payload["status"] = "blocked"
        payload["reason_policy"] = {
            "accepted_reason_codes": [],
            "observed_reason_counts": {"unexplained_interval_change": 1},
            "unaccepted_reason_codes": ["unexplained_interval_change"],
            "unknown_reason_count": 0,
        }
        payload["content_sha256"] = canonical_sha256(
            {key: value for key, value in payload.items() if key != "content_sha256"}
        )
        return FundingCoverageAudit(
            payload=payload,
            passed=False,
            anomaly_records=audit.anomaly_records,
        )

    monkeypatch.setattr(
        campaign_coverage,
        "build_completed_funding_coverage_audit",
        blocked_funding,
    )
    aggregate_path = _aggregate_audit(tmp_path, source, publication_plan, completed)
    monkeypatch.setattr(
        campaign_repairs,
        "build_completed_history_coverage_audit",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("passed candles or blocked funding were recomputed")
        ),
    )
    prepared = _prepare(tmp_path, source, publication_plan, completed, aggregate_path)

    assert prepared.status == "complete-no-blocked-candle-children"
    assert prepared.blocked_candle_count == 0
    assert prepared.repair_plan_count == 0
    assert not (prepared.preparation_root / "children").exists()
    manifest = json.loads(prepared.manifest_path.read_text(encoding="utf-8"))
    assert manifest["inventory"]["blocked_funding_count"] == 1
    assert [item["classification"] for item in manifest["children"]] == [
        "not-blocked",
        "funding-repair-separate",
    ]


def test_campaign_repair_cli_exposes_prepare_and_verify_commands() -> None:
    prepare_args = command_parser().parse_args(
        [
            "prepare-history-campaign-repairs",
            "--publication-root",
            "publication",
            "--campaign-root",
            "campaign",
            "--coverage-audit",
            "coverage.json",
            "--instrument-registry",
            "registry.json",
            "--capacity-evidence",
            "capacity.json",
            "--store-root",
            "store",
            "--preparation-root",
            "private-preparation",
            "--planner-software-identity",
            PLANNER_IDENTITY,
        ]
    )
    verify_args = command_parser().parse_args(
        [
            "verify-history-campaign-repairs",
            "--publication-root",
            "publication",
            "--campaign-root",
            "campaign",
            "--coverage-audit",
            "coverage.json",
            "--instrument-registry",
            "registry.json",
            "--capacity-evidence",
            "capacity.json",
            "--store-root",
            "store",
            "--preparation-root",
            "private-preparation",
        ]
    )

    assert prepare_args.handler.__name__ == "_prepare_history_campaign_repairs"
    assert verify_args.handler.__name__ == "_verify_history_campaign_repairs"
