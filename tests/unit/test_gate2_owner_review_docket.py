from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks import gate2_owner_review_docket as docket_module
from benchmarks.gate2_owner_review_docket import (
    EXPECTED_BLOCKERS,
    EXPECTED_GATE,
    EXPECTED_OWNER_REVIEW,
    EXPECTED_READINESS_COUNTS,
    EXPECTED_V5_IMPLEMENTATION,
    Gate2OwnerReviewDocketError,
    build_gate2_owner_review_docket,
)

ROOT = Path(__file__).parents[2]
IMPLEMENTATION = "git:" + "a" * 40


def _criteria() -> list[dict[str, Any]]:
    return [
        {
            "blocker_codes": EXPECTED_BLOCKERS[:2],
            "criterion_id": "deterministic-rerun-and-repair",
            "criterion_text": "deterministic re-run and repair",
            "evidence_roles": [
                "full-history-landing",
                "full-history-canonical-publication",
                "canonical-integrity-fault-injection",
                "candle-gap-repair-execution",
                "funding-repair-candidate-audit",
            ],
            "readiness": "blocked",
        },
        {
            "blocker_codes": [],
            "criterion_id": "preflight-before-mutation",
            "criterion_text": "no mutation before preflight succeeds",
            "evidence_roles": [
                "full-history-preflight-performance",
                "full-history-canonical-publication",
                "full-history-catalog",
                "stale-output-fault-injection",
                "trade-compaction-50x90",
            ],
            "readiness": "evidence-ready",
        },
        {
            "blocker_codes": [],
            "criterion_id": "no-duplicate-or-conflicting-keys",
            "criterion_text": "no duplicate/conflicting canonical keys",
            "evidence_roles": [
                "full-history-coverage-audit",
                "full-history-catalog",
                "coverage-audit-100x31",
                "trade-compaction-50x90",
                "canonical-integrity-fault-injection",
            ],
            "readiness": "evidence-ready",
        },
        {
            "blocker_codes": [],
            "criterion_id": "stale-building-output-detected",
            "criterion_text": "stale building outputs detected",
            "evidence_roles": ["stale-output-fault-injection"],
            "readiness": "evidence-ready",
        },
        {
            "blocker_codes": [
                "funding-cadence-policy-unresolved",
                "historical-point-in-time-metadata-missing",
                "official-announcement-history-insufficient",
                "unaccepted-candle-absence-reasons",
            ],
            "criterion_id": "lifecycle-explains-expected-coverage",
            "criterion_text": "expected coverage explained by listing/delisting metadata",
            "evidence_roles": [
                "full-history-coverage-audit",
                "full-history-boundary-diagnostic",
                "candle-gap-repair-execution",
                "announcement-archive-depth",
                "coverage-audit-100x31",
                "funding-repair-candidate-audit",
                "instrument-timeline-current-policy",
            ],
            "readiness": "blocked",
        },
        {
            "blocker_codes": ["full-history-end-to-end-performance-envelope-unqualified"],
            "criterion_id": "performance-within-envelope",
            "criterion_text": "performance remains within measured envelope",
            "evidence_roles": [
                "full-history-landing",
                "full-history-canonical-publication",
                "full-history-boundary-diagnostic",
                "full-history-preflight-performance",
                "full-history-catalog",
                "incremental-catalog-performance",
            ],
            "readiness": "blocked",
        },
    ]


def _v5() -> dict[str, Any]:
    return {
        "bindings": {"implementation_identity": EXPECTED_V5_IMPLEMENTATION},
        "criteria": _criteria(),
        "criteria_source": {
            "artifact": "14_ROADMAP_AND_GATES.md",
            "artifact_sha256": ("492458c7126bb6768dbc1b328ec5959095e67e0cdbf865b7de54b05ecc94f534"),
            "criteria_count": 6,
        },
        "gate_2": EXPECTED_GATE,
        "observations": {
            "current_universe": {
                "catalog_deterministic_repeat_equal": True,
                "catalog_first_pass_rows_per_second": 1_200_000,
                "catalog_repeat_pass_rows_per_second": 1_180_000,
            },
            "funding_cadence_policy": {
                "affected_series_count": 5,
                "explained_interval_change_count": 11,
                "unexplained_interval_change_count": 0,
            },
            "official_lifecycle_coverage": {
                "delisting_ambiguous_instrument_count": 2,
                "delisting_unmatched_instrument_count": 40,
                "listing_ambiguous_instrument_count": 91,
                "listing_unmatched_instrument_count": 84,
                "record_matching_complete": False,
                "remaining_pre_archive_listing_instrument_count": 168,
                "selected_instrument_count": 981,
            },
            "owner_review": EXPECTED_OWNER_REVIEW,
        },
        "readiness_counts": EXPECTED_READINESS_COUNTS,
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_instrument_identities": False,
            "evidence_contains_market_values": False,
            "evidence_contains_runtime_paths": False,
            "runtime_market_artifacts_committed_to_git": False,
        },
    }


