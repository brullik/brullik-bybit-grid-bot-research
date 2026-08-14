"""Receipt-resumable canonical publication for a completed public history campaign."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, Literal, cast

from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file
from grid_market_store import (
    FUNDING_CANONICAL_LAYOUT_ID,
    MAX_MEMORY_PERCENT,
    FundingPublicationPlan,
    HostSnapshot,
    PublicationError,
    PublicationPlan,
    PublishedDataset,
    verify_committed_candle_dataset,
    verify_committed_funding_dataset,
)

from grid_data.funding_acquisition import (
    CompletedFundingJob,
    FundingAcquisitionError,
    verify_completed_funding_job_integrity,
)
from grid_data.funding_publication import (
    FUNDING_HISTORY_PUBLICATION_CONTRACT,
    ResolvedFundingPublication,
    preflight_completed_funding_publication,
    publish_preflighted_funding,
)
from grid_data.history_acquisition import (
    CANONICAL_ADMISSION_POLICY,
    CANONICAL_ADMISSION_REASONS,
    CompletedHistoryJob,
    HistoryAcquisitionError,
    verify_completed_history_job_integrity,
)
from grid_data.history_campaign import (
    CAMPAIGN_RECEIPT_CONTRACT,
    CompletedHistoryCampaign,
    HistoryCampaignError,
    verify_completed_history_campaign,
)
from grid_data.history_publication import (
    ResolvedHistoryPublication,
    history_publication_build_config_sha256,
    preflight_completed_history_publication,
    publish_preflighted_history,
)
from grid_data.history_request import load_verified_capacity_evidence
from grid_data.instrument_registry import load_verified_instrument_registry

CAMPAIGN_PUBLICATION_PLAN_CONTRACT: Final = "grid.history-campaign-publication-plan/v1"
CAMPAIGN_PUBLICATION_MANIFEST_CONTRACT: Final = "grid.history-campaign-publication-manifest/v1"
CAMPAIGN_PUBLICATION_RECEIPT_CONTRACT: Final = "grid.history-campaign-publication-receipt/v1"
MAX_CAMPAIGN_PUBLICATIONS: Final = 2_880
MAX_PREPARED_PLAN_SNAPSHOT_AGE_MS: Final = 60_000
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
CampaignKind = Literal["trade", "mark", "funding"]
ResolvedChildPublication = ResolvedHistoryPublication | ResolvedFundingPublication

_PUBLICATION_POLICY: Final = {
    "child_order": "source-campaign-sequence-v1",
    "max_concurrent_writers": 1,
    "private_endpoints": False,
    "receipt_resume": True,
    "tick_rows_requested": False,
}


def _verify_source_child_integrity(
    job_root: Path,
    kind: CampaignKind,
) -> CompletedHistoryJob | CompletedFundingJob:
    """Verify immutable source bytes/receipts after semantic admission already occurred."""

    return (
        verify_completed_funding_job_integrity(job_root)
        if kind == "funding"
        else verify_completed_history_job_integrity(job_root)
    )


_PLAN_JOB_KEYS: Final = {
    "dataset_id",
    "dataset_root",
    "dataset_type",
    "input_table_sha256",
    "job_id",
    "kind",
    "planned_peak_memory_bytes",
    "publication_request_sha256",
    "required_free_bytes",
    "row_count",
    "sequence",
    "source_job_manifest_sha256",
    "source_job_plan_sha256",
    "source_job_root",
}
_PLAN_JOB_ADMISSION_KEYS: Final = _PLAN_JOB_KEYS | {
    "canonical_admission",
    "source_row_count",
}
_MANIFEST_DATASET_KEYS: Final = {
    "dataset_id",
    "dataset_root",
    "dataset_type",
    "file_count",
    "kind",
    "manifest_sha256",
    "parquet_bytes",
    "publication_request_sha256",
    "row_count",
    "sequence",
    "source_job_manifest_sha256",
}
_MANIFEST_DATASET_ADMISSION_KEYS: Final = _MANIFEST_DATASET_KEYS | {
    "canonical_admission",
    "source_row_count",
}
_CANONICAL_ADMISSION_KEYS: Final = {
    "admitted_row_count",
    "excluded_row_count",
    "excluded_rows_sha256",
    "policy",
    "reason_counts",
    "source_row_count",
}
_PLAN_KEYS: Final = {
    "campaign_id",
    "capacity_evidence_sha256",
    "contract",
    "dataset_count",
    "instrument_evidence_sha256",
    "jobs",
    "publication_policy",
    "publisher_software_identity",
    "row_count",
    "source_campaign_manifest_sha256",
    "source_campaign_plan_sha256",
}


class HistoryCampaignPublicationError(RuntimeError):
    """Raised when aggregate canonical publication cannot be proven safe."""


@dataclass(frozen=True, slots=True)
class SourceCampaignJob:
    sequence: int
    kind: CampaignKind
    job_id: str
    job_root_relative: str
    job_root: Path
    job_plan_sha256: str
    job_manifest_sha256: str
    row_count: int


@dataclass(frozen=True, slots=True)
class PreparedCampaignPublication:
    sequence: int
    kind: CampaignKind
    job_id: str
    source_job_root: str
    source_job_plan_sha256: str
    source_job_manifest_sha256: str
    dataset_id: str
    dataset_type: str
    dataset_root: str
    input_table_sha256: str
    publication_request_sha256: str
    row_count: int
    source_row_count: int
    canonical_admission: dict[str, object] | None
    required_free_bytes: int
    planned_peak_memory_bytes: int
    existing_commit: bool

    def plan_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "dataset_id": self.dataset_id,
            "dataset_root": self.dataset_root,
            "dataset_type": self.dataset_type,
            "input_table_sha256": self.input_table_sha256,
            "job_id": self.job_id,
            "kind": self.kind,
            "planned_peak_memory_bytes": self.planned_peak_memory_bytes,
            "publication_request_sha256": self.publication_request_sha256,
            "required_free_bytes": self.required_free_bytes,
            "row_count": self.row_count,
            "sequence": self.sequence,
            "source_job_manifest_sha256": self.source_job_manifest_sha256,
            "source_job_plan_sha256": self.source_job_plan_sha256,
            "source_job_root": self.source_job_root,
        }
        if self.canonical_admission is not None:
            payload["canonical_admission"] = self.canonical_admission
            payload["source_row_count"] = self.source_row_count
        return payload


@dataclass(frozen=True, slots=True)
class HistoryCampaignPublicationPlan:
    source_campaign: CompletedHistoryCampaign
    source_campaign_plan_sha256: str
    source_campaign_manifest_sha256: str
    instrument_registry_path: Path
    instrument_evidence_sha256: str
    capacity_evidence_path: Path
    capacity_evidence_sha256: str
    store_root: Path
    publication_root: Path
    plan_path: Path
    plan_receipt_path: Path
    manifest_path: Path
    completion_receipt_path: Path
    publisher_software_identity: str
    jobs: tuple[PreparedCampaignPublication, ...]
    plan_payload: dict[str, object]
    plan_sha256: str
    required_free_bytes: int
    planned_peak_memory_bytes: int
    existing_complete: bool


@dataclass(frozen=True, slots=True)
class CompletedHistoryCampaignPublication:
    publication_root: Path
    plan_path: Path
    manifest_path: Path
    receipt_path: Path
    manifest_sha256: str
    dataset_count: int
    row_count: int
    file_count: int
    parquet_bytes: int
    published_datasets: tuple[PublishedDataset, ...]


def _load_canonical_object(path: Path) -> dict[str, object]:
    try:
        data = path.read_bytes()
        raw = json.loads(data)
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryCampaignPublicationError(f"cannot load canonical JSON: {path}") from error
    if not isinstance(raw, dict) or canonical_json_bytes(raw) != data:
        raise HistoryCampaignPublicationError(f"artifact is not canonical JSON: {path}")
    return cast(dict[str, object], raw)


def _receipt_payload(artifact: str, digest: str) -> dict[str, object]:
    return {
        "artifact": artifact,
        "artifact_sha256": digest,
        "contract": CAMPAIGN_PUBLICATION_RECEIPT_CONTRACT,
        "status": "complete",
    }


def _verify_receipt(path: Path, receipt_path: Path) -> tuple[dict[str, object], str]:
    if not path.is_file() or not receipt_path.is_file():
        raise HistoryCampaignPublicationError(
            f"publication artifact/receipt pair is incomplete: {path}"
        )
    payload = _load_canonical_object(path)
    receipt = _load_canonical_object(receipt_path)
    digest = sha256_file(path)
    if receipt != _receipt_payload(path.name, digest):
        raise HistoryCampaignPublicationError(f"publication receipt does not verify: {path}")
    return payload, digest


def _atomic_write_new(path: Path, payload: Mapping[str, object]) -> None:
    if path.exists():
        raise HistoryCampaignPublicationError(f"refusing to replace publication artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".building",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise HistoryCampaignPublicationError(f"{name} must be non-empty trimmed text")
    return value


def _integer(name: str, value: object, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise HistoryCampaignPublicationError(f"{name} must be an integer >= {minimum}")
    return value


def _sha256(name: str, value: object) -> str:
    text = _text(name, value)
    if SHA256_RE.fullmatch(text) is None:
        raise HistoryCampaignPublicationError(f"{name} must be a lowercase SHA-256 digest")
    return text


def _canonical_admission(
    value: object,
    *,
    source_row_count: int,
) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != _CANONICAL_ADMISSION_KEYS:
        raise HistoryCampaignPublicationError("canonical admission fields differ from v1")
    admitted = _integer("canonical admitted row count", value.get("admitted_row_count"))
    excluded = _integer(
        "canonical excluded row count",
        value.get("excluded_row_count"),
        minimum=1,
    )
    if (
        value.get("policy") != CANONICAL_ADMISSION_POLICY
        or value.get("source_row_count") != source_row_count
        or admitted + excluded != source_row_count
    ):
        raise HistoryCampaignPublicationError("canonical admission counts do not verify")
    excluded_sha = value.get("excluded_rows_sha256")
    if not isinstance(excluded_sha, str) or re.fullmatch(r"[0-9a-f]{64}", excluded_sha) is None:
        raise HistoryCampaignPublicationError("canonical admission exclusion hash is invalid")
    raw_reasons = value.get("reason_counts")
    if (
        not isinstance(raw_reasons, dict)
        or set(raw_reasons) != set(CANONICAL_ADMISSION_REASONS)
        or any(
            isinstance(raw_reasons[reason], bool)
            or not isinstance(raw_reasons[reason], int)
            or cast(int, raw_reasons[reason]) < 0
            for reason in CANONICAL_ADMISSION_REASONS
        )
        or sum(cast(int, raw_reasons[reason]) for reason in CANONICAL_ADMISSION_REASONS) != excluded
    ):
        raise HistoryCampaignPublicationError("canonical admission reasons do not verify")
    return cast(dict[str, object], value)


def _source_job_path(
    source_campaign_root: Path,
    relative_text: object,
    kind: CampaignKind,
) -> tuple[str, Path]:
    relative_value = _text("source job root", relative_text)
    relative = PurePosixPath(relative_value)
    expected_parent = ".funding-landing" if kind == "funding" else ".landing"
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or len(relative.parts) != 2
        or relative.parts[0] != expected_parent
    ):
        raise HistoryCampaignPublicationError("source job root escapes its Landing namespace")
    staging_root = source_campaign_root.parent.parent
    return relative.as_posix(), staging_root.joinpath(*relative.parts)


def _source_jobs(
    completed: CompletedHistoryCampaign,
) -> tuple[SourceCampaignJob, ...]:
    source_plan = _load_canonical_object(completed.plan_path)
    source_manifest = _load_canonical_object(completed.manifest_path)
    raw_plan_jobs = source_plan.get("jobs")
    raw_manifest_jobs = source_manifest.get("jobs")
    if not isinstance(raw_plan_jobs, list) or not isinstance(raw_manifest_jobs, list):
        raise HistoryCampaignPublicationError("source campaign jobs must be arrays")
    if not raw_plan_jobs or len(raw_plan_jobs) != len(raw_manifest_jobs):
        raise HistoryCampaignPublicationError("source campaign job inventories differ")
    if len(raw_plan_jobs) > MAX_CAMPAIGN_PUBLICATIONS:
        raise HistoryCampaignPublicationError("source campaign exceeds publication hard bound")
    jobs: list[SourceCampaignJob] = []
    for sequence, (raw_plan, raw_manifest) in enumerate(
        zip(raw_plan_jobs, raw_manifest_jobs, strict=True)
    ):
        if not isinstance(raw_plan, dict) or not isinstance(raw_manifest, dict):
            raise HistoryCampaignPublicationError("source campaign child must be an object")
        kind_raw = raw_plan.get("kind")
        if kind_raw not in ("trade", "mark", "funding") or raw_manifest.get("kind") != kind_raw:
            raise HistoryCampaignPublicationError("source campaign child kind is invalid")
        kind = cast(CampaignKind, kind_raw)
        if raw_plan.get("sequence") != sequence or raw_manifest.get("sequence") != sequence:
            raise HistoryCampaignPublicationError("source campaign sequences are not contiguous")
        job_id = _text("source job id", raw_plan.get("job_id"))
        if raw_manifest.get("job_id") != job_id:
            raise HistoryCampaignPublicationError("source campaign job identities differ")
        plan_sha = _text("source job plan hash", raw_plan.get("job_plan_sha256"))
        manifest_sha = _text("source job manifest hash", raw_manifest.get("job_manifest_sha256"))
        if raw_manifest.get("job_plan_sha256") != plan_sha:
            raise HistoryCampaignPublicationError("source campaign child plan hashes differ")
        relative, job_root = _source_job_path(
            completed.campaign_root,
            raw_plan.get("job_root"),
            kind,
        )
        if raw_manifest.get("job_root") != relative:
            raise HistoryCampaignPublicationError("source campaign child roots differ")
        row_count = _integer("source job row count", raw_manifest.get("row_count"))
        jobs.append(
            SourceCampaignJob(
                sequence=sequence,
                kind=kind,
                job_id=job_id,
                job_root_relative=relative,
                job_root=job_root,
                job_plan_sha256=plan_sha,
                job_manifest_sha256=manifest_sha,
                row_count=row_count,
            )
        )
    return tuple(jobs)


def _source_from_completed_child(
    completed: CompletedHistoryJob | CompletedFundingJob,
    *,
    sequence: int,
    kind: CampaignKind,
    source_campaign_root: Path,
) -> SourceCampaignJob:
    plan = _load_canonical_object(completed.plan_path)
    raw_spec = plan.get("spec")
    if not isinstance(raw_spec, dict):
        raise HistoryCampaignPublicationError("verified source child has no plan spec")
    job_id = _text("source job id", raw_spec.get("job_id"))
    try:
        relative = completed.job_root.relative_to(source_campaign_root.parent.parent).as_posix()
    except ValueError as error:
        raise HistoryCampaignPublicationError(
            "verified source child escapes the campaign staging root"
        ) from error
    validated_relative, expected_root = _source_job_path(
        source_campaign_root,
        relative,
        kind,
    )
    if expected_root.resolve() != completed.job_root:
        raise HistoryCampaignPublicationError("verified source child root is not deterministic")
    return SourceCampaignJob(
        sequence=sequence,
        kind=kind,
        job_id=job_id,
        job_root_relative=validated_relative,
        job_root=completed.job_root,
        job_plan_sha256=sha256_file(completed.plan_path),
        job_manifest_sha256=completed.manifest_sha256,
        row_count=completed.row_count,
    )


def _dataset_type(kind: CampaignKind) -> str:
    return {
        "trade": "trade_kline_1m",
        "mark": "mark_kline_1m",
        "funding": "funding_event",
    }[kind]


def _dataset_id(kind: CampaignKind, source_manifest_sha256: str) -> str:
    prefix = {"trade": "trade-1m", "mark": "mark-1m", "funding": "funding"}[kind]
    return f"{prefix}-{source_manifest_sha256[:24]}"


def _resolved_plan(
    resolved: ResolvedChildPublication,
) -> PublicationPlan | FundingPublicationPlan:
    return resolved.plan


def _prepare_child(
    source: SourceCampaignJob,
    resolved: ResolvedChildPublication,
    *,
    store_root: Path,
) -> PreparedCampaignPublication:
    child_plan = _resolved_plan(resolved)
    dataset_type = child_plan.batch.dataset_type.value
    if dataset_type != _dataset_type(source.kind):
        raise HistoryCampaignPublicationError("canonical dataset type differs from source kind")
    if child_plan.spec.dataset_id != _dataset_id(source.kind, source.job_manifest_sha256):
        raise HistoryCampaignPublicationError("canonical dataset id is not source-derived")
    canonical_admission: dict[str, object] | None = None
    if isinstance(resolved, ResolvedHistoryPublication):
        admission = resolved.canonical_admission
        if admission.source_row_count != source.row_count:
            raise HistoryCampaignPublicationError(
                "canonical admission source count differs from source job"
            )
        if admission.excluded_row_count:
            canonical_admission = admission.public_payload()
        if child_plan.batch.table.num_rows != admission.admitted_row_count:
            raise HistoryCampaignPublicationError(
                "canonical input row count differs from admission result"
            )
    elif child_plan.batch.table.num_rows != source.row_count:
        raise HistoryCampaignPublicationError("canonical input row count differs from source job")
    expected_root = PurePosixPath("datasets") / child_plan.spec.dataset_id
    try:
        relative_root = child_plan.paths.dataset_root.relative_to(store_root.resolve()).as_posix()
    except ValueError as error:
        raise HistoryCampaignPublicationError(
            "canonical dataset root escapes the market store"
        ) from error
    if relative_root != expected_root.as_posix():
        raise HistoryCampaignPublicationError("canonical dataset root is not deterministic")
    return PreparedCampaignPublication(
        sequence=source.sequence,
        kind=source.kind,
        job_id=source.job_id,
        source_job_root=source.job_root_relative,
        source_job_plan_sha256=source.job_plan_sha256,
        source_job_manifest_sha256=source.job_manifest_sha256,
        dataset_id=child_plan.spec.dataset_id,
        dataset_type=dataset_type,
        dataset_root=relative_root,
        input_table_sha256=child_plan.input_table_sha256,
        publication_request_sha256=child_plan.request_sha256,
        row_count=child_plan.batch.table.num_rows,
        source_row_count=source.row_count,
        canonical_admission=canonical_admission,
        required_free_bytes=child_plan.required_free_bytes,
        planned_peak_memory_bytes=child_plan.planned_peak_memory_bytes,
        existing_commit=child_plan.existing_commit,
    )


def _preflight_child_publication(
    job_root: Path,
    kind: CampaignKind,
    *,
    sequence: int,
    store_root: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    snapshot: HostSnapshot,
    now_ms: int,
    software_identity: str,
) -> ResolvedChildPublication:
    try:
        if kind == "funding":
            resolved: ResolvedChildPublication = preflight_completed_funding_publication(
                store_root,
                job_root,
                instrument_registry_path,
                capacity_evidence_path,
                snapshot,
                now_ms=now_ms,
                software_identity=software_identity,
            )
        else:
            resolved = preflight_completed_history_publication(
                store_root,
                job_root,
                instrument_registry_path,
                capacity_evidence_path,
                snapshot,
                now_ms=now_ms,
                software_identity=software_identity,
            )
    except (FundingAcquisitionError, HistoryAcquisitionError, PublicationError) as error:
        raise HistoryCampaignPublicationError(
            f"source campaign child {sequence} publication preflight failed: {error}"
        ) from error
    return resolved


def _resolve_child(
    source: SourceCampaignJob,
    *,
    store_root: Path,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    snapshot: HostSnapshot,
    now_ms: int,
    software_identity: str,
) -> tuple[PreparedCampaignPublication, ResolvedChildPublication]:
    resolved = _preflight_child_publication(
        source.job_root,
        source.kind,
        sequence=source.sequence,
        store_root=store_root,
        instrument_registry_path=instrument_registry_path,
        capacity_evidence_path=capacity_evidence_path,
        snapshot=snapshot,
        now_ms=now_ms,
        software_identity=software_identity,
    )
    return _prepare_child(source, resolved, store_root=store_root), resolved


def _campaign_plan_payload(
    *,
    source_campaign: CompletedHistoryCampaign,
    source_campaign_plan_sha256: str,
    instrument_evidence_sha256: str,
    capacity_evidence_sha256: str,
    publisher_software_identity: str,
    jobs: tuple[PreparedCampaignPublication, ...],
) -> dict[str, object]:
    source_plan = _load_canonical_object(source_campaign.plan_path)
    campaign_id = _text("source campaign id", source_plan.get("campaign_id"))
    return {
        "campaign_id": campaign_id,
        "capacity_evidence_sha256": capacity_evidence_sha256,
        "contract": CAMPAIGN_PUBLICATION_PLAN_CONTRACT,
        "dataset_count": len(jobs),
        "instrument_evidence_sha256": instrument_evidence_sha256,
        "jobs": [job.plan_payload() for job in jobs],
        "publication_policy": _PUBLICATION_POLICY,
        "publisher_software_identity": publisher_software_identity,
        "row_count": sum(job.row_count for job in jobs),
        "source_campaign_manifest_sha256": source_campaign.manifest_sha256,
        "source_campaign_plan_sha256": source_campaign_plan_sha256,
    }


def _existing_state(
    publication_root: Path,
    *,
    expected_plan: Mapping[str, object],
    source_campaign_root: Path,
) -> bool:
    if not publication_root.exists():
        return False
    if not publication_root.is_dir() or publication_root.is_symlink():
        raise HistoryCampaignPublicationError(
            "publication campaign root must be a non-symlink directory"
        )
    names = {path.name for path in publication_root.iterdir()}
    partial = {"plan.json", "plan.receipt.json"}
    complete = partial | {"manifest.json", "completion-receipt.json"}
    if names not in (partial, complete):
        raise HistoryCampaignPublicationError(
            "publication campaign root contains incomplete or orphan artifacts"
        )
    plan, _digest = _verify_receipt(
        publication_root / "plan.json",
        publication_root / "plan.receipt.json",
    )
    if plan != expected_plan:
        raise HistoryCampaignPublicationError(
            "existing publication campaign plan differs from deterministic preflight"
        )
    if names == partial:
        return False
    verify_completed_history_campaign_publication(publication_root, source_campaign_root)
    return True


def preflight_history_campaign_publication(
    source_campaign_root: Path,
    *,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    store_root: Path,
    snapshot: HostSnapshot,
    now_ms: int,
    software_identity: str,
) -> HistoryCampaignPublicationPlan:
    """Verify and plan every child canonical write without retaining aggregate Arrow data."""

    if SOFTWARE_IDENTITY_RE.fullmatch(software_identity) is None:
        raise HistoryCampaignPublicationError(
            "software identity must be git:<40-character-lowercase-commit-sha>"
        )
    try:
        registry = load_verified_instrument_registry(instrument_registry_path)
        capacity_path, _capacity, capacity_sha = load_verified_capacity_evidence(
            capacity_evidence_path
        )
    except (HistoryCampaignError, HistoryAcquisitionError) as error:
        raise HistoryCampaignPublicationError(str(error)) from error
    resolved_store = store_root.resolve()
    prepared: list[PreparedCampaignPublication] = []

    def preflight_verified_child(
        job_root: Path,
        kind: CampaignKind,
    ) -> CompletedHistoryJob | CompletedFundingJob:
        sequence = len(prepared)
        resolved = _preflight_child_publication(
            job_root,
            kind,
            sequence=sequence,
            store_root=resolved_store,
            instrument_registry_path=instrument_registry_path,
            capacity_evidence_path=capacity_path,
            snapshot=snapshot,
            now_ms=now_ms,
            software_identity=software_identity,
        )
        completed = (
            resolved.verified.completed
            if isinstance(resolved, ResolvedFundingPublication)
            else resolved.completed_history
        )
        source = _source_from_completed_child(
            completed,
            sequence=sequence,
            kind=kind,
            source_campaign_root=source_campaign_root.resolve(),
        )
        prepared.append(_prepare_child(source, resolved, store_root=resolved_store))
        return completed

    try:
        source_campaign = verify_completed_history_campaign(
            source_campaign_root,
            child_verifier=preflight_verified_child,
        )
    except (HistoryCampaignError, HistoryAcquisitionError) as error:
        raise HistoryCampaignPublicationError(str(error)) from error
    source_plan = _load_canonical_object(source_campaign.plan_path)
    if source_plan.get("instrument_evidence_sha256") != registry.artifact_sha256:
        raise HistoryCampaignPublicationError(
            "source campaign does not bind the supplied instrument registry"
        )
    if source_plan.get("capacity_evidence_sha256") != capacity_sha:
        raise HistoryCampaignPublicationError(
            "source campaign does not bind the supplied capacity evidence"
        )
    source_campaign_plan_sha = sha256_file(source_campaign.plan_path)
    source_jobs = _source_jobs(source_campaign)
    if len(prepared) != len(source_jobs):
        raise HistoryCampaignPublicationError("publication preflight did not verify every child")
    for child, source in zip(prepared, source_jobs, strict=True):
        if (
            child.sequence != source.sequence
            or child.kind != source.kind
            or child.job_id != source.job_id
            or child.source_job_root != source.job_root_relative
            or child.source_job_plan_sha256 != source.job_plan_sha256
            or child.source_job_manifest_sha256 != source.job_manifest_sha256
            or child.source_row_count != source.row_count
            or child.row_count > source.row_count
        ):
            raise HistoryCampaignPublicationError(
                "publication preflight child differs from source campaign inventory"
            )
    jobs = tuple(prepared)
    if not jobs:
        raise HistoryCampaignPublicationError("source campaign resolved to no publications")
    plan_payload = _campaign_plan_payload(
        source_campaign=source_campaign,
        source_campaign_plan_sha256=source_campaign_plan_sha,
        instrument_evidence_sha256=registry.artifact_sha256,
        capacity_evidence_sha256=capacity_sha,
        publisher_software_identity=software_identity,
        jobs=jobs,
    )
    plan_sha = canonical_sha256(plan_payload)
    namespace = resolved_store / ".publication-campaigns"
    if namespace.is_symlink():
        raise HistoryCampaignPublicationError("publication campaign namespace cannot be a symlink")
    campaign_id = cast(str, plan_payload["campaign_id"])
    publication_root = namespace / f"{campaign_id}--{plan_sha[:16]}"
    existing_complete = _existing_state(
        publication_root,
        expected_plan=plan_payload,
        source_campaign_root=source_campaign.campaign_root,
    )
    required_free = max(job.required_free_bytes for job in jobs)
    planned_memory = max(job.planned_peak_memory_bytes for job in jobs)
    if snapshot.volume_free_bytes < required_free:
        raise HistoryCampaignPublicationError(
            "insufficient free space for one sequential canonical writer and full reserve"
        )
    if planned_memory > snapshot.memory_available_bytes:
        raise HistoryCampaignPublicationError("insufficient available memory for canonical writer")
    if planned_memory * 100 > snapshot.memory_total_bytes * MAX_MEMORY_PERCENT:
        raise HistoryCampaignPublicationError("publication campaign exceeds the 70% memory gate")
    return HistoryCampaignPublicationPlan(
        source_campaign=source_campaign,
        source_campaign_plan_sha256=source_campaign_plan_sha,
        source_campaign_manifest_sha256=source_campaign.manifest_sha256,
        instrument_registry_path=instrument_registry_path.resolve(),
        instrument_evidence_sha256=registry.artifact_sha256,
        capacity_evidence_path=capacity_path,
        capacity_evidence_sha256=capacity_sha,
        store_root=resolved_store,
        publication_root=publication_root,
        plan_path=publication_root / "plan.json",
        plan_receipt_path=publication_root / "plan.receipt.json",
        manifest_path=publication_root / "manifest.json",
        completion_receipt_path=publication_root / "completion-receipt.json",
        publisher_software_identity=software_identity,
        jobs=jobs,
        plan_payload=plan_payload,
        plan_sha256=plan_sha,
        required_free_bytes=required_free,
        planned_peak_memory_bytes=planned_memory,
        existing_complete=existing_complete,
    )


def _publish_plan_if_new(plan: HistoryCampaignPublicationPlan) -> None:
    if plan.plan_path.exists():
        return
    _atomic_write_new(plan.plan_path, plan.plan_payload)
    _atomic_write_new(
        plan.plan_receipt_path,
        _receipt_payload(plan.plan_path.name, sha256_file(plan.plan_path)),
    )


def prepare_history_campaign_publication_plan(
    plan: HistoryCampaignPublicationPlan,
) -> HistoryCampaignPublicationPlan:
    """Persist only the fully semantic-preflighted aggregate plan and its receipt."""

    if plan.existing_complete:
        raise HistoryCampaignPublicationError(
            "completed publication does not need a prepared-plan checkpoint"
        )
    _assert_source_campaign_envelope_unchanged(plan)
    _publish_plan_if_new(plan)
    persisted, digest = _verify_receipt(plan.plan_path, plan.plan_receipt_path)
    if persisted != plan.plan_payload or digest != plan.plan_sha256:
        raise HistoryCampaignPublicationError("prepared publication plan does not verify")
    return plan


def _load_bound_source_campaign(
    source_campaign_root: Path,
    *,
    expected_plan_sha256: str,
    expected_manifest_sha256: str,
) -> CompletedHistoryCampaign:
    """Load the frozen aggregate envelope without re-reading every Landing page."""

    supplied = source_campaign_root.absolute()
    if supplied.is_symlink() or supplied.parent.is_symlink():
        raise HistoryCampaignPublicationError(
            "source campaign root and namespace cannot be symlinks"
        )
    root = supplied.resolve()
    if not root.is_dir():
        raise HistoryCampaignPublicationError("source campaign root is missing")
    if {path.name for path in root.iterdir()} != {
        "completion-receipt.json",
        "manifest.json",
        "plan.json",
        "plan.receipt.json",
    }:
        raise HistoryCampaignPublicationError("source campaign envelope allowlist changed")
    plan_path = root / "plan.json"
    manifest_path = root / "manifest.json"
    plan = _load_canonical_object(plan_path)
    manifest = _load_canonical_object(manifest_path)
    plan_sha = sha256_file(plan_path)
    manifest_sha = sha256_file(manifest_path)
    plan_receipt = _load_canonical_object(root / "plan.receipt.json")
    completion_receipt = _load_canonical_object(root / "completion-receipt.json")
    if (
        plan_sha != expected_plan_sha256
        or manifest_sha != expected_manifest_sha256
        or plan_receipt
        != {
            "artifact": "plan.json",
            "artifact_sha256": plan_sha,
            "contract": CAMPAIGN_RECEIPT_CONTRACT,
            "status": "complete",
        }
        or completion_receipt
        != {
            "artifact": "manifest.json",
            "artifact_sha256": manifest_sha,
            "contract": CAMPAIGN_RECEIPT_CONTRACT,
            "status": "complete",
        }
        or manifest.get("campaign_plan_sha256") != canonical_sha256(plan)
        or manifest.get("status") != "complete"
    ):
        raise HistoryCampaignPublicationError("prepared plan source campaign binding changed")
    job_count = _integer("source campaign job count", manifest.get("job_count"), minimum=1)
    if plan.get("job_count") != job_count:
        raise HistoryCampaignPublicationError("source campaign job count changed")
    return CompletedHistoryCampaign(
        campaign_root=root,
        plan_path=plan_path,
        manifest_path=manifest_path,
        receipt_path=root / "completion-receipt.json",
        manifest_sha256=manifest_sha,
        job_count=job_count,
        page_count=_integer("source campaign page count", manifest.get("page_count")),
        row_count=_integer("source campaign row count", manifest.get("row_count")),
        http_request_count=_integer(
            "source campaign HTTP request count",
            manifest.get("http_request_count"),
        ),
    )


def _prepared_child_from_payload(
    raw: object,
    source: SourceCampaignJob,
    *,
    store_root: Path,
) -> PreparedCampaignPublication:
    if not isinstance(raw, dict) or set(raw) not in (_PLAN_JOB_KEYS, _PLAN_JOB_ADMISSION_KEYS):
        raise HistoryCampaignPublicationError("prepared publication child fields differ from v1")
    expected_source = {
        "job_id": source.job_id,
        "kind": source.kind,
        "sequence": source.sequence,
        "source_job_manifest_sha256": source.job_manifest_sha256,
        "source_job_plan_sha256": source.job_plan_sha256,
        "source_job_root": source.job_root_relative,
    }
    if any(raw.get(name) != value for name, value in expected_source.items()):
        raise HistoryCampaignPublicationError("prepared publication source lineage differs")
    canonical_admission = _canonical_admission(
        raw.get("canonical_admission"),
        source_row_count=source.row_count,
    )
    if canonical_admission is not None and source.kind == "funding":
        raise HistoryCampaignPublicationError(
            "funding publication cannot carry candle canonical admission"
        )
    row_count = (
        cast(int, canonical_admission["admitted_row_count"])
        if canonical_admission is not None
        else source.row_count
    )
    if canonical_admission is not None and raw.get("source_row_count") != source.row_count:
        raise HistoryCampaignPublicationError("prepared canonical admission source count changed")
    dataset_id = _text("prepared canonical dataset id", raw.get("dataset_id"))
    dataset_type = _dataset_type(source.kind)
    dataset_root = (PurePosixPath("datasets") / dataset_id).as_posix()
    if (
        dataset_id != _dataset_id(source.kind, source.job_manifest_sha256)
        or raw.get("dataset_type") != dataset_type
        or raw.get("dataset_root") != dataset_root
        or raw.get("row_count") != row_count
    ):
        raise HistoryCampaignPublicationError("prepared canonical dataset identity changed")
    dataset_path = store_root.joinpath(*PurePosixPath(dataset_root).parts)
    if dataset_path.is_symlink() or dataset_path.parent.is_symlink():
        raise HistoryCampaignPublicationError(
            "prepared canonical dataset and namespace cannot be symlinks"
        )
    existing_commit = dataset_path.exists()
    if existing_commit and (
        not dataset_path.is_dir() or not (dataset_path / "completion-receipt.json").is_file()
    ):
        raise HistoryCampaignPublicationError("existing canonical dataset has no commit receipt")
    return PreparedCampaignPublication(
        sequence=source.sequence,
        kind=source.kind,
        job_id=source.job_id,
        source_job_root=source.job_root_relative,
        source_job_plan_sha256=source.job_plan_sha256,
        source_job_manifest_sha256=source.job_manifest_sha256,
        dataset_id=dataset_id,
        dataset_type=dataset_type,
        dataset_root=dataset_root,
        input_table_sha256=_sha256(
            "prepared canonical input table hash",
            raw.get("input_table_sha256"),
        ),
        publication_request_sha256=_sha256(
            "prepared publication request hash",
            raw.get("publication_request_sha256"),
        ),
        row_count=row_count,
        source_row_count=source.row_count,
        canonical_admission=canonical_admission,
        required_free_bytes=_integer(
            "prepared required free bytes",
            raw.get("required_free_bytes"),
            minimum=1,
        ),
        planned_peak_memory_bytes=_integer(
            "prepared peak memory bytes",
            raw.get("planned_peak_memory_bytes"),
            minimum=1,
        ),
        existing_commit=existing_commit,
    )


def _assert_prepared_plan_resources(
    store_root: Path,
    snapshot: HostSnapshot,
    *,
    now_ms: int,
    required_free_bytes: int,
    planned_peak_memory_bytes: int,
) -> None:
    age = now_ms - snapshot.observed_at_ms
    if age < 0 or age > MAX_PREPARED_PLAN_SNAPSHOT_AGE_MS:
        raise HistoryCampaignPublicationError("host snapshot must be fresh and not future-dated")
    if not store_root.is_relative_to(snapshot.volume_root.resolve()):
        raise HistoryCampaignPublicationError("market store is not on the observed storage volume")
    current = store_root
    while not current.exists() and current != current.parent:
        current = current.parent
    if not current.is_dir() or current.is_symlink():
        raise HistoryCampaignPublicationError(
            "market-store ancestor must be an existing non-symlink directory"
        )
    if snapshot.volume_free_bytes < required_free_bytes:
        raise HistoryCampaignPublicationError(
            "insufficient free space for one sequential canonical writer and full reserve"
        )
    if planned_peak_memory_bytes > snapshot.memory_available_bytes:
        raise HistoryCampaignPublicationError("insufficient available memory for canonical writer")
    if planned_peak_memory_bytes * 100 > snapshot.memory_total_bytes * MAX_MEMORY_PERCENT:
        raise HistoryCampaignPublicationError("publication campaign exceeds the 70% memory gate")


def load_prepared_history_campaign_publication(
    source_campaign_root: Path,
    publication_root: Path,
    *,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    store_root: Path,
    snapshot: HostSnapshot,
    now_ms: int,
    software_identity: str,
) -> HistoryCampaignPublicationPlan:
    """Load a receipt-bound semantic plan without repeating whole-campaign row decoding."""

    if SOFTWARE_IDENTITY_RE.fullmatch(software_identity) is None:
        raise HistoryCampaignPublicationError(
            "software identity must be git:<40-character-lowercase-commit-sha>"
        )
    supplied_store = store_root.absolute()
    if supplied_store.is_symlink():
        raise HistoryCampaignPublicationError("market store cannot be a symlink")
    resolved_store = supplied_store.resolve()
    namespace = resolved_store / ".publication-campaigns"
    supplied_root = publication_root.absolute()
    if supplied_root.is_symlink() or supplied_root.parent.is_symlink():
        raise HistoryCampaignPublicationError("publication root and namespace cannot be symlinks")
    root = supplied_root.resolve()
    if root.parent != namespace or not root.is_dir():
        raise HistoryCampaignPublicationError(
            "prepared publication root must be an existing direct campaign namespace child"
        )
    names = {path.name for path in root.iterdir()}
    partial = {"plan.json", "plan.receipt.json"}
    complete = partial | {"manifest.json", "completion-receipt.json"}
    if names not in (partial, complete):
        raise HistoryCampaignPublicationError(
            "prepared publication root contains incomplete or orphan artifacts"
        )
    plan_payload, plan_sha = _verify_receipt(root / "plan.json", root / "plan.receipt.json")
    if (
        set(plan_payload) != _PLAN_KEYS
        or plan_payload.get("contract") != CAMPAIGN_PUBLICATION_PLAN_CONTRACT
        or plan_payload.get("publication_policy") != _PUBLICATION_POLICY
        or plan_payload.get("publisher_software_identity") != software_identity
        or plan_sha != canonical_sha256(plan_payload)
    ):
        raise HistoryCampaignPublicationError("prepared publication plan contract does not verify")
    campaign_id = _text("prepared source campaign id", plan_payload.get("campaign_id"))
    if root.name != f"{campaign_id}--{plan_sha[:16]}":
        raise HistoryCampaignPublicationError("prepared publication root is not plan-derived")
    source_plan_sha = _sha256(
        "prepared source campaign plan hash",
        plan_payload.get("source_campaign_plan_sha256"),
    )
    source_manifest_sha = _sha256(
        "prepared source campaign manifest hash",
        plan_payload.get("source_campaign_manifest_sha256"),
    )
    source_campaign = _load_bound_source_campaign(
        source_campaign_root,
        expected_plan_sha256=source_plan_sha,
        expected_manifest_sha256=source_manifest_sha,
    )
    source_plan = _load_canonical_object(source_campaign.plan_path)
    try:
        registry = load_verified_instrument_registry(instrument_registry_path)
        capacity_path, _capacity, capacity_sha = load_verified_capacity_evidence(
            capacity_evidence_path
        )
    except (HistoryCampaignError, HistoryAcquisitionError) as error:
        raise HistoryCampaignPublicationError(str(error)) from error
    if (
        source_plan.get("campaign_id") != campaign_id
        or source_plan.get("instrument_evidence_sha256") != registry.artifact_sha256
        or source_plan.get("capacity_evidence_sha256") != capacity_sha
        or plan_payload.get("instrument_evidence_sha256") != registry.artifact_sha256
        or plan_payload.get("capacity_evidence_sha256") != capacity_sha
    ):
        raise HistoryCampaignPublicationError("prepared publication evidence binding changed")
    source_jobs = _source_jobs(source_campaign)
    raw_jobs = plan_payload.get("jobs")
    if (
        not isinstance(raw_jobs, list)
        or not raw_jobs
        or len(raw_jobs) > MAX_CAMPAIGN_PUBLICATIONS
        or len(raw_jobs) != len(source_jobs)
        or plan_payload.get("dataset_count") != len(raw_jobs)
    ):
        raise HistoryCampaignPublicationError("prepared publication inventory does not verify")
    jobs = tuple(
        _prepared_child_from_payload(raw, source, store_root=resolved_store)
        for raw, source in zip(raw_jobs, source_jobs, strict=True)
    )
    if len({job.dataset_id for job in jobs}) != len(jobs):
        raise HistoryCampaignPublicationError("prepared publication dataset ids are not unique")
    if plan_payload.get("row_count") != sum(job.row_count for job in jobs):
        raise HistoryCampaignPublicationError("prepared publication row total does not verify")
    required_free = max(job.required_free_bytes for job in jobs)
    planned_memory = max(job.planned_peak_memory_bytes for job in jobs)
    _assert_prepared_plan_resources(
        resolved_store,
        snapshot,
        now_ms=now_ms,
        required_free_bytes=required_free,
        planned_peak_memory_bytes=planned_memory,
    )
    existing_complete = names == complete
    if existing_complete:
        manifest, _manifest_sha = _verify_receipt(
            root / "manifest.json",
            root / "completion-receipt.json",
        )
        if (
            manifest.get("contract") != CAMPAIGN_PUBLICATION_MANIFEST_CONTRACT
            or manifest.get("status") != "complete"
            or manifest.get("publication_plan_sha256") != plan_sha
        ):
            raise HistoryCampaignPublicationError(
                "completed prepared publication does not bind its plan"
            )
    return HistoryCampaignPublicationPlan(
        source_campaign=source_campaign,
        source_campaign_plan_sha256=source_plan_sha,
        source_campaign_manifest_sha256=source_manifest_sha,
        instrument_registry_path=instrument_registry_path.resolve(),
        instrument_evidence_sha256=registry.artifact_sha256,
        capacity_evidence_path=capacity_path,
        capacity_evidence_sha256=capacity_sha,
        store_root=resolved_store,
        publication_root=root,
        plan_path=root / "plan.json",
        plan_receipt_path=root / "plan.receipt.json",
        manifest_path=root / "manifest.json",
        completion_receipt_path=root / "completion-receipt.json",
        publisher_software_identity=software_identity,
        jobs=jobs,
        plan_payload=plan_payload,
        plan_sha256=plan_sha,
        required_free_bytes=required_free,
        planned_peak_memory_bytes=planned_memory,
        existing_complete=existing_complete,
    )


def _assert_current_child(
    expected: PreparedCampaignPublication,
    current: PreparedCampaignPublication,
) -> None:
    if expected.plan_payload() != current.plan_payload():
        raise HistoryCampaignPublicationError(
            f"publication child {expected.sequence} changed after campaign preflight"
        )


def _published_entry(
    child: PreparedCampaignPublication,
    published: PublishedDataset,
) -> dict[str, object]:
    if (
        published.manifest.dataset_id != child.dataset_id
        or published.manifest.dataset_type.value != child.dataset_type
        or published.manifest.row_count != child.row_count
    ):
        raise HistoryCampaignPublicationError("published child differs from campaign plan")
    payload: dict[str, object] = {
        "dataset_id": child.dataset_id,
        "dataset_root": child.dataset_root,
        "dataset_type": child.dataset_type,
        "file_count": len(published.manifest.files),
        "kind": child.kind,
        "manifest_sha256": published.receipt.manifest_sha256,
        "parquet_bytes": sum(item.size_bytes for item in published.manifest.files),
        "publication_request_sha256": child.publication_request_sha256,
        "row_count": published.manifest.row_count,
        "sequence": child.sequence,
        "source_job_manifest_sha256": child.source_job_manifest_sha256,
    }
    if child.canonical_admission is not None:
        payload["canonical_admission"] = child.canonical_admission
        payload["source_row_count"] = child.source_row_count
    return payload


def _assert_source_campaign_envelope_unchanged(
    plan: HistoryCampaignPublicationPlan,
) -> None:
    root = plan.source_campaign.campaign_root
    if root.is_symlink() or root.parent.is_symlink() or not root.is_dir():
        raise HistoryCampaignPublicationError("source campaign root became unsafe")
    expected_names = {
        "completion-receipt.json",
        "manifest.json",
        "plan.json",
        "plan.receipt.json",
    }
    if {path.name for path in root.iterdir()} != expected_names:
        raise HistoryCampaignPublicationError("source campaign envelope allowlist changed")
    source_plan = _load_canonical_object(plan.source_campaign.plan_path)
    source_manifest = _load_canonical_object(plan.source_campaign.manifest_path)
    plan_sha = sha256_file(plan.source_campaign.plan_path)
    manifest_sha = sha256_file(plan.source_campaign.manifest_path)
    plan_receipt = _load_canonical_object(root / "plan.receipt.json")
    completion_receipt = _load_canonical_object(root / "completion-receipt.json")
    if (
        plan_sha != plan.source_campaign_plan_sha256
        or manifest_sha != plan.source_campaign_manifest_sha256
        or plan_receipt
        != {
            "artifact": "plan.json",
            "artifact_sha256": plan_sha,
            "contract": CAMPAIGN_RECEIPT_CONTRACT,
            "status": "complete",
        }
        or completion_receipt
        != {
            "artifact": "manifest.json",
            "artifact_sha256": manifest_sha,
            "contract": CAMPAIGN_RECEIPT_CONTRACT,
            "status": "complete",
        }
        or source_manifest.get("campaign_plan_sha256") != canonical_sha256(source_plan)
    ):
        raise HistoryCampaignPublicationError("source campaign envelope changed after preflight")


def _verify_existing_child_against_plan(
    child: PreparedCampaignPublication,
    source: SourceCampaignJob,
    plan: HistoryCampaignPublicationPlan,
) -> PublishedDataset:
    dataset_root = plan.store_root.joinpath(*PurePosixPath(child.dataset_root).parts)
    try:
        published = (
            verify_committed_funding_dataset(dataset_root)
            if child.kind == "funding"
            else verify_committed_candle_dataset(dataset_root)
        )
    except PublicationError as error:
        raise HistoryCampaignPublicationError(
            f"existing canonical child {child.sequence} does not verify: {error}"
        ) from error
    expected_source_evidence = _expected_source_evidence(
        source,
        plan.instrument_evidence_sha256,
        child.canonical_admission,
    )
    expected_build_config = _expected_build_config(
        child.kind,
        dataset_id=child.dataset_id,
        source_manifest_sha256=child.source_job_manifest_sha256,
        software_identity=plan.publisher_software_identity,
        canonical_admission=child.canonical_admission,
    )
    audit = _load_canonical_object(published.audit_path)
    if (
        published.manifest.dataset_id != child.dataset_id
        or published.manifest.dataset_type.value != child.dataset_type
        or published.manifest.row_count != child.row_count
        or published.manifest.parent_dataset_ids
        or published.manifest.source_evidence_sha256 != expected_source_evidence
        or published.manifest.build_config_sha256 != expected_build_config
        or published.manifest.software_identity != plan.publisher_software_identity
        or audit.get("request_sha256") != child.publication_request_sha256
        or audit.get("input_table_sha256") != child.input_table_sha256
        or audit.get("coverage_evidence_sha256") != child.source_job_manifest_sha256
        or audit.get("capacity_evidence_sha256") != plan.capacity_evidence_sha256
    ):
        raise HistoryCampaignPublicationError(
            f"existing canonical child {child.sequence} differs from prepared plan"
        )
    return published


def execute_history_campaign_publication(
    plan: HistoryCampaignPublicationPlan,
    *,
    snapshot_provider: Callable[[], HostSnapshot],
    now_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    progress: Callable[[PreparedCampaignPublication, PublishedDataset], None] | None = None,
) -> CompletedHistoryCampaignPublication:
    """Publish child datasets sequentially and write the aggregate completion receipt last."""

    if plan.existing_complete:
        return verify_completed_history_campaign_publication(
            plan.publication_root,
            plan.source_campaign.campaign_root,
        )
    _assert_source_campaign_envelope_unchanged(plan)
    source_campaign = plan.source_campaign
    source_jobs = _source_jobs(source_campaign)
    if len(source_jobs) != len(plan.jobs):
        raise HistoryCampaignPublicationError("source campaign job count changed after preflight")
    _publish_plan_if_new(plan)
    entries: list[dict[str, object]] = []
    for expected, source in zip(plan.jobs, source_jobs, strict=True):
        if expected.existing_commit:
            published = _verify_existing_child_against_plan(expected, source, plan)
            entries.append(_published_entry(expected, published))
            if progress is not None:
                progress(expected, published)
            continue
        current_snapshot = snapshot_provider()
        current_time = now_ms()
        current, resolved = _resolve_child(
            source,
            store_root=plan.store_root,
            instrument_registry_path=plan.instrument_registry_path,
            capacity_evidence_path=plan.capacity_evidence_path,
            snapshot=current_snapshot,
            now_ms=current_time,
            software_identity=plan.publisher_software_identity,
        )
        _assert_current_child(expected, current)
        if current.existing_commit:
            published = (
                verify_committed_funding_dataset(resolved.plan.paths.dataset_root)
                if current.kind == "funding"
                else verify_committed_candle_dataset(resolved.plan.paths.dataset_root)
            )
        elif current.kind == "funding":
            if not isinstance(resolved, ResolvedFundingPublication):
                raise HistoryCampaignPublicationError("funding child resolved to candle writer")
            published = publish_preflighted_funding(resolved, snapshot_provider, now_ms)
        else:
            if not isinstance(resolved, ResolvedHistoryPublication):
                raise HistoryCampaignPublicationError("candle child resolved to funding writer")
            published = publish_preflighted_history(resolved, snapshot_provider, now_ms)
        entries.append(_published_entry(current, published))
        if progress is not None:
            progress(current, published)
    manifest: dict[str, object] = {
        "campaign_id": plan.plan_payload["campaign_id"],
        "capacity_evidence_sha256": plan.capacity_evidence_sha256,
        "completed_at_ms": now_ms(),
        "contract": CAMPAIGN_PUBLICATION_MANIFEST_CONTRACT,
        "dataset_count": len(entries),
        "datasets": entries,
        "file_count": sum(cast(int, item["file_count"]) for item in entries),
        "instrument_evidence_sha256": plan.instrument_evidence_sha256,
        "parquet_bytes": sum(cast(int, item["parquet_bytes"]) for item in entries),
        "publication_plan_sha256": plan.plan_sha256,
        "publisher_software_identity": plan.publisher_software_identity,
        "row_count": sum(cast(int, item["row_count"]) for item in entries),
        "source_campaign_manifest_sha256": plan.source_campaign_manifest_sha256,
        "source_campaign_plan_sha256": plan.source_campaign_plan_sha256,
        "status": "complete",
    }
    _atomic_write_new(plan.manifest_path, manifest)
    _atomic_write_new(
        plan.completion_receipt_path,
        _receipt_payload(plan.manifest_path.name, sha256_file(plan.manifest_path)),
    )
    return verify_completed_history_campaign_publication(
        plan.publication_root,
        plan.source_campaign.campaign_root,
    )


def _expected_build_config(
    kind: CampaignKind,
    *,
    dataset_id: str,
    source_manifest_sha256: str,
    software_identity: str,
    canonical_admission: dict[str, object] | None = None,
) -> str:
    if kind == "funding":
        return canonical_sha256(
            {
                "canonical_layout": FUNDING_CANONICAL_LAYOUT_ID,
                "contract": FUNDING_HISTORY_PUBLICATION_CONTRACT,
                "dataset_id": dataset_id,
                "funding_manifest_sha256": source_manifest_sha256,
                "semantic_version": "1.0.0",
                "software_identity": software_identity,
            }
        )
    return history_publication_build_config_sha256(
        dataset_id=dataset_id,
        history_manifest_sha256=source_manifest_sha256,
        software_identity=software_identity,
        canonical_admission=canonical_admission,
    )


def _expected_source_evidence(
    source: SourceCampaignJob,
    instrument_evidence_sha256: str,
    canonical_admission: dict[str, object] | None = None,
) -> tuple[str, ...]:
    values = [source.job_manifest_sha256, instrument_evidence_sha256]
    if canonical_admission is not None:
        values.append(
            _text(
                "canonical admission exclusion hash",
                canonical_admission.get("excluded_rows_sha256"),
            )
        )
    if source.kind == "funding":
        source_manifest = _load_canonical_object(source.job_root / "manifest.json")
        values.append(
            _text(
                "funding boundary evidence hash",
                source_manifest.get("boundary_evidence_sha256"),
            )
        )
    return tuple(dict.fromkeys(values))


def verify_completed_history_campaign_publication(
    publication_root: Path,
    source_campaign_root: Path,
) -> CompletedHistoryCampaignPublication:
    """Verify aggregate receipts, source lineage, and every committed canonical dataset."""

    supplied = publication_root.absolute()
    if supplied.is_symlink() or supplied.parent.is_symlink() or supplied.parent.parent.is_symlink():
        raise HistoryCampaignPublicationError("publication root and namespace cannot be symlinks")
    root = supplied.resolve()
    if not root.is_dir():
        raise HistoryCampaignPublicationError("publication campaign root is missing")
    expected_names = {
        "plan.json",
        "plan.receipt.json",
        "manifest.json",
        "completion-receipt.json",
    }
    if {path.name for path in root.iterdir()} != expected_names:
        raise HistoryCampaignPublicationError("publication campaign allowlist does not match v1")
    plan, plan_artifact_sha = _verify_receipt(root / "plan.json", root / "plan.receipt.json")
    manifest, manifest_sha = _verify_receipt(
        root / "manifest.json", root / "completion-receipt.json"
    )
    expected_manifest_keys = {
        "campaign_id",
        "capacity_evidence_sha256",
        "completed_at_ms",
        "contract",
        "dataset_count",
        "datasets",
        "file_count",
        "instrument_evidence_sha256",
        "parquet_bytes",
        "publication_plan_sha256",
        "publisher_software_identity",
        "row_count",
        "source_campaign_manifest_sha256",
        "source_campaign_plan_sha256",
        "status",
    }
    if set(plan) != _PLAN_KEYS or set(manifest) != expected_manifest_keys:
        raise HistoryCampaignPublicationError("publication plan or manifest fields differ from v1")
    if plan.get("contract") != CAMPAIGN_PUBLICATION_PLAN_CONTRACT:
        raise HistoryCampaignPublicationError("unsupported publication campaign plan")
    if (
        manifest.get("contract") != CAMPAIGN_PUBLICATION_MANIFEST_CONTRACT
        or manifest.get("status") != "complete"
    ):
        raise HistoryCampaignPublicationError("unsupported or incomplete publication manifest")
    if plan_artifact_sha != canonical_sha256(plan):
        raise HistoryCampaignPublicationError("publication plan canonical hash does not verify")
    if manifest.get("publication_plan_sha256") != canonical_sha256(plan):
        raise HistoryCampaignPublicationError("publication manifest does not bind the exact plan")
    if plan.get("publication_policy") != _PUBLICATION_POLICY:
        raise HistoryCampaignPublicationError("publication policy differs from sequential v1")
    software_identity = _text(
        "publisher software identity", plan.get("publisher_software_identity")
    )
    if SOFTWARE_IDENTITY_RE.fullmatch(software_identity) is None:
        raise HistoryCampaignPublicationError("publisher software identity is mutable or invalid")
    source_campaign = verify_completed_history_campaign(
        source_campaign_root,
        child_verifier=_verify_source_child_integrity,
    )
    source_plan_sha = sha256_file(source_campaign.plan_path)
    if (
        plan.get("source_campaign_manifest_sha256") != source_campaign.manifest_sha256
        or plan.get("source_campaign_plan_sha256") != source_plan_sha
    ):
        raise HistoryCampaignPublicationError("publication plan does not bind source campaign")
    source_plan = _load_canonical_object(source_campaign.plan_path)
    for field in ("campaign_id", "instrument_evidence_sha256", "capacity_evidence_sha256"):
        if plan.get(field) != source_plan.get(field):
            raise HistoryCampaignPublicationError(f"publication plan changed source {field}")
    source_jobs = _source_jobs(source_campaign)
    raw_jobs = plan.get("jobs")
    raw_datasets = manifest.get("datasets")
    if not isinstance(raw_jobs, list) or not isinstance(raw_datasets, list):
        raise HistoryCampaignPublicationError("publication jobs/datasets must be arrays")
    if not raw_jobs or len(raw_jobs) > MAX_CAMPAIGN_PUBLICATIONS:
        raise HistoryCampaignPublicationError("publication job inventory is empty or unbounded")
    if len(raw_jobs) != len(raw_datasets) or len(raw_jobs) != len(source_jobs):
        raise HistoryCampaignPublicationError("publication inventories differ")
    if plan.get("dataset_count") != len(raw_jobs) or manifest.get("dataset_count") != len(
        raw_datasets
    ):
        raise HistoryCampaignPublicationError("publication dataset count differs from inventory")
    store_root = root.parent.parent
    seen_ids: set[str] = set()
    total_rows = 0
    total_files = 0
    total_bytes = 0
    published_datasets: list[PublishedDataset] = []
    for sequence, (raw_job, raw_dataset, source) in enumerate(
        zip(raw_jobs, raw_datasets, source_jobs, strict=True)
    ):
        if not isinstance(raw_job, dict) or not isinstance(raw_dataset, dict):
            raise HistoryCampaignPublicationError("publication child must be an object")
        job_fields = set(raw_job)
        dataset_fields = set(raw_dataset)
        has_admission = job_fields == _PLAN_JOB_ADMISSION_KEYS
        if (
            job_fields not in (_PLAN_JOB_KEYS, _PLAN_JOB_ADMISSION_KEYS)
            or dataset_fields
            not in (
                _MANIFEST_DATASET_KEYS,
                _MANIFEST_DATASET_ADMISSION_KEYS,
            )
            or has_admission != (dataset_fields == _MANIFEST_DATASET_ADMISSION_KEYS)
        ):
            raise HistoryCampaignPublicationError("publication child fields differ from v1")
        if raw_job.get("sequence") != sequence or raw_dataset.get("sequence") != sequence:
            raise HistoryCampaignPublicationError("publication sequences are not contiguous")
        expected_source = {
            "job_id": source.job_id,
            "kind": source.kind,
            "source_job_manifest_sha256": source.job_manifest_sha256,
            "source_job_plan_sha256": source.job_plan_sha256,
            "source_job_root": source.job_root_relative,
        }
        if any(raw_job.get(name) != value for name, value in expected_source.items()):
            raise HistoryCampaignPublicationError("publication child source lineage differs")
        dataset_id = _text("canonical dataset id", raw_job.get("dataset_id"))
        if dataset_id != _dataset_id(source.kind, source.job_manifest_sha256):
            raise HistoryCampaignPublicationError("publication dataset id is not source-derived")
        if dataset_id in seen_ids:
            raise HistoryCampaignPublicationError("publication dataset ids are not unique")
        seen_ids.add(dataset_id)
        dataset_type = _dataset_type(source.kind)
        expected_dataset_root = (PurePosixPath("datasets") / dataset_id).as_posix()
        canonical_admission = _canonical_admission(
            raw_job.get("canonical_admission"),
            source_row_count=source.row_count,
        )
        if canonical_admission is not None and source.kind == "funding":
            raise HistoryCampaignPublicationError(
                "funding publication cannot carry candle canonical admission"
            )
        expected_row_count = (
            cast(int, canonical_admission["admitted_row_count"])
            if canonical_admission is not None
            else source.row_count
        )
        if (
            raw_job.get("dataset_type") != dataset_type
            or raw_job.get("dataset_root") != expected_dataset_root
            or raw_job.get("row_count") != expected_row_count
            or (
                canonical_admission is not None
                and raw_job.get("source_row_count") != source.row_count
            )
        ):
            raise HistoryCampaignPublicationError(
                "publication dataset identity differs from source"
            )
        for field in (
            "dataset_id",
            "dataset_root",
            "dataset_type",
            "kind",
            "publication_request_sha256",
            "row_count",
            "source_job_manifest_sha256",
            *(
                ("canonical_admission", "source_row_count")
                if canonical_admission is not None
                else ()
            ),
        ):
            if raw_dataset.get(field) != raw_job.get(field):
                raise HistoryCampaignPublicationError(
                    f"publication manifest child changed planned {field}"
                )
        dataset_root = store_root.joinpath(*PurePosixPath(expected_dataset_root).parts)
        try:
            published = (
                verify_committed_funding_dataset(dataset_root)
                if source.kind == "funding"
                else verify_committed_candle_dataset(dataset_root)
            )
        except PublicationError as error:
            raise HistoryCampaignPublicationError(
                f"canonical dataset {sequence} does not verify: {error}"
            ) from error
        expected_source_evidence = _expected_source_evidence(
            source,
            cast(str, plan["instrument_evidence_sha256"]),
            canonical_admission,
        )
        expected_build_config = _expected_build_config(
            source.kind,
            dataset_id=dataset_id,
            source_manifest_sha256=source.job_manifest_sha256,
            software_identity=software_identity,
            canonical_admission=canonical_admission,
        )
        if (
            published.manifest.dataset_type.value != dataset_type
            or published.manifest.row_count != expected_row_count
            or published.manifest.parent_dataset_ids
            or published.manifest.source_evidence_sha256 != expected_source_evidence
            or published.manifest.build_config_sha256 != expected_build_config
            or published.manifest.software_identity != software_identity
            or published.receipt.manifest_sha256 != raw_dataset.get("manifest_sha256")
        ):
            raise HistoryCampaignPublicationError("canonical manifest differs from campaign plan")
        audit = _load_canonical_object(published.audit_path)
        if (
            audit.get("request_sha256") != raw_job.get("publication_request_sha256")
            or audit.get("input_table_sha256") != raw_job.get("input_table_sha256")
            or audit.get("coverage_evidence_sha256") != source.job_manifest_sha256
            or audit.get("capacity_evidence_sha256") != plan.get("capacity_evidence_sha256")
        ):
            raise HistoryCampaignPublicationError("canonical audit bindings differ from plan")
        file_count = len(published.manifest.files)
        parquet_bytes = sum(item.size_bytes for item in published.manifest.files)
        if (
            raw_dataset.get("file_count") != file_count
            or raw_dataset.get("parquet_bytes") != parquet_bytes
        ):
            raise HistoryCampaignPublicationError("canonical file totals differ from manifest")
        published_datasets.append(published)
        _integer("required free bytes", raw_job.get("required_free_bytes"), minimum=1)
        _integer("planned peak memory bytes", raw_job.get("planned_peak_memory_bytes"), minimum=1)
        total_rows += expected_row_count
        total_files += file_count
        total_bytes += parquet_bytes
    totals = {
        "dataset_count": len(source_jobs),
        "file_count": total_files,
        "parquet_bytes": total_bytes,
        "row_count": total_rows,
    }
    if any(manifest.get(name) != value for name, value in totals.items()):
        raise HistoryCampaignPublicationError("publication manifest totals do not verify")
    if plan.get("row_count") != total_rows:
        raise HistoryCampaignPublicationError("publication plan row total does not verify")
    for field in (
        "campaign_id",
        "capacity_evidence_sha256",
        "instrument_evidence_sha256",
        "publisher_software_identity",
        "source_campaign_manifest_sha256",
        "source_campaign_plan_sha256",
    ):
        if manifest.get(field) != plan.get(field):
            raise HistoryCampaignPublicationError(f"publication manifest changed {field}")
    _integer("publication completion time", manifest.get("completed_at_ms"))
    return CompletedHistoryCampaignPublication(
        publication_root=root,
        plan_path=root / "plan.json",
        manifest_path=root / "manifest.json",
        receipt_path=root / "completion-receipt.json",
        manifest_sha256=manifest_sha,
        dataset_count=len(source_jobs),
        row_count=total_rows,
        file_count=total_files,
        parquet_bytes=total_bytes,
        published_datasets=tuple(published_datasets),
    )
