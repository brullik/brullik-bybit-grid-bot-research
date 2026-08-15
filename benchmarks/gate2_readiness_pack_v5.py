"""Consolidate current-universe and policy evidence for Gate 2 owner review."""

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
EVIDENCE_CONTRACT: Final = "grid.gate2-readiness-pack/v5"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
EXPECTED_V4_IMPLEMENTATION: Final = "git:d65dcf6c0958d6a459efa99069806cd21ac5d4a0"
EXPECTED_V3_ARTIFACT_SHA256: Final = (
    "4607ced71078bd4c0e11e8fef7863018532e26e81fbedb719839fe9de11d1278"
)
EXPECTED_V3_CONTENT_SHA256: Final = (
    "0929aaf2cd66c62248b346a43c40a7c0d34709f7af3bdc2525dd9b1b33523283"
)
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
EXPECTED_LIFECYCLE_BLOCKERS: Final = [
    "delisting-announcement-match-ambiguous",
    "eligible-delisting-announcement-match-missing",
    "eligible-listing-announcement-match-missing",
    "historical-point-in-time-metadata-still-incomplete",
    "listing-announcement-match-ambiguous",
    "remaining-pre-archive-listing-evidence-missing",
]


class Gate2ReadinessV5Error(RuntimeError):
    """The consolidated owner-review evidence failed closed."""


@dataclass(frozen=True, slots=True)
class SourceSpec:
    schema_relative: str
    contract_key: str
    contract: str
    status: str
    expected_artifact_sha256: str | None = None


