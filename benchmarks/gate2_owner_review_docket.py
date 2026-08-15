"""Build one non-promoting decision docket for every current Gate 2 blocker."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file
from grid_data.evidence import preflight_evidence, publish_evidence, verify_evidence
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

ROOT: Final = Path(__file__).parents[1]
EVIDENCE_CONTRACT: Final = "grid.gate2-owner-review-docket/v1"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
EXPECTED_V5_IMPLEMENTATION: Final = "git:06489b5e348cc482957994b5d002c5ea19c58a96"
EXPECTED_BLOCKERS: Final = [
    "candle-repair-source-gap-remains",
    "eligible-funding-repair-candidate-unavailable",
    "full-history-end-to-end-performance-envelope-unqualified",
    "funding-cadence-policy-unresolved",
    "historical-point-in-time-metadata-missing",
    "official-announcement-history-insufficient",
    "unaccepted-candle-absence-reasons",
]
EXPECTED_GATE: Final = {
    "automatic_phase3_authorization": False,
    "blocker_codes": EXPECTED_BLOCKERS,
    "data_quality_owner_decision_required": True,
    "readiness": "blocked-pending-evidence-and-policy",
    "status": "closed-pending-data-quality-owner",
}
EXPECTED_READINESS_COUNTS: Final = {
    "blocked_criterion_count": 3,
    "criterion_count": 6,
    "evidence_ready_criterion_count": 3,
}
EXPECTED_OWNER_REVIEW: Final = {
    "blocked_criterion_count": 3,
    "blocker_removal_performed": False,
    "funding_cadence_owner_disposition": "pending",
    "lifecycle_owner_disposition": "pending",
    "owner_decision_required": True,
    "performance_envelope_qualified": False,
    "unique_blocker_count": 7,
}
EXPECTED_CRITERIA: Final = (
    (
        "deterministic-rerun-and-repair",
        "deterministic re-run and repair",
        "blocked",
        (
            "candle-repair-source-gap-remains",
            "eligible-funding-repair-candidate-unavailable",
        ),
        (
            "full-history-landing",
            "full-history-canonical-publication",
            "canonical-integrity-fault-injection",
            "candle-gap-repair-execution",
            "funding-repair-candidate-audit",
        ),
    ),
    (
        "preflight-before-mutation",
        "no mutation before preflight succeeds",
        "evidence-ready",
        (),
        (
            "full-history-preflight-performance",
            "full-history-canonical-publication",
            "full-history-catalog",
            "stale-output-fault-injection",
            "trade-compaction-50x90",
        ),
    ),
    (
        "no-duplicate-or-conflicting-keys",
        "no duplicate/conflicting canonical keys",
        "evidence-ready",
        (),
        (
            "full-history-coverage-audit",
            "full-history-catalog",
            "coverage-audit-100x31",
            "trade-compaction-50x90",
            "canonical-integrity-fault-injection",
        ),
    ),
    (
        "stale-building-output-detected",
        "stale building outputs detected",
        "evidence-ready",
        (),
        ("stale-output-fault-injection",),
    ),
    (
        "lifecycle-explains-expected-coverage",
        "expected coverage explained by listing/delisting metadata",
        "blocked",
        (
            "funding-cadence-policy-unresolved",
            "historical-point-in-time-metadata-missing",
            "official-announcement-history-insufficient",
            "unaccepted-candle-absence-reasons",
        ),
        (
            "full-history-coverage-audit",
            "full-history-boundary-diagnostic",
            "candle-gap-repair-execution",
            "announcement-archive-depth",
            "coverage-audit-100x31",
            "funding-repair-candidate-audit",
            "instrument-timeline-current-policy",
        ),
    ),
    (
        "performance-within-envelope",
        "performance remains within measured envelope",
        "blocked",
        ("full-history-end-to-end-performance-envelope-unqualified",),
        (
            "full-history-landing",
            "full-history-canonical-publication",
            "full-history-boundary-diagnostic",
            "full-history-preflight-performance",
            "full-history-catalog",
            "incremental-catalog-performance",
        ),
    ),
)


class Gate2OwnerReviewDocketError(RuntimeError):
    """The Gate 2 owner-review docket failed closed."""


@dataclass(frozen=True, slots=True)
class SourceSpec:
    schema_relative: str
    contract: str
    status: str


V5_SPEC: Final = SourceSpec(
    schema_relative="schemas/evidence/v5/gate2-readiness-pack.schema.json",
    contract="grid.gate2-readiness-pack/v5",
    status="blocked-consolidated-evidence-awaiting-owner-decision",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Gate2OwnerReviewDocketError(message)


def _mapping(parent: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise Gate2OwnerReviewDocketError(f"evidence field must be an object: {key}")
    return cast(dict[str, Any], value)


def _array(parent: Mapping[str, Any], key: str) -> list[Any]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise Gate2OwnerReviewDocketError(f"evidence field must be an array: {key}")
    return value


def _integer(parent: Mapping[str, Any], key: str, *, minimum: int = 0) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise Gate2OwnerReviewDocketError(f"evidence integer is invalid: {key}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Gate2OwnerReviewDocketError(f"invalid JSON evidence: {path.name}") from error
    if not isinstance(value, dict):
        raise Gate2OwnerReviewDocketError(f"JSON evidence must be an object: {path.name}")
    return cast(dict[str, Any], value)


def _verify_generated_at(generated_at_utc: str) -> None:
    _require(generated_at_utc.endswith("Z"), "generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(generated_at_utc.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise Gate2OwnerReviewDocketError("generated_at_utc is invalid") from error
    offset = parsed.utcoffset()
    _require(offset is not None and offset.total_seconds() == 0, "generated_at_utc must be UTC")


def _verify_source(
    path: Path, spec: SourceSpec, repo_root: Path
) -> tuple[dict[str, Any], dict[str, str]]:
    _require(not path.is_symlink(), f"source artifact is a symlink: {path.name}")
    resolved = path.resolve()
    receipt = resolved.with_suffix(resolved.suffix + ".receipt.json")
    _require(
        resolved.is_file() and receipt.is_file() and not receipt.is_symlink(),
        f"source artifact/receipt pair is unsafe or missing: {path.name}",
    )
    _require(verify_evidence(resolved), f"source receipt does not verify: {path.name}")
    payload = _load_json(resolved)
    try:
        artifact_bytes = resolved.read_bytes()
    except OSError as error:
        raise Gate2OwnerReviewDocketError(f"cannot read source bytes: {path.name}") from error
    _require(
        artifact_bytes == canonical_json_bytes(payload) + b"\n",
        f"source is not canonical JSON plus LF: {path.name}",
    )
    schema = _load_json(repo_root / spec.schema_relative)
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    except Exception as error:
        raise Gate2OwnerReviewDocketError(f"source schema does not verify: {path.name}") from error
    _require(payload.get("evidence_schema") == spec.contract, "source contract differs")
    _require(payload.get("status") == spec.status, "source status differs")
    hash_input = dict(payload)
    embedded = hash_input.pop("content_sha256", None)
    _require(embedded == canonical_sha256(hash_input), "source content hash differs")
    return payload, {
        "artifact": resolved.name,
        "artifact_sha256": sha256_file(resolved),
        "content_sha256": cast(str, embedded),
        "contract": spec.contract,
        "status": spec.status,
    }


def _verify_v5(source: Mapping[str, Any]) -> None:
    _require(source.get("gate_2") == EXPECTED_GATE, "v5 Gate 2 decision changed")
    _require(
        source.get("readiness_counts") == EXPECTED_READINESS_COUNTS,
        "v5 readiness counts changed",
    )
    criteria = _array(source, "criteria")
    _require(len(criteria) == len(EXPECTED_CRITERIA), "v5 criteria count changed")
    for raw, (criterion_id, criterion_text, readiness, blockers, evidence_roles) in zip(
        criteria, EXPECTED_CRITERIA, strict=True
    ):
        _require(isinstance(raw, dict), "v5 criterion is not an object")
        criterion = cast(dict[str, Any], raw)
        _require(criterion.get("criterion_id") == criterion_id, "v5 criterion order changed")
        _require(
            criterion.get("criterion_text") == criterion_text,
            f"v5 criterion text changed: {criterion_id}",
        )
        _require(criterion.get("readiness") == readiness, f"v5 readiness changed: {criterion_id}")
        _require(
            criterion.get("blocker_codes") == list(blockers),
            f"v5 blocker assignment changed: {criterion_id}",
        )
        _require(
            criterion.get("evidence_roles") == list(evidence_roles),
            f"v5 evidence roles changed: {criterion_id}",
        )
    bindings = _mapping(source, "bindings")
    _require(
        bindings.get("implementation_identity") == EXPECTED_V5_IMPLEMENTATION,
        "v5 implementation identity changed",
    )
    owner_review = _mapping(_mapping(source, "observations"), "owner_review")
    _require(owner_review == EXPECTED_OWNER_REVIEW, "v5 owner-review state changed")


def _review_items(source: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    observations = _mapping(source, "observations")
    current = _mapping(observations, "current_universe")
    funding = _mapping(observations, "funding_cadence_policy")
    lifecycle = _mapping(observations, "official_lifecycle_coverage")
    return {
        "deterministic_repair": {
            "blocker_codes": EXPECTED_BLOCKERS[:2],
            "criterion_id": "deterministic-rerun-and-repair",
            "evidence_classification": "measured-negative-repair-evidence",
            "owner_decision_required": True,
            "owner_disposition": "pending",
        },
        "funding_cadence": {
            "blocker_codes": ["funding-cadence-policy-unresolved"],
            "criterion_id": "lifecycle-explains-expected-coverage",
            "evidence_classification": "verified-official-policy-consistency",
            "evidence_summary": {
                "affected_series_count": _integer(funding, "affected_series_count", minimum=1),
                "explained_interval_change_count": _integer(
                    funding, "explained_interval_change_count", minimum=1
                ),
                "unexplained_interval_change_count": _integer(
                    funding, "unexplained_interval_change_count"
                ),
            },
            "owner_decision_required": True,
            "owner_disposition": "pending",
        },
        "lifecycle_and_absence_policy": {
            "blocker_codes": EXPECTED_BLOCKERS[4:],
            "criterion_id": "lifecycle-explains-expected-coverage",
            "evidence_classification": "verified-partial-official-lifecycle-evidence",
            "evidence_summary": {
                "delisting_ambiguous_instrument_count": _integer(
                    lifecycle, "delisting_ambiguous_instrument_count"
                ),
                "delisting_unmatched_instrument_count": _integer(
                    lifecycle, "delisting_unmatched_instrument_count"
                ),
                "listing_ambiguous_instrument_count": _integer(
                    lifecycle, "listing_ambiguous_instrument_count"
                ),
                "listing_unmatched_instrument_count": _integer(
                    lifecycle, "listing_unmatched_instrument_count"
                ),
                "record_matching_complete": lifecycle.get("record_matching_complete") is True,
                "remaining_pre_archive_listing_instrument_count": _integer(
                    lifecycle, "remaining_pre_archive_listing_instrument_count"
                ),
                "selected_instrument_count": _integer(
                    lifecycle, "selected_instrument_count", minimum=1
                ),
            },
            "owner_decision_required": True,
            "owner_disposition": "pending",
        },
        "performance_envelope": {
            "blocker_codes": ["full-history-end-to-end-performance-envelope-unqualified"],
            "criterion_id": "performance-within-envelope",
            "evidence_classification": "measured-component-performance-unqualified-envelope",
            "evidence_summary": {
                "catalog_deterministic_repeat_equal": (
                    current.get("catalog_deterministic_repeat_equal") is True
                ),
                "catalog_first_pass_rows_per_second": _integer(
                    current, "catalog_first_pass_rows_per_second", minimum=1
                ),
                "catalog_repeat_pass_rows_per_second": _integer(
                    current, "catalog_repeat_pass_rows_per_second", minimum=1
                ),
                "end_to_end_envelope_qualified": False,
            },
            "owner_decision_required": True,
            "owner_disposition": "pending",
        },
    }


def _verify_blocker_assignment(review_items: Mapping[str, Mapping[str, Any]]) -> None:
    _require(len(review_items) == 4, "owner-review item count changed")
    assigned: list[str] = []
    for item in review_items.values():
        assigned.extend(cast(list[str], _array(item, "blocker_codes")))
        _require(item.get("owner_disposition") == "pending", "owner disposition is not pending")
    _require(len(assigned) == len(set(assigned)), "a Gate 2 blocker is assigned more than once")
    _require(sorted(assigned) == EXPECTED_BLOCKERS, "not every Gate 2 blocker is assigned")


def build_gate2_owner_review_docket(
    *,
    implementation_identity: str,
    generated_at_utc: str,
    prior_readiness_v5_path: Path,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Build one pending owner-review docket over the exact v5 readiness pack."""

    _require(
        SOFTWARE_IDENTITY_RE.fullmatch(implementation_identity) is not None,
        "implementation identity must be git:<40 lowercase hex>",
    )
    _verify_generated_at(generated_at_utc)
    root = repo_root.resolve()
    _require(root.is_dir() and not repo_root.is_symlink(), "repository root is unsafe")
    source, source_record = _verify_source(prior_readiness_v5_path, V5_SPEC, root)
    _verify_v5(source)
    review_items = _review_items(source)
    _verify_blocker_assignment(review_items)
    payload: dict[str, Any] = {
        "assurances": {
            "all_seven_blockers_assigned_once": True,
            "automatic_gate_acceptance_performed": False,
            "blocker_removal_performed": False,
            "gate_status_change_performed": False,
            "market_data_or_policy_network_request_performed": False,
            "owner_decision_recorded": False,
            "phase3_authorized": False,
            "private_or_live_capability_used": False,
            "source_content_hash_verified": True,
            "source_receipt_verified": True,
            "source_schema_verified": True,
        },
        "bindings": {
            "implementation_identity": implementation_identity,
            "prior_readiness_v5_artifact_sha256": source_record["artifact_sha256"],
            "prior_readiness_v5_content_sha256": source_record["content_sha256"],
        },
        "content_sha256": "",
        "criteria": source["criteria"],
        "criteria_source": source["criteria_source"],
        "decision_state": {
            "data_quality_owner_decision_recorded": False,
            "gate_opening_authorized": False,
            "owner_decision_required": True,
            "phase3_implementation_authorized": False,
            "required_review_item_count": 4,
            "status": "pending",
        },
        "evidence_schema": EVIDENCE_CONTRACT,
        "gate_2": EXPECTED_GATE,
        "generated_at_utc": generated_at_utc,
        "readiness_counts": EXPECTED_READINESS_COUNTS,
        "review_items": review_items,
        "source": source_record,
        "status": "pending-explicit-data-quality-owner-decision",
        "storage_policy": source["storage_policy"],
    }
    payload["content_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    schema = _load_json(root / "schemas/evidence/v1/gate2-owner-review-docket.schema.json")
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    except Exception as error:
        raise Gate2OwnerReviewDocketError(
            "Gate 2 owner-review docket does not match schema"
        ) from error
    return payload


def publish_gate2_owner_review_docket(
    *,
    implementation_identity: str,
    prior_readiness_v5_path: Path,
    output: Path,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Atomically publish the non-promoting owner-review docket."""

    output, _receipt = preflight_evidence(output)
    payload = build_gate2_owner_review_docket(
        implementation_identity=implementation_identity,
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        prior_readiness_v5_path=prior_readiness_v5_path,
        repo_root=repo_root,
    )
    publish_evidence(output, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation-identity", required=True)
    parser.add_argument("--prior-readiness-v5", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = publish_gate2_owner_review_docket(
        implementation_identity=args.implementation_identity,
        prior_readiness_v5_path=args.prior_readiness_v5,
        output=args.output,
        repo_root=args.repo_root,
    )
    print(
        json.dumps(
            {
                "artifact": str(args.output),
                "pending_review_item_count": payload["decision_state"][
                    "required_review_item_count"
                ],
                "receipt": str(args.output.with_suffix(args.output.suffix + ".receipt.json")),
                "status": payload["status"],
            },
            sort_keys=True,
        )
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
