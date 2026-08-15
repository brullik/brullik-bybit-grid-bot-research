from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from grid_contracts.canonical import canonical_sha256
from grid_data.evidence import publish_evidence
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

import benchmarks.gate2_readiness_pack_v5 as readiness_module
from benchmarks.gate2_readiness_pack_v5 import (
    FUNDING_POLICY_SPEC,
    LEGACY_SPEC,
    LIFECYCLE_SPEC,
    PRIOR_SPEC,
    Gate2ReadinessV5Error,
    build_gate2_readiness_pack_v5,
)

ROOT = Path(__file__).parents[2]
GENERATED = "2026-08-15T04:00:00Z"
IMPLEMENTATION = f"git:{'a' * 40}"
REGISTRY_ARTIFACT = "1" * 64
REGISTRY_CONTENT = "2" * 64


def _v3() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            (ROOT / "benchmarks/results/m2-gate2-readiness-pack-v3-20260814.json").read_text(
                encoding="utf-8"
            )
        ),
    )


def _prior() -> dict[str, Any]:
    v3 = _v3()
    return {
        "assurances": {"current_universe_scope_reconciled": True},
        "bindings": {
            "implementation_identity": readiness_module.EXPECTED_V4_IMPLEMENTATION,
            "prior_readiness_artifact_sha256": readiness_module.EXPECTED_V3_ARTIFACT_SHA256,
            "prior_readiness_content_sha256": readiness_module.EXPECTED_V3_CONTENT_SHA256,
            "source_chain_sha256": "3" * 64,
        },
        "criteria": v3["criteria"],
        "criteria_source": v3["criteria_source"],
        "gate_2": readiness_module.EXPECTED_GATE,
        "observations": {
            "current_universe_candles": {
                "catalog_dataset_count": 12,
                "instrument_count": 6,
                "missing_minute_count": 7,
            },
            "current_universe_catalog_performance": {
                "deterministic_repeat_equal": True,
                "first_pass_rows_per_second": 100,
                "repeat_pass_rows_per_second": 120,
            },
            "current_universe_funding": {
                "canonical_dataset_count": 6,
                "interval_change_count": 11,
            },
            "owner_review": {
                "blocked_criterion_count": 3,
                "envelope_qualified": False,
                "owner_review_required": True,
                "unique_blocker_count": 7,
            },
        },
        "readiness_counts": v3["readiness_counts"],
        "sources": {},
        "storage_policy": v3["storage_policy"],
    }


def _policy() -> dict[str, Any]:
    return {
        "quality": {
            "affected_series_count": 5,
            "completed_hourly_episode_count": 4,
            "coverage_audit_count": 4,
            "explained_interval_change_count": 11,
            "observed_interval_change_count": 11,
            "open_hourly_episode_count": 1,
            "policy_consistent_series_count": 5,
            "series_count": 86,
            "unexplained_interval_change_count": 0,
        }
    }


def _legacy() -> dict[str, Any]:
    return {
        "bindings": {
            "instrument_registry_artifact_sha256": REGISTRY_ARTIFACT,
            "instrument_registry_content_sha256": REGISTRY_CONTENT,
        },
        "quality": {
            "official_document_count": 3,
            "official_document_selected_match_count": 5,
            "selected_instrument_count": 5,
            "trade_first_candle": {
                "event_day_match_count": 4,
                "first_candle_before_event_day_count": 1,
            },
        },
    }


