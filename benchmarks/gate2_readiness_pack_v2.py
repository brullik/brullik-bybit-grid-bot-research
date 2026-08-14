"""Build the receipt-linked Gate 2 readiness successor from current evidence."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from grid_contracts.canonical import canonical_sha256
from grid_data.evidence import preflight_evidence, publish_evidence
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

from benchmarks.gate2_readiness_pack import (
    CRITERIA,
    ROOT,
    Gate2ReadinessError,
    SourceSpec,
    _load_json,
    _require,
    _verify_criteria_source,
    _verify_generated_at,
    _verify_source,
)

EVIDENCE_CONTRACT: Final = "grid.gate2-readiness-pack/v2"

SOURCE_SPECS: Final[dict[str, SourceSpec]] = {
    "announcement-archive-depth": SourceSpec(
        artifact="m2-announcement-archive-depth-oldest-5-20260814.json",
        schema="phase2-announcement-archive-depth.schema.json",
        contract_key="evidence_schema",
        contract="grid.phase2-announcement-archive-depth/v1",
        status="blocked-insufficient-official-announcement-history",
        artifact_sha256="68c12ffbf7b5824175a0e56e68f591665e8e3e480ccf6765aa3285dfc8437688",
    ),
    "canonical-integrity-fault-injection": SourceSpec(
        artifact="m2-canonical-integrity-fault-injection-20260814.json",
        schema="phase2-canonical-integrity-fault-injection.schema.json",
        contract_key="evidence_schema",
        contract="grid.phase2-canonical-integrity-fault-injection/v1",
        status="verified-canonical-integrity-fault-injection",
        artifact_sha256="93af2d7b5cf73e7f672a9d846a19bbc858e770cde2ed54780150a1ce2222e8a1",
    ),
    "coverage-audit-100x31": SourceSpec(
        artifact="m2-history-campaign-coverage-audit-100x31-20260813.json",
        schema="history-campaign-coverage-audit.schema.json",
        contract_key="contract",
        contract="grid.history-campaign-coverage-audit/v1",
        status="blocked",
        artifact_sha256="6b9fab62147a78bedf2879cadfcd6031af5d6b1f6566e42e716b902b12236358",
    ),
    "full-history-boundary-diagnostic": SourceSpec(
        artifact="m2-candle-boundary-diagnostic-20260814.json",
        schema="phase2-candle-boundary-diagnostic.schema.json",
        contract_key="contract",
        contract="grid.phase2-candle-boundary-diagnostic/v1",
        status="diagnosed-unaccepted-candle-boundaries",
        artifact_sha256="f5917d3ba23d83d56e704662126212ba18148cb6a92c009f51c75f4868872f03",
    ),
    "full-history-canonical-publication": SourceSpec(
        artifact="m2-canonical-history-campaign-20260814.json",
        schema="phase2-history-campaign-publication.schema.json",
        contract_key="evidence_schema",
        contract="grid.phase2-history-campaign-publication/v1",
        status="verified-canonical-history-campaign-publication",
        artifact_sha256="5f8598d4bc343c9384f0d9df5c1476659bd2bf86ecc11fb7faa4103ac642a74d",
    ),
    "full-history-coverage-audit": SourceSpec(
        artifact="m2-history-campaign-coverage-audit-20260814.json",
        schema="history-campaign-coverage-audit.schema.json",
        contract_key="contract",
        contract="grid.history-campaign-coverage-audit/v1",
        status="blocked",
        artifact_sha256="98d6d15dfc5a5e036b79c8d653199112a75596e7fdf397b256553295f8e1c58f",
    ),
    "full-history-landing": SourceSpec(
        artifact="m2-public-history-oldest-5-full-candles-20260814.json",
        schema="phase2-public-history-campaign.schema.json",
        contract_key="evidence_schema",
        contract="grid.phase2-public-history-campaign/v1",
        status="verified-public-landing-campaign",
        artifact_sha256="c5deda196b79d028f0f9c14325576c2fe90412a171020be89d74dab281862f57",
    ),
    "full-history-preflight-performance": SourceSpec(
        artifact="m2-history-campaign-preflight-performance-5xfull-20260813.json",
        schema="phase2-history-campaign-preflight-performance.schema.json",
        contract_key="evidence_schema",
        contract="grid.phase2-history-campaign-preflight-performance/v1",
        status="qualified-full-history-campaign-preflight-performance",
        artifact_sha256="579c0906fec9fbf9906db5a8b9cad6c55ee8818ea64d33a4830440eee4eb1047",
    ),
    "incremental-catalog-performance": SourceSpec(
        artifact="m2-incremental-catalog-selection-performance-20260814.json",
        schema="phase2-incremental-catalog-selection-performance.schema.json",
        contract_key="evidence_schema",
        contract="grid.phase2-incremental-catalog-selection-performance/v1",
        status="measured-incremental-catalog-selection",
        artifact_sha256="5987c967f049342e54c5f81c3546bc9232e94c500c370a3376b764c3fadfa7a7",
    ),
    "instrument-timeline-current-policy": SourceSpec(
        artifact="m2-instrument-timeline-current-policy-20260813.json",
        schema="instrument-timeline-summary.schema.json",
        contract_key="evidence_schema",
        contract="grid.instrument-timeline-summary/v1",
        status="blocked",
        artifact_sha256="df349a854a1453e762dde3c11a18641904dc3f525f0dfd291c35974bf66bc5ee",
    ),
    "stale-output-fault-injection": SourceSpec(
        artifact="m2-stale-output-fault-injection-20260814.json",
        schema="phase2-stale-output-fault-injection.schema.json",
        contract_key="evidence_schema",
        contract="grid.phase2-stale-output-fault-injection/v1",
        status="verified-stale-output-fault-injection",
        artifact_sha256="8cec6fac0cbd1e14eb2bbcc53b4fe9af5d8a07cd6b434f7a31a38b4428688c10",
    ),
    "trade-compaction-50x90": SourceSpec(
        artifact="m2-trade-april-50x90-compaction-20260813.json",
        schema="canonical-1m-compaction.schema.json",
        contract_key="contract",
        contract="grid.canonical-1m-compaction/v1",
        status="passed",
        artifact_sha256="c584fb9595d1bef05c96b84f65a2e2edb4070e1d986a0f77bf614a4a21bb1e8a",
    ),
}


def _verify_cross_bindings(sources: Mapping[str, dict[str, Any]]) -> None:
    landing = sources["full-history-landing"]
    canonical = sources["full-history-canonical-publication"]
    coverage = sources["full-history-coverage-audit"]
    boundary = sources["full-history-boundary-diagnostic"]
    announcement = sources["announcement-archive-depth"]
    preflight = sources["full-history-preflight-performance"]
    timeline = sources["instrument-timeline-current-policy"]

    landing_bindings = landing["bindings"]
    canonical_bindings = canonical["bindings"]
    coverage_bindings = coverage["bindings"]
    boundary_bindings = boundary["bindings"]
    for key in ("capacity_evidence_sha256", "instrument_registry_sha256"):
        _require(
            landing_bindings[key]
            == canonical_bindings[key]
            == coverage_bindings[key]
            == preflight["bindings"][key],
            f"full-history cross-source binding mismatch: {key}",
        )
    _require(
        landing_bindings["campaign_manifest_sha256"]
        == canonical_bindings["source_campaign_manifest_sha256"]
        == coverage_bindings["source_campaign_manifest_sha256"]
        == boundary_bindings["source_campaign_manifest_sha256"],
        "full-history campaign manifest binding mismatch",
    )
    _require(
        landing_bindings["campaign_plan_sha256"]
        == canonical_bindings["source_campaign_plan_sha256"]
        == coverage_bindings["source_campaign_plan_sha256"]
        == boundary_bindings["source_campaign_plan_sha256"],
        "full-history campaign plan binding mismatch",
    )
    for key in ("publication_manifest_sha256", "publication_plan_sha256"):
        _require(
            canonical_bindings[key] == coverage_bindings[key] == boundary_bindings[key],
            f"full-history publication binding mismatch: {key}",
        )
    coverage_spec = SOURCE_SPECS["full-history-coverage-audit"]
    _require(
        boundary_bindings["campaign_coverage_artifact_sha256"] == coverage_spec.artifact_sha256,
        "boundary diagnostic coverage artifact binding mismatch",
    )
    _require(
        boundary_bindings["campaign_coverage_content_sha256"] == coverage["content_sha256"],
        "boundary diagnostic coverage content binding mismatch",
    )
    _require(landing["scope"] == canonical["scope"], "full-history scope mismatch")
    _require(
        canonical["canonical"]["dataset_count"] == coverage["inventory"]["dataset_count"]
        and canonical["canonical"]["row_count"] == coverage["inventory"]["row_count"],
        "full-history publication/audit inventory mismatch",
    )
    registry_sha256 = landing_bindings["instrument_registry_sha256"]
    _require(
        boundary_bindings["instrument_registry_sha256"] == registry_sha256
        and announcement["bindings"]["instrument_registry_artifact_sha256"] == registry_sha256
        and timeline["timeline"]["registry_artifact_sha256s"][-1] == registry_sha256,
        "lifecycle evidence registry binding mismatch",
    )
    _require(
        announcement["scope"]["selected_instrument_count"] == landing["scope"]["symbol_count"],
        "announcement/full-history selected scope mismatch",
    )


def _verify_expected_observations(sources: Mapping[str, dict[str, Any]]) -> None:
    landing = sources["full-history-landing"]
    canonical = sources["full-history-canonical-publication"]
    coverage = sources["full-history-coverage-audit"]
    boundary = sources["full-history-boundary-diagnostic"]
    announcement = sources["announcement-archive-depth"]
    controlled = sources["coverage-audit-100x31"]
    timeline = sources["instrument-timeline-current-policy"]
    integrity = sources["canonical-integrity-fault-injection"]
    incremental = sources["incremental-catalog-performance"]
    preflight = sources["full-history-preflight-performance"]
    stale = sources["stale-output-fault-injection"]
    compaction = sources["trade-compaction-50x90"]

    _require(
        landing["process"]["deterministic_resume_supported"] is True
        and landing["landing"]["job_count"] == 978
        and landing["landing"]["row_count"] == 30_832_408,
        "completed full-history Landing observations changed",
    )
    _require(
        canonical["process"]["deterministic_resume_supported"] is True
        and canonical["canonical"]["dataset_count"] == 978
        and canonical["canonical"]["row_count"] == 30_832_334
        and canonical["canonical"]["admission"]["excluded_row_count"] == 74,
        "full-history canonical observations changed",
    )
    candle = coverage["quality"]["candle"]
    _require(
        candle["duplicate_key_count"] == 0
        and candle["conflicting_key_count"] == 0
        and candle["unexpected_timestamp_count"] == 0
        and candle["unrequested_row_count"] == 0
        and candle["lifecycle_failure_count"] == 0
        and candle["missing_minute_count"] == 11_981_746,
        "full-history candle audit observations changed",
    )
    _require(
        coverage["reason_policy"]["observed_reason_counts"]
        == {
            "canonical_representation_overflow": 74,
            "quarantined_source_row": 1,
            "rest_returned_no_data": 11_981_671,
        }
        and coverage["reason_policy"]["accepted_reason_codes"] == [],
        "full-history missing-minute reason policy changed",
    )
    _require(
        boundary["result"]["coverage_reconciled"] is True
        and boundary["result"]["leading_missing_minute_count"] == 11_981_670
        and boundary["result"]["internal_missing_minute_count"] == 76
        and boundary["result"]["trailing_missing_minute_count"] == 0,
        "candle boundary topology changed",
    )
    _require(
        announcement["archive_depth"]["all_selected_registry_launches_within_new_listing_archive"]
        is False
        and announcement["archive_depth"]["selected_launch_before_new_listing_archive_count"] == 5,
        "official announcement archive-depth blocker changed",
    )
    _require(
        controlled["quality"]["candle"]["duplicate_key_count"] == 0
        and controlled["quality"]["candle"]["conflicting_key_count"] == 0
        and controlled["quality"]["funding"]["duplicate_key_count"] == 0
        and controlled["quality"]["funding"]["interval_change_count"] == 7
        and controlled["reason_policy"]["unaccepted_reason_codes"]
        == ["unexplained_interval_change"],
        "controlled funding observations changed",
    )
    _require(
        timeline["blocker_codes"] == ["partial_source_inventory"]
        and timeline["timeline"]["snapshot_count"] == 3
        and timeline["universe"]["partial_snapshot_count"] == 2,
        "instrument-timeline limitation changed",
    )
    _require(
        integrity["measurement"]
        == {"case_count": 6, "detected_count": 6, "filesystem_state_preserved_count": 6},
        "canonical integrity fault-injection observations changed",
    )
    _require(
        incremental["correctness"]["deterministic_repeat_equal"] is True
        and incremental["correctness"]["store_fingerprint_equal_before_after"] is True
        and incremental["configuration"]["total_row_count"] == 368_640,
        "incremental catalog performance observations changed",
    )
    _require(
        preflight["qualified"]["preflight_elapsed_ms"] == 3_284
        and preflight["comparison"]["speedup_milli"] == 38_246
        and preflight["comparison"]["same_reference_host_identity_verified"] is True,
        "full-history preflight performance observations changed",
    )
    _require(
        stale["measurement"]
        == {
            "case_count": 5,
            "detected_count": 5,
            "marker_preserved_count": 5,
            "target_mutation_count": 0,
        },
        "stale-output measurement changed",
    )
    _require(
        compaction["compaction"]["logical_table_equal"] is True
        and compaction["compaction"]["duplicate_key_count"] == 0
        and compaction["compaction"]["conflicting_key_count"] == 0
        and compaction["lineage"]["parent_datasets_mutated"] is False,
        "compaction immutability observations changed",
    )


def _criteria_assessment() -> list[dict[str, object]]:
    return [
        {
            "blocker_codes": [
                "genuine-candle-gap-repair-evidence-missing",
                "measured-funding-repair-evidence-missing",
            ],
            "criterion_id": "deterministic-rerun-and-repair",
            "criterion_text": "deterministic re-run and repair",
            "evidence_roles": [
                "full-history-landing",
                "full-history-canonical-publication",
                "canonical-integrity-fault-injection",
            ],
            "readiness": "blocked",
        },
        {
            "blocker_codes": [],
            "criterion_id": "preflight-before-mutation",
            "criterion_text": "no mutation before preflight succeeds",
            "evidence_roles": [
                "full-history-preflight-performance",
                "full-history-canonical-publication",
                "stale-output-fault-injection",
                "trade-compaction-50x90",
            ],
            "readiness": "evidence-ready",
        },
        {
            "blocker_codes": [],
            "criterion_id": "no-duplicate-or-conflicting-keys",
            "criterion_text": "no duplicate/conflicting canonical keys",
            "evidence_roles": [
                "full-history-coverage-audit",
                "coverage-audit-100x31",
                "trade-compaction-50x90",
                "canonical-integrity-fault-injection",
            ],
            "readiness": "evidence-ready",
        },
        {
            "blocker_codes": [],
            "criterion_id": "stale-building-output-detected",
            "criterion_text": "stale building outputs detected",
            "evidence_roles": ["stale-output-fault-injection"],
            "readiness": "evidence-ready",
        },
        {
            "blocker_codes": [
                "funding-cadence-policy-unresolved",
                "historical-point-in-time-metadata-missing",
                "official-announcement-history-insufficient",
                "unaccepted-candle-absence-reasons",
            ],
            "criterion_id": "lifecycle-explains-expected-coverage",
            "criterion_text": "expected coverage explained by listing/delisting metadata",
            "evidence_roles": [
                "full-history-coverage-audit",
                "full-history-boundary-diagnostic",
                "announcement-archive-depth",
                "coverage-audit-100x31",
                "instrument-timeline-current-policy",
            ],
            "readiness": "blocked",
        },
        {
            "blocker_codes": ["full-history-end-to-end-performance-envelope-unqualified"],
            "criterion_id": "performance-within-envelope",
            "criterion_text": "performance remains within measured envelope",
            "evidence_roles": [
                "full-history-landing",
                "full-history-canonical-publication",
                "full-history-boundary-diagnostic",
                "full-history-preflight-performance",
                "incremental-catalog-performance",
            ],
            "readiness": "blocked",
        },
    ]


def build_gate2_readiness_pack_v2(
    *,
    implementation_identity: str,
    generated_at_utc: str,
    repo_root: Path = ROOT,
    criteria_path: Path | None = None,
    source_paths: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    """Verify current public evidence and return the non-promoting v2 projection."""

    _require(
        implementation_identity.startswith("git:")
        and len(implementation_identity) == 44
        and all(character in "0123456789abcdef" for character in implementation_identity[4:]),
        "implementation identity must be git:<40-character-lowercase-commit-sha>",
    )
    _verify_generated_at(generated_at_utc)
    repo_root = repo_root.resolve()
    criteria_source = _verify_criteria_source(
        criteria_path or repo_root / "docs" / "14_ROADMAP_AND_GATES.md"
    )
    overrides = dict(source_paths or {})
    _require(not (set(overrides) - set(SOURCE_SPECS)), "unknown Gate 2 source role supplied")
    payloads: dict[str, dict[str, Any]] = {}
    source_records: dict[str, dict[str, str]] = {}
    for role, spec in SOURCE_SPECS.items():
        path = overrides.get(role, repo_root / "benchmarks" / "results" / spec.artifact)
        payloads[role], source_records[role] = _verify_source(path, spec, repo_root)
    _verify_cross_bindings(payloads)
    _verify_expected_observations(payloads)

    criteria = _criteria_assessment()
    _require(
        [(item["criterion_id"], item["criterion_text"]) for item in criteria] == list(CRITERIA),
        "Gate 2 criteria assessment changed",
    )
    blocker_code_set: set[str] = set()
    for criterion in criteria:
        criterion_blockers = criterion["blocker_codes"]
        if not isinstance(criterion_blockers, list):
            raise Gate2ReadinessError("criterion blockers must be a list")
        blocker_code_set.update(str(code) for code in criterion_blockers)
    blocker_codes = sorted(blocker_code_set)
    evidence_ready_count = sum(item["readiness"] == "evidence-ready" for item in criteria)
    landing = payloads["full-history-landing"]
    canonical = payloads["full-history-canonical-publication"]
    coverage = payloads["full-history-coverage-audit"]
    boundary = payloads["full-history-boundary-diagnostic"]
    announcement = payloads["announcement-archive-depth"]
    controlled = payloads["coverage-audit-100x31"]
    timeline = payloads["instrument-timeline-current-policy"]
    integrity = payloads["canonical-integrity-fault-injection"]
    incremental = payloads["incremental-catalog-performance"]
    preflight = payloads["full-history-preflight-performance"]
    stale = payloads["stale-output-fault-injection"]
    compaction = payloads["trade-compaction-50x90"]

    payload: dict[str, Any] = {
        "assurances": {
            "all_source_content_hashes_verified": True,
            "all_source_receipts_verified": True,
            "all_source_schemas_verified": True,
            "automatic_gate_acceptance_performed": False,
            "criteria_source_hash_verified": True,
            "cross_source_bindings_verified": True,
            "network_request_performed": False,
            "phase3_authorized": False,
            "private_or_live_capability_used": False,
        },
        "bindings": {"implementation_identity": implementation_identity},
        "criteria": criteria,
        "criteria_source": criteria_source,
        "evidence_schema": EVIDENCE_CONTRACT,
        "gate_2": {
            "automatic_phase3_authorization": False,
            "blocker_codes": blocker_codes,
            "data_quality_owner_decision_required": True,
            "readiness": "blocked-pending-evidence-and-policy",
            "status": "closed-pending-data-quality-owner",
        },
        "generated_at_utc": generated_at_utc,
        "observations": {
            "candle_gap_topology": {
                "accepted_reason_count": len(boundary["reason_policy"]["accepted_reason_codes"]),
                "internal_missing_minute_count": boundary["result"][
                    "internal_missing_minute_count"
                ],
                "leading_missing_minute_count": boundary["result"]["leading_missing_minute_count"],
                "trailing_missing_minute_count": boundary["result"][
                    "trailing_missing_minute_count"
                ],
            },
            "canonical_integrity": integrity["measurement"],
            "compaction_50x90": {
                "conflicting_key_count": compaction["compaction"]["conflicting_key_count"],
                "duplicate_key_count": compaction["compaction"]["duplicate_key_count"],
                "logical_table_equal": compaction["compaction"]["logical_table_equal"],
                "parent_datasets_mutated": compaction["lineage"]["parent_datasets_mutated"],
                "row_count": compaction["compaction"]["row_count"],
            },
            "controlled_100x31": {
                "funding_duplicate_key_count": controlled["quality"]["funding"][
                    "duplicate_key_count"
                ],
                "funding_unexplained_interval_change_count": controlled["quality"]["funding"][
                    "interval_change_count"
                ],
                "row_count": controlled["inventory"]["row_count"],
            },
            "full_history_candle_campaign": {
                "campaign_elapsed_ms": landing["timing"]["campaign_elapsed_ms"],
                "canonical_dataset_count": canonical["canonical"]["dataset_count"],
                "canonical_representation_excluded_row_count": canonical["canonical"]["admission"][
                    "excluded_row_count"
                ],
                "canonical_row_count": canonical["canonical"]["row_count"],
                "canonical_verification_elapsed_ms": canonical["verification"][
                    "completed_publication_verification_elapsed_ms"
                ],
                "conflicting_key_count": coverage["quality"]["candle"]["conflicting_key_count"],
                "duplicate_key_count": coverage["quality"]["candle"]["duplicate_key_count"],
                "job_count": landing["landing"]["job_count"],
                "landing_row_count": landing["landing"]["row_count"],
                "missing_minute_count": coverage["quality"]["candle"]["missing_minute_count"],
                "month_count": landing["scope"]["month_count"],
                "quarantined_source_row_count": landing["source_quality"]["quarantined_row_count"],
                "symbol_count": landing["scope"]["symbol_count"],
            },
            "instrument_timeline": {
                "historical_point_in_time_metadata_complete": False,
                "partial_snapshot_count": timeline["universe"]["partial_snapshot_count"],
                "snapshot_count": timeline["timeline"]["snapshot_count"],
            },
            "official_announcement_archive": {
                "all_selected_registry_launches_within_new_listing_archive": announcement[
                    "archive_depth"
                ]["all_selected_registry_launches_within_new_listing_archive"],
                "selected_launch_before_new_listing_archive_count": announcement["archive_depth"][
                    "selected_launch_before_new_listing_archive_count"
                ],
            },
            "performance": {
                "incremental_first_rows_per_second": incremental["measurement"][
                    "first_selection_rows_per_second"
                ],
                "incremental_repeat_rows_per_second": incremental["measurement"][
                    "repeat_selection_rows_per_second"
                ],
                "preflight_elapsed_ms": preflight["qualified"]["preflight_elapsed_ms"],
                "preflight_speedup_milli": preflight["comparison"]["speedup_milli"],
            },
            "stale_output": stale["measurement"],
        },
        "readiness_counts": {
            "blocked_criterion_count": len(criteria) - evidence_ready_count,
            "criterion_count": len(criteria),
            "evidence_ready_criterion_count": evidence_ready_count,
        },
        "sources": source_records,
        "status": "blocked-pending-gate2-evidence-and-policy",
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_instrument_identities": False,
            "evidence_contains_market_values": False,
            "evidence_contains_runtime_paths": False,
            "runtime_market_artifacts_committed_to_git": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    schema_path = repo_root / "schemas" / "evidence" / "v2" / "gate2-readiness-pack.schema.json"
    try:
        Draft202012Validator(
            _load_json(schema_path),
            format_checker=FormatChecker(),
        ).validate(payload)
    except Exception as error:
        raise Gate2ReadinessError("Gate 2 readiness pack v2 does not match its schema") from error
    return payload


def publish_gate2_readiness_pack_v2(
    *,
    implementation_identity: str,
    output: Path,
    repo_root: Path = ROOT,
    force: bool = False,
) -> dict[str, Any]:
    """Build and atomically publish the current non-promoting v2 pack."""

    output, _receipt = preflight_evidence(output, force=force)
    payload = build_gate2_readiness_pack_v2(
        implementation_identity=implementation_identity,
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        repo_root=repo_root,
    )
    publish_evidence(output, payload, force=force)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation-identity", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    payload = publish_gate2_readiness_pack_v2(
        implementation_identity=args.implementation_identity,
        output=args.output,
        repo_root=args.repo_root,
    )
    print(
        json.dumps(
            {
                "blocker_count": len(payload["gate_2"]["blocker_codes"]),
                "evidence_ready_criterion_count": payload["readiness_counts"][
                    "evidence_ready_criterion_count"
                ],
                "status": payload["status"],
            }
        )
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
