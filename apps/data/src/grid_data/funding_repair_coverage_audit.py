"""Post-publication source-parity and chronology audit for a funding repair child."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final, cast

from grid_contracts.canonical import canonical_sha256, sha256_file

from grid_data.evidence import verify_evidence
from grid_data.funding_acquisition import FundingAcquisitionError
from grid_data.funding_coverage_audit import (
    FundingCoverageAudit,
    build_verified_funding_coverage_audit,
)
from grid_data.funding_publication import (
    SOFTWARE_IDENTITY_RE,
    load_verified_funding_publication_input,
)
from grid_data.funding_repair_publication import (
    verify_committed_funding_repair,
    verify_funding_repair_replacement_evidence,
)

FUNDING_REPAIR_COVERAGE_AUDIT_CONTRACT: Final = "grid.canonical-funding-repair-coverage-audit/v1"


def _object(path: Path, *, name: str) -> dict[str, object]:
    try:
        raw = json.loads(path.resolve().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FundingAcquisitionError(f"{name} cannot be loaded") from error
    if not isinstance(raw, dict):
        raise FundingAcquisitionError(f"{name} must be an object")
    return cast(dict[str, object], raw)


def build_funding_repair_coverage_audit(
    repair_execution_path: Path,
    repair_plan_path: Path,
    original_coverage_audit_path: Path,
    original_job_root: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    store_root: Path,
    repair_staging_root: Path,
    replacement_evidence_path: Path,
    *,
    publisher_software_identity: str,
    audit_software_identity: str,
    generated_at_utc: str,
) -> FundingCoverageAudit:
    """Re-verify repair lineage and audit the exact original-plus-repair source union."""

    if not SOFTWARE_IDENTITY_RE.fullmatch(publisher_software_identity):
        raise FundingAcquisitionError(
            "publisher_software_identity must be git:<40-character-lowercase-commit-sha>"
        )
    if not SOFTWARE_IDENTITY_RE.fullmatch(audit_software_identity):
        raise FundingAcquisitionError(
            "audit_software_identity must be git:<40-character-lowercase-commit-sha>"
        )
    resolved = verify_committed_funding_repair(
        repair_execution_path,
        repair_plan_path,
        original_coverage_audit_path,
        original_job_root,
        instrument_registry_path,
        capacity_evidence_path,
        store_root,
        repair_staging_root,
        software_identity=publisher_software_identity,
    )
    published = resolved.published
    replacement = verify_funding_repair_replacement_evidence(
        replacement_evidence_path,
        resolved,
        published,
    )
    verified_original = load_verified_funding_publication_input(
        original_job_root,
        instrument_registry_path,
        capacity_evidence_path,
    )
    execution = resolved.verified_execution
    execution_bindings = cast(dict[str, object], execution.payload["bindings"])
    return build_verified_funding_coverage_audit(
        verified_original,
        published,
        resolved.batch.table,
        contract=FUNDING_REPAIR_COVERAGE_AUDIT_CONTRACT,
        bindings={
            "boundary_evidence_sha256": resolved.spec.boundary_evidence_sha256,
            "canonical_manifest_sha256": published.receipt.manifest_sha256,
            "capacity_evidence_sha256": resolved.spec.capacity_evidence_sha256,
            "instrument_registry_sha256": resolved.registry_sha256,
            "original_coverage_audit_artifact_sha256": execution_bindings[
                "coverage_audit_artifact_sha256"
            ],
            "original_funding_manifest_sha256": verified_original.completed.manifest_sha256,
            "parent_manifest_sha256": resolved.parent.receipt.manifest_sha256,
            "publisher_software_identity": published.manifest.software_identity,
            "repair_execution_artifact_sha256": execution.artifact_sha256,
            "repair_plan_artifact_sha256": execution.verified_plan.artifact_sha256,
            "replacement_evidence_artifact_sha256": sha256_file(
                replacement_evidence_path.resolve()
            ),
            "replacement_evidence_content_sha256": replacement["content_sha256"],
        },
        limitations=[
            "Coverage is evaluated only inside the original explicitly requested source windows.",
            "Source parity combines the original Landing response with exact receipt-verified "
            "repair observations; it is not an independently sourced exchange ledger.",
            "The original blocked audit remains immutable and is not retroactively reclassified.",
            "Current instrument fundingInterval metadata is not used as historical evidence.",
            "A passed audit does not accept a general cadence policy, register the child, close "
            "Gate 2, or authorize private or live operations.",
        ],
        storage_policy={
            "account_data_included": False,
            "funding_rates_included": False,
            "github_commit_eligible": False,
            "observed_settlement_timestamps_included": False,
            "private_runtime_artifact": True,
            "runtime_paths_included": False,
        },
        audit_software_identity=audit_software_identity,
        generated_at_utc=generated_at_utc,
    )


def verify_funding_repair_coverage_audit(
    audit_path: Path,
    repair_execution_path: Path,
    repair_plan_path: Path,
    original_coverage_audit_path: Path,
    original_job_root: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    store_root: Path,
    repair_staging_root: Path,
    replacement_evidence_path: Path,
    *,
    expected_publisher_software_identity: str | None = None,
    expected_audit_software_identity: str | None = None,
) -> FundingCoverageAudit:
    """Verify a receipt-committed repair audit and rebuild it from all runtime inputs."""

    resolved_path = audit_path.resolve()
    if not verify_evidence(resolved_path):
        raise FundingAcquisitionError("funding repair coverage audit receipt does not verify")
    stored = _object(resolved_path, name="funding repair coverage audit")
    embedded = stored.get("content_sha256")
    hash_input = dict(stored)
    hash_input.pop("content_sha256", None)
    publisher_identity = cast(dict[str, object], stored.get("bindings", {})).get(
        "publisher_software_identity"
    )
    audit_identity = stored.get("audit_software_identity")
    generated_at = stored.get("generated_at_utc")
    if (
        stored.get("contract") != FUNDING_REPAIR_COVERAGE_AUDIT_CONTRACT
        or stored.get("status") not in ("passed", "blocked")
        or not isinstance(embedded, str)
        or embedded != canonical_sha256(hash_input)
        or not isinstance(publisher_identity, str)
        or not isinstance(audit_identity, str)
        or not isinstance(generated_at, str)
    ):
        raise FundingAcquisitionError("funding repair coverage audit identity is invalid")
    if (
        expected_publisher_software_identity is not None
        and publisher_identity != expected_publisher_software_identity
    ):
        raise FundingAcquisitionError("funding repair audit publisher identity differs")
    if (
        expected_audit_software_identity is not None
        and audit_identity != expected_audit_software_identity
    ):
        raise FundingAcquisitionError("funding repair audit software identity differs")
    recomputed = build_funding_repair_coverage_audit(
        repair_execution_path,
        repair_plan_path,
        original_coverage_audit_path,
        original_job_root,
        instrument_registry_path,
        capacity_evidence_path,
        store_root,
        repair_staging_root,
        replacement_evidence_path,
        publisher_software_identity=publisher_identity,
        audit_software_identity=audit_identity,
        generated_at_utc=generated_at,
    )
    if recomputed.payload != stored:
        raise FundingAcquisitionError(
            "funding repair coverage audit no longer matches verified runtime inputs"
        )
    return recomputed
