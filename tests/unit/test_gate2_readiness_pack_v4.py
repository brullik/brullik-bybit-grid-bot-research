from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from grid_contracts.canonical import canonical_sha256
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

import benchmarks.gate2_readiness_pack_v4 as readiness_module
from benchmarks.gate2_readiness_pack_v4 import (
    CANDLE_SPEC,
    EXPECTED_BLOCKERS,
    PRIOR_SPEC,
    Gate2ReadinessV4Error,
    build_gate2_readiness_pack_v4,
)

ROOT = Path(__file__).parents[2]
GENERATED = "2026-08-14T21:00:00Z"
IMPLEMENTATION = f"git:{'a' * 40}"
SHA = {
    "capacity": "1" * 64,
    "registry": "2" * 64,
    "bundle_artifact": "3" * 64,
    "bundle_content": "4" * 64,
    "catalog": "5" * 64,
    "candle_artifact": "6" * 64,
}


def _prior() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            (ROOT / "benchmarks/results/m2-gate2-readiness-pack-v3-20260814.json").read_text(
                encoding="utf-8"
            )
        ),
    )


def _candle() -> dict[str, Any]:
    def inventory(kind: str, row_count: int, size_bytes: int) -> dict[str, Any]:
        return {
            "kind": kind,
            "catalog_dataset_count": 1,
            "catalog_object_count": 1,
            "catalog_row_count": row_count,
            "catalog_size_bytes": size_bytes,
        }

    return {
        "bindings": {
            "capacity_evidence_sha256": SHA["capacity"],
            "catalog_bundle_artifact_sha256": SHA["bundle_artifact"],
            "catalog_bundle_content_sha256": SHA["bundle_content"],
            "instrument_registry_sha256": SHA["registry"],
        },
        "catalog": {"content_sha256": SHA["catalog"], "revision": 7},
        "inventory": {
            "by_kind": [inventory("trade", 10, 100), inventory("mark", 20, 200)],
            "instrument_count": 2,
            "selection_count": 2,
            "source_count": 1,
        },
        "performance": {"envelope": {"owner_review_required": True, "qualified": False}},
        "quality": {
            "candle": {
                "conflicting_key_count": 0,
                "duplicate_key_count": 0,
                "lifecycle_failure_count": 0,
                "missing_minute_count": 3,
                "unexpected_timestamp_count": 0,
                "unrequested_row_count": 0,
            }
        },
    }


