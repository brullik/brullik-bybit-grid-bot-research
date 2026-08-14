"""Build a receipt-linked, non-promoting Gate 2 readiness pack."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_data.evidence import preflight_evidence, publish_evidence, verify_evidence
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

ROOT: Final = Path(__file__).resolve().parents[1]
EVIDENCE_CONTRACT: Final = "grid.gate2-readiness-pack/v1"
CRITERIA_SOURCE_SHA256: Final = "492458c7126bb6768dbc1b328ec5959095e67e0cdbf865b7de54b05ecc94f534"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")

CRITERIA: Final = (
    ("deterministic-rerun-and-repair", "deterministic re-run and repair"),
    ("preflight-before-mutation", "no mutation before preflight succeeds"),
    ("no-duplicate-or-conflicting-keys", "no duplicate/conflicting canonical keys"),
    ("stale-building-output-detected", "stale building outputs detected"),
    (
        "lifecycle-explains-expected-coverage",
        "expected coverage explained by listing/delisting metadata",
    ),
    ("performance-within-envelope", "performance remains within measured envelope"),
)


@dataclass(frozen=True, slots=True)
class SourceSpec:
    artifact: str
    schema: str
    contract_key: str
    contract: str
    status: str
    artifact_sha256: str


SOURCE_SPECS: Final[dict[str, SourceSpec]] = {
    "canonical-publication-100x31": SourceSpec(
        artifact="m2-canonical-history-campaign-100x31-20260813.json",
        schema="phase2-history-campaign-publication.schema.json",
        contract_key="evidence_schema",
        contract="grid.phase2-history-campaign-publication/v1",
        status="verified-canonical-history-campaign-publication",
        artifact_sha256="09f2c0b36b9b01ffb690e453d14dcd93b2ba78b7d28ddcb471a9d9f4c2a61eb6",
    ),
    "coverage-audit-100x31": SourceSpec(
        artifact="m2-history-campaign-coverage-audit-100x31-20260813.json",
        schema="history-campaign-coverage-audit.schema.json",
        contract_key="contract",
        contract="grid.history-campaign-coverage-audit/v1",
        status="blocked",
        artifact_sha256="6b9fab62147a78bedf2879cadfcd6031af5d6b1f6566e42e716b902b12236358",
    ),
    "landing-long-run-100x31": SourceSpec(
        artifact="m2-public-history-long-run-100x31-20260813.json",
        schema="phase2-public-history-campaign.schema.json",
        contract_key="evidence_schema",
        contract="grid.phase2-public-history-campaign/v1",
        status="verified-public-landing-campaign",
        artifact_sha256="9190278119673b2eb39ba467ab6a22fb128c51f977c0e337582c04aa87b5f4f9",
    ),
    "full-history-preflight-performance": SourceSpec(
        artifact="m2-history-campaign-preflight-performance-5xfull-20260813.json",
        schema="phase2-history-campaign-preflight-performance.schema.json",
        contract_key="evidence_schema",
        contract="grid.phase2-history-campaign-preflight-performance/v1",
        status="qualified-full-history-campaign-preflight-performance",
        artifact_sha256="579c0906fec9fbf9906db5a8b9cad6c55ee8818ea64d33a4830440eee4eb1047",
    ),
    "full-history-resume-performance": SourceSpec(
        artifact="m2-history-campaign-resume-performance-5xfull-20260814.json",
        schema="phase2-history-campaign-resume-performance.schema.json",
        contract_key="evidence_schema",
        contract="grid.phase2-history-campaign-resume-performance/v1",
        status="verified-post-merge-history-campaign-resume-performance",
        artifact_sha256="e21e26d04460598a497f833bc0b540798a8dcfdd954b73b9af10cdf33976ed07",
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


class Gate2ReadinessError(RuntimeError):
    """A source, binding, or unchanged Gate 2 criterion did not verify."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Gate2ReadinessError(f"source is not valid JSON: {path.name}") from error
    if not isinstance(payload, dict):
        raise Gate2ReadinessError(f"source is not a JSON object: {path.name}")
    return payload


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Gate2ReadinessError(message)


