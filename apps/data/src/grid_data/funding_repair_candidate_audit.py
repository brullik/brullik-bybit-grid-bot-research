"""Receipt-verified eligibility audit for genuine funding repair discovery inputs."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, Literal, cast

from grid_contracts.canonical import canonical_sha256, sha256_file

from grid_data.evidence import verify_evidence
from grid_data.funding_acquisition import FundingAcquisitionError
from grid_data.funding_publication import SOFTWARE_IDENTITY_RE
from grid_data.funding_repair_plan import build_funding_repair_plan

AUDIT_CONTRACT: Final = "grid.funding-repair-candidate-audit/v1"
EVIDENCE_CONTRACT: Final = "grid.phase2-funding-repair-candidate-audit/v1"
CANDIDATE_POLICY: Final = "receipt-verified-funding-repair-eligibility-v1"
MAX_AUDITS: Final = 1_000
_NON_ISOLATED_ERROR: Final = (
    "funding chronology is not a complete set of isolated integer-multiple cadence sandwiches"
)

CandidateClassification = Literal[
    "eligible",
    "non-isolated-or-non-integer-chronology",
]
CANDIDATE_CLASSIFICATIONS: Final = (
    "eligible",
    "non-isolated-or-non-integer-chronology",
)


class FundingRepairCandidateAuditError(RuntimeError):
    """The supplied funding audit set cannot produce trustworthy eligibility evidence."""


@dataclass(frozen=True, slots=True)
class FundingRepairCandidateInput:
    coverage_audit_path: Path
    job_root: Path
    instrument_registry_path: Path


def _object(path: Path, *, name: str) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FundingRepairCandidateAuditError(f"{name} cannot be loaded") from error
    if not isinstance(raw, dict):
        raise FundingRepairCandidateAuditError(f"{name} must be an object")
    return cast(dict[str, object], raw)


def _generated_at(value: str) -> str:
    if not value.endswith("Z"):
        raise FundingRepairCandidateAuditError("generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise FundingRepairCandidateAuditError("generated_at_utc is invalid") from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise FundingRepairCandidateAuditError("generated_at_utc must be UTC")
    return value


def _software_identity(value: str) -> str:
    if not SOFTWARE_IDENTITY_RE.fullmatch(value):
        raise FundingRepairCandidateAuditError(
            "software identity must be git:<40-character-lowercase-commit-sha>"
        )
    return value


def _non_negative(mapping: dict[str, object], name: str) -> int:
    value = mapping.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FundingRepairCandidateAuditError(f"candidate audit {name} is invalid")
    return value


def _audit_result(
    candidate: FundingRepairCandidateInput,
    capacity_evidence_path: Path,
    store_root: Path,
    *,
    generated_at_utc: str,
    auditor_software_identity: str,
) -> dict[str, object]:
    audit_path = candidate.coverage_audit_path.resolve()
    if not verify_evidence(audit_path):
        raise FundingRepairCandidateAuditError("funding coverage audit receipt does not verify")
    audit = _object(audit_path, name="funding coverage audit")
    try:
        plan = build_funding_repair_plan(
            audit_path,
            candidate.job_root,
            candidate.instrument_registry_path,
            capacity_evidence_path,
            store_root,
            generated_at_utc=generated_at_utc,
            planner_software_identity=auditor_software_identity,
        )
    except FundingAcquisitionError as error:
        if str(error) != _NON_ISOLATED_ERROR:
            raise FundingRepairCandidateAuditError(
                "funding repair input failed verification or unsupported eligibility policy"
            ) from error
        classification: CandidateClassification = "non-isolated-or-non-integer-chronology"
        task_count = 0
        candidate_count = 0
        planned_max_http_requests = 0
        plan_content_sha256 = None
    else:
        classification = "eligible"
        task_count = plan.task_count
        candidate_count = plan.candidate_count
        planned_max_http_requests = plan.planned_max_http_requests
        plan_content_sha256 = plan.payload["content_sha256"]
    quality = audit.get("quality")
    if not isinstance(quality, dict):
        raise FundingRepairCandidateAuditError("funding coverage audit quality is invalid")
    result: dict[str, object] = {
        "candidate_settlement_count": candidate_count,
        "classification": classification,
        "coverage_audit_artifact_sha256": sha256_file(audit_path),
        "coverage_audit_content_sha256": audit.get("content_sha256"),
        "dataset_id": audit.get("dataset_id"),
        "instrument_registry_artifact_sha256": sha256_file(
            candidate.instrument_registry_path.resolve()
        ),
        "interval_change_count": _non_negative(
            cast(dict[str, object], quality), "interval_change_count"
        ),
        "planned_max_http_requests": planned_max_http_requests,
        "repair_plan_content_sha256": plan_content_sha256,
        "task_count": task_count,
    }
    if not all(
        isinstance(result[name], str)
        for name in (
            "coverage_audit_content_sha256",
            "dataset_id",
            "instrument_registry_artifact_sha256",
        )
    ):
        raise FundingRepairCandidateAuditError("funding candidate identity is invalid")
    return result


def build_funding_repair_candidate_audit(
    candidates: Sequence[FundingRepairCandidateInput],
    capacity_evidence_path: Path,
    store_root: Path,
    *,
    auditor_software_identity: str,
    generated_at_utc: str,
) -> dict[str, object]:
    """Reverify and classify every explicitly supplied blocked funding audit."""

    if not 1 <= len(candidates) <= MAX_AUDITS:
        raise FundingRepairCandidateAuditError(
            f"funding repair audit count must be in [1, {MAX_AUDITS}]"
        )
    identity = _software_identity(auditor_software_identity)
    generated_at = _generated_at(generated_at_utc)
    capacity_path = capacity_evidence_path.resolve()
    try:
        capacity_sha256 = sha256_file(capacity_path)
    except OSError as error:
        raise FundingRepairCandidateAuditError("capacity evidence cannot be hashed") from error
    results = [
        _audit_result(
            candidate,
            capacity_path,
            store_root,
            generated_at_utc=generated_at,
            auditor_software_identity=identity,
        )
        for candidate in candidates
    ]
    artifact_hashes = [cast(str, item["coverage_audit_artifact_sha256"]) for item in results]
    if len(set(artifact_hashes)) != len(artifact_hashes):
        raise FundingRepairCandidateAuditError("funding repair audit inputs must be unique")
    results.sort(key=lambda item: cast(str, item["coverage_audit_artifact_sha256"]))
    counts: Counter[str] = Counter(cast(str, item["classification"]) for item in results)
    classification_counts = {name: counts[name] for name in CANDIDATE_CLASSIFICATIONS}
    eligible_count = classification_counts["eligible"]
    payload: dict[str, object] = {
        "audit_count": len(results),
        "auditor_software_identity": identity,
        "candidate_settlement_count": sum(
            cast(int, item["candidate_settlement_count"]) for item in results
        ),
        "candidates": results,
        "capacity_evidence_sha256": capacity_sha256,
        "classification_counts": classification_counts,
        "contract": AUDIT_CONTRACT,
        "generated_at_utc": generated_at,
        "input_set_sha256": canonical_sha256(results),
        "interval_change_count": sum(cast(int, item["interval_change_count"]) for item in results),
        "planned_max_http_requests": sum(
            cast(int, item["planned_max_http_requests"]) for item in results
        ),
        "policy": CANDIDATE_POLICY,
        "status": "eligible-candidates-observed" if eligible_count else "no-eligible-candidates",
        "task_count": sum(cast(int, item["task_count"]) for item in results),
    }
    return payload


def verify_funding_repair_candidate_audit(
    audit_path: Path,
    candidates: Sequence[FundingRepairCandidateInput],
    capacity_evidence_path: Path,
    store_root: Path,
) -> dict[str, object]:
    """Receipt-verify and reproduce the detailed audit from immutable inputs."""

    path = audit_path.resolve()
    if not verify_evidence(path):
        raise FundingRepairCandidateAuditError("candidate audit receipt verification failed")
    stored = _object(path, name="funding repair candidate audit")
    identity = stored.get("auditor_software_identity")
    generated_at = stored.get("generated_at_utc")
    if not isinstance(identity, str) or not isinstance(generated_at, str):
        raise FundingRepairCandidateAuditError("candidate audit identity fields are invalid")
    rebuilt = build_funding_repair_candidate_audit(
        candidates,
        capacity_evidence_path,
        store_root,
        auditor_software_identity=identity,
        generated_at_utc=generated_at,
    )
    if stored != rebuilt:
        raise FundingRepairCandidateAuditError(
            "candidate audit no longer matches its receipt-verified funding inputs"
        )
    return stored


def build_funding_repair_candidate_evidence(
    audit_path: Path,
    candidates: Sequence[FundingRepairCandidateInput],
    capacity_evidence_path: Path,
    store_root: Path,
    *,
    publisher_software_identity: str,
) -> dict[str, object]:
    """Project the detailed audit into a GitHub-safe aggregate."""

    publisher = _software_identity(publisher_software_identity)
    audit = verify_funding_repair_candidate_audit(
        audit_path,
        candidates,
        capacity_evidence_path,
        store_root,
    )
    raw_counts = audit.get("classification_counts")
    if not isinstance(raw_counts, dict) or set(raw_counts) != set(CANDIDATE_CLASSIFICATIONS):
        raise FundingRepairCandidateAuditError("candidate audit classifications are invalid")
    counts = {
        name: _non_negative(cast(dict[str, object], raw_counts), name)
        for name in CANDIDATE_CLASSIFICATIONS
    }
    audit_count = _non_negative(audit, "audit_count")
    if sum(counts.values()) != audit_count:
        raise FundingRepairCandidateAuditError("candidate audit classification arithmetic failed")
    eligible_count = counts["eligible"]
    payload: dict[str, object] = {
        "assurances": {
            "all_coverage_audits_receipt_verified_and_recomputed": True,
            "candidate_requests_executed": False,
            "current_instrument_interval_used": False,
            "parent_datasets_mutated": False,
            "private_or_live_capability_used": False,
        },
        "bindings": {
            "audit_artifact_sha256": sha256_file(audit_path.resolve()),
            "auditor_software_identity": audit["auditor_software_identity"],
            "capacity_evidence_sha256": audit["capacity_evidence_sha256"],
            "input_set_sha256": audit["input_set_sha256"],
            "publisher_software_identity": publisher,
        },
        "classification_counts": counts,
        "content_sha256": "",
        "evidence_schema": EVIDENCE_CONTRACT,
        "generated_at_utc": audit["generated_at_utc"],
        "inventory": {
            "audit_count": audit_count,
            "candidate_settlement_count": _non_negative(audit, "candidate_settlement_count"),
            "interval_change_count": _non_negative(audit, "interval_change_count"),
            "planned_max_http_requests": _non_negative(audit, "planned_max_http_requests"),
            "task_count": _non_negative(audit, "task_count"),
        },
        "limitations": [
            "Eligibility covers only the exact receipt-bound blocked audit input set.",
            "A no-candidate result does not accept any historical cadence change.",
            "A future distinct blocked audit requires a new candidate audit.",
            (
                "This evidence does not execute repair, publish a child, close Gate 2, "
                "or authorize Phase 3."
            ),
        ],
        "policy": CANDIDATE_POLICY,
        "status": (
            "verified-eligible-funding-repair-candidates"
            if eligible_count
            else "verified-no-eligible-funding-repair-candidates"
        ),
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_dataset_or_instrument_identities": False,
            "evidence_contains_funding_rates_or_timestamps": False,
            "evidence_contains_runtime_paths": False,
            "runtime_market_artifacts_committed_to_git": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    return payload


def verify_funding_repair_candidate_evidence(
    evidence_path: Path,
    audit_path: Path,
    candidates: Sequence[FundingRepairCandidateInput],
    capacity_evidence_path: Path,
    store_root: Path,
) -> dict[str, object]:
    """Verify public evidence receipt, content hash, and private audit binding."""

    path = evidence_path.resolve()
    if not verify_evidence(path):
        raise FundingRepairCandidateAuditError("candidate evidence receipt verification failed")
    stored = _object(path, name="funding repair candidate evidence")
    bindings = stored.get("bindings")
    if not isinstance(bindings, dict):
        raise FundingRepairCandidateAuditError("candidate evidence bindings are invalid")
    publisher = bindings.get("publisher_software_identity")
    content_hash = stored.get("content_sha256")
    without_hash = dict(stored)
    without_hash.pop("content_sha256", None)
    if not isinstance(publisher, str) or content_hash != canonical_sha256(without_hash):
        raise FundingRepairCandidateAuditError("candidate evidence identity or hash is invalid")
    rebuilt = build_funding_repair_candidate_evidence(
        audit_path,
        candidates,
        capacity_evidence_path,
        store_root,
        publisher_software_identity=publisher,
    )
    if stored != rebuilt:
        raise FundingRepairCandidateAuditError(
            "candidate evidence no longer matches its private audit"
        )
    return stored
