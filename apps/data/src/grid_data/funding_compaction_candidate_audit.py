"""Receipt-verified discovery of genuine ADR-0054 funding compaction candidates."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime
from itertools import combinations
from pathlib import Path, PurePosixPath
from typing import Final, Literal, cast

import pyarrow as pa  # type: ignore[import-untyped]
from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_market_store import (
    PublishedDataset,
    load_committed_funding_table,
    verify_committed_funding_dataset,
)

from grid_data.evidence import verify_evidence
from grid_data.funding_compaction import funding_union_problem
from grid_data.funding_publication import SOFTWARE_IDENTITY_RE

AUDIT_CONTRACT: Final = "grid.funding-compaction-candidate-audit/v1"
EVIDENCE_CONTRACT: Final = "grid.phase2-funding-compaction-candidate-audit/v1"
CANDIDATE_POLICY: Final = "receipt-verified-all-funding-parent-pairs-v1"
MAX_DATASETS: Final = 10_000
MAX_PAIRS: Final = 100_000

PairClassification = Literal[
    "duplicate-or-conflicting-keys",
    "eligible",
    "schema-mismatch",
    "unresolved-settlement-interval",
]
PAIR_CLASSIFICATIONS: Final = (
    "duplicate-or-conflicting-keys",
    "eligible",
    "schema-mismatch",
    "unresolved-settlement-interval",
)


class FundingCompactionCandidateAuditError(RuntimeError):
    """The local funding inventory cannot produce a trustworthy candidate audit."""


def _object(path: Path, *, name: str) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FundingCompactionCandidateAuditError(f"{name} cannot be loaded") from error
    if not isinstance(raw, dict):
        raise FundingCompactionCandidateAuditError(f"{name} must be an object")
    return cast(dict[str, object], raw)


def _generated_at(value: str) -> str:
    if not value.endswith("Z"):
        raise FundingCompactionCandidateAuditError("generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise FundingCompactionCandidateAuditError("generated_at_utc is invalid") from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise FundingCompactionCandidateAuditError("generated_at_utc must be UTC")
    return value


def _software_identity(value: str) -> str:
    if not SOFTWARE_IDENTITY_RE.fullmatch(value):
        raise FundingCompactionCandidateAuditError(
            "software identity must be git:<40-character-lowercase-commit-sha>"
        )
    return value


def _partition(parent: PublishedDataset) -> PurePosixPath:
    partitions = {PurePosixPath(item.path).parent for item in parent.manifest.files}
    if len(partitions) != 1:
        raise FundingCompactionCandidateAuditError(
            "every funding dataset must contain exactly one month/bucket partition"
        )
    return next(iter(partitions))


def _verified_inventory(
    store_root: Path,
) -> tuple[tuple[PublishedDataset, pa.Table, PurePosixPath], ...]:
    store = store_root.resolve()
    datasets_root = store / "datasets"
    if not datasets_root.is_dir() or datasets_root.is_symlink() or store.is_symlink():
        raise FundingCompactionCandidateAuditError(
            "market-store datasets root must be an existing non-symlink directory"
        )
    roots = tuple(
        sorted(
            (
                path
                for path in datasets_root.iterdir()
                if path.name.startswith("funding-") and path.is_dir()
            ),
            key=lambda path: path.name,
        )
    )
    if not roots:
        raise FundingCompactionCandidateAuditError("no canonical funding datasets were found")
    if len(roots) > MAX_DATASETS:
        raise FundingCompactionCandidateAuditError("funding dataset inventory exceeds hard bound")
    inventory: list[tuple[PublishedDataset, pa.Table, PurePosixPath]] = []
    for root in roots:
        if root.is_symlink():
            raise FundingCompactionCandidateAuditError("funding dataset roots cannot be symlinks")
        try:
            parent = verify_committed_funding_dataset(root)
            table = load_committed_funding_table(root)
        except (OSError, RuntimeError, ValueError) as error:
            raise FundingCompactionCandidateAuditError(
                "funding inventory contains an invalid or incomplete dataset"
            ) from error
        inventory.append((parent, table, _partition(parent)))
    return tuple(inventory)


def _pair_classification(left: pa.Table, right: pa.Table) -> PairClassification:
    if not left.schema.equals(right.schema, check_metadata=True):
        return "schema-mismatch"
    union = (
        pa.concat_tables((left, right))
        .sort_by([("instrument_id", "ascending"), ("funding_time_ms", "ascending")])
        .combine_chunks()
    )
    problem = funding_union_problem(union)
    return "eligible" if problem is None else problem


def build_funding_compaction_candidate_audit(
    store_root: Path,
    *,
    auditor_software_identity: str,
    generated_at_utc: str,
) -> dict[str, object]:
    """Scan every same-partition parent pair and retain detailed private diagnostics."""

    identity = _software_identity(auditor_software_identity)
    generated_at = _generated_at(generated_at_utc)
    inventory = _verified_inventory(store_root)
    groups: dict[PurePosixPath, list[tuple[PublishedDataset, pa.Table]]] = defaultdict(list)
    dataset_bindings: list[dict[str, str]] = []
    for parent, table, partition in inventory:
        groups[partition].append((parent, table))
        dataset_bindings.append(
            {
                "dataset_id": parent.manifest.dataset_id,
                "manifest_sha256": parent.receipt.manifest_sha256,
                "partition": partition.as_posix(),
            }
        )
    pair_count = sum(len(group) * (len(group) - 1) // 2 for group in groups.values())
    if pair_count > MAX_PAIRS:
        raise FundingCompactionCandidateAuditError(
            "funding candidate pair count exceeds hard bound"
        )
    pairs: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    for partition in sorted(groups, key=lambda item: item.as_posix()):
        group = sorted(groups[partition], key=lambda item: item[0].manifest.dataset_id)
        for left, right in combinations(group, 2):
            left_parent, left_table = left
            right_parent, right_table = right
            classification = _pair_classification(left_table, right_table)
            counts[classification] += 1
            parent_bindings = [
                {
                    "dataset_id": parent.manifest.dataset_id,
                    "manifest_sha256": parent.receipt.manifest_sha256,
                }
                for parent in (left_parent, right_parent)
            ]
            pairs.append(
                {
                    "classification": classification,
                    "pair_sha256": canonical_sha256(parent_bindings),
                    "parents": parent_bindings,
                    "partition": partition.as_posix(),
                }
            )
    classification_counts = {name: counts[name] for name in PAIR_CLASSIFICATIONS}
    eligible_count = classification_counts["eligible"]
    return {
        "auditor_software_identity": identity,
        "classification_counts": classification_counts,
        "contract": AUDIT_CONTRACT,
        "dataset_count": len(inventory),
        "generated_at_utc": generated_at,
        "multi_parent_partition_count": sum(len(group) > 1 for group in groups.values()),
        "pair_count": len(pairs),
        "pairs": pairs,
        "partition_count": len(groups),
        "policy": CANDIDATE_POLICY,
        "status": "eligible-candidates-observed" if eligible_count else "no-eligible-candidates",
        "store_state_sha256": canonical_sha256(dataset_bindings),
    }


def verify_funding_compaction_candidate_audit(
    audit_path: Path,
    store_root: Path,
) -> dict[str, object]:
    """Receipt-verify the private audit and reproduce it from the current immutable store."""

    path = audit_path.resolve()
    if not verify_evidence(path):
        raise FundingCompactionCandidateAuditError("candidate audit receipt verification failed")
    stored = _object(path, name="funding compaction candidate audit")
    identity = stored.get("auditor_software_identity")
    generated_at = stored.get("generated_at_utc")
    if not isinstance(identity, str) or not isinstance(generated_at, str):
        raise FundingCompactionCandidateAuditError("candidate audit identity fields are invalid")
    rebuilt = build_funding_compaction_candidate_audit(
        store_root,
        auditor_software_identity=identity,
        generated_at_utc=generated_at,
    )
    if stored != rebuilt:
        raise FundingCompactionCandidateAuditError(
            "candidate audit no longer matches the receipt-verified funding store"
        )
    return stored


def _integer(mapping: Mapping[str, object], name: str) -> int:
    value = mapping.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FundingCompactionCandidateAuditError(f"candidate audit {name} is invalid")
    return value


def build_funding_compaction_candidate_evidence(
    audit_path: Path,
    store_root: Path,
    *,
    publisher_software_identity: str,
) -> dict[str, object]:
    """Build a GitHub-safe aggregate without dataset, partition, time, or value identities."""

    publisher = _software_identity(publisher_software_identity)
    audit = verify_funding_compaction_candidate_audit(audit_path, store_root)
    raw_counts = audit.get("classification_counts")
    if not isinstance(raw_counts, dict) or set(raw_counts) != set(PAIR_CLASSIFICATIONS):
        raise FundingCompactionCandidateAuditError("candidate audit classifications are invalid")
    counts = {name: _integer(raw_counts, name) for name in PAIR_CLASSIFICATIONS}
    pair_count = _integer(audit, "pair_count")
    if sum(counts.values()) != pair_count:
        raise FundingCompactionCandidateAuditError("candidate audit pair arithmetic is invalid")
    eligible_count = counts["eligible"]
    payload: dict[str, object] = {
        "assurances": {
            "all_canonical_funding_datasets_receipt_verified": True,
            "all_same_partition_parent_pairs_classified": True,
            "duplicate_keys_never_deduplicated": True,
            "funding_values_or_timestamps_published": False,
            "parent_datasets_mutated": False,
            "private_or_live_capability_used": False,
        },
        "bindings": {
            "audit_artifact_sha256": sha256_file(audit_path.resolve()),
            "auditor_software_identity": audit["auditor_software_identity"],
            "publisher_software_identity": publisher,
            "store_state_sha256": audit["store_state_sha256"],
        },
        "classification_counts": counts,
        "evidence_schema": EVIDENCE_CONTRACT,
        "generated_at_utc": audit["generated_at_utc"],
        "inventory": {
            "dataset_count": _integer(audit, "dataset_count"),
            "multi_parent_partition_count": _integer(audit, "multi_parent_partition_count"),
            "pair_count": pair_count,
            "partition_count": _integer(audit, "partition_count"),
        },
        "limitations": [
            "Candidate discovery does not perform or qualify canonical funding compaction.",
            "A no-candidate result is valid only for the receipt-bound store state.",
            "The audit does not accept funding chronology, coverage, repair, catalog, or Gate 2.",
            "Detailed dataset and partition identities remain private runtime evidence.",
        ],
        "policy": CANDIDATE_POLICY,
        "status": (
            "verified-eligible-funding-compaction-candidates"
            if eligible_count
            else "verified-no-eligible-funding-compaction-candidates"
        ),
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_dataset_or_instrument_identities": False,
            "evidence_contains_funding_rates_or_timestamps": False,
            "evidence_contains_runtime_paths": False,
            "runtime_market_artifacts_committed_to_git": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def verify_funding_compaction_candidate_evidence(
    evidence_path: Path,
    audit_path: Path,
    store_root: Path,
) -> dict[str, object]:
    """Verify public evidence receipt, content hash, and current private audit binding."""

    path = evidence_path.resolve()
    if not verify_evidence(path):
        raise FundingCompactionCandidateAuditError("candidate evidence receipt verification failed")
    stored = _object(path, name="funding compaction candidate evidence")
    bindings = stored.get("bindings")
    if not isinstance(bindings, dict):
        raise FundingCompactionCandidateAuditError("candidate evidence bindings are invalid")
    publisher = bindings.get("publisher_software_identity")
    content_hash = stored.get("content_sha256")
    without_hash = dict(stored)
    without_hash.pop("content_sha256", None)
    if not isinstance(publisher, str) or content_hash != canonical_sha256(without_hash):
        raise FundingCompactionCandidateAuditError("candidate evidence identity or hash is invalid")
    rebuilt = build_funding_compaction_candidate_evidence(
        audit_path,
        store_root,
        publisher_software_identity=publisher,
    )
    if stored != rebuilt:
        raise FundingCompactionCandidateAuditError(
            "candidate evidence no longer matches its private audit"
        )
    return stored