PRIOR_SPEC: Final = SourceSpec(
    schema_relative="schemas/evidence/v4/gate2-readiness-pack.schema.json",
    contract_key="evidence_schema",
    contract="grid.gate2-readiness-pack/v4",
    status="blocked-current-universe-evidence-awaiting-owner-policy",
)
FUNDING_POLICY_SPEC: Final = SourceSpec(
    schema_relative="schemas/evidence/v1/phase2-funding-cadence-policy-evidence.schema.json",
    contract_key="contract",
    contract="grid.phase2-funding-cadence-policy-evidence/v1",
    status="verified-official-funding-cadence-policy-consistency",
    expected_artifact_sha256=("665e44d36b71cc9e9f93a558a026ae38b1443a96fe2190873840ab84dc9b3408"),
)
LEGACY_SPEC: Final = SourceSpec(
    schema_relative="schemas/evidence/v1/phase2-legacy-listing-event-evidence.schema.json",
    contract_key="contract",
    contract="grid.phase2-legacy-listing-event-evidence/v1",
    status="verified-four-exact-and-one-bounded-legacy-listing-event",
    expected_artifact_sha256=("6a243bde1c5051151d22f90eb73af7692ae66bc381fa4a5bf43c484cc6cf7b24"),
)
LIFECYCLE_SPEC: Final = SourceSpec(
    schema_relative="schemas/evidence/v1/phase2-announcement-lifecycle-coverage.schema.json",
    contract_key="contract",
    contract="grid.phase2-announcement-lifecycle-coverage/v1",
    status="verified-partial-official-lifecycle-evidence",
    expected_artifact_sha256=("1d320e030f0aca19eb8455a5de90008b318e11e76269f7feee0af16850b37c06"),
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Gate2ReadinessV5Error(message)


def _mapping(parent: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise Gate2ReadinessV5Error(f"evidence field must be an object: {key}")
    return cast(dict[str, Any], value)


def _array(parent: Mapping[str, Any], key: str) -> list[Any]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise Gate2ReadinessV5Error(f"evidence field must be an array: {key}")
    return value


def _integer(parent: Mapping[str, Any], key: str, *, minimum: int = 0) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise Gate2ReadinessV5Error(f"evidence integer is invalid: {key}")
    return value


def _sha(parent: Mapping[str, Any], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise Gate2ReadinessV5Error(f"evidence SHA-256 is invalid: {key}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Gate2ReadinessV5Error(f"invalid JSON evidence: {path.name}") from error
    if not isinstance(value, dict):
        raise Gate2ReadinessV5Error(f"JSON evidence must be an object: {path.name}")
    return cast(dict[str, Any], value)


def _verify_generated_at(generated_at_utc: str) -> None:
    _require(generated_at_utc.endswith("Z"), "generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(generated_at_utc.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise Gate2ReadinessV5Error("generated_at_utc is invalid") from error
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
        raise Gate2ReadinessV5Error(f"cannot read source bytes: {path.name}") from error
    _require(
        artifact_bytes == canonical_json_bytes(payload) + b"\n",
        f"source is not canonical JSON plus LF: {path.name}",
    )
    schema = _load_json(repo_root / spec.schema_relative)
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    except Exception as error:
        raise Gate2ReadinessV5Error(f"source schema does not verify: {path.name}") from error
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
            f"source artifact differs from the accepted evidence: {path.name}",
        )
    return payload, {
        "artifact": resolved.name,
        "artifact_sha256": artifact_sha256,
        "content_sha256": cast(str, embedded),
        "contract": spec.contract,
        "status": spec.status,
    }


def _verify_prior(prior: Mapping[str, Any]) -> None:
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
            _require(isinstance(code, str), "prior Gate 2 blocker is not a string")
            blocker_codes.add(code)
    _require(sorted(blocker_codes) == EXPECTED_BLOCKERS, "prior Gate 2 blocker set changed")
    bindings = _mapping(prior, "bindings")
    _require(
        bindings.get("implementation_identity") == EXPECTED_V4_IMPLEMENTATION,
        "prior v4 implementation identity changed",
    )
    _require(
        _sha(bindings, "prior_readiness_artifact_sha256") == EXPECTED_V3_ARTIFACT_SHA256
        and _sha(bindings, "prior_readiness_content_sha256") == EXPECTED_V3_CONTENT_SHA256,
        "prior v4 binds another v3 decision",
    )
    owner_review = _mapping(_mapping(prior, "observations"), "owner_review")
    _require(
        owner_review
        == {
            "blocked_criterion_count": 3,
            "envelope_qualified": False,
            "owner_review_required": True,
            "unique_blocker_count": 7,
        },
        "prior v4 owner-review state changed",
    )


def _verify_policy(policy: Mapping[str, Any]) -> dict[str, int]:
    quality = _mapping(policy, "quality")
    observed = _integer(quality, "observed_interval_change_count", minimum=1)
    explained = _integer(quality, "explained_interval_change_count", minimum=1)
    _require(
        observed == explained == 11 and _integer(quality, "unexplained_interval_change_count") == 0,
        "funding cadence policy does not explain every observed change",
    )
    _require(
        _integer(quality, "affected_series_count", minimum=1)
        == _integer(quality, "policy_consistent_series_count", minimum=1)
        == 5,
        "funding cadence policy series accounting changed",
    )
    return {
        "affected_series_count": 5,
        "completed_hourly_episode_count": _integer(
            quality, "completed_hourly_episode_count", minimum=1
        ),
        "coverage_audit_count": _integer(quality, "coverage_audit_count", minimum=1),
        "explained_interval_change_count": explained,
        "open_hourly_episode_count": _integer(quality, "open_hourly_episode_count", minimum=1),
        "series_count": _integer(quality, "series_count", minimum=1),
        "unexplained_interval_change_count": 0,
    }


def _verify_lifecycle(
    lifecycle: Mapping[str, Any],
    legacy: Mapping[str, Any],
    *,
    legacy_record: Mapping[str, str],
) -> dict[str, Any]:
    _require(
        lifecycle.get("blocker_codes") == EXPECTED_LIFECYCLE_BLOCKERS,
        "lifecycle evidence blocker set changed",
    )
    archive_sources: dict[str, dict[str, Any]] = {}
    for raw_source in _array(lifecycle, "archive_sources"):
        _require(isinstance(raw_source, dict), "lifecycle archive source must be an object")
        source = cast(dict[str, Any], raw_source)
        announcement_type = source.get("announcement_type")
        _require(
            announcement_type in {"new_crypto", "delistings"},
            "lifecycle archive source type changed",
        )
        _require(
            cast(str, announcement_type) not in archive_sources,
            "lifecycle archive source type repeats",
        )
        archive_sources[cast(str, announcement_type)] = source
    _require(
        set(archive_sources) == {"new_crypto", "delistings"},
        "lifecycle archive sources are incomplete",
    )
    archive_listing_count = _integer(archive_sources["new_crypto"], "item_count", minimum=1)
    archive_delisting_count = _integer(archive_sources["delistings"], "item_count", minimum=1)
    _require(
        archive_listing_count == 1692 and archive_delisting_count == 460,
        "lifecycle archive totals changed",
    )
    lifecycle_bindings = _mapping(lifecycle, "bindings")
    legacy_bindings = _mapping(legacy, "bindings")
    _require(
        _sha(lifecycle_bindings, "instrument_registry_artifact_sha256")
        == _sha(legacy_bindings, "instrument_registry_artifact_sha256")
        and _sha(lifecycle_bindings, "instrument_registry_content_sha256")
        == _sha(legacy_bindings, "instrument_registry_content_sha256"),
        "lifecycle and legacy registry bindings differ",
    )
    lifecycle_legacy = _mapping(lifecycle, "legacy_evidence")
    lifecycle_legacy_source = _mapping(lifecycle_legacy, "source")
    _require(
        lifecycle_legacy_source
        == {
            "artifact": legacy_record["artifact"],
            "artifact_sha256": legacy_record["artifact_sha256"],
            "content_sha256": legacy_record["content_sha256"],
            "contract": legacy_record["contract"],
            "status": legacy_record["status"],
        },
        "lifecycle evidence binds another legacy artifact",
    )
    scope = _mapping(lifecycle, "scope")
    _require(
        _integer(scope, "campaign_request_count", minimum=1) == 3
        and _integer(scope, "selected_instrument_count", minimum=1) == 981,
        "lifecycle selected-universe scope changed",
    )
    matching = _mapping(lifecycle, "matching")
    _require(matching.get("record_matching_complete") is False, "partial lifecycle result changed")
    listing = _mapping(matching, "listing")
    delisting = _mapping(matching, "delisting")
    for label, item in (("listing", listing), ("delisting", delisting)):
        _require(
            _integer(item, "eligible_instrument_count", minimum=1)
            == _integer(item, "unique_match_instrument_count")
            + _integer(item, "unmatched_instrument_count")
            + _integer(item, "ambiguous_instrument_count"),
            f"{label} match accounting does not reconcile",
        )
    _require(
        _integer(listing, "eligible_instrument_count")
        + _integer(listing, "outside_archive_instrument_count")
        == _integer(scope, "selected_instrument_count"),
        "listing archive scope does not reconcile",
    )
    legacy_quality = _mapping(legacy, "quality")
    legacy_selected = _integer(legacy_quality, "selected_instrument_count", minimum=1)
    remaining_pre_archive = _integer(
        lifecycle_legacy, "remaining_pre_archive_listing_instrument_count"
    )
    _require(
        legacy_selected == _integer(lifecycle_legacy, "selected_instrument_count", minimum=1) == 5
        and remaining_pre_archive + legacy_selected
        == _integer(listing, "outside_archive_instrument_count"),
        "legacy/pre-archive lifecycle accounting changed",
    )
    process = _mapping(lifecycle, "process")
    _require(
        process.get("announcement_text_persisted") is False
        and _integer(process, "market_data_request_count") == 0
        and _integer(process, "private_endpoint_request_count") == 0
        and _integer(process, "response_count", minimum=1) == 108
        and _integer(process, "transport_max_attempts", minimum=1) == 1,
        "lifecycle process assurance changed",
    )
    return {
        "archive_delisting_count": archive_delisting_count,
        "archive_listing_count": archive_listing_count,
        "delisting_ambiguous_instrument_count": _integer(delisting, "ambiguous_instrument_count"),
        "delisting_unique_match_instrument_count": _integer(
            delisting, "unique_match_instrument_count"
        ),
        "delisting_unmatched_instrument_count": _integer(delisting, "unmatched_instrument_count"),
        "listing_ambiguous_instrument_count": _integer(listing, "ambiguous_instrument_count"),
        "listing_unique_match_instrument_count": _integer(listing, "unique_match_instrument_count"),
        "listing_unmatched_instrument_count": _integer(listing, "unmatched_instrument_count"),
        "record_matching_complete": False,
        "remaining_pre_archive_listing_instrument_count": remaining_pre_archive,
        "selected_instrument_count": 981,
    }


def _legacy_observation(legacy: Mapping[str, Any]) -> dict[str, int]:
    quality = _mapping(legacy, "quality")
    trade = _mapping(quality, "trade_first_candle")
    return {
        "official_document_count": _integer(quality, "official_document_count", minimum=1),
        "official_document_selected_match_count": _integer(
            quality, "official_document_selected_match_count", minimum=1
        ),
        "selected_instrument_count": _integer(quality, "selected_instrument_count", minimum=1),
        "trade_event_day_match_count": _integer(trade, "event_day_match_count", minimum=1),
        "trade_first_candle_before_event_day_count": _integer(
            trade, "first_candle_before_event_day_count", minimum=1
        ),
    }


def _current_universe_observation(prior: Mapping[str, Any]) -> dict[str, int | bool]:
    observations = _mapping(prior, "observations")
    candles = _mapping(observations, "current_universe_candles")
    funding = _mapping(observations, "current_universe_funding")
    performance = _mapping(observations, "current_universe_catalog_performance")
    return {
        "candle_catalog_dataset_count": _integer(candles, "catalog_dataset_count", minimum=1),
        "candle_instrument_count": _integer(candles, "instrument_count", minimum=1),
        "candle_missing_minute_count": _integer(candles, "missing_minute_count"),
        "catalog_deterministic_repeat_equal": (
            performance.get("deterministic_repeat_equal") is True
        ),
        "catalog_first_pass_rows_per_second": _integer(
            performance, "first_pass_rows_per_second", minimum=1
        ),
        "catalog_repeat_pass_rows_per_second": _integer(
            performance, "repeat_pass_rows_per_second", minimum=1
        ),
        "funding_canonical_dataset_count": _integer(funding, "canonical_dataset_count", minimum=1),
        "funding_interval_change_count": _integer(funding, "interval_change_count"),
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


def build_gate2_readiness_pack_v5(
    *,
    implementation_identity: str,
    generated_at_utc: str,
    prior_readiness_path: Path,
    funding_policy_path: Path,
    legacy_listing_path: Path,
    lifecycle_coverage_path: Path,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Build a non-promoting owner-review pack over v4 and later policy evidence."""

    _require(
        SOFTWARE_IDENTITY_RE.fullmatch(implementation_identity) is not None,
        "implementation identity must be git:<40 lowercase hex>",
    )
    _verify_generated_at(generated_at_utc)
    root = repo_root.resolve()
    _require(root.is_dir() and not repo_root.is_symlink(), "repository root is unsafe")
    prior, prior_record = _verify_source(prior_readiness_path, PRIOR_SPEC, root)
    policy, policy_record = _verify_source(funding_policy_path, FUNDING_POLICY_SPEC, root)
    legacy, legacy_record = _verify_source(legacy_listing_path, LEGACY_SPEC, root)
    lifecycle, lifecycle_record = _verify_source(lifecycle_coverage_path, LIFECYCLE_SPEC, root)
    _verify_prior(prior)
    policy_observation = _verify_policy(policy)
    lifecycle_observation = _verify_lifecycle(
        lifecycle,
        legacy,
        legacy_record=legacy_record,
    )
    records = {
        "funding-cadence-policy": policy_record,
        "legacy-listing-events": legacy_record,
        "official-lifecycle-coverage": lifecycle_record,
        "prior-readiness-v4": prior_record,
    }
    payload: dict[str, Any] = {
        "assurances": {
            "all_source_content_hashes_verified": True,
            "all_source_receipts_verified": True,
            "all_source_schemas_verified": True,
            "automatic_gate_acceptance_performed": False,
            "cross_source_bindings_verified": True,
            "current_universe_v4_verified": True,
            "market_data_or_policy_network_request_performed": False,
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
        "criteria": prior["criteria"],
        "criteria_source": prior["criteria_source"],
        "evidence_schema": EVIDENCE_CONTRACT,
        "gate_2": EXPECTED_GATE,
        "generated_at_utc": generated_at_utc,
        "observations": {
            "current_universe": _current_universe_observation(prior),
            "funding_cadence_policy": policy_observation,
            "legacy_listing_events": _legacy_observation(legacy),
            "official_lifecycle_coverage": lifecycle_observation,
            "owner_review": {
                "blocked_criterion_count": 3,
                "blocker_removal_performed": False,
                "funding_cadence_owner_disposition": "pending",
                "lifecycle_owner_disposition": "pending",
                "owner_decision_required": True,
                "performance_envelope_qualified": False,
                "unique_blocker_count": 7,
            },
        },
        "readiness_counts": prior["readiness_counts"],
        "sources": records,
        "status": "blocked-consolidated-evidence-awaiting-owner-decision",
        "storage_policy": prior["storage_policy"],
    }
    payload["content_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    schema = _load_json(root / "schemas/evidence/v5/gate2-readiness-pack.schema.json")
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    except Exception as error:
        raise Gate2ReadinessV5Error("Gate 2 readiness pack v5 does not match its schema") from error
    return payload


def publish_gate2_readiness_pack_v5(
    *,
    implementation_identity: str,
    prior_readiness_path: Path,
    funding_policy_path: Path,
    legacy_listing_path: Path,
    lifecycle_coverage_path: Path,
    output: Path,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Atomically publish the non-promoting owner-review pack."""

    output, _receipt = preflight_evidence(output)
    payload = build_gate2_readiness_pack_v5(
        implementation_identity=implementation_identity,
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        prior_readiness_path=prior_readiness_path,
        funding_policy_path=funding_policy_path,
        legacy_listing_path=legacy_listing_path,
        lifecycle_coverage_path=lifecycle_coverage_path,
        repo_root=repo_root,
    )
    publish_evidence(output, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation-identity", required=True)
    parser.add_argument("--prior-readiness-v4", type=Path, required=True)
    parser.add_argument("--funding-cadence-policy", type=Path, required=True)
    parser.add_argument("--legacy-listing-evidence", type=Path, required=True)
    parser.add_argument("--lifecycle-coverage", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = publish_gate2_readiness_pack_v5(
        implementation_identity=args.implementation_identity,
        prior_readiness_path=args.prior_readiness_v4,
        funding_policy_path=args.funding_cadence_policy,
        legacy_listing_path=args.legacy_listing_evidence,
        lifecycle_coverage_path=args.lifecycle_coverage,
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
