"""Bind current-universe evidence into a non-promoting Gate 2 readiness successor."""

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
EVIDENCE_CONTRACT: Final = "grid.gate2-readiness-pack/v4"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
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
PRIOR_ARTIFACT_SHA256: Final = "4607ced71078bd4c0e11e8fef7863018532e26e81fbedb719839fe9de11d1278"
PRIOR_CONTENT_SHA256: Final = "0929aaf2cd66c62248b346a43c40a7c0d34709f7af3bdc2525dd9b1b33523283"


class Gate2ReadinessV4Error(RuntimeError):
    """The current-universe readiness chain failed closed."""


@dataclass(frozen=True, slots=True)
class SourceSpec:
    schema_relative: str
    contract: str
    status: str


PRIOR_SPEC: Final = SourceSpec(
    schema_relative="schemas/evidence/v3/gate2-readiness-pack.schema.json",
    contract="grid.gate2-readiness-pack/v3",
    status="blocked-pending-gate2-evidence-and-policy",
)
CANDLE_SPEC: Final = SourceSpec(
    schema_relative="schemas/evidence/v1/phase2-current-universe-candle-evidence.schema.json",
    contract="grid.phase2-current-universe-candle-evidence/v1",
    status="verified-current-universe-candle-evidence",
)
FUNDING_SPEC: Final = SourceSpec(
    schema_relative="schemas/evidence/v1/phase2-current-universe-funding-evidence.schema.json",
    contract="grid.phase2-current-universe-funding-evidence/v1",
    status="verified-current-universe-funding-evidence",
)
PERFORMANCE_SPEC: Final = SourceSpec(
    schema_relative=("schemas/evidence/v1/phase2-current-universe-catalog-performance.schema.json"),
    contract="grid.phase2-current-universe-catalog-performance/v1",
    status="measured-current-universe-catalog-selection",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Gate2ReadinessV4Error(message)


def _mapping(parent: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise Gate2ReadinessV4Error(f"evidence field must be an object: {key}")
    return cast(dict[str, Any], value)


def _array(parent: Mapping[str, Any], key: str) -> list[Any]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise Gate2ReadinessV4Error(f"evidence field must be an array: {key}")
    return value


def _integer(parent: Mapping[str, Any], key: str, *, minimum: int = 0) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise Gate2ReadinessV4Error(f"evidence integer is invalid: {key}")
    return value


def _sha(parent: Mapping[str, Any], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise Gate2ReadinessV4Error(f"evidence SHA-256 is invalid: {key}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Gate2ReadinessV4Error(f"invalid JSON evidence: {path.name}") from error
    if not isinstance(value, dict):
        raise Gate2ReadinessV4Error(f"JSON evidence must be an object: {path.name}")
    return cast(dict[str, Any], value)


def _verify_generated_at(generated_at_utc: str) -> None:
    _require(generated_at_utc.endswith("Z"), "generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(generated_at_utc.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise Gate2ReadinessV4Error("generated_at_utc is invalid") from error
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
        raise Gate2ReadinessV4Error(f"cannot read source bytes: {path.name}") from error
    _require(
        artifact_bytes == canonical_json_bytes(payload) + b"\n",
        f"source is not canonical JSON plus LF: {path.name}",
    )
    schema = _load_json(repo_root / spec.schema_relative)
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    except Exception as error:
        raise Gate2ReadinessV4Error(f"source schema does not verify: {path.name}") from error
    _require(
        payload.get("evidence_schema") == spec.contract,
        f"source contract differs: {path.name}",
    )
    _require(payload.get("status") == spec.status, f"source status differs: {path.name}")
    hash_input = dict(payload)
    embedded = hash_input.pop("content_sha256", None)
    _require(embedded == canonical_sha256(hash_input), f"source content hash differs: {path.name}")
    return payload, {
        "artifact": resolved.name,
        "artifact_sha256": sha256_file(resolved),
        "content_sha256": cast(str, embedded),
        "contract": spec.contract,
        "status": spec.status,
    }


def _kind_inventory(candle: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for raw in _array(_mapping(candle, "inventory"), "by_kind"):
        _require(isinstance(raw, dict), "candle kind inventory must be an object")
        item = cast(dict[str, Any], raw)
        kind = item.get("kind")
        _require(kind in {"trade", "mark"}, "candle kind inventory is invalid")
        _require(cast(str, kind) not in values, "candle kind inventory repeats a kind")
        values[cast(str, kind)] = item
    _require(set(values) == {"trade", "mark"}, "candle kind inventory is incomplete")
    return values


def _verify_cross_bindings(
    candle: Mapping[str, Any],
    funding: Mapping[str, Any],
    performance: Mapping[str, Any],
    *,
    candle_artifact_sha256: str,
) -> dict[str, dict[str, Any]]:
    candle_bindings = _mapping(candle, "bindings")
    funding_bindings = _mapping(funding, "bindings")
    performance_bindings = _mapping(performance, "bindings")
    _require(
        _sha(candle_bindings, "capacity_evidence_sha256")
        == _sha(funding_bindings, "capacity_evidence_sha256")
        and _sha(candle_bindings, "instrument_registry_sha256")
        == _sha(funding_bindings, "instrument_registry_sha256"),
        "current-universe registry/capacity bindings differ",
    )
    _require(
        _sha(funding_bindings, "candle_evidence_artifact_sha256") == candle_artifact_sha256,
        "funding evidence binds another candle artifact",
    )
    _require(
        _sha(performance_bindings, "bundle_evidence_artifact_sha256")
        == _sha(candle_bindings, "catalog_bundle_artifact_sha256")
        and _sha(performance_bindings, "bundle_evidence_content_sha256")
        == _sha(candle_bindings, "catalog_bundle_content_sha256"),
        "catalog performance binds another bundle evidence",
    )
    _require(
        _mapping(candle, "catalog")
        == {
            "content_sha256": _sha(performance_bindings, "catalog_content_sha256"),
            "revision": _integer(performance_bindings, "catalog_revision", minimum=1),
        },
        "catalog performance snapshot differs from candle evidence",
    )

    candle_inventory = _mapping(candle, "inventory")
    funding_inventory = _mapping(funding, "inventory")
    funding_universe = _mapping(funding, "universe")
    performance_correctness = _mapping(performance, "correctness")
    performance_configuration = _mapping(performance, "configuration")
    _require(
        _integer(candle_inventory, "instrument_count", minimum=1)
        == _integer(funding_inventory, "symbol_count", minimum=1)
        == _integer(funding_universe, "symbol_count", minimum=1),
        "candle/funding universe count differs",
    )
    _require(
        funding_universe.get("interval_partition_exact") is True,
        "funding interval partition is not exact",
    )
    by_kind = _kind_inventory(candle)
    candle_dataset_count = sum(
        _integer(item, "catalog_dataset_count", minimum=1) for item in by_kind.values()
    )
    candle_object_count = sum(
        _integer(item, "catalog_object_count", minimum=1) for item in by_kind.values()
    )
    candle_row_count = sum(_integer(item, "catalog_row_count") for item in by_kind.values())
    candle_size_bytes = sum(
        _integer(item, "catalog_size_bytes", minimum=1) for item in by_kind.values()
    )
    _require(
        candle_dataset_count == _integer(performance_correctness, "dataset_count", minimum=1)
        and candle_object_count == _integer(performance_correctness, "object_count", minimum=1)
        and candle_row_count == _integer(performance_correctness, "row_count", minimum=1)
        and candle_size_bytes == _integer(performance_correctness, "size_bytes", minimum=1)
        and _integer(candle_inventory, "selection_count", minimum=1)
        == _integer(performance_configuration, "selection_count", minimum=1)
        and _integer(candle_inventory, "source_count", minimum=1)
        == _integer(performance_correctness, "source_count", minimum=1),
        "catalog performance inventory differs from candle evidence",
    )
    return by_kind


def _verify_quality(candle: Mapping[str, Any], funding: Mapping[str, Any]) -> None:
    candle_quality = _mapping(_mapping(candle, "quality"), "candle")
    funding_quality = _mapping(_mapping(funding, "quality"), "funding")
    for key in (
        "conflicting_key_count",
        "duplicate_key_count",
        "lifecycle_failure_count",
        "unexpected_timestamp_count",
        "unrequested_row_count",
    ):
        _require(
            _integer(candle_quality, key) == 0,
            f"current candle quality contradicts v3: {key}",
        )
    for key in (
        "duplicate_key_count",
        "internal_interval_mismatch_count",
        "lifecycle_failure_count",
        "predecessor_interval_mismatch_count",
        "unexpected_timestamp_count",
        "unrequested_row_count",
    ):
        _require(
            _integer(funding_quality, key) == 0,
            f"current funding quality contradicts v3: {key}",
        )


def _source_record_chain(records: Mapping[str, Mapping[str, str]]) -> str:
    return canonical_sha256(
        [
            {
                "artifact_sha256": record["artifact_sha256"],
                "content_sha256": record["content_sha256"],
                "contract": record["contract"],
                "role": role,
                "status": record["status"],
            }
            for role, record in sorted(records.items())
        ]
    )


def build_gate2_readiness_pack_v4(
    *,
    implementation_identity: str,
    generated_at_utc: str,
    prior_readiness_path: Path,
    candle_evidence_path: Path,
    funding_evidence_path: Path,
    catalog_performance_path: Path,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Verify current-universe evidence while preserving the exact v3 decision."""

    _require(
        SOFTWARE_IDENTITY_RE.fullmatch(implementation_identity) is not None,
        "implementation identity must be git:<40 lowercase hex>",
    )
    _verify_generated_at(generated_at_utc)
    root = repo_root.resolve()
    _require(root.is_dir() and not repo_root.is_symlink(), "repository root is unsafe")
    prior, prior_record = _verify_source(prior_readiness_path, PRIOR_SPEC, root)
    candle, candle_record = _verify_source(candle_evidence_path, CANDLE_SPEC, root)
    funding, funding_record = _verify_source(funding_evidence_path, FUNDING_SPEC, root)
    performance, performance_record = _verify_source(
        catalog_performance_path, PERFORMANCE_SPEC, root
    )
    _require(
        prior_record["artifact_sha256"] == PRIOR_ARTIFACT_SHA256
        and prior_record["content_sha256"] == PRIOR_CONTENT_SHA256,
        "prior Gate 2 readiness v3 artifact differs from the accepted source",
    )
    by_kind = _verify_cross_bindings(
        candle,
        funding,
        performance,
        candle_artifact_sha256=candle_record["artifact_sha256"],
    )
    _verify_quality(candle, funding)

    _require(prior.get("gate_2") == EXPECTED_GATE, "prior Gate 2 decision changed")
    _require(
        prior.get("readiness_counts")
        == {
            "blocked_criterion_count": 3,
            "criterion_count": 6,
            "evidence_ready_criterion_count": 3,
        },
        "prior readiness counts changed",
    )
    criteria = _array(prior, "criteria")
    _require(len(criteria) == 6, "prior Gate 2 criteria count changed")
    blocker_codes: set[str] = set()
    for item in criteria:
        _require(isinstance(item, dict), "prior Gate 2 criterion is not an object")
        for code in _array(cast(dict[str, Any], item), "blocker_codes"):
            _require(isinstance(code, str), "prior Gate 2 blocker code is not a string")
            blocker_codes.add(code)
    _require(sorted(blocker_codes) == EXPECTED_BLOCKERS, "prior Gate 2 blocker set changed")
    candle_inventory = _mapping(candle, "inventory")
    candle_quality = _mapping(_mapping(candle, "quality"), "candle")
    funding_inventory = _mapping(funding, "inventory")
    funding_quality = _mapping(_mapping(funding, "quality"), "funding")
    performance_correctness = _mapping(performance, "correctness")
    performance_measurement = _mapping(performance, "measurement")
    candle_performance = _mapping(candle, "performance")
    funding_performance = _mapping(funding, "performance")
    _require(
        _mapping(candle_performance, "envelope")
        == _mapping(funding_performance, "envelope")
        == {"owner_review_required": True, "qualified": False},
        "current-universe performance envelope was reinterpreted",
    )
    records = {
        "current-universe-candles": candle_record,
        "current-universe-catalog-performance": performance_record,
        "current-universe-funding": funding_record,
        "prior-readiness-v3": prior_record,
    }
    candle_catalog_dataset_count = sum(
        _integer(item, "catalog_dataset_count", minimum=1) for item in by_kind.values()
    )
    candle_catalog_object_count = sum(
        _integer(item, "catalog_object_count", minimum=1) for item in by_kind.values()
    )
    candle_catalog_row_count = sum(_integer(item, "catalog_row_count") for item in by_kind.values())
    candle_catalog_size_bytes = sum(
        _integer(item, "catalog_size_bytes", minimum=1) for item in by_kind.values()
    )
    payload: dict[str, Any] = {
        "assurances": {
            "all_source_content_hashes_verified": True,
            "all_source_receipts_verified": True,
            "all_source_schemas_verified": True,
            "automatic_gate_acceptance_performed": False,
            "cross_source_bindings_verified": True,
            "current_universe_scope_reconciled": True,
            "network_request_performed": False,
            "phase3_authorized": False,
            "prior_readiness_decision_preserved": True,
            "private_or_live_capability_used": False,
        },
        "bindings": {
            "implementation_identity": implementation_identity,
            "prior_readiness_artifact_sha256": prior_record["artifact_sha256"],
            "prior_readiness_content_sha256": prior_record["content_sha256"],
            "source_chain_sha256": _source_record_chain(records),
        },
        "content_sha256": "",
        "criteria": criteria,
        "criteria_source": prior["criteria_source"],
        "evidence_schema": EVIDENCE_CONTRACT,
        "gate_2": EXPECTED_GATE,
        "generated_at_utc": generated_at_utc,
        "observations": {
            "current_universe_candles": {
                "catalog_dataset_count": candle_catalog_dataset_count,
                "catalog_object_count": candle_catalog_object_count,
                "catalog_row_count": candle_catalog_row_count,
                "catalog_size_bytes": candle_catalog_size_bytes,
                "conflicting_key_count": _integer(candle_quality, "conflicting_key_count"),
                "duplicate_key_count": _integer(candle_quality, "duplicate_key_count"),
                "instrument_count": _integer(candle_inventory, "instrument_count", minimum=1),
                "missing_minute_count": _integer(candle_quality, "missing_minute_count"),
                "selection_count": _integer(candle_inventory, "selection_count", minimum=1),
                "source_count": _integer(candle_inventory, "source_count", minimum=1),
            },
            "current_universe_funding": {
                "canonical_dataset_count": _integer(
                    funding_inventory, "canonical_dataset_count", minimum=1
                ),
                "canonical_row_count": _integer(
                    funding_inventory, "canonical_row_count", minimum=1
                ),
                "duplicate_key_count": _integer(funding_quality, "duplicate_key_count"),
                "empty_range_page_count": _integer(funding_quality, "empty_range_page_count"),
                "interval_change_count": _integer(funding_quality, "interval_change_count"),
                "source_count": _integer(funding_inventory, "source_count", minimum=1),
                "symbol_count": _integer(funding_inventory, "symbol_count", minimum=1),
            },
            "current_universe_catalog_performance": {
                "dataset_count": _integer(performance_correctness, "dataset_count", minimum=1),
                "deterministic_repeat_equal": (
                    performance_correctness.get("deterministic_repeat_equal") is True
                ),
                "first_pass_rows_per_second": _integer(
                    performance_measurement, "first_pass_rows_per_second", minimum=1
                ),
                "first_pass_wall_elapsed_ns": _integer(
                    performance_measurement, "first_pass_wall_elapsed_ns", minimum=1
                ),
                "repeat_pass_rows_per_second": _integer(
                    performance_measurement, "repeat_pass_rows_per_second", minimum=1
                ),
                "repeat_pass_wall_elapsed_ns": _integer(
                    performance_measurement, "repeat_pass_wall_elapsed_ns", minimum=1
                ),
                "row_count": _integer(performance_correctness, "row_count", minimum=1),
                "state_fingerprint_equal_before_after": (
                    performance_correctness.get("state_fingerprint_equal_before_after") is True
                ),
            },
            "owner_review": {
                "blocked_criterion_count": 3,
                "envelope_qualified": False,
                "owner_review_required": True,
                "unique_blocker_count": len(EXPECTED_BLOCKERS),
            },
        },
        "readiness_counts": prior["readiness_counts"],
        "sources": records,
        "status": "blocked-current-universe-evidence-awaiting-owner-policy",
        "storage_policy": prior["storage_policy"],
    }
    payload["content_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    schema = _load_json(root / "schemas/evidence/v4/gate2-readiness-pack.schema.json")
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    except Exception as error:
        raise Gate2ReadinessV4Error("Gate 2 readiness pack v4 does not match its schema") from error
    return payload


def publish_gate2_readiness_pack_v4(
    *,
    implementation_identity: str,
    prior_readiness_path: Path,
    candle_evidence_path: Path,
    funding_evidence_path: Path,
    catalog_performance_path: Path,
    output: Path,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    output, _receipt = preflight_evidence(output)
    payload = build_gate2_readiness_pack_v4(
        implementation_identity=implementation_identity,
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        prior_readiness_path=prior_readiness_path,
        candle_evidence_path=candle_evidence_path,
        funding_evidence_path=funding_evidence_path,
        catalog_performance_path=catalog_performance_path,
        repo_root=repo_root,
    )
    publish_evidence(output, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation-identity", required=True)
    parser.add_argument("--prior-readiness", type=Path, required=True)
    parser.add_argument("--candle-evidence", type=Path, required=True)
    parser.add_argument("--funding-evidence", type=Path, required=True)
    parser.add_argument("--catalog-performance", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = publish_gate2_readiness_pack_v4(
        implementation_identity=args.implementation_identity,
        prior_readiness_path=args.prior_readiness,
        candle_evidence_path=args.candle_evidence,
        funding_evidence_path=args.funding_evidence,
        catalog_performance_path=args.catalog_performance,
        output=args.output,
        repo_root=args.repo_root,
    )
    print(
        json.dumps(
            {
                "artifact": str(args.output),
                "blocked_criterion_count": payload["readiness_counts"]["blocked_criterion_count"],
                "receipt": str(args.output.with_suffix(args.output.suffix + ".receipt.json")),
                "status": payload["status"],
            },
            sort_keys=True,
        )
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
