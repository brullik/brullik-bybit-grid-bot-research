"""Build one receipt-linked current-universe candle evidence projection."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file
from grid_data.evidence import preflight_evidence, publish_evidence, verify_evidence
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

ROOT: Final = Path(__file__).resolve().parents[1]
EVIDENCE_CONTRACT: Final = "grid.phase2-current-universe-candle-evidence/v1"
LANDING_CONTRACT: Final = "grid.phase2-public-history-campaign/v1"
PUBLICATION_CONTRACT: Final = "grid.phase2-history-campaign-publication/v1"
COVERAGE_CONTRACT: Final = "grid.history-campaign-coverage-audit/v1"
CATALOG_BUNDLE_CONTRACT: Final = "grid.phase2-catalog-selection-bundle/v1"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
CANDLE_KINDS: Final = ("trade", "mark")
REASON_CODES: Final = (
    "canonical_representation_overflow",
    "canonical_source_mismatch",
    "duplicate_canonical_key",
    "internal_interval_mismatch",
    "predecessor_interval_mismatch",
    "quarantined_source_row",
    "registry_lifecycle_failure",
    "rest_returned_no_data",
    "source_window_returned_no_event",
    "unexpected_settlement_timestamp",
    "unrequested_instrument_row",
    "unexplained_interval_change",
)


class CurrentUniverseCandleEvidenceError(RuntimeError):
    """The offline current-universe evidence projection failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CurrentUniverseCandleEvidenceError(message)


