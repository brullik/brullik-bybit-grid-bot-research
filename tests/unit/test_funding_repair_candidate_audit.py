from __future__ import annotations

import json
from pathlib import Path

import pytest
from grid_contracts.canonical import canonical_sha256
from grid_data import funding_repair_candidate_audit as candidate_audit_module
from grid_data.evidence import publish_evidence
from grid_data.funding_acquisition import FundingAcquisitionError
from grid_data.funding_repair_candidate_audit import (
    FundingRepairCandidateAuditError,
    FundingRepairCandidateInput,
    build_funding_repair_candidate_audit,
    build_funding_repair_candidate_evidence,
    verify_funding_repair_candidate_audit,
    verify_funding_repair_candidate_evidence,
)
from jsonschema import Draft202012Validator, FormatChecker

from tests.unit.test_funding_acquisition import FakeFundingClient
from tests.unit.test_funding_repair_plan import (
    MissingSettlementClient,
    TrailingUnexplainedChangeClient,
    blocked_audit_fixture,
)

ROOT = Path(__file__).parents[2]
SOFTWARE_IDENTITY = f"git:{'7' * 40}"


def candidate_fixture(
    tmp_path: Path,
    *,
    client_factory: type[FakeFundingClient] = MissingSettlementClient,
) -> tuple[FundingRepairCandidateInput, Path, Path]:
    audit, job_root, registry, capacity, store = blocked_audit_fixture(
        tmp_path,
        client_factory=client_factory,
    )
    return FundingRepairCandidateInput(audit, job_root, registry), capacity, store


def test_candidate_audit_classifies_eligible_and_non_isolated_inputs(
    tmp_path: Path,
) -> None:
    eligible, capacity, store = candidate_fixture(tmp_path / "eligible")
    eligible_audit = build_funding_repair_candidate_audit(
        (eligible,),
        capacity,
        store,
        auditor_software_identity=SOFTWARE_IDENTITY,
        generated_at_utc="2026-08-14T02:00:00Z",
    )
    assert eligible_audit["classification_counts"] == {
        "eligible": 1,
        "non-isolated-or-non-integer-chronology": 0,
    }
    assert eligible_audit["candidate_settlement_count"] == 1
    assert eligible_audit["interval_change_count"] == 2
    assert eligible_audit["planned_max_http_requests"] == 4
    assert eligible_audit["task_count"] == 1
    assert eligible_audit["status"] == "eligible-candidates-observed"

    non_isolated, capacity, store = candidate_fixture(
        tmp_path / "non-isolated",
        client_factory=TrailingUnexplainedChangeClient,
    )
    audit = build_funding_repair_candidate_audit(
        (non_isolated,),
        capacity,
        store,
        auditor_software_identity=SOFTWARE_IDENTITY,
        generated_at_utc="2026-08-14T02:00:00Z",
    )

    assert audit["audit_count"] == 1
    assert audit["classification_counts"] == {
        "eligible": 0,
        "non-isolated-or-non-integer-chronology": 1,
    }
    assert audit["candidate_settlement_count"] == 0
    assert audit["interval_change_count"] == 1
    assert audit["planned_max_http_requests"] == 0
    assert audit["task_count"] == 0
    assert audit["status"] == "no-eligible-candidates"


def test_no_candidate_evidence_is_sanitized_receipted_and_reproducible(
    tmp_path: Path,
) -> None:
    candidate, capacity, store = candidate_fixture(
        tmp_path,
        client_factory=TrailingUnexplainedChangeClient,
    )
    audit = build_funding_repair_candidate_audit(
        (candidate,),
        capacity,
        store,
        auditor_software_identity=SOFTWARE_IDENTITY,
        generated_at_utc="2026-08-14T02:01:00Z",
    )
    audit_path, _ = publish_evidence(tmp_path / "private-audit.json", audit)
    assert (
        verify_funding_repair_candidate_audit(
            audit_path,
            (candidate,),
            capacity,
            store,
        )
        == audit
    )

    evidence = build_funding_repair_candidate_evidence(
        audit_path,
        (candidate,),
        capacity,
        store,
        publisher_software_identity=SOFTWARE_IDENTITY,
    )
    schema = json.loads(
        (
            ROOT
            / "schemas"
            / "evidence"
            / "v1"
            / "phase2-funding-repair-candidate-audit.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(evidence)
    without_hash = dict(evidence)
    content_hash = without_hash.pop("content_sha256")
    assert content_hash == canonical_sha256(without_hash)
    assert evidence["status"] == "verified-no-eligible-funding-repair-candidates"
    rendered = json.dumps(evidence).lower()
    assert "aaausdt" not in rendered
    assert "funding-2026-01-b01-repair-plan" not in rendered
    assert "1767225600000" not in rendered
    assert "c:\\" not in rendered

    evidence_path, _ = publish_evidence(tmp_path / "public-evidence.json", evidence)
    assert (
        verify_funding_repair_candidate_evidence(
            evidence_path,
            audit_path,
            (candidate,),
            capacity,
            store,
        )
        == evidence
    )


def test_candidate_audit_fails_closed_on_duplicate_input_or_other_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate, capacity, store = candidate_fixture(tmp_path / "first")
    with pytest.raises(FundingRepairCandidateAuditError, match="must be unique"):
        build_funding_repair_candidate_audit(
            (candidate, candidate),
            capacity,
            store,
            auditor_software_identity=SOFTWARE_IDENTITY,
            generated_at_utc="2026-08-14T02:02:00Z",
        )

    def unsupported_plan(*args: object, **kwargs: object) -> None:
        raise FundingAcquisitionError("other audit blockers remain")

    monkeypatch.setattr(
        candidate_audit_module,
        "build_funding_repair_plan",
        unsupported_plan,
    )
    with pytest.raises(FundingRepairCandidateAuditError, match="failed verification"):
        build_funding_repair_candidate_audit(
            (candidate,),
            capacity,
            store,
            auditor_software_identity=SOFTWARE_IDENTITY,
            generated_at_utc="2026-08-14T02:03:00Z",
        )
