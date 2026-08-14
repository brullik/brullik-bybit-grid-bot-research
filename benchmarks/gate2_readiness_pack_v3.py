"""Build the append-only Gate 2 readiness pack from the latest public evidence."""

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
    _verify_generated_at,
    _verify_source,
)
from benchmarks.gate2_readiness_pack_v2 import (
    SOURCE_SPECS as V2_SOURCE_SPECS,
)
from benchmarks.gate2_readiness_pack_v2 import (
    build_gate2_readiness_pack_v2,
)

EVIDENCE_CONTRACT: Final = "grid.gate2-readiness-pack/v3"

NEW_SOURCE_SPECS: Final[dict[str, SourceSpec]] = {
    "candle-gap-repair-execution": SourceSpec(
        artifact="m2-candle-gap-repair-execution-20260814.json",
        schema="bybit-1m-gap-repair-execution-public.schema.json",
        contract_key="contract",
        contract="grid.bybit-1m-gap-repair-execution-public/v1",
        status="blocked",
        artifact_sha256="f7d3efd6bab544c02ab63171040d99c364c94531c7e9fc08f31776f820d42cd5",
    ),
    "funding-repair-candidate-audit": SourceSpec(
        artifact="m2-funding-repair-candidate-audit-20260814.json",
        schema="phase2-funding-repair-candidate-audit.schema.json",
        contract_key="evidence_schema",
        contract="grid.phase2-funding-repair-candidate-audit/v1",
        status="verified-no-eligible-funding-repair-candidates",
        artifact_sha256="c14bee09eb5da94cf06b55c80f48c242e4eef9762c295f414cca3dc621740584",
    ),
    "full-history-catalog": SourceSpec(
        artifact="m2-full-history-catalog-20260814.json",
        schema="phase2-full-history-catalog.schema.json",
        contract_key="evidence_schema",
        contract="grid.phase2-full-history-catalog/v1",
        status="verified-full-history-catalog-selection",
        artifact_sha256="c36612505d1b07f50ae6092efe4a158129ced9f25832e2f9a757924a514366d0",
    ),
}

SOURCE_SPECS: Final[dict[str, SourceSpec]] = {**V2_SOURCE_SPECS, **NEW_SOURCE_SPECS}


def _verify_new_cross_bindings(
    base: Mapping[str, Any],
    new_sources: Mapping[str, dict[str, Any]],
    repo_root: Path,
    source_paths: Mapping[str, Path],
) -> None:
    landing_record = base["sources"]["full-history-landing"]
    landing = _load_json(
        source_paths.get(
            "full-history-landing",
            repo_root / "benchmarks" / "results" / landing_record["artifact"],
        )
    )
    canonical_record = base["sources"]["full-history-canonical-publication"]
    canonical = _load_json(
        source_paths.get(
            "full-history-canonical-publication",
            repo_root / "benchmarks" / "results" / canonical_record["artifact"],
        )
    )
    repair = new_sources["candle-gap-repair-execution"]
    funding = new_sources["funding-repair-candidate-audit"]
    catalog = new_sources["full-history-catalog"]

    _require(
        repair["bindings"]["capacity_evidence_sha256"]
        == funding["bindings"]["capacity_evidence_sha256"]
        == landing["bindings"]["capacity_evidence_sha256"],
        "new repair evidence capacity binding mismatch",
    )
    _require(
        repair["bindings"]["instrument_registry_sha256"]
        == landing["bindings"]["instrument_registry_sha256"],
        "candle repair registry binding mismatch",
    )
    _require(
        catalog["inventory"]["dataset_count"] == canonical["canonical"]["dataset_count"]
        and catalog["inventory"]["object_count"] == canonical["canonical"]["file_count"]
        and catalog["inventory"]["row_count"] == canonical["canonical"]["row_count"]
        and catalog["inventory"]["size_bytes"] == canonical["canonical"]["parquet_bytes"],
        "full-history catalog/publication inventory mismatch",
    )
    canonical_by_kind = {
        item["kind"]: (item["dataset_count"], item["row_count"], item["parquet_bytes"])
        for item in canonical["canonical"]["by_kind"]
    }
    catalog_by_kind = {
        item["kind"]: (item["dataset_count"], item["row_count"], item["size_bytes"])
        for item in catalog["inventory"]["by_kind"]
    }
    _require(catalog_by_kind == canonical_by_kind, "full-history catalog kind inventory mismatch")


