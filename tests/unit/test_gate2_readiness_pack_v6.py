from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from grid_contracts.canonical import canonical_sha256
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

import benchmarks.gate2_readiness_pack_v6 as readiness_module
from benchmarks.gate2_readiness_pack_v6 import (
    CANDLE_SPEC,
    FUNDING_POLICY_SPEC,
    FUNDING_SPEC,
    LEGACY_SPEC,
    LIFECYCLE_SPEC,
    PERFORMANCE_SPEC,
    PRIOR_SPEC,
    Gate2ReadinessV6Error,
    build_gate2_readiness_pack_v6,
)
from tests.unit.test_gate2_readiness_pack_v4 import SHA, _candle, _performance, _prior
from tests.unit.test_gate2_readiness_pack_v5 import _legacy, _lifecycle, _policy

ROOT = Path(__file__).parents[2]
GENERATED = "2026-08-24T21:00:00Z"
IMPLEMENTATION = f"git:{'b' * 40}"


def _funding_v2() -> dict[str, Any]:
    return {
        "bindings": {
            "candle_evidence_artifact_sha256": SHA["candle_artifact"],
            "capacity_evidence_sha256": SHA["capacity"],
            "instrument_registry_sha256": SHA["registry"],
            "private_anomaly_sha256": "8" * 64,
        },
        "inventory": {
            "canonical_dataset_count": 1,
            "canonical_row_count": 4,
            "source_count": 1,
            "symbol_count": 1,
        },
        "performance": {"envelope": {"owner_review_required": True, "qualified": False}},
        "quality": {
            "funding": {
                "duplicate_key_count": 0,
                "empty_range_page_count": 1,
                "internal_interval_mismatch_count": 0,
                "interval_change_count": 2,
                "lifecycle_failure_count": 0,
                "predecessor_interval_mismatch_count": 0,
                "unexpected_timestamp_count": 0,
                "unrequested_row_count": 0,
            }
        },
        "terminal_partition": {
            "funding_coverage_complete": False,
            "predecessor_proven_count": 1,
            "private_anomaly_sha256": "8" * 64,
            "symbol_count": 2,
            "terminal_insufficient_one_count": 1,
            "terminal_insufficient_zero_count": 0,
        },
        "universe": {
            "candle_symbol_count": 2,
            "full_scope_exact": False,
            "funding_symbol_count": 1,
            "predecessor_partition_exact": True,
            "terminal_insufficient_symbol_count": 1,
        },
    }


def _record(spec: readiness_module.SourceSpec, name: str, artifact_sha256: str) -> dict[str, str]:
    return {
        "artifact": f"{name}.json",
        "artifact_sha256": artifact_sha256,
        "content_sha256": "7" * 64,
        "contract": spec.contract,
        "status": spec.status,
    }


