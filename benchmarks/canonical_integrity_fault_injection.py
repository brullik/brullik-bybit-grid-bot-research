"""Offline orphan and partial-write fault injection for canonical dataset verifiers."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Final

from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_contracts.market import Candle1m, DatasetType, FundingEvent
from grid_data.evidence import publish_evidence
from grid_market_store import (
    MIN_OPERATING_RESERVE_BYTES,
    CandleDatasetSpec,
    CapacityBudget,
    FundingDatasetSpec,
    HostSnapshot,
    PublicationError,
    PublishedDataset,
    build_canonical_candle_batch,
    build_canonical_funding_batch,
    preflight_candle_dataset,
    preflight_funding_dataset,
    publish_candle_dataset,
    publish_funding_dataset,
    verify_committed_candle_dataset,
    verify_committed_funding_dataset,
)

EVIDENCE_CONTRACT: Final = "grid.phase2-canonical-integrity-fault-injection/v1"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
JANUARY_1_2026_MS: Final = 1_767_225_600_000
ORPHAN_BYTES: Final = b"preserve-orphan-integrity-evidence-v1\n"


class CanonicalIntegrityFaultInjectionError(RuntimeError):
    """A production verifier did not reject or preserve an injected integrity failure."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CanonicalIntegrityFaultInjectionError(message)


def _snapshot(root: Path, *, observed_at_ms: int) -> HostSnapshot:
    return HostSnapshot(
        observed_at_ms=observed_at_ms,
        memory_total_bytes=16 * 1024**3,
        memory_available_bytes=8 * 1024**3,
        storage_kind="nvme",
        storage_device_id="canonical-integrity-fixture-nvme",
        volume_root=root.resolve(),
        volume_free_bytes=200 * 1024**3,
    )


def _budget() -> CapacityBudget:
    return CapacityBudget(
        active_and_building_bytes=0,
        rest_staging_bytes=0,
        operating_reserve_bytes=MIN_OPERATING_RESERVE_BYTES,
    )


def _candle(timestamp: int) -> Candle1m:
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
        source_id="offline-integrity-fixture/v1",
        ingestion_id="canonical-integrity-fixture",
    )


def _funding(timestamp: int, rate: str) -> FundingEvent:
    return FundingEvent(
        category="linear",
        instrument_id=9,
        funding_time_ms=timestamp,
        funding_rate=Decimal(rate),
        funding_interval_minutes=480,
        source_id="offline-integrity-fixture/v1",
        ingestion_id="canonical-integrity-fixture",
    )


def _publish_pristine_candle(root: Path) -> PublishedDataset:
    spec = CandleDatasetSpec(
        dataset_id="trade-1m-integrity-fixture",
        semantic_version="1.0.0",
        parent_dataset_ids=(),
        source_evidence_sha256=("a" * 64,),
        coverage_evidence_sha256="a" * 64,
        capacity_evidence_sha256="b" * 64,
        build_config_sha256="c" * 64,
        software_identity="offline-canonical-integrity-fixture@1",
    )
    batch = build_canonical_candle_batch(
        (
            _candle(JANUARY_1_2026_MS),
            _candle(JANUARY_1_2026_MS + 60_000),
        ),
        DatasetType.TRADE_KLINE_1M,
    )
    plan = preflight_candle_dataset(
        root / "pristine-candle-store",
        spec,
        batch,
        _budget(),
        _snapshot(root, observed_at_ms=1_000),
        now_ms=1_001,
    )
    return publish_candle_dataset(
        plan,
        _snapshot(root, observed_at_ms=1_002),
        committed_at_ms=1_003,
    )


def _publish_pristine_funding(root: Path) -> PublishedDataset:
    spec = FundingDatasetSpec(
        dataset_id="funding-integrity-fixture",
        semantic_version="1.0.0",
        parent_dataset_ids=(),
        source_evidence_sha256=("a" * 64, "d" * 64),
        coverage_evidence_sha256="a" * 64,
        boundary_evidence_sha256="d" * 64,
        capacity_evidence_sha256="b" * 64,
        build_config_sha256="c" * 64,
        software_identity="offline-canonical-integrity-fixture@1",
    )
    batch = build_canonical_funding_batch(
        (
            _funding(JANUARY_1_2026_MS, "0.0001"),
            _funding(JANUARY_1_2026_MS + 480 * 60_000, "-0.0002"),
        )
    )
    plan = preflight_funding_dataset(
        root / "pristine-funding-store",
        spec,
        batch,
        _budget(),
        _snapshot(root, observed_at_ms=2_000),
        now_ms=2_001,
    )
    return publish_funding_dataset(
        plan,
        _snapshot(root, observed_at_ms=2_002),
        committed_at_ms=2_003,
    )


def _clone_dataset(pristine: PublishedDataset, case_root: Path) -> Path:
    target = case_root / pristine.dataset_root.name
    shutil.copytree(pristine.dataset_root, target)
    return target


