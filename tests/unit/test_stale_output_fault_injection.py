from __future__ import annotations

import json
from pathlib import Path

from grid_contracts.canonical import canonical_sha256
from jsonschema import Draft202012Validator, FormatChecker

from benchmarks.stale_output_fault_injection import (
    build_stale_output_fault_injection_evidence,
)

ROOT = Path(__file__).parents[2]


def test_stale_output_fault_injection_exercises_all_production_boundaries() -> None:
    evidence = build_stale_output_fault_injection_evidence(
        implementation_identity=f"git:{'a' * 40}",
        generated_at_utc="2026-08-14T02:00:00Z",
    )
    schema = json.loads(
        (
            ROOT / "schemas" / "evidence" / "v1" / "phase2-stale-output-fault-injection.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(evidence)
    without_hash = dict(evidence)
    content_hash = without_hash.pop("content_sha256")
    assert content_hash == canonical_sha256(without_hash)
    cases = evidence["cases"]
    assert isinstance(cases, list)
    assert {item["case_id"] for item in cases} == {
        "canonical-candle-compaction-building",
        "canonical-candle-publication-building",
        "canonical-funding-publication-building",
        "catalog-registration-building",
        "catalog-registration-lock",
    }
    assert all(item["detected"] is True for item in cases)
    assert all(item["marker_preserved"] is True for item in cases)
    assert all(item["target_mutated"] is False for item in cases)
    rendered = json.dumps(evidence).lower()
    assert "c:\\" not in rendered
    for forbidden in ('"funding_rate"', '"open"', '"runtime_path"', '"turnover"'):
        assert forbidden not in rendered
