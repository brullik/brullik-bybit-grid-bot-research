"""Bind a verified funding Landing batch to receipt-last canonical publication."""

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
    FUNDING_CANONICAL_LAYOUT_ID,
    CanonicalFundingBatch,
    CapacityBudget,
    FundingDatasetSpec,
    FundingPublicationPlan,
    HostSnapshot,
    PublicationError,
    PublishedDataset,
    preflight_funding_dataset,
    publish_funding_dataset,
)

from grid_data.funding_acquisition import (
    CompletedFundingJob,
    FundingAcquisitionError,
    load_completed_funding_batch,
    verify_completed_funding_job,
)
from grid_data.history_acquisition import HistoryAcquisitionError
from grid_data.history_request import (
    active_and_building_bytes_from_capacity,
    load_verified_capacity_evidence,
)
from grid_data.instrument_registry import (
    VerifiedInstrumentRegistry,
    load_verified_instrument_registry,
)

FUNDING_HISTORY_PUBLICATION_CONTRACT: Final = "grid.funding-history-to-canonical/v1"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")


@dataclass(frozen=True, slots=True)
class VerifiedFundingPublicationInput:
    completed: CompletedFundingJob
    registry: VerifiedInstrumentRegistry
    capacity_evidence_path: Path
    capacity_evidence_sha256: str
    batch: CanonicalFundingBatch
    budget: CapacityBudget
    dataset_id: str


@dataclass(frozen=True, slots=True)
class ResolvedFundingPublication:
    verified: VerifiedFundingPublicationInput
    plan: FundingPublicationPlan


def _object(path: Path, *, name: str) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FundingAcquisitionError(f"verified {name} cannot be loaded") from error
    if not isinstance(raw, dict):
        raise FundingAcquisitionError(f"verified {name} must be an object")
    return cast(dict[str, object], raw)


def _capacity_budget(plan: dict[str, object]) -> CapacityBudget:
    raw = plan.get("capacity_budget")
    if not isinstance(raw, dict):
        raise FundingAcquisitionError("funding plan has no capacity budget")
    try:
        return CapacityBudget(**raw)
    except (TypeError, PublicationError) as error:
        raise FundingAcquisitionError("funding capacity budget is invalid") from error


def _validate_registry_coverage(
    registry: VerifiedInstrumentRegistry,
    batch: CanonicalFundingBatch,
) -> None:
    by_id = {item.instrument_id: item for item in registry.snapshots}
    identifiers = set(batch.table.column("instrument_id").to_pylist())
    for identifier in identifiers:
        snapshot = by_id.get(identifier)
        if snapshot is None:
            raise FundingAcquisitionError(
                f"funding batch instrument_id is absent from registry: {identifier}"
            )
        mask = pc.equal(batch.table.column("instrument_id"), identifier)
        bounds = cast(
            dict[str, int],
            pc.min_max(pc.filter(batch.table.column("funding_time_ms"), mask)).as_py(),
        )
        if bounds["min"] < snapshot.launch_time_ms:
            raise FundingAcquisitionError("funding batch begins before registry launch")
        if snapshot.delivery_time_ms is not None and bounds["max"] > snapshot.delivery_time_ms:
            raise FundingAcquisitionError("funding batch ends after registry delivery")