def _verify_new_observations(new_sources: Mapping[str, dict[str, Any]]) -> None:
    repair = new_sources["candle-gap-repair-execution"]
    funding = new_sources["funding-repair-candidate-audit"]
    catalog = new_sources["full-history-catalog"]

    _require(
        repair["limits"]
        == {
            "actual_http_requests": 1,
            "missing_minute_count": 1,
            "observed_row_count": 0,
            "planned_max_http_requests": 3,
            "task_count": 1,
            "total_missing_minutes": 1,
        }
        and repair["outcome"]
        == {
            "classification": "source-gap-remains",
            "parent_dataset_mutated": False,
            "replacement_dataset_published": False,
            "replacement_eligible": False,
        },
        "candle repair outcome changed",
    )
    _require(
        funding["assurances"]["candidate_requests_executed"] is False
        and funding["classification_counts"]
        == {"eligible": 0, "non-isolated-or-non-integer-chronology": 4}
        and funding["inventory"]
        == {
            "audit_count": 4,
            "candidate_settlement_count": 0,
            "interval_change_count": 11,
            "planned_max_http_requests": 0,
            "task_count": 0,
        },
        "funding repair candidate observations changed",
    )
    _require(
        catalog["catalog"]["revision"] == 5
        and catalog["inventory"]["dataset_count"] == 978
        and catalog["inventory"]["object_count"] == 978
        and catalog["inventory"]["required_partition_count"] == 978
        and catalog["inventory"]["empty_dataset_count"] == 268
        and catalog["inventory"]["row_count"] == 30_832_334
        and catalog["inventory"]["size_bytes"] == 529_794_759
        and catalog["process"]["selection_union_matches_registration"] is True
        and len(catalog["topology"]) == 2,
        "full-history catalog observations changed",
    )


def _criteria_assessment() -> list[dict[str, object]]:
    return [
        {
            "blocker_codes": [
                "candle-repair-source-gap-remains",
                "eligible-funding-repair-candidate-unavailable",
            ],
            "criterion_id": "deterministic-rerun-and-repair",
            "criterion_text": "deterministic re-run and repair",
            "evidence_roles": [
                "full-history-landing",
                "full-history-canonical-publication",
                "canonical-integrity-fault-injection",
                "candle-gap-repair-execution",
                "funding-repair-candidate-audit",
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
                "full-history-catalog",
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
                "full-history-catalog",
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
                "candle-gap-repair-execution",
                "announcement-archive-depth",
                "coverage-audit-100x31",
                "funding-repair-candidate-audit",
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
                "full-history-catalog",
                "incremental-catalog-performance",
            ],
            "readiness": "blocked",
        },
    ]


