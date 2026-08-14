from __future__ import annotations

import json
from pathlib import Path

import pytest
from grid_contracts.canonical import canonical_sha256
from grid_market_store import verify_committed_candle_dataset
from jsonschema import Draft202012Validator, FormatChecker

from benchmarks.canonical_integrity_fault_injection import (
    CanonicalIntegrityFaultInjectionError,
    build_canonical_integrity_fault_injection_evidence,
)

ROOT = Path(__file__).parents[2]


def test_canonical_integrity_fault_injection_exercises_all_verifier_failures() -> None:
    evidence = build_canonical_integrity_fault_injection_evidence(
        implementation_identity=f"git:{'a' * 40}",
        generated_at_utc="2026-08-14T04:00:00Z",
    )
    schema = json.loads(
        (
            ROOT / "schemas/evidence/v1/phase2-canonical-integrity-fault-injection.schema.json"
        ).read_text(encoding="utf-8")
    )

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(evidence)
    hash_input = dict(evidence)
    content_sha256 = hash_input.pop("content_sha256")
    assert content_sha256 == canonical_sha256(hash_input)
    assert evidence["measurement"] == {
        "case_count": 6,
        "detected_count": 6,
        "filesystem_state_preserved_count": 6,
    }
    cases = evidence["cases"]
    assert {item["case_id"] for item in cases} == {
        "canonical-candle-missing-completion-receipt",
        "canonical-candle-missing-parquet",
        "canonical-candle-orphan-file",
        "canonical-funding-missing-completion-receipt",
        "canonical-funding-missing-parquet",
        "canonical-funding-orphan-file",
    }
    assert all(item["detected"] is True for item in cases)
    assert all(item["filesystem_state_preserved"] is True for item in cases)
    rendered = json.dumps(evidence).lower()
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        '"symbol"',
        '"instrument_id"',
        '"dataset_id"',
        '"runtime_path"',
        '"open"',
        '"volume"',
        "funding_rate",
    ):
        assert forbidden not in rendered


def test_canonical_integrity_fault_injection_rejects_verifier_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutating_verifier(dataset_root: Path):  # type: ignore[no-untyped-def]
        try:
            return verify_committed_candle_dataset(dataset_root)
        finally:
            (dataset_root / "verifier-mutated").write_text("unsafe", encoding="utf-8")

    monkeypatch.setattr(
        "benchmarks.canonical_integrity_fault_injection.verify_committed_candle_dataset",
        mutating_verifier,
    )
    with pytest.raises(CanonicalIntegrityFaultInjectionError, match="changed the injected fixture"):
        build_canonical_integrity_fault_injection_evidence(
            implementation_identity=f"git:{'a' * 40}",
            generated_at_utc="2026-08-14T04:00:00Z",
        )