def load_verified_funding_publication_input(
    job_root: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
) -> VerifiedFundingPublicationInput:
    """Verify Landing and upstream evidence without probing the host or mutating storage."""

    completed = verify_completed_funding_job(job_root)
    manifest = _object(completed.manifest_path, name="funding manifest")
    plan = _object(completed.plan_path, name="funding plan")
    registry = load_verified_instrument_registry(instrument_registry_path)
    try:
        capacity_path, capacity, capacity_sha = load_verified_capacity_evidence(
            capacity_evidence_path
        )
    except HistoryAcquisitionError as error:
        raise FundingAcquisitionError(str(error)) from error
    if manifest.get("instrument_evidence_sha256") != registry.artifact_sha256:
        raise FundingAcquisitionError("funding manifest does not bind supplied registry")
    if manifest.get("capacity_evidence_sha256") != capacity_sha:
        raise FundingAcquisitionError("funding manifest does not bind supplied capacity evidence")
    if manifest.get("boundary_evidence_sha256") != completed.boundary_evidence_sha256:
        raise FundingAcquisitionError("funding manifest boundary evidence does not verify")
    budget = _capacity_budget(plan)
    try:
        expected_active = active_and_building_bytes_from_capacity(capacity)
    except HistoryAcquisitionError as error:
        raise FundingAcquisitionError(str(error)) from error
    if budget.active_and_building_bytes != expected_active:
        raise FundingAcquisitionError("funding capacity budget differs from accepted layout")
    batch = load_completed_funding_batch(completed.job_root)
    _validate_registry_coverage(registry, batch)
    return VerifiedFundingPublicationInput(
        completed=completed,
        registry=registry,
        capacity_evidence_path=capacity_path,
        capacity_evidence_sha256=capacity_sha,
        batch=batch,
        budget=budget,
        dataset_id=f"funding-{completed.manifest_sha256[:24]}",
    )


def funding_publication_spec(
    verified: VerifiedFundingPublicationInput,
    *,
    software_identity: str,
) -> FundingDatasetSpec:
    """Resolve deterministic canonical funding identity and evidence bindings."""

    if not SOFTWARE_IDENTITY_RE.fullmatch(software_identity):
        raise FundingAcquisitionError(
            "software_identity must be git:<40-character-lowercase-commit-sha>"
        )
    build_config_sha = canonical_sha256(
        {
            "canonical_layout": FUNDING_CANONICAL_LAYOUT_ID,
            "contract": FUNDING_HISTORY_PUBLICATION_CONTRACT,
            "dataset_id": verified.dataset_id,
            "funding_manifest_sha256": verified.completed.manifest_sha256,
            "semantic_version": "1.0.0",
            "software_identity": software_identity,
        }
    )
    source_evidence = tuple(
        dict.fromkeys(
            (
                verified.completed.manifest_sha256,
                verified.registry.artifact_sha256,
                verified.completed.boundary_evidence_sha256,
            )
        )
    )
    return FundingDatasetSpec(
        dataset_id=verified.dataset_id,
        semantic_version="1.0.0",
        parent_dataset_ids=(),
        source_evidence_sha256=source_evidence,
        coverage_evidence_sha256=verified.completed.manifest_sha256,
        boundary_evidence_sha256=verified.completed.boundary_evidence_sha256,
        capacity_evidence_sha256=verified.capacity_evidence_sha256,
        build_config_sha256=build_config_sha,
        software_identity=software_identity,
    )


def preflight_completed_funding_publication(
    store_root: Path,
    job_root: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    snapshot: HostSnapshot,
    *,
    now_ms: int,
    software_identity: str,
) -> ResolvedFundingPublication:
    """Verify all evidence and plan one immutable funding dataset without mutation."""

    verified = load_verified_funding_publication_input(
        job_root,
        instrument_registry_path,
        capacity_evidence_path,
    )
    plan = preflight_funding_dataset(
        store_root,
        funding_publication_spec(verified, software_identity=software_identity),
        verified.batch,
        verified.budget,
        snapshot,
        now_ms=now_ms,
    )
    return ResolvedFundingPublication(verified=verified, plan=plan)


def publish_preflighted_funding(
    resolved: ResolvedFundingPublication,
    snapshot_provider: Callable[[], HostSnapshot],
    now_ms: Callable[[], int],
) -> PublishedDataset:
    """Repeat current-host observation and invoke receipt-last funding publication."""

    fresh_snapshot = snapshot_provider()
    committed_at_ms = now_ms()
    return publish_funding_dataset(
        resolved.plan,
        fresh_snapshot,
        committed_at_ms=committed_at_ms,
    )
