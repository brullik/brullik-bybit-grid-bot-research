"""GitHub-safe aggregate evidence for a verified candle-gap repair execution."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Final, cast

from grid_contracts.canonical import canonical_sha256

from grid_data.evidence import verify_evidence
from grid_data.history_acquisition import HistoryAcquisitionError
from grid_data.history_repair_execution import VerifiedRepairExecution

CANDLE_REPAIR_EXECUTION_PUBLIC_CONTRACT: Final = "grid.bybit-1m-gap-repair-execution-public/v1"


def _generated_at(value: str) -> str:
    if not value.endswith("Z"):
        raise HistoryAcquisitionError("generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise HistoryAcquisitionError("generated_at_utc is invalid") from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise HistoryAcquisitionError("generated_at_utc must be UTC")
    return value


def _object(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryAcquisitionError("candle repair public evidence cannot be loaded") from error
    if not isinstance(raw, dict):
        raise HistoryAcquisitionError("candle repair public evidence must be an object")
    return cast(dict[str, object], raw)


def build_candle_repair_execution_public_evidence(
    execution: VerifiedRepairExecution,
    *,
    generated_at_utc: str,
) -> dict[str, object]:
    """Project a private execution into identifier- and value-free aggregate evidence."""

    bindings = cast(dict[str, object], execution.payload["bindings"])
    limits = cast(dict[str, object], execution.payload["limits"])
    status = execution.payload["status"]
    passed = status == "passed"
    payload: dict[str, object] = {
        "bindings": {
            "canonical_parent_manifest_sha256": bindings["canonical_parent_manifest_sha256"],
            "capacity_evidence_sha256": bindings["capacity_evidence_sha256"],
            "coverage_audit_artifact_sha256": bindings["coverage_audit_artifact_sha256"],
            "coverage_audit_content_sha256": bindings["coverage_audit_content_sha256"],
            "instrument_registry_sha256": bindings["instrument_registry_sha256"],
            "original_history_manifest_sha256": bindings["original_history_manifest_sha256"],
            "private_execution_artifact_sha256": execution.artifact_sha256,
            "repair_plan_artifact_sha256": bindings["repair_plan_artifact_sha256"],
            "repair_plan_content_sha256": bindings["repair_plan_content_sha256"],
        },
        "contract": CANDLE_REPAIR_EXECUTION_PUBLIC_CONTRACT,
        "execution_software_identity": execution.payload["executor_software_identity"],
        "generated_at_utc": _generated_at(generated_at_utc),
        "limits": dict(limits),
        "limitations": [
            "Evidence covers only the exact gaps in the bound private repair plan.",
            "A remaining source gap is not accepted as an absent historical candle.",
            "Replacement publication, catalog registration, and Gate 2 remain separate "
            "transitions.",
        ],
        "outcome": {
            "classification": ("exact-gap-repair-completed" if passed else "source-gap-remains"),
            "parent_dataset_mutated": False,
            "replacement_dataset_published": False,
            "replacement_eligible": passed,
        },
        "status": status,
        "storage_policy": {
            "account_data_included": False,
            "credentials_included": False,
            "github_commit_eligible": True,
            "instrument_or_dataset_identifiers_included": False,
            "market_values_included": False,
            "minute_timestamps_included": False,
            "runtime_paths_included": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def verify_candle_repair_execution_public_evidence(
    evidence_path: Path,
    execution: VerifiedRepairExecution,
) -> dict[str, object]:
    """Verify and deterministically rebuild one committed public projection."""

    path = evidence_path.resolve()
    if not verify_evidence(path):
        raise HistoryAcquisitionError(
            "candle repair public execution evidence receipt does not verify"
        )
    stored = _object(path)
    embedded = stored.get("content_sha256")
    hash_input = dict(stored)
    hash_input.pop("content_sha256", None)
    generated_at = stored.get("generated_at_utc")
    if (
        stored.get("contract") != CANDLE_REPAIR_EXECUTION_PUBLIC_CONTRACT
        or stored.get("status") not in ("passed", "blocked")
        or not isinstance(generated_at, str)
        or not isinstance(embedded, str)
        or embedded != canonical_sha256(hash_input)
    ):
        raise HistoryAcquisitionError("candle repair public execution evidence identity is invalid")
    recomputed = build_candle_repair_execution_public_evidence(
        execution,
        generated_at_utc=generated_at,
    )
    if recomputed != stored:
        raise HistoryAcquisitionError(
            "candle repair public execution evidence no longer matches runtime inputs"
        )
    return stored
