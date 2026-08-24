"""Build a non-promoting owner docket over terminal-funding readiness v6."""

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

import benchmarks.gate2_owner_review_docket as docket_v1

ROOT: Final = Path(__file__).parents[1]
EVIDENCE_CONTRACT: Final = "grid.gate2-owner-review-docket/v2"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
EXPECTED_BLOCKERS: Final = docket_v1.EXPECTED_BLOCKERS
EXPECTED_GATE: Final = docket_v1.EXPECTED_GATE
EXPECTED_READINESS_COUNTS: Final = docket_v1.EXPECTED_READINESS_COUNTS
EXPECTED_OWNER_REVIEW: Final = {
    **docket_v1.EXPECTED_OWNER_REVIEW,
    "funding_availability_owner_disposition": "pending",
}


class Gate2OwnerReviewDocketV2Error(RuntimeError):
    """The terminal-funding owner-review docket failed closed."""


@dataclass(frozen=True, slots=True)
class SourceSpec:
    schema_relative: str
    contract: str
    status: str


READINESS_V6_SPEC: Final = SourceSpec(
    schema_relative="schemas/evidence/v6/gate2-readiness-pack.schema.json",
    contract="grid.gate2-readiness-pack/v6",
    status="blocked-terminal-funding-evidence-awaiting-owner-decision",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Gate2OwnerReviewDocketV2Error(message)


def _mapping(parent: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise Gate2OwnerReviewDocketV2Error(f"evidence field must be an object: {key}")
    return cast(dict[str, Any], value)


def _array(parent: Mapping[str, Any], key: str) -> list[Any]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise Gate2OwnerReviewDocketV2Error(f"evidence field must be an array: {key}")
    return value


def _integer(parent: Mapping[str, Any], key: str, *, minimum: int = 0) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise Gate2OwnerReviewDocketV2Error(f"evidence integer is invalid: {key}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Gate2OwnerReviewDocketV2Error(f"invalid JSON evidence: {path.name}") from error
    if not isinstance(value, dict):
        raise Gate2OwnerReviewDocketV2Error(f"JSON evidence must be an object: {path.name}")
    return cast(dict[str, Any], value)


def _verify_generated_at(generated_at_utc: str) -> None:
    _require(generated_at_utc.endswith("Z"), "generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(generated_at_utc.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise Gate2OwnerReviewDocketV2Error("generated_at_utc is invalid") from error
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
        raise Gate2OwnerReviewDocketV2Error(f"cannot read source bytes: {path.name}") from error
    _require(
        artifact_bytes == canonical_json_bytes(payload) + b"\n",
        f"source is not canonical JSON plus LF: {path.name}",
    )
    schema = _load_json(repo_root / spec.schema_relative)
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    except Exception as error:
        raise Gate2OwnerReviewDocketV2Error(
            f"source schema does not verify: {path.name}"
        ) from error
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


def _verify_v6(source: Mapping[str, Any]) -> dict[str, int]:
    _require(source.get("gate_2") == EXPECTED_GATE, "v6 Gate 2 decision changed")
    _require(
        source.get("readiness_counts") == EXPECTED_READINESS_COUNTS,
        "v6 readiness counts changed",
    )
    criteria = _array(source, "criteria")
    _require(len(criteria) == len(docket_v1.EXPECTED_CRITERIA), "v6 criteria count changed")
    for raw, expected in zip(criteria, docket_v1.EXPECTED_CRITERIA, strict=True):
        _require(isinstance(raw, dict), "v6 criterion is not an object")
        criterion = cast(dict[str, Any], raw)
        criterion_id, criterion_text, readiness, blockers, evidence_roles = expected
        _require(criterion.get("criterion_id") == criterion_id, "v6 criterion order changed")
        _require(criterion.get("criterion_text") == criterion_text, "v6 criterion text changed")
        _require(criterion.get("readiness") == readiness, "v6 criterion readiness changed")
        _require(criterion.get("blocker_codes") == list(blockers), "v6 blockers changed")
        _require(criterion.get("evidence_roles") == list(evidence_roles), "v6 roles changed")
    observations = _mapping(source, "observations")
    _require(
        _mapping(observations, "owner_review") == EXPECTED_OWNER_REVIEW,
        "v6 owner-review state changed",
    )
    current = _mapping(observations, "current_universe")
    terminal_count = _integer(current, "funding_terminal_insufficient_count", minimum=1)
    predecessor_count = _integer(current, "funding_predecessor_proven_count", minimum=1)
    candle_count = _integer(current, "candle_instrument_count", minimum=2)
    _require(current.get("funding_full_scope_exact") is False, "v6 funding scope changed")
    _require(
        terminal_count + predecessor_count == candle_count,
        "v6 funding availability counts do not reconcile",
    )
    return {
        "candle_instrument_count": candle_count,
        "funding_predecessor_proven_count": predecessor_count,
        "funding_terminal_insufficient_count": terminal_count,
    }


def _review_items(source: Mapping[str, Any], availability: Mapping[str, int]) -> dict[str, Any]:
    try:
        items = docket_v1._review_items(source)
    except docket_v1.Gate2OwnerReviewDocketError as error:
        raise Gate2OwnerReviewDocketV2Error(str(error)) from error
    items["deterministic_repair"]["evidence_summary"] = {
        "candle_instrument_count": availability["candle_instrument_count"],
        "funding_full_scope_exact": False,
        "funding_predecessor_proven_count": availability["funding_predecessor_proven_count"],
        "funding_terminal_insufficient_count": availability["funding_terminal_insufficient_count"],
    }
    try:
        docket_v1._verify_blocker_assignment(items)
    except docket_v1.Gate2OwnerReviewDocketError as error:
        raise Gate2OwnerReviewDocketV2Error(str(error)) from error
    return items


def build_gate2_owner_review_docket_v2(
    *,
    implementation_identity: str,
    generated_at_utc: str,
    readiness_v6_path: Path,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Build the pending owner docket over one receipt-verified readiness v6 artifact."""

    _require(
        SOFTWARE_IDENTITY_RE.fullmatch(implementation_identity) is not None,
        "implementation identity must be git:<40 lowercase hex>",
    )
    _verify_generated_at(generated_at_utc)
    root = repo_root.resolve()
    _require(root.is_dir() and not repo_root.is_symlink(), "repository root is unsafe")
    source, source_record = _verify_source(readiness_v6_path, READINESS_V6_SPEC, root)
    availability = _verify_v6(source)
    review_items = _review_items(source, availability)
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
            "terminal_funding_availability_presented": True,
        },
        "bindings": {
            "implementation_identity": implementation_identity,
            "readiness_v6_artifact_sha256": source_record["artifact_sha256"],
            "readiness_v6_content_sha256": source_record["content_sha256"],
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
        "status": "pending-terminal-funding-data-quality-owner-decision",
        "storage_policy": source["storage_policy"],
    }
    payload["content_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    schema = _load_json(root / "schemas/evidence/v2/gate2-owner-review-docket.schema.json")
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    except Exception as error:
        raise Gate2OwnerReviewDocketV2Error(
            "Gate 2 owner-review docket v2 does not match schema"
        ) from error
    return payload


def publish_gate2_owner_review_docket_v2(
    *,
    implementation_identity: str,
    readiness_v6_path: Path,
    output: Path,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Atomically publish the non-promoting terminal-funding owner docket."""

    target, _receipt = preflight_evidence(output)
    payload = build_gate2_owner_review_docket_v2(
        implementation_identity=implementation_identity,
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        readiness_v6_path=readiness_v6_path,
        repo_root=repo_root,
    )
    publish_evidence(target, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation-identity", required=True)
    parser.add_argument("--readiness-v6", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = publish_gate2_owner_review_docket_v2(
        implementation_identity=args.implementation_identity,
        readiness_v6_path=args.readiness_v6,
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
