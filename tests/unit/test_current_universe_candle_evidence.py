from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from grid_contracts.canonical import canonical_sha256
from grid_data.evidence import publish_evidence, verify_evidence
from jsonschema import Draft202012Validator

from benchmarks.current_universe_candle_evidence import (
    CurrentUniverseCandleEvidenceError,
    build_current_universe_candle_evidence,
    publish_current_universe_candle_evidence,
)

ROOT = Path(__file__).resolve().parents[2]
SOFTWARE_IDENTITY = "git:" + "d" * 40
LANDING_PATHS = (
    ROOT / "benchmarks/results/m2-public-history-oldest-5-full-candles-20260814.json",
    ROOT / "benchmarks/results/m2-public-history-long-run-100x31-20260813.json",
)
PUBLICATION_PATHS = (
    ROOT / "benchmarks/results/m2-canonical-history-campaign-20260814.json",
    ROOT / "benchmarks/results/m2-canonical-history-campaign-100x31-20260813.json",
)
COVERAGE_PATHS = (
    ROOT / "benchmarks/results/m2-history-campaign-coverage-audit-20260814.json",
    ROOT / "benchmarks/results/m2-history-campaign-coverage-audit-100x31-20260813.json",
)


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _by_kind(parent: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    return {item["kind"]: item for item in parent[key]}


def _catalog_bundle_payload() -> dict[str, Any]:
    publications = [_load(path) for path in PUBLICATION_PATHS]
    landings = [_load(path) for path in LANDING_PATHS]
    by_kind: list[dict[str, Any]] = []
    for kind in ("trade", "mark"):
        rows = [_by_kind(item["canonical"], "by_kind")[kind] for item in publications]
        by_kind.append(
            {
                "dataset_count": sum(item["dataset_count"] for item in rows),
                "kind": kind,
                "object_count": sum(item["file_count"] for item in rows),
                "row_count": sum(item["row_count"] for item in rows),
                "selection_count": 1,
                "size_bytes": sum(item["parquet_bytes"] for item in rows),
            }
        )
    source_chain = []
    for landing, publication in zip(landings, publications, strict=True):
        source_chain.append(
            {
                "campaign_manifest_sha256": landing["bindings"]["campaign_manifest_sha256"],
                "campaign_plan_sha256": landing["bindings"]["campaign_plan_sha256"],
                "publication_manifest_sha256": publication["bindings"][
                    "publication_manifest_sha256"
                ],
                "publication_plan_sha256": publication["bindings"]["publication_plan_sha256"],
            }
        )
    payload: dict[str, Any] = {
        "assurances": {
            "catalog_snapshot_bound": True,
            "cross_source_key_space_disjoint": True,
            "network_request_performed": False,
            "private_or_live_capability_used": False,
            "selection_receipts_verified": True,
            "source_campaigns_and_publications_verified": True,
        },
        "bindings": {
            "bundle_manifest_artifact_sha256": "1" * 64,
            "bundle_plan_sha256": "2" * 64,
            "bundle_request_sha256": "3" * 64,
            "evidence_builder_software_identity": SOFTWARE_IDENTITY,
            "selection_chain_sha256": "4" * 64,
            "source_chain_sha256": canonical_sha256(source_chain),
        },
        "catalog": {"content_sha256": "5" * 64, "revision": 8},
        "evidence_schema": "grid.phase2-catalog-selection-bundle/v1",
        "generated_at_utc": "2026-08-14T18:00:00Z",
        "inventory": {
            "by_kind": by_kind,
            "dataset_count": sum(item["dataset_count"] for item in by_kind),
            "empty_object_count": 268,
            "instrument_count": 100,
            "object_count": sum(item["object_count"] for item in by_kind),
            "row_count": sum(item["row_count"] for item in by_kind),
            "selection_count": sum(item["selection_count"] for item in by_kind),
            "size_bytes": sum(item["size_bytes"] for item in by_kind),
            "source_count": 2,
        },
        "limitations": [
            "Catalog selection does not prove gap-free historical coverage or lifecycle reasons.",
            "The bundle is candle-only and does not accept funding chronology or cadence.",
            "Schema-only objects remain explicit and do not accept missing source history.",
            "This evidence does not close Gate 2, authorize Phase 3, or enable live execution.",
        ],
        "status": "verified-catalog-selection-bundle",
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_dataset_identities": False,
            "evidence_contains_instrument_identities": False,
            "evidence_contains_market_values": False,
            "evidence_contains_request_time_bounds": False,
            "evidence_contains_runtime_paths": False,
            "runtime_catalog_or_market_artifacts_committed_to_git": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def _publish_catalog(tmp_path: Path, payload: dict[str, Any] | None = None) -> Path:
    path = tmp_path / "catalog-bundle.json"
    publish_evidence(path, payload or _catalog_bundle_payload())
    return path


def test_current_universe_candle_evidence_reconciles_public_source_chains(
    tmp_path: Path,
) -> None:
    catalog = _publish_catalog(tmp_path)
    payload = build_current_universe_candle_evidence(
        landing_evidence_paths=LANDING_PATHS,
        publication_evidence_paths=PUBLICATION_PATHS,
        coverage_evidence_paths=COVERAGE_PATHS,
        catalog_bundle_evidence_path=catalog,
        generated_at_utc="2026-08-14T18:01:00Z",
        software_identity=SOFTWARE_IDENTITY,
    )

    assert payload["status"] == "verified-current-universe-candle-evidence"
    assert payload["inventory"]["source_count"] == 2
    assert payload["quality"]["coverage_status"] == "blocked"
    assert payload["quality"]["candle"]["duplicate_key_count"] == 0
    assert payload["performance"]["acquisition"]["campaign_count"] == 2
    assert payload["performance"]["publication"] == {
        "complete_source_timing": False,
        "earliest_started_at_ms": None,
        "latest_completed_at_ms": None,
        "source_count": 2,
        "summed_elapsed_ms": 0,
        "timed_source_count": 0,
    }
    assert payload["performance"]["envelope"]["qualified"] is False
    assert payload["excluded_funding"]["canonical_dataset_count"] == 8
    rendered = json.dumps(payload, sort_keys=True).lower()
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        '"symbol"',
        '"instrument_id"',
        '"dataset_id"',
        '"runtime_path"',
        '"campaign_id"',
        '"open_time_ms"',
    ):
        assert forbidden not in rendered
    schema = _load(ROOT / "schemas/evidence/v1/phase2-current-universe-candle-evidence.schema.json")
    Draft202012Validator(schema).validate(payload)


def test_current_universe_candle_evidence_publishes_receipt(tmp_path: Path) -> None:
    catalog = _publish_catalog(tmp_path)
    output = tmp_path / "current-universe.json"
    payload = publish_current_universe_candle_evidence(
        landing_evidence_paths=LANDING_PATHS,
        publication_evidence_paths=PUBLICATION_PATHS,
        coverage_evidence_paths=COVERAGE_PATHS,
        catalog_bundle_evidence_path=catalog,
        generated_at_utc="2026-08-14T18:01:00Z",
        software_identity=SOFTWARE_IDENTITY,
        output=output,
    )

    assert verify_evidence(output)
    assert payload["assurances"]["market_store_read"] is False
    assert payload["assurances"]["phase3_authorized"] is False


def test_current_universe_candle_evidence_rejects_source_order_substitution(
    tmp_path: Path,
) -> None:
    catalog = _publish_catalog(tmp_path)

    with pytest.raises(
        CurrentUniverseCandleEvidenceError,
        match="catalog bundle source chain",
    ):
        build_current_universe_candle_evidence(
            landing_evidence_paths=tuple(reversed(LANDING_PATHS)),
            publication_evidence_paths=tuple(reversed(PUBLICATION_PATHS)),
            coverage_evidence_paths=tuple(reversed(COVERAGE_PATHS)),
            catalog_bundle_evidence_path=catalog,
            generated_at_utc="2026-08-14T18:01:00Z",
            software_identity=SOFTWARE_IDENTITY,
        )


def test_current_universe_candle_evidence_rejects_catalog_row_substitution(
    tmp_path: Path,
) -> None:
    catalog_payload = _catalog_bundle_payload()
    catalog_payload["inventory"]["by_kind"][0]["row_count"] += 1
    catalog_payload["inventory"]["row_count"] += 1
    catalog_payload.pop("content_sha256")
    catalog_payload["content_sha256"] = canonical_sha256(catalog_payload)
    catalog = _publish_catalog(tmp_path, catalog_payload)

    with pytest.raises(CurrentUniverseCandleEvidenceError, match="catalog/canonical mismatch"):
        build_current_universe_candle_evidence(
            landing_evidence_paths=LANDING_PATHS,
            publication_evidence_paths=PUBLICATION_PATHS,
            coverage_evidence_paths=COVERAGE_PATHS,
            catalog_bundle_evidence_path=catalog,
            generated_at_utc="2026-08-14T18:01:00Z",
            software_identity=SOFTWARE_IDENTITY,
        )
