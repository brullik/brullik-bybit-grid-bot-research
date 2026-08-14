"""Fast read-only progress observation for receipt-resumable history campaigns."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, Literal, cast

from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file

PROGRESS_CONTRACT: Final = "grid.history-campaign-progress/v1"
INTEGRITY_SCOPE: Final = "receipt-bound-metadata-no-page-read/v1"
CAMPAIGN_PLAN_CONTRACT: Final = "grid.public-history-campaign-plan/v1"
CAMPAIGN_MANIFEST_CONTRACT: Final = "grid.public-history-campaign-manifest/v1"
CAMPAIGN_RECEIPT_CONTRACT: Final = "grid.history-campaign-receipt/v1"
CHILD_RECEIPT_CONTRACT: Final = "grid.history-acquisition-receipt/v1"
HISTORY_PLAN_CONTRACT: Final = "grid.bybit-1m-history-plan/v1"
HISTORY_MANIFEST_CONTRACT: Final = "grid.bybit-1m-history-acquisition/v1"
FUNDING_PLAN_CONTRACT: Final = "grid.bybit-funding-history-plan/v1"
FUNDING_MANIFEST_CONTRACT: Final = "grid.bybit-funding-history-acquisition/v1"
MAX_CAMPAIGNS: Final = 16
MAX_JOBS: Final = 2_880
MIN_WINDOW_SECONDS: Final = 60
MAX_WINDOW_SECONDS: Final = 86_400
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
CAMPAIGN_ID_RE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{2,79}$")
JOB_ID_RE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
MONTH_RE: Final = re.compile(r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")

CampaignKind = Literal["trade", "mark", "funding"]

_PLAN_KEYS: Final = frozenset(
    {
        "campaign_id",
        "campaign_request",
        "campaign_request_sha256",
        "capacity_evidence_sha256",
        "contract",
        "funding_source_boundary",
        "instrument_evidence_sha256",
        "job_count",
        "jobs",
        "lifecycle_policy",
        "source_policy",
    }
)
_JOB_KEYS: Final = frozenset(
    {
        "bucket",
        "job_id",
        "job_plan_sha256",
        "job_root",
        "kind",
        "month",
        "planned_page_count",
        "request",
        "request_sha256",
        "sequence",
    }
)


class HistoryCampaignProgressError(RuntimeError):
    """Campaign progress metadata is incomplete, inconsistent, or unsafe to inspect."""


@dataclass(frozen=True, slots=True)
class _JobDescriptor:
    sequence: int
    job_id: str
    kind: CampaignKind
    relative_root: str
    plan_sha256: str
    request_sha256: str
    planned_page_count: int


@dataclass(frozen=True, slots=True)
class _CompletedJob:
    descriptor: _JobDescriptor
    manifest_sha256: str
    page_count: int
    row_count: int
    actual_http_requests: int
    started_at_ms: int | None
    completed_at_ms: int


def _load_canonical_object(path: Path) -> dict[str, object]:
    try:
        data = path.read_bytes()
        raw = json.loads(data)
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryCampaignProgressError(
            f"cannot load canonical campaign JSON: {path}"
        ) from error
    if not isinstance(raw, dict) or canonical_json_bytes(raw) != data:
        raise HistoryCampaignProgressError(f"campaign metadata is not canonical JSON: {path}")
    return cast(dict[str, object], raw)


def _verify_receipted_object(
    path: Path,
    receipt_path: Path,
    *,
    receipt_contract: str,
) -> tuple[dict[str, object], str]:
    if (
        not path.is_file()
        or not receipt_path.is_file()
        or path.is_symlink()
        or receipt_path.is_symlink()
    ):
        raise HistoryCampaignProgressError(f"artifact/receipt pair is incomplete: {path}")
    payload = _load_canonical_object(path)
    receipt = _load_canonical_object(receipt_path)
    digest = sha256_file(path)
    expected = {
        "artifact": path.name,
        "artifact_sha256": digest,
        "contract": receipt_contract,
        "status": "complete",
    }
    if receipt != expected:
        raise HistoryCampaignProgressError(f"artifact receipt does not verify: {path}")
    return payload, digest


def _integer(name: str, value: object, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise HistoryCampaignProgressError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise HistoryCampaignProgressError(f"{name} must be non-empty trimmed text")
    return value


def _sha256(name: str, value: object) -> str:
    text = _text(name, value)
    if SHA256_RE.fullmatch(text) is None:
        raise HistoryCampaignProgressError(f"{name} must be lowercase SHA-256 text")
    return text


def _mapping(name: str, value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise HistoryCampaignProgressError(f"{name} must be an object")
    return cast(dict[str, object], value)


def _array(name: str, value: object) -> list[object]:
    if not isinstance(value, list):
        raise HistoryCampaignProgressError(f"{name} must be an array")
    return cast(list[object], value)


def _safe_campaign_root(path: Path) -> Path:
    supplied = path.absolute()
    if supplied.is_symlink() or supplied.parent.is_symlink():
        raise HistoryCampaignProgressError("campaign root and namespace cannot be symlinks")
    root = supplied.resolve()
    if not root.is_dir() or root.parent.name != ".campaigns":
        raise HistoryCampaignProgressError("campaign root must be a directory below .campaigns")
    if root.parent.parent.is_symlink():
        raise HistoryCampaignProgressError("campaign staging root cannot be a symlink")
    return root


def _job_descriptor(raw: object, *, expected_sequence: int) -> _JobDescriptor:
    item = _mapping("campaign job", raw)
    if set(item) != _JOB_KEYS:
        raise HistoryCampaignProgressError("campaign job fields do not match v1")
    sequence = _integer(
        "campaign job sequence", item.get("sequence"), minimum=0, maximum=MAX_JOBS - 1
    )
    if sequence != expected_sequence:
        raise HistoryCampaignProgressError("campaign job sequence is not contiguous")
    _integer("campaign job bucket", item.get("bucket"), minimum=0, maximum=7)
    if MONTH_RE.fullmatch(_text("campaign job month", item.get("month"))) is None:
        raise HistoryCampaignProgressError("campaign job month does not match YYYY-MM")
    kind_raw = item.get("kind")
    kind: CampaignKind
    if kind_raw == "trade":
        kind = "trade"
    elif kind_raw == "mark":
        kind = "mark"
    elif kind_raw == "funding":
        kind = "funding"
    else:
        raise HistoryCampaignProgressError("campaign job kind is unsupported")
    relative_text = _text("campaign job root", item.get("job_root"))
    relative = PurePosixPath(relative_text)
    expected_namespace = ".funding-landing" if kind == "funding" else ".landing"
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or len(relative.parts) != 2
        or relative.parts[0] != expected_namespace
    ):
        raise HistoryCampaignProgressError("campaign job root escapes its Landing namespace")
    request = _mapping("campaign job request", item.get("request"))
    request_sha256 = _sha256("campaign job request SHA-256", item.get("request_sha256"))
    job_id = _text("campaign job id", item.get("job_id"))
    expected_request_contract = (
        "grid.bybit-funding-history-request/v1"
        if kind == "funding"
        else "grid.bybit-1m-history-request/v1"
    )
    if JOB_ID_RE.fullmatch(job_id) is None:
        raise HistoryCampaignProgressError("campaign job id does not match the v1 identifier")
    if (
        canonical_sha256(request) != request_sha256
        or request.get("job_id") != job_id
        or request.get("contract") != expected_request_contract
    ):
        raise HistoryCampaignProgressError("campaign job request hash does not verify")
    return _JobDescriptor(
        sequence=sequence,
        job_id=job_id,
        kind=kind,
        relative_root=relative_text,
        plan_sha256=_sha256("campaign child plan SHA-256", item.get("job_plan_sha256")),
        request_sha256=request_sha256,
        planned_page_count=_integer(
            "campaign planned page count",
            item.get("planned_page_count"),
            minimum=1,
            maximum=100_000,
        ),
    )


def _verified_campaign_plan(
    root: Path,
) -> tuple[dict[str, object], str, tuple[_JobDescriptor, ...]]:
    plan, plan_sha256 = _verify_receipted_object(
        root / "plan.json",
        root / "plan.receipt.json",
        receipt_contract=CAMPAIGN_RECEIPT_CONTRACT,
    )
    if set(plan) - _PLAN_KEYS or plan.get("contract") != CAMPAIGN_PLAN_CONTRACT:
        raise HistoryCampaignProgressError("campaign plan fields or contract do not match v1")
    if plan.get("lifecycle_policy") != "registry-lifecycle-intersection-v1":
        raise HistoryCampaignProgressError("campaign lifecycle policy is unsupported")
    _sha256("campaign capacity evidence SHA-256", plan.get("capacity_evidence_sha256"))
    _sha256("campaign instrument evidence SHA-256", plan.get("instrument_evidence_sha256"))
    _mapping("campaign source policy", plan.get("source_policy"))
    campaign_id = _text("campaign id", plan.get("campaign_id"))
    if CAMPAIGN_ID_RE.fullmatch(campaign_id) is None:
        raise HistoryCampaignProgressError("campaign id does not match the v1 identifier")
    if root.name != f"{campaign_id}--{plan_sha256[:16]}":
        raise HistoryCampaignProgressError("campaign root does not match its plan identity")
    request = _mapping("campaign request", plan.get("campaign_request"))
    request_sha256 = _sha256("campaign request SHA-256", plan.get("campaign_request_sha256"))
    if (
        canonical_sha256(request) != request_sha256
        or request.get("campaign_id") != campaign_id
        or request.get("contract") != "grid.public-history-campaign-request/v1"
    ):
        raise HistoryCampaignProgressError("campaign request binding does not verify")
    if plan.get("source_policy") != {
        "funding": "/v5/market/funding/history",
        "mark": "/v5/market/mark-price-kline",
        "tick_rows_requested": False,
        "trade": "/v5/market/kline",
    }:
        raise HistoryCampaignProgressError("campaign source policy is unsupported")
    jobs_raw = _array("campaign jobs", plan.get("jobs"))
    job_count = _integer("campaign job count", plan.get("job_count"), minimum=1, maximum=MAX_JOBS)
    if len(jobs_raw) != job_count:
        raise HistoryCampaignProgressError("campaign job count does not match the job array")
    jobs = tuple(
        _job_descriptor(item, expected_sequence=sequence) for sequence, item in enumerate(jobs_raw)
    )
    if len({job.job_id for job in jobs}) != len(jobs) or len(
        {job.relative_root for job in jobs}
    ) != len(jobs):
        raise HistoryCampaignProgressError("campaign job ids and roots must be unique")
    return plan, plan_sha256, jobs


def _child_contracts(kind: CampaignKind) -> tuple[str, str]:
    if kind == "funding":
        return FUNDING_PLAN_CONTRACT, FUNDING_MANIFEST_CONTRACT
    return HISTORY_PLAN_CONTRACT, HISTORY_MANIFEST_CONTRACT


def _completed_child(
    staging_root: Path,
    descriptor: _JobDescriptor,
    *,
    observed_at_ms: int,
) -> _CompletedJob | None:
    relative = PurePosixPath(descriptor.relative_root)
    child_root = staging_root.joinpath(*relative.parts)
    if not child_root.exists():
        return None
    if not child_root.is_dir() or child_root.is_symlink() or child_root.parent.is_symlink():
        raise HistoryCampaignProgressError("campaign child root must be a non-symlink directory")
    allowed = {
        ".run-lock",
        "plan.json",
        "plan.receipt.json",
        "pages",
        "manifest.json",
        "manifest.receipt.json",
        "completion-receipt.json",
    }
    names = {item.name for item in child_root.iterdir()}
    if names - allowed or not {"plan.json", "plan.receipt.json"}.issubset(names):
        raise HistoryCampaignProgressError("campaign child contains incomplete or unknown metadata")
    pages = child_root / "pages"
    if pages.exists() and (not pages.is_dir() or pages.is_symlink()):
        raise HistoryCampaignProgressError("campaign child pages must be a non-symlink directory")
    run_lock = child_root / ".run-lock"
    if run_lock.exists() and (not run_lock.is_dir() or run_lock.is_symlink()):
        raise HistoryCampaignProgressError(
            "campaign child run lock must be a non-symlink directory"
        )
    plan, child_plan_sha256 = _verify_receipted_object(
        child_root / "plan.json",
        child_root / "plan.receipt.json",
        receipt_contract=CHILD_RECEIPT_CONTRACT,
    )
    expected_plan_contract, expected_manifest_contract = _child_contracts(descriptor.kind)
    if child_root.name != f"{descriptor.job_id}--{child_plan_sha256[:16]}":
        raise HistoryCampaignProgressError("campaign child root does not match its plan identity")
    spec = _mapping("campaign child spec", plan.get("spec"))
    tasks = _array("campaign child tasks", plan.get("tasks"))
    if (
        plan.get("contract") != expected_plan_contract
        or child_plan_sha256 != descriptor.plan_sha256
        or spec.get("job_id") != descriptor.job_id
        or spec.get("request_sha256") != descriptor.request_sha256
        or len(tasks) != descriptor.planned_page_count
    ):
        raise HistoryCampaignProgressError("campaign child plan binding does not verify")
    for sequence, raw_task in enumerate(tasks):
        task = _mapping("campaign child task", raw_task)
        if task.get("sequence") != sequence:
            raise HistoryCampaignProgressError("campaign child task sequence is not contiguous")
    if run_lock.exists():
        return None
    completion_names = {"manifest.json", "manifest.receipt.json", "completion-receipt.json"}
    present_completion_names = names & completion_names
    if present_completion_names and present_completion_names != completion_names:
        raise HistoryCampaignProgressError("campaign child completion pair is incomplete")
    if not present_completion_names:
        return None
    manifest, manifest_sha256 = _verify_receipted_object(
        child_root / "manifest.json",
        child_root / "completion-receipt.json",
        receipt_contract=CHILD_RECEIPT_CONTRACT,
    )
    manifest_receipt = _load_canonical_object(child_root / "manifest.receipt.json")
    expected_manifest_receipt = {
        "artifact": "manifest.json",
        "artifact_sha256": manifest_sha256,
        "contract": CHILD_RECEIPT_CONTRACT,
        "status": "complete",
    }
    if manifest_receipt != expected_manifest_receipt:
        raise HistoryCampaignProgressError("campaign child manifest receipt does not verify")
    page_count = _integer(
        "campaign child page count", manifest.get("page_count"), minimum=1, maximum=100_000
    )
    rows = _integer(
        "campaign child row count",
        manifest.get("row_count"),
        minimum=0,
        maximum=2**63 - 1,
    )
    started_raw = manifest.get("started_at_ms")
    started_at_ms = (
        None
        if started_raw is None
        else _integer("campaign child started time", started_raw, minimum=0, maximum=2**63 - 1)
    )
    completed_at_ms = _integer(
        "campaign child completed time",
        manifest.get("completed_at_ms"),
        minimum=started_at_ms if started_at_ms is not None else 0,
        maximum=2**63 - 1,
    )
    if completed_at_ms > observed_at_ms:
        return None
    request_bound = _mapping("campaign child request bound", manifest.get("request_bound"))
    actual_http_requests = _integer(
        "campaign child HTTP request count",
        request_bound.get("actual_http_requests"),
        minimum=0,
        maximum=500_000,
    )
    manifest_pages = _array("campaign child manifest pages", manifest.get("pages"))
    if (
        manifest.get("contract") != expected_manifest_contract
        or manifest.get("status") != "complete"
        or manifest.get("job_id") != descriptor.job_id
        or manifest.get("plan_sha256") != descriptor.plan_sha256
        or manifest.get("request_sha256") != descriptor.request_sha256
        or page_count != descriptor.planned_page_count
        or len(manifest_pages) != page_count
    ):
        raise HistoryCampaignProgressError("campaign child manifest binding does not verify")
    manifest_row_count = 0
    manifest_attempt_count = 0
    for sequence, raw_page in enumerate(manifest_pages):
        page = _mapping("campaign child manifest page", raw_page)
        if page.get("sequence") != sequence:
            raise HistoryCampaignProgressError("campaign child manifest page sequence is invalid")
        manifest_row_count += _integer(
            "campaign child manifest page row count",
            page.get("row_count"),
            minimum=0,
            maximum=2**63 - 1,
        )
        manifest_attempt_count += _integer(
            "campaign child manifest page attempt count",
            page.get("attempt_count"),
            minimum=1,
            maximum=5,
        )
    if manifest_row_count != rows or manifest_attempt_count != actual_http_requests:
        raise HistoryCampaignProgressError("campaign child manifest totals do not verify")
    return _CompletedJob(
        descriptor=descriptor,
        manifest_sha256=manifest_sha256,
        page_count=page_count,
        row_count=rows,
        actual_http_requests=actual_http_requests,
        started_at_ms=started_at_ms,
        completed_at_ms=completed_at_ms,
    )


def _verify_campaign_completion(
    root: Path,
    *,
    plan: Mapping[str, object],
    plan_sha256: str,
    jobs: Sequence[_CompletedJob],
    observed_at_ms: int,
) -> bool:
    manifest_exists = (root / "manifest.json").exists()
    receipt_exists = (root / "completion-receipt.json").exists()
    if manifest_exists != receipt_exists:
        raise HistoryCampaignProgressError("campaign aggregate completion pair is incomplete")
    if not manifest_exists:
        return False
    manifest, _manifest_sha256 = _verify_receipted_object(
        root / "manifest.json",
        root / "completion-receipt.json",
        receipt_contract=CAMPAIGN_RECEIPT_CONTRACT,
    )
    manifest_jobs = _array("campaign aggregate jobs", manifest.get("jobs"))
    completed_at_ms = _integer(
        "campaign aggregate completed time",
        manifest.get("completed_at_ms"),
        minimum=0,
        maximum=2**63 - 1,
    )
    if completed_at_ms > observed_at_ms:
        return False
    if (
        manifest.get("contract") != CAMPAIGN_MANIFEST_CONTRACT
        or manifest.get("status") != "complete"
        or manifest.get("campaign_id") != plan.get("campaign_id")
        or manifest.get("campaign_plan_sha256") != plan_sha256
        or manifest.get("campaign_request_sha256") != plan.get("campaign_request_sha256")
        or manifest.get("capacity_evidence_sha256") != plan.get("capacity_evidence_sha256")
        or manifest.get("instrument_evidence_sha256") != plan.get("instrument_evidence_sha256")
        or manifest.get("job_count") != len(jobs)
        or manifest.get("http_request_count") != sum(item.actual_http_requests for item in jobs)
        or manifest.get("page_count") != sum(item.page_count for item in jobs)
        or manifest.get("row_count") != sum(item.row_count for item in jobs)
        or len(manifest_jobs) != len(jobs)
        or any(item.completed_at_ms > completed_at_ms for item in jobs)
    ):
        raise HistoryCampaignProgressError("campaign aggregate manifest binding does not verify")
    for raw, completed in zip(manifest_jobs, jobs, strict=True):
        entry = _mapping("campaign aggregate job", raw)
        descriptor = completed.descriptor
        expected = {
            "actual_http_requests": completed.actual_http_requests,
            "job_id": descriptor.job_id,
            "job_manifest_sha256": completed.manifest_sha256,
            "job_plan_sha256": descriptor.plan_sha256,
            "job_root": descriptor.relative_root,
            "kind": descriptor.kind,
            "page_count": completed.page_count,
            "row_count": completed.row_count,
            "sequence": descriptor.sequence,
        }
        if entry != expected:
            raise HistoryCampaignProgressError("campaign aggregate child entry does not verify")
    return True


def _rate_projection(
    completed: Sequence[_CompletedJob],
    *,
    pending_page_count: int,
    observed_at_ms: int,
    window_seconds: int,
) -> dict[str, int | None]:
    cutoff = max(0, observed_at_ms - window_seconds * 1_000)
    recent = sorted(
        (item for item in completed if item.completed_at_ms >= cutoff),
        key=lambda item: (item.completed_at_ms, item.descriptor.sequence),
    )
    if len(recent) >= 2:
        sample = recent[1:]
        elapsed_ms = observed_at_ms - recent[0].completed_at_ms
    elif recent:
        sample = recent
        elapsed_ms = (
            recent[0].completed_at_ms - recent[0].started_at_ms
            if recent[0].started_at_ms is not None
            else 0
        )
    else:
        sample = []
        elapsed_ms = 0
    sample_pages = sum(item.descriptor.planned_page_count for item in sample)
    rate_milli = sample_pages * 1_000_000 // elapsed_ms if sample_pages and elapsed_ms else None
    eta_seconds = (
        (pending_page_count * 1_000 + rate_milli - 1) // rate_milli
        if pending_page_count and rate_milli
        else (0 if pending_page_count == 0 else None)
    )
    return {
        "eta_seconds": eta_seconds,
        "rate_sample_completed_job_count": len(sample),
        "rate_sample_elapsed_ms": elapsed_ms,
        "rate_sample_planned_page_count": sample_pages,
        "recent_rate_milli_pages_per_second": rate_milli,
    }


def _campaign_progress(
    supplied_root: Path,
    *,
    observed_at_ms: int,
    window_seconds: int,
) -> tuple[dict[str, object], int]:
    root = _safe_campaign_root(supplied_root)
    names = {item.name for item in root.iterdir()}
    allowed = {"plan.json", "plan.receipt.json", "manifest.json", "completion-receipt.json"}
    if names - allowed or not {"plan.json", "plan.receipt.json"}.issubset(names):
        raise HistoryCampaignProgressError("campaign root contains incomplete or unknown metadata")
    plan, plan_sha256, descriptors = _verified_campaign_plan(root)
    staging_root = root.parent.parent
    completed = tuple(
        result
        for descriptor in descriptors
        if (
            result := _completed_child(
                staging_root,
                descriptor,
                observed_at_ms=observed_at_ms,
            )
        )
        is not None
    )
    aggregate_complete = _verify_campaign_completion(
        root,
        plan=plan,
        plan_sha256=plan_sha256,
        jobs=completed,
        observed_at_ms=observed_at_ms,
    )
    if aggregate_complete and len(completed) != len(descriptors):
        raise HistoryCampaignProgressError("completed campaign has incomplete children")
    completed_pages = sum(item.descriptor.planned_page_count for item in completed)
    planned_pages = sum(item.planned_page_count for item in descriptors)
    pending_pages = planned_pages - completed_pages
    if aggregate_complete:
        status = "complete"
    elif len(completed) == len(descriptors):
        status = "finalization-pending"
    elif completed:
        status = "in-progress"
    else:
        status = "not-started"
    last_completed_at_ms = max((item.completed_at_ms for item in completed), default=None)
    rate = _rate_projection(
        completed,
        pending_page_count=pending_pages,
        observed_at_ms=observed_at_ms,
        window_seconds=window_seconds,
    )
    payload: dict[str, object] = {
        "campaign_id": plan["campaign_id"],
        "campaign_plan_sha256": plan_sha256,
        "completed_job_count": len(completed),
        "completed_planned_page_count": completed_pages,
        "completed_row_count": sum(item.row_count for item in completed),
        "job_count": len(descriptors),
        "last_completed_at_ms": last_completed_at_ms,
        "last_completion_age_seconds": (
            (observed_at_ms - last_completed_at_ms) // 1_000
            if last_completed_at_ms is not None
            else None
        ),
        "pending_job_count": len(descriptors) - len(completed),
        "pending_planned_page_count": pending_pages,
        "planned_page_count": planned_pages,
        "progress_millionths": completed_pages * 1_000_000 // planned_pages,
        "status": status,
        **rate,
    }
    return payload, shutil.disk_usage(root).free


def build_history_campaign_progress(
    campaign_roots: Sequence[Path],
    *,
    observed_at_ms: int,
    window_seconds: int = 3_600,
) -> dict[str, object]:
    """Inspect one or more campaigns without network, mutation, or page-artifact reads."""

    if not campaign_roots or len(campaign_roots) > MAX_CAMPAIGNS:
        raise HistoryCampaignProgressError(
            f"campaign roots must contain 1 through {MAX_CAMPAIGNS} values"
        )
    _integer("observed_at_ms", observed_at_ms, minimum=0, maximum=2**63 - 1)
    _integer(
        "window_seconds",
        window_seconds,
        minimum=MIN_WINDOW_SECONDS,
        maximum=MAX_WINDOW_SECONDS,
    )
    resolved = [path.absolute().resolve() for path in campaign_roots]
    if len(set(resolved)) != len(resolved):
        raise HistoryCampaignProgressError("campaign roots must be unique")
    campaigns: list[dict[str, object]] = []
    free_bytes: list[int] = []
    for root in campaign_roots:
        payload, observed_free = _campaign_progress(
            root,
            observed_at_ms=observed_at_ms,
            window_seconds=window_seconds,
        )
        campaigns.append(payload)
        free_bytes.append(observed_free)
    planned_pages = sum(cast(int, item["planned_page_count"]) for item in campaigns)
    completed_pages = sum(cast(int, item["completed_planned_page_count"]) for item in campaigns)
    eta_values = [
        cast(int, item["eta_seconds"])
        for item in campaigns
        if item["status"] != "complete" and item["eta_seconds"] is not None
    ]
    incomplete_count = sum(item["status"] != "complete" for item in campaigns)
    aggregate_eta = (
        0
        if incomplete_count == 0
        else (max(eta_values) if len(eta_values) == incomplete_count else None)
    )
    return {
        "assurances": {
            "authoritative_campaign_verification_performed": False,
            "mutation_performed": False,
            "network_request_performed": False,
            "page_artifact_bytes_read": 0,
            "receipt_bound_metadata_verified": True,
        },
        "campaign_count": len(campaigns),
        "campaigns": campaigns,
        "contract": PROGRESS_CONTRACT,
        "integrity_scope": INTEGRITY_SCOPE,
        "minimum_volume_free_bytes": min(free_bytes),
        "observed_at_ms": observed_at_ms,
        "projection": {
            "eta_seconds": aggregate_eta,
            "rate_is_descriptive_not_acceptance_evidence": True,
            "window_seconds": window_seconds,
        },
        "summary": {
            "completed_campaign_count": len(campaigns) - incomplete_count,
            "completed_job_count": sum(
                cast(int, item["completed_job_count"]) for item in campaigns
            ),
            "completed_planned_page_count": completed_pages,
            "job_count": sum(cast(int, item["job_count"]) for item in campaigns),
            "pending_campaign_count": incomplete_count,
            "pending_job_count": sum(cast(int, item["pending_job_count"]) for item in campaigns),
            "pending_planned_page_count": planned_pages - completed_pages,
            "planned_page_count": planned_pages,
            "progress_millionths": completed_pages * 1_000_000 // planned_pages,
        },
    }