def _build(
    monkeypatch: pytest.MonkeyPatch, *, source: dict[str, Any] | None = None
) -> dict[str, Any]:
    source_payload = source or _v5()
    source_record = {
        "artifact": "m2-gate2-readiness-pack-v5-20260815.json",
        "artifact_sha256": "b" * 64,
        "content_sha256": "c" * 64,
        "contract": "grid.gate2-readiness-pack/v5",
        "status": "blocked-consolidated-evidence-awaiting-owner-decision",
    }
    monkeypatch.setattr(
        docket_module,
        "_verify_source",
        lambda *_arguments, **_keywords: (source_payload, source_record),
    )
    return build_gate2_owner_review_docket(
        implementation_identity=IMPLEMENTATION,
        generated_at_utc="2026-08-15T08:00:00Z",
        prior_readiness_v5_path=Path("v5.json"),
        repo_root=ROOT,
    )


def test_owner_review_docket_assigns_every_blocker_once_and_remains_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _build(monkeypatch)

    assert payload["status"] == "pending-explicit-data-quality-owner-decision"
    assert payload["gate_2"] == EXPECTED_GATE
    assert payload["decision_state"] == {
        "data_quality_owner_decision_recorded": False,
        "gate_opening_authorized": False,
        "owner_decision_required": True,
        "phase3_implementation_authorized": False,
        "required_review_item_count": 4,
        "status": "pending",
    }
    review_items = payload["review_items"]
    assigned = [blocker for item in review_items.values() for blocker in item["blocker_codes"]]
    assert sorted(assigned) == EXPECTED_BLOCKERS
    assert len(assigned) == len(set(assigned)) == 7
    assert review_items["deterministic_repair"]["owner_disposition"] == "pending"
    assert review_items["funding_cadence"]["evidence_summary"] == {
        "affected_series_count": 5,
        "explained_interval_change_count": 11,
        "unexplained_interval_change_count": 0,
    }
    assert review_items["performance_envelope"]["evidence_summary"] == {
        "catalog_deterministic_repeat_equal": True,
        "catalog_first_pass_rows_per_second": 1_200_000,
        "catalog_repeat_pass_rows_per_second": 1_180_000,
        "end_to_end_envelope_qualified": False,
    }
    assert payload["assurances"]["automatic_gate_acceptance_performed"] is False
    assert payload["assurances"]["phase3_authorized"] is False


def test_owner_review_docket_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _build(monkeypatch)
    rendered = json.dumps(payload).lower()
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        '"symbol"',
        '"instrument_id"',
        '"dataset_id"',
        '"runtime_path"',
        '"funding_rate"',
        '"market_value"',
    ):
        assert forbidden not in rendered


def test_owner_review_docket_rejects_repair_blocker_assignment_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _v5()
    source["criteria"][0]["blocker_codes"] = ["candle-repair-source-gap-remains"]
    with pytest.raises(Gate2OwnerReviewDocketError, match="blocker assignment changed"):
        _build(monkeypatch, source=source)


def test_owner_review_docket_rejects_prior_owner_disposition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _v5()
    source["observations"]["owner_review"] = {
        **EXPECTED_OWNER_REVIEW,
        "funding_cadence_owner_disposition": "accepted",
    }
    with pytest.raises(Gate2OwnerReviewDocketError, match="owner-review state changed"):
        _build(monkeypatch, source=source)


def test_owner_review_docket_rejects_substituted_v5_implementation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _v5()
    source["bindings"]["implementation_identity"] = "git:" + "d" * 40
    with pytest.raises(Gate2OwnerReviewDocketError, match="implementation identity changed"):
        _build(monkeypatch, source=source)


def test_owner_review_docket_rejects_duplicate_blocker() -> None:
    review_items = {
        "a": {"blocker_codes": EXPECTED_BLOCKERS, "owner_disposition": "pending"},
        "b": {
            "blocker_codes": [EXPECTED_BLOCKERS[0]],
            "owner_disposition": "pending",
        },
        "c": {"blocker_codes": [], "owner_disposition": "pending"},
        "d": {"blocker_codes": [], "owner_disposition": "pending"},
    }
    with pytest.raises(Gate2OwnerReviewDocketError, match="assigned more than once"):
        docket_module._verify_blocker_assignment(review_items)


def test_owner_review_docket_cli_returns_two_after_pending_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "owner-review-docket.json"
    published = False

    def publish(**_arguments: object) -> dict[str, Any]:
        nonlocal published
        published = True
        return {
            "decision_state": {"required_review_item_count": 4},
            "status": "pending-explicit-data-quality-owner-decision",
        }

    monkeypatch.setattr(docket_module, "publish_gate2_owner_review_docket", publish)
    monkeypatch.setattr(
        "sys.argv",
        [
            "gate2-owner-review-docket",
            "--implementation-identity",
            IMPLEMENTATION,
            "--prior-readiness-v5",
            "v5.json",
            "--output",
            str(output),
        ],
    )
    assert docket_module.main() == 2
    assert published
