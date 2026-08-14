from __future__ import annotations

import json
from pathlib import Path

from grid_contracts.canonical import canonical_sha256
from grid_data.evidence import verify_evidence
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[2]
ARTIFACT = ROOT / "benchmarks" / "results" / "m2-funding-cadence-policy-20260815.json"
SCHEMA = ROOT / "schemas" / "evidence" / "v1" / "phase2-funding-cadence-policy-evidence.schema.json"


def test_measured_funding_cadence_policy_evidence_is_bound_verified_and_redacted() -> None:
    payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    assert verify_evidence(ARTIFACT)

    content = dict(payload)
    embedded_hash = content.pop("content_sha256")
    assert embedded_hash == canonical_sha256(content)
    assert payload["status"] == "verified-official-funding-cadence-policy-consistency"
    assert payload["bindings"]["software_identity"] == (
        "git:41c48c09173e31d38ecf909b0c4441ca2cb17fba"
    )
    assert len(payload["bindings"]["sources"]) == 4
    assert sum(item["interval_change_count"] for item in payload["bindings"]["sources"]) == 11
    assert payload["quality"] == {
        "affected_series_count": 5,
        "completed_hourly_episode_count": 4,
        "coverage_audit_count": 4,
        "explained_interval_change_count": 11,
        "hourly_episode_count": 5,
        "observed_interval_change_count": 11,
        "open_hourly_episode_count": 1,
        "open_nonqualifying_hourly_episode_count": 1,
        "policy_consistent_series_count": 5,
        "qualifying_settlement_count_histogram": [
            {"episode_count": 3, "qualifying_settlement_count": 16},
            {"episode_count": 1, "qualifying_settlement_count": 17},
        ],
        "series_count": 86,
        "unexplained_interval_change_count": 0,
    }
    rendered = json.dumps(payload).lower()
    for forbidden in (
        "ontusdt",
        "pippinusdt",
        "sklusdt",
        "cotiusdt",
        "lrcusdt",
        "c:\\",
        '"funding_rate":',
        '"funding_time_ms":',
        '"instrument_id":',
        "api_key",
        "api_secret",
    ):
        assert forbidden not in rendered