def build_gate2_readiness_pack_v3(
    *,
    implementation_identity: str,
    generated_at_utc: str,
    repo_root: Path = ROOT,
    criteria_path: Path | None = None,
    source_paths: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    """Verify the latest public evidence and return the non-promoting v3 projection."""

    _verify_generated_at(generated_at_utc)
    repo_root = repo_root.resolve()
    overrides = dict(source_paths or {})
    _require(not (set(overrides) - set(SOURCE_SPECS)), "unknown Gate 2 source role supplied")
    base = build_gate2_readiness_pack_v2(
        implementation_identity=implementation_identity,
        generated_at_utc=generated_at_utc,
        repo_root=repo_root,
        criteria_path=criteria_path,
        source_paths={role: overrides[role] for role in V2_SOURCE_SPECS if role in overrides},
    )

    new_payloads: dict[str, dict[str, Any]] = {}
    new_records: dict[str, dict[str, str]] = {}
    for role, spec in NEW_SOURCE_SPECS.items():
        path = overrides.get(role, repo_root / "benchmarks" / "results" / spec.artifact)
        new_payloads[role], new_records[role] = _verify_source(path, spec, repo_root)
    _verify_new_cross_bindings(base, new_payloads, repo_root, overrides)
    _verify_new_observations(new_payloads)

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
    repair = new_payloads["candle-gap-repair-execution"]
    funding = new_payloads["funding-repair-candidate-audit"]
    catalog = new_payloads["full-history-catalog"]
    observations = dict(base["observations"])
    observations.update(
        {
            "candle_repair": {
                "actual_http_request_count": repair["limits"]["actual_http_requests"],
                "missing_minute_count": repair["limits"]["missing_minute_count"],
                "observed_row_count": repair["limits"]["observed_row_count"],
                "parent_dataset_mutated": repair["outcome"]["parent_dataset_mutated"],
                "replacement_dataset_published": repair["outcome"]["replacement_dataset_published"],
                "source_gap_remains": repair["outcome"]["classification"] == "source-gap-remains",
            },
            "funding_repair_candidates": {
                "audit_count": funding["inventory"]["audit_count"],
                "candidate_request_count": funding["inventory"]["planned_max_http_requests"],
                "candidate_requests_executed": funding["assurances"]["candidate_requests_executed"],
                "candidate_settlement_count": funding["inventory"]["candidate_settlement_count"],
                "eligible_audit_count": funding["classification_counts"]["eligible"],
                "interval_change_count": funding["inventory"]["interval_change_count"],
                "task_count": funding["inventory"]["task_count"],
            },
            "full_history_catalog": {
                "catalog_revision": catalog["catalog"]["revision"],
                "dataset_count": catalog["inventory"]["dataset_count"],
                "empty_dataset_count": catalog["inventory"]["empty_dataset_count"],
                "object_count": catalog["inventory"]["object_count"],
                "required_partition_count": catalog["inventory"]["required_partition_count"],
                "row_count": catalog["inventory"]["row_count"],
                "selection_union_matches_registration": catalog["process"][
                    "selection_union_matches_registration"
                ],
                "size_bytes": catalog["inventory"]["size_bytes"],
                "topology_segment_count": len(catalog["topology"]),
            },
        }
    )
    source_records = dict(base["sources"])
    source_records.update(new_records)
    payload: dict[str, Any] = {
        "assurances": base["assurances"],
        "bindings": {"implementation_identity": implementation_identity},
        "criteria": criteria,
        "criteria_source": base["criteria_source"],
        "evidence_schema": EVIDENCE_CONTRACT,
        "gate_2": {
            "automatic_phase3_authorization": False,
            "blocker_codes": blocker_codes,
            "data_quality_owner_decision_required": True,
            "readiness": "blocked-pending-evidence-and-policy",
            "status": "closed-pending-data-quality-owner",
        },
        "generated_at_utc": generated_at_utc,
        "observations": observations,
        "readiness_counts": {
            "blocked_criterion_count": len(criteria) - evidence_ready_count,
            "criterion_count": len(criteria),
            "evidence_ready_criterion_count": evidence_ready_count,
        },
        "sources": source_records,
        "status": "blocked-pending-gate2-evidence-and-policy",
        "storage_policy": base["storage_policy"],
    }
    payload["content_sha256"] = canonical_sha256(payload)
    schema_path = repo_root / "schemas" / "evidence" / "v3" / "gate2-readiness-pack.schema.json"
    try:
        Draft202012Validator(_load_json(schema_path), format_checker=FormatChecker()).validate(
            payload
        )
    except Exception as error:
        raise Gate2ReadinessError("Gate 2 readiness pack v3 does not match its schema") from error
    return payload


def publish_gate2_readiness_pack_v3(
    *,
    implementation_identity: str,
    output: Path,
    repo_root: Path = ROOT,
    force: bool = False,
) -> dict[str, Any]:
    """Build and atomically publish the latest non-promoting v3 pack."""

    output, _receipt = preflight_evidence(output, force=force)
    payload = build_gate2_readiness_pack_v3(
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
    payload = publish_gate2_readiness_pack_v3(
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
