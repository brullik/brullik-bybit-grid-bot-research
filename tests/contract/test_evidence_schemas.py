from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

from grid_bybit_private.fgrid_validate import (
    EXPECTED_CHECK_CODE,
    FuturesGridValidateRequest,
    build_probe_report,
)
from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_data.evidence import verify_evidence
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[2]


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_all_json_schemas_are_valid_draft_2020_12() -> None:
    for path in sorted((ROOT / "schemas").rglob("*.schema.json")):
        Draft202012Validator.check_schema(load_json(path))


def test_funding_compaction_candidate_audit_matches_schema_receipt_and_redaction() -> None:
    artifact = (
        ROOT / "benchmarks" / "results" / "m2-funding-compaction-candidate-audit-20260814.json"
    )
    schema = load_json(
        ROOT
        / "schemas"
        / "evidence"
        / "v1"
        / "phase2-funding-compaction-candidate-audit.schema.json"
    )
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    content_hash = payload.pop("content_sha256")
    assert content_hash == canonical_sha256(payload)
    payload["content_sha256"] = content_hash
    assert verify_evidence(artifact)
    assert sha256_file(artifact) == (
        "f7c47dabb42a7749c048ed601aa01f760c81d17b22f9fef5dd6225871df1c3c5"
    )
    assert payload["bindings"] == {
        "audit_artifact_sha256": (
            "6256d7dad13559454a35c460073da32c24ab5341bf57e1b19a39805c9fb19bd9"
        ),
        "auditor_software_identity": "git:b57e6b6c328ee7fa5db3812a2fe2b1b7753e07f6",
        "publisher_software_identity": "git:b57e6b6c328ee7fa5db3812a2fe2b1b7753e07f6",
        "store_state_sha256": ("09b699e184f1bb0f052d7214c4321dceebd6f7aef748b99fb1fdc55b6078a79b"),
    }
    assert payload["inventory"] == {
        "dataset_count": 37,
        "multi_parent_partition_count": 1,
        "pair_count": 3,
        "partition_count": 35,
    }
    assert payload["classification_counts"] == {
        "duplicate-or-conflicting-keys": 3,
        "eligible": 0,
        "schema-mismatch": 0,
        "unresolved-settlement-interval": 0,
    }
    assert payload["status"] == "verified-no-eligible-funding-compaction-candidates"
    rendered = json.dumps(payload).lower()
    for forbidden in (
        '"dataset_id"',
        '"funding_rate"',
        '"funding_time_ms"',
        '"instrument_id"',
        '"parents"',
        '"partition"',
        "c:\\",
    ):
        assert forbidden not in rendered


def test_stale_output_fault_injection_matches_schema_receipt_and_redaction() -> None:
    artifact = ROOT / "benchmarks" / "results" / "m2-stale-output-fault-injection-20260814.json"
    schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "phase2-stale-output-fault-injection.schema.json"
    )
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == "8931046401916b97f342e0404a5ce98faf859e63b9a9eb6b21307e322f1685d3"
    assert embedded_hash == canonical_sha256(hash_input)
    assert verify_evidence(artifact)
    assert sha256_file(artifact) == (
        "8cec6fac0cbd1e14eb2bbcc53b4fe9af5d8a07cd6b434f7a31a38b4428688c10"
    )
    assert payload["bindings"] == {
        "implementation_identity": "git:5ba281181e9c92da1aa30cd85dd520e888e11498"
    }
    assert payload["measurement"] == {
        "case_count": 5,
        "detected_count": 5,
        "marker_preserved_count": 5,
        "target_mutation_count": 0,
    }
    cases = payload["cases"]
    assert {case["case_id"] for case in cases} == {
        "canonical-candle-compaction-building",
        "canonical-candle-publication-building",
        "canonical-funding-publication-building",
        "catalog-registration-building",
        "catalog-registration-lock",
    }
    assert all(case["detected"] is True for case in cases)
    assert all(case["marker_preserved"] is True for case in cases)
    assert all(case["target_mutated"] is False for case in cases)
    assert payload["assurances"] == {
        "injected_markers_preserved": True,
        "network_request_performed": False,
        "private_or_live_capability_used": False,
        "production_preflight_functions_exercised": True,
        "target_mutation_observed": False,
        "temporary_fixture_removed": True,
    }
    rendered = artifact.read_text(encoding="utf-8").lower()
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        "authorization",
        "device_identity_sha256",
        '"symbol"',
        '"instrument_id"',
        '"dataset_id"',
        '"runtime_path"',
        '"open"',
        '"volume"',
        "funding_rate",
    ):
        assert forbidden not in rendered


def test_gate2_readiness_pack_matches_schema_receipt_and_remains_blocked() -> None:
    artifact = ROOT / "benchmarks/results/m2-gate2-readiness-pack-20260814.json"
    schema = load_json(ROOT / "schemas/evidence/v1/gate2-readiness-pack.schema.json")
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == "84bef609ab1e2028b2e2df0b08f56803166a4b2630426e5b576058bc6bf2e473"
    assert embedded_hash == canonical_sha256(hash_input)
    assert verify_evidence(artifact)
    assert sha256_file(artifact) == (
        "1deec7db53ebb52b25da8dc18fe96f68233294f1a02dfe01c24b12c49c1e2625"
    )
    assert payload["bindings"] == {
        "implementation_identity": "git:b58e03933096cc35cf4aa3d774147457f13e5e77"
    }
    assert payload["readiness_counts"] == {
        "blocked_criterion_count": 4,
        "criterion_count": 6,
        "evidence_ready_criterion_count": 2,
    }
    assert payload["gate_2"] == {
        "automatic_phase3_authorization": False,
        "blocker_codes": [
            "full-history-campaign-incomplete",
            "full-history-canonical-publication-and-audit-missing",
            "full-history-end-to-end-performance-missing",
            "funding-cadence-policy-unresolved",
            "genuine-candle-gap-repair-evidence-missing",
            "historical-point-in-time-metadata-missing",
            "measured-funding-repair-evidence-missing",
        ],
        "data_quality_owner_decision_required": True,
        "readiness": "blocked-by-missing-evidence",
        "status": "closed-pending-data-quality-owner",
    }
    assert payload["assurances"] == {
        "all_source_content_hashes_verified": True,
        "all_source_receipts_verified": True,
        "all_source_schemas_verified": True,
        "automatic_gate_acceptance_performed": False,
        "criteria_source_hash_verified": True,
        "cross_source_bindings_verified": True,
        "network_request_performed": False,
        "phase3_authorized": False,
        "private_or_live_capability_used": False,
    }
    assert set(payload["sources"]) == {
        "canonical-publication-100x31",
        "coverage-audit-100x31",
        "full-history-preflight-performance",
        "full-history-resume-performance",
        "instrument-timeline-current-policy",
        "landing-long-run-100x31",
        "stale-output-fault-injection",
        "trade-compaction-50x90",
    }
    rendered = artifact.read_text(encoding="utf-8").lower()
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        '"authorization":',
        "device_identity_sha256",
        '"symbol"',
        '"instrument_id"',
        '"dataset_id"',
        '"runtime_path"',
        '"open"',
        '"volume"',
        "funding_rate",
    ):
        assert forbidden not in rendered


def test_gate2_readiness_pack_v2_matches_schema_receipt_and_remains_blocked() -> None:
    artifact = ROOT / "benchmarks/results/m2-gate2-readiness-pack-v2-20260814.json"
    schema = load_json(ROOT / "schemas/evidence/v2/gate2-readiness-pack.schema.json")
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == "306e7aadf51fa8591b62858a45c23152c117ddcdfb7d0990502e796393e89e46"
    assert embedded_hash == canonical_sha256(hash_input)
    assert verify_evidence(artifact)
    assert sha256_file(artifact) == (
        "d28041effc793e2a5c7daf81b3a1f5ae5035804ca342a2efe21632383ffbcc52"
    )
    assert payload["bindings"] == {
        "implementation_identity": "git:847de3e43c0c8411c609eca5f65a279adc42dcbe"
    }
    assert payload["readiness_counts"] == {
        "blocked_criterion_count": 3,
        "criterion_count": 6,
        "evidence_ready_criterion_count": 3,
    }
    assert payload["gate_2"] == {
        "automatic_phase3_authorization": False,
        "blocker_codes": [
            "full-history-end-to-end-performance-envelope-unqualified",
            "funding-cadence-policy-unresolved",
            "genuine-candle-gap-repair-evidence-missing",
            "historical-point-in-time-metadata-missing",
            "measured-funding-repair-evidence-missing",
            "official-announcement-history-insufficient",
            "unaccepted-candle-absence-reasons",
        ],
        "data_quality_owner_decision_required": True,
        "readiness": "blocked-pending-evidence-and-policy",
        "status": "closed-pending-data-quality-owner",
    }
    assert payload["assurances"]["network_request_performed"] is False
    assert payload["assurances"]["automatic_gate_acceptance_performed"] is False
    assert payload["assurances"]["phase3_authorized"] is False
    assert len(payload["sources"]) == 12
    rendered = artifact.read_text(encoding="utf-8").lower()
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        '"authorization":',
        "device_identity_sha256",
        '"symbol"',
        '"instrument_id"',
        '"dataset_id"',
        '"runtime_path"',
        '"open"',
        '"volume"',
        "funding_rate",
    ):
        assert forbidden not in rendered


def test_canonical_integrity_fault_injection_matches_schema_receipt_and_redaction() -> None:
    artifact = ROOT / "benchmarks/results/m2-canonical-integrity-fault-injection-20260814.json"
    schema = load_json(
        ROOT / "schemas/evidence/v1/phase2-canonical-integrity-fault-injection.schema.json"
    )
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == "9dff752b91209daae385473120a06c6235f603ececcc0fe24f013d469752c3d2"
    assert embedded_hash == canonical_sha256(hash_input)
    assert verify_evidence(artifact)
    assert sha256_file(artifact) == (
        "93af2d7b5cf73e7f672a9d846a19bbc858e770cde2ed54780150a1ce2222e8a1"
    )
    assert payload["bindings"] == {
        "implementation_identity": "git:d38ed8e618de9580623aba3de8b26f1ccd5d9c37"
    }
    assert payload["measurement"] == {
        "case_count": 6,
        "detected_count": 6,
        "filesystem_state_preserved_count": 6,
    }
    assert payload["assurances"] == {
        "filesystem_state_preserved_during_verification": True,
        "network_request_performed": False,
        "private_or_live_capability_used": False,
        "production_verifier_functions_exercised": True,
        "retained_market_store_accessed": False,
        "temporary_fixture_removed": True,
    }
    assert {case["case_id"] for case in payload["cases"]} == {
        "canonical-candle-missing-completion-receipt",
        "canonical-candle-missing-parquet",
        "canonical-candle-orphan-file",
        "canonical-funding-missing-completion-receipt",
        "canonical-funding-missing-parquet",
        "canonical-funding-orphan-file",
    }
    assert all(case["detected"] is True for case in payload["cases"])
    assert all(case["filesystem_state_preserved"] is True for case in payload["cases"])
    rendered = artifact.read_text(encoding="utf-8").lower()
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        '"authorization":',
        "device_identity_sha256",
        '"symbol"',
        '"instrument_id"',
        '"dataset_id"',
        '"runtime_path"',
        '"open"',
        '"volume"',
        "funding_rate",
    ):
        assert forbidden not in rendered


