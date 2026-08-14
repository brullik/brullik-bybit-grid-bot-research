from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from grid_contracts.canonical import canonical_json_bytes, canonical_sha256
from grid_data.evidence import publish_evidence, verify_evidence
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from benchmarks.current_universe_candle_evidence import (
    publish_current_universe_candle_evidence,
)
from benchmarks.current_universe_funding_evidence import (
    CurrentUniverseFundingEvidenceError,
    build_current_universe_funding_evidence,
    publish_current_universe_funding_evidence,
)

ROOT = Path(__file__).resolve().parents[2]
SOFTWARE_IDENTITY = "git:" + "d" * 40
START_MS = 0
END_MS = 120_000


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(payload) + b"\n")
    return path


def _with_content_hash(payload: dict[str, Any]) -> dict[str, Any]:
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def _campaign_request(
    *, campaign_id: str, symbols: list[str], kinds: list[str], start_ms: int = START_MS
) -> dict[str, Any]:
    return {
        "campaign_id": campaign_id,
        "contract": "grid.public-history-campaign-request/v1",
        "end_ms": END_MS,
        "funding_page_limit": 200,
        "funding_page_span_minutes": 10080,
        "history_page_limit": 1000,
        "kinds": kinds,
        "lifecycle_policy": "registry-lifecycle-intersection-v1",
        "max_attempts": 3,
        "start_ms": start_ms,
        "symbols": symbols,
        "target_rps": 10,
        "workers": 4,
    }


def _kind_row(kind: str, rows: int) -> dict[str, Any]:
    return {
        "http_request_count": 1,
        "job_count": 1,
        "kind": kind,
        "page_count": 1,
        "row_count": rows,
    }


def _publication_kind(kind: str, rows: int) -> dict[str, Any]:
    return {
        "dataset_count": 1,
        "file_count": 1,
        "kind": kind,
        "parquet_bytes": 100 + rows,
        "row_count": rows,
    }


def _coverage_kind(kind: str, rows: int, *, blocked: bool) -> dict[str, Any]:
    return {
        "blocked_count": int(blocked),
        "dataset_count": 1,
        "kind": kind,
        "passed_count": int(not blocked),
        "row_count": rows,
    }


