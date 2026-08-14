"""Offline Gate 2 fault injection for stale canonical write outputs and catalog locks."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from grid_contracts.canonical import canonical_sha256
from grid_contracts.market import Candle1m, DatasetType, FundingEvent
from grid_data.evidence import publish_evidence
from grid_market_store import (
    MIN_OPERATING_RESERVE_BYTES,
    CandleDatasetSpec,
    CapacityBudget,
    FundingDatasetSpec,
    HostSnapshot,
    PublicationError,
    build_canonical_candle_batch,
    build_canonical_funding_batch,
    preflight_candle_compaction,
    preflight_candle_dataset,
    preflight_funding_dataset,
    publish_candle_dataset,
    verify_committed_candle_dataset,
)
from grid_market_store.catalog import CatalogError, preflight_catalog_registration

EVIDENCE_CONTRACT: Final = "grid.phase2-stale-output-fault-injection/v1"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
JANUARY_1_2026_MS: Final = 1_767_225_600_000
MARKER_BYTES: Final = b"preserve-stale-evidence-v1\n"


class StaleOutputFaultInjectionError(RuntimeError):
    """A production preflight did not preserve and reject an injected stale marker."""


@dataclass(frozen=True, slots=True)
class InjectedCase:
    case_id: str
    boundary: str
    marker_kind: str
    expected_error_text: str
    marker_path: Path
    target_path: Path
    invoke: Callable[[], object]


def _snapshot(root: Path, *, observed_at_ms: int) -> HostSnapshot:
    return HostSnapshot(
        observed_at_ms=observed_at_ms,
        memory_total_bytes=16 * 1024**3,
        memory_available_bytes=8 * 1024**3,
        storage_kind="nvme",
        storage_device_id="stale-output-fixture-nvme",
        volume_root=root.resolve(),
        volume_free_bytes=200 * 1024**3,
    )


def _budget() -> CapacityBudget:
    return CapacityBudget(
        active_and_building_bytes=0,
        rest_staging_bytes=0,
        operating_reserve_bytes=MIN_OPERATING_RESERVE_BYTES,
    )


def _candle(timestamp: int, *, ingestion_id: str) -> Candle1m:
    return Candle1m(
        category="linear",
        instrument_id=9,
        open_time_ms=timestamp,
        open=Decimal("100"),
        high=Decimal("102"),
        low=Decimal("99"),
        close=Decimal("101"),
        volume=Decimal("10"),
        turnover=Decimal("1000"),
        source_id="offline-fixture/v1",
        ingestion_id=ingestion_id,
    )


def _funding(timestamp: int) -> FundingEvent:
    return FundingEvent(
        category="linear",
        instrument_id=9,
        funding_time_ms=timestamp,
        funding_rate=Decimal("0.0001"),
        funding_interval_minutes=480,
        source_id="offline-fixture/v1",
        ingestion_id="funding-stale-output-fixture",
    )


def _candle_spec(dataset_id: str, *, parents: tuple[str, ...] = ()) -> CandleDatasetSpec:
    return CandleDatasetSpec(
        dataset_id=dataset_id,
        semantic_version="1.0.0",
        parent_dataset_ids=parents,
        source_evidence_sha256=("a" * 64,),
        coverage_evidence_sha256="a" * 64,
        capacity_evidence_sha256="b" * 64,
        build_config_sha256=canonical_sha256({"dataset_id": dataset_id}),
        software_identity="offline-stale-output-fixture@1",
    )


def _funding_spec(dataset_id: str) -> FundingDatasetSpec:
    return FundingDatasetSpec(
        dataset_id=dataset_id,
        semantic_version="1.0.0",
        parent_dataset_ids=(),
        source_evidence_sha256=("a" * 64, "c" * 64),
        coverage_evidence_sha256="a" * 64,
        boundary_evidence_sha256="c" * 64,
        capacity_evidence_sha256="b" * 64,
        build_config_sha256=canonical_sha256({"dataset_id": dataset_id}),
        software_identity="offline-stale-output-fixture@1",
    )


def _publish_candle_parent(
    root: Path,
    store: Path,
    *,
    dataset_id: str,
    timestamp: int,
    clock_ms: int,
) -> Path:
    plan = preflight_candle_dataset(
        store,
        _candle_spec(dataset_id),
        build_canonical_candle_batch(
            (_candle(timestamp, ingestion_id=dataset_id),),
            DatasetType.TRADE_KLINE_1M,
        ),
        _budget(),
        _snapshot(root, observed_at_ms=clock_ms),
        now_ms=clock_ms + 1,
    )
    published = publish_candle_dataset(
        plan,
        _snapshot(root, observed_at_ms=clock_ms + 2),
        committed_at_ms=clock_ms + 3,
    )
    return published.dataset_root


def _assert_case(case: InjectedCase) -> dict[str, object]:
    case.marker_path.parent.mkdir(parents=True, exist_ok=True)
    case.marker_path.write_bytes(MARKER_BYTES)
    detected = False
    error_class = ""
    try:
        case.invoke()
    except (CatalogError, PublicationError) as error:
        detected = case.expected_error_text in str(error)
        error_class = type(error).__name__
    if not detected:
        raise StaleOutputFaultInjectionError(
            f"{case.case_id} did not fail with the expected stale-output classification"
        )
    if case.marker_path.read_bytes() != MARKER_BYTES:
        raise StaleOutputFaultInjectionError(f"{case.case_id} changed its injected marker")
    if case.target_path.exists():
        raise StaleOutputFaultInjectionError(f"{case.case_id} mutated its target")
    return {
        "boundary": case.boundary,
        "case_id": case.case_id,
        "detected": True,
        "error_class": error_class,
        "marker_kind": case.marker_kind,
        "marker_preserved": True,
        "target_mutated": False,
    }


def _cases(root: Path) -> tuple[InjectedCase, ...]:
    candle_store = root / "candle-publication-store"
    candle_batch = build_canonical_candle_batch(
        (_candle(JANUARY_1_2026_MS, ingestion_id="candle-publication"),),
        DatasetType.TRADE_KLINE_1M,
    )
    candle_spec = _candle_spec("trade-1m-stale-publication")
    candle_plan = preflight_candle_dataset(
        candle_store,
        candle_spec,
        candle_batch,
        _budget(),
        _snapshot(root, observed_at_ms=1_000),
        now_ms=1_001,
    )

    funding_store = root / "funding-publication-store"
    funding_batch = build_canonical_funding_batch((_funding(JANUARY_1_2026_MS),))
    funding_spec = _funding_spec("funding-stale-publication")
    funding_plan = preflight_funding_dataset(
        funding_store,
        funding_spec,
        funding_batch,
        _budget(),
        _snapshot(root, observed_at_ms=2_000),
        now_ms=2_001,
    )

    compaction_store = root / "compaction-store"
    first_root = _publish_candle_parent(
        root,
        compaction_store,
        dataset_id="trade-1m-stale-parent-a",
        timestamp=JANUARY_1_2026_MS,
        clock_ms=3_000,
    )
    second_root = _publish_candle_parent(
        root,
        compaction_store,
        dataset_id="trade-1m-stale-parent-b",
        timestamp=JANUARY_1_2026_MS + 60_000,
        clock_ms=3_010,
    )
    parent_hashes = tuple(
        verify_committed_candle_dataset(path).receipt.manifest_sha256
        for path in (first_root, second_root)
    )
    compaction_spec = CandleDatasetSpec(
        dataset_id="trade-1m-stale-compaction",
        semantic_version="1.0.0",
        parent_dataset_ids=("trade-1m-stale-parent-a", "trade-1m-stale-parent-b"),
        source_evidence_sha256=parent_hashes,
        coverage_evidence_sha256=parent_hashes[0],
        capacity_evidence_sha256="b" * 64,
        build_config_sha256=canonical_sha256({"boundary": "candle-compaction"}),
        software_identity="offline-stale-output-fixture@1",
    )
    compaction_plan = preflight_candle_compaction(
        compaction_store,
        (first_root, second_root),
        compaction_spec,
        _budget(),
        _snapshot(root, observed_at_ms=3_020),
        now_ms=3_021,
    )

    catalog_building_store = root / "catalog-building-store"
    catalog_building_store.mkdir()
    catalog_building = catalog_building_store / "catalog" / ".canonical.duckdb.building"
    catalog_building_target = catalog_building_store / "catalog" / "canonical.duckdb"

    catalog_lock_store = root / "catalog-lock-store"
    catalog_lock_store.mkdir()
    catalog_lock = catalog_lock_store / "catalog" / ".canonical.duckdb.lock"
    catalog_lock_target = catalog_lock_store / "catalog" / "canonical.duckdb"

    return (
        InjectedCase(
            case_id="canonical-candle-publication-building",
            boundary="canonical-candle-publication",
            marker_kind="building-directory-marker",
            expected_error_text="stale building output detected",
            marker_path=candle_plan.paths.building_root / "injected.marker",
            target_path=candle_plan.paths.dataset_root,
            invoke=lambda: preflight_candle_dataset(
                candle_store,
                candle_spec,
                candle_batch,
                _budget(),
                _snapshot(root, observed_at_ms=1_004),
                now_ms=1_005,
            ),
        ),
        InjectedCase(
            case_id="canonical-funding-publication-building",
            boundary="canonical-funding-publication",
            marker_kind="building-directory-marker",
            expected_error_text="stale building output detected",
            marker_path=funding_plan.paths.building_root / "injected.marker",
            target_path=funding_plan.paths.dataset_root,
            invoke=lambda: preflight_funding_dataset(
                funding_store,
                funding_spec,
                funding_batch,
                _budget(),
                _snapshot(root, observed_at_ms=2_004),
                now_ms=2_005,
            ),
        ),
        InjectedCase(
            case_id="canonical-candle-compaction-building",
            boundary="canonical-candle-compaction",
            marker_kind="building-directory-marker",
            expected_error_text="stale building output detected",
            marker_path=compaction_plan.paths.building_root / "injected.marker",
            target_path=compaction_plan.paths.dataset_root,
            invoke=lambda: preflight_candle_compaction(
                compaction_store,
                (first_root, second_root),
                compaction_spec,
                _budget(),
                _snapshot(root, observed_at_ms=3_024),
                now_ms=3_025,
            ),
        ),
        InjectedCase(
            case_id="catalog-registration-building",
            boundary="canonical-catalog-registration",
            marker_kind="catalog-building-file",
            expected_error_text="stale catalog building output detected",
            marker_path=catalog_building,
            target_path=catalog_building_target,
            invoke=lambda: preflight_catalog_registration(
                ("trade-1m-unused-fixture",),
                catalog_building_store,
                catalog_building_target,
                software_identity=f"git:{'d' * 40}",
            ),
        ),
        InjectedCase(
            case_id="catalog-registration-lock",
            boundary="canonical-catalog-registration",
            marker_kind="catalog-write-lock",
            expected_error_text="concurrent or stale catalog write lock detected",
            marker_path=catalog_lock,
            target_path=catalog_lock_target,
            invoke=lambda: preflight_catalog_registration(
                ("trade-1m-unused-fixture",),
                catalog_lock_store,
                catalog_lock_target,
                software_identity=f"git:{'d' * 40}",
            ),
        ),
    )


def build_stale_output_fault_injection_evidence(
    *,
    implementation_identity: str,
    generated_at_utc: str,
) -> dict[str, object]:
    """Exercise production preflights in a temporary offline store and return sanitized proof."""

    if not SOFTWARE_IDENTITY_RE.fullmatch(implementation_identity):
        raise StaleOutputFaultInjectionError(
            "implementation identity must be git:<40-character-lowercase-commit-sha>"
        )
    if not generated_at_utc.endswith("Z"):
        raise StaleOutputFaultInjectionError("generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(generated_at_utc.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise StaleOutputFaultInjectionError("generated_at_utc is invalid") from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise StaleOutputFaultInjectionError("generated_at_utc must be UTC")
    with TemporaryDirectory(prefix="grid-stale-output-") as temporary:
        results = [_assert_case(case) for case in _cases(Path(temporary))]
    payload: dict[str, object] = {
        "assurances": {
            "injected_markers_preserved": True,
            "network_request_performed": False,
            "production_preflight_functions_exercised": True,
            "private_or_live_capability_used": False,
            "target_mutation_observed": False,
            "temporary_fixture_removed": True,
        },
        "bindings": {"implementation_identity": implementation_identity},
        "cases": results,
        "evidence_schema": EVIDENCE_CONTRACT,
        "generated_at_utc": generated_at_utc,
        "measurement": {
            "case_count": len(results),
            "detected_count": sum(bool(item["detected"]) for item in results),
            "marker_preserved_count": sum(bool(item["marker_preserved"]) for item in results),
            "target_mutation_count": sum(bool(item["target_mutated"]) for item in results),
        },
        "scope": {
            "canonical_candle_compaction": True,
            "canonical_candle_publication": True,
            "canonical_catalog_registration": True,
            "canonical_funding_publication": True,
        },
        "status": "verified-stale-output-fault-injection",
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_market_values": False,
            "evidence_contains_runtime_paths": False,
            "runtime_fixture_committed_to_git": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation-identity", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_stale_output_fault_injection_evidence(
        implementation_identity=args.implementation_identity,
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    artifact, receipt = publish_evidence(args.output, payload)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "case_count": payload["measurement"]["case_count"],  # type: ignore[index]
                "receipt": str(receipt),
                "status": payload["status"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