def test_public_sample_evidence_matches_schema_and_hashes() -> None:
    artifact = ROOT / "benchmarks" / "results" / "m1-bybit-public-sample.json"
    schema = load_json(ROOT / "schemas" / "evidence" / "v1" / "bybit-public-sample.schema.json")
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    embedded_hash = payload.pop("content_sha256")
    assert embedded_hash == canonical_sha256(payload)
    assert verify_evidence(artifact)


def test_public_benchmark_evidence_matches_schemas_and_receipts() -> None:
    cases = (
        (
            "m1-bybit-demo-validate-conclusion.json",
            "v1/bybit-fgrid-validate-conclusion.schema.json",
        ),
        (
            "m1-bybit-mainnet-validate-conclusion.json",
            "v1/bybit-fgrid-mainnet-validate-conclusion.schema.json",
        ),
        (
            "m1-mainnet-validate-candidates.json",
            "v1/mainnet-validate-candidates.schema.json",
        ),
        ("m1-layout-smoke.json", "v1/layout-benchmark.schema.json"),
        ("m1-layout-out-of-core-smoke.json", "v2/layout-benchmark.schema.json"),
        ("m1-layout-out-of-core-scaled.json", "v2/layout-benchmark.schema.json"),
        (
            "m1-layout-out-of-core-full-candidate.json",
            "v2/layout-benchmark.schema.json",
        ),
        (
            "m1-layout-exact-decision-candidate.json",
            "v3/layout-benchmark.schema.json",
        ),
        ("m1-feature-scaled.json", "v1/feature-benchmark.schema.json"),
        ("m1-feature-reference-candidate.json", "v1/feature-benchmark.schema.json"),
        ("m1-workstation-snapshot.json", "v1/workstation-snapshot.schema.json"),
        ("m1-capacity-projection.json", "v1/capacity-projection.schema.json"),
        (
            "m1-exact-capacity-projection.json",
            "v2/capacity-projection.schema.json",
        ),
        (
            "m1-real-market-capacity-projection.json",
            "v3/capacity-projection.schema.json",
        ),
        (
            "m1-owner-storage-review-workstation-20260812.json",
            "v1/workstation-snapshot.schema.json",
        ),
        (
            "m1-owner-storage-review-capacity-20260812.json",
            "v1/current-universe-capacity.schema.json",
        ),
        (
            "m1-owner-measured-host-qualification-20260812.json",
            "v1/reference-host-qualification.schema.json",
        ),
    )
    for artifact_name, versioned_schema_name in cases:
        artifact = ROOT / "benchmarks" / "results" / artifact_name
        schema = load_json(ROOT / "schemas" / "evidence" / versioned_schema_name)

        Draft202012Validator(schema, format_checker=FormatChecker()).validate(load_json(artifact))
        assert verify_evidence(artifact)


def test_phase2_public_1m_pilot_matches_schema_hash_receipt_and_redaction() -> None:
    artifact = ROOT / "benchmarks" / "results" / "m2-public-1m-canonical-pilot-20260812.json"
    schema = load_json(ROOT / "schemas" / "evidence" / "v1" / "phase2-public-1m-pilot.schema.json")
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    embedded_hash = payload.pop("content_sha256")
    assert embedded_hash == canonical_sha256(payload)
    assert verify_evidence(artifact)
    rendered = artifact.read_text(encoding="utf-8").lower()
    for forbidden in (
        "c:\\",
        "api_key",
        "api_secret",
        "authorization",
        "device_identity",
        '"open"',
        '"volume"',
    ):
        assert forbidden not in rendered


def test_canonical_coverage_audit_matches_schema_hash_receipt_and_redaction() -> None:
    artifact = ROOT / "benchmarks" / "results" / "m2-canonical-coverage-audit-20260812.json"
    schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "canonical-1m-coverage-audit.schema.json"
    )
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    embedded_hash = payload.pop("content_sha256")
    assert embedded_hash == canonical_sha256(payload)
    assert verify_evidence(artifact)
    rendered = artifact.read_text(encoding="utf-8").lower()
    for forbidden in (
        "c:\\",
        "api_key",
        "api_secret",
        "authorization",
        "device_identity",
        '"open"',
        '"volume"',
    ):
        assert forbidden not in rendered


def test_instrument_timeline_summary_matches_schema_hash_receipt_and_redaction() -> None:
    artifact = ROOT / "benchmarks" / "results" / "m2-instrument-timeline-20260813.json"
    schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "instrument-timeline-summary.schema.json"
    )
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == canonical_sha256(hash_input)
    assert verify_evidence(artifact)
    assert payload["status"] == "blocked"
    assert payload["blocker_codes"] == ["partial_source_inventory"]
    assert payload["universe"]["coverage_blocked_instrument_count"] == 0
    rendered = artifact.read_text(encoding="utf-8").lower()
    for forbidden in (
        "c:\\",
        "api_key",
        "api_secret",
        "authorization",
        "device_identity",
        '"records"',
        '"symbol"',
    ):
        assert forbidden not in rendered


def test_current_status_policy_timeline_results_preserve_positive_and_negative_evidence() -> None:
    results = ROOT / "benchmarks" / "results"
    schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "instrument-timeline-summary.schema.json"
    )
    combined_artifact = results / "m2-instrument-timeline-current-policy-20260813.json"
    current_artifact = results / "m2-instrument-timeline-complete-current-20260813.json"
    combined = load_json(combined_artifact)
    current = load_json(current_artifact)

    for artifact, payload in ((combined_artifact, combined), (current_artifact, current)):
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
        hash_input = dict(payload)
        embedded_hash = hash_input.pop("content_sha256")
        assert embedded_hash == canonical_sha256(hash_input)
        assert verify_evidence(artifact)
        assert payload["software_identity"] == ("git:c558a056337915ed83d9d3ce598d463f8af56cac")
        rendered = artifact.read_text(encoding="utf-8").lower()
        for forbidden in (
            "c:\\",
            "api_key",
            "api_secret",
            "authorization",
            "device_identity",
            '"records"',
            '"symbol"',
        ):
            assert forbidden not in rendered

    assert current["status"] == "passed"
    assert current["blocker_codes"] == []
    assert current["timeline"]["snapshot_count"] == 1
    assert current["universe"] == {
        "coverage_blocked_instrument_count": 0,
        "coverage_instrument_count": 1015,
        "delivery_bounded_instrument_count": 303,
        "latest_inventory_status": "complete",
        "latest_status_counts": {"Closed": 303, "PreLaunch": 5, "Trading": 707},
        "latest_usdt_linear_perpetual_count": 1015,
        "open_ended_instrument_count": 712,
        "partial_snapshot_count": 0,
    }

    assert combined["status"] == "blocked"
    assert combined["blocker_codes"] == ["partial_source_inventory"]
    assert combined["timeline"]["snapshot_count"] == 3
    assert combined["universe"]["latest_inventory_status"] == "complete"
    assert combined["universe"]["partial_snapshot_count"] == 2
    assert combined["universe"]["coverage_blocked_instrument_count"] == 0


def test_measured_funding_source_boundary_matches_schema_hash_receipt_and_redaction() -> None:
    artifact = ROOT / "benchmarks/results/m2-funding-source-boundary-5xfull-20260813.json"
    schema = load_json(ROOT / "schemas/evidence/v1/phase2-funding-source-boundary.schema.json")
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == canonical_sha256(hash_input)
    assert verify_evidence(artifact)
    assert payload["process"]["discovery_software_identity"] == (
        "git:149fe395d0ae7efede2dc91bb60f12e70325bee7"
    )
    assert payload["process"]["evidence_software_identity"] == (
        "git:d05ff84dca929e7b40a6edc7c42224293b3ed5ec"
    )
    assert payload["scope"] == {
        "end_ms": 1785542340000,
        "start_ms": 1514764800000,
        "symbol_count": 5,
    }
    assert payload["landing"] == {
        "event_count": 37286,
        "http_attempt_count": 193,
        "page_count": 193,
        "retry_count": 0,
    }
    assert payload["result"] == {
        "canonical_start_proven_count": 5,
        "predecessor_proven_count": 5,
    }
    adaptive = payload["adaptive_throttling"]
    assert adaptive["response_observation_count"] == 193
    assert adaptive["transport_attempt_without_response_count"] == 0
    assert adaptive["rate_limit_event_count"] == 0
    rendered = artifact.read_text(encoding="utf-8").lower()
    for forbidden in (
        "bchusdt",
        "btcusdt",
        "linkusdt",
        "ltcusdt",
        "xtzusdt",
        '"symbol":',
        '"instrument_id":',
        '"fundingrate":',
        '"funding_rate":',
        "1607932800000",
        "1585152000000",
        "1603267200000",
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        "authorization",
        "device_identity",
    ):
        assert forbidden not in rendered


def test_representative_multi_year_campaign_request_is_bounded_and_sanitized() -> None:
    artifact = (
        ROOT
        / "benchmarks"
        / "specifications"
        / "m2-representative-5x24-history-campaign-request-20260813.json"
    )
    schema = load_json(
        ROOT / "schemas" / "market" / "v1" / "public-history-campaign-request.schema.json"
    )
    payload = load_json(artifact)

    Draft202012Validator(schema).validate(payload)
    assert payload["kinds"] == ["trade", "mark", "funding"]
    assert payload["symbols"] == ["BTCUSDT", "UNIUSDT", "FILUSDT", "CHZUSDT", "SUIUSDT"]
    assert (payload["end_ms"] - payload["start_ms"]) // 60_000 + 1 == 1_052_640
    assert payload["target_rps"] == 15
    rendered = artifact.read_text(encoding="utf-8").lower()
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        "authorization",
        "device_identity",
        "instrument_id",
    ):
        assert forbidden not in rendered


def test_representative_multi_year_campaign_evidence_is_bound_and_sanitized() -> None:
    artifact = ROOT / "benchmarks/results/m2-public-history-campaign-5x24-20260813.json"
    schema = load_json(ROOT / "schemas/evidence/v1/phase2-public-history-campaign.schema.json")
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == canonical_sha256(hash_input)
    assert verify_evidence(artifact)
    assert payload["bindings"]["campaign_manifest_sha256"] == (
        "cef361cb5eb04cee9f2c645a5281b06f50b050eaaf327c58d170b725f558485a"
    )
    assert payload["bindings"]["campaign_plan_sha256"] == (
        "ab32162397e396975071ee3a64cdc372b58938c3f1865439b9e93501611d8f4e"
    )
    assert payload["landing"] == {
        "artifact_bytes": 693_425_484,
        "by_kind": [
            {
                "http_request_count": 5_326,
                "job_count": 24,
                "kind": "trade",
                "page_count": 5_325,
                "row_count": 5_263_200,
            },
            {
                "http_request_count": 5_326,
                "job_count": 24,
                "kind": "mark",
                "page_count": 5_325,
                "row_count": 5_263_200,
            },
            {
                "http_request_count": 715,
                "job_count": 24,
                "kind": "funding",
                "page_count": 715,
                "row_count": 10_965,
            },
        ],
        "http_request_count": 11_367,
        "job_count": 72,
        "page_count": 11_365,
        "retry_count": 2,
        "row_count": 10_537_365,
    }
    rendered = artifact.read_text(encoding="utf-8").lower()
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        "authorization",
        "device_identity",
        '"symbol"',
        '"instrument_id"',
        '"open"',
        '"volume"',
        "funding_rate",
    ):
        assert forbidden not in rendered