def _funding() -> dict[str, Any]:
    return {
        "bindings": {
            "candle_evidence_artifact_sha256": SHA["candle_artifact"],
            "capacity_evidence_sha256": SHA["capacity"],
            "instrument_registry_sha256": SHA["registry"],
        },
        "inventory": {
            "canonical_dataset_count": 1,
            "canonical_row_count": 5,
            "source_count": 1,
            "symbol_count": 2,
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
        "universe": {"interval_partition_exact": True, "symbol_count": 2},
    }


def _performance() -> dict[str, Any]:
    return {
        "bindings": {
            "bundle_evidence_artifact_sha256": SHA["bundle_artifact"],
            "bundle_evidence_content_sha256": SHA["bundle_content"],
            "catalog_content_sha256": SHA["catalog"],
            "catalog_revision": 7,
        },
        "configuration": {"selection_count": 2},
        "correctness": {
            "dataset_count": 2,
            "deterministic_repeat_equal": True,
            "object_count": 2,
            "row_count": 30,
            "size_bytes": 300,
            "source_count": 1,
            "state_fingerprint_equal_before_after": True,
        },
        "measurement": {
            "first_pass_rows_per_second": 100,
            "first_pass_wall_elapsed_ns": 300_000_000,
            "repeat_pass_rows_per_second": 150,
            "repeat_pass_wall_elapsed_ns": 200_000_000,
        },
    }


def _record(name: str, contract: str, status: str, artifact_sha256: str) -> dict[str, str]:
    return {
        "artifact": f"{name}.json",
        "artifact_sha256": artifact_sha256,
        "content_sha256": "7" * 64,
        "contract": contract,
        "status": status,
    }


def _build(
    monkeypatch: pytest.MonkeyPatch,
    *,
    candle: dict[str, Any] | None = None,
    funding: dict[str, Any] | None = None,
    performance: dict[str, Any] | None = None,
    prior_artifact_sha256: str = readiness_module.PRIOR_ARTIFACT_SHA256,
) -> dict[str, Any]:
    sources = {
        PRIOR_SPEC.contract: (
            _prior(),
            {
                **_record(
                    "prior",
                    PRIOR_SPEC.contract,
                    PRIOR_SPEC.status,
                    prior_artifact_sha256,
                ),
                "content_sha256": readiness_module.PRIOR_CONTENT_SHA256,
            },
        ),
        CANDLE_SPEC.contract: (
            candle or _candle(),
            _record(
                "candles",
                CANDLE_SPEC.contract,
                CANDLE_SPEC.status,
                SHA["candle_artifact"],
            ),
        ),
        readiness_module.FUNDING_SPEC.contract: (
            funding or _funding(),
            _record(
                "funding",
                readiness_module.FUNDING_SPEC.contract,
                readiness_module.FUNDING_SPEC.status,
                "9" * 64,
            ),
        ),
        readiness_module.PERFORMANCE_SPEC.contract: (
            performance or _performance(),
            _record(
                "performance",
                readiness_module.PERFORMANCE_SPEC.contract,
                readiness_module.PERFORMANCE_SPEC.status,
                "a" * 64,
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
    return build_gate2_readiness_pack_v4(
        implementation_identity=IMPLEMENTATION,
        generated_at_utc=GENERATED,
        prior_readiness_path=Path("prior.json"),
        candle_evidence_path=Path("candles.json"),
        funding_evidence_path=Path("funding.json"),
        catalog_performance_path=Path("performance.json"),
        repo_root=ROOT,
    )


def test_gate2_readiness_v4_preserves_gate_and_adds_sanitized_observations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _build(monkeypatch)
    schema = json.loads(
        (ROOT / "schemas/evidence/v4/gate2-readiness-pack.schema.json").read_text(encoding="utf-8")
    )

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    content_sha256 = hash_input.pop("content_sha256")
    assert content_sha256 == canonical_sha256(hash_input)
    assert payload["gate_2"] == readiness_module.EXPECTED_GATE
    assert payload["readiness_counts"] == _prior()["readiness_counts"]
    assert payload["criteria"] == _prior()["criteria"]
    assert payload["observations"]["current_universe_catalog_performance"] == {
        "dataset_count": 2,
        "deterministic_repeat_equal": True,
        "first_pass_rows_per_second": 100,
        "first_pass_wall_elapsed_ns": 300_000_000,
        "repeat_pass_rows_per_second": 150,
        "repeat_pass_wall_elapsed_ns": 200_000_000,
        "row_count": 30,
        "state_fingerprint_equal_before_after": True,
    }
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
    ):
        assert forbidden not in rendered


def test_gate2_readiness_v4_rejects_cross_bound_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    funding = _funding()
    funding["bindings"]["candle_evidence_artifact_sha256"] = "f" * 64

    with pytest.raises(Gate2ReadinessV4Error, match="binds another candle"):
        _build(monkeypatch, funding=funding)


def test_gate2_readiness_v4_rejects_resealed_prior_substitution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(Gate2ReadinessV4Error, match="differs from the accepted source"):
        _build(monkeypatch, prior_artifact_sha256="f" * 64)


def test_gate2_readiness_v4_rejects_quality_contradiction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candle = _candle()
    candle["quality"]["candle"]["duplicate_key_count"] = 1

    with pytest.raises(Gate2ReadinessV4Error, match="quality contradicts v3"):
        _build(monkeypatch, candle=candle)


def test_gate2_readiness_v4_verifies_committed_prior_receipt() -> None:
    path = ROOT / "benchmarks/results/m2-gate2-readiness-pack-v3-20260814.json"

    payload, record = readiness_module._verify_source(path, PRIOR_SPEC, ROOT)

    assert payload["gate_2"]["blocker_codes"] == EXPECTED_BLOCKERS
    assert record["artifact"] == path.name
    assert record["content_sha256"] == payload["content_sha256"]


def test_gate2_readiness_v4_cli_returns_two_after_negative_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "readiness-v4.json"
    published = False

    def publish(**_arguments: object) -> dict[str, Any]:
        nonlocal published
        published = True
        return {
            "readiness_counts": {"blocked_criterion_count": 3},
            "status": "blocked-current-universe-evidence-awaiting-owner-policy",
        }

    monkeypatch.setattr(readiness_module, "publish_gate2_readiness_pack_v4", publish)
    monkeypatch.setattr(
        "sys.argv",
        [
            "gate2-readiness-v4",
            "--implementation-identity",
            IMPLEMENTATION,
            "--prior-readiness",
            "prior.json",
            "--candle-evidence",
            "candles.json",
            "--funding-evidence",
            "funding.json",
            "--catalog-performance",
            "performance.json",
            "--output",
            str(output),
        ],
    )

    assert readiness_module.main() == 2
    assert published