def _build(
    monkeypatch: pytest.MonkeyPatch,
    *,
    funding: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    prior_artifact_sha256: str = readiness_module.EXPECTED_V3_ARTIFACT_SHA256,
) -> dict[str, Any]:
    legacy_record = _record(
        LEGACY_SPEC,
        "legacy",
        cast(str, LEGACY_SPEC.expected_artifact_sha256),
    )
    sources = {
        PRIOR_SPEC.contract: (
            _prior(),
            {
                **_record(PRIOR_SPEC, "prior-v3", prior_artifact_sha256),
                "content_sha256": readiness_module.EXPECTED_V3_CONTENT_SHA256,
            },
        ),
        CANDLE_SPEC.contract: (
            _candle(),
            _record(CANDLE_SPEC, "candles", SHA["candle_artifact"]),
        ),
        FUNDING_SPEC.contract: (
            funding or _funding_v2(),
            _record(FUNDING_SPEC, "funding-v2", "9" * 64),
        ),
        PERFORMANCE_SPEC.contract: (
            _performance(),
            _record(PERFORMANCE_SPEC, "performance", "a" * 64),
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
            _lifecycle(legacy_record),
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
    return build_gate2_readiness_pack_v6(
        implementation_identity=IMPLEMENTATION,
        generated_at_utc=GENERATED,
        prior_readiness_path=Path("prior-v3.json"),
        candle_evidence_path=Path("candles.json"),
        funding_evidence_v2_path=Path("funding-v2.json"),
        catalog_performance_path=Path("performance.json"),
        funding_policy_path=Path("policy.json"),
        legacy_listing_path=Path("legacy.json"),
        lifecycle_coverage_path=Path("lifecycle.json"),
        repo_root=ROOT,
    )


def test_gate2_readiness_v6_preserves_gate_and_exposes_terminal_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _build(monkeypatch)
    schema = json.loads(
        (ROOT / "schemas/evidence/v6/gate2-readiness-pack.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded = hash_input.pop("content_sha256")
    assert embedded == canonical_sha256(hash_input)
    assert payload["gate_2"] == readiness_module.EXPECTED_GATE
    assert payload["criteria"] == _prior()["criteria"]
    assert payload["readiness_counts"] == readiness_module.EXPECTED_READINESS_COUNTS
    current = payload["observations"]["current_universe"]
    assert current["funding_full_scope_exact"] is False
    assert current["funding_predecessor_proven_count"] == 1
    assert current["funding_terminal_insufficient_count"] == 1
    assert (
        payload["observations"]["owner_review"]["funding_availability_owner_disposition"]
        == "pending"
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
        '"funding_rate"',
    ):
        assert forbidden not in rendered


def test_gate2_readiness_v6_rejects_partition_or_prior_substitution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    funding = _funding_v2()
    funding["universe"]["terminal_insufficient_symbol_count"] = 2
    with pytest.raises(Gate2ReadinessV6Error, match="does not reconcile"):
        _build(monkeypatch, funding=funding)

    with pytest.raises(Gate2ReadinessV6Error, match="differs from the accepted source"):
        _build(monkeypatch, prior_artifact_sha256="f" * 64)


def test_gate2_readiness_v6_rejects_unexplained_policy_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _policy()
    policy["quality"]["unexplained_interval_change_count"] = 1
    with pytest.raises(Gate2ReadinessV6Error, match="does not explain every"):
        _build(monkeypatch, policy=policy)


def test_gate2_readiness_v6_verifies_exact_committed_governance_sources() -> None:
    cases = (
        ("m2-gate2-readiness-pack-v3-20260814.json", PRIOR_SPEC),
        ("m2-funding-cadence-policy-20260815.json", FUNDING_POLICY_SPEC),
        ("m2-legacy-listing-event-evidence-20260815.json", LEGACY_SPEC),
        ("m2-announcement-lifecycle-coverage-20260815.json", LIFECYCLE_SPEC),
    )
    for artifact, spec in cases:
        path = ROOT / "benchmarks" / "results" / artifact
        payload, record = readiness_module._verify_source(path, spec, ROOT)
        assert record["artifact_sha256"] == spec.expected_artifact_sha256
        assert record["content_sha256"] == payload["content_sha256"]


def test_gate2_readiness_v6_cli_returns_two_after_blocked_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "readiness-v6.json"
    published = False

    def publish(**_arguments: object) -> dict[str, Any]:
        nonlocal published
        published = True
        return {
            "readiness_counts": {"blocked_criterion_count": 3},
            "status": "blocked-terminal-funding-evidence-awaiting-owner-decision",
        }

    monkeypatch.setattr(readiness_module, "publish_gate2_readiness_pack_v6", publish)
    monkeypatch.setattr(
        "sys.argv",
        [
            "gate2-readiness-v6",
            "--implementation-identity",
            IMPLEMENTATION,
            "--prior-readiness-v3",
            "prior.json",
            "--candle-evidence",
            "candles.json",
            "--funding-evidence-v2",
            "funding.json",
            "--catalog-performance",
            "performance.json",
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
