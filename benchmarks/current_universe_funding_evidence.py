"""Build a receipt-linked current-universe funding evidence projection."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Final, cast

from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file
from grid_data.evidence import preflight_evidence, publish_evidence, verify_evidence
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

ROOT: Final = Path(__file__).resolve().parents[1]
REQUEST_CONTRACT: Final = "grid.current-universe-funding-evidence-request/v1"
EVIDENCE_CONTRACT: Final = "grid.phase2-current-universe-funding-evidence/v1"
CANDLE_BUNDLE_REQUEST_CONTRACT: Final = "grid.canonical-catalog-selection-bundle-request/v1"
CANDLE_BUNDLE_CONTRACT: Final = "grid.phase2-catalog-selection-bundle/v1"
CANDLE_EVIDENCE_CONTRACT: Final = "grid.phase2-current-universe-candle-evidence/v1"
CAMPAIGN_REQUEST_CONTRACT: Final = "grid.public-history-campaign-request/v1"
BOUNDARY_REQUEST_CONTRACT: Final = "grid.bybit-funding-source-boundary-request/v1"
BOUNDARY_EVIDENCE_CONTRACT: Final = "grid.phase2-funding-source-boundary/v1"
LANDING_CONTRACT: Final = "grid.phase2-public-history-campaign/v1"
PUBLICATION_CONTRACT: Final = "grid.phase2-history-campaign-publication/v1"
COVERAGE_CONTRACT: Final = "grid.history-campaign-coverage-audit/v1"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
MINUTE_MS: Final = 60_000
FUNDING_QUALITY_FIELDS: Final = (
    "boundary_page_count",
    "duplicate_key_count",
    "empty_range_page_count",
    "internal_interval_mismatch_count",
    "interval_change_count",
    "lifecycle_failure_count",
    "observed_event_count",
    "predecessor_interval_mismatch_count",
    "range_page_count",
    "unexpected_timestamp_count",
    "unrequested_row_count",
)
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
FUNDING_REASON_CODES: Final = (
    "canonical_source_mismatch",
    "duplicate_canonical_key",
    "internal_interval_mismatch",
    "predecessor_interval_mismatch",
    "registry_lifecycle_failure",
    "source_window_returned_no_event",
    "unexpected_settlement_timestamp",
    "unexplained_interval_change",
    "unrequested_instrument_row",
)


class CurrentUniverseFundingEvidenceError(RuntimeError):
    """The current-universe funding evidence projection failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CurrentUniverseFundingEvidenceError(message)


