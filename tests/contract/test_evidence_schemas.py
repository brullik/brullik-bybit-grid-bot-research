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