def _publish_campaign_triplet(
    root: Path,
    *,
    label: str,
    request: dict[str, Any],
    rows_by_kind: dict[str, int],
    boundary_manifest: str | None = None,
    blocked_reason: str | None = None,
    publication_timing: bool = True,
) -> tuple[Path, Path, Path, Path]:
    request_path = _write_json(root / f"{label}-request.json", request)
    request_hash = canonical_sha256(request)
    registry_hash = _sha("registry")
    capacity_hash = _sha("capacity")
    campaign_manifest = _sha(f"{label}-campaign-manifest")
    campaign_plan = _sha(f"{label}-campaign-plan")
    publication_manifest = _sha(f"{label}-publication-manifest")
    publication_plan = _sha(f"{label}-publication-plan")
    publisher_identity = "git:" + "a" * 40
    scope = {
        "bucket_count": 1,
        "end_ms": request["end_ms"],
        "kind_count": len(rows_by_kind),
        "month_count": 1,
        "start_ms": request["start_ms"],
        "symbol_count": len(request["symbols"]),
    }
    landing_bindings = {
        "campaign_manifest_sha256": campaign_manifest,
        "campaign_plan_sha256": campaign_plan,
        "campaign_request_sha256": request_hash,
        "capacity_evidence_sha256": capacity_hash,
        "instrument_registry_sha256": registry_hash,
    }
    if boundary_manifest is not None:
        landing_bindings["funding_source_boundary_manifest_sha256"] = boundary_manifest
    landing_rows = [_kind_row(kind, rows) for kind, rows in rows_by_kind.items()]
    landing: dict[str, Any] = {
        "bindings": landing_bindings,
        "evidence_schema": "grid.phase2-public-history-campaign/v1",
        "generated_at_utc": "2026-08-14T18:00:00Z",
        "landing": {
            "artifact_bytes": 1000,
            "by_kind": landing_rows,
            "http_request_count": len(landing_rows),
            "job_count": len(landing_rows),
            "page_count": len(landing_rows),
            "retry_count": 0,
            "row_count": sum(item["row_count"] for item in landing_rows),
        },
        "limitations": ["a", "b", "c", "d"],
        "process": {
            "aggregate_receipt_verified": True,
            "child_receipts_verified": True,
            "deterministic_resume_supported": True,
            "software_identity": SOFTWARE_IDENTITY,
        },
        "scope": scope,
        "source_policy": {
            "authentication": "none",
            "base_url": "https://api.bybit.com",
            "funding_endpoint": "/v5/market/funding/history",
            "mark_endpoint": "/v5/market/mark-price-kline",
            "private_endpoints_called": False,
            "tick_rows_requested": False,
            "trade_endpoint": "/v5/market/kline",
        },
        "status": "verified-public-landing-campaign",
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_market_values": False,
            "evidence_contains_runtime_paths": False,
            "runtime_market_artifacts_committed_to_git": False,
        },
        "timing": {
            "campaign_completed_at_ms": 2000,
            "campaign_elapsed_ms": 1000,
            "campaign_started_at_ms": 1000,
            "summed_child_elapsed_ms": 500,
            "timed_child_count": len(landing_rows),
        },
    }
    landing_path = root / f"{label}-landing.json"
    publish_evidence(landing_path, _with_content_hash(landing))

    publication_rows = [_publication_kind(kind, rows) for kind, rows in rows_by_kind.items()]
    publication: dict[str, Any] = {
        "bindings": {
            "capacity_evidence_sha256": capacity_hash,
            "instrument_registry_sha256": registry_hash,
            "publication_manifest_sha256": publication_manifest,
            "publication_plan_sha256": publication_plan,
            "source_campaign_manifest_sha256": campaign_manifest,
            "source_campaign_plan_sha256": campaign_plan,
            "source_campaign_request_sha256": request_hash,
        },
        "canonical": {
            "by_kind": publication_rows,
            "dataset_count": len(publication_rows),
            "file_count": len(publication_rows),
            "parquet_bytes": sum(item["parquet_bytes"] for item in publication_rows),
            "row_count": sum(item["row_count"] for item in publication_rows),
        },
        "evidence_schema": "grid.phase2-history-campaign-publication/v1",
        "generated_at_utc": "2026-08-14T18:01:00Z",
        "limitations": ["a", "b", "c", "d", "e"],
        "process": {
            "canonical_child_receipts_verified": True,
            "deterministic_resume_supported": True,
            "evidence_builder_software_identity": SOFTWARE_IDENTITY,
            "max_concurrent_writers": 1,
            "publication_aggregate_receipt_verified": True,
            "publisher_software_identity": publisher_identity,
            "source_aggregate_receipt_verified": True,
            "source_child_receipts_verified": True,
        },
        "resource_bounds": {
            "maximum_child_planned_peak_memory_bytes": 1,
            "maximum_child_required_free_bytes": 1,
        },
        "scope": scope,
        "status": "verified-canonical-history-campaign-publication",
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_instrument_identities": False,
            "evidence_contains_market_values": False,
            "evidence_contains_runtime_paths": False,
            "runtime_market_artifacts_committed_to_git": False,
        },
    }
    if publication_timing:
        publication["timing"] = {
            "completed_at_ms": 2600,
            "elapsed_ms": 500,
            "started_at_ms": 2100,
        }
    publication_path = root / f"{label}-publication.json"
    publish_evidence(publication_path, _with_content_hash(publication))

    blocked = blocked_reason is not None
    coverage_rows = [
        _coverage_kind(kind, rows, blocked=blocked and kind == "funding")
        for kind, rows in rows_by_kind.items()
    ]
    funding_rows = rows_by_kind.get("funding", 0)
    candle_rows = sum(rows for kind, rows in rows_by_kind.items() if kind != "funding")
    observed_reasons = {blocked_reason: 1} if blocked_reason else {}
    coverage: dict[str, Any] = {
        "audit_software_identity": SOFTWARE_IDENTITY,
        "bindings": {
            "capacity_evidence_sha256": capacity_hash,
            "instrument_registry_sha256": registry_hash,
            "publication_manifest_sha256": publication_manifest,
            "publication_plan_sha256": publication_plan,
            "publisher_software_identity": publisher_identity,
            "source_campaign_manifest_sha256": campaign_manifest,
            "source_campaign_plan_sha256": campaign_plan,
        },
        "child_results": [
            {
                "audit_content_sha256": _sha(f"{label}-audit-{index}"),
                "kind": item["kind"],
                "sequence": index,
                "status": "blocked" if item["blocked_count"] else "passed",
            }
            for index, item in enumerate(coverage_rows)
        ],
        "contract": "grid.history-campaign-coverage-audit/v1",
        "generated_at_utc": "2026-08-14T18:02:00Z",
        "inventory": {
            "blocked_count": sum(item["blocked_count"] for item in coverage_rows),
            "by_kind": coverage_rows,
            "dataset_count": len(coverage_rows),
            "passed_count": sum(item["passed_count"] for item in coverage_rows),
            "row_count": sum(item["row_count"] for item in coverage_rows),
        },
        "limitations": ["a", "b", "c", "d"],
        "quality": {
            "candle": {
                "conflicting_key_count": 0,
                "duplicate_key_count": 0,
                "expected_minute_count": candle_rows,
                "gap_range_count": 0,
                "lifecycle_failure_count": 0,
                "missing_minute_count": 0,
                "observed_row_count": candle_rows,
                "unexpected_timestamp_count": 0,
                "unrequested_row_count": 0,
            },
            "funding": {
                "boundary_page_count": int(funding_rows > 0),
                "duplicate_key_count": 0,
                "empty_range_page_count": 0,
                "internal_interval_mismatch_count": 0,
                "interval_change_count": int(blocked_reason == "unexplained_interval_change"),
                "lifecycle_failure_count": 0,
                "observed_event_count": funding_rows,
                "predecessor_interval_mismatch_count": 0,
                "range_page_count": int(funding_rows > 0),
                "unexpected_timestamp_count": 0,
                "unrequested_row_count": 0,
            },
        },
        "reason_policy": {
            "accepted_reason_codes": [],
            "observed_reason_counts": observed_reasons,
            "unaccepted_reason_codes": list(observed_reasons),
            "unknown_reason_count": 0,
        },
        "status": "blocked" if blocked else "passed",
        "storage_policy": {
            "account_data_included": False,
            "dataset_or_instrument_identities_included": False,
            "market_values_included": False,
            "runtime_paths_included": False,
        },
    }
    coverage_path = root / f"{label}-coverage.json"
    publish_evidence(coverage_path, _with_content_hash(coverage))
    return request_path, landing_path, publication_path, coverage_path