def _mapping(parent: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise CurrentUniverseFundingEvidenceError(f"field must be an object: {key}")
    return cast(dict[str, Any], value)


def _array(parent: Mapping[str, Any], key: str) -> list[Any]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise CurrentUniverseFundingEvidenceError(f"field must be an array: {key}")
    return value


def _integer(parent: Mapping[str, Any], key: str, *, minimum: int = 0) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CurrentUniverseFundingEvidenceError(f"integer field is invalid: {key}")
    return value


def _sha(parent: Mapping[str, Any], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise CurrentUniverseFundingEvidenceError(f"SHA-256 field is invalid: {key}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CurrentUniverseFundingEvidenceError(f"invalid JSON artifact: {path.name}") from error
    if not isinstance(value, dict):
        raise CurrentUniverseFundingEvidenceError(f"JSON artifact must be an object: {path.name}")
    return cast(dict[str, Any], value)


def _validate_schema(payload: Mapping[str, Any], schema_path: Path, *, label: str) -> None:
    schema = _load_json(schema_path)
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    except Exception as error:
        raise CurrentUniverseFundingEvidenceError(f"{label} schema does not verify") from error


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
        raise CurrentUniverseFundingEvidenceError(
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
    _validate_schema(
        payload,
        ROOT / "schemas/evidence/v1" / schema_name,
        label=f"evidence {supplied.name}",
    )
    return payload


def _load_document(path: Path, *, schema_name: str, contract: str) -> dict[str, Any]:
    payload = _load_json(path)
    _require(payload.get("contract") == contract, f"request contract differs: {path.name}")
    _validate_schema(
        payload,
        ROOT / "schemas/market/v1" / schema_name,
        label=f"request {path.name}",
    )
    return payload


def _load_request(path: Path, *, schema_name: str, contract: str) -> dict[str, Any]:
    payload = _load_document(path, schema_name=schema_name, contract=contract)
    symbols = _array(payload, "symbols")
    _require(
        len(symbols) == len(set(symbols)),
        "request symbols must be unique",
    )
    _require(_integer(payload, "start_ms") <= _integer(payload, "end_ms"), "request range invalid")
    return payload


def _verify_generated_at(value: str) -> None:
    _require(value.endswith("Z"), "generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise CurrentUniverseFundingEvidenceError("generated_at_utc is invalid") from error
    offset = parsed.utcoffset()
    _require(offset is not None and offset.total_seconds() == 0, "generated_at_utc must be UTC")


def _resolve_path(artifact_root: Path, raw: object) -> Path:
    _require(isinstance(raw, str), "source path must be a string")
    pure = PurePosixPath(cast(str, raw))
    _require(not pure.is_absolute() and ".." not in pure.parts, "source path must be safe-relative")
    root = artifact_root.resolve()
    resolved = (root / Path(*pure.parts)).resolve()
    _require(resolved.is_relative_to(root), "source path escapes artifact root")
    return resolved


def _kind_map(parent: Mapping[str, Any], key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in _array(parent, key):
        _require(isinstance(raw, dict), f"{key} item must be an object")
        item = cast(dict[str, Any], raw)
        kind = item.get("kind")
        _require(kind in {"trade", "mark", "funding"}, f"{key} kind is invalid")
        _require(kind not in result, f"{key} repeats a kind")
        result[cast(str, kind)] = item
    return result


def _verify_triplet(
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
    for landing_name, publication_name in (
        ("campaign_manifest_sha256", "source_campaign_manifest_sha256"),
        ("campaign_plan_sha256", "source_campaign_plan_sha256"),
    ):
        _require(
            landing_bindings.get(landing_name)
            == publication_bindings.get(publication_name)
            == coverage_bindings.get(publication_name),
            f"source triplet binding mismatch: {landing_name}",
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


def _request_interval_map(request: Mapping[str, Any]) -> dict[str, list[tuple[int, int]]]:
    start = _integer(request, "start_ms")
    end = _integer(request, "end_ms")
    return {cast(str, symbol): [(start, end)] for symbol in _array(request, "symbols")}


def _append_intervals(
    target: dict[str, list[tuple[int, int]]],
    source: Mapping[str, Sequence[tuple[int, int]]],
) -> None:
    for symbol, intervals in source.items():
        target.setdefault(symbol, []).extend(intervals)


def _normalized_intervals(
    source: Mapping[str, Sequence[tuple[int, int]]], *, label: str
) -> dict[str, tuple[tuple[int, int], ...]]:
    result: dict[str, tuple[tuple[int, int], ...]] = {}
    for intervals in source.values():
        _require(bool(intervals), f"{label} interval list is empty")
    for symbol, intervals in source.items():
        merged: list[tuple[int, int]] = []
        for start, end in sorted(intervals):
            _require(start <= end, f"{label} interval is invalid")
            if not merged:
                merged.append((start, end))
                continue
            prior_start, prior_end = merged[-1]
            _require(start > prior_end, f"{label} intervals overlap")
            if start == prior_end + MINUTE_MS:
                merged[-1] = (prior_start, end)
            else:
                merged.append((start, end))
        result[symbol] = tuple(merged)
    return result


def _load_source_manifest(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    _require(payload.get("contract") == REQUEST_CONTRACT, "source manifest contract differs")
    try:
        artifact_bytes = path.read_bytes()
    except OSError as error:
        raise CurrentUniverseFundingEvidenceError("cannot read source manifest bytes") from error
    _require(
        artifact_bytes == canonical_json_bytes(payload) + b"\n",
        "source manifest is not canonical JSON plus LF",
    )
    _validate_schema(
        payload,
        ROOT / "schemas/evidence/v1/current-universe-funding-evidence-request.schema.json",
        label="source manifest",
    )
    return payload


def _load_campaign_evidence_triplet(
    *, landing_path: Path, publication_path: Path, coverage_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
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
    _verify_triplet(landing, publication, coverage)
    return landing, publication, coverage


def build_current_universe_funding_evidence(
    *,
    source_manifest_path: Path,
    artifact_root: Path,
    generated_at_utc: str,
    software_identity: str,
) -> dict[str, Any]:
    """Verify exact candle/funding scope parity and aggregate funding evidence."""

    _verify_generated_at(generated_at_utc)
    _require(
        SOFTWARE_IDENTITY_RE.fullmatch(software_identity) is not None,
        "software identity must be an immutable Git SHA",
    )
    manifest = _load_source_manifest(source_manifest_path)
    root = artifact_root.resolve()
    _require(root.is_dir(), "artifact root must be a directory")

    bundle_request_path = _resolve_path(root, manifest.get("candle_bundle_request"))
    bundle_evidence_path = _resolve_path(root, manifest.get("candle_bundle_evidence"))
    candle_evidence_path = _resolve_path(root, manifest.get("candle_evidence"))
    bundle_request = _load_document(
        bundle_request_path,
        schema_name="canonical-catalog-selection-bundle-request.schema.json",
        contract=CANDLE_BUNDLE_REQUEST_CONTRACT,
    )
    bundle_evidence = _load_verified_evidence(
        bundle_evidence_path,
        schema_name="phase2-catalog-selection-bundle.schema.json",
        contract_key="evidence_schema",
        contract=CANDLE_BUNDLE_CONTRACT,
        statuses={"verified-catalog-selection-bundle"},
    )
    candle_evidence = _load_verified_evidence(
        candle_evidence_path,
        schema_name="phase2-current-universe-candle-evidence.schema.json",
        contract_key="evidence_schema",
        contract=CANDLE_EVIDENCE_CONTRACT,
        statuses={"verified-current-universe-candle-evidence"},
    )
    bundle_request_hash = canonical_sha256(bundle_request)
    _require(
        _mapping(bundle_evidence, "bindings").get("bundle_request_sha256") == bundle_request_hash,
        "candle bundle request binding mismatch",
    )
    candle_bindings = _mapping(candle_evidence, "bindings")
    _require(
        candle_bindings.get("catalog_bundle_artifact_sha256") == sha256_file(bundle_evidence_path),
        "candle evidence catalog artifact binding mismatch",
    )
    _require(
        candle_bindings.get("catalog_bundle_content_sha256")
        == _sha(bundle_evidence, "content_sha256"),
        "candle evidence catalog content binding mismatch",
    )

    bundle_sources = _array(bundle_request, "sources")
    candle_sources = _array(manifest, "candle_sources")
    _require(len(bundle_sources) == len(candle_sources), "candle source count differs")
    _require(
        _integer(_mapping(bundle_evidence, "inventory"), "source_count", minimum=1)
        == len(candle_sources)
        == _integer(_mapping(candle_evidence, "inventory"), "source_count", minimum=1),
        "public candle source count differs",
    )

    target_intervals: dict[str, list[tuple[int, int]]] = {}
    candle_chain: list[dict[str, str]] = []
    candle_artifact_chain: list[dict[str, str]] = []
    registry_hash: str | None = None
    capacity_hash: str | None = None
    for bundle_source_raw, source_raw in zip(bundle_sources, candle_sources, strict=True):
        _require(isinstance(bundle_source_raw, dict), "candle bundle source must be an object")
        _require(isinstance(source_raw, dict), "candle source must be an object")
        bundle_source = cast(dict[str, Any], bundle_source_raw)
        source = cast(dict[str, Any], source_raw)
        request_path = _resolve_path(root, source.get("request"))
        landing_path = _resolve_path(root, source.get("landing_evidence"))
        publication_path = _resolve_path(root, source.get("publication_evidence"))
        coverage_path = _resolve_path(root, source.get("coverage_evidence"))
        request = _load_request(
            request_path,
            schema_name="public-history-campaign-request.schema.json",
            contract=CAMPAIGN_REQUEST_CONTRACT,
        )
        landing, publication, coverage = _load_campaign_evidence_triplet(
            landing_path=landing_path,
            publication_path=publication_path,
            coverage_path=coverage_path,
        )
        _require(
            request.get("campaign_id") == bundle_source.get("campaign_id"),
            "candle campaign differs",
        )
        kinds = set(_array(request, "kinds"))
        _require({"trade", "mark"}.issubset(kinds), "candle source lacks candle kinds")
        _require(
            _mapping(landing, "bindings").get("campaign_request_sha256")
            == canonical_sha256(request),
            "candle request binding mismatch",
        )
        start = _integer(bundle_source, "start_time_ms")
        end = _integer(bundle_source, "end_time_ms")
        _require(
            _integer(request, "start_ms") <= start <= end <= _integer(request, "end_ms"),
            "candle bundle clip is outside its source request",
        )
        for symbol in _array(request, "symbols"):
            target_intervals.setdefault(cast(str, symbol), []).append((start, end))
        landing_bindings = _mapping(landing, "bindings")
        publication_bindings = _mapping(publication, "bindings")
        current_registry = _sha(landing_bindings, "instrument_registry_sha256")
        current_capacity = _sha(landing_bindings, "capacity_evidence_sha256")
        registry_hash = current_registry if registry_hash is None else registry_hash
        capacity_hash = current_capacity if capacity_hash is None else capacity_hash
        _require(current_registry == registry_hash, "candle sources use different registries")
        _require(
            current_capacity == capacity_hash, "candle sources use different capacity evidence"
        )
        candle_chain.append(
            {
                "campaign_manifest_sha256": _sha(landing_bindings, "campaign_manifest_sha256"),
                "campaign_plan_sha256": _sha(landing_bindings, "campaign_plan_sha256"),
                "publication_manifest_sha256": _sha(
                    publication_bindings, "publication_manifest_sha256"
                ),
                "publication_plan_sha256": _sha(publication_bindings, "publication_plan_sha256"),
            }
        )
        candle_artifact_chain.append(
            {
                "coverage_artifact_sha256": sha256_file(coverage_path),
                "landing_artifact_sha256": sha256_file(landing_path),
                "publication_artifact_sha256": sha256_file(publication_path),
            }
        )

    _require(
        _mapping(bundle_evidence, "bindings").get("source_chain_sha256")
        == canonical_sha256(candle_chain),
        "candle bundle source chain differs",
    )
    _require(
        candle_bindings.get("source_evidence_chain_sha256")
        == canonical_sha256(candle_artifact_chain),
        "current-universe candle evidence chain differs",
    )
    _require(
        candle_bindings.get("instrument_registry_sha256") == registry_hash
        and candle_bindings.get("capacity_evidence_sha256") == capacity_hash,
        "current-universe candle evidence governance bindings differ",
    )
    normalized_targets = _normalized_intervals(target_intervals, label="candle target")
    target_symbol_count = len(normalized_targets)
    _require(
        _integer(_mapping(bundle_evidence, "inventory"), "instrument_count", minimum=1)
        == target_symbol_count
        == _integer(_mapping(candle_evidence, "inventory"), "instrument_count", minimum=1),
        "current-universe instrument count differs",
    )

    funding_intervals: dict[str, list[tuple[int, int]]] = {}
    funding_artifact_chain: list[dict[str, Any]] = []
    seen_funding_requests: set[str] = set()
    source_boundary_totals = {
        "canonical_start_proven_count": 0,
        "event_count": 0,
        "http_attempt_count": 0,
        "page_count": 0,
        "predecessor_proven_count": 0,
        "retry_count": 0,
        "source_count": 0,
    }
    inventory = {
        "canonical_dataset_count": 0,
        "canonical_file_count": 0,
        "canonical_parquet_bytes": 0,
        "canonical_row_count": 0,
        "coverage_blocked_count": 0,
        "coverage_passed_count": 0,
        "landing_http_request_count": 0,
        "landing_job_count": 0,
        "landing_page_count": 0,
        "landing_row_count": 0,
        "source_count": 0,
        "symbol_count": target_symbol_count,
    }
    funding_quality = {key: 0 for key in FUNDING_QUALITY_FIELDS}
    reason_counts = {key: 0 for key in REASON_CODES}
    coverage_status = "passed"
    acquisition_starts: list[int] = []
    acquisition_completions: list[int] = []
    acquisition_elapsed = 0
    acquisition_child_elapsed = 0
    publication_starts: list[int] = []
    publication_completions: list[int] = []
    publication_elapsed = 0

    funding_sources = _array(manifest, "funding_sources")
    _require(bool(funding_sources), "funding source list is empty")
    for source_raw in funding_sources:
        _require(isinstance(source_raw, dict), "funding source must be an object")
        source = cast(dict[str, Any], source_raw)
        mode = source.get("mode")
        _require(mode in {"boundary-backed", "reused-bounded"}, "funding source mode differs")
        request_path = _resolve_path(root, source.get("request"))
        landing_path = _resolve_path(root, source.get("landing_evidence"))
        publication_path = _resolve_path(root, source.get("publication_evidence"))
        coverage_path = _resolve_path(root, source.get("coverage_evidence"))
        request = _load_request(
            request_path,
            schema_name="public-history-campaign-request.schema.json",
            contract=CAMPAIGN_REQUEST_CONTRACT,
        )
        _require("funding" in _array(request, "kinds"), "funding source lacks funding kind")
        request_hash = canonical_sha256(request)
        _require(request_hash not in seen_funding_requests, "funding request is repeated")
        seen_funding_requests.add(request_hash)
        landing, publication, coverage = _load_campaign_evidence_triplet(
            landing_path=landing_path,
            publication_path=publication_path,
            coverage_path=coverage_path,
        )
        landing_bindings = _mapping(landing, "bindings")
        _require(
            landing_bindings.get("campaign_request_sha256") == request_hash,
            "funding request binding mismatch",
        )
        _require(
            landing_bindings.get("instrument_registry_sha256") == registry_hash
            and landing_bindings.get("capacity_evidence_sha256") == capacity_hash,
            "funding source governance bindings differ",
        )
        _append_intervals(funding_intervals, _request_interval_map(request))
        source_binding: dict[str, Any] = {
            "coverage_artifact_sha256": sha256_file(coverage_path),
            "landing_artifact_sha256": sha256_file(landing_path),
            "mode": mode,
            "publication_artifact_sha256": sha256_file(publication_path),
            "request_content_sha256": request_hash,
        }

        landing_summary = _mapping(landing, "landing")
        landing_kinds = _kind_map(landing_summary, "by_kind")
        publication_summary = _mapping(publication, "canonical")
        publication_kinds = _kind_map(publication_summary, "by_kind")
        coverage_inventory = _mapping(coverage, "inventory")
        coverage_kinds = _kind_map(coverage_inventory, "by_kind")
        _require(
            "funding" in landing_kinds
            and "funding" in publication_kinds
            and "funding" in coverage_kinds,
            "funding source triplet lacks funding inventory",
        )
        if mode == "reused-bounded":
            _require(
                all(
                    _integer(item, "blocked_count") == 0
                    for kind, item in coverage_kinds.items()
                    if kind != "funding"
                ),
                "reused funding source has blocked non-funding coverage",
            )
        landing_funding = landing_kinds["funding"]
        publication_funding = publication_kinds["funding"]
        coverage_funding = coverage_kinds["funding"]
        landing_rows = _integer(landing_funding, "row_count")
        canonical_rows = _integer(publication_funding, "row_count")
        _require(landing_rows == canonical_rows, "funding Landing/canonical rows differ")
        _require(
            canonical_rows == _integer(coverage_funding, "row_count"),
            "funding canonical/coverage rows differ",
        )
        _require(
            _integer(publication_funding, "dataset_count", minimum=1)
            == _integer(coverage_funding, "dataset_count", minimum=1),
            "funding canonical/coverage dataset counts differ",
        )
        _require(
            _integer(coverage_funding, "blocked_count") + _integer(coverage_funding, "passed_count")
            == _integer(coverage_funding, "dataset_count", minimum=1),
            "funding coverage status counts do not reconcile",
        )
        coverage_quality = _mapping(_mapping(coverage, "quality"), "funding")
        _require(
            _integer(coverage_quality, "observed_event_count") == canonical_rows,
            "funding observed event count differs from canonical rows",
        )
        for key in FUNDING_QUALITY_FIELDS:
            funding_quality[key] += _integer(coverage_quality, key)
        reason_policy = _mapping(coverage, "reason_policy")
        _require(
            not _array(reason_policy, "accepted_reason_codes"), "funding coverage accepts a reason"
        )
        _require(
            _integer(reason_policy, "unknown_reason_count") == 0,
            "funding coverage has unknown reasons",
        )
        observed_reasons = _mapping(reason_policy, "observed_reason_counts")
        _require(
            set(_array(reason_policy, "unaccepted_reason_codes")) == set(observed_reasons),
            "funding unaccepted reasons do not match observations",
        )
        for key, value in observed_reasons.items():
            _require(key in FUNDING_REASON_CODES, "funding coverage reason is not attributable")
            _require(
                isinstance(value, int) and not isinstance(value, bool) and value > 0,
                "funding reason count is invalid",
            )
            reason_counts[key] += value
        if _integer(coverage_funding, "blocked_count") > 0:
            coverage_status = "blocked"

        inventory["source_count"] += 1
        inventory["landing_job_count"] += _integer(landing_funding, "job_count", minimum=1)
        inventory["landing_page_count"] += _integer(landing_funding, "page_count", minimum=1)
        inventory["landing_http_request_count"] += _integer(
            landing_funding, "http_request_count", minimum=1
        )
        inventory["landing_row_count"] += landing_rows
        inventory["canonical_dataset_count"] += _integer(
            publication_funding, "dataset_count", minimum=1
        )
        inventory["canonical_file_count"] += _integer(publication_funding, "file_count", minimum=1)
        inventory["canonical_parquet_bytes"] += _integer(
            publication_funding, "parquet_bytes", minimum=1
        )
        inventory["canonical_row_count"] += canonical_rows
        inventory["coverage_blocked_count"] += _integer(coverage_funding, "blocked_count")
        inventory["coverage_passed_count"] += _integer(coverage_funding, "passed_count")

        landing_timing = _mapping(landing, "timing")
        landing_start = _integer(landing_timing, "campaign_started_at_ms")
        landing_complete = _integer(landing_timing, "campaign_completed_at_ms")
        landing_elapsed = _integer(landing_timing, "campaign_elapsed_ms")
        _require(
            landing_complete - landing_start == landing_elapsed, "funding Landing timing differs"
        )
        _require(
            _integer(landing_timing, "timed_child_count", minimum=1)
            == _integer(landing_summary, "job_count", minimum=1),
            "funding Landing timing does not cover every child",
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
            _require(completed - started == elapsed, "funding publication timing differs")
            publication_starts.append(started)
            publication_completions.append(completed)
            publication_elapsed += elapsed

        if mode == "boundary-backed":
            _require(
                set(_array(request, "kinds")) == {"funding"},
                "boundary-backed source must be funding-only",
            )
            boundary_request_path = _resolve_path(root, source.get("boundary_request"))
            boundary_evidence_path = _resolve_path(root, source.get("boundary_evidence"))
            boundary_request = _load_request(
                boundary_request_path,
                schema_name="funding-source-boundary-request.schema.json",
                contract=BOUNDARY_REQUEST_CONTRACT,
            )
            boundary_evidence = _load_verified_evidence(
                boundary_evidence_path,
                schema_name="phase2-funding-source-boundary.schema.json",
                contract_key="evidence_schema",
                contract=BOUNDARY_EVIDENCE_CONTRACT,
                statuses={"verified-public-funding-source-boundary"},
            )
            _require(
                _array(boundary_request, "symbols") == _array(request, "symbols")
                and _integer(boundary_request, "start_ms") == _integer(request, "start_ms")
                and _integer(boundary_request, "end_ms") == _integer(request, "end_ms"),
                "funding boundary/request scope differs",
            )
            boundary_bindings = _mapping(boundary_evidence, "bindings")
            _require(
                boundary_bindings.get("boundary_request_sha256")
                == canonical_sha256(boundary_request),
                "funding boundary request binding differs",
            )
            _require(
                boundary_bindings.get("instrument_registry_sha256") == registry_hash,
                "funding boundary registry differs",
            )
            _require(
                landing_bindings.get("funding_source_boundary_manifest_sha256")
                == boundary_bindings.get("boundary_manifest_sha256"),
                "funding campaign/source-boundary binding differs",
            )
            boundary_scope = _mapping(boundary_evidence, "scope")
            symbol_count = len(_array(request, "symbols"))
            _require(
                _integer(boundary_scope, "symbol_count", minimum=1) == symbol_count
                and _integer(boundary_scope, "start_ms") == _integer(request, "start_ms")
                and _integer(boundary_scope, "end_ms") == _integer(request, "end_ms"),
                "funding boundary evidence scope differs",
            )
            boundary_result = _mapping(boundary_evidence, "result")
            _require(
                _integer(boundary_result, "canonical_start_proven_count", minimum=1)
                == symbol_count
                == _integer(boundary_result, "predecessor_proven_count", minimum=1),
                "funding boundary predecessor admission is incomplete",
            )
            boundary_landing = _mapping(boundary_evidence, "landing")
            _require(
                _integer(boundary_landing, "event_count", minimum=2) - symbol_count == landing_rows,
                "funding boundary/campaign event counts differ",
            )
            source_boundary_totals["source_count"] += 1
            source_boundary_totals["event_count"] += _integer(
                boundary_landing, "event_count", minimum=2
            )
            source_boundary_totals["page_count"] += _integer(
                boundary_landing, "page_count", minimum=1
            )
            source_boundary_totals["http_attempt_count"] += _integer(
                boundary_landing, "http_attempt_count", minimum=1
            )
            source_boundary_totals["retry_count"] += _integer(boundary_landing, "retry_count")
            source_boundary_totals["canonical_start_proven_count"] += symbol_count
            source_boundary_totals["predecessor_proven_count"] += symbol_count
            source_binding["boundary_evidence_artifact_sha256"] = sha256_file(
                boundary_evidence_path
            )
            source_binding["boundary_request_content_sha256"] = canonical_sha256(boundary_request)
        else:
            _require(
                "boundary_request" not in source and "boundary_evidence" not in source,
                "reused funding source unexpectedly carries boundary inputs",
            )
        funding_artifact_chain.append(source_binding)

    normalized_funding = _normalized_intervals(funding_intervals, label="funding source")
    _require(
        normalized_funding == normalized_targets,
        "funding source intervals do not exactly cover the candle universe",
    )
    _require(inventory["symbol_count"] == len(normalized_funding), "funding symbol count differs")

    timed_publication_count = len(publication_starts)
    payload: dict[str, Any] = {
        "assurances": {
            "all_source_content_hashes_verified": True,
            "all_source_receipts_verified": True,
            "all_source_schemas_verified": True,
            "automatic_gate_acceptance_performed": False,
            "candle_and_funding_scope_exactly_equal": True,
            "funding_source_intervals_non_overlapping": True,
            "market_store_read": False,
            "network_request_performed": False,
            "phase3_authorized": False,
            "private_request_artifacts_read": True,
            "private_or_live_capability_used": False,
        },
        "bindings": {
            "candle_bundle_artifact_sha256": sha256_file(bundle_evidence_path),
            "candle_bundle_request_sha256": bundle_request_hash,
            "candle_evidence_artifact_sha256": sha256_file(candle_evidence_path),
            "capacity_evidence_sha256": capacity_hash,
            "evidence_builder_software_identity": software_identity,
            "funding_source_chain_sha256": canonical_sha256(funding_artifact_chain),
            "instrument_registry_sha256": registry_hash,
            "source_manifest_sha256": canonical_sha256(manifest),
        },
        "evidence_schema": EVIDENCE_CONTRACT,
        "generated_at_utc": generated_at_utc,
        "inventory": inventory,
        "limitations": [
            "The pack proves exact current-universe funding source scope and retained evidence, "
            "not an independent venue ledger.",
            "Observed cadence changes and empty source windows remain unaccepted unless separate "
            "dated evidence or owner policy resolves them.",
            "Current instrument fundingInterval metadata is not historical evidence.",
            "Catalog registration and deterministic funding selection remain separate evidence.",
            "Measured campaign timings may include reused mixed-kind work and are not an "
            "owner-reviewed end-to-end performance envelope.",
            "This evidence does not close Gate 2, authorize Phase 3, promote research data, or "
            "enable live execution.",
        ],
        "performance": {
            "acquisition": {
                "campaign_count": len(funding_sources),
                "earliest_started_at_ms": min(acquisition_starts),
                "latest_completed_at_ms": max(acquisition_completions),
                "observed_wall_span_ms": max(acquisition_completions) - min(acquisition_starts),
                "summed_campaign_elapsed_ms": acquisition_elapsed,
                "summed_child_elapsed_ms": acquisition_child_elapsed,
            },
            "envelope": {"owner_review_required": True, "qualified": False},
            "publication": {
                "complete_source_timing": timed_publication_count == len(funding_sources),
                "earliest_started_at_ms": min(publication_starts) if publication_starts else None,
                "latest_completed_at_ms": max(publication_completions)
                if publication_completions
                else None,
                "source_count": len(funding_sources),
                "summed_elapsed_ms": publication_elapsed,
                "timed_source_count": timed_publication_count,
            },
        },
        "quality": {
            "accepted_reason_count": 0,
            "coverage_status": coverage_status,
            "funding": funding_quality,
            "reason_counts": reason_counts,
        },
        "source_boundary": source_boundary_totals,
        "status": "verified-current-universe-funding-evidence",
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_dataset_identities": False,
            "evidence_contains_funding_rates": False,
            "evidence_contains_instrument_identities": False,
            "evidence_contains_market_time_bounds": False,
            "evidence_contains_market_values": False,
            "evidence_contains_observed_settlement_timestamps": False,
            "evidence_contains_runtime_paths": False,
            "runtime_market_artifacts_committed_to_git": False,
        },
        "universe": {
            "candle_source_count": len(candle_sources),
            "funding_source_count": len(funding_sources),
            "interval_partition_exact": True,
            "symbol_count": target_symbol_count,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    _validate_schema(
        payload,
        ROOT / "schemas/evidence/v1/phase2-current-universe-funding-evidence.schema.json",
        label="current-universe funding evidence",
    )
    return payload


def publish_current_universe_funding_evidence(
    *,
    source_manifest_path: Path,
    artifact_root: Path,
    generated_at_utc: str,
    software_identity: str,
    output: Path,
) -> dict[str, Any]:
    target, _receipt = preflight_evidence(output)
    payload = build_current_universe_funding_evidence(
        source_manifest_path=source_manifest_path,
        artifact_root=artifact_root,
        generated_at_utc=generated_at_utc,
        software_identity=software_identity,
    )
    publish_evidence(target, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, default=ROOT)
    parser.add_argument("--software-identity", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = publish_current_universe_funding_evidence(
        source_manifest_path=args.source_manifest,
        artifact_root=args.artifact_root,
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
                "symbol_count": payload["inventory"]["symbol_count"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
