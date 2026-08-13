"""Bind a verified 1m Landing batch to receipt-last canonical publication."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

import pyarrow.compute as pc  # type: ignore[import-untyped]
from grid_contracts.canonical import canonical_sha256
from grid_market_store import (
    CANONICAL_LAYOUT_ID,
    CandleDatasetSpec,
    CanonicalCandleBatch,
    CapacityBudget,
    HostSnapshot,
    PublicationError,
    PublicationPlan,
    PublishedDataset,
    preflight_candle_dataset,
    publish_candle_dataset,
)

from grid_data.history_acquisition import (
    CompletedHistoryJob,
    HistoryAcquisitionError,
    load_verified_completed_history_batch,
)
from grid_data.history_request import (
    active_and_building_bytes_from_capacity,
    load_verified_capacity_evidence,
)
from grid_data.instrument_registry import (
    VerifiedInstrumentRegistry,
    load_verified_instrument_registry,
)

HISTORY_PUBLICATION_CONTRACT: Final = "grid.history-to-canonical-publication/v1"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")


@dataclass(frozen=True, slots=True)
class ResolvedHistoryPublication:
    completed_history: CompletedHistoryJob
    instrument_registry: VerifiedInstrumentRegistry
    capacity_evidence_path: Path
    capacity_evidence_sha256: str
    plan: PublicationPlan


@dataclass(frozen=True, slots=True)
class VerifiedHistoryPublicationInput:
    completed_history: CompletedHistoryJob
    instrument_registry: VerifiedInstrumentRegistry
    capacity_evidence_path: Path
    capacity_evidence_sha256: str
    batch: CanonicalCandleBatch
    budget: CapacityBudget
    dataset_id: str


def _object(path: Path, *, name: str) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryAcquisitionError(f"verified {name} cannot be loaded") from error
    if not isinstance(raw, dict):
        raise HistoryAcquisitionError(f"verified {name} must be an object")
    return cast(dict[str, object], raw)


def _capacity_budget(plan: dict[str, object]) -> CapacityBudget:
    raw = plan.get("capacity_budget")
    if not isinstance(raw, dict):
        raise HistoryAcquisitionError("history plan has no capacity budget")
    try:
        return CapacityBudget(**raw)
    except (TypeError, PublicationError) as error:
        raise HistoryAcquisitionError("history plan capacity budget is invalid") from error


def _validate_registry_coverage(
    registry: VerifiedInstrumentRegistry,
    batch: CanonicalCandleBatch,
) -> None:
    by_id = {item.instrument_id: item for item in registry.snapshots}
    identifiers = set(batch.table.column("instrument_id").to_pylist())
    for identifier in identifiers:
        snapshot = by_id.get(identifier)
        if snapshot is None:
            raise HistoryAcquisitionError(
                f"canonical batch instrument_id is absent from registry: {identifier}"
            )
        mask = pc.equal(batch.table.column("instrument_id"), identifier)
        bounds = cast(
            dict[str, int],
            pc.min_max(pc.filter(batch.table.column("open_time_ms"), mask)).as_py(),
        )
        if bounds["min"] < snapshot.launch_time_ms:
            raise HistoryAcquisitionError("canonical batch begins before registry launch time")
        if snapshot.delivery_time_ms is not None and bounds["max"] > snapshot.delivery_time_ms:
            raise HistoryAcquisitionError("canonical batch ends after registry delivery time")


def _dataset_id(dataset_type: str, history_manifest_sha256: str) -> str:
    prefix = "trade-1m" if dataset_type == "trade_kline_1m" else "mark-1m"
    return f"{prefix}-{history_manifest_sha256[:24]}"


def load_verified_history_publication_input(
    job_root: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
) -> VerifiedHistoryPublicationInput:
    """Verify Landing and upstream evidence without probing the host or mutating storage."""

    completed, batch = load_verified_completed_history_batch(job_root)
    manifest = _object(completed.manifest_path, name="history manifest")
    history_plan = _object(completed.plan_path, name="history plan")
    registry = load_verified_instrument_registry(instrument_registry_path)
    capacity_path, capacity, capacity_sha = load_verified_capacity_evidence(capacity_evidence_path)
    if manifest.get("instrument_evidence_sha256") != registry.artifact_sha256:
        raise HistoryAcquisitionError("history manifest does not bind the supplied registry")
    if manifest.get("capacity_evidence_sha256") != capacity_sha:
        raise HistoryAcquisitionError(
            "history manifest does not bind the supplied capacity evidence"
        )
    budget = _capacity_budget(history_plan)
    expected_active = active_and_building_bytes_from_capacity(capacity)
    if budget.active_and_building_bytes != expected_active:
        raise HistoryAcquisitionError(
            "history capacity budget does not match the supplied accepted-layout evidence"
        )
    _validate_registry_coverage(registry, batch)
    return VerifiedHistoryPublicationInput(
        completed_history=completed,
        instrument_registry=registry,
        capacity_evidence_path=capacity_path,
        capacity_evidence_sha256=capacity_sha,
        batch=batch,
        budget=budget,
        dataset_id=_dataset_id(batch.dataset_type.value, completed.manifest_sha256),
    )


def history_publication_spec(
    verified: VerifiedHistoryPublicationInput,
    *,
    software_identity: str,
) -> CandleDatasetSpec:
    """Resolve the deterministic canonical specification for verified Landing evidence."""

    if not SOFTWARE_IDENTITY_RE.fullmatch(software_identity):
        raise HistoryAcquisitionError(
            "software_identity must be git:<40-character-lowercase-commit-sha>"
        )
    build_config_sha = canonical_sha256(
        {
            "canonical_layout": CANONICAL_LAYOUT_ID,
            "contract": HISTORY_PUBLICATION_CONTRACT,
            "dataset_id": verified.dataset_id,
            "history_manifest_sha256": verified.completed_history.manifest_sha256,
            "semantic_version": "1.0.0",
            "software_identity": software_identity,
        }
    )
    return CandleDatasetSpec(
        dataset_id=verified.dataset_id,
        semantic_version="1.0.0",
        parent_dataset_ids=(),
        source_evidence_sha256=(
            verified.completed_history.manifest_sha256,
            verified.instrument_registry.artifact_sha256,
        ),
        coverage_evidence_sha256=verified.completed_history.manifest_sha256,
        capacity_evidence_sha256=verified.capacity_evidence_sha256,
        build_config_sha256=build_config_sha,
        software_identity=software_identity,
    )


def preflight_completed_history_publication(
    store_root: Path,
    job_root: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    snapshot: HostSnapshot,
    *,
    now_ms: int,
    software_identity: str,
) -> ResolvedHistoryPublication:
    """Verify all upstream evidence and plan one immutable canonical dataset without mutation."""

    verified = load_verified_history_publication_input(
        job_root,
        instrument_registry_path,
        capacity_evidence_path,
    )
    spec = history_publication_spec(verified, software_identity=software_identity)
    publication_plan = preflight_candle_dataset(
        store_root,
        spec,
        verified.batch,
        verified.budget,
        snapshot,
        now_ms=now_ms,
    )
    return ResolvedHistoryPublication(
        completed_history=verified.completed_history,
        instrument_registry=verified.instrument_registry,
        capacity_evidence_path=verified.capacity_evidence_path,
        capacity_evidence_sha256=verified.capacity_evidence_sha256,
        plan=publication_plan,
    )


def publish_preflighted_history(
    resolved: ResolvedHistoryPublication,
    snapshot_provider: Callable[[], HostSnapshot],
    now_ms: Callable[[], int],
) -> PublishedDataset:
    """Repeat the host observation in safe order and invoke receipt-last publication."""

    fresh_snapshot = snapshot_provider()
    committed_at_ms = now_ms()
    return publish_candle_dataset(
        resolved.plan,
        fresh_snapshot,
        committed_at_ms=committed_at_ms,
    )