def _verify_generated_at(generated_at_utc: str) -> None:
    _require(generated_at_utc.endswith("Z"), "generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(generated_at_utc.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise Gate2ReadinessError("generated_at_utc is invalid") from error
    offset = parsed.utcoffset()
    _require(offset is not None and offset.total_seconds() == 0, "generated_at_utc must be UTC")


def _verify_criteria_source(criteria_path: Path) -> dict[str, object]:
    criteria_path = criteria_path.resolve()
    _require(
        sha256_file(criteria_path) == CRITERIA_SOURCE_SHA256,
        "Gate 2 criteria source hash changed; a reviewed successor contract is required",
    )
    text = criteria_path.read_text(encoding="utf-8")
    positions = [text.find(f"- {criterion_text};") for _, criterion_text in CRITERIA[:-1]]
    positions.append(text.find(f"- {CRITERIA[-1][1]}."))
    _require(all(position >= 0 for position in positions), "unchanged Gate 2 criteria not found")
    _require(positions == sorted(positions), "Gate 2 criterion order changed")
    return {
        "artifact": criteria_path.name,
        "artifact_sha256": CRITERIA_SOURCE_SHA256,
        "criteria_count": len(CRITERIA),
    }


def _verify_source(
    path: Path, spec: SourceSpec, repo_root: Path
) -> tuple[dict[str, Any], dict[str, str]]:
    path = path.resolve()
    _require(path.name == spec.artifact, f"unexpected artifact name for {spec.artifact}")
    _require(verify_evidence(path), f"source evidence receipt does not verify: {spec.artifact}")
    actual_sha256 = sha256_file(path)
    _require(
        actual_sha256 == spec.artifact_sha256, f"source artifact hash changed: {spec.artifact}"
    )
    payload = _load_json(path)
    schema_path = repo_root / "schemas" / "evidence" / "v1" / spec.schema
    try:
        Draft202012Validator(
            _load_json(schema_path),
            format_checker=FormatChecker(),
        ).validate(payload)
    except Exception as error:
        raise Gate2ReadinessError(f"source schema does not verify: {spec.artifact}") from error
    _require(
        payload.get(spec.contract_key) == spec.contract, f"source contract changed: {spec.artifact}"
    )
    _require(payload.get("status") == spec.status, f"source status changed: {spec.artifact}")
    hash_input = dict(payload)
    content_sha256 = hash_input.pop("content_sha256", None)
    _require(
        isinstance(content_sha256, str) and content_sha256 == canonical_sha256(hash_input),
        f"source content hash does not verify: {spec.artifact}",
    )
    return payload, {
        "artifact": spec.artifact,
        "artifact_sha256": actual_sha256,
        "content_sha256": content_sha256,
        "contract": spec.contract,
        "status": spec.status,
    }


def _verify_cross_bindings(sources: Mapping[str, dict[str, Any]]) -> None:
    canonical = sources["canonical-publication-100x31"]
    coverage = sources["coverage-audit-100x31"]
    landing = sources["landing-long-run-100x31"]
    canonical_bindings = canonical["bindings"]
    coverage_bindings = coverage["bindings"]
    landing_bindings = landing["bindings"]
    for key in ("capacity_evidence_sha256", "instrument_registry_sha256"):
        _require(
            canonical_bindings[key] == coverage_bindings[key] == landing_bindings[key],
            f"100x31 cross-source binding mismatch: {key}",
        )
    _require(
        canonical_bindings["source_campaign_manifest_sha256"]
        == coverage_bindings["source_campaign_manifest_sha256"]
        == landing_bindings["campaign_manifest_sha256"],
        "100x31 campaign manifest binding mismatch",
    )
    _require(
        canonical_bindings["source_campaign_plan_sha256"]
        == coverage_bindings["source_campaign_plan_sha256"]
        == landing_bindings["campaign_plan_sha256"],
        "100x31 campaign plan binding mismatch",
    )
    _require(
        canonical_bindings["publication_manifest_sha256"]
        == coverage_bindings["publication_manifest_sha256"],
        "100x31 publication manifest binding mismatch",
    )
    _require(canonical["scope"] == landing["scope"], "100x31 source/publication scope mismatch")
    _require(
        canonical["canonical"]["dataset_count"] == coverage["inventory"]["dataset_count"]
        and canonical["canonical"]["row_count"] == coverage["inventory"]["row_count"],
        "100x31 publication/audit inventory mismatch",
    )


def _verify_expected_observations(sources: Mapping[str, dict[str, Any]]) -> None:
    coverage = sources["coverage-audit-100x31"]
    candle = coverage["quality"]["candle"]
    funding = coverage["quality"]["funding"]
    _require(
        candle["duplicate_key_count"] == 0
        and candle["conflicting_key_count"] == 0
        and candle["missing_minute_count"] == 0
        and candle["gap_range_count"] == 0,
        "controlled candle quality observations changed",
    )
    _require(
        funding["duplicate_key_count"] == 0
        and funding["interval_change_count"] == 7
        and coverage["reason_policy"]["unaccepted_reason_codes"] == ["unexplained_interval_change"],
        "controlled funding quality observations changed",
    )
    resume = sources["full-history-resume-performance"]
    _require(
        resume["measurement"]["completed_jobs_reused"] == 927
        and resume["measurement"]["pending_job_count"] == 51
        and resume["measurement"]["pending_page_count"] == 2_271,
        "full-history pending inventory changed",
    )
    _require(
        resume["assurances"]["network_request_performed"] is False
        and resume["assurances"]["first_pending_failure_fail_closed"] is True,
        "full-history resume safety assurances changed",
    )
    timeline = sources["instrument-timeline-current-policy"]
    _require(
        timeline["blocker_codes"] == ["partial_source_inventory"]
        and timeline["timeline"]["snapshot_count"] == 3
        and timeline["universe"]["partial_snapshot_count"] == 2,
        "instrument-timeline limitation changed",
    )
    stale = sources["stale-output-fault-injection"]
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
    compaction = sources["trade-compaction-50x90"]
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
                "full-history-campaign-incomplete",
                "genuine-candle-gap-repair-evidence-missing",
                "measured-funding-repair-evidence-missing",
            ],
            "criterion_id": "deterministic-rerun-and-repair",
            "criterion_text": "deterministic re-run and repair",
            "evidence_roles": [
                "canonical-publication-100x31",
                "full-history-resume-performance",
            ],
            "readiness": "blocked",
        },
        {
            "blocker_codes": [],
            "criterion_id": "preflight-before-mutation",
            "criterion_text": "no mutation before preflight succeeds",
            "evidence_roles": [
                "canonical-publication-100x31",
                "stale-output-fault-injection",
                "trade-compaction-50x90",
            ],
            "readiness": "evidence-ready",
        },
        {
            "blocker_codes": ["full-history-canonical-publication-and-audit-missing"],
            "criterion_id": "no-duplicate-or-conflicting-keys",
            "criterion_text": "no duplicate/conflicting canonical keys",
            "evidence_roles": ["coverage-audit-100x31", "trade-compaction-50x90"],
            "readiness": "blocked",
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
                "full-history-canonical-publication-and-audit-missing",
            ],
            "criterion_id": "lifecycle-explains-expected-coverage",
            "criterion_text": "expected coverage explained by listing/delisting metadata",
            "evidence_roles": [
                "coverage-audit-100x31",
                "instrument-timeline-current-policy",
            ],
            "readiness": "blocked",
        },
        {
            "blocker_codes": [
                "full-history-campaign-incomplete",
                "full-history-end-to-end-performance-missing",
            ],
            "criterion_id": "performance-within-envelope",
            "criterion_text": "performance remains within measured envelope",
            "evidence_roles": [
                "landing-long-run-100x31",
                "full-history-preflight-performance",
                "full-history-resume-performance",
            ],
            "readiness": "blocked",
        },
    ]