def _publish_boundary(
    root: Path, *, label: str, symbols: list[str], manifest_hash: str, landing_rows: int
) -> tuple[Path, Path]:
    request = {
        "contract": "grid.bybit-funding-source-boundary-request/v1",
        "discovery_id": label,
        "end_ms": END_MS,
        "max_attempts": 3,
        "max_pages_per_symbol": 512,
        "page_limit": 200,
        "start_ms": START_MS,
        "symbols": symbols,
        "target_rps": 10,
        "workers": 4,
    }
    request_path = _write_json(root / f"{label}-boundary-request.json", request)
    event_count = landing_rows + len(symbols)
    payload: dict[str, Any] = {
        "adaptive_throttling": {
            "automatic_increase_count": 0,
            "complete_header_observation_count": 0,
            "completed_page_response_coverage_complete": True,
            "configured_target_rps": 10,
            "cooldown_event_count": 0,
            "final_effective_rps": 10,
            "header_absent_observation_count": 1,
            "invalid_header_observation_count": 0,
            "low_headroom_event_count": 0,
            "maximum_cooldown_ms": 0,
            "minimum_effective_rps": 10,
            "policy": "bybit-v5-response-header-decrease-only-v1",
            "rate_limit_event_count": 0,
            "rate_reduction_count": 0,
            "response_observation_count": 1,
            "transport_attempt_accounting_complete": True,
            "transport_attempt_count": 1,
            "transport_attempt_without_response_count": 0,
        },
        "bindings": {
            "boundary_manifest_sha256": manifest_hash,
            "boundary_plan_sha256": _sha(f"{label}-boundary-plan"),
            "boundary_request_sha256": canonical_sha256(request),
            "instrument_registry_sha256": _sha("registry"),
        },
        "evidence_schema": "grid.phase2-funding-source-boundary/v1",
        "generated_at_utc": "2026-08-14T17:00:00Z",
        "landing": {
            "event_count": event_count,
            "http_attempt_count": 1,
            "page_count": 1,
            "retry_count": 0,
        },
        "limitations": ["a", "b", "c", "d"],
        "process": {
            "aggregate_receipt_verified": True,
            "deterministic_resume_supported": True,
            "discovery_software_identity": SOFTWARE_IDENTITY,
            "evidence_software_identity": SOFTWARE_IDENTITY,
            "page_receipts_verified": True,
        },
        "result": {
            "canonical_start_proven_count": len(symbols),
            "predecessor_proven_count": len(symbols),
        },
        "scope": {
            "end_ms": END_MS,
            "start_ms": START_MS,
            "symbol_count": len(symbols),
        },
        "source_policy": {
            "authentication": "none",
            "base_url": "https://api.bybit.com",
            "endpoint": "/v5/market/funding/history",
            "private_endpoints_called": False,
            "retained_source_fields": ["fundingRateTimestamp"],
            "source_rates_validated_not_retained": True,
        },
        "status": "verified-public-funding-source-boundary",
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_funding_rates": False,
            "evidence_contains_instrument_identifiers": False,
            "evidence_contains_observed_settlement_timestamps": False,
            "evidence_contains_runtime_paths": False,
            "runtime_market_artifacts_committed_to_git": False,
        },
    }
    evidence_path = root / f"{label}-boundary.json"
    publish_evidence(evidence_path, _with_content_hash(payload))
    return request_path, evidence_path


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _fixture(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    candle_triplets = []
    candle_requests = [
        _campaign_request(campaign_id="candle-a", symbols=["AAA", "CCC"], kinds=["trade", "mark"]),
        _campaign_request(campaign_id="candle-b", symbols=["BBB"], kinds=["trade", "mark"]),
    ]
    for index, request in enumerate(candle_requests):
        candle_triplets.append(
            _publish_campaign_triplet(
                tmp_path,
                label=f"candle-{index}",
                request=request,
                rows_by_kind={"trade": 3, "mark": 3},
            )
        )

    bundle_request: dict[str, Any] = {
        "bundle_id": "current-universe-test",
        "catalog_content_sha256": _sha("catalog"),
        "catalog_revision": 1,
        "consumer_software_identity": SOFTWARE_IDENTITY,
        "contract": "grid.canonical-catalog-selection-bundle-request/v1",
        "sources": [
            {
                "campaign_id": request["campaign_id"],
                "end_time_ms": END_MS,
                "start_time_ms": START_MS,
            }
            for request in candle_requests
        ],
    }
    bundle_request_path = _write_json(tmp_path / "bundle-request.json", bundle_request)
    by_kind = [
        {
            "dataset_count": 2,
            "kind": kind,
            "object_count": 2,
            "row_count": 6,
            "selection_count": 1,
            "size_bytes": 206,
        }
        for kind in ("trade", "mark")
    ]
    source_chain = []
    for _request, landing_path, publication_path, _coverage_path in candle_triplets:
        landing = json.loads(landing_path.read_text(encoding="utf-8"))
        publication = json.loads(publication_path.read_text(encoding="utf-8"))
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
    bundle: dict[str, Any] = {
        "assurances": {
            "catalog_snapshot_bound": True,
            "cross_source_key_space_disjoint": True,
            "network_request_performed": False,
            "private_or_live_capability_used": False,
            "selection_receipts_verified": True,
            "source_campaigns_and_publications_verified": True,
        },
        "bindings": {
            "bundle_manifest_artifact_sha256": _sha("bundle-manifest"),
            "bundle_plan_sha256": _sha("bundle-plan"),
            "bundle_request_sha256": canonical_sha256(bundle_request),
            "evidence_builder_software_identity": SOFTWARE_IDENTITY,
            "selection_chain_sha256": _sha("selections"),
            "source_chain_sha256": canonical_sha256(source_chain),
        },
        "catalog": {"content_sha256": _sha("catalog"), "revision": 1},
        "evidence_schema": "grid.phase2-catalog-selection-bundle/v1",
        "generated_at_utc": "2026-08-14T18:03:00Z",
        "inventory": {
            "by_kind": by_kind,
            "dataset_count": 4,
            "empty_object_count": 0,
            "instrument_count": 3,
            "object_count": 4,
            "row_count": 12,
            "selection_count": 2,
            "size_bytes": 412,
            "source_count": 2,
        },
        "limitations": ["a", "b", "c", "d"],
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
    bundle_path = tmp_path / "bundle.json"
    publish_evidence(bundle_path, _with_content_hash(bundle))
    candle_path = tmp_path / "candle-evidence.json"
    publish_current_universe_candle_evidence(
        landing_evidence_paths=[item[1] for item in candle_triplets],
        publication_evidence_paths=[item[2] for item in candle_triplets],
        coverage_evidence_paths=[item[3] for item in candle_triplets],
        catalog_bundle_evidence_path=bundle_path,
        generated_at_utc="2026-08-14T18:04:00Z",
        software_identity=SOFTWARE_IDENTITY,
        output=candle_path,
    )

    boundary_manifest = _sha("funding-a-boundary-manifest")
    funding_a = _publish_campaign_triplet(
        tmp_path,
        label="funding-a",
        request=_campaign_request(
            campaign_id="funding-a", symbols=["CCC", "AAA"], kinds=["funding"]
        ),
        rows_by_kind={"funding": 2},
        boundary_manifest=boundary_manifest,
    )
    boundary_request, boundary_evidence = _publish_boundary(
        tmp_path,
        label="funding-a",
        symbols=["AAA", "CCC"],
        manifest_hash=boundary_manifest,
        landing_rows=2,
    )
    funding_b = _publish_campaign_triplet(
        tmp_path,
        label="funding-b",
        request=_campaign_request(
            campaign_id="funding-b", symbols=["BBB"], kinds=["trade", "mark", "funding"]
        ),
        rows_by_kind={"trade": 3, "mark": 3, "funding": 2},
        blocked_reason="unexplained_interval_change",
        publication_timing=False,
    )
    manifest: dict[str, Any] = {
        "candle_bundle_evidence": _relative(tmp_path, bundle_path),
        "candle_bundle_request": _relative(tmp_path, bundle_request_path),
        "candle_evidence": _relative(tmp_path, candle_path),
        "candle_sources": [
            {
                "coverage_evidence": _relative(tmp_path, item[3]),
                "landing_evidence": _relative(tmp_path, item[1]),
                "publication_evidence": _relative(tmp_path, item[2]),
                "request": _relative(tmp_path, item[0]),
            }
            for item in candle_triplets
        ],
        "contract": "grid.current-universe-funding-evidence-request/v1",
        "funding_sources": [
            {
                "boundary_evidence": _relative(tmp_path, boundary_evidence),
                "boundary_request": _relative(tmp_path, boundary_request),
                "coverage_evidence": _relative(tmp_path, funding_a[3]),
                "landing_evidence": _relative(tmp_path, funding_a[1]),
                "mode": "boundary-backed",
                "publication_evidence": _relative(tmp_path, funding_a[2]),
                "request": _relative(tmp_path, funding_a[0]),
            },
            {
                "coverage_evidence": _relative(tmp_path, funding_b[3]),
                "landing_evidence": _relative(tmp_path, funding_b[1]),
                "mode": "reused-bounded",
                "publication_evidence": _relative(tmp_path, funding_b[2]),
                "request": _relative(tmp_path, funding_b[0]),
            },
        ],
    }
    manifest_path = _write_json(tmp_path / "source-manifest.json", manifest)
    return manifest_path, manifest


def test_current_universe_funding_evidence_reconciles_exact_scope(tmp_path: Path) -> None:
    manifest_path, _manifest = _fixture(tmp_path)
    payload = build_current_universe_funding_evidence(
        source_manifest_path=manifest_path,
        artifact_root=tmp_path,
        generated_at_utc="2026-08-14T18:05:00Z",
        software_identity=SOFTWARE_IDENTITY,
    )

    assert payload["status"] == "verified-current-universe-funding-evidence"
    assert payload["universe"] == {
        "candle_source_count": 2,
        "funding_source_count": 2,
        "interval_partition_exact": True,
        "symbol_count": 3,
    }
    assert payload["inventory"]["canonical_row_count"] == 4
    assert payload["source_boundary"]["source_count"] == 1
    assert payload["quality"]["coverage_status"] == "blocked"
    assert payload["quality"]["funding"]["interval_change_count"] == 1
    assert payload["performance"]["publication"]["timed_source_count"] == 1
    rendered = json.dumps(payload, sort_keys=True).lower()
    for forbidden in (
        '"aaa"',
        '"bbb"',
        '"ccc"',
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        '"symbol"',
        '"instrument_id"',
        '"dataset_id"',
        '"runtime_path"',
        '"campaign_id"',
        '"funding_time_ms"',
    ):
        assert forbidden not in rendered
    schema = cast(
        dict[str, Any],
        json.loads(
            (
                ROOT / "schemas/evidence/v1/phase2-current-universe-funding-evidence.schema.json"
            ).read_text(encoding="utf-8")
        ),
    )
    Draft202012Validator(schema).validate(payload)


def test_current_universe_funding_evidence_publishes_receipt(tmp_path: Path) -> None:
    manifest_path, _manifest = _fixture(tmp_path)
    output = tmp_path / "funding-evidence.json"
    payload = publish_current_universe_funding_evidence(
        source_manifest_path=manifest_path,
        artifact_root=tmp_path,
        generated_at_utc="2026-08-14T18:05:00Z",
        software_identity=SOFTWARE_IDENTITY,
        output=output,
    )

    assert verify_evidence(output)
    assert payload["assurances"]["network_request_performed"] is False
    assert payload["assurances"]["phase3_authorized"] is False


def test_current_universe_funding_evidence_rejects_incomplete_scope(tmp_path: Path) -> None:
    manifest_path, manifest = _fixture(tmp_path)
    manifest["funding_sources"] = manifest["funding_sources"][:1]
    _write_json(manifest_path, manifest)

    with pytest.raises(
        CurrentUniverseFundingEvidenceError,
        match="do not exactly cover",
    ):
        build_current_universe_funding_evidence(
            source_manifest_path=manifest_path,
            artifact_root=tmp_path,
            generated_at_utc="2026-08-14T18:05:00Z",
            software_identity=SOFTWARE_IDENTITY,
        )


def test_current_universe_funding_evidence_rejects_boundary_count_substitution(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _fixture(tmp_path)
    source = manifest["funding_sources"][0]
    original_path = tmp_path / source["boundary_evidence"]
    payload = cast(dict[str, Any], json.loads(original_path.read_text(encoding="utf-8")))
    payload.pop("content_sha256")
    payload["landing"]["event_count"] += 1
    bad_path = tmp_path / "bad-boundary.json"
    publish_evidence(bad_path, _with_content_hash(payload))
    source["boundary_evidence"] = _relative(tmp_path, bad_path)
    _write_json(manifest_path, manifest)

    with pytest.raises(
        CurrentUniverseFundingEvidenceError,
        match="boundary/campaign event counts differ",
    ):
        build_current_universe_funding_evidence(
            source_manifest_path=manifest_path,
            artifact_root=tmp_path,
            generated_at_utc="2026-08-14T18:05:00Z",
            software_identity=SOFTWARE_IDENTITY,
        )


def test_current_universe_funding_evidence_rejects_blocked_reused_candle_scope(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _fixture(tmp_path)
    source = manifest["funding_sources"][1]
    original_path = tmp_path / source["coverage_evidence"]
    payload = cast(dict[str, Any], json.loads(original_path.read_text(encoding="utf-8")))
    payload.pop("content_sha256")
    inventory = payload["inventory"]
    trade = next(item for item in inventory["by_kind"] if item["kind"] == "trade")
    trade["blocked_count"] = 1
    trade["passed_count"] = 0
    inventory["blocked_count"] += 1
    inventory["passed_count"] -= 1
    bad_path = tmp_path / "bad-reused-coverage.json"
    publish_evidence(bad_path, _with_content_hash(payload))
    source["coverage_evidence"] = _relative(tmp_path, bad_path)
    _write_json(manifest_path, manifest)

    with pytest.raises(
        CurrentUniverseFundingEvidenceError,
        match="blocked non-funding coverage",
    ):
        build_current_universe_funding_evidence(
            source_manifest_path=manifest_path,
            artifact_root=tmp_path,
            generated_at_utc="2026-08-14T18:05:00Z",
            software_identity=SOFTWARE_IDENTITY,
        )