def _tree_fingerprint(root: Path) -> str:
    entries: list[dict[str, object]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            entries.append({"kind": "directory", "path": relative})
        elif path.is_file():
            entries.append(
                {
                    "kind": "file",
                    "path": relative,
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
            )
        else:
            raise CanonicalIntegrityFaultInjectionError("fixture contains an unsafe path type")
    return canonical_sha256(entries)


def _verify_injected_case(
    *,
    case_id: str,
    dataset_type: str,
    injected_condition: str,
    root: Path,
    expected_error_text: str,
) -> dict[str, object]:
    before = _tree_fingerprint(root)
    detected = False
    error_class = ""
    try:
        if dataset_type == "candle":
            verify_committed_candle_dataset(root)
        else:
            verify_committed_funding_dataset(root)
    except PublicationError as error:
        detected = expected_error_text in str(error)
        error_class = type(error).__name__
    after = _tree_fingerprint(root)
    filesystem_state_preserved = before == after
    _require(detected, f"{case_id} did not produce the expected fail-closed classification")
    _require(filesystem_state_preserved, f"{case_id} changed the injected fixture during verify")
    return {
        "case_id": case_id,
        "dataset_type": dataset_type,
        "detected": True,
        "error_class": error_class,
        "filesystem_state_preserved": True,
        "injected_condition": injected_condition,
    }


def _run_cases(root: Path) -> list[dict[str, object]]:
    candle = _publish_pristine_candle(root)
    funding = _publish_pristine_funding(root)
    cases: list[dict[str, object]] = []
    for dataset_type, pristine, expected_paths_error in (
        ("candle", candle, "committed dataset contains orphan or missing files"),
        ("funding", funding, "committed funding dataset contains orphan or missing paths"),
    ):
        prefix = "canonical-candle" if dataset_type == "candle" else "canonical-funding"

        orphan_root = _clone_dataset(pristine, root / "cases" / f"{prefix}-orphan-file")
        (orphan_root / "unexpected.integrity-marker").write_bytes(ORPHAN_BYTES)
        cases.append(
            _verify_injected_case(
                case_id=f"{prefix}-orphan-file",
                dataset_type=dataset_type,
                injected_condition="orphan-file",
                root=orphan_root,
                expected_error_text=expected_paths_error,
            )
        )

        missing_parquet_root = _clone_dataset(
            pristine, root / "cases" / f"{prefix}-missing-parquet"
        )
        (missing_parquet_root / pristine.manifest.files[0].path).unlink()
        cases.append(
            _verify_injected_case(
                case_id=f"{prefix}-missing-parquet",
                dataset_type=dataset_type,
                injected_condition="missing-parquet",
                root=missing_parquet_root,
                expected_error_text="dataset file hash or size mismatch",
            )
        )

        missing_receipt_root = _clone_dataset(
            pristine, root / "cases" / f"{prefix}-missing-completion-receipt"
        )
        (missing_receipt_root / "completion-receipt.json").unlink()
        cases.append(
            _verify_injected_case(
                case_id=f"{prefix}-missing-completion-receipt",
                dataset_type=dataset_type,
                injected_condition="missing-completion-receipt",
                root=missing_receipt_root,
                expected_error_text="dataset has no completion receipt and is not committed",
            )
        )
    return cases


def _verify_generated_at(generated_at_utc: str) -> None:
    _require(generated_at_utc.endswith("Z"), "generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(generated_at_utc.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise CanonicalIntegrityFaultInjectionError("generated_at_utc is invalid") from error
    offset = parsed.utcoffset()
    _require(offset is not None and offset.total_seconds() == 0, "generated_at_utc must be UTC")


def build_canonical_integrity_fault_injection_evidence(
    *,
    implementation_identity: str,
    generated_at_utc: str,
) -> dict[str, Any]:
    """Exercise production canonical verifiers in an automatically removed temporary store."""

    _require(
        SOFTWARE_IDENTITY_RE.fullmatch(implementation_identity) is not None,
        "implementation identity must be git:<40-character-lowercase-commit-sha>",
    )
    _verify_generated_at(generated_at_utc)
    with TemporaryDirectory(prefix="grid-canonical-integrity-") as temporary:
        cases = _run_cases(Path(temporary))
    payload: dict[str, Any] = {
        "assurances": {
            "filesystem_state_preserved_during_verification": True,
            "network_request_performed": False,
            "private_or_live_capability_used": False,
            "production_verifier_functions_exercised": True,
            "retained_market_store_accessed": False,
            "temporary_fixture_removed": True,
        },
        "bindings": {"implementation_identity": implementation_identity},
        "cases": cases,
        "evidence_schema": EVIDENCE_CONTRACT,
        "generated_at_utc": generated_at_utc,
        "measurement": {
            "case_count": len(cases),
            "detected_count": sum(bool(item["detected"]) for item in cases),
            "filesystem_state_preserved_count": sum(
                bool(item["filesystem_state_preserved"]) for item in cases
            ),
        },
        "scope": {
            "canonical_candle_verifier": True,
            "canonical_funding_verifier": True,
            "missing_completion_receipt": True,
            "missing_parquet": True,
            "orphan_file": True,
        },
        "status": "verified-canonical-integrity-fault-injection",
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_dataset_or_instrument_identities": False,
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
    payload = build_canonical_integrity_fault_injection_evidence(
        implementation_identity=args.implementation_identity,
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    artifact, receipt = publish_evidence(args.output, payload)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "case_count": payload["measurement"]["case_count"],
                "receipt": str(receipt),
                "status": payload["status"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
