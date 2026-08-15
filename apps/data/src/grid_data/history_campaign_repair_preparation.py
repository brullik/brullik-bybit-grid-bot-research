"""Receipt-resumable preparation of blocked candle repair plans from a campaign audit."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Final, cast

from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file

from grid_data.evidence import publish_evidence, verify_evidence
from grid_data.history_acquisition import HistoryAcquisitionError
from grid_data.history_campaign_coverage_audit import CAMPAIGN_COVERAGE_AUDIT_CONTRACT
from grid_data.history_campaign_publication import (
    CAMPAIGN_PUBLICATION_PLAN_CONTRACT,
    HistoryCampaignPublicationError,
    verify_completed_history_campaign_publication,
)
from grid_data.history_coverage_audit import (
    COVERAGE_AUDIT_CONTRACT,
    CoverageAudit,
    build_completed_history_coverage_audit,
)
from grid_data.history_publication import SOFTWARE_IDENTITY_RE
from grid_data.history_repair_plan import (
    REPAIR_PLAN_CONTRACT,
    GapRepairPlanIneligible,
    build_gap_repair_plan_from_recomputed_audit,
)

PREPARATION_REQUEST_CONTRACT: Final = "grid.history-campaign-repair-preparation-request/v1"
PREPARATION_CHILD_RESULT_CONTRACT: Final = "grid.history-campaign-repair-preparation-child/v1"
PREPARATION_MANIFEST_CONTRACT: Final = "grid.history-campaign-repair-preparation/v1"
PREPARATION_POLICY: Final = {
    "aggregate_passed_children_recomputed": False,
    "blocked_candle_children_recomputed": True,
    "canonical_dataset_mutated": False,
    "funding_repair_delegated_to_separate_pipeline": True,
    "market_requests_executed": False,
    "repair_execution_performed": False,
}
_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_CHILD_CLASSIFICATIONS: Final = {
    "eligible",
    "no-missing-minute-gap",
    "non-gap-audit-blocker-remains",
    "reason-policy-incompatible",
    "repair-request-limit-exceeded",
    "repair-task-limit-exceeded",
}


class HistoryCampaignRepairPreparationError(RuntimeError):
    """The preparation checkpoint cannot be trusted or completed safely."""


@dataclass(frozen=True, slots=True)
class CompletedHistoryCampaignRepairPreparation:
    preparation_root: Path
    request_path: Path
    manifest_path: Path
    manifest_sha256: str
    dataset_count: int
    blocked_candle_count: int
    eligible_candle_count: int
    ineligible_candle_count: int
    repair_plan_count: int
    task_count: int
    planned_max_http_requests: int
    status: str
    existing_complete: bool


@dataclass(frozen=True, slots=True)
class _PreparationInputs:
    publication_plan: dict[str, object]
    aggregate_audit: dict[str, object]
    child_results: tuple[dict[str, object], ...]
    source_campaign_root: Path
    instrument_registry_path: Path
    capacity_evidence_path: Path
    store_root: Path
    request_static: dict[str, object]


def _load_object(path: Path, *, name: str) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryCampaignRepairPreparationError(f"{name} cannot be loaded") from error
    if not isinstance(raw, dict):
        raise HistoryCampaignRepairPreparationError(f"{name} must be an object")
    return cast(dict[str, object], raw)


def _load_receipted_object(path: Path, *, name: str) -> dict[str, object]:
    resolved = path.resolve()
    if not verify_evidence(resolved):
        raise HistoryCampaignRepairPreparationError(f"{name} receipt does not verify")
    payload = _load_object(resolved, name=name)
    try:
        stored = resolved.read_bytes()
    except OSError as error:
        raise HistoryCampaignRepairPreparationError(f"{name} cannot be read") from error
    if stored != canonical_json_bytes(payload) + b"\n":
        raise HistoryCampaignRepairPreparationError(f"{name} is not canonical JSON")
    return payload


def _content_hash(payload: dict[str, object], *, name: str) -> str:
    embedded = payload.get("content_sha256")
    without_hash = dict(payload)
    without_hash.pop("content_sha256", None)
    if not isinstance(embedded, str) or embedded != canonical_sha256(without_hash):
        raise HistoryCampaignRepairPreparationError(f"{name} content hash is invalid")
    return embedded


def _sha256(value: object, *, name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise HistoryCampaignRepairPreparationError(f"{name} must be lowercase SHA-256 text")
    return value


def _integer(
    parent: dict[str, object],
    key: str,
    *,
    positive: bool = False,
) -> int:
    value = parent.get(key)
    minimum = 1 if positive else 0
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise HistoryCampaignRepairPreparationError(
            f"{key} must be {'positive' if positive else 'non-negative'} integer"
        )
    return value


def _object_value(parent: dict[str, object], key: str) -> dict[str, object]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise HistoryCampaignRepairPreparationError(f"{key} must be an object")
    return cast(dict[str, object], value)


def _generated_at(value: str) -> str:
    if not value.endswith("Z"):
        raise HistoryCampaignRepairPreparationError("generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise HistoryCampaignRepairPreparationError("generated_at_utc is invalid") from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise HistoryCampaignRepairPreparationError("generated_at_utc must be UTC")
    return value


def _software_identity(value: object, *, name: str) -> str:
    if not isinstance(value, str) or SOFTWARE_IDENTITY_RE.fullmatch(value) is None:
        raise HistoryCampaignRepairPreparationError(f"{name} must be immutable Git identity")
    return value


def _safe_job_root(source_campaign_root: Path, relative: object) -> Path:
    if not isinstance(relative, str):
        raise HistoryCampaignRepairPreparationError("publication child source root is invalid")
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative:
        raise HistoryCampaignRepairPreparationError("publication child source root is unsafe")
    staging_root = source_campaign_root.resolve().parent.parent
    candidate = staging_root.joinpath(*path.parts).resolve()
    try:
        candidate.relative_to(staging_root)
    except ValueError as error:
        raise HistoryCampaignRepairPreparationError(
            "publication child source root escapes staging"
        ) from error
    return candidate


def _verify_inputs(
    publication_root: Path,
    source_campaign_root: Path,
    campaign_coverage_audit_path: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    store_root: Path,
    *,
    planner_software_identity: str,
) -> _PreparationInputs:
    planner_identity = _software_identity(
        planner_software_identity,
        name="planner software identity",
    )
    source_root = source_campaign_root.resolve()
    registry_path = instrument_registry_path.resolve()
    capacity_path = capacity_evidence_path.resolve()
    canonical_store = store_root.resolve()
    try:
        completed = verify_completed_history_campaign_publication(
            publication_root,
            source_root,
        )
    except HistoryCampaignPublicationError as error:
        raise HistoryCampaignRepairPreparationError(
            "completed campaign publication does not verify"
        ) from error
    plan = _load_object(completed.plan_path, name="campaign publication plan")
    if plan.get("contract") != CAMPAIGN_PUBLICATION_PLAN_CONTRACT:
        raise HistoryCampaignRepairPreparationError("campaign publication plan contract differs")
    expected_store = completed.publication_root.parent.parent
    if canonical_store != expected_store:
        raise HistoryCampaignRepairPreparationError("store root differs from publication root")
    try:
        registry_sha = sha256_file(registry_path)
        capacity_sha = sha256_file(capacity_path)
    except OSError as error:
        raise HistoryCampaignRepairPreparationError(
            "registry or capacity evidence cannot be hashed"
        ) from error
    if (
        plan.get("instrument_evidence_sha256") != registry_sha
        or plan.get("capacity_evidence_sha256") != capacity_sha
    ):
        raise HistoryCampaignRepairPreparationError(
            "registry or capacity evidence differs from publication plan"
        )

    aggregate_path = campaign_coverage_audit_path.resolve()
    aggregate = _load_receipted_object(aggregate_path, name="campaign coverage audit")
    aggregate_content_sha = _content_hash(aggregate, name="campaign coverage audit")
    if aggregate.get("contract") != CAMPAIGN_COVERAGE_AUDIT_CONTRACT:
        raise HistoryCampaignRepairPreparationError("campaign coverage audit contract differs")
    if aggregate.get("status") not in ("passed", "blocked"):
        raise HistoryCampaignRepairPreparationError("campaign coverage audit status is invalid")
    publisher_identity = _software_identity(
        plan.get("publisher_software_identity"),
        name="publisher software identity",
    )
    audit_identity = _software_identity(
        aggregate.get("audit_software_identity"),
        name="audit software identity",
    )
    audit_generated_at = aggregate.get("generated_at_utc")
    if not isinstance(audit_generated_at, str):
        raise HistoryCampaignRepairPreparationError("campaign audit generated_at is invalid")
    _generated_at(audit_generated_at)
    bindings = _object_value(aggregate, "bindings")
    expected_bindings = {
        "capacity_evidence_sha256": plan["capacity_evidence_sha256"],
        "instrument_registry_sha256": plan["instrument_evidence_sha256"],
        "publication_manifest_sha256": completed.manifest_sha256,
        "publication_plan_sha256": canonical_sha256(plan),
        "publisher_software_identity": publisher_identity,
        "source_campaign_manifest_sha256": plan["source_campaign_manifest_sha256"],
        "source_campaign_plan_sha256": plan["source_campaign_plan_sha256"],
    }
    if bindings != expected_bindings:
        raise HistoryCampaignRepairPreparationError(
            "campaign coverage audit does not bind the supplied publication"
        )
    raw_jobs = plan.get("jobs")
    raw_results = aggregate.get("child_results")
    if (
        not isinstance(raw_jobs, list)
        or not isinstance(raw_results, list)
        or len(raw_jobs) != completed.dataset_count
        or len(raw_results) != len(raw_jobs)
    ):
        raise HistoryCampaignRepairPreparationError("campaign child inventories differ")
    children: list[dict[str, object]] = []
    for sequence, (raw_job, raw_result) in enumerate(zip(raw_jobs, raw_results, strict=True)):
        if not isinstance(raw_job, dict) or not isinstance(raw_result, dict):
            raise HistoryCampaignRepairPreparationError("campaign child entry is invalid")
        if set(raw_result) != {"audit_content_sha256", "kind", "sequence", "status"}:
            raise HistoryCampaignRepairPreparationError("campaign child result fields differ")
        kind = raw_job.get("kind")
        if (
            raw_result.get("sequence") != sequence
            or raw_result.get("kind") != kind
            or kind not in ("trade", "mark", "funding")
            or raw_result.get("status") not in ("passed", "blocked")
        ):
            raise HistoryCampaignRepairPreparationError("campaign child result identity differs")
        _sha256(raw_result.get("audit_content_sha256"), name="child audit content hash")
        children.append(cast(dict[str, object], raw_result))
    blocked_count = sum(item["status"] == "blocked" for item in children)
    if aggregate.get("status") != ("blocked" if blocked_count else "passed"):
        raise HistoryCampaignRepairPreparationError("campaign aggregate status arithmetic differs")
    inventory = _object_value(aggregate, "inventory")
    if (
        inventory.get("dataset_count") != len(children)
        or inventory.get("blocked_count") != blocked_count
        or inventory.get("passed_count") != len(children) - blocked_count
    ):
        raise HistoryCampaignRepairPreparationError("campaign aggregate inventory differs")

    request_static: dict[str, object] = {
        "bindings": {
            "aggregate_coverage_audit_artifact_sha256": sha256_file(aggregate_path),
            "aggregate_coverage_audit_content_sha256": aggregate_content_sha,
            "capacity_evidence_artifact_sha256": capacity_sha,
            "instrument_registry_artifact_sha256": registry_sha,
            "publication_manifest_sha256": completed.manifest_sha256,
            "publication_plan_sha256": canonical_sha256(plan),
            "source_campaign_manifest_sha256": plan["source_campaign_manifest_sha256"],
            "source_campaign_plan_sha256": plan["source_campaign_plan_sha256"],
        },
        "blocked_candle_count": sum(
            item["status"] == "blocked" and item["kind"] in ("trade", "mark") for item in children
        ),
        "contract": PREPARATION_REQUEST_CONTRACT,
        "dataset_count": len(children),
        "policy": PREPARATION_POLICY,
        "publisher_software_identity": publisher_identity,
        "audit_software_identity": audit_identity,
        "planner_software_identity": planner_identity,
    }
    return _PreparationInputs(
        publication_plan=plan,
        aggregate_audit=aggregate,
        child_results=tuple(children),
        source_campaign_root=source_root,
        instrument_registry_path=registry_path,
        capacity_evidence_path=capacity_path,
        store_root=canonical_store,
        request_static=request_static,
    )


def _request_payload(inputs: _PreparationInputs, generated_at_utc: str) -> dict[str, object]:
    payload = dict(inputs.request_static)
    payload["generated_at_utc"] = _generated_at(generated_at_utc)
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def _resolve_root(preparation_root: Path) -> Path:
    supplied = preparation_root.absolute()
    if supplied.is_symlink() or supplied.parent.is_symlink():
        raise HistoryCampaignRepairPreparationError(
            "preparation root and parent cannot be symlinks"
        )
    root = supplied.resolve()
    if root.exists() and not root.is_dir():
        raise HistoryCampaignRepairPreparationError("preparation root is not a directory")
    return root


def _pair_state(path: Path) -> str:
    receipt = path.with_suffix(path.suffix + ".receipt.json")
    if path.is_file() and receipt.is_file():
        return "complete"
    if path.exists() or receipt.exists():
        return "incomplete"
    return "absent"


def _load_or_create_request(
    root: Path,
    inputs: _PreparationInputs,
    *,
    generated_at_utc: str,
) -> dict[str, object]:
    request_path = root / "request.json"
    state = _pair_state(request_path)
    if state == "incomplete":
        raise HistoryCampaignRepairPreparationError("preparation request pair is incomplete")
    if state == "absent":
        if root.exists() and any(root.iterdir()):
            raise HistoryCampaignRepairPreparationError(
                "preparation root contains state without a request receipt"
            )
        root.mkdir(parents=True, exist_ok=True)
        payload = _request_payload(inputs, generated_at_utc)
        publish_evidence(request_path, payload)
        return payload
    stored = _load_receipted_object(request_path, name="preparation request")
    _content_hash(stored, name="preparation request")
    stored_generated_at = stored.get("generated_at_utc")
    if not isinstance(stored_generated_at, str):
        raise HistoryCampaignRepairPreparationError("preparation request time is invalid")
    if stored != _request_payload(inputs, stored_generated_at):
        raise HistoryCampaignRepairPreparationError(
            "preparation request differs from supplied immutable inputs"
        )
    return stored


def _publish_or_verify(path: Path, payload: dict[str, object], *, name: str) -> None:
    state = _pair_state(path)
    if state == "incomplete":
        raise HistoryCampaignRepairPreparationError(f"{name} pair is incomplete")
    if state == "absent":
        publish_evidence(path, payload)
        return
    if _load_receipted_object(path, name=name) != payload:
        raise HistoryCampaignRepairPreparationError(f"{name} conflicts with recomputed result")


def _child_result_payload(
    *,
    sequence: int,
    kind: str,
    aggregate_content_sha256: str,
    coverage_path: Path,
    coverage: CoverageAudit,
    classification: str,
    repair_plan_path: Path | None,
    repair_plan_payload: dict[str, object] | None,
    task_count: int,
    planned_max_http_requests: int,
) -> dict[str, object]:
    quality = _object_value(coverage.payload, "quality")
    payload: dict[str, object] = {
        "aggregate_child_audit_content_sha256": aggregate_content_sha256,
        "classification": classification,
        "contract": PREPARATION_CHILD_RESULT_CONTRACT,
        "coverage_audit_artifact_sha256": sha256_file(coverage_path),
        "coverage_audit_content_sha256": coverage.payload["content_sha256"],
        "gap_range_count": len(coverage.gap_ranges),
        "kind": kind,
        "missing_minute_count": _integer(quality, "missing_minute_count"),
        "planned_max_http_requests": planned_max_http_requests,
        "repair_plan_artifact_sha256": (
            sha256_file(repair_plan_path) if repair_plan_path is not None else None
        ),
        "repair_plan_content_sha256": (
            repair_plan_payload["content_sha256"] if repair_plan_payload is not None else None
        ),
        "sequence": sequence,
        "status": (
            "eligible-repair-plan-prepared"
            if classification == "eligible"
            else "ineligible-candle-blocker-preserved"
        ),
        "task_count": task_count,
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def _verify_plan_checkpoint(
    path: Path,
    coverage_path: Path,
    *,
    planner_software_identity: str,
) -> dict[str, object]:
    plan = _load_receipted_object(path, name="prepared child repair plan")
    _content_hash(plan, name="prepared child repair plan")
    bindings = _object_value(plan, "bindings")
    if (
        plan.get("contract") != REPAIR_PLAN_CONTRACT
        or plan.get("status") != "planned"
        or plan.get("planner_software_identity") != planner_software_identity
        or bindings.get("coverage_audit_artifact_sha256") != sha256_file(coverage_path)
    ):
        raise HistoryCampaignRepairPreparationError("prepared child repair plan binding differs")
    coverage = _load_receipted_object(coverage_path, name="prepared child coverage audit")
    if bindings.get("coverage_audit_content_sha256") != coverage.get("content_sha256"):
        raise HistoryCampaignRepairPreparationError(
            "prepared child repair plan changed coverage content binding"
        )
    return plan


def _verify_child_result(
    child_root: Path,
    aggregate_child: dict[str, object],
    *,
    planner_software_identity: str,
) -> dict[str, object]:
    allowed = {
        "coverage-audit.json",
        "coverage-audit.json.receipt.json",
        "repair-plan.json",
        "repair-plan.json.receipt.json",
        "result.json",
        "result.json.receipt.json",
    }
    actual = {item.name for item in child_root.iterdir()}
    if not actual <= allowed:
        raise HistoryCampaignRepairPreparationError("preparation child allowlist differs")
    result_path = child_root / "result.json"
    if _pair_state(result_path) != "complete":
        raise HistoryCampaignRepairPreparationError("preparation child result is incomplete")
    result = _load_receipted_object(result_path, name="preparation child result")
    _content_hash(result, name="preparation child result")
    classification = result.get("classification")
    if (
        result.get("contract") != PREPARATION_CHILD_RESULT_CONTRACT
        or result.get("sequence") != aggregate_child["sequence"]
        or result.get("kind") != aggregate_child["kind"]
        or result.get("aggregate_child_audit_content_sha256")
        != aggregate_child["audit_content_sha256"]
        or classification not in _CHILD_CLASSIFICATIONS
    ):
        raise HistoryCampaignRepairPreparationError("preparation child result identity differs")
    coverage_path = child_root / "coverage-audit.json"
    coverage = _load_receipted_object(coverage_path, name="prepared child coverage audit")
    coverage_content = _content_hash(coverage, name="prepared child coverage audit")
    if (
        coverage.get("contract") != COVERAGE_AUDIT_CONTRACT
        or coverage.get("status") != "blocked"
        or coverage_content != aggregate_child["audit_content_sha256"]
        or result.get("coverage_audit_artifact_sha256") != sha256_file(coverage_path)
        or result.get("coverage_audit_content_sha256") != coverage_content
    ):
        raise HistoryCampaignRepairPreparationError("prepared child coverage binding differs")
    plan_path = child_root / "repair-plan.json"
    if classification == "eligible":
        if _pair_state(plan_path) != "complete":
            raise HistoryCampaignRepairPreparationError("eligible repair plan pair is incomplete")
        plan = _verify_plan_checkpoint(
            plan_path,
            coverage_path,
            planner_software_identity=planner_software_identity,
        )
        limits = _object_value(plan, "limits")
        if (
            result.get("repair_plan_artifact_sha256") != sha256_file(plan_path)
            or result.get("repair_plan_content_sha256") != plan.get("content_sha256")
            or result.get("task_count") != limits.get("task_count")
            or result.get("planned_max_http_requests") != limits.get("planned_max_http_requests")
            or result.get("status") != "eligible-repair-plan-prepared"
        ):
            raise HistoryCampaignRepairPreparationError("eligible child plan summary differs")
    elif (
        _pair_state(plan_path) != "absent"
        or result.get("repair_plan_artifact_sha256") is not None
        or result.get("repair_plan_content_sha256") is not None
        or result.get("task_count") != 0
        or result.get("planned_max_http_requests") != 0
        or result.get("status") != "ineligible-candle-blocker-preserved"
    ):
        raise HistoryCampaignRepairPreparationError("ineligible child unexpectedly has a plan")
    return result


def _prepare_blocked_candle(
    inputs: _PreparationInputs,
    aggregate_child: dict[str, object],
    child_root: Path,
    *,
    request: dict[str, object],
) -> dict[str, object]:
    result_path = child_root / "result.json"
    result_state = _pair_state(result_path)
    if result_state == "incomplete":
        raise HistoryCampaignRepairPreparationError("preparation child result pair is incomplete")
    planner_identity = cast(str, request["planner_software_identity"])
    if result_state == "complete":
        return _verify_child_result(
            child_root,
            aggregate_child,
            planner_software_identity=planner_identity,
        )
    if child_root.exists() and not child_root.is_dir():
        raise HistoryCampaignRepairPreparationError("preparation child root is not a directory")
    if child_root.exists():
        allowed = {
            "coverage-audit.json",
            "coverage-audit.json.receipt.json",
            "repair-plan.json",
            "repair-plan.json.receipt.json",
            "result.json",
            "result.json.receipt.json",
        }
        if {item.name for item in child_root.iterdir()} - allowed:
            raise HistoryCampaignRepairPreparationError("preparation child allowlist differs")
        for artifact in ("coverage-audit.json", "repair-plan.json"):
            if _pair_state(child_root / artifact) == "incomplete":
                raise HistoryCampaignRepairPreparationError(
                    f"preparation child {artifact} pair is incomplete"
                )
    child_root.mkdir(parents=True, exist_ok=True)
    sequence = cast(int, aggregate_child["sequence"])
    raw_jobs = cast(list[dict[str, object]], inputs.publication_plan["jobs"])
    raw_job = raw_jobs[sequence]
    job_root = _safe_job_root(inputs.source_campaign_root, raw_job.get("source_job_root"))
    try:
        coverage = build_completed_history_coverage_audit(
            job_root,
            inputs.instrument_registry_path,
            inputs.capacity_evidence_path,
            inputs.store_root,
            publisher_software_identity=cast(
                str,
                inputs.request_static["publisher_software_identity"],
            ),
            audit_software_identity=cast(str, inputs.request_static["audit_software_identity"]),
            generated_at_utc=cast(str, inputs.aggregate_audit["generated_at_utc"]),
        )
    except HistoryAcquisitionError as error:
        raise HistoryCampaignRepairPreparationError(
            f"blocked candle child {sequence} cannot be recomputed"
        ) from error
    aggregate_hash = cast(str, aggregate_child["audit_content_sha256"])
    if coverage.passed or coverage.payload.get("content_sha256") != aggregate_hash:
        raise HistoryCampaignRepairPreparationError(
            f"blocked candle child {sequence} differs from aggregate audit"
        )
    coverage_path = child_root / "coverage-audit.json"
    _publish_or_verify(
        coverage_path,
        coverage.payload,
        name="prepared child coverage audit",
    )
    repair_plan_path = child_root / "repair-plan.json"
    try:
        repair_plan = build_gap_repair_plan_from_recomputed_audit(
            coverage_path,
            coverage,
            job_root,
            generated_at_utc=cast(str, request["generated_at_utc"]),
            planner_software_identity=planner_identity,
        )
    except GapRepairPlanIneligible as error:
        if error.classification not in _CHILD_CLASSIFICATIONS - {"eligible"}:
            raise HistoryCampaignRepairPreparationError(
                "blocked candle classification is unsupported"
            ) from error
        if _pair_state(repair_plan_path) != "absent":
            raise HistoryCampaignRepairPreparationError(
                "ineligible blocked candle has an orphan repair plan"
            ) from error
        classification = error.classification
        repair_plan_payload = None
        repair_plan_artifact = None
        task_count = 0
        planned_requests = 0
    except HistoryAcquisitionError as error:
        raise HistoryCampaignRepairPreparationError(
            f"blocked candle child {sequence} repair planning failed verification"
        ) from error
    else:
        classification = "eligible"
        repair_plan_payload = repair_plan.payload
        repair_plan_artifact = repair_plan_path
        task_count = repair_plan.task_count
        planned_requests = repair_plan.planned_max_http_requests
        _publish_or_verify(
            repair_plan_path,
            repair_plan_payload,
            name="prepared child repair plan",
        )
    result = _child_result_payload(
        sequence=sequence,
        kind=cast(str, aggregate_child["kind"]),
        aggregate_content_sha256=aggregate_hash,
        coverage_path=coverage_path,
        coverage=coverage,
        classification=classification,
        repair_plan_path=repair_plan_artifact,
        repair_plan_payload=repair_plan_payload,
        task_count=task_count,
        planned_max_http_requests=planned_requests,
    )
    _publish_or_verify(result_path, result, name="preparation child result")
    return result


def _manifest_payload(
    inputs: _PreparationInputs,
    request: dict[str, object],
    child_preparations: dict[int, dict[str, object]],
    root: Path,
) -> dict[str, object]:
    children: list[dict[str, object]] = []
    eligible_count = 0
    ineligible_count = 0
    blocked_funding_count = 0
    task_count = 0
    planned_requests = 0
    total_missing = 0
    total_gap_ranges = 0
    for aggregate_child in inputs.child_results:
        sequence = cast(int, aggregate_child["sequence"])
        kind = cast(str, aggregate_child["kind"])
        status = cast(str, aggregate_child["status"])
        if status == "passed":
            classification = "not-blocked"
            result_sha: str | None = None
        elif kind == "funding":
            classification = "funding-repair-separate"
            blocked_funding_count += 1
            result_sha = None
        else:
            result = child_preparations[sequence]
            classification = cast(str, result["classification"])
            result_path = root / "children" / f"{sequence:06d}" / "result.json"
            result_sha = sha256_file(result_path)
            if classification == "eligible":
                eligible_count += 1
            else:
                ineligible_count += 1
            task_count += cast(int, result["task_count"])
            planned_requests += cast(int, result["planned_max_http_requests"])
            total_missing += cast(int, result["missing_minute_count"])
            total_gap_ranges += cast(int, result["gap_range_count"])
        children.append(
            {
                "aggregate_audit_content_sha256": aggregate_child["audit_content_sha256"],
                "classification": classification,
                "kind": kind,
                "preparation_result_artifact_sha256": result_sha,
                "sequence": sequence,
                "status": status,
            }
        )
    blocked_candle_count = eligible_count + ineligible_count
    if ineligible_count:
        status = "complete-with-ineligible-candle-children"
    elif blocked_candle_count:
        status = "complete-repair-plans-prepared"
    else:
        status = "complete-no-blocked-candle-children"
    payload: dict[str, object] = {
        "bindings": request["bindings"],
        "children": children,
        "contract": PREPARATION_MANIFEST_CONTRACT,
        "generated_at_utc": request["generated_at_utc"],
        "inventory": {
            "blocked_candle_count": blocked_candle_count,
            "blocked_funding_count": blocked_funding_count,
            "dataset_count": len(children),
            "eligible_candle_count": eligible_count,
            "gap_range_count": total_gap_ranges,
            "ineligible_candle_count": ineligible_count,
            "passed_count": sum(item["status"] == "passed" for item in children),
            "planned_max_http_requests": planned_requests,
            "repair_plan_count": eligible_count,
            "task_count": task_count,
            "total_missing_minute_count": total_missing,
        },
        "planner_software_identity": request["planner_software_identity"],
        "policy": PREPARATION_POLICY,
        "request_artifact_sha256": sha256_file(root / "request.json"),
        "status": status,
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def _completed_result(
    root: Path,
    manifest: dict[str, object],
    *,
    existing_complete: bool,
) -> CompletedHistoryCampaignRepairPreparation:
    inventory = _object_value(manifest, "inventory")
    return CompletedHistoryCampaignRepairPreparation(
        preparation_root=root,
        request_path=root / "request.json",
        manifest_path=root / "manifest.json",
        manifest_sha256=sha256_file(root / "manifest.json"),
        dataset_count=_integer(inventory, "dataset_count", positive=True),
        blocked_candle_count=_integer(inventory, "blocked_candle_count"),
        eligible_candle_count=_integer(inventory, "eligible_candle_count"),
        ineligible_candle_count=_integer(inventory, "ineligible_candle_count"),
        repair_plan_count=_integer(inventory, "repair_plan_count"),
        task_count=_integer(inventory, "task_count"),
        planned_max_http_requests=_integer(inventory, "planned_max_http_requests"),
        status=cast(str, manifest["status"]),
        existing_complete=existing_complete,
    )


def _verify_completed(
    root: Path,
    inputs: _PreparationInputs,
    request: dict[str, object],
    *,
    existing_complete: bool,
) -> CompletedHistoryCampaignRepairPreparation:
    expected_root_names = {
        "request.json",
        "request.json.receipt.json",
        "manifest.json",
        "manifest.json.receipt.json",
    }
    blocked_candles = [
        item
        for item in inputs.child_results
        if item["status"] == "blocked" and item["kind"] in ("trade", "mark")
    ]
    if blocked_candles:
        expected_root_names.add("children")
    actual_root_names = {item.name for item in root.iterdir()}
    if actual_root_names != expected_root_names:
        raise HistoryCampaignRepairPreparationError("preparation root allowlist differs")
    child_preparations: dict[int, dict[str, object]] = {}
    if blocked_candles:
        children_root = root / "children"
        if children_root.is_symlink() or not children_root.is_dir():
            raise HistoryCampaignRepairPreparationError("preparation children root is invalid")
        expected_names = {f"{cast(int, item['sequence']):06d}" for item in blocked_candles}
        if {item.name for item in children_root.iterdir()} != expected_names:
            raise HistoryCampaignRepairPreparationError("preparation child directory set differs")
        for aggregate_child in blocked_candles:
            sequence = cast(int, aggregate_child["sequence"])
            child_root = children_root / f"{sequence:06d}"
            if child_root.is_symlink() or not child_root.is_dir():
                raise HistoryCampaignRepairPreparationError("preparation child root is invalid")
            child_preparations[sequence] = _verify_child_result(
                child_root,
                aggregate_child,
                planner_software_identity=cast(str, request["planner_software_identity"]),
            )
    manifest_path = root / "manifest.json"
    manifest = _load_receipted_object(manifest_path, name="preparation manifest")
    _content_hash(manifest, name="preparation manifest")
    expected = _manifest_payload(inputs, request, child_preparations, root)
    if manifest != expected:
        raise HistoryCampaignRepairPreparationError(
            "preparation manifest no longer matches its receipt-bound children"
        )
    return _completed_result(root, manifest, existing_complete=existing_complete)


def prepare_history_campaign_repairs(
    publication_root: Path,
    source_campaign_root: Path,
    campaign_coverage_audit_path: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    store_root: Path,
    preparation_root: Path,
    *,
    generated_at_utc: str,
    planner_software_identity: str,
) -> CompletedHistoryCampaignRepairPreparation:
    """Persist exact audits/plans only for aggregate-blocked candle children."""

    inputs = _verify_inputs(
        publication_root,
        source_campaign_root,
        campaign_coverage_audit_path,
        instrument_registry_path,
        capacity_evidence_path,
        store_root,
        planner_software_identity=planner_software_identity,
    )
    root = _resolve_root(preparation_root)
    request = _load_or_create_request(
        root,
        inputs,
        generated_at_utc=generated_at_utc,
    )
    allowed_partial_root = {
        "children",
        "manifest.json",
        "manifest.json.receipt.json",
        "request.json",
        "request.json.receipt.json",
    }
    if {item.name for item in root.iterdir()} - allowed_partial_root:
        raise HistoryCampaignRepairPreparationError("preparation root allowlist differs")
    children_root = root / "children"
    if children_root.exists() and (children_root.is_symlink() or not children_root.is_dir()):
        raise HistoryCampaignRepairPreparationError("preparation children root is invalid")
    manifest_state = _pair_state(root / "manifest.json")
    if manifest_state == "incomplete":
        raise HistoryCampaignRepairPreparationError("preparation manifest pair is incomplete")
    if manifest_state == "complete":
        return _verify_completed(root, inputs, request, existing_complete=True)

    child_preparations: dict[int, dict[str, object]] = {}
    for aggregate_child in inputs.child_results:
        if aggregate_child["status"] != "blocked" or aggregate_child["kind"] == "funding":
            continue
        sequence = cast(int, aggregate_child["sequence"])
        child_preparations[sequence] = _prepare_blocked_candle(
            inputs,
            aggregate_child,
            root / "children" / f"{sequence:06d}",
            request=request,
        )
    manifest = _manifest_payload(inputs, request, child_preparations, root)
    publish_evidence(root / "manifest.json", manifest)
    return _verify_completed(root, inputs, request, existing_complete=False)


def verify_completed_history_campaign_repair_preparation(
    publication_root: Path,
    source_campaign_root: Path,
    campaign_coverage_audit_path: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    store_root: Path,
    preparation_root: Path,
) -> CompletedHistoryCampaignRepairPreparation:
    """Verify a completed checkpoint without repeating blocked-child semantic audits."""

    root = _resolve_root(preparation_root)
    request_path = root / "request.json"
    if _pair_state(request_path) != "complete":
        raise HistoryCampaignRepairPreparationError("preparation request pair is incomplete")
    request = _load_receipted_object(request_path, name="preparation request")
    _content_hash(request, name="preparation request")
    planner_identity = _software_identity(
        request.get("planner_software_identity"),
        name="planner software identity",
    )
    inputs = _verify_inputs(
        publication_root,
        source_campaign_root,
        campaign_coverage_audit_path,
        instrument_registry_path,
        capacity_evidence_path,
        store_root,
        planner_software_identity=planner_identity,
    )
    stored_generated_at = request.get("generated_at_utc")
    if not isinstance(stored_generated_at, str) or request != _request_payload(
        inputs,
        stored_generated_at,
    ):
        raise HistoryCampaignRepairPreparationError("preparation request binding differs")
    if _pair_state(root / "manifest.json") != "complete":
        raise HistoryCampaignRepairPreparationError("preparation manifest pair is incomplete")
    return _verify_completed(root, inputs, request, existing_complete=True)
