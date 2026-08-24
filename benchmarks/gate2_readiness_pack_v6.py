"""Build a non-promoting Gate 2 readiness successor over terminal funding evidence."""

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

import benchmarks.gate2_readiness_pack_v5 as readiness_v5

ROOT: Final = Path(__file__).parents[1]
EVIDENCE_CONTRACT: Final = "grid.gate2-readiness-pack/v6"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
EXPECTED_V3_ARTIFACT_SHA256: Final = (
    "4607ced71078bd4c0e11e8fef7863018532e26e81fbedb719839fe9de11d1278"
)
EXPECTED_V3_CONTENT_SHA256: Final = (
    "0929aaf2cd66c62248b346a43c40a7c0d34709f7af3bdc2525dd9b1b33523283"
)
EXPECTED_BLOCKERS: Final = readiness_v5.EXPECTED_BLOCKERS
EXPECTED_GATE: Final = readiness_v5.EXPECTED_GATE
EXPECTED_READINESS_COUNTS: Final = {
    "blocked_criterion_count": 3,
    "criterion_count": 6,
    "evidence_ready_criterion_count": 3,
}


class Gate2ReadinessV6Error(RuntimeError):
    """The terminal-funding Gate 2 readiness chain failed closed."""


@dataclass(frozen=True, slots=True)
class SourceSpec:
    schema_relative: str
    contract_key: str
    contract: str
    status: str
    expected_artifact_sha256: str | None = None


