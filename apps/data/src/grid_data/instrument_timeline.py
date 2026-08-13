"""Immutable instrument snapshots with separate as-of and ex-post lifecycle views."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file
from grid_contracts.market import InstrumentSnapshot

from grid_data.evidence import verify_evidence
from grid_data.instrument_registry import (
    IDENTITY_ALGORITHM,
    InstrumentRegistryError,
    VerifiedInstrumentRegistry,
    load_verified_instrument_registry,
    parse_instrument_registry_payload,
)

TIMELINE_CONTRACT: Final = "grid.instrument-timeline/v1"
SUMMARY_CONTRACT: Final = "grid.instrument-timeline-summary/v1"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
MAX_SNAPSHOTS: Final = 10_000
UINT32_MAX: Final = (1 << 32) - 1


class InstrumentTimelineError(ValueError):
    """Timeline evidence cannot safely establish its declared point-in-time state."""


@dataclass(frozen=True, slots=True)
class TimelineSnapshot:
    artifact_sha256: str
    content_sha256: str
    inventory_status: str
    snapshot_time_ms: int
    records: tuple[InstrumentSnapshot, ...]
    registry_payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class LifecycleCoverage:
    instrument_id: int
    source_symbol_id: int
    observed_symbols: tuple[str, ...]
    launch_time_ms: int | None
    delivery_time_ms: int | None
    first_observed_snapshot_ms: int
    last_observed_snapshot_ms: int
    snapshot_count: int
    source_registry_sha256s: tuple[str, ...]
    blocker_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VerifiedInstrumentTimeline:
    path: Path
    artifact_sha256: str
    content_sha256: str
    snapshots: tuple[TimelineSnapshot, ...]
    coverage: tuple[LifecycleCoverage, ...]
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class AsOfInstrumentSelection:
    as_of_ms: int
    snapshot_time_ms: int
    registry_artifact_sha256: str
    inventory_status: str
    records: tuple[InstrumentSnapshot, ...]


def _eligible(record: InstrumentSnapshot) -> bool:
    return (
        record.category == "linear"
        and record.contract_type == "LinearPerpetual"
        and record.quote_coin == "USDT"
        and record.settle_coin == "USDT"
    )


def _registry_snapshot(registry: VerifiedInstrumentRegistry) -> TimelineSnapshot:
    times = {item.snapshot_time_ms for item in registry.snapshots}
    if len(times) != 1:
        raise InstrumentTimelineError("one registry must contain exactly one snapshot timestamp")
    source = registry.payload.get("source_inventory")
    content_sha256 = registry.payload.get("content_sha256")
    if (
        not isinstance(source, dict)
        or source.get("inventory_status") not in ("complete", "partial")
        or not isinstance(content_sha256, str)
        or not SHA256_RE.fullmatch(content_sha256)
    ):
        raise InstrumentTimelineError("registry source or content binding is invalid")
    return TimelineSnapshot(
        artifact_sha256=registry.artifact_sha256,
        content_sha256=content_sha256,
        inventory_status=cast(str, source["inventory_status"]),
        snapshot_time_ms=times.pop(),
        records=registry.snapshots,
        registry_payload=registry.payload,
    )


def _snapshot_payload(snapshot: TimelineSnapshot) -> dict[str, object]:
    return {
        "instrument_registry_artifact_sha256": snapshot.artifact_sha256,
        "registry": snapshot.registry_payload,
    }


def _validate_snapshot_sequence(snapshots: Sequence[TimelineSnapshot]) -> None:
    if not 1 <= len(snapshots) <= MAX_SNAPSHOTS:
        raise InstrumentTimelineError(f"timeline snapshot count must be in [1, {MAX_SNAPSHOTS}]")
    times = [item.snapshot_time_ms for item in snapshots]
    if times != sorted(times) or len(times) != len(set(times)):
        raise InstrumentTimelineError("timeline snapshot timestamps must be strictly increasing")
    hashes = [item.artifact_sha256 for item in snapshots]
    if len(hashes) != len(set(hashes)):
        raise InstrumentTimelineError("timeline cannot contain a registry artifact twice")
    identity_by_id: dict[int, int] = {}
    for snapshot in snapshots:
        identities = [item.instrument_id for item in snapshot.records]
        symbols = [item.symbol for item in snapshot.records]
        if identities != sorted(identities) or len(identities) != len(set(identities)):
            raise InstrumentTimelineError("snapshot identities must be sorted and unique")
        if len(symbols) != len(set(symbols)):
            raise InstrumentTimelineError("snapshot symbols must be unique")
        if any(item.snapshot_time_ms != snapshot.snapshot_time_ms for item in snapshot.records):
            raise InstrumentTimelineError("snapshot rows escape their registry timestamp")
        for item in snapshot.records:
            prior = identity_by_id.setdefault(item.instrument_id, item.source_symbol_id)
            if prior != item.source_symbol_id or item.instrument_id != item.source_symbol_id:
                raise InstrumentTimelineError("stable source identity changed across snapshots")


def _coverage_records(
    snapshots: Sequence[TimelineSnapshot],
) -> tuple[LifecycleCoverage, ...]:
    observations: dict[int, list[tuple[TimelineSnapshot, InstrumentSnapshot]]] = defaultdict(list)
    symbol_ids: dict[str, set[int]] = defaultdict(set)
    for snapshot in snapshots:
        for record in snapshot.records:
            if _eligible(record):
                observations[record.instrument_id].append((snapshot, record))
                symbol_ids[record.symbol].add(record.instrument_id)

    result: list[LifecycleCoverage] = []
    for instrument_id, items in sorted(observations.items()):
        records = [item[1] for item in items]
        launch_times = {item.launch_time_ms for item in records}
        delivery_times = {
            item.delivery_time_ms for item in records if item.delivery_time_ms is not None
        }
        symbols = tuple(sorted({item.symbol for item in records}))
        blockers: set[str] = set()
        if len(launch_times) != 1:
            blockers.add("conflicting_launch_time")
        if len(delivery_times) > 1:
            blockers.add("conflicting_delivery_time")
        if any(len(symbol_ids[symbol]) > 1 for symbol in symbols):
            blockers.add("symbol_reused_across_instrument_ids")
        launch_time = next(iter(launch_times)) if len(launch_times) == 1 else None
        delivery_time = next(iter(delivery_times)) if len(delivery_times) == 1 else None
        if any(item.status == "Closed" for item in records) and delivery_time is None:
            blockers.add("closed_without_delivery_time")
        if launch_time is not None and delivery_time is not None and delivery_time <= launch_time:
            blockers.add("non_positive_lifecycle_interval")
        result.append(
            LifecycleCoverage(
                instrument_id=instrument_id,
                source_symbol_id=records[0].source_symbol_id,
                observed_symbols=symbols,
                launch_time_ms=launch_time,
                delivery_time_ms=delivery_time,
                first_observed_snapshot_ms=items[0][0].snapshot_time_ms,
                last_observed_snapshot_ms=items[-1][0].snapshot_time_ms,
                snapshot_count=len(items),
                source_registry_sha256s=tuple(item[0].artifact_sha256 for item in items),
                blocker_codes=tuple(sorted(blockers)),
            )
        )
    return tuple(result)


def _summary(
    snapshots: Sequence[TimelineSnapshot], coverage: Sequence[LifecycleCoverage]
) -> dict[str, object]:
    latest = snapshots[-1]
    latest_eligible = tuple(item for item in latest.records if _eligible(item))
    status_counts: dict[str, int] = {}
    for record in latest_eligible:
        status_counts[record.status] = status_counts.get(record.status, 0) + 1
    blocker_codes = sorted({code for item in coverage for code in item.blocker_codes})
    return {
        "coverage_blocker_code_count": len(blocker_codes),
        "coverage_blocker_codes": blocker_codes,
        "coverage_instrument_count": len(coverage),
        "first_snapshot_time_ms": snapshots[0].snapshot_time_ms,
        "latest_inventory_status": latest.inventory_status,
        "latest_snapshot_time_ms": latest.snapshot_time_ms,
        "latest_status_counts": dict(sorted(status_counts.items())),
        "latest_usdt_linear_perpetual_count": len(latest_eligible),
        "partial_snapshot_count": sum(item.inventory_status == "partial" for item in snapshots),
        "snapshot_count": len(snapshots),
    }


def build_instrument_timeline(registry_paths: Sequence[Path]) -> dict[str, object]:
    """Build a deterministic immutable timeline from receipt-verified registry snapshots."""

    registries = tuple(load_verified_instrument_registry(path) for path in registry_paths)
    snapshots = tuple(
        sorted(
            (_registry_snapshot(item) for item in registries),
            key=lambda item: item.snapshot_time_ms,
        )
    )
    _validate_snapshot_sequence(snapshots)
    coverage = _coverage_records(snapshots)
    payload: dict[str, object] = {
        "evidence_schema": TIMELINE_CONTRACT,
        "identity_policy": {
            "algorithm": IDENTITY_ALGORITHM,
            "category": "linear",
            "instrument_id_expression": "source_symbol_id",
            "range": "uint32-positive",
        },
        "semantics": {
            "as_of_selection": "latest_snapshot_at_or_before_decision_time_only",
            "future_snapshot_fields_exposed_to_as_of_selection": False,
            "lifecycle_coverage_usage": "ex-post-data-quality-only",
            "metadata_effective_time_inference": "forbidden",
        },
        "snapshots": [_snapshot_payload(item) for item in snapshots],
        "summary": _summary(snapshots, coverage),
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def _timeline_snapshot_from_payload(raw: object) -> TimelineSnapshot:
    if not isinstance(raw, dict):
        raise InstrumentTimelineError("timeline snapshot must be an object")
    required = {"instrument_registry_artifact_sha256", "registry"}
    if set(raw) != required:
        raise InstrumentTimelineError("timeline snapshot fields do not match v1")
    artifact_sha256 = raw["instrument_registry_artifact_sha256"]
    registry_raw = raw["registry"]
    if not isinstance(artifact_sha256, str) or not SHA256_RE.fullmatch(artifact_sha256):
        raise InstrumentTimelineError("timeline snapshot identity or records are invalid")
    try:
        registry_payload, records = parse_instrument_registry_payload(registry_raw)
    except InstrumentRegistryError as error:
        raise InstrumentTimelineError("embedded instrument registry does not verify") from error
    expected_artifact_sha256 = hashlib.sha256(
        canonical_json_bytes(registry_payload) + b"\n"
    ).hexdigest()
    if artifact_sha256 != expected_artifact_sha256:
        raise InstrumentTimelineError("embedded registry artifact hash does not verify")
    times = {item.snapshot_time_ms for item in records}
    if len(times) != 1:
        raise InstrumentTimelineError("embedded registry has multiple snapshot timestamps")
    source = registry_payload.get("source_inventory")
    content_sha256 = registry_payload.get("content_sha256")
    if (
        not isinstance(source, dict)
        or source.get("inventory_status") not in ("complete", "partial")
        or not isinstance(content_sha256, str)
    ):
        raise InstrumentTimelineError("embedded registry source binding is invalid")
    return TimelineSnapshot(
        artifact_sha256=artifact_sha256,
        content_sha256=content_sha256,
        inventory_status=cast(str, source["inventory_status"]),
        snapshot_time_ms=times.pop(),
        records=records,
        registry_payload=registry_payload,
    )


def load_verified_instrument_timeline(path: Path) -> VerifiedInstrumentTimeline:
    """Verify the receipt, embedded hash, snapshots, summary, and temporal semantics."""

    resolved = path.resolve()
    if not verify_evidence(resolved):
        raise InstrumentTimelineError(f"instrument timeline receipt does not verify: {resolved}")
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InstrumentTimelineError("instrument timeline is not valid JSON") from error
    if not isinstance(raw, dict) or raw.get("evidence_schema") != TIMELINE_CONTRACT:
        raise InstrumentTimelineError("unsupported instrument timeline contract")
    payload = cast(dict[str, object], raw)
    embedded_hash = payload.get("content_sha256")
    hash_input = dict(payload)
    hash_input.pop("content_sha256", None)
    if embedded_hash != canonical_sha256(hash_input):
        raise InstrumentTimelineError("instrument timeline embedded hash does not verify")
    if payload.get("identity_policy") != {
        "algorithm": IDENTITY_ALGORITHM,
        "category": "linear",
        "instrument_id_expression": "source_symbol_id",
        "range": "uint32-positive",
    }:
        raise InstrumentTimelineError("instrument timeline identity policy does not match v1")
    if payload.get("semantics") != {
        "as_of_selection": "latest_snapshot_at_or_before_decision_time_only",
        "future_snapshot_fields_exposed_to_as_of_selection": False,
        "lifecycle_coverage_usage": "ex-post-data-quality-only",
        "metadata_effective_time_inference": "forbidden",
    }:
        raise InstrumentTimelineError("instrument timeline temporal semantics do not match v1")
    raw_snapshots = payload.get("snapshots")
    if not isinstance(raw_snapshots, list):
        raise InstrumentTimelineError("instrument timeline has no snapshots")
    snapshots = tuple(_timeline_snapshot_from_payload(item) for item in raw_snapshots)
    _validate_snapshot_sequence(snapshots)
    coverage = _coverage_records(snapshots)
    if payload.get("summary") != _summary(snapshots, coverage):
        raise InstrumentTimelineError("instrument timeline summary does not verify")
    return VerifiedInstrumentTimeline(
        path=resolved,
        artifact_sha256=sha256_file(resolved),
        content_sha256=embedded_hash,
        snapshots=snapshots,
        coverage=coverage,
        payload=payload,
    )


def select_instruments_as_of(
    timeline: VerifiedInstrumentTimeline,
    *,
    as_of_ms: int,
    instrument_ids: Iterable[int] | None = None,
    require_complete_inventory: bool = False,
) -> AsOfInstrumentSelection:
    """Select only a snapshot known by ``as_of_ms``; future snapshots are never consulted."""

    if isinstance(as_of_ms, bool) or not isinstance(as_of_ms, int) or as_of_ms < 0:
        raise InstrumentTimelineError("as_of_ms must be a non-negative integer")
    available = tuple(item for item in timeline.snapshots if item.snapshot_time_ms <= as_of_ms)
    if not available:
        raise InstrumentTimelineError("no instrument snapshot was known by as_of_ms")
    selected = available[-1]
    if require_complete_inventory and selected.inventory_status != "complete":
        raise InstrumentTimelineError("selected as-of inventory is partial")
    eligible = tuple(item for item in selected.records if _eligible(item))
    if instrument_ids is not None:
        requested = tuple(sorted(set(instrument_ids)))
        if not requested or any(
            isinstance(item, bool) or not isinstance(item, int) or not 1 <= item <= UINT32_MAX
            for item in requested
        ):
            raise InstrumentTimelineError("requested instrument IDs must be positive UInt32 values")
        by_id = {item.instrument_id: item for item in eligible}
        missing = tuple(item for item in requested if item not in by_id)
        if missing:
            raise InstrumentTimelineError(
                f"requested instruments absent from as-of snapshot: {missing}"
            )
        eligible = tuple(by_id[item] for item in requested)
    return AsOfInstrumentSelection(
        as_of_ms=as_of_ms,
        snapshot_time_ms=selected.snapshot_time_ms,
        registry_artifact_sha256=selected.artifact_sha256,
        inventory_status=selected.inventory_status,
        records=eligible,
    )


def build_instrument_timeline_summary(
    timeline: VerifiedInstrumentTimeline,
    *,
    software_identity: str,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Build bounded GitHub-safe facts without copying instrument rows or local paths."""

    if not SOFTWARE_IDENTITY_RE.fullmatch(software_identity):
        raise InstrumentTimelineError("software_identity must be git:<40 lowercase hex>")
    generated = generated_at or datetime.now(UTC)
    if generated.tzinfo is None or generated.utcoffset() != UTC.utcoffset(generated):
        raise InstrumentTimelineError("generated_at must be timezone-aware UTC")
    summary = cast(dict[str, object], timeline.payload["summary"])
    blocker_codes = list(cast(list[str], summary["coverage_blocker_codes"]))
    partial_count = cast(int, summary["partial_snapshot_count"])
    if partial_count:
        blocker_codes.append("partial_source_inventory")
    blocker_codes = sorted(set(blocker_codes))
    coverage = timeline.coverage
    payload: dict[str, object] = {
        "blocker_codes": blocker_codes,
        "content_sha256": "",
        "evidence_schema": SUMMARY_CONTRACT,
        "generated_at_utc": generated.isoformat().replace("+00:00", "Z"),
        "limitations": [
            "Ex-post launch/delivery bounds are data-quality evidence only and are not "
            "exposed by as-of selection.",
            "As-of selection fails before the first snapshot and uses no snapshot newer "
            "than the decision time.",
            "Undated tick-size, quantity, leverage, fee, funding-interval, or status values "
            "are not projected backward.",
            "Suspensions and source-API omissions require separate dated evidence and remain "
            "unaccepted.",
            "No public-trade archive body or tick row was downloaded, retained, or summarized.",
            "This bounded evidence does not by itself close Gate 2 or authorize research/live "
            "execution.",
        ],
        "quality": {
            "embedded_hash_verified": True,
            "future_snapshot_fields_exposed_to_as_of_selection": False,
            "identity_stability_verified": True,
            "receipt_verified": True,
            "source_registry_receipts_verified_at_build": True,
        },
        "software_identity": software_identity,
        "status": "passed" if not blocker_codes else "blocked",
        "storage_policy": {
            "contains_account_data": False,
            "contains_credentials": False,
            "contains_instrument_rows": False,
            "contains_local_paths": False,
            "contains_market_values": False,
            "runtime_timeline_committed_to_git": False,
        },
        "timeline": {
            "artifact_sha256": timeline.artifact_sha256,
            "content_sha256": timeline.content_sha256,
            "first_snapshot_time_ms": summary["first_snapshot_time_ms"],
            "latest_snapshot_time_ms": summary["latest_snapshot_time_ms"],
            "registry_artifact_sha256s": [item.artifact_sha256 for item in timeline.snapshots],
            "snapshot_count": len(timeline.snapshots),
        },
        "universe": {
            "coverage_blocked_instrument_count": sum(bool(item.blocker_codes) for item in coverage),
            "coverage_instrument_count": len(coverage),
            "delivery_bounded_instrument_count": sum(
                item.delivery_time_ms is not None and not item.blocker_codes for item in coverage
            ),
            "latest_inventory_status": summary["latest_inventory_status"],
            "latest_status_counts": summary["latest_status_counts"],
            "latest_usdt_linear_perpetual_count": summary["latest_usdt_linear_perpetual_count"],
            "open_ended_instrument_count": sum(
                item.delivery_time_ms is None and not item.blocker_codes for item in coverage
            ),
            "partial_snapshot_count": partial_count,
        },
    }
    payload["content_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    return payload