def test_long_run_throttling_campaign_evidence_is_bound_complete_and_sanitized() -> None:
    artifact = ROOT / "benchmarks/results/m2-public-history-long-run-100x31-20260813.json"
    schema = load_json(ROOT / "schemas/evidence/v1/phase2-public-history-campaign.schema.json")
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == canonical_sha256(hash_input)
    assert verify_evidence(artifact)
    assert payload["bindings"]["campaign_manifest_sha256"] == (
        "a87ef79466ea579c847e500d84d84a3681d45f05d74d301f6a685cca6e358033"
    )
    assert payload["scope"] == {
        "bucket_count": 8,
        "end_ms": 1_785_542_340_000,
        "kind_count": 3,
        "month_count": 1,
        "start_ms": 1_782_864_000_000,
        "symbol_count": 100,
    }
    assert payload["landing"] == {
        "artifact_bytes": 591_702_449,
        "by_kind": [
            {
                "http_request_count": 4_500,
                "job_count": 8,
                "kind": "trade",
                "page_count": 4_500,
                "row_count": 4_464_000,
            },
            {
                "http_request_count": 4_521,
                "job_count": 8,
                "kind": "mark",
                "page_count": 4_500,
                "row_count": 4_464_000,
            },
            {
                "http_request_count": 600,
                "job_count": 8,
                "kind": "funding",
                "page_count": 600,
                "row_count": 10_466,
            },
        ],
        "http_request_count": 9_621,
        "job_count": 24,
        "page_count": 9_600,
        "retry_count": 21,
        "row_count": 8_938_466,
    }
    assert payload["adaptive_throttling"] == {
        "automatic_increase_count": 0,
        "child_job_count": 24,
        "complete_header_observation_count": 0,
        "completed_page_response_coverage_complete": True,
        "configured_target_rps": 15,
        "cooldown_event_count": 0,
        "header_absent_observation_count": 9_600,
        "invalid_header_observation_count": 0,
        "low_headroom_event_count": 0,
        "maximum_child_final_effective_rps": 15,
        "maximum_cooldown_ms": 0,
        "minimum_child_effective_rps": 15,
        "minimum_child_final_effective_rps": 15,
        "policy": "bybit-v5-response-header-decrease-only-v1",
        "rate_limit_event_count": 0,
        "rate_reduction_count": 0,
        "response_observation_classification_complete": True,
        "response_observation_count": 9_600,
        "transport_attempt_accounting_complete": True,
        "transport_attempt_count": 9_621,
        "transport_attempt_without_response_count": 21,
    }
    assert payload["timing"] == {
        "campaign_completed_at_ms": 1_786_639_371_670,
        "campaign_elapsed_ms": 2_643_108,
        "campaign_started_at_ms": 1_786_636_728_562,
        "summed_child_elapsed_ms": 849_023,
        "timed_child_count": 24,
    }
    assert payload["process"]["software_identity"] == (
        "git:580394c4f51c2aeef2a05fd83c90cedb735953b4"
    )
    rendered = artifact.read_text(encoding="utf-8").lower()
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        "authorization",
        "device_identity",
        '"symbol"',
        '"instrument_id"',
        '"open"',
        '"volume"',
        "funding_rate",
    ):
        assert forbidden not in rendered


def test_representative_canonical_campaign_evidence_is_bound_and_sanitized() -> None:
    artifact = ROOT / "benchmarks/results/m2-canonical-history-campaign-5x24-20260813.json"
    schema = load_json(ROOT / "schemas/evidence/v1/phase2-history-campaign-publication.schema.json")
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == canonical_sha256(hash_input)
    assert verify_evidence(artifact)
    assert payload["bindings"] == {
        "capacity_evidence_sha256": (
            "2363e5795c108186764f098e572388c6bf61185f77ab342c07e1fc61b2ac46d0"
        ),
        "instrument_registry_sha256": (
            "a351fd4a28e143b84ca7bc1f3449601f4f07904bd9c0dda1d31a9dfd9e3e3c88"
        ),
        "publication_manifest_sha256": (
            "0a5f8b24fd5cfd11d790528dde808fd23c3264100fe25243ec0615d56eeb281d"
        ),
        "publication_plan_sha256": (
            "a127ee5abb5dd74e7be033b60fea5a5140403212b35b8dec53f7a916ae9aae1f"
        ),
        "source_campaign_manifest_sha256": (
            "cef361cb5eb04cee9f2c645a5281b06f50b050eaaf327c58d170b725f558485a"
        ),
        "source_campaign_plan_sha256": (
            "ab32162397e396975071ee3a64cdc372b58938c3f1865439b9e93501611d8f4e"
        ),
        "source_campaign_request_sha256": (
            "2c93143e6cec6bf402994cb23dac98ff25bffd3b8319e19de029f5ec378fc120"
        ),
    }
    assert payload["canonical"] == {
        "by_kind": [
            {
                "dataset_count": 24,
                "file_count": 24,
                "kind": "trade",
                "parquet_bytes": 119_694_112,
                "row_count": 5_263_200,
            },
            {
                "dataset_count": 24,
                "file_count": 24,
                "kind": "mark",
                "parquet_bytes": 67_476_126,
                "row_count": 5_263_200,
            },
            {
                "dataset_count": 24,
                "file_count": 24,
                "kind": "funding",
                "parquet_bytes": 182_293,
                "row_count": 10_965,
            },
        ],
        "dataset_count": 72,
        "file_count": 72,
        "parquet_bytes": 187_352_531,
        "row_count": 10_537_365,
    }
    assert payload["resource_bounds"] == {
        "maximum_child_planned_peak_memory_bytes": 199_020_064,
        "maximum_child_required_free_bytes": 98_858_563_994,
    }
    rendered = artifact.read_text(encoding="utf-8").lower()
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        "authorization",
        "device_identity",
        '"symbol"',
        '"instrument_id"',
        '"dataset_id"',
        '"source_job_root"',
        '"open"',
        '"volume"',
        "funding_rate",
    ):
        assert forbidden not in rendered


def test_100x31_canonical_campaign_evidence_is_bound_and_sanitized() -> None:
    artifact = ROOT / "benchmarks/results/m2-canonical-history-campaign-100x31-20260813.json"
    schema = load_json(ROOT / "schemas/evidence/v1/phase2-history-campaign-publication.schema.json")
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == canonical_sha256(hash_input)
    assert verify_evidence(artifact)
    assert payload["bindings"] == {
        "capacity_evidence_sha256": (
            "2363e5795c108186764f098e572388c6bf61185f77ab342c07e1fc61b2ac46d0"
        ),
        "instrument_registry_sha256": (
            "9e78d2db1cebb33d1b1bf328df2dee3ee3ad9f7c3db6b42ae916c9017a0fa733"
        ),
        "publication_manifest_sha256": (
            "46df7b00d0a4e42782e3a098676a8bffd46180089dde2521ba2994c257389152"
        ),
        "publication_plan_sha256": (
            "ecee3d5bfce3da39ef09b7ae6a05ca40356d72b4396ad43c9ba13fe042ae42ab"
        ),
        "source_campaign_manifest_sha256": (
            "a87ef79466ea579c847e500d84d84a3681d45f05d74d301f6a685cca6e358033"
        ),
        "source_campaign_plan_sha256": (
            "4657105de047d546551ea3b4efe1d9819101279d1f02a13da5c02900c6ecf259"
        ),
        "source_campaign_request_sha256": (
            "a06ee05fa5aae0d54c02e686e0dac85d2a009253d41562545a95c72b21ca1509"
        ),
    }
    assert payload["canonical"] == {
        "by_kind": [
            {
                "dataset_count": 8,
                "file_count": 8,
                "kind": "trade",
                "parquet_bytes": 75_267_921,
                "row_count": 4_464_000,
            },
            {
                "dataset_count": 8,
                "file_count": 8,
                "kind": "mark",
                "parquet_bytes": 39_502_722,
                "row_count": 4_464_000,
            },
            {
                "dataset_count": 8,
                "file_count": 8,
                "kind": "funding",
                "parquet_bytes": 96_558,
                "row_count": 10_466,
            },
        ],
        "dataset_count": 24,
        "file_count": 24,
        "parquet_bytes": 114_867_201,
        "row_count": 8_938_466,
    }
    assert payload["process"]["publisher_software_identity"] == (
        "git:eafb4b422e8467085122fb84ea7a4c983bee141d"
    )
    assert payload["resource_bounds"] == {
        "maximum_child_planned_peak_memory_bytes": 436_460_224,
        "maximum_child_required_free_bytes": 99_229_194_074,
    }
    rendered = artifact.read_text(encoding="utf-8").lower()
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        "authorization",
        "device_identity",
        '"symbol"',
        '"instrument_id"',
        '"dataset_id"',
        '"source_job_root"',
        '"open"',
        '"volume"',
        "funding_rate",
    ):
        assert forbidden not in rendered


def test_100x31_integrity_fastpath_evidence_is_bound_measured_and_sanitized() -> None:
    artifact = (
        ROOT / "benchmarks/results/"
        "m2-canonical-history-campaign-100x31-integrity-fastpath-20260813.json"
    )
    baseline = load_json(
        ROOT / "benchmarks/results/m2-canonical-history-campaign-100x31-20260813.json"
    )
    schema = load_json(ROOT / "schemas/evidence/v1/phase2-history-campaign-publication.schema.json")
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == "beb8e6dc9f989404b56d6705dcc3c458c7e1b3613a91d9555423d96ce8707406"
    assert embedded_hash == canonical_sha256(hash_input)
    assert verify_evidence(artifact)
    assert payload["bindings"] == baseline["bindings"]
    assert payload["canonical"] == baseline["canonical"]
    assert payload["scope"] == baseline["scope"]
    assert payload["process"]["evidence_builder_software_identity"] == (
        "git:10031a3e9603d031f7d806adc0d5fe20307d501e"
    )
    assert payload["process"]["initial_source_semantic_admission_required"] is True
    assert payload["process"]["source_reverification_mode"] == (
        "receipt-integrity-without-row-decode-v1"
    )
    assert payload["verification"] == {
        "completed_publication_verification_elapsed_ms": 88_566,
        "source_reverification_mode": "receipt-integrity-without-row-decode-v1",
    }
    rendered = artifact.read_text(encoding="utf-8").lower()
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        "authorization",
        "device_identity",
        '"symbol"',
        '"instrument_id"',
        '"dataset_id"',
        '"source_job_root"',
        '"open"',
        '"volume"',
        "funding_rate",
    ):
        assert forbidden not in rendered


def test_full_history_campaign_preflight_performance_is_bound_and_sanitized() -> None:
    artifact = (
        ROOT / "benchmarks/results/m2-history-campaign-preflight-performance-5xfull-20260813.json"
    )
    schema = load_json(
        ROOT / "schemas/evidence/v1/phase2-history-campaign-preflight-performance.schema.json"
    )
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == "3ee0eb78079900d203c102af3142dbe536c06c4c5eabfa7d4cf35946fb48a340"
    assert embedded_hash == canonical_sha256(hash_input)
    assert verify_evidence(artifact)
    assert payload["baseline"]["implementation_identity"] == (
        "git:f14df8fe8eff4741ca7c488b97ad28704c1d1372"
    )
    assert payload["qualified"]["implementation_identity"] == (
        "git:8bb04ef4e21b84c7a3461c95d95fba70e28888f2"
    )
    assert payload["baseline"]["preflight_elapsed_ms"] == 125_600
    assert payload["qualified"]["preflight_elapsed_ms"] == 3_284
    assert payload["comparison"] == {
        "job_count_unchanged": True,
        "page_count_unchanged": True,
        "planned_peak_memory_unchanged": True,
        "preflight_elapsed_reduction_basis_points": 9_739,
        "request_scope_equivalent_except_campaign_id": True,
        "required_free_bytes_unchanged": True,
        "same_reference_host_identity_verified": True,
        "speedup_milli": 38_246,
    }
    assert payload["scope"] == {
        "end_ms": 1_785_542_340_000,
        "kind_count": 3,
        "month_count": 103,
        "start_ms": 1_514_764_800_000,
        "symbol_count": 5,
        "tick_rows_requested": False,
    }
    rendered = artifact.read_text(encoding="utf-8").lower()
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        "authorization",
        "device_identity_sha256",
        '"symbol"',
        '"instrument_id"',
        '"dataset_id"',
        '"campaign_root"',
        '"open"',
        '"volume"',
        "funding_rate",
    ):
        assert forbidden not in rendered