PRIOR_SPEC: Final = SourceSpec(
    schema_relative="schemas/evidence/v3/gate2-readiness-pack.schema.json",
    contract_key="evidence_schema",
    contract="grid.gate2-readiness-pack/v3",
    status="blocked-pending-gate2-evidence-and-policy",
    expected_artifact_sha256=EXPECTED_V3_ARTIFACT_SHA256,
)
CANDLE_SPEC: Final = SourceSpec(
    schema_relative="schemas/evidence/v1/phase2-current-universe-candle-evidence.schema.json",
    contract_key="evidence_schema",
    contract="grid.phase2-current-universe-candle-evidence/v1",
    status="verified-current-universe-candle-evidence",
)
FUNDING_SPEC: Final = SourceSpec(
    schema_relative="schemas/evidence/v1/phase2-current-universe-funding-evidence-v2.schema.json",
    contract_key="evidence_schema",
    contract="grid.phase2-current-universe-funding-evidence/v2",
    status="blocked-current-universe-funding-terminal-absence",
)
PERFORMANCE_SPEC: Final = SourceSpec(
    schema_relative="schemas/evidence/v1/phase2-current-universe-catalog-performance.schema.json",
    contract_key="evidence_schema",
    contract="grid.phase2-current-universe-catalog-performance/v1",
    status="measured-current-universe-catalog-selection",
)
FUNDING_POLICY_SPEC: Final = SourceSpec(
    schema_relative=readiness_v5.FUNDING_POLICY_SPEC.schema_relative,
    contract_key=readiness_v5.FUNDING_POLICY_SPEC.contract_key,
    contract=readiness_v5.FUNDING_POLICY_SPEC.contract,
    status=readiness_v5.FUNDING_POLICY_SPEC.status,
    expected_artifact_sha256=readiness_v5.FUNDING_POLICY_SPEC.expected_artifact_sha256,
)
LEGACY_SPEC: Final = SourceSpec(
    schema_relative=readiness_v5.LEGACY_SPEC.schema_relative,
    contract_key=readiness_v5.LEGACY_SPEC.contract_key,
    contract=readiness_v5.LEGACY_SPEC.contract,
    status=readiness_v5.LEGACY_SPEC.status,
    expected_artifact_sha256=readiness_v5.LEGACY_SPEC.expected_artifact_sha256,
)
LIFECYCLE_SPEC: Final = SourceSpec(
    schema_relative=readiness_v5.LIFECYCLE_SPEC.schema_relative,
    contract_key=readiness_v5.LIFECYCLE_SPEC.contract_key,
    contract=readiness_v5.LIFECYCLE_SPEC.contract,
    status=readiness_v5.LIFECYCLE_SPEC.status,
    expected_artifact_sha256=readiness_v5.LIFECYCLE_SPEC.expected_artifact_sha256,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Gate2ReadinessV6Error(message)


def _mapping(parent: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise Gate2ReadinessV6Error(f"evidence field must be an object: {key}")
    return cast(dict[str, Any], value)


def _array(parent: Mapping[str, Any], key: str) -> list[Any]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise Gate2ReadinessV6Error(f"evidence field must be an array: {key}")
    return value


def _integer(parent: Mapping[str, Any], key: str, *, minimum: int = 0) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise Gate2ReadinessV6Error(f"evidence integer is invalid: {key}")
    return value


def _sha(parent: Mapping[str, Any], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise Gate2ReadinessV6Error(f"evidence SHA-256 is invalid: {key}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Gate2ReadinessV6Error(f"invalid JSON evidence: {path.name}") from error
    if not isinstance(value, dict):
        raise Gate2ReadinessV6Error(f"JSON evidence must be an object: {path.name}")
    return cast(dict[str, Any], value)


def _verify_generated_at(generated_at_utc: str) -> None:
    _require(generated_at_utc.endswith("Z"), "generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(generated_at_utc.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise Gate2ReadinessV6Error("generated_at_utc is invalid") from error
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
        raise Gate2ReadinessV6Error(f"cannot read source bytes: {path.name}") from error
    _require(
        artifact_bytes == canonical_json_bytes(payload) + b"\n",
        f"source is not canonical JSON plus LF: {path.name}",
    )
    schema = _load_json(repo_root / spec.schema_relative)
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    except Exception as error:
        raise Gate2ReadinessV6Error(f"source schema does not verify: {path.name}") from error
    _require(
        payload.get(spec.contract_key) == spec.contract,
        f"source contract differs: {path.name}",
    )
    _require(payload.get("status") == spec.status, f"source status differs: {path.name}")
    hash_input = dict(payload)
    embedded = hash_input.pop("content_sha256", None)
    _require(embedded == canonical_sha256(hash_input), f"source content hash differs: {path.name}")
    artifact_sha256 = sha256_file(resolved)
    if spec.expected_artifact_sha256 is not None:
        _require(
            artifact_sha256 == spec.expected_artifact_sha256,
            f"source artifact differs from accepted evidence: {path.name}",
        )
    return payload, {
        "artifact": resolved.name,
        "artifact_sha256": artifact_sha256,
        "content_sha256": cast(str, embedded),
        "contract": spec.contract,
        "status": spec.status,
    }


def _verify_prior(prior: Mapping[str, Any], record: Mapping[str, str]) -> None:
    _require(
        record.get("artifact_sha256") == EXPECTED_V3_ARTIFACT_SHA256
        and record.get("content_sha256") == EXPECTED_V3_CONTENT_SHA256,
        "prior Gate 2 readiness v3 differs from the accepted source",
    )
    _require(prior.get("gate_2") == EXPECTED_GATE, "prior Gate 2 decision changed")
    _require(
        prior.get("readiness_counts") == EXPECTED_READINESS_COUNTS,
        "prior readiness counts changed",
    )
    criteria = _array(prior, "criteria")
    _require(len(criteria) == 6, "prior Gate 2 criteria count changed")
    blockers: list[str] = []
    for raw in criteria:
        _require(isinstance(raw, dict), "prior Gate 2 criterion is not an object")
        blockers.extend(cast(list[str], _array(cast(dict[str, Any], raw), "blocker_codes")))
    _require(len(blockers) == len(set(blockers)), "prior Gate 2 blocker repeats")
    _require(sorted(blockers) == EXPECTED_BLOCKERS, "prior Gate 2 blocker set changed")


def _kind_inventory(candle: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in _array(_mapping(candle, "inventory"), "by_kind"):
        _require(isinstance(raw, dict), "candle kind inventory must be an object")
        item = cast(dict[str, Any], raw)
        kind = item.get("kind")
        _require(kind in {"trade", "mark"}, "candle kind inventory is invalid")
        _require(cast(str, kind) not in result, "candle kind inventory repeats")
        result[cast(str, kind)] = item
    _require(set(result) == {"trade", "mark"}, "candle kind inventory is incomplete")
    return result


def _verify_current_universe(
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
        "funding v2 binds another candle artifact",
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
    terminal = _mapping(funding, "terminal_partition")
    candle_count = _integer(candle_inventory, "instrument_count", minimum=1)
    funding_count = _integer(funding_inventory, "symbol_count", minimum=1)
    insufficient_count = _integer(funding_universe, "terminal_insufficient_symbol_count", minimum=1)
    _require(
        candle_count == _integer(funding_universe, "candle_symbol_count", minimum=2),
        "funding v2 candle universe count differs",
    )
    _require(
        funding_count
        == _integer(funding_universe, "funding_symbol_count", minimum=1)
        == _integer(terminal, "predecessor_proven_count", minimum=1),
        "funding v2 predecessor-proven count differs",
    )
    _require(
        insufficient_count
        == _integer(terminal, "terminal_insufficient_one_count")
        + _integer(terminal, "terminal_insufficient_zero_count")
        and funding_count + insufficient_count == candle_count
        and _integer(terminal, "symbol_count", minimum=2) == candle_count,
        "funding v2 terminal partition does not reconcile",
    )
    _require(
        funding_universe.get("full_scope_exact") is False
        and funding_universe.get("predecessor_partition_exact") is True
        and terminal.get("funding_coverage_complete") is False,
        "funding v2 availability state was reinterpreted",
    )
    _require(
        _sha(terminal, "private_anomaly_sha256")
        == _sha(funding_bindings, "private_anomaly_sha256"),
        "funding v2 private anomaly binding differs",
    )

    by_kind = _kind_inventory(candle)
    correctness = _mapping(performance, "correctness")
    configuration = _mapping(performance, "configuration")
    _require(
        sum(_integer(item, "catalog_dataset_count", minimum=1) for item in by_kind.values())
        == _integer(correctness, "dataset_count", minimum=1)
        and sum(_integer(item, "catalog_object_count", minimum=1) for item in by_kind.values())
        == _integer(correctness, "object_count", minimum=1)
        and sum(_integer(item, "catalog_row_count") for item in by_kind.values())
        == _integer(correctness, "row_count", minimum=1)
        and sum(_integer(item, "catalog_size_bytes", minimum=1) for item in by_kind.values())
        == _integer(correctness, "size_bytes", minimum=1)
        and _integer(candle_inventory, "selection_count", minimum=1)
        == _integer(configuration, "selection_count", minimum=1)
        and _integer(candle_inventory, "source_count", minimum=1)
        == _integer(correctness, "source_count", minimum=1),
        "catalog performance inventory differs from candle evidence",
    )

    candle_quality = _mapping(_mapping(candle, "quality"), "candle")
    funding_quality = _mapping(_mapping(funding, "quality"), "funding")
    for key in (
        "conflicting_key_count",
        "duplicate_key_count",
        "lifecycle_failure_count",
        "unexpected_timestamp_count",
        "unrequested_row_count",
    ):
        _require(_integer(candle_quality, key) == 0, f"candle quality contradicts v3: {key}")
    for key in (
        "duplicate_key_count",
        "internal_interval_mismatch_count",
        "lifecycle_failure_count",
        "predecessor_interval_mismatch_count",
        "unexpected_timestamp_count",
        "unrequested_row_count",
    ):
        _require(_integer(funding_quality, key) == 0, f"funding quality contradicts v3: {key}")
    _require(
        _mapping(_mapping(candle, "performance"), "envelope")
        == _mapping(_mapping(funding, "performance"), "envelope")
        == {"owner_review_required": True, "qualified": False},
        "current-universe performance envelope was reinterpreted",
    )
    return {
        "by_kind": cast(dict[str, Any], by_kind),
        "candle_inventory": candle_inventory,
        "candle_quality": candle_quality,
        "funding_inventory": funding_inventory,
        "funding_quality": funding_quality,
        "funding_universe": funding_universe,
        "performance_correctness": correctness,
        "performance_measurement": _mapping(performance, "measurement"),
        "terminal": terminal,
    }


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


def _accepted_policy_observations(
    policy: Mapping[str, Any],
    legacy: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    *,
    legacy_record: Mapping[str, str],
) -> tuple[dict[str, int], dict[str, int], dict[str, Any]]:
    try:
        return (
            readiness_v5._verify_policy(policy),
            readiness_v5._legacy_observation(legacy),
            readiness_v5._verify_lifecycle(
                lifecycle,
                legacy,
                legacy_record=legacy_record,
            ),
        )
    except readiness_v5.Gate2ReadinessV5Error as error:
        raise Gate2ReadinessV6Error(str(error)) from error


def build_gate2_readiness_pack_v6(
    *,
    implementation_identity: str,
    generated_at_utc: str,
    prior_readiness_path: Path,
    candle_evidence_path: Path,
    funding_evidence_v2_path: Path,
    catalog_performance_path: Path,
    funding_policy_path: Path,
    legacy_listing_path: Path,
    lifecycle_coverage_path: Path,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Build one blocked readiness pack without requiring unavailable v4/v5 artifacts."""

    _require(
        SOFTWARE_IDENTITY_RE.fullmatch(implementation_identity) is not None,
        "implementation identity must be git:<40 lowercase hex>",
    )
    _verify_generated_at(generated_at_utc)
    root = repo_root.resolve()
    _require(root.is_dir() and not repo_root.is_symlink(), "repository root is unsafe")
    prior, prior_record = _verify_source(prior_readiness_path, PRIOR_SPEC, root)
    candle, candle_record = _verify_source(candle_evidence_path, CANDLE_SPEC, root)
    funding, funding_record = _verify_source(funding_evidence_v2_path, FUNDING_SPEC, root)
    performance, performance_record = _verify_source(
        catalog_performance_path, PERFORMANCE_SPEC, root
    )
    policy, policy_record = _verify_source(funding_policy_path, FUNDING_POLICY_SPEC, root)
    legacy, legacy_record = _verify_source(legacy_listing_path, LEGACY_SPEC, root)
    lifecycle, lifecycle_record = _verify_source(lifecycle_coverage_path, LIFECYCLE_SPEC, root)
    _verify_prior(prior, prior_record)
    current = _verify_current_universe(
        candle,
        funding,
        performance,
        candle_artifact_sha256=candle_record["artifact_sha256"],
    )
    policy_observation, legacy_observation, lifecycle_observation = _accepted_policy_observations(
        policy,
        legacy,
        lifecycle,
        legacy_record=legacy_record,
    )
    records = {
        "current-universe-candles": candle_record,
        "current-universe-catalog-performance": performance_record,
        "current-universe-funding-v2": funding_record,
        "funding-cadence-policy": policy_record,
        "legacy-listing-events": legacy_record,
        "official-lifecycle-coverage": lifecycle_record,
        "prior-readiness-v3": prior_record,
    }
    by_kind = current["by_kind"]
    candle_inventory = current["candle_inventory"]
    candle_quality = current["candle_quality"]
    funding_inventory = current["funding_inventory"]
    funding_quality = current["funding_quality"]
    funding_universe = current["funding_universe"]
    terminal = current["terminal"]
    correctness = current["performance_correctness"]
    measurement = current["performance_measurement"]
    payload: dict[str, Any] = {
        "assurances": {
            "all_source_content_hashes_verified": True,
            "all_source_receipts_verified": True,
            "all_source_schemas_verified": True,
            "automatic_gate_acceptance_performed": False,
            "cross_source_bindings_verified": True,
            "full_candle_universe_preserved": True,
            "market_data_or_policy_network_request_performed": False,
            "phase3_authorized": False,
            "prior_readiness_decision_preserved": True,
            "private_or_live_capability_used": False,
            "terminal_funding_partition_verified": True,
        },
        "bindings": {
            "funding_v2_artifact_sha256": funding_record["artifact_sha256"],
            "funding_v2_content_sha256": funding_record["content_sha256"],
            "implementation_identity": implementation_identity,
            "prior_readiness_artifact_sha256": prior_record["artifact_sha256"],
            "prior_readiness_content_sha256": prior_record["content_sha256"],
            "source_chain_sha256": _source_record_chain(records),
        },
        "content_sha256": "",
        "criteria": prior["criteria"],
        "criteria_source": prior["criteria_source"],
        "evidence_schema": EVIDENCE_CONTRACT,
        "gate_2": EXPECTED_GATE,
        "generated_at_utc": generated_at_utc,
        "observations": {
            "current_universe": {
                "candle_catalog_dataset_count": sum(
                    _integer(item, "catalog_dataset_count", minimum=1) for item in by_kind.values()
                ),
                "candle_instrument_count": _integer(
                    candle_inventory, "instrument_count", minimum=1
                ),
                "candle_missing_minute_count": _integer(candle_quality, "missing_minute_count"),
                "catalog_deterministic_repeat_equal": (
                    correctness.get("deterministic_repeat_equal") is True
                ),
                "catalog_first_pass_rows_per_second": _integer(
                    measurement, "first_pass_rows_per_second", minimum=1
                ),
                "catalog_repeat_pass_rows_per_second": _integer(
                    measurement, "repeat_pass_rows_per_second", minimum=1
                ),
                "funding_canonical_dataset_count": _integer(
                    funding_inventory, "canonical_dataset_count", minimum=1
                ),
                "funding_full_scope_exact": False,
                "funding_interval_change_count": _integer(funding_quality, "interval_change_count"),
                "funding_predecessor_proven_count": _integer(
                    terminal, "predecessor_proven_count", minimum=1
                ),
                "funding_terminal_insufficient_count": _integer(
                    funding_universe, "terminal_insufficient_symbol_count", minimum=1
                ),
            },
            "funding_cadence_policy": policy_observation,
            "legacy_listing_events": legacy_observation,
            "official_lifecycle_coverage": lifecycle_observation,
            "owner_review": {
                "blocked_criterion_count": 3,
                "blocker_removal_performed": False,
                "funding_availability_owner_disposition": "pending",
                "funding_cadence_owner_disposition": "pending",
                "lifecycle_owner_disposition": "pending",
                "owner_decision_required": True,
                "performance_envelope_qualified": False,
                "unique_blocker_count": 7,
            },
        },
        "readiness_counts": EXPECTED_READINESS_COUNTS,
        "sources": records,
        "status": "blocked-terminal-funding-evidence-awaiting-owner-decision",
        "storage_policy": prior["storage_policy"],
    }
    payload["content_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    schema = _load_json(root / "schemas/evidence/v6/gate2-readiness-pack.schema.json")
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    except Exception as error:
        raise Gate2ReadinessV6Error("Gate 2 readiness pack v6 does not match its schema") from error
    return payload


def publish_gate2_readiness_pack_v6(
    *,
    implementation_identity: str,
    prior_readiness_path: Path,
    candle_evidence_path: Path,
    funding_evidence_v2_path: Path,
    catalog_performance_path: Path,
    funding_policy_path: Path,
    legacy_listing_path: Path,
    lifecycle_coverage_path: Path,
    output: Path,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Publish receipt-last blocked v6 readiness evidence."""

    target, _receipt = preflight_evidence(output)
    payload = build_gate2_readiness_pack_v6(
        implementation_identity=implementation_identity,
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        prior_readiness_path=prior_readiness_path,
        candle_evidence_path=candle_evidence_path,
        funding_evidence_v2_path=funding_evidence_v2_path,
        catalog_performance_path=catalog_performance_path,
        funding_policy_path=funding_policy_path,
        legacy_listing_path=legacy_listing_path,
        lifecycle_coverage_path=lifecycle_coverage_path,
        repo_root=repo_root,
    )
    publish_evidence(target, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation-identity", required=True)
    parser.add_argument("--prior-readiness-v3", type=Path, required=True)
    parser.add_argument("--candle-evidence", type=Path, required=True)
    parser.add_argument("--funding-evidence-v2", type=Path, required=True)
    parser.add_argument("--catalog-performance", type=Path, required=True)
    parser.add_argument("--funding-cadence-policy", type=Path, required=True)
    parser.add_argument("--legacy-listing-evidence", type=Path, required=True)
    parser.add_argument("--lifecycle-coverage", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = publish_gate2_readiness_pack_v6(
        implementation_identity=args.implementation_identity,
        prior_readiness_path=args.prior_readiness_v3,
        candle_evidence_path=args.candle_evidence,
        funding_evidence_v2_path=args.funding_evidence_v2,
        catalog_performance_path=args.catalog_performance,
        funding_policy_path=args.funding_cadence_policy,
        legacy_listing_path=args.legacy_listing_evidence,
        lifecycle_coverage_path=args.lifecycle_coverage,
        repo_root=args.repo_root,
        output=args.output,
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
