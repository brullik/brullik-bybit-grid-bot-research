"""Evidence-bound immutable compaction for canonical one-minute fragments."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, cast

from grid_contracts.canonical import canonical_sha256
from grid_contracts.market import DatasetType
from grid_market_store import (
    CANONICAL_LAYOUT_ID,
    COMPACTION_CALIBRATION_ALGORITHM,
    TARGET_FILE_SIZE_BYTES,
    CandleCompactionPlan,
    CandleDatasetSpec,
    CapacityBudget,
    HostSnapshot,
    PublishedDataset,
    preflight_candle_compaction,
    publish_compacted_candle_dataset,
    verify_committed_candle_dataset,
    verify_compacted_candle_dataset,
)

from grid_data.evidence import verify_evidence
from grid_data.history_publication import SOFTWARE_IDENTITY_RE
from grid_data.history_request import (
    active_and_building_bytes_from_capacity,
    load_verified_capacity_evidence,
)

COMPACTION_EVIDENCE_CONTRACT: Final = "grid.canonical-1m-compaction/v1"
COMPACTION_BUILD_CONTRACT: Final = "grid.canonical-1m-compaction-build/v1"
DATASET_ID_RE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")


class HistoryCompactionError(RuntimeError):
    """Canonical history fragments cannot be compacted safely."""


@dataclass(frozen=True, slots=True)
class ResolvedHistoryCompaction:
    capacity_evidence_sha256: str
    plan: CandleCompactionPlan


def _object(path: Path, *, name: str) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryCompactionError(f"{name} cannot be loaded") from error
    if not isinstance(raw, dict):
        raise HistoryCompactionError(f"{name} must be an object")
    return cast(dict[str, object], raw)


def _generated_at(value: str) -> str:
    if not value.endswith("Z"):
        raise HistoryCompactionError("generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise HistoryCompactionError("generated_at_utc is invalid") from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise HistoryCompactionError("generated_at_utc must be UTC")
    return value


def _output_dataset_id(dataset_type: DatasetType, identity_sha256: str) -> str:
    prefix = "trade-1m" if dataset_type is DatasetType.TRADE_KLINE_1M else "mark-1m"
    return f"{prefix}-compact-{identity_sha256[:24]}"


def preflight_history_compaction(
    dataset_ids: tuple[str, ...],
    capacity_evidence_path: Path,
    store_root: Path,
    snapshot: HostSnapshot,
    *,
    now_ms: int,
    software_identity: str,
) -> ResolvedHistoryCompaction:
    """Resolve immutable parents and run the complete no-mutation compaction preflight."""

    if not SOFTWARE_IDENTITY_RE.fullmatch(software_identity):
        raise HistoryCompactionError(
            "software_identity must be git:<40-character-lowercase-commit-sha>"
        )
    if not dataset_ids or len(dataset_ids) != len(set(dataset_ids)):
        raise HistoryCompactionError("compaction dataset identities must be non-empty and unique")
    ordered_ids = tuple(sorted(dataset_ids))
    if any(not DATASET_ID_RE.fullmatch(dataset_id) for dataset_id in ordered_ids):
        raise HistoryCompactionError("compaction dataset identity is unsafe")
    store = store_root.resolve()
    parent_roots = tuple(store / "datasets" / dataset_id for dataset_id in ordered_ids)
    parents = tuple(verify_committed_candle_dataset(root) for root in parent_roots)
    parent_types = {parent.manifest.dataset_type for parent in parents}
    if len(parent_types) != 1:
        raise HistoryCompactionError("compaction parents must share one candle dataset type")
    parent_bindings = [
        {
            "dataset_id": parent.manifest.dataset_id,
            "manifest_sha256": parent.receipt.manifest_sha256,
        }
        for parent in parents
    ]
    coverage_sha = canonical_sha256(
        {
            "contract": COMPACTION_BUILD_CONTRACT,
            "parent_manifests": parent_bindings,
        }
    )
    identity_sha = canonical_sha256(
        {
            "canonical_layout": CANONICAL_LAYOUT_ID,
            "calibration_algorithm": COMPACTION_CALIBRATION_ALGORITHM,
            "contract": COMPACTION_BUILD_CONTRACT,
            "parent_manifests": parent_bindings,
            "software_identity": software_identity,
            "target_file_bytes": TARGET_FILE_SIZE_BYTES,
        }
    )
    dataset_id = _output_dataset_id(next(iter(parent_types)), identity_sha)
    build_config_sha = canonical_sha256(
        {
            "canonical_layout": CANONICAL_LAYOUT_ID,
            "contract": COMPACTION_BUILD_CONTRACT,
            "dataset_id": dataset_id,
            "parent_manifests": parent_bindings,
            "semantic_version": "1.0.0",
            "software_identity": software_identity,
            "target_file_bytes": TARGET_FILE_SIZE_BYTES,
            "tail_policy": "only-final-file-may-be-below-row-target",
        }
    )
    _capacity_path, capacity, capacity_sha = load_verified_capacity_evidence(capacity_evidence_path)
    source_digests = tuple(
        dict.fromkeys(
            (
                coverage_sha,
                *(parent.receipt.manifest_sha256 for parent in parents),
            )
        )
    )
    spec = CandleDatasetSpec(
        dataset_id=dataset_id,
        semantic_version="1.0.0",
        parent_dataset_ids=ordered_ids,
        source_evidence_sha256=source_digests,
        coverage_evidence_sha256=coverage_sha,
        capacity_evidence_sha256=capacity_sha,
        build_config_sha256=build_config_sha,
        software_identity=software_identity,
    )
    plan = preflight_candle_compaction(
        store,
        parent_roots,
        spec,
        CapacityBudget(
            active_and_building_bytes=active_and_building_bytes_from_capacity(capacity),
            rest_staging_bytes=0,
        ),
        snapshot,
        now_ms=now_ms,
    )
    return ResolvedHistoryCompaction(
        capacity_evidence_sha256=capacity_sha,
        plan=plan,
    )


def publish_preflighted_compaction(
    resolved: ResolvedHistoryCompaction,
    snapshot_provider: Callable[[], HostSnapshot],
    now_ms: Callable[[], int],
) -> PublishedDataset:
    """Repeat the host observation and atomically publish the compacted child."""

    return publish_compacted_candle_dataset(
        resolved.plan,
        snapshot_provider(),
        committed_at_ms=now_ms(),
    )


def build_compaction_evidence(
    resolved: ResolvedHistoryCompaction,
    published: PublishedDataset,
    *,
    generated_at_utc: str,
) -> dict[str, object]:
    """Build a GitHub-safe proof of immutable, logically identical compaction."""

    verified = verify_compacted_candle_dataset(published.dataset_root)
    plan = resolved.plan
    if (
        verified.receipt.manifest_sha256 != published.receipt.manifest_sha256
        or verified.manifest.dataset_id != plan.spec.dataset_id
        or verified.manifest.parent_dataset_ids != plan.spec.parent_dataset_ids
    ):
        raise HistoryCompactionError("compaction publication differs from its preflight")
    audit = _object(verified.audit_path, name="compaction audit")
    facts = audit.get("compaction")
    if not isinstance(facts, dict):
        raise HistoryCompactionError("compaction audit has no file facts")
    payload: dict[str, object] = {
        "bindings": {
            "capacity_evidence_sha256": resolved.capacity_evidence_sha256,
            "compacted_manifest_sha256": verified.receipt.manifest_sha256,
            "input_table_sha256": plan.input_table_sha256,
            "output_table_sha256": audit.get("output_table_sha256"),
            "parent_manifests": [
                {
                    "dataset_id": parent.manifest.dataset_id,
                    "manifest_sha256": parent.receipt.manifest_sha256,
                }
                for parent in plan.parents
            ],
        },
        "calibration": audit.get("calibration"),
        "compaction": {
            "conflicting_key_count": 0,
            "duplicate_key_count": 0,
            "input_file_count": plan.input_file_count,
            "logical_table_equal": True,
            "output_file_count": len(verified.manifest.files),
            "output_total_bytes": facts.get("output_total_bytes"),
            "row_count": verified.manifest.row_count,
            "rows_per_file_target": plan.rows_per_file_target,
            "tail_file_count": facts.get("tail_file_count"),
            "target_band_non_tail_file_count": facts.get("target_band_non_tail_file_count"),
            "target_file_bytes": TARGET_FILE_SIZE_BYTES,
        },
        "compaction_software_identity": verified.manifest.software_identity,
        "contract": COMPACTION_EVIDENCE_CONTRACT,
        "generated_at_utc": _generated_at(generated_at_utc),
        "limitations": [
            "Compaction proves only the supplied immutable month/bucket parent union.",
            "Target attainment remains observable per file and is not inferred from metadata.",
            "This transition does not register a catalog entry or close Gate 2.",
        ],
        "lineage": {
            "compacted_dataset_id": verified.manifest.dataset_id,
            "parent_dataset_ids": list(verified.manifest.parent_dataset_ids),
            "parent_datasets_mutated": False,
        },
        "status": "passed",
        "storage_policy": {
            "account_data_included": False,
            "market_values_included": False,
            "runtime_paths_included": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def verify_compaction_evidence(
    evidence_path: Path,
    resolved: ResolvedHistoryCompaction,
    published: PublishedDataset,
) -> dict[str, object]:
    """Verify receipt/content hash and rebuild the compaction proof."""

    path = evidence_path.resolve()
    if not verify_evidence(path):
        raise HistoryCompactionError("compaction evidence receipt does not verify")
    stored = _object(path, name="compaction evidence")
    embedded_hash = stored.get("content_sha256")
    hash_input = dict(stored)
    hash_input.pop("content_sha256", None)
    generated_at = stored.get("generated_at_utc")
    if (
        stored.get("contract") != COMPACTION_EVIDENCE_CONTRACT
        or stored.get("status") != "passed"
        or not isinstance(generated_at, str)
        or not isinstance(embedded_hash, str)
        or embedded_hash != canonical_sha256(hash_input)
    ):
        raise HistoryCompactionError("compaction evidence identity or content hash is invalid")
    recomputed = build_compaction_evidence(
        resolved,
        published,
        generated_at_utc=generated_at,
    )
    if recomputed != stored:
        raise HistoryCompactionError("compaction evidence no longer matches runtime inputs")
    return stored