def test_full_history_campaign_resume_performance_is_bound_and_sanitized() -> None:
    artifact = (
        ROOT / "benchmarks/results/m2-history-campaign-resume-performance-5xfull-20260814.json"
    )
    schema = load_json(
        ROOT / "schemas/evidence/v1/phase2-history-campaign-resume-performance.schema.json"
    )
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == "ba23ddf0e0663d9c569235e989322b28241a9ff2667e2535d46224be535c2c88"
    assert embedded_hash == canonical_sha256(hash_input)
    assert verify_evidence(artifact)
    assert payload["bindings"]["implementation_identity"] == (
        "git:60363277432a2bdcfb8d2a23ea05060057eb3aaa"
    )
    assert payload["measurement"] == {
        "completed_child_verification_mode": "receipt-integrity-without-row-decode-v1",
        "completed_jobs_reused": 927,
        "execute_to_first_pending_failure_ms": 1_283,
        "first_pending_client_calls": 1,
        "first_pending_failure_class": "synthetic-http-403-fail-closed",
        "job_count": 978,
        "page_count": 43_328,
        "pending_job_count": 51,
        "pending_page_count": 2_271,
        "planned_peak_memory_bytes": 146_800_640,
        "preflight_elapsed_ms": 72_762,
        "required_free_bytes": 103_198_759_642,
        "resume_to_first_pending_failure_elapsed_ms": 74_045,
    }
    assert payload["assurances"]["network_request_performed"] is False
    rendered = artifact.read_text(encoding="utf-8").lower()
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        "authorization",
        "device_identity_sha256",
        '"symbol"',
        '"instrument_id"',
        '"job_id"',
        '"runtime_path"',
        '"open"',
        '"volume"',
        "funding_rate",
    ):
        assert forbidden not in rendered


def test_representative_campaign_coverage_audit_is_bound_and_sanitized() -> None:
    artifact = ROOT / "benchmarks/results/m2-history-campaign-coverage-audit-20260813.json"
    schema = load_json(ROOT / "schemas/evidence/v1/history-campaign-coverage-audit.schema.json")
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == canonical_sha256(hash_input)
    assert verify_evidence(artifact)
    assert payload["status"] == "passed"
    assert len(payload["child_results"]) == 72
    assert [item["sequence"] for item in payload["child_results"]] == list(range(72))
    assert all(item["status"] == "passed" for item in payload["child_results"])
    assert payload["inventory"] == {
        "blocked_count": 0,
        "by_kind": [
            {
                "blocked_count": 0,
                "dataset_count": 24,
                "kind": "trade",
                "passed_count": 24,
                "row_count": 5_263_200,
            },
            {
                "blocked_count": 0,
                "dataset_count": 24,
                "kind": "mark",
                "passed_count": 24,
                "row_count": 5_263_200,
            },
            {
                "blocked_count": 0,
                "dataset_count": 24,
                "kind": "funding",
                "passed_count": 24,
                "row_count": 10_965,
            },
        ],
        "dataset_count": 72,
        "passed_count": 72,
        "row_count": 10_537_365,
    }
    assert payload["quality"] == {
        "candle": {
            "conflicting_key_count": 0,
            "duplicate_key_count": 0,
            "expected_minute_count": 10_526_400,
            "gap_range_count": 0,
            "lifecycle_failure_count": 0,
            "missing_minute_count": 0,
            "observed_row_count": 10_526_400,
            "unexpected_timestamp_count": 0,
            "unrequested_row_count": 0,
        },
        "funding": {
            "boundary_page_count": 120,
            "duplicate_key_count": 0,
            "empty_range_page_count": 0,
            "internal_interval_mismatch_count": 0,
            "interval_change_count": 0,
            "lifecycle_failure_count": 0,
            "observed_event_count": 10_965,
            "predecessor_interval_mismatch_count": 0,
            "range_page_count": 595,
            "unexpected_timestamp_count": 0,
            "unrequested_row_count": 0,
        },
    }
    assert payload["reason_policy"] == {
        "accepted_reason_codes": [],
        "observed_reason_counts": {},
        "unaccepted_reason_codes": [],
        "unknown_reason_count": 0,
    }
    rendered = artifact.read_text(encoding="utf-8").lower()
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        "authorization",
        "device_identity",
        '"symbol"',
        '"instrument_id"',
        '"dataset_id"',
        '"source_job_root"',
        '"open"',
        '"volume"',
        "funding_rate",
    ):
        assert forbidden not in rendered


def test_100x31_campaign_coverage_audit_preserves_funding_blockers() -> None:
    artifact = ROOT / "benchmarks/results/m2-history-campaign-coverage-audit-100x31-20260813.json"
    schema = load_json(ROOT / "schemas/evidence/v1/history-campaign-coverage-audit.schema.json")
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == canonical_sha256(hash_input)
    assert verify_evidence(artifact)
    assert payload["status"] == "blocked"
    assert payload["audit_software_identity"] == ("git:eafb4b422e8467085122fb84ea7a4c983bee141d")
    assert len(payload["child_results"]) == 24
    assert [item["sequence"] for item in payload["child_results"]] == list(range(24))
    blocked = [item for item in payload["child_results"] if item["status"] == "blocked"]
    assert [(item["sequence"], item["kind"]) for item in blocked] == [
        (17, "funding"),
        (19, "funding"),
        (22, "funding"),
    ]
    assert payload["inventory"] == {
        "blocked_count": 3,
        "by_kind": [
            {
                "blocked_count": 0,
                "dataset_count": 8,
                "kind": "trade",
                "passed_count": 8,
                "row_count": 4_464_000,
            },
            {
                "blocked_count": 0,
                "dataset_count": 8,
                "kind": "mark",
                "passed_count": 8,
                "row_count": 4_464_000,
            },
            {
                "blocked_count": 3,
                "dataset_count": 8,
                "kind": "funding",
                "passed_count": 5,
                "row_count": 10_466,
            },
        ],
        "dataset_count": 24,
        "passed_count": 21,
        "row_count": 8_938_466,
    }
    assert payload["quality"] == {
        "candle": {
            "conflicting_key_count": 0,
            "duplicate_key_count": 0,
            "expected_minute_count": 8_928_000,
            "gap_range_count": 0,
            "lifecycle_failure_count": 0,
            "missing_minute_count": 0,
            "observed_row_count": 8_928_000,
            "unexpected_timestamp_count": 0,
            "unrequested_row_count": 0,
        },
        "funding": {
            "boundary_page_count": 100,
            "duplicate_key_count": 0,
            "empty_range_page_count": 0,
            "internal_interval_mismatch_count": 0,
            "interval_change_count": 7,
            "lifecycle_failure_count": 0,
            "observed_event_count": 10_466,
            "predecessor_interval_mismatch_count": 0,
            "range_page_count": 500,
            "unexpected_timestamp_count": 0,
            "unrequested_row_count": 0,
        },
    }
    assert payload["reason_policy"] == {
        "accepted_reason_codes": [],
        "observed_reason_counts": {"unexplained_interval_change": 7},
        "unaccepted_reason_codes": ["unexplained_interval_change"],
        "unknown_reason_count": 0,
    }
    rendered = artifact.read_text(encoding="utf-8").lower()
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        "authorization",
        "device_identity",
        '"symbol"',
        '"instrument_id"',
        '"dataset_id"',
        '"source_job_root"',
        '"open"',
        '"volume"',
        "funding_rate",
    ):
        assert forbidden not in rendered


def test_canonical_catalog_evidence_chain_matches_schema_hash_receipts_and_redaction() -> None:
    specifications = ROOT / "benchmarks" / "specifications"
    results = ROOT / "benchmarks" / "results"
    request_path = specifications / "m2-canonical-catalog-selection-20260813.json"
    registration_path = results / "m2-canonical-catalog-registration-20260813.json"
    selection_path = results / "m2-canonical-catalog-selection-20260813.json"
    pilot_path = results / "m2-public-1m-canonical-pilot-20260812.json"
    request = load_json(request_path)
    registration = load_json(registration_path)
    selection = load_json(selection_path)
    pilot = load_json(pilot_path)

    Draft202012Validator(
        load_json(
            ROOT / "schemas" / "market" / "v1" / "canonical-dataset-selection-request.schema.json"
        )
    ).validate(request)
    Draft202012Validator(
        load_json(
            ROOT
            / "schemas"
            / "evidence"
            / "v1"
            / "canonical-dataset-catalog-registration.schema.json"
        ),
        format_checker=FormatChecker(),
    ).validate(registration)
    Draft202012Validator(
        load_json(ROOT / "schemas" / "evidence" / "v1" / "canonical-dataset-selection.schema.json"),
        format_checker=FormatChecker(),
    ).validate(selection)

    for artifact_path, payload in (
        (registration_path, registration),
        (selection_path, selection),
    ):
        hash_input = dict(payload)
        embedded_hash = hash_input.pop("content_sha256")
        assert embedded_hash == canonical_sha256(hash_input)
        assert verify_evidence(artifact_path)

    assert selection["request"] == request
    assert selection["request_sha256"] == canonical_sha256(request)
    assert registration["catalog"] == {
        "backend": "duckdb",
        "content_sha256": selection["catalog"]["content_sha256"],
        "dataset_count": 1,
        "file_count": 1,
        "revision": selection["catalog"]["revision"],
        "schema_version": 1,
    }
    assert registration["datasets"][0]["manifest_sha256"] == pilot["canonical"]["manifest_sha256"]
    assert selection["selected_dataset_manifests"] == [
        {
            "dataset_id": registration["datasets"][0]["dataset_id"],
            "manifest_sha256": registration["datasets"][0]["manifest_sha256"],
        }
    ]
    assert selection["selection"] == {
        "object_count": 1,
        "selected_row_inventory": pilot["canonical"]["row_count"],
        "selected_size_bytes": pilot["canonical"]["parquet_bytes"],
    }
    assert selection["objects"][0]["file_sha256"] in selection["objects"][0]["object_key"]
    for artifact_path in (registration_path, selection_path, request_path):
        rendered = artifact_path.read_text(encoding="utf-8").lower()
        for forbidden in (
            "c:\\",
            "api_key",
            "api_secret",
            "authorization",
            "device_identity",
            '"open"',
            '"volume"',
        ):
            assert forbidden not in rendered


