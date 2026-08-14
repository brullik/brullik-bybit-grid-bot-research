from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from benchmarks.pooled_public_rest_performance import (
    PooledRestPerformanceError,
    build_sanitized_performance_evidence,
)

ROOT = Path(__file__).parents[2]


def load_json(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def measurement_inputs() -> tuple[dict[str, object], dict[str, object]]:
    baseline = load_json(
        ROOT / "benchmarks/results/m1-bybit-rest-throughput-20260812-confirmation.json"
    )
    measured = copy.deepcopy(baseline)
    measured["fetched_at_utc"] = "2026-08-14T14:00:00Z"
    profiles = measured["profiles"]
    assert isinstance(profiles, list) and len(profiles) == 1
    profile = profiles[0]
    assert isinstance(profile, dict)
    profile.update(
        {
            "latency_ms": {
                "max": "1500.000",
                "min": "100.000",
                "p50": "250.000",
                "p95": "800.000",
                "p99": "1200.000",
            },
            "observed_requests_per_second": "9.500000",
            "observed_rows_per_second": "9500.000000",
            "status": "passed",
            "target_attainment_ratio": "0.950000",
            "wall_duration_seconds": "10.526316",
        }
    )
    return measured, baseline


def build_fixture() -> dict[str, object]:
    measured, baseline = measurement_inputs()
    return build_sanitized_performance_evidence(
        measured,
        baseline,
        generated_at_utc="2026-08-14T14:00:00Z",
        implementation_identity="git:" + "1" * 40,
        inventory_artifact_sha256="2" * 64,
        source_assessment_artifact_sha256="3" * 64,
        workstation_artifact_sha256="4" * 64,
        baseline_artifact_sha256="5" * 64,
        memory_total_bytes=16_000_000_000,
        memory_available_bytes=8_000_000_000,
        volume_free_bytes=200_000_000_000,
        storage_kind="nvme",
    )


def test_sanitized_pooled_result_matches_schema_and_excludes_runtime_identities() -> None:
    payload = build_fixture()
    schema = load_json(
        ROOT / "schemas/evidence/v1/phase2-pooled-public-rest-performance.schema.json"
    )

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    assert payload["status"] == "measured-pooled-public-rest-throughput"
    assert payload["comparison"] == {
        "observed_request_rate_speedup_ratio": "1.223534",
        "wall_elapsed_reduction_percent": "18.269509",
    }
    assert payload["configuration"] == {
        "max_connections": 24,
        "planned_request_count": 100,
        "sample_size": 8,
        "stage_seconds": 10,
        "target_requests_per_second": 10,
        "transport_max_attempts": 1,
        "transport_policy": "bounded-http11-keep-alive-v1",
        "workers": 24,
    }
    rendered = json.dumps(payload).lower()
    for forbidden in (
        "c:\\",
        "/home/",
        '"command"',
        '"symbol"',
        '"instrument_id"',
        '"benchmark_end_ms"',
        '"api_key"',
        '"api_secret"',
    ):
        assert forbidden not in rendered


def test_sanitizer_fails_closed_on_partial_measurement() -> None:
    measured, baseline = measurement_inputs()
    profiles = measured["profiles"]
    assert isinstance(profiles, list)
    profile = profiles[0]
    assert isinstance(profile, dict)
    profile["error_count"] = 1
    profile["success_count"] = 99

    with pytest.raises(PooledRestPerformanceError, match="not every request succeeded"):
        build_sanitized_performance_evidence(
            measured,
            baseline,
            generated_at_utc="2026-08-14T14:00:00Z",
            implementation_identity="git:" + "1" * 40,
            inventory_artifact_sha256="2" * 64,
            source_assessment_artifact_sha256="3" * 64,
            workstation_artifact_sha256="4" * 64,
            baseline_artifact_sha256="5" * 64,
            memory_total_bytes=16_000_000_000,
            memory_available_bytes=8_000_000_000,
            volume_free_bytes=200_000_000_000,
            storage_kind="nvme",
        )