def _mapping(parent: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise CurrentUniverseCandleEvidenceError(f"evidence field must be an object: {key}")
    return cast(dict[str, Any], value)


def _array(parent: Mapping[str, Any], key: str) -> list[Any]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise CurrentUniverseCandleEvidenceError(f"evidence field must be an array: {key}")
    return value


def _integer(parent: Mapping[str, Any], key: str, *, minimum: int = 0) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CurrentUniverseCandleEvidenceError(f"evidence integer is invalid: {key}")
    return value


def _sha(parent: Mapping[str, Any], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise CurrentUniverseCandleEvidenceError(f"evidence SHA-256 is invalid: {key}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CurrentUniverseCandleEvidenceError(f"invalid JSON evidence: {path.name}") from error
    if not isinstance(value, dict):
        raise CurrentUniverseCandleEvidenceError(f"JSON must be an object: {path.name}")
    return cast(dict[str, Any], value)


def _load_verified_evidence(
    path: Path,
    *,
    schema_name: str,
    contract_key: str,
    contract: str,
    statuses: set[str],
) -> dict[str, Any]:
    supplied = path.resolve()
    _require(verify_evidence(supplied), f"evidence receipt does not verify: {supplied.name}")
    payload = _load_json(supplied)
    try:
        artifact_bytes = supplied.read_bytes()
    except OSError as error:
        raise CurrentUniverseCandleEvidenceError(
            f"cannot read evidence bytes: {supplied.name}"
        ) from error
    _require(
        artifact_bytes == canonical_json_bytes(payload) + b"\n",
        f"evidence is not canonical JSON plus LF: {supplied.name}",
    )
    _require(payload.get(contract_key) == contract, f"evidence contract differs: {supplied.name}")
    _require(payload.get("status") in statuses, f"evidence status differs: {supplied.name}")
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256", None)
    _require(
        embedded_hash == canonical_sha256(hash_input),
        f"evidence content hash does not verify: {supplied.name}",
    )
    schema = _load_json(ROOT / "schemas/evidence/v1" / schema_name)
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    except Exception as error:
        raise CurrentUniverseCandleEvidenceError(
            f"evidence schema does not verify: {supplied.name}"
        ) from error
    return payload


def _verify_generated_at(value: str) -> None:
    _require(value.endswith("Z"), "generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise CurrentUniverseCandleEvidenceError("generated_at_utc is invalid") from error
    offset = parsed.utcoffset()
    _require(
        offset is not None and offset.total_seconds() == 0,
        "generated_at_utc must be UTC",
    )


def _kind_map(parent: Mapping[str, Any], key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in _array(parent, key):
        _require(isinstance(raw, dict), f"{key} item must be an object")
        item = cast(dict[str, Any], raw)
        kind = item.get("kind")
        _require(kind in {"trade", "mark", "funding"}, f"{key} kind is invalid")
        _require(kind not in result, f"{key} repeats kind: {kind}")
        result[cast(str, kind)] = item
    return result


def _source_chain_binding(
    landing: Mapping[str, Any], publication: Mapping[str, Any]
) -> dict[str, str]:
    landing_bindings = _mapping(landing, "bindings")
    publication_bindings = _mapping(publication, "bindings")
    return {
        "campaign_manifest_sha256": _sha(landing_bindings, "campaign_manifest_sha256"),
        "campaign_plan_sha256": _sha(landing_bindings, "campaign_plan_sha256"),
        "publication_manifest_sha256": _sha(publication_bindings, "publication_manifest_sha256"),
        "publication_plan_sha256": _sha(publication_bindings, "publication_plan_sha256"),
    }


def _verify_source_triplet(
    landing: Mapping[str, Any],
    publication: Mapping[str, Any],
    coverage: Mapping[str, Any],
) -> None:
    landing_bindings = _mapping(landing, "bindings")
    publication_bindings = _mapping(publication, "bindings")
    coverage_bindings = _mapping(coverage, "bindings")
    for key in ("capacity_evidence_sha256", "instrument_registry_sha256"):
        _require(
            landing_bindings.get(key)
            == publication_bindings.get(key)
            == coverage_bindings.get(key),
            f"source triplet binding mismatch: {key}",
        )
    for source_name, publication_name in (
        ("campaign_manifest_sha256", "source_campaign_manifest_sha256"),
        ("campaign_plan_sha256", "source_campaign_plan_sha256"),
    ):
        _require(
            landing_bindings.get(source_name)
            == publication_bindings.get(publication_name)
            == coverage_bindings.get(publication_name),
            f"source triplet binding mismatch: {source_name}",
        )
    _require(
        landing_bindings.get("campaign_request_sha256")
        == publication_bindings.get("source_campaign_request_sha256"),
        "source triplet request binding mismatch",
    )
    for key in ("publication_manifest_sha256", "publication_plan_sha256"):
        _require(
            publication_bindings.get(key) == coverage_bindings.get(key),
            f"publication/coverage binding mismatch: {key}",
        )
    _require(
        _mapping(publication, "process").get("publisher_software_identity")
        == coverage_bindings.get("publisher_software_identity"),
        "publication/coverage publisher identity mismatch",
    )
    _require(
        _mapping(landing, "scope") == _mapping(publication, "scope"),
        "landing/publication scope mismatch",
    )


def _empty_kind_totals(kind: str) -> dict[str, int | str]:
    return {
        "canonical_dataset_count": 0,
        "canonical_file_count": 0,
        "canonical_parquet_bytes": 0,
        "canonical_row_count": 0,
        "catalog_dataset_count": 0,
        "catalog_object_count": 0,
        "catalog_row_count": 0,
        "catalog_selection_count": 0,
        "catalog_size_bytes": 0,
        "coverage_blocked_count": 0,
        "coverage_passed_count": 0,
        "kind": kind,
        "landing_http_request_count": 0,
        "landing_job_count": 0,
        "landing_page_count": 0,
        "landing_row_count": 0,
    }


def build_current_universe_candle_evidence(
    *,
    landing_evidence_paths: Sequence[Path],
    publication_evidence_paths: Sequence[Path],
    coverage_evidence_paths: Sequence[Path],
    catalog_bundle_evidence_path: Path,
    generated_at_utc: str,
    software_identity: str,
) -> dict[str, Any]:
    """Verify ordered public source triplets and aggregate their candle-only catalog scope."""

    _verify_generated_at(generated_at_utc)
    _require(
        SOFTWARE_IDENTITY_RE.fullmatch(software_identity) is not None,
        "software identity must be an immutable Git SHA",
    )
    source_count = len(landing_evidence_paths)
    _require(1 <= source_count <= 16, "source count must be between 1 and 16")
    _require(
        len(publication_evidence_paths) == source_count
        and len(coverage_evidence_paths) == source_count,
        "landing/publication/coverage evidence counts must match",
    )

    catalog_bundle = _load_verified_evidence(
        catalog_bundle_evidence_path,
        schema_name="phase2-catalog-selection-bundle.schema.json",
        contract_key="evidence_schema",
        contract=CATALOG_BUNDLE_CONTRACT,
        statuses={"verified-catalog-selection-bundle"},
    )
    source_rows: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    source_artifact_bindings: list[dict[str, str]] = []
    source_chain_bindings: list[dict[str, str]] = []
    seen_campaign_plans: set[str] = set()
    capacity_hash: str | None = None
    registry_hash: str | None = None
    for landing_path, publication_path, coverage_path in zip(
        landing_evidence_paths,
        publication_evidence_paths,
        coverage_evidence_paths,
        strict=True,
    ):
        landing = _load_verified_evidence(
            landing_path,
            schema_name="phase2-public-history-campaign.schema.json",
            contract_key="evidence_schema",
            contract=LANDING_CONTRACT,
            statuses={"verified-public-landing-campaign"},
        )
        publication = _load_verified_evidence(
            publication_path,
            schema_name="phase2-history-campaign-publication.schema.json",
            contract_key="evidence_schema",
            contract=PUBLICATION_CONTRACT,
            statuses={"verified-canonical-history-campaign-publication"},
        )
        coverage = _load_verified_evidence(
            coverage_path,
            schema_name="history-campaign-coverage-audit.schema.json",
            contract_key="contract",
            contract=COVERAGE_CONTRACT,
            statuses={"passed", "blocked"},
        )
        _verify_source_triplet(landing, publication, coverage)
        bindings = _mapping(landing, "bindings")
        current_capacity = _sha(bindings, "capacity_evidence_sha256")
        current_registry = _sha(bindings, "instrument_registry_sha256")
        capacity_hash = current_capacity if capacity_hash is None else capacity_hash
        registry_hash = current_registry if registry_hash is None else registry_hash
        _require(current_capacity == capacity_hash, "sources use different capacity evidence")
        _require(current_registry == registry_hash, "sources use different instrument registries")
        campaign_plan = _sha(bindings, "campaign_plan_sha256")
        _require(campaign_plan not in seen_campaign_plans, "source campaign is repeated")
        seen_campaign_plans.add(campaign_plan)
        source_rows.append((landing, publication, coverage))
        source_chain_bindings.append(_source_chain_binding(landing, publication))
        source_artifact_bindings.append(
            {
                "coverage_artifact_sha256": sha256_file(coverage_path),
                "landing_artifact_sha256": sha256_file(landing_path),
                "publication_artifact_sha256": sha256_file(publication_path),
            }
        )

    catalog_bindings = _mapping(catalog_bundle, "bindings")
    _require(
        catalog_bindings.get("source_chain_sha256") == canonical_sha256(source_chain_bindings),
        "catalog bundle source chain does not match ordered public evidence",
    )
    catalog_inventory = _mapping(catalog_bundle, "inventory")
    _require(
        _integer(catalog_inventory, "source_count", minimum=1) == source_count,
        "catalog bundle source count differs",
    )

    by_kind = {kind: _empty_kind_totals(kind) for kind in CANDLE_KINDS}
    reason_counts = {reason: 0 for reason in REASON_CODES}
    candle_quality = {
        "conflicting_key_count": 0,
        "duplicate_key_count": 0,
        "expected_minute_count": 0,
        "gap_range_count": 0,
        "lifecycle_failure_count": 0,
        "missing_minute_count": 0,
        "observed_row_count": 0,
        "unexpected_timestamp_count": 0,
        "unrequested_row_count": 0,
    }
    quarantine_count = 0
    representation_exclusion_count = 0
    coverage_status = "passed"
    acquisition_starts: list[int] = []
    acquisition_completions: list[int] = []
    acquisition_elapsed = 0
    acquisition_child_elapsed = 0
    publication_starts: list[int] = []
    publication_completions: list[int] = []
    publication_elapsed = 0
    excluded_funding = {
        "canonical_dataset_count": 0,
        "canonical_row_count": 0,
        "landing_job_count": 0,
        "landing_row_count": 0,
    }

    for landing, publication, coverage in source_rows:
        landing_summary = _mapping(landing, "landing")
        landing_kinds = _kind_map(landing_summary, "by_kind")
        publication_summary = _mapping(publication, "canonical")
        publication_kinds = _kind_map(publication_summary, "by_kind")
        coverage_inventory = _mapping(coverage, "inventory")
        coverage_kinds = _kind_map(coverage_inventory, "by_kind")
        for aggregate_field, child_field in (
            ("job_count", "job_count"),
            ("page_count", "page_count"),
            ("http_request_count", "http_request_count"),
            ("row_count", "row_count"),
        ):
            _require(
                _integer(landing_summary, aggregate_field, minimum=1)
                == sum(_integer(item, child_field) for item in landing_kinds.values()),
                f"landing by-kind total differs: {aggregate_field}",
            )
        for aggregate_field, child_field in (
            ("dataset_count", "dataset_count"),
            ("file_count", "file_count"),
            ("parquet_bytes", "parquet_bytes"),
            ("row_count", "row_count"),
        ):
            _require(
                _integer(publication_summary, aggregate_field, minimum=1)
                == sum(_integer(item, child_field) for item in publication_kinds.values()),
                f"publication by-kind total differs: {aggregate_field}",
            )
        for aggregate_field, child_field in (
            ("dataset_count", "dataset_count"),
            ("blocked_count", "blocked_count"),
            ("passed_count", "passed_count"),
            ("row_count", "row_count"),
        ):
            _require(
                _integer(coverage_inventory, aggregate_field)
                == sum(_integer(item, child_field) for item in coverage_kinds.values()),
                f"coverage by-kind total differs: {aggregate_field}",
            )
        for kind in CANDLE_KINDS:
            _require(
                kind in landing_kinds and kind in publication_kinds and kind in coverage_kinds,
                f"source triplet is missing candle kind: {kind}",
            )
            landing_kind = landing_kinds[kind]
            publication_kind = publication_kinds[kind]
            coverage_kind = coverage_kinds[kind]
            _require(
                _integer(publication_kind, "dataset_count", minimum=1)
                == _integer(coverage_kind, "dataset_count", minimum=1),
                f"publication/coverage dataset count mismatch: {kind}",
            )
            _require(
                _integer(publication_kind, "row_count") == _integer(coverage_kind, "row_count"),
                f"publication/coverage row count mismatch: {kind}",
            )
            _require(
                _integer(coverage_kind, "blocked_count") + _integer(coverage_kind, "passed_count")
                == _integer(coverage_kind, "dataset_count", minimum=1),
                f"coverage status counts do not reconcile: {kind}",
            )
            target = by_kind[kind]
            target["landing_job_count"] = cast(int, target["landing_job_count"]) + _integer(
                landing_kind, "job_count", minimum=1
            )
            target["landing_page_count"] = cast(int, target["landing_page_count"]) + _integer(
                landing_kind, "page_count", minimum=1
            )
            target["landing_http_request_count"] = cast(
                int, target["landing_http_request_count"]
            ) + _integer(landing_kind, "http_request_count", minimum=1)
            target["landing_row_count"] = cast(int, target["landing_row_count"]) + _integer(
                landing_kind, "row_count"
            )
            target["canonical_dataset_count"] = cast(
                int, target["canonical_dataset_count"]
            ) + _integer(publication_kind, "dataset_count", minimum=1)
            target["canonical_file_count"] = cast(int, target["canonical_file_count"]) + _integer(
                publication_kind, "file_count", minimum=1
            )
            target["canonical_parquet_bytes"] = cast(
                int, target["canonical_parquet_bytes"]
            ) + _integer(publication_kind, "parquet_bytes", minimum=1)
            target["canonical_row_count"] = cast(int, target["canonical_row_count"]) + _integer(
                publication_kind, "row_count"
            )
            target["coverage_blocked_count"] = cast(
                int, target["coverage_blocked_count"]
            ) + _integer(coverage_kind, "blocked_count")
            target["coverage_passed_count"] = cast(int, target["coverage_passed_count"]) + _integer(
                coverage_kind, "passed_count"
            )

        candle_landing_rows = sum(
            _integer(landing_kinds[kind], "row_count") for kind in CANDLE_KINDS
        )
        candle_canonical_rows = sum(
            _integer(publication_kinds[kind], "row_count") for kind in CANDLE_KINDS
        )
        source_quality = landing.get("source_quality")
        if source_quality is not None:
            _require(isinstance(source_quality, dict), "landing source_quality must be an object")
            typed_quality = cast(dict[str, Any], source_quality)
            _require(
                _integer(typed_quality, "admitted_candle_row_count") == candle_landing_rows,
                "landing quarantine admission count differs from candle rows",
            )
            current_quarantine = _integer(typed_quality, "quarantined_row_count")
            _require(
                _integer(typed_quality, "source_candle_row_count")
                == candle_landing_rows + current_quarantine,
                "landing source/quarantine row counts do not reconcile",
            )
            quarantine_reasons = _mapping(typed_quality, "reason_counts")
            _require(
                sum(_integer(quarantine_reasons, key) for key in quarantine_reasons)
                == current_quarantine,
                "landing quarantine reasons do not reconcile",
            )
            quarantine_count += current_quarantine
        admission = publication_summary.get("admission")
        if admission is None:
            _require(
                candle_landing_rows == candle_canonical_rows,
                "canonical row reduction lacks representation admission evidence",
            )
        else:
            _require(isinstance(admission, dict), "canonical admission must be an object")
            typed_admission = cast(dict[str, Any], admission)
            _require(
                _integer(typed_admission, "source_row_count") == candle_landing_rows
                and _integer(typed_admission, "admitted_row_count") == candle_canonical_rows,
                "canonical representation admission does not reconcile candle rows",
            )
            excluded = _integer(typed_admission, "excluded_row_count", minimum=1)
            _require(
                candle_landing_rows - candle_canonical_rows == excluded,
                "canonical representation exclusion count differs",
            )
            admission_reasons = _mapping(typed_admission, "reason_counts")
            _require(
                sum(_integer(admission_reasons, key) for key in admission_reasons) == excluded,
                "canonical representation reasons do not reconcile",
            )
            representation_exclusion_count += excluded

        coverage_quality = _mapping(_mapping(coverage, "quality"), "candle")
        _require(
            _integer(coverage_quality, "observed_row_count") == candle_canonical_rows,
            "coverage observed row count differs from canonical candle rows",
        )
        for key in candle_quality:
            candle_quality[key] += _integer(coverage_quality, key)
        reason_policy = _mapping(coverage, "reason_policy")
        _require(not _array(reason_policy, "accepted_reason_codes"), "coverage accepts a reason")
        _require(
            _integer(reason_policy, "unknown_reason_count") == 0, "coverage has unknown reasons"
        )
        observed_reasons = _mapping(reason_policy, "observed_reason_counts")
        _require(
            set(_array(reason_policy, "unaccepted_reason_codes")) == set(observed_reasons),
            "coverage unaccepted reasons do not match observations",
        )
        for key, value in observed_reasons.items():
            _require(key in reason_counts, f"coverage reason is unknown: {key}")
            _require(
                isinstance(value, int) and not isinstance(value, bool) and value > 0,
                "coverage reason count is invalid",
            )
            reason_counts[key] += value
        if coverage.get("status") == "blocked":
            coverage_status = "blocked"

        landing_timing = _mapping(landing, "timing")
        landing_start = _integer(landing_timing, "campaign_started_at_ms")
        landing_complete = _integer(landing_timing, "campaign_completed_at_ms")
        landing_elapsed = _integer(landing_timing, "campaign_elapsed_ms")
        _require(
            landing_complete - landing_start == landing_elapsed, "landing timing does not reconcile"
        )
        _require(
            _integer(landing_timing, "timed_child_count", minimum=1)
            == _integer(landing_summary, "job_count", minimum=1),
            "landing timing does not cover every child",
        )
        acquisition_starts.append(landing_start)
        acquisition_completions.append(landing_complete)
        acquisition_elapsed += landing_elapsed
        acquisition_child_elapsed += _integer(landing_timing, "summed_child_elapsed_ms")

        publication_timing = publication.get("timing")
        if publication_timing is not None:
            _require(isinstance(publication_timing, dict), "publication timing must be an object")
            typed_timing = cast(dict[str, Any], publication_timing)
            started = _integer(typed_timing, "started_at_ms")
            completed = _integer(typed_timing, "completed_at_ms")
            elapsed = _integer(typed_timing, "elapsed_ms")
            _require(completed - started == elapsed, "publication timing does not reconcile")
            publication_starts.append(started)
            publication_completions.append(completed)
            publication_elapsed += elapsed

        if "funding" in landing_kinds:
            excluded_funding["landing_job_count"] += _integer(
                landing_kinds["funding"], "job_count", minimum=1
            )
            excluded_funding["landing_row_count"] += _integer(landing_kinds["funding"], "row_count")
        if "funding" in publication_kinds:
            excluded_funding["canonical_dataset_count"] += _integer(
                publication_kinds["funding"], "dataset_count", minimum=1
            )
            excluded_funding["canonical_row_count"] += _integer(
                publication_kinds["funding"], "row_count"
            )

    catalog_kind_map = _kind_map(catalog_inventory, "by_kind")
    for kind in CANDLE_KINDS:
        _require(kind in catalog_kind_map, f"catalog bundle is missing kind: {kind}")
        catalog_kind = catalog_kind_map[kind]
        target = by_kind[kind]
        for catalog_field, canonical_field in (
            ("dataset_count", "canonical_dataset_count"),
            ("object_count", "canonical_file_count"),
            ("row_count", "canonical_row_count"),
            ("size_bytes", "canonical_parquet_bytes"),
        ):
            value = _integer(
                catalog_kind, catalog_field, minimum=1 if catalog_field != "row_count" else 0
            )
            _require(
                value == target[canonical_field],
                f"catalog/canonical mismatch: {kind} {catalog_field}",
            )
            target[f"catalog_{catalog_field}"] = value
        target["catalog_selection_count"] = _integer(catalog_kind, "selection_count", minimum=1)

    aggregate_catalog_dataset_count = sum(
        cast(int, by_kind[kind]["catalog_dataset_count"]) for kind in CANDLE_KINDS
    )
    aggregate_catalog_object_count = sum(
        cast(int, by_kind[kind]["catalog_object_count"]) for kind in CANDLE_KINDS
    )
    aggregate_catalog_rows = sum(
        cast(int, by_kind[kind]["catalog_row_count"]) for kind in CANDLE_KINDS
    )
    aggregate_catalog_bytes = sum(
        cast(int, by_kind[kind]["catalog_size_bytes"]) for kind in CANDLE_KINDS
    )
    for key, expected in (
        ("dataset_count", aggregate_catalog_dataset_count),
        ("object_count", aggregate_catalog_object_count),
        ("row_count", aggregate_catalog_rows),
        ("size_bytes", aggregate_catalog_bytes),
    ):
        _require(_integer(catalog_inventory, key) == expected, f"catalog aggregate differs: {key}")
    _require(
        _integer(catalog_inventory, "selection_count", minimum=1)
        == sum(cast(int, by_kind[kind]["catalog_selection_count"]) for kind in CANDLE_KINDS),
        "catalog aggregate differs: selection_count",
    )
    _require(
        _integer(catalog_inventory, "empty_object_count") <= aggregate_catalog_object_count,
        "catalog empty-object count exceeds object count",
    )

    timed_publication_count = len(publication_starts)
    payload: dict[str, Any] = {
        "assurances": {
            "all_source_content_hashes_verified": True,
            "all_source_receipts_verified": True,
            "all_source_schemas_verified": True,
            "automatic_gate_acceptance_performed": False,
            "catalog_inventory_reconciled": True,
            "catalog_source_chain_reconciled": True,
            "cross_source_bindings_verified": True,
            "market_store_read": False,
            "network_request_performed": False,
            "phase3_authorized": False,
            "private_or_live_capability_used": False,
        },
        "bindings": {
            "capacity_evidence_sha256": capacity_hash,
            "catalog_bundle_artifact_sha256": sha256_file(catalog_bundle_evidence_path),
            "catalog_bundle_content_sha256": _sha(catalog_bundle, "content_sha256"),
            "evidence_builder_software_identity": software_identity,
            "instrument_registry_sha256": registry_hash,
            "source_evidence_chain_sha256": canonical_sha256(source_artifact_bindings),
        },
        "catalog": dict(_mapping(catalog_bundle, "catalog")),
        "evidence_schema": EVIDENCE_CONTRACT,
        "excluded_funding": excluded_funding,
        "generated_at_utc": generated_at_utc,
        "inventory": {
            "by_kind": [by_kind[kind] for kind in CANDLE_KINDS],
            "empty_object_count": _integer(catalog_inventory, "empty_object_count"),
            "instrument_count": _integer(catalog_inventory, "instrument_count", minimum=1),
            "selection_count": _integer(catalog_inventory, "selection_count", minimum=1),
            "source_count": source_count,
        },
        "limitations": [
            "The pack verifies current-universe candle evidence but does not accept missing "
            "history or lifecycle reasons.",
            "Funding rows are reported as excluded and remain governed by separate chronology "
            "and cadence evidence.",
            "Legacy publication sources without receipt-bound start checkpoints remain valid "
            "but do not contribute publication elapsed time.",
            "Measured timings are not an owner-reviewed end-to-end performance envelope.",
            "This evidence does not close Gate 2, authorize Phase 3, promote research data, "
            "or enable live execution.",
        ],
        "performance": {
            "acquisition": {
                "campaign_count": source_count,
                "earliest_started_at_ms": min(acquisition_starts),
                "latest_completed_at_ms": max(acquisition_completions),
                "observed_wall_span_ms": max(acquisition_completions) - min(acquisition_starts),
                "summed_campaign_elapsed_ms": acquisition_elapsed,
                "summed_child_elapsed_ms": acquisition_child_elapsed,
            },
            "envelope": {
                "owner_review_required": True,
                "qualified": False,
            },
            "publication": {
                "complete_source_timing": timed_publication_count == source_count,
                "earliest_started_at_ms": min(publication_starts) if publication_starts else None,
                "latest_completed_at_ms": max(publication_completions)
                if publication_completions
                else None,
                "source_count": source_count,
                "summed_elapsed_ms": publication_elapsed,
                "timed_source_count": timed_publication_count,
            },
        },
        "quality": {
            "accepted_reason_count": 0,
            "candle": candle_quality,
            "canonical_representation_excluded_row_count": representation_exclusion_count,
            "coverage_status": coverage_status,
            "quarantined_source_row_count": quarantine_count,
            "reason_counts": reason_counts,
        },
        "status": "verified-current-universe-candle-evidence",
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
    schema = _load_json(
        ROOT / "schemas/evidence/v1/phase2-current-universe-candle-evidence.schema.json"
    )
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    except Exception as error:
        raise CurrentUniverseCandleEvidenceError(
            "output evidence schema does not verify"
        ) from error
    return payload


def publish_current_universe_candle_evidence(
    *,
    landing_evidence_paths: Sequence[Path],
    publication_evidence_paths: Sequence[Path],
    coverage_evidence_paths: Sequence[Path],
    catalog_bundle_evidence_path: Path,
    generated_at_utc: str,
    software_identity: str,
    output: Path,
) -> dict[str, Any]:
    target, _receipt = preflight_evidence(output)
    payload = build_current_universe_candle_evidence(
        landing_evidence_paths=landing_evidence_paths,
        publication_evidence_paths=publication_evidence_paths,
        coverage_evidence_paths=coverage_evidence_paths,
        catalog_bundle_evidence_path=catalog_bundle_evidence_path,
        generated_at_utc=generated_at_utc,
        software_identity=software_identity,
    )
    publish_evidence(target, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--landing-evidence", action="append", type=Path, required=True)
    parser.add_argument("--publication-evidence", action="append", type=Path, required=True)
    parser.add_argument("--coverage-evidence", action="append", type=Path, required=True)
    parser.add_argument("--catalog-bundle-evidence", type=Path, required=True)
    parser.add_argument("--software-identity", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = publish_current_universe_candle_evidence(
        landing_evidence_paths=args.landing_evidence,
        publication_evidence_paths=args.publication_evidence,
        coverage_evidence_paths=args.coverage_evidence,
        catalog_bundle_evidence_path=args.catalog_bundle_evidence,
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        software_identity=args.software_identity,
        output=args.output,
    )
    print(
        json.dumps(
            {
                "coverage_status": payload["quality"]["coverage_status"],
                "source_count": payload["inventory"]["source_count"],
                "status": payload["status"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