def test_funding_catalog_evidence_chain_matches_schema_hash_receipts_and_redaction() -> None:
    specifications = ROOT / "benchmarks" / "specifications"
    results = ROOT / "benchmarks" / "results"
    request_path = specifications / "m2-canonical-funding-catalog-selection-20260813.json"
    registration_path = results / "m2-canonical-funding-catalog-registration-20260813.json"
    selection_path = results / "m2-canonical-funding-catalog-selection-20260813.json"
    pilot_path = results / "m2-public-funding-canonical-pilot-20260813.json"
    coverage_path = results / "m2-canonical-funding-coverage-audit-20260813.json"
    request = load_json(request_path)
    registration = load_json(registration_path)
    selection = load_json(selection_path)
    pilot = load_json(pilot_path)
    coverage = load_json(coverage_path)

    Draft202012Validator(
        load_json(
            ROOT / "schemas" / "market" / "v1" / "canonical-dataset-selection-request.schema.json"
        )
    ).validate(request)
    Draft202012Validator(
        load_json(
            ROOT
            / "schemas"
            / "evidence"
            / "v1"
            / "canonical-dataset-catalog-registration.schema.json"
        ),
        format_checker=FormatChecker(),
    ).validate(registration)
    Draft202012Validator(
        load_json(ROOT / "schemas" / "evidence" / "v1" / "canonical-dataset-selection.schema.json"),
        format_checker=FormatChecker(),
    ).validate(selection)

    for artifact_path, payload in (
        (registration_path, registration),
        (selection_path, selection),
    ):
        hash_input = dict(payload)
        embedded_hash = hash_input.pop("content_sha256")
        assert embedded_hash == canonical_sha256(hash_input)
        assert verify_evidence(artifact_path)

    assert selection["request"] == request
    assert selection["request_sha256"] == canonical_sha256(request)
    assert registration["catalog"] == {
        "backend": "duckdb",
        "content_sha256": selection["catalog"]["content_sha256"],
        "dataset_count": 2,
        "file_count": 2,
        "revision": selection["catalog"]["revision"],
        "schema_version": 1,
    }
    assert registration["datasets"][0]["dataset_type"] == "funding_event"
    assert registration["datasets"][0]["manifest_sha256"] == pilot["canonical"]["manifest_sha256"]
    assert (
        coverage["bindings"]["canonical_manifest_sha256"]
        == registration["datasets"][0]["manifest_sha256"]
    )
    assert selection["selected_dataset_manifests"] == [
        {
            "dataset_id": registration["datasets"][0]["dataset_id"],
            "manifest_sha256": registration["datasets"][0]["manifest_sha256"],
        }
    ]
    assert selection["selection"] == {
        "object_count": 1,
        "selected_row_inventory": pilot["canonical"]["row_count"],
        "selected_size_bytes": pilot["canonical"]["parquet_bytes"],
    }
    assert selection["objects"][0]["file_sha256"] in selection["objects"][0]["object_key"]
    for artifact_path in (registration_path, selection_path, request_path):
        rendered = artifact_path.read_text(encoding="utf-8").lower()
        for forbidden in (
            "c:\\",
            "api_key",
            "api_secret",
            "authorization",
            "device_identity",
            '"funding_rate"',
            '"open"',
            '"volume"',
        ):
            assert forbidden not in rendered


def test_phase2_ten_by_seven_scale_chain_is_complete_bound_and_sanitized() -> None:
    specifications = ROOT / "benchmarks" / "specifications"
    results = ROOT / "benchmarks" / "results"
    market_request_schema = load_json(
        ROOT / "schemas" / "market" / "v1" / "bybit-1m-history-request.schema.json"
    )
    funding_request_schema = load_json(
        ROOT / "schemas" / "market" / "v1" / "bybit-funding-history-request.schema.json"
    )
    candle_pilot_schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "phase2-public-1m-pilot.schema.json"
    )
    candle_audit_schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "canonical-1m-coverage-audit.schema.json"
    )
    funding_pilot_schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "phase2-public-funding-pilot.schema.json"
    )
    funding_audit_schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "canonical-funding-coverage-audit.schema.json"
    )
    registration_schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "canonical-dataset-catalog-registration.schema.json"
    )
    selection_request_schema = load_json(
        ROOT / "schemas" / "market" / "v1" / "canonical-dataset-selection-request.schema.json"
    )
    selection_schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "canonical-dataset-selection.schema.json"
    )
    flows = {
        "trade": {
            "request": specifications / "m2-trade-10x7-history-request-20260813.json",
            "pilot": results / "m2-public-trade-10x7-canonical-scale-20260813.json",
            "audit": results / "m2-trade-10x7-coverage-audit-20260813.json",
            "selection_request": specifications / "m2-trade-10x7-catalog-selection-20260813.json",
            "selection": results / "m2-trade-10x7-catalog-selection-20260813.json",
        },
        "mark": {
            "request": specifications / "m2-mark-10x7-history-request-20260813.json",
            "pilot": results / "m2-public-mark-10x7-canonical-scale-20260813.json",
            "audit": results / "m2-mark-10x7-coverage-audit-20260813.json",
            "selection_request": specifications / "m2-mark-10x7-catalog-selection-20260813.json",
            "selection": results / "m2-mark-10x7-catalog-selection-20260813.json",
        },
        "funding": {
            "request": specifications / "m2-funding-10x7-history-request-20260813.json",
            "pilot": results / "m2-public-funding-10x7-canonical-scale-20260813.json",
            "audit": results / "m2-funding-10x7-coverage-audit-20260813.json",
            "selection_request": specifications / "m2-funding-10x7-catalog-selection-20260813.json",
            "selection": results / "m2-funding-10x7-catalog-selection-20260813.json",
        },
    }
    registration_path = results / "m2-10x7-catalog-registration-20260813.json"
    registration = load_json(registration_path)
    Draft202012Validator(
        registration_schema,
        format_checker=FormatChecker(),
    ).validate(registration)
    registered = {item["dataset_type"]: item for item in registration["datasets"]}
    expected_symbols: set[str] | None = None

    for name, paths in flows.items():
        request = load_json(paths["request"])
        pilot = load_json(paths["pilot"])
        audit = load_json(paths["audit"])
        selection_request = load_json(paths["selection_request"])
        selection = load_json(paths["selection"])
        request_schema = funding_request_schema if name == "funding" else market_request_schema
        pilot_schema = funding_pilot_schema if name == "funding" else candle_pilot_schema
        audit_schema = funding_audit_schema if name == "funding" else candle_audit_schema
        Draft202012Validator(request_schema).validate(request)
        Draft202012Validator(pilot_schema, format_checker=FormatChecker()).validate(pilot)
        Draft202012Validator(audit_schema, format_checker=FormatChecker()).validate(audit)
        Draft202012Validator(selection_request_schema).validate(selection_request)
        Draft202012Validator(
            selection_schema,
            format_checker=FormatChecker(),
        ).validate(selection)
        symbols = {item["symbol"] for item in request["series"]}
        assert len(symbols) == 10
        expected_symbols = symbols if expected_symbols is None else expected_symbols
        assert symbols == expected_symbols
        request_hash_field = (
            pilot["bindings"]["funding_request_sha256"]
            if name == "funding"
            else pilot["landing"]["request_sha256"]
        )
        assert request_hash_field == canonical_sha256(request)
        assert audit["dataset_id"] == pilot["canonical"]["dataset_id"]
        audit_manifest_hash = audit["bindings"]["canonical_manifest_sha256"]
        assert audit_manifest_hash == pilot["canonical"]["manifest_sha256"]
        assert selection["request"] == selection_request
        assert selection["request_sha256"] == canonical_sha256(selection_request)
        assert selection["catalog"] == {
            "content_sha256": registration["catalog"]["content_sha256"],
            "revision": 3,
            "schema_version": 1,
        }
        assert selection["selection"] == {
            "object_count": 1,
            "selected_row_inventory": pilot["canonical"]["row_count"],
            "selected_size_bytes": pilot["canonical"]["parquet_bytes"],
        }
        dataset_type = pilot["canonical"]["dataset_type"]
        assert registered[dataset_type]["manifest_sha256"] == pilot["canonical"]["manifest_sha256"]
        assert selection["selected_dataset_manifests"] == [
            {
                "dataset_id": pilot["canonical"]["dataset_id"],
                "manifest_sha256": pilot["canonical"]["manifest_sha256"],
            }
        ]
        for artifact_path, payload in (
            (paths["pilot"], pilot),
            (paths["audit"], audit),
            (paths["selection"], selection),
        ):
            content = dict(payload)
            embedded_hash = content.pop("content_sha256")
            assert embedded_hash == canonical_sha256(content)
            assert verify_evidence(artifact_path)

    assert registration["catalog"] == {
        "backend": "duckdb",
        "content_sha256": "dcbc0e430e9b7aea72f7c7d9e7b2187644e191bf90ccfc096bed0ad7c43d686f",
        "dataset_count": 5,
        "file_count": 5,
        "revision": 3,
        "schema_version": 1,
    }
    registration_content = dict(registration)
    embedded_registration_hash = registration_content.pop("content_sha256")
    assert embedded_registration_hash == canonical_sha256(registration_content)
    assert verify_evidence(registration_path)
    assert registered["trade_kline_1m"]["row_count"] == 100_800
    assert registered["mark_kline_1m"]["row_count"] == 100_800
    assert registered["funding_event"]["row_count"] == 231
    assert load_json(flows["trade"]["audit"])["quality"]["missing_minute_count"] == 0
    assert load_json(flows["mark"]["audit"])["quality"]["missing_minute_count"] == 0
    funding_quality = load_json(flows["funding"]["audit"])["quality"]
    assert funding_quality["source_range_enumeration_complete"] is True
    assert funding_quality["interval_change_count"] == 0
    assert funding_quality["predecessor_interval_mismatch_count"] == 0

    evidence_paths = [registration_path]
    for paths in flows.values():
        evidence_paths.extend(paths.values())
    for artifact_path in evidence_paths:
        rendered = artifact_path.read_text(encoding="utf-8").lower()
        for forbidden in (
            "c:\\",
            "/home/",
            "api_key",
            "api_secret",
            "authorization",
            "device_identity",
            '"funding_rate"',
            '"open"',
            '"volume"',
        ):
            assert forbidden not in rendered