def build_gate2_readiness_pack(
    *,
    implementation_identity: str,
    generated_at_utc: str,
    repo_root: Path = ROOT,
    criteria_path: Path | None = None,
    source_paths: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    """Verify current public Gate 2 evidence and return a non-promoting readiness projection."""

    _require(
        SOFTWARE_IDENTITY_RE.fullmatch(implementation_identity) is not None,
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
    blocker_code_set: set[str] = set()
    for criterion in criteria:
        criterion_blockers = criterion["blocker_codes"]
        if not isinstance(criterion_blockers, list):
            raise Gate2ReadinessError("criterion blockers must be a list")
        blocker_code_set.update(str(code) for code in criterion_blockers)
    blocker_codes = sorted(blocker_code_set)
    evidence_ready_count = sum(item["readiness"] == "evidence-ready" for item in criteria)
    coverage = payloads["coverage-audit-100x31"]
    resume = payloads["full-history-resume-performance"]
    timeline = payloads["instrument-timeline-current-policy"]
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
            "readiness": "blocked-by-missing-evidence",
            "status": "closed-pending-data-quality-owner",
        },
        "generated_at_utc": generated_at_utc,
        "observations": {
            "compaction_50x90": {
                "conflicting_key_count": compaction["compaction"]["conflicting_key_count"],
                "duplicate_key_count": compaction["compaction"]["duplicate_key_count"],
                "logical_table_equal": compaction["compaction"]["logical_table_equal"],
                "parent_datasets_mutated": compaction["lineage"]["parent_datasets_mutated"],
                "row_count": compaction["compaction"]["row_count"],
            },
            "controlled_100x31": {
                "blocked_dataset_count": coverage["inventory"]["blocked_count"],
                "candle_conflicting_key_count": coverage["quality"]["candle"][
                    "conflicting_key_count"
                ],
                "candle_duplicate_key_count": coverage["quality"]["candle"]["duplicate_key_count"],
                "candle_missing_minute_count": coverage["quality"]["candle"][
                    "missing_minute_count"
                ],
                "funding_duplicate_key_count": coverage["quality"]["funding"][
                    "duplicate_key_count"
                ],
                "funding_unexplained_interval_change_count": coverage["quality"]["funding"][
                    "interval_change_count"
                ],
                "row_count": coverage["inventory"]["row_count"],
            },
            "full_history_candle_campaign": {
                "completed_job_count": resume["measurement"]["completed_jobs_reused"],
                "job_count": resume["measurement"]["job_count"],
                "month_count": resume["scope"]["month_count"],
                "pending_job_count": resume["measurement"]["pending_job_count"],
                "pending_page_count": resume["measurement"]["pending_page_count"],
                "symbol_count": resume["scope"]["symbol_count"],
            },
            "instrument_timeline": {
                "historical_point_in_time_metadata_complete": False,
                "partial_snapshot_count": timeline["universe"]["partial_snapshot_count"],
                "snapshot_count": timeline["timeline"]["snapshot_count"],
            },
            "stale_output": stale["measurement"],
        },
        "readiness_counts": {
            "blocked_criterion_count": len(criteria) - evidence_ready_count,
            "criterion_count": len(criteria),
            "evidence_ready_criterion_count": evidence_ready_count,
        },
        "sources": source_records,
        "status": "blocked-by-missing-gate2-evidence",
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_instrument_identities": False,
            "evidence_contains_market_values": False,
            "evidence_contains_runtime_paths": False,
            "runtime_market_artifacts_committed_to_git": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    schema_path = repo_root / "schemas" / "evidence" / "v1" / "gate2-readiness-pack.schema.json"
    try:
        Draft202012Validator(
            _load_json(schema_path),
            format_checker=FormatChecker(),
        ).validate(payload)
    except Exception as error:
        raise Gate2ReadinessError("Gate 2 readiness pack does not match its schema") from error
    return payload


def publish_gate2_readiness_pack(
    *,
    implementation_identity: str,
    output: Path,
    repo_root: Path = ROOT,
    force: bool = False,
) -> dict[str, Any]:
    """Build and atomically publish the current non-promoting Gate 2 readiness pack."""

    output, _receipt = preflight_evidence(output, force=force)
    payload = build_gate2_readiness_pack(
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
    payload = publish_gate2_readiness_pack(
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
