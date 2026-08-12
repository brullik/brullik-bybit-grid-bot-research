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
from grid_contracts.canonical import canonical_sha256
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
    )
    for artifact_name, versioned_schema_name in cases:
        artifact = ROOT / "benchmarks" / "results" / artifact_name
        schema = load_json(ROOT / "schemas" / "evidence" / versioned_schema_name)

        Draft202012Validator(schema, format_checker=FormatChecker()).validate(load_json(artifact))
        assert verify_evidence(artifact)


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


def test_reference_layout_protocol_smoke_matches_schema_and_receipt() -> None:
    artifact = ROOT / "benchmarks" / "results" / "m1-reference-layout-protocol-smoke.json"
    schema = load_json(
        ROOT / "schemas" / "evidence" / "v1" / "reference-layout-benchmark.schema.json"
    )

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(load_json(artifact))
    assert verify_evidence(artifact)


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