def test_phase2_fifty_by_ninety_scale_chain_is_bound_sanitized_and_fail_closed() -> None:
    specifications = ROOT / "benchmarks" / "specifications"
    results = ROOT / "benchmarks" / "results"
    market_request_schema = load_json(
        ROOT / "schemas" / "market" / "v1" / "bybit-1m-history-request.schema.json"
    )
    funding_request_schema = load_json(
        ROOT / "schemas" / "market" / "v1" / "bybit-funding-history-request.schema.json"
    )
    candle_audit_schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "canonical-1m-coverage-audit.schema.json"
    )
    funding_audit_schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "canonical-funding-coverage-audit.schema.json"
    )
    registration_schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "canonical-dataset-catalog-registration.schema.json"
    )
    selection_request_schema = load_json(
        ROOT / "schemas" / "market" / "v1" / "canonical-dataset-selection-request.schema.json"
    )
    selection_schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "canonical-dataset-selection.schema.json"
    )
    months = (
        ("2026-04", "2026-04", 2_160_000),
        ("2026-05", "2026-05", 2_232_000),
        ("2026-06-partial", "2026-06-partial", 2_088_000),
    )
    dataset_types = {
        "trade": "trade_kline_1m",
        "mark": "mark_kline_1m",
        "funding": "funding_event",
    }
    registration_path = results / "m2-50x90-catalog-registration-20260813.json"
    registration = load_json(registration_path)
    Draft202012Validator(
        registration_schema,
        format_checker=FormatChecker(),
    ).validate(registration)
    registration_content = dict(registration)
    embedded_registration_hash = registration_content.pop("content_sha256")
    assert embedded_registration_hash == canonical_sha256(registration_content)
    assert verify_evidence(registration_path)
    assert registration["catalog"] == {
        "backend": "duckdb",
        "content_sha256": "f7883c006fff2a8eaa5c897964fb69b1fbdd4a7f6baa00d8ce9b00293d6595bc",
        "dataset_count": 14,
        "file_count": 14,
        "revision": 4,
        "schema_version": 1,
    }
    assert len(registration["datasets"]) == 9
    registered = {item["dataset_id"]: item for item in registration["datasets"]}
    expected_symbols: set[str] | None = None

    for flow, dataset_type in dataset_types.items():
        selection_request_path = specifications / f"m2-{flow}-50x90-catalog-selection-20260813.json"
        selection_path = results / f"m2-{flow}-50x90-catalog-selection-20260813.json"
        selection_request = load_json(selection_request_path)
        selection = load_json(selection_path)
        Draft202012Validator(selection_request_schema).validate(selection_request)
        Draft202012Validator(
            selection_schema,
            format_checker=FormatChecker(),
        ).validate(selection)
        selection_content = dict(selection)
        embedded_selection_hash = selection_content.pop("content_sha256")
        assert embedded_selection_hash == canonical_sha256(selection_content)
        assert verify_evidence(selection_path)
        assert selection["request"] == selection_request
        assert selection["request_sha256"] == canonical_sha256(selection_request)
        assert selection["catalog"] == {
            "content_sha256": registration["catalog"]["content_sha256"],
            "revision": 4,
            "schema_version": 1,
        }
        assert selection["selection"]["object_count"] == 3
        assert selection["selection"]["selected_row_inventory"] == (
            21_421 if flow == "funding" else 6_480_000
        )
        selected_ids = {item["dataset_id"] for item in selection["selected_dataset_manifests"]}
        assert selected_ids == set(selection_request["dataset_ids"])
        assert all(
            registered[dataset_id]["dataset_type"] == dataset_type for dataset_id in selected_ids
        )

        for request_name, audit_name, expected_minutes in months:
            request_path = (
                specifications / f"m2-{flow}-{request_name}-50x90-history-request-20260813.json"
            )
            audit_path = results / f"m2-{flow}-{audit_name}-50x90-coverage-audit-20260813.json"
            request = load_json(request_path)
            audit = load_json(audit_path)
            request_schema = funding_request_schema if flow == "funding" else market_request_schema
            audit_schema = funding_audit_schema if flow == "funding" else candle_audit_schema
            Draft202012Validator(request_schema).validate(request)
            Draft202012Validator(
                audit_schema,
                format_checker=FormatChecker(),
            ).validate(audit)
            audit_content = dict(audit)
            embedded_audit_hash = audit_content.pop("content_sha256")
            assert embedded_audit_hash == canonical_sha256(audit_content)
            assert verify_evidence(audit_path)
            symbols = {item["symbol"] for item in request["series"]}
            assert len(symbols) == 50
            expected_symbols = symbols if expected_symbols is None else expected_symbols
            assert symbols == expected_symbols
            assert audit["dataset_id"] in selected_ids
            assert (
                audit["bindings"]["canonical_manifest_sha256"]
                == registered[audit["dataset_id"]]["manifest_sha256"]
            )
            quality = audit["quality"]
            assert quality["canonical_source_table_equal"] is True
            assert quality["duplicate_key_count"] == 0
            assert quality["unrequested_row_count"] == 0
            assert quality["unexpected_timestamp_count"] == 0
            assert quality["lifecycle_failure_count"] == 0
            if flow == "funding":
                assert quality["requested_window_minutes"] == expected_minutes
                assert quality["empty_range_page_count"] == 0
                assert quality["internal_interval_mismatch_count"] == 0
                assert quality["predecessor_interval_mismatch_count"] == 0
            else:
                assert audit["status"] == "passed"
                assert quality["expected_minute_count"] == expected_minutes
                assert quality["missing_minute_count"] == 0
                assert quality["observed_row_count"] == expected_minutes

    april_funding = load_json(results / "m2-funding-2026-04-50x90-coverage-audit-20260813.json")
    assert april_funding["status"] == "blocked"
    assert april_funding["quality"]["interval_change_count"] == 4
    assert april_funding["quality"]["source_range_enumeration_complete"] is False
    assert april_funding["reason_policy"] == {
        "accepted_reason_codes": [],
        "observed_reason_counts": {"unexplained_interval_change": 4},
        "unaccepted_reason_codes": ["unexplained_interval_change"],
        "unknown_reason_count": 0,
    }
    changed_symbols = {
        item["symbol"] for item in april_funding["series"] if item["interval_change_count"] > 0
    }
    assert changed_symbols == {"ONTUSDT", "PIPPINUSDT"}
    for month in ("2026-05", "2026-06-partial"):
        funding = load_json(results / f"m2-funding-{month}-50x90-coverage-audit-20260813.json")
        assert funding["status"] == "passed"
        assert funding["quality"]["interval_change_count"] == 0
        assert funding["quality"]["source_range_enumeration_complete"] is True

    evidence_paths = [registration_path]
    evidence_paths.extend(specifications.glob("m2-*-50x90-*.json"))
    evidence_paths.extend(results.glob("m2-*-50x90-*.json"))
    for artifact_path in evidence_paths:
        rendered = artifact_path.read_text(encoding="utf-8").lower()
        for forbidden in (
            "c:\\",
            "/home/",
            "api_key",
            "api_secret",
            "authorization",
            "device_identity",
            '"funding_rate"',
            '"open"',
            '"volume"',
        ):
            assert forbidden not in rendered


def test_phase2_measured_compaction_chain_is_complete_bound_and_sanitized() -> None:
    specifications = ROOT / "benchmarks" / "specifications"
    results = ROOT / "benchmarks" / "results"
    request_schema = load_json(
        ROOT / "schemas" / "market" / "v1" / "bybit-1m-history-request.schema.json"
    )
    pilot_schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "phase2-public-1m-pilot.schema.json"
    )
    compaction_schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "canonical-1m-compaction.schema.json"
    )
    parent_manifests: dict[str, str] = {}
    all_symbols: set[str] = set()
    parent_parquet_bytes = 0
    evidence_paths: list[Path] = []

    for group in ("g01", "g02", "g03", "g04", "g05"):
        request_path = (
            specifications / f"m2-trade-april-compaction-{group}-history-request-20260813.json"
        )
        pilot_path = results / f"m2-public-trade-april-compaction-{group}-20260813.json"
        request = load_json(request_path)
        pilot = load_json(pilot_path)
        Draft202012Validator(request_schema).validate(request)
        Draft202012Validator(
            pilot_schema,
            format_checker=FormatChecker(),
        ).validate(pilot)
        pilot_content = dict(pilot)
        embedded_pilot_hash = pilot_content.pop("content_sha256")
        assert embedded_pilot_hash == canonical_sha256(pilot_content)
        assert verify_evidence(pilot_path)
        assert pilot["landing"]["request_sha256"] == canonical_sha256(request)
        assert pilot["canonical"]["row_count"] == 432_000
        assert pilot["canonical"]["file_count"] == 1
        assert pilot["canonical"]["instrument_count"] == 10
        assert pilot["scope"]["exact_requested_coverage"] is True
        assert pilot["scope"]["requested_minute_count"] == 432_000
        symbols = {item["symbol"] for item in request["series"]}
        assert len(symbols) == 10
        assert all_symbols.isdisjoint(symbols)
        all_symbols.update(symbols)
        parent_manifests[pilot["canonical"]["dataset_id"]] = pilot["canonical"]["manifest_sha256"]
        parent_parquet_bytes += pilot["canonical"]["parquet_bytes"]
        evidence_paths.extend((request_path, pilot_path))

    assert len(all_symbols) == 50
    assert len(parent_manifests) == 5
    compaction_path = results / "m2-trade-april-50x90-compaction-20260813.json"
    compaction = load_json(compaction_path)
    Draft202012Validator(
        compaction_schema,
        format_checker=FormatChecker(),
    ).validate(compaction)
    compaction_content = dict(compaction)
    embedded_compaction_hash = compaction_content.pop("content_sha256")
    assert embedded_compaction_hash == canonical_sha256(compaction_content)
    assert verify_evidence(compaction_path)
    assert compaction["status"] == "passed"
    assert compaction["compaction"] == {
        "conflicting_key_count": 0,
        "duplicate_key_count": 0,
        "input_file_count": 5,
        "logical_table_equal": True,
        "output_file_count": 3,
        "output_total_bytes": 38_548_890,
        "row_count": 2_160_000,
        "rows_per_file_target": 1_024_000,
        "tail_file_count": 1,
        "target_band_non_tail_file_count": 2,
        "target_file_bytes": 16_777_216,
    }
    assert (
        compaction["bindings"]["input_table_sha256"]
        == compaction["bindings"]["output_table_sha256"]
    )
    bound_parents = {
        item["dataset_id"]: item["manifest_sha256"]
        for item in compaction["bindings"]["parent_manifests"]
    }
    assert bound_parents == parent_manifests
    assert set(compaction["lineage"]["parent_dataset_ids"]) == set(parent_manifests)
    assert compaction["lineage"]["parent_datasets_mutated"] is False
    assert compaction["compaction_software_identity"] == (
        "git:a16bb3c57d17056cd7cde3ec490354b8e55d8374"
    )
    assert parent_parquet_bytes == 38_593_039
    assert compaction["compaction"]["output_total_bytes"] < parent_parquet_bytes

    evidence_paths.append(compaction_path)
    for artifact_path in evidence_paths:
        rendered = artifact_path.read_text(encoding="utf-8").lower()
        for forbidden in (
            "c:\\",
            "/home/",
            "api_key",
            "api_secret",
            "authorization",
            "device_identity",
            '"open"',
            '"volume"',
        ):
            assert forbidden not in rendered


def test_archive_coverage_matches_schema_hash_and_receipt() -> None:
    artifact = ROOT / "benchmarks" / "results" / "m1-bybit-archive-coverage.json"
    schema = load_json(ROOT / "schemas" / "evidence" / "v1" / "bybit-archive-coverage.schema.json")
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    embedded_hash = payload.pop("content_sha256")
    assert embedded_hash == canonical_sha256(payload)
    assert verify_evidence(artifact)


def test_history_source_assessment_matches_schema_hash_and_receipt() -> None:
    artifact = ROOT / "benchmarks" / "results" / "m1-bybit-history-source-assessment.json"
    schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "bybit-history-source-assessment.schema.json"
    )
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    embedded_hash = payload.pop("content_sha256")
    assert embedded_hash == canonical_sha256(payload)
    assert verify_evidence(artifact)


def test_one_minute_source_assessment_matches_v2_schema_hash_and_receipt() -> None:
    artifact = (
        ROOT / "benchmarks" / "results" / "m1-bybit-one-minute-source-assessment-20260812.json"
    )
    schema = load_json(
        ROOT / "schemas" / "evidence" / "v2" / "bybit-history-source-assessment.schema.json"
    )
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    embedded_hash = payload.pop("content_sha256")
    assert embedded_hash == canonical_sha256(payload)
    assert payload["assessment"]["tick_data_downloaded"] is False
    assert payload["assessment"]["tick_data_retained"] is False
    assert payload["inventory_backfill_estimate"]["combined_requests"] == {
        "conservative_60m_funding_interval": 1_845_401,
        "current_funding_intervals": 1_785_544,
    }
    assert verify_evidence(artifact)