def _lifecycle(legacy_record: dict[str, str]) -> dict[str, Any]:
    return {
        "archive_sources": [
            {"announcement_type": "new_crypto", "item_count": 1692},
            {"announcement_type": "delistings", "item_count": 460},
        ],
        "bindings": {
            "instrument_registry_artifact_sha256": REGISTRY_ARTIFACT,
            "instrument_registry_content_sha256": REGISTRY_CONTENT,
        },
        "blocker_codes": readiness_module.EXPECTED_LIFECYCLE_BLOCKERS,
        "legacy_evidence": {
            "remaining_pre_archive_listing_instrument_count": 168,
            "selected_instrument_count": 5,
            "source": dict(legacy_record),
        },
        "matching": {
            "delisting": {
                "ambiguous_instrument_count": 2,
                "eligible_instrument_count": 297,
                "outside_archive_instrument_count": 6,
                "unique_match_instrument_count": 255,
                "unmatched_instrument_count": 40,
            },
            "listing": {
                "ambiguous_instrument_count": 91,
                "eligible_instrument_count": 808,
                "outside_archive_instrument_count": 173,
                "unique_match_instrument_count": 633,
                "unmatched_instrument_count": 84,
            },
            "record_matching_complete": False,
        },
        "process": {
            "announcement_text_persisted": False,
            "market_data_request_count": 0,
            "private_endpoint_request_count": 0,
            "response_count": 108,
            "transport_max_attempts": 1,
        },
        "scope": {"campaign_request_count": 3, "selected_instrument_count": 981},
    }


def _record(spec: readiness_module.SourceSpec, name: str, artifact_sha256: str) -> dict[str, str]:
    return {
        "artifact": f"{name}.json",
        "artifact_sha256": artifact_sha256,
        "content_sha256": "4" * 64,
        "contract": spec.contract,
        "status": spec.status,
    }