def test_rest_history_boundary_matches_schema_hash_receipt_and_storage_policy() -> None:
    artifact = ROOT / "benchmarks" / "results" / "m1-bybit-rest-history-boundary-20260812.json"
    inventory = ROOT / "benchmarks" / "results" / "m1-owner-storage-review-inventory-20260812.json"
    schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "bybit-rest-history-boundary.schema.json"
    )
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    embedded_hash = payload.pop("content_sha256")
    assert embedded_hash == canonical_sha256(payload)
    assert payload["inventory_source"]["artifact_sha256"] == sha256_file(inventory)
    assert payload["request_audit"]["actual_request_count"] == 84
    assert payload["request_audit"]["planned_request_upper_bound"] == 84
    assert payload["request_audit"]["transport_max_attempts"] == 1
    assert payload["storage_policy"] == {
        "market_rows_persisted": False,
        "market_values_persisted": False,
        "response_content_hashes_persisted": True,
        "tick_rows_requested": False,
    }
    assert payload["selection"]["symbols"] == [item["symbol"] for item in payload["symbols"]]
    actual_requests = 0
    for symbol in payload["symbols"]:
        for dataset in symbol["datasets"].values():
            checkpoints = dataset["checkpoints"]
            actual_requests += dataset["request_count"]
            assert dataset["request_count"] == 1 + len(checkpoints)
            assert dataset["checkpoint_empty_count"] == sum(
                not checkpoint["nonempty"] for checkpoint in checkpoints
            )
            assert dataset["checkpoint_nonempty_count"] == sum(
                checkpoint["nonempty"] for checkpoint in checkpoints
            )
            if dataset["launch_window_nonempty"]:
                assert dataset["observation_semantics"] == "exact-within-launch-window"
            elif dataset["status"] == "available":
                assert dataset["observation_semantics"] == ("sampled-checkpoint-not-exact-boundary")
            else:
                assert dataset["observation_semantics"] == ("none-observed-in-probed-windows")
    assert actual_requests == payload["request_audit"]["actual_request_count"]
    forbidden_keys = {
        "close",
        "closePrice",
        "fundingRate",
        "high",
        "highPrice",
        "low",
        "lowPrice",
        "open",
        "openPrice",
        "turnover",
        "volume",
    }

    def assert_no_market_value_keys(value: Any) -> None:
        if isinstance(value, Mapping):
            assert forbidden_keys.isdisjoint(value)
            for nested in value.values():
                assert_no_market_value_keys(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_no_market_value_keys(nested)

    assert_no_market_value_keys(payload)
    assert verify_evidence(artifact)


def test_rest_throughput_evidence_chain_matches_schema_receipts_and_safety_bounds() -> None:
    results = ROOT / "benchmarks" / "results"
    inventory = results / "m1-owner-storage-review-inventory-20260812.json"
    source = results / "m1-bybit-one-minute-source-assessment-20260812.json"
    workstation = results / "m1-owner-storage-review-workstation-20260812.json"
    schema = load_json(ROOT / "schemas" / "evidence" / "v1" / "bybit-rest-throughput.schema.json")
    artifacts = (
        results / "m1-bybit-rest-throughput-20260812.json",
        results / "m1-bybit-rest-throughput-20260812-r2.json",
        results / "m1-bybit-rest-throughput-20260812-confirmation.json",
    )
    payloads = []
    for artifact in artifacts:
        payload = load_json(artifact)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
        hash_input = dict(payload)
        embedded_hash = hash_input.pop("content_sha256")
        assert embedded_hash == canonical_sha256(hash_input)
        assert payload["inventory_source"]["artifact_sha256"] == sha256_file(inventory)
        assert payload["source_assessment"]["artifact_sha256"] == sha256_file(source)
        assert payload["workstation_source"]["artifact_sha256"] == sha256_file(workstation)
        assert payload["source_policy"] == {
            "mark_price_1m": "/v5/market/mark-price-kline",
            "trade_price_1m": "/v5/market/kline",
        }
        assert payload["official_limit"]["benchmark_ceiling_requests_per_second"] == 96
        assert payload["workload"]["transport_max_attempts"] == 1
        assert payload["storage_policy"] == {
            "market_rows_persisted": False,
            "market_values_persisted": False,
            "response_content_hashes_persisted": True,
            "tick_rows_requested": False,
        }
        actual_requests = sum(profile["actual_request_count"] for profile in payload["profiles"])
        assert actual_requests == payload["request_audit"]["actual_request_count"]
        assert actual_requests <= payload["request_audit"]["planned_request_count"]
        assert (
            payload["request_audit"]["planned_request_count"]
            <= payload["request_audit"]["max_requests"]
        )
        assert all(
            profile["row_count"] == profile["full_page_count"] * 1_000
            for profile in payload["profiles"]
        )
        assert verify_evidence(artifact)
        payloads.append(payload)

    initial, sweep, confirmation = payloads
    assert initial["request_audit"]["actual_request_count"] == 15
    assert initial["status"] == "bounded-benchmark-partial"
    assert sweep["request_audit"]["actual_request_count"] == 424
    assert sweep["profiles"][-1]["target_requests_per_second"] == 40
    assert sweep["profiles"][-1]["status"] == "failed"
    assert sweep["profiles"][-1]["error_count"] == 2
    assert confirmation["status"] == "bounded-benchmark-complete"
    assert confirmation["request_audit"]["actual_request_count"] == 100
    assert confirmation["profiles"][0]["target_requests_per_second"] == 10
    assert confirmation["profiles"][0]["error_count"] == 0
    assert confirmation["profiles"][0]["status"] == "under-target"

    forbidden_keys = {
        "close",
        "closePrice",
        "fundingRate",
        "high",
        "highPrice",
        "low",
        "lowPrice",
        "open",
        "openPrice",
        "turnover",
        "volume",
    }

    def assert_no_market_value_keys(value: Any) -> None:
        if isinstance(value, Mapping):
            assert forbidden_keys.isdisjoint(value)
            for nested in value.values():
                assert_no_market_value_keys(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_no_market_value_keys(nested)

    for payload in payloads:
        assert_no_market_value_keys(payload)


def test_reference_layout_protocol_smoke_matches_schema_and_receipt() -> None:
    artifact = ROOT / "benchmarks" / "results" / "m1-reference-layout-protocol-smoke.json"
    schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "reference-layout-benchmark.schema.json"
    )

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(load_json(artifact))
    assert verify_evidence(artifact)


def test_real_market_layout_skew_matches_schema_hash_and_receipt() -> None:
    artifact = ROOT / "benchmarks" / "results" / "m1-real-market-layout-skew.json"
    schema = load_json(ROOT / "schemas" / "evidence" / "v1" / "real-market-layout-skew.schema.json")
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    embedded_hash = payload.pop("content_sha256")
    assert embedded_hash == canonical_sha256(payload)
    assert len({item["layout"]["bucket_count"] for item in payload["layouts"]}) == 2
    assert len({item["logical_summary"]["logical_sha256"] for item in payload["layouts"]}) == 1
    assert payload["total_row_count"] == sum(item["row_count"] for item in payload["per_symbol"])
    assert verify_evidence(artifact)


def test_real_market_capacity_projection_is_bound_to_skew_and_decision_evidence() -> None:
    artifact = ROOT / "benchmarks" / "results" / "m1-real-market-capacity-projection.json"
    payload = load_json(artifact)
    real_market = ROOT / "benchmarks" / "results" / "m1-real-market-layout-skew.json"
    decision = ROOT / "benchmarks" / "results" / "m1-layout-exact-decision-candidate.json"

    assert payload["provenance"]["real_market"]["artifact_sha256"] == sha256_file(real_market)
    assert payload["provenance"]["layout"]["artifact_sha256"] == sha256_file(decision)
    real_layouts = payload["real_market_layout_projections"]
    assert [item["layout"] for item in real_layouts] == [
        item["layout"] for item in payload["selected_exact_layout_projections"]
    ]
    assert all(
        item["projected_trade_and_mark_bytes_at_trade_row_width"] > item["projected_trade_bytes"]
        for item in real_layouts
    )


def test_owner_storage_review_evidence_chain_is_complete_and_bound() -> None:
    results = ROOT / "benchmarks" / "results"
    inventory = results / "m1-owner-storage-review-inventory-20260812.json"
    history = results / "m1-owner-storage-review-history-20260812.json"
    workstation = results / "m1-owner-storage-review-workstation-20260812.json"
    capacity_basis = results / "m1-real-market-capacity-projection.json"
    projection = results / "m1-owner-storage-review-capacity-20260812.json"

    inventory_payload = load_json(inventory)
    inventory_hash = inventory_payload.pop("content_sha256")
    assert inventory_hash == canonical_sha256(inventory_payload)
    assert inventory_payload["evidence_schema"] == "grid.bybit-public-inventory/v1"
    assert inventory_payload["inventory_status"] == "partial"
    assert verify_evidence(inventory)

    history_payload = load_json(history)
    Draft202012Validator(
        load_json(
            ROOT / "schemas" / "evidence" / "v1" / "bybit-history-source-assessment.schema.json"
        ),
        format_checker=FormatChecker(),
    ).validate(history_payload)
    history_content = dict(history_payload)
    history_hash = history_content.pop("content_sha256")
    assert history_hash == canonical_sha256(history_content)
    assert history_payload["inventory_source"]["artifact_sha256"] == sha256_file(inventory)
    assert verify_evidence(history)

    projection_payload = load_json(projection)
    assert projection_payload["sources"]["history"]["artifact_sha256"] == sha256_file(history)
    assert projection_payload["sources"]["workstation"]["artifact_sha256"] == sha256_file(
        workstation
    )
    assert projection_payload["sources"]["capacity"]["artifact_sha256"] == sha256_file(
        capacity_basis
    )
    assert projection_payload["disk_headroom"]["measured_canonical_scenarios_fit"] is True
    assert projection_payload["disk_headroom"]["planning_64_byte_rebuild_scenario_fits"] is False
    assert (
        projection_payload["disk_headroom"]["raw_source_archives"]["safe_full_bootstrap_conclusion"]
        is False
    )
    assert verify_evidence(projection)


def test_public_funding_pilot_matches_schema_hash_receipt_and_safety_boundary() -> None:
    artifact = ROOT / "benchmarks" / "results" / "m2-public-funding-canonical-pilot-20260813.json"
    schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "phase2-public-funding-pilot.schema.json"
    )
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    content = dict(payload)
    embedded_hash = content.pop("content_sha256")
    assert embedded_hash == canonical_sha256(content)
    assert verify_evidence(artifact)
    assert payload["status"] == "verified-canonical-funding-publication"
    assert payload["scope"]["observed_event_count"] == 42
    assert payload["scope"]["requested_window_minutes"] == 20_160
    assert [item["observed_event_count"] for item in payload["scope"]["series"]] == [21, 21]
    assert payload["source"] == {
        "actual_http_requests": 4,
        "authentication": "none",
        "base_url": "https://api.bybit.com",
        "boundary_page_count": 2,
        "endpoint": "/v5/market/funding/history",
        "max_attempt_count_observed": 1,
        "max_attempts_per_page": 3,
        "page_count": 4,
        "page_limit": 200,
        "page_span_minutes": 10_080,
        "private_endpoints_called": False,
        "range_page_count": 2,
        "saturated_range_pages_accepted": False,
        "target_rps": 4,
        "workers": 4,
    }
    assert payload["canonical"]["row_count"] == 42
    assert payload["canonical"]["parquet_bytes"] == 5_050
    assert payload["canonical"]["single_file_classification"] == "tail-below-target"
    assert payload["publication"]["software_identity"] == (
        "git:cbe8391db0b9d5b9bdeb9ebae5af4035e570a7e2"
    )
    assert payload["quality"] == {
        "canonical_receipt_verified": True,
        "exact_landing_canonical_table_equality": True,
        "funding_rates_exact_decimal128": True,
        "internal_intervals_recomputed": True,
        "predecessor_intervals_recomputed": True,
        "sorted_unique_keys_verified": True,
    }

    forbidden_keys = {
        "device_identity_sha256",
        "fundingRate",
        "funding_rate",
        "funding_time_ms",
        "host_preflight",
        "rows",
        "settlement_time_ms",
    }

    def assert_sanitized(value: Any) -> None:
        if isinstance(value, Mapping):
            assert forbidden_keys.isdisjoint(value)
            for nested in value.values():
                assert_sanitized(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_sanitized(nested)

    assert_sanitized(payload)
    rendered = json.dumps(payload)
    assert "C:\\" not in rendered
    assert "/home/" not in rendered


def test_measured_funding_coverage_audit_is_bound_passed_and_sanitized() -> None:
    artifact = ROOT / "benchmarks" / "results" / "m2-canonical-funding-coverage-audit-20260813.json"
    pilot = load_json(
        ROOT / "benchmarks" / "results" / "m2-public-funding-canonical-pilot-20260813.json"
    )
    schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "canonical-funding-coverage-audit.schema.json"
    )
    payload = load_json(artifact)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    content = dict(payload)
    embedded_hash = content.pop("content_sha256")
    assert embedded_hash == canonical_sha256(content)
    assert verify_evidence(artifact)
    assert payload["status"] == "passed"
    assert payload["audit_software_identity"] == ("git:97bce032b351f95e11d78352b74fe5f2098f8834")
    assert payload["bindings"]["publisher_software_identity"] == (
        "git:cbe8391db0b9d5b9bdeb9ebae5af4035e570a7e2"
    )
    assert (
        payload["bindings"]["canonical_manifest_sha256"]
        == (pilot["bindings"]["canonical_manifest_sha256"])
    )
    assert (
        payload["bindings"]["funding_manifest_sha256"]
        == (pilot["bindings"]["funding_manifest_sha256"])
    )
    assert (
        payload["bindings"]["boundary_evidence_sha256"]
        == (pilot["bindings"]["boundary_evidence_sha256"])
    )
    assert payload["chronology_anomaly_evidence"] == {
        "anomaly_count": 0,
        "anomaly_records_sha256": canonical_sha256([]),
    }
    assert payload["quality"] == {
        "boundary_page_count": 2,
        "canonical_source_table_equal": True,
        "conflicting_key_count": 0,
        "duplicate_key_count": 0,
        "empty_range_page_count": 0,
        "internal_interval_mismatch_count": 0,
        "interval_change_count": 0,
        "lifecycle_failure_count": 0,
        "observed_event_count": 42,
        "predecessor_interval_mismatch_count": 0,
        "range_page_count": 2,
        "requested_window_minutes": 20_160,
        "source_range_enumeration_complete": True,
        "unexpected_timestamp_count": 0,
        "unrequested_row_count": 0,
    }
    assert payload["reason_policy"] == {
        "accepted_reason_codes": [],
        "observed_reason_counts": {},
        "unaccepted_reason_codes": [],
        "unknown_reason_count": 0,
    }
    assert [item["interval_histogram"] for item in payload["series"]] == [
        [{"event_count": 21, "interval_minutes": 480}],
        [{"event_count": 21, "interval_minutes": 480}],
    ]
    assert payload["coverage_basis"]["current_instrument_interval_used"] is False

    forbidden_keys = {
        "device_identity_sha256",
        "fundingRate",
        "funding_rate",
        "funding_time_ms",
        "host_preflight",
        "rows",
        "settlement_time_ms",
    }

    def assert_sanitized(value: Any) -> None:
        if isinstance(value, Mapping):
            assert forbidden_keys.isdisjoint(value)
            for nested in value.values():
                assert_sanitized(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_sanitized(nested)

    assert_sanitized(payload)
    rendered = json.dumps(payload)
    assert "C:\\" not in rendered
    assert "/home/" not in rendered


def test_incremental_catalog_selection_performance_is_bound_measured_and_sanitized() -> None:
    artifact = (
        ROOT
        / "benchmarks"
        / "results"
        / "m2-incremental-catalog-selection-performance-20260814.json"
    )
    receipt_path = artifact.with_name(f"{artifact.name}.receipt.json")
    schema = load_json(
        ROOT
        / "schemas"
        / "evidence"
        / "v1"
        / "phase2-incremental-catalog-selection-performance.schema.json"
    )
    payload = load_json(artifact)
    receipt = load_json(receipt_path)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == canonical_sha256(hash_input)
    assert embedded_hash == "2a39c2ee7507f63ab8e634d3fb9c54d997e430910dd61f122cea21e7f7973834"
    assert verify_evidence(artifact)
    assert sha256_file(artifact) == (
        "5987c967f049342e54c5f81c3546bc9232e94c500c370a3376b764c3fadfa7a7"
    )
    assert receipt == {
        "artifact": artifact.name,
        "artifact_sha256": "5987c967f049342e54c5f81c3546bc9232e94c500c370a3376b764c3fadfa7a7",
        "receipt_schema": "grid.evidence-receipt/v1",
        "status": "complete",
    }
    assert payload["evidence_schema"] == (
        "grid.phase2-incremental-catalog-selection-performance/v1"
    )
    assert payload["status"] == "measured-incremental-catalog-selection"
    assert payload["bindings"] == {
        "implementation_identity": "git:9b68150b740d9bd8988ed791c98dbd9bf4a90a72"
    }
    assert payload["configuration"] == {
        "exact_key_batch_rows": 4_096,
        "fragment_count": 16,
        "instrument_count": 32,
        "max_exact_key_streams": 128,
        "minutes_per_fragment": 720,
        "total_row_count": 368_640,
    }
    assert payload["correctness"] == {
        "ambiguous_adjacent_bound_count": 15,
        "catalog_revision": 1,
        "deterministic_repeat_equal": True,
        "selected_object_count": 16,
        "selected_row_count": 368_640,
        "selection_fingerprint_sha256": (
            "67e445d4dfc79a33d55e5be4f707f951b7dc014487bd511b0d3ddaabba034dbc"
        ),
        "store_fingerprint_equal_before_after": True,
    }
    assert payload["measurement"] == {
        "first_selection_elapsed_ns": 816_325_700,
        "first_selection_rows_per_second": 451_584,
        "repeat_selection_elapsed_ns": 804_938_400,
        "repeat_selection_rows_per_second": 457_972,
    }
    assert payload["assurances"] == {
        "catalog_and_dataset_state_preserved": True,
        "network_request_performed": False,
        "private_or_live_capability_used": False,
        "production_catalog_selector_exercised": True,
        "retained_market_store_accessed": False,
        "temporary_fixture_removed": True,
    }
    rendered = json.dumps(payload).lower()
    for forbidden in (
        "c:\\",
        "/home/",
        '"api_key"',
        '"api_secret"',
        '"dataset_id"',
        '"funding_rate"',
        '"instrument_id"',
        '"open_time_ms"',
        '"runtime_path"',
        '"source_id"',
        '"storage_device_id"',
        '"symbol"',
    ):
        assert forbidden not in rendered


def test_announcement_archive_depth_is_bound_blocked_and_sanitized() -> None:
    artifact = (
        ROOT / "benchmarks" / "results" / "m2-announcement-archive-depth-oldest-5-20260814.json"
    )
    receipt_path = artifact.with_name(f"{artifact.name}.receipt.json")
    schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "phase2-announcement-archive-depth.schema.json"
    )
    payload = load_json(artifact)
    receipt = load_json(receipt_path)

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == canonical_sha256(hash_input)
    assert embedded_hash == "11913c639a63b04af9b518ea7db73df64b9dbd8346bb9b3ae57fd3e8343bee1e"
    assert verify_evidence(artifact)
    artifact_sha256 = "68c12ffbf7b5824175a0e56e68f591665e8e3e480ccf6765aa3285dfc8437688"
    assert sha256_file(artifact) == artifact_sha256
    assert receipt == {
        "artifact": artifact.name,
        "artifact_sha256": artifact_sha256,
        "receipt_schema": "grid.evidence-receipt/v1",
        "status": "complete",
    }
    assert payload["evidence_schema"] == "grid.phase2-announcement-archive-depth/v1"
    assert payload["status"] == "blocked-insufficient-official-announcement-history"
    assert payload["process"] == {
        "documented_announcement_type_count": 8,
        "first_and_last_page_only": True,
        "lifecycle_depth_type_count": 2,
        "maximum_response_count": 16,
        "response_count": 15,
        "reused_single_page_count": 1,
        "software_identity": "git:777f3c8745da3b83125f9178734538d700a0accd",
    }
    assert payload["archive_depth"] == {
        "all_selected_registry_launches_within_new_listing_archive": False,
        "delistings_declared_last_page_min_date_timestamp_ms": 1_660_194_000_000,
        "documented_types_declared_last_page_min_date_timestamp_ms": 1_651_831_200_000,
        "new_crypto_declared_last_page_min_date_timestamp_ms": 1_654_063_851_000,
        "selected_launch_before_new_listing_archive_count": 5,
        "selected_registry_launch_max_ms": 1_584_230_400_000,
        "selected_registry_launch_min_ms": 1_514_764_800_000,
    }
    probes = {item["announcement_type"]: item for item in payload["type_probes"]}
    assert probes["new_crypto"]["lifecycle_depth_type"] is True
    assert probes["new_crypto"]["declared_page_date_order_consistent"] is True
    assert probes["delistings"]["lifecycle_depth_type"] is True
    assert probes["delistings"]["declared_page_date_order_consistent"] is True
    assert probes["latest_activities"]["lifecycle_depth_type"] is False
    assert probes["latest_activities"]["declared_page_date_order_consistent"] is False
    assert probes["latest_activities"]["first_page_adjacent_date_inversion_count"] == 1
    assert sum(item["last_page_publish_time_present_count"] == 0 for item in probes.values()) == 7

    rendered = json.dumps(payload).lower()
    for forbidden in (
        "c:\\",
        "/home/",
        '"api_key"',
        '"api_secret"',
        '"description"',
        '"instrument_id"',
        '"symbol"',
        '"title"',
        '"url"',
    ):
        assert forbidden not in rendered


class FakeValidateTransport:
    environment = "testnet"

    def validate(self, _payload: Mapping[str, str]) -> Mapping[str, Any]:
        return {"retCode": 0, "result": {"check_code": EXPECTED_CHECK_CODE}}


def test_fgrid_validate_report_matches_schema_and_hashes() -> None:
    schema = load_json(ROOT / "schemas" / "evidence" / "v2" / "fgrid-validate-probe.schema.json")
    report = build_probe_report(
        FakeValidateTransport(),
        FuturesGridValidateRequest(
            symbol="BTCUSDT",
            cell_number=20,
            min_price=Decimal("100"),
            max_price=Decimal("200"),
            leverage=Decimal("2"),
            stop_loss_price=Decimal("90"),
            take_profit_price=Decimal("220"),
        ),
    )

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(report)
    embedded_hash = report.pop("content_sha256")
    assert embedded_hash == canonical_sha256(report)