def _build(
    monkeypatch: pytest.MonkeyPatch,
    *,
    prior: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    lifecycle_mutator: str | None = None,
) -> dict[str, Any]:
    legacy_record = _record(
        LEGACY_SPEC,
        "legacy",
        cast(str, LEGACY_SPEC.expected_artifact_sha256),
    )
    lifecycle = _lifecycle(legacy_record)
    if lifecycle_mutator == "legacy-content":
        lifecycle["legacy_evidence"]["source"]["content_sha256"] = "f" * 64
    sources = {
        PRIOR_SPEC.contract: (
            prior or _prior(),
            _record(PRIOR_SPEC, "prior-v4", "5" * 64),
        ),
        FUNDING_POLICY_SPEC.contract: (
            policy or _policy(),
            _record(
                FUNDING_POLICY_SPEC,
                "policy",
                cast(str, FUNDING_POLICY_SPEC.expected_artifact_sha256),
            ),
        ),
        LEGACY_SPEC.contract: (_legacy(), legacy_record),
        LIFECYCLE_SPEC.contract: (
            lifecycle,
            _record(
                LIFECYCLE_SPEC,
                "lifecycle",
                cast(str, LIFECYCLE_SPEC.expected_artifact_sha256),
            ),
        ),
    }

    def verify_source(
        _path: Path,
        spec: readiness_module.SourceSpec,
        _repo_root: Path,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        return sources[spec.contract]

    monkeypatch.setattr(readiness_module, "_verify_source", verify_source)
    return build_gate2_readiness_pack_v5(
        implementation_identity=IMPLEMENTATION,
        generated_at_utc=GENERATED,
        prior_readiness_path=Path("prior.json"),
        funding_policy_path=Path("policy.json"),
        legacy_listing_path=Path("legacy.json"),
        lifecycle_coverage_path=Path("lifecycle.json"),
        repo_root=ROOT,
    )


def test_gate2_readiness_v5_consolidates_evidence_without_promoting_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _build(monkeypatch)
    schema = json.loads(
        (ROOT / "schemas/evidence/v5/gate2-readiness-pack.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded = hash_input.pop("content_sha256")
    assert embedded == canonical_sha256(hash_input)
    assert payload["gate_2"] == readiness_module.EXPECTED_GATE
    assert payload["criteria"] == _v3()["criteria"]
    assert payload["observations"]["funding_cadence_policy"] == {
        "affected_series_count": 5,
        "completed_hourly_episode_count": 4,
        "coverage_audit_count": 4,
        "explained_interval_change_count": 11,
        "open_hourly_episode_count": 1,
        "series_count": 86,
        "unexplained_interval_change_count": 0,
    }
    assert (
        payload["observations"]["official_lifecycle_coverage"][
            "remaining_pre_archive_listing_instrument_count"
        ]
        == 168
    )
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
        "announcements.bybit.com",
    ):
        assert forbidden not in rendered


def test_gate2_readiness_v5_rejects_prior_gate_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prior = _prior()
    prior["gate_2"] = {**readiness_module.EXPECTED_GATE, "status": "open"}
    with pytest.raises(Gate2ReadinessV5Error, match="prior Gate 2 decision changed"):
        _build(monkeypatch, prior=prior)


def test_gate2_readiness_v5_rejects_cross_bound_legacy_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(Gate2ReadinessV5Error, match="binds another legacy"):
        _build(monkeypatch, lifecycle_mutator="legacy-content")


def test_gate2_readiness_v5_rejects_unexplained_funding_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _policy()
    policy["quality"]["unexplained_interval_change_count"] = 1
    with pytest.raises(Gate2ReadinessV5Error, match="does not explain every"):
        _build(monkeypatch, policy=policy)


def test_gate2_readiness_v5_verifies_exact_committed_later_sources() -> None:
    cases = (
        ("m2-funding-cadence-policy-20260815.json", FUNDING_POLICY_SPEC),
        ("m2-legacy-listing-event-evidence-20260815.json", LEGACY_SPEC),
        ("m2-announcement-lifecycle-coverage-20260815.json", LIFECYCLE_SPEC),
    )
    for artifact, spec in cases:
        path = ROOT / "benchmarks" / "results" / artifact
        payload, record = readiness_module._verify_source(path, spec, ROOT)
        assert record["artifact_sha256"] == spec.expected_artifact_sha256
        assert record["content_sha256"] == payload["content_sha256"]


def test_gate2_readiness_v5_reconciles_committed_policy_and_lifecycle_sources() -> None:
    results = ROOT / "benchmarks" / "results"
    policy, _policy_record = readiness_module._verify_source(
        results / "m2-funding-cadence-policy-20260815.json",
        FUNDING_POLICY_SPEC,
        ROOT,
    )
    legacy, legacy_record = readiness_module._verify_source(
        results / "m2-legacy-listing-event-evidence-20260815.json",
        LEGACY_SPEC,
        ROOT,
    )
    lifecycle, _lifecycle_record = readiness_module._verify_source(
        results / "m2-announcement-lifecycle-coverage-20260815.json",
        LIFECYCLE_SPEC,
        ROOT,
    )
    assert readiness_module._verify_policy(policy)["unexplained_interval_change_count"] == 0
    observation = readiness_module._verify_lifecycle(
        lifecycle,
        legacy,
        legacy_record=legacy_record,
    )
    assert observation["selected_instrument_count"] == 981
    assert observation["remaining_pre_archive_listing_instrument_count"] == 168


def test_gate2_readiness_v5_rejects_resealed_policy_substitution(tmp_path: Path) -> None:
    source = ROOT / "benchmarks/results/m2-funding-cadence-policy-20260815.json"
    payload = cast(dict[str, Any], json.loads(source.read_text(encoding="utf-8")))
    payload["generated_at_utc"] = "2026-08-15T04:00:00Z"
    payload["content_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    artifact, _receipt = publish_evidence(tmp_path / "resealed-policy.json", payload)
    with pytest.raises(Gate2ReadinessV5Error, match="differs from the accepted evidence"):
        readiness_module._verify_source(artifact, FUNDING_POLICY_SPEC, ROOT)


def test_gate2_readiness_v5_cli_returns_two_after_negative_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "readiness-v5.json"
    published = False

    def publish(**_arguments: object) -> dict[str, Any]:
        nonlocal published
        published = True
        return {
            "readiness_counts": {"blocked_criterion_count": 3},
            "status": "blocked-consolidated-evidence-awaiting-owner-decision",
        }

    monkeypatch.setattr(readiness_module, "publish_gate2_readiness_pack_v5", publish)
    monkeypatch.setattr(
        "sys.argv",
        [
            "gate2-readiness-v5",
            "--implementation-identity",
            IMPLEMENTATION,
            "--prior-readiness-v4",
            "prior.json",
            "--funding-cadence-policy",
            "policy.json",
            "--legacy-listing-evidence",
            "legacy.json",
            "--lifecycle-coverage",
            "lifecycle.json",
            "--output",
            str(output),
        ],
    )
    assert readiness_module.main() == 2
    assert published
