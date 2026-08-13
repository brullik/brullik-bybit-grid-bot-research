"""Deterministic, receipt-resumable orchestration for public history jobs."""

from __future__ import annotations

import calendar
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
from grid_contracts.market import MINUTE_MS, InstrumentSnapshot
from grid_market_store import BUCKET_COUNT, MAX_MEMORY_PERCENT, HostSnapshot

from grid_data.funding_acquisition import (
    MAX_PAGE_ARTIFACT_BYTES as FUNDING_MAX_PAGE_ARTIFACT_BYTES,
)
from grid_data.funding_acquisition import (
    STAGING_METADATA_BYTES as FUNDING_STAGING_METADATA_BYTES,
)
from grid_data.funding_acquisition import (
    CompletedFundingJob,
    FundingClient,
    FundingJobPlan,
    execute_funding_job,
    preflight_funding_job,
    verify_completed_funding_job,
)
from grid_data.funding_request import (
    FUNDING_REQUEST_CONTRACT,
    resolve_funding_request_payload,
)
from grid_data.funding_source_boundary import (
    FundingSourceBoundaryError,
    verify_completed_funding_source_boundary,
)
from grid_data.history_acquisition import (
    MAX_PAGE_ARTIFACT_BYTES as HISTORY_MAX_PAGE_ARTIFACT_BYTES,
)
from grid_data.history_acquisition import (
    STAGING_METADATA_BYTES as HISTORY_STAGING_METADATA_BYTES,
)
from grid_data.history_acquisition import (
    CompletedHistoryJob,
    HistoryJobPlan,
    KlineClient,
    execute_history_job,
    preflight_history_job,
    verify_completed_history_job,
)
from grid_data.history_request import (
    HISTORY_REQUEST_CONTRACT,
    active_and_building_bytes_from_capacity,
    load_verified_request_evidence,
    resolve_history_request_payload,
)

CAMPAIGN_REQUEST_CONTRACT: Final = "grid.public-history-campaign-request/v1"
CAMPAIGN_PLAN_CONTRACT: Final = "grid.public-history-campaign-plan/v1"
CAMPAIGN_MANIFEST_CONTRACT: Final = "grid.public-history-campaign-manifest/v1"
CAMPAIGN_RECEIPT_CONTRACT: Final = "grid.history-campaign-receipt/v1"
LIFECYCLE_POLICY: Final = "registry-lifecycle-intersection-v1"
MAX_CAMPAIGN_MONTHS: Final = 120
MAX_CAMPAIGN_JOBS: Final = MAX_CAMPAIGN_MONTHS * BUCKET_COUNT * 3
MAX_CAMPAIGN_SYMBOLS: Final = 700
CAMPAIGN_ID_RE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{2,79}$")
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
CampaignKind = Literal["trade", "mark", "funding"]
CampaignChildVerifier = Callable[
    [Path, CampaignKind],
    CompletedHistoryJob | CompletedFundingJob,
]
_KIND_ORDER: Final = {"trade": 0, "mark": 1, "funding": 2}
_REQUEST_KEYS: Final = frozenset(
    {
        "contract",
        "campaign_id",
        "kinds",
        "symbols",
        "start_ms",
        "end_ms",
        "lifecycle_policy",
        "history_page_limit",
        "funding_page_limit",
        "funding_page_span_minutes",
        "workers",
        "target_rps",
        "max_attempts",
    }
)


class HistoryCampaignError(RuntimeError):
    """Raised when a campaign cannot be planned, resumed, or verified safely."""


@dataclass(frozen=True, slots=True)
class PreparedCampaignJob:
    sequence: int
    kind: CampaignKind
    year: int
    month: int
    bucket: int
    request_payload: dict[str, object]
    plan: HistoryJobPlan | FundingJobPlan

    @property
    def job_id(self) -> str:
        return self.plan.spec.job_id

    @property
    def planned_page_count(self) -> int:
        return len(self.plan.tasks)

    @property
    def pending_page_count(self) -> int:
        return len(self.plan.pending_tasks)

    @property
    def existing_complete(self) -> bool:
        return self.plan.existing_complete


@dataclass(frozen=True, slots=True)
class HistoryCampaignPlan:
    request_path: Path
    request_payload: dict[str, object]
    request_sha256: str
    instrument_evidence_sha256: str
    capacity_evidence_sha256: str
    staging_root: Path
    campaign_root: Path
    plan_path: Path
    plan_receipt_path: Path
    manifest_path: Path
    completion_receipt_path: Path
    jobs: tuple[PreparedCampaignJob, ...]
    plan_payload: dict[str, object]
    plan_sha256: str
    required_free_bytes: int
    planned_peak_memory_bytes: int
    existing_complete: bool


@dataclass(frozen=True, slots=True)
class CompletedHistoryCampaign:
    campaign_root: Path
    plan_path: Path
    manifest_path: Path
    receipt_path: Path
    manifest_sha256: str
    job_count: int
    page_count: int
    row_count: int
    http_request_count: int


def _load_request(path: Path) -> tuple[Path, dict[str, object]]:
    resolved = path.resolve()
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryCampaignError("campaign request is not a readable JSON object") from error
    if not isinstance(raw, dict):
        raise HistoryCampaignError("campaign request must contain a JSON object")
    return resolved, cast(dict[str, object], raw)


def _integer(name: str, value: object, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise HistoryCampaignError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise HistoryCampaignError(f"{name} must be non-empty trimmed text")
    return value


def _kinds(value: object) -> tuple[CampaignKind, ...]:
    if not isinstance(value, list) or not value:
        raise HistoryCampaignError("campaign kinds must be a non-empty array")
    if any(item not in _KIND_ORDER for item in value) or len(value) != len(set(value)):
        raise HistoryCampaignError("campaign kinds must be unique trade, mark, or funding values")
    return tuple(sorted(cast(list[CampaignKind], value), key=_KIND_ORDER.__getitem__))


def _symbols(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > MAX_CAMPAIGN_SYMBOLS:
        raise HistoryCampaignError(
            f"campaign symbols must contain 1 through {MAX_CAMPAIGN_SYMBOLS} values"
        )
    if any(
        not isinstance(item, str) or not item or item != item.upper() or not item.isalnum()
        for item in value
    ):
        raise HistoryCampaignError("campaign symbols must be uppercase alphanumeric text")
    symbols = cast(list[str], value)
    if len(symbols) != len(set(symbols)):
        raise HistoryCampaignError("campaign symbols must be unique")
    return tuple(symbols)


def _month_windows(start_ms: int, end_ms: int) -> tuple[tuple[int, int, int, int], ...]:
    start_seconds = start_ms // 1000
    try:
        start_struct = time.gmtime(start_seconds)
    except (OverflowError, OSError, ValueError) as error:
        raise HistoryCampaignError(
            "campaign timestamp is outside the supported UTC range"
        ) from error
    year = start_struct.tm_year
    month = start_struct.tm_mon
    windows: list[tuple[int, int, int, int]] = []
    while True:
        month_start = calendar.timegm((year, month, 1, 0, 0, 0)) * 1000
        if month == 12:
            next_year, next_month = year + 1, 1
        else:
            next_year, next_month = year, month + 1
        next_start = calendar.timegm((next_year, next_month, 1, 0, 0, 0)) * 1000
        window_start = max(start_ms, month_start)
        window_end = min(end_ms, next_start - MINUTE_MS)
        if window_start <= window_end:
            windows.append((year, month, window_start, window_end))
        if len(windows) > MAX_CAMPAIGN_MONTHS:
            raise HistoryCampaignError(
                f"campaign exceeds the {MAX_CAMPAIGN_MONTHS}-month capacity boundary"
            )
        if next_start > end_ms:
            break
        year, month = next_year, next_month
    return tuple(windows)


def _eligible(snapshot: InstrumentSnapshot) -> bool:
    return (
        snapshot.category == "linear"
        and snapshot.contract_type == "LinearPerpetual"
        and snapshot.quote_coin == "USDT"
        and snapshot.settle_coin == "USDT"
    )


def _first_aligned_at_or_after(timestamp_ms: int) -> int:
    return ((timestamp_ms + MINUTE_MS - 1) // MINUTE_MS) * MINUTE_MS


def _first_aligned_after(timestamp_ms: int) -> int:
    return (timestamp_ms // MINUTE_MS + 1) * MINUTE_MS


def _last_aligned_at_or_before(timestamp_ms: int) -> int:
    return timestamp_ms // MINUTE_MS * MINUTE_MS


def _series_window(
    instrument: InstrumentSnapshot,
    *,
    kind: CampaignKind,
    window_start_ms: int,
    window_end_ms: int,
    funding_source_start_ms: int | None = None,
) -> tuple[int, int] | None:
    launch_floor = (
        _first_aligned_after(instrument.launch_time_ms)
        if kind == "funding"
        else _first_aligned_at_or_after(instrument.launch_time_ms)
    )
    start_ms = max(window_start_ms, launch_floor)
    if kind == "funding" and funding_source_start_ms is not None:
        start_ms = max(start_ms, funding_source_start_ms)
    end_ms = window_end_ms
    if instrument.delivery_time_ms is not None:
        end_ms = min(end_ms, _last_aligned_at_or_before(instrument.delivery_time_ms))
    return None if start_ms > end_ms else (start_ms, end_ms)


def _page_count(
    series: list[dict[str, object]],
    *,
    kind: CampaignKind,
    history_page_limit: int,
    funding_page_span_minutes: int,
) -> int:
    count = 0
    for item in series:
        minutes = (cast(int, item["end_ms"]) - cast(int, item["start_ms"])) // MINUTE_MS + 1
        if kind == "funding":
            count += 1 + (minutes + funding_page_span_minutes - 1) // funding_page_span_minutes
        else:
            count += (minutes + history_page_limit - 1) // history_page_limit
    return count


def _job_request(
    *,
    campaign_id: str,
    kind: CampaignKind,
    year: int,
    month: int,
    bucket: int,
    series: list[dict[str, object]],
    history_page_limit: int,
    funding_page_limit: int,
    funding_page_span_minutes: int,
    workers: int,
    target_rps: int,
    max_attempts: int,
) -> dict[str, object]:
    pages = _page_count(
        series,
        kind=kind,
        history_page_limit=history_page_limit,
        funding_page_span_minutes=funding_page_span_minutes,
    )
    max_http_requests = pages * max_attempts
    if max_http_requests > 100_000:
        raise HistoryCampaignError("generated monthly job exceeds the 100,000-request hard bound")
    job_id = f"{campaign_id}-{kind}-{year:04d}-{month:02d}-b{bucket:02d}"
    common: dict[str, object] = {
        "job_id": job_id,
        "series": series,
        "workers": workers,
        "target_rps": target_rps,
        "max_attempts": max_attempts,
        "max_http_requests": max_http_requests,
    }
    if kind == "funding":
        return {
            "contract": FUNDING_REQUEST_CONTRACT,
            **common,
            "page_span_minutes": funding_page_span_minutes,
            "page_limit": funding_page_limit,
        }
    return {
        "contract": HISTORY_REQUEST_CONTRACT,
        **common,
        "kind": kind,
        "page_limit": history_page_limit,
    }


def _relative_job_root(staging_root: Path, plan: HistoryJobPlan | FundingJobPlan) -> str:
    return plan.paths.job_root.relative_to(staging_root).as_posix()


def _campaign_plan_payload(
    *,
    request: Mapping[str, object],
    request_sha256: str,
    instrument_evidence_sha256: str,
    capacity_evidence_sha256: str,
    staging_root: Path,
    jobs: tuple[PreparedCampaignJob, ...],
    funding_source_boundary: Mapping[str, object] | None,
) -> dict[str, object]:
    descriptors: list[dict[str, object]] = []
    for job in jobs:
        descriptors.append(
            {
                "bucket": job.bucket,
                "job_id": job.job_id,
                "job_plan_sha256": job.plan.plan_sha256,
                "job_root": _relative_job_root(staging_root, job.plan),
                "kind": job.kind,
                "month": f"{job.year:04d}-{job.month:02d}",
                "planned_page_count": job.planned_page_count,
                "request": job.request_payload,
                "request_sha256": canonical_sha256(job.request_payload),
                "sequence": job.sequence,
            }
        )
    payload: dict[str, object] = {
        "campaign_id": request["campaign_id"],
        "campaign_request": request,
        "campaign_request_sha256": request_sha256,
        "capacity_evidence_sha256": capacity_evidence_sha256,
        "contract": CAMPAIGN_PLAN_CONTRACT,
        "instrument_evidence_sha256": instrument_evidence_sha256,
        "job_count": len(descriptors),
        "jobs": descriptors,
        "lifecycle_policy": LIFECYCLE_POLICY,
        "source_policy": {
            "funding": "/v5/market/funding/history",
            "mark": "/v5/market/mark-price-kline",
            "trade": "/v5/market/kline",
            "tick_rows_requested": False,
        },
    }
    if funding_source_boundary is not None:
        payload["funding_source_boundary"] = dict(funding_source_boundary)
    return payload


def _receipt_payload(artifact: str, digest: str) -> dict[str, object]:
    return {
        "artifact": artifact,
        "artifact_sha256": digest,
        "contract": CAMPAIGN_RECEIPT_CONTRACT,
        "status": "complete",
    }


def _atomic_write_new(path: Path, payload: Mapping[str, object]) -> None:
    if path.exists():
        raise HistoryCampaignError(f"refusing to replace campaign artifact: {path}")
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


def _load_canonical_object(path: Path) -> dict[str, object]:
    try:
        data = path.read_bytes()
        raw = json.loads(data)
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryCampaignError(f"cannot load campaign JSON: {path}") from error
    if not isinstance(raw, dict) or canonical_json_bytes(raw) != data:
        raise HistoryCampaignError(f"campaign artifact is not canonical JSON: {path}")
    return cast(dict[str, object], raw)


def _verify_receipt(path: Path, receipt_path: Path) -> tuple[dict[str, object], str]:
    if not path.is_file() or not receipt_path.is_file():
        raise HistoryCampaignError(f"campaign artifact/receipt pair is incomplete: {path}")
    payload = _load_canonical_object(path)
    receipt = _load_canonical_object(receipt_path)
    digest = sha256_file(path)
    if receipt != _receipt_payload(path.name, digest):
        raise HistoryCampaignError(f"campaign receipt does not verify: {path}")
    return payload, digest


def _existing_state(
    campaign_root: Path,
    *,
    expected_plan: Mapping[str, object],
) -> bool:
    if not campaign_root.exists():
        return False
    if not campaign_root.is_dir() or campaign_root.is_symlink():
        raise HistoryCampaignError("campaign root must be a non-symlink directory")
    names = {path.name for path in campaign_root.iterdir()}
    partial = {"plan.json", "plan.receipt.json"}
    complete = partial | {"manifest.json", "completion-receipt.json"}
    if names not in (partial, complete):
        raise HistoryCampaignError("campaign root contains incomplete or orphan artifacts")
    plan, _digest = _verify_receipt(
        campaign_root / "plan.json",
        campaign_root / "plan.receipt.json",
    )
    if plan != expected_plan:
        raise HistoryCampaignError("existing campaign plan does not match deterministic preflight")
    if names == partial:
        return False
    verify_completed_history_campaign(campaign_root)
    return True


def preflight_history_campaign(
    request_path: Path,
    *,
    instrument_registry_path: Path,
    capacity_evidence_path: Path,
    staging_root: Path,
    snapshot: HostSnapshot,
    now_ms: int,
    closed_before_ms: int,
    funding_source_boundary_root: Path | None = None,
) -> HistoryCampaignPlan:
    """Resolve every monthly/bucket job and aggregate admission before mutation."""

    resolved_request_path, request = _load_request(request_path)
    if set(request) - _REQUEST_KEYS or request.get("contract") != CAMPAIGN_REQUEST_CONTRACT:
        raise HistoryCampaignError("campaign request fields or contract do not match v1")
    campaign_id = _text("campaign_id", request.get("campaign_id"))
    if CAMPAIGN_ID_RE.fullmatch(campaign_id) is None:
        raise HistoryCampaignError("campaign_id does not match the bounded v1 identifier")
    if request.get("lifecycle_policy") != LIFECYCLE_POLICY:
        raise HistoryCampaignError("campaign must explicitly select the v1 lifecycle policy")
    kinds = _kinds(request.get("kinds"))
    symbols = _symbols(request.get("symbols"))
    start_ms = _integer("start_ms", request.get("start_ms"), minimum=0, maximum=2**63 - 1)
    end_ms = _integer("end_ms", request.get("end_ms"), minimum=0, maximum=2**63 - 1)
    if start_ms % MINUTE_MS or end_ms % MINUTE_MS or end_ms < start_ms:
        raise HistoryCampaignError("campaign range must be ordered and UTC-minute aligned")
    if (
        isinstance(closed_before_ms, bool)
        or not isinstance(closed_before_ms, int)
        or closed_before_ms < 0
        or closed_before_ms % MINUTE_MS
    ):
        raise HistoryCampaignError("closed_before_ms must be an aligned UTC minute")
    if end_ms >= closed_before_ms:
        raise HistoryCampaignError("campaign may acquire only closed one-minute history")
    history_page_limit = _integer(
        "history_page_limit", request.get("history_page_limit", 1000), minimum=1, maximum=1000
    )
    funding_page_limit = _integer(
        "funding_page_limit", request.get("funding_page_limit", 200), minimum=1, maximum=200
    )
    funding_page_span_minutes = _integer(
        "funding_page_span_minutes",
        request.get("funding_page_span_minutes", 10_080),
        minimum=1,
        maximum=10_080,
    )
    workers = _integer("workers", request.get("workers", 24), minimum=1, maximum=32)
    target_rps = _integer("target_rps", request.get("target_rps", 10), minimum=1, maximum=96)
    max_attempts = _integer("max_attempts", request.get("max_attempts", 3), minimum=1, maximum=5)

    verified_evidence = load_verified_request_evidence(
        instrument_registry_path, capacity_evidence_path
    )
    registry = verified_evidence.registry
    capacity_path = verified_evidence.capacity_path
    capacity = verified_evidence.capacity
    capacity_sha256 = verified_evidence.capacity_artifact_sha256
    by_symbol = registry.by_symbol()
    selected: list[InstrumentSnapshot] = []
    for symbol in symbols:
        instrument = by_symbol.get(symbol)
        if instrument is None:
            raise HistoryCampaignError(f"campaign symbol is absent from registry: {symbol}")
        if not _eligible(instrument):
            raise HistoryCampaignError(f"campaign symbol is not a USDT linear perpetual: {symbol}")
        selected.append(instrument)
    selected.sort(key=lambda item: item.instrument_id)
    funding_source_starts: dict[str, int] = {}
    funding_source_predecessors: dict[str, int] = {}
    funding_boundary_binding: dict[str, object] | None = None
    if funding_source_boundary_root is not None:
        if "funding" not in kinds:
            raise HistoryCampaignError(
                "funding source boundary requires funding in the campaign kinds"
            )
        try:
            completed_boundary = verify_completed_funding_source_boundary(
                funding_source_boundary_root
            )
        except FundingSourceBoundaryError as error:
            raise HistoryCampaignError("funding source boundary does not verify") from error
        if completed_boundary.registry_sha256 != registry.artifact_sha256:
            raise HistoryCampaignError("funding source boundary registry differs from campaign")
        if completed_boundary.scan_start_ms > start_ms or completed_boundary.scan_end_ms < end_ms:
            raise HistoryCampaignError("funding source boundary does not cover campaign range")
        results_by_symbol = {result.symbol: result for result in completed_boundary.results}
        if set(results_by_symbol) != set(symbols):
            raise HistoryCampaignError("funding source boundary symbol inventory differs")
        selected_by_symbol = {instrument.symbol: instrument for instrument in selected}
        for symbol, result in results_by_symbol.items():
            instrument = selected_by_symbol[symbol]
            if (
                result.instrument_id != instrument.instrument_id
                or result.predecessor_settlement_ms != result.first_observed_settlement_ms
                or result.predecessor_settlement_ms >= result.canonical_start_ms
                or result.canonical_start_ms > end_ms
            ):
                raise HistoryCampaignError("funding source boundary result is incompatible")
            funding_source_starts[symbol] = result.canonical_start_ms
            funding_source_predecessors[symbol] = result.predecessor_settlement_ms
        funding_boundary_binding = {
            "manifest_sha256": completed_boundary.manifest_sha256,
            "plan_sha256": completed_boundary.plan_sha256,
            "request_sha256": completed_boundary.request_sha256,
            "software_identity": completed_boundary.software_identity,
        }
    windows = _month_windows(start_ms, end_ms)

    prepared: list[PreparedCampaignJob] = []
    represented: dict[CampaignKind, set[str]] = {kind: set() for kind in kinds}
    root = staging_root.resolve()
    for year, month, window_start, window_end in windows:
        for kind in kinds:
            by_bucket: dict[int, list[dict[str, object]]] = {}
            for instrument in selected:
                intersection = _series_window(
                    instrument,
                    kind=kind,
                    window_start_ms=window_start,
                    window_end_ms=window_end,
                    funding_source_start_ms=(
                        funding_source_starts.get(instrument.symbol) if kind == "funding" else None
                    ),
                )
                if intersection is None:
                    continue
                represented[kind].add(instrument.symbol)
                item = {
                    "symbol": instrument.symbol,
                    "start_ms": intersection[0],
                    "end_ms": intersection[1],
                }
                by_bucket.setdefault(instrument.instrument_id % BUCKET_COUNT, []).append(item)
            for bucket, series in sorted(by_bucket.items()):
                payload = _job_request(
                    campaign_id=campaign_id,
                    kind=kind,
                    year=year,
                    month=month,
                    bucket=bucket,
                    series=series,
                    history_page_limit=history_page_limit,
                    funding_page_limit=funding_page_limit,
                    funding_page_span_minutes=funding_page_span_minutes,
                    workers=workers,
                    target_rps=target_rps,
                    max_attempts=max_attempts,
                )
                if kind == "funding":
                    predecessor_by_symbol = {
                        cast(str, item["symbol"]): funding_source_predecessors[
                            cast(str, item["symbol"])
                        ]
                        for item in series
                        if cast(int, item["start_ms"])
                        == funding_source_starts.get(cast(str, item["symbol"]))
                    }
                    funding = resolve_funding_request_payload(
                        payload,
                        source_path=resolved_request_path,
                        instrument_registry_path=instrument_registry_path,
                        capacity_evidence_path=capacity_path,
                        verified_evidence=verified_evidence,
                        predecessor_by_symbol=predecessor_by_symbol,
                    )
                    job_plan: HistoryJobPlan | FundingJobPlan = preflight_funding_job(
                        root,
                        funding.spec,
                        funding.budget,
                        snapshot,
                        now_ms=now_ms,
                        closed_before_ms=closed_before_ms,
                    )
                else:
                    history = resolve_history_request_payload(
                        payload,
                        source_path=resolved_request_path,
                        instrument_registry_path=instrument_registry_path,
                        capacity_evidence_path=capacity_path,
                        verified_evidence=verified_evidence,
                    )
                    job_plan = preflight_history_job(
                        root,
                        history.spec,
                        history.budget,
                        snapshot,
                        now_ms=now_ms,
                        closed_before_ms=closed_before_ms,
                    )
                prepared.append(
                    PreparedCampaignJob(
                        sequence=len(prepared),
                        kind=kind,
                        year=year,
                        month=month,
                        bucket=bucket,
                        request_payload=payload,
                        plan=job_plan,
                    )
                )
                if len(prepared) > MAX_CAMPAIGN_JOBS:
                    raise HistoryCampaignError(
                        f"campaign exceeds the {MAX_CAMPAIGN_JOBS}-job hard bound"
                    )
    absent = [
        f"{kind}:{symbol}"
        for kind in kinds
        for symbol in symbols
        if symbol not in represented[kind]
    ]
    if absent:
        raise HistoryCampaignError(
            "campaign range has no lifecycle intersection for requested series: "
            + ", ".join(absent)
        )
    jobs = tuple(prepared)
    if not jobs:
        raise HistoryCampaignError("campaign resolved to no acquisition jobs")
    request_sha256 = canonical_sha256(request)
    plan_payload = _campaign_plan_payload(
        request=request,
        request_sha256=request_sha256,
        instrument_evidence_sha256=registry.artifact_sha256,
        capacity_evidence_sha256=capacity_sha256,
        staging_root=root,
        jobs=jobs,
        funding_source_boundary=funding_boundary_binding,
    )
    plan_sha256 = canonical_sha256(plan_payload)
    campaigns_root = root / ".campaigns"
    if campaigns_root.is_symlink():
        raise HistoryCampaignError("campaign namespace cannot be a symlink")
    campaign_root = root / ".campaigns" / f"{campaign_id}--{plan_sha256[:16]}"
    existing_complete = _existing_state(campaign_root, expected_plan=plan_payload)

    active_and_building = active_and_building_bytes_from_capacity(capacity)
    operating_reserve = jobs[0].plan.budget.operating_reserve_bytes
    remaining_staging = 0
    planned_peak_memory = 0
    for job in jobs:
        planned_peak_memory = max(planned_peak_memory, job.plan.planned_peak_memory_bytes)
        if job.existing_complete:
            continue
        if job.kind == "funding":
            remaining_staging += FUNDING_STAGING_METADATA_BYTES
            remaining_staging += job.pending_page_count * FUNDING_MAX_PAGE_ARTIFACT_BYTES
        else:
            remaining_staging += HISTORY_STAGING_METADATA_BYTES
            remaining_staging += job.pending_page_count * HISTORY_MAX_PAGE_ARTIFACT_BYTES
    required_free = active_and_building + operating_reserve + remaining_staging
    if snapshot.volume_free_bytes < required_free:
        raise HistoryCampaignError(
            "insufficient free space for the aggregate pending campaign and active/building reserve"
        )
    if planned_peak_memory > snapshot.memory_available_bytes:
        raise HistoryCampaignError("insufficient available memory for campaign workers")
    if planned_peak_memory * 100 > snapshot.memory_total_bytes * MAX_MEMORY_PERCENT:
        raise HistoryCampaignError("campaign exceeds the 70% total-memory gate")
    return HistoryCampaignPlan(
        request_path=resolved_request_path,
        request_payload=request,
        request_sha256=request_sha256,
        instrument_evidence_sha256=registry.artifact_sha256,
        capacity_evidence_sha256=capacity_sha256,
        staging_root=root,
        campaign_root=campaign_root,
        plan_path=campaign_root / "plan.json",
        plan_receipt_path=campaign_root / "plan.receipt.json",
        manifest_path=campaign_root / "manifest.json",
        completion_receipt_path=campaign_root / "completion-receipt.json",
        jobs=jobs,
        plan_payload=plan_payload,
        plan_sha256=plan_sha256,
        required_free_bytes=required_free,
        planned_peak_memory_bytes=planned_peak_memory,
        existing_complete=existing_complete,
    )


def _publish_plan_if_new(plan: HistoryCampaignPlan) -> None:
    if plan.plan_path.exists():
        return
    _atomic_write_new(plan.plan_path, plan.plan_payload)
    _atomic_write_new(
        plan.plan_receipt_path,
        _receipt_payload(plan.plan_path.name, sha256_file(plan.plan_path)),
    )


def _completed_job_entry(
    job: PreparedCampaignJob,
    completed: CompletedHistoryJob | CompletedFundingJob,
    *,
    staging_root: Path,
) -> dict[str, object]:
    manifest = _load_canonical_object(completed.manifest_path)
    request_bound = manifest.get("request_bound")
    if not isinstance(request_bound, dict):
        raise HistoryCampaignError("completed child manifest has no request bound")
    actual_http_requests = request_bound.get("actual_http_requests")
    if isinstance(actual_http_requests, bool) or not isinstance(actual_http_requests, int):
        raise HistoryCampaignError("completed child manifest has invalid HTTP request count")
    return {
        "actual_http_requests": actual_http_requests,
        "job_id": job.job_id,
        "job_manifest_sha256": completed.manifest_sha256,
        "job_plan_sha256": job.plan.plan_sha256,
        "job_root": completed.job_root.relative_to(staging_root).as_posix(),
        "kind": job.kind,
        "page_count": completed.page_count,
        "row_count": completed.row_count,
        "sequence": job.sequence,
    }


def execute_history_campaign(
    plan: HistoryCampaignPlan,
    *,
    kline_client_factory: Callable[[], KlineClient],
    funding_client_factory: Callable[[], FundingClient],
    snapshot_provider: Callable[[], HostSnapshot],
    now_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    progress: Callable[[PreparedCampaignJob, CompletedHistoryJob | CompletedFundingJob], None]
    | None = None,
) -> CompletedHistoryCampaign:
    """Run child jobs sequentially and publish a receipt-last aggregate manifest."""

    if plan.existing_complete:
        return verify_completed_history_campaign(plan.campaign_root)
    _publish_plan_if_new(plan)
    entries: list[dict[str, object]] = []
    for job in plan.jobs:
        if job.kind == "funding":
            if not isinstance(job.plan, FundingJobPlan):
                raise HistoryCampaignError("funding campaign job has the wrong plan type")
            completed: CompletedHistoryJob | CompletedFundingJob = execute_funding_job(
                job.plan,
                funding_client_factory,
                snapshot_provider,
                now_ms=now_ms,
            )
        else:
            if not isinstance(job.plan, HistoryJobPlan):
                raise HistoryCampaignError("candle campaign job has the wrong plan type")
            completed = execute_history_job(
                job.plan,
                kline_client_factory,
                snapshot_provider,
                now_ms=now_ms,
            )
        entries.append(_completed_job_entry(job, completed, staging_root=plan.staging_root))
        if progress is not None:
            progress(job, completed)
    manifest: dict[str, object] = {
        "campaign_id": plan.request_payload["campaign_id"],
        "campaign_plan_sha256": plan.plan_sha256,
        "campaign_request_sha256": plan.request_sha256,
        "capacity_evidence_sha256": plan.capacity_evidence_sha256,
        "completed_at_ms": now_ms(),
        "contract": CAMPAIGN_MANIFEST_CONTRACT,
        "http_request_count": sum(cast(int, item["actual_http_requests"]) for item in entries),
        "instrument_evidence_sha256": plan.instrument_evidence_sha256,
        "job_count": len(entries),
        "jobs": entries,
        "page_count": sum(cast(int, item["page_count"]) for item in entries),
        "row_count": sum(cast(int, item["row_count"]) for item in entries),
        "source_policy": plan.plan_payload["source_policy"],
        "status": "complete",
    }
    _atomic_write_new(plan.manifest_path, manifest)
    _atomic_write_new(
        plan.completion_receipt_path,
        _receipt_payload(plan.manifest_path.name, sha256_file(plan.manifest_path)),
    )
    return verify_completed_history_campaign(plan.campaign_root)


def _relative_child_root(campaign_root: Path, raw: object) -> Path:
    if not isinstance(raw, str):
        raise HistoryCampaignError("campaign child root must be relative POSIX text")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 2:
        raise HistoryCampaignError("campaign child root escapes the staging namespace")
    staging_root = campaign_root.parent.parent
    return staging_root.joinpath(*relative.parts)


def verify_completed_history_campaign(
    campaign_root: Path,
    *,
    child_verifier: CampaignChildVerifier | None = None,
) -> CompletedHistoryCampaign:
    """Verify the aggregate receipt, child manifests, hashes, totals, and exact allowlist."""

    supplied_root = campaign_root.absolute()
    if supplied_root.is_symlink() or supplied_root.parent.is_symlink():
        raise HistoryCampaignError("campaign root and namespace cannot be symlinks")
    root = supplied_root.resolve()
    if not root.is_dir():
        raise HistoryCampaignError("campaign root must be a non-symlink directory")
    expected_names = {
        "plan.json",
        "plan.receipt.json",
        "manifest.json",
        "completion-receipt.json",
    }
    if {path.name for path in root.iterdir()} != expected_names:
        raise HistoryCampaignError("completed campaign allowlist does not match v1")
    plan, plan_artifact_sha = _verify_receipt(root / "plan.json", root / "plan.receipt.json")
    manifest, manifest_sha = _verify_receipt(
        root / "manifest.json", root / "completion-receipt.json"
    )
    expected_plan_keys = {
        "campaign_id",
        "campaign_request",
        "campaign_request_sha256",
        "capacity_evidence_sha256",
        "contract",
        "instrument_evidence_sha256",
        "job_count",
        "jobs",
        "lifecycle_policy",
        "source_policy",
    }
    if "funding_source_boundary" in plan:
        expected_plan_keys.add("funding_source_boundary")
    expected_manifest_keys = {
        "campaign_id",
        "campaign_plan_sha256",
        "campaign_request_sha256",
        "capacity_evidence_sha256",
        "completed_at_ms",
        "contract",
        "http_request_count",
        "instrument_evidence_sha256",
        "job_count",
        "jobs",
        "page_count",
        "row_count",
        "source_policy",
        "status",
    }
    if set(plan) != expected_plan_keys or set(manifest) != expected_manifest_keys:
        raise HistoryCampaignError("campaign plan or manifest fields do not match v1")
    if plan.get("contract") != CAMPAIGN_PLAN_CONTRACT:
        raise HistoryCampaignError("unsupported campaign plan contract")
    if (
        manifest.get("contract") != CAMPAIGN_MANIFEST_CONTRACT
        or manifest.get("status") != "complete"
    ):
        raise HistoryCampaignError("unsupported or incomplete campaign manifest")
    if manifest.get("campaign_plan_sha256") != canonical_sha256(plan):
        raise HistoryCampaignError("campaign manifest does not bind the exact plan content")
    if plan_artifact_sha != canonical_sha256(plan):
        raise HistoryCampaignError("campaign plan artifact is not canonical-hash bound")
    campaign_request = plan.get("campaign_request")
    if not isinstance(campaign_request, dict) or plan.get(
        "campaign_request_sha256"
    ) != canonical_sha256(campaign_request):
        raise HistoryCampaignError("campaign request hash does not verify")
    if (
        set(campaign_request) - _REQUEST_KEYS
        or campaign_request.get("contract") != CAMPAIGN_REQUEST_CONTRACT
        or campaign_request.get("lifecycle_policy") != LIFECYCLE_POLICY
    ):
        raise HistoryCampaignError("bound campaign request fields do not match v1")
    campaign_id = _text("campaign_id", campaign_request.get("campaign_id"))
    if CAMPAIGN_ID_RE.fullmatch(campaign_id) is None:
        raise HistoryCampaignError("bound campaign identifier is invalid")
    _kinds(campaign_request.get("kinds"))
    _symbols(campaign_request.get("symbols"))
    request_start = _integer(
        "start_ms", campaign_request.get("start_ms"), minimum=0, maximum=2**63 - 1
    )
    request_end = _integer("end_ms", campaign_request.get("end_ms"), minimum=0, maximum=2**63 - 1)
    if request_start % MINUTE_MS or request_end % MINUTE_MS or request_end < request_start:
        raise HistoryCampaignError("bound campaign range is invalid")
    _month_windows(request_start, request_end)
    optional_integer_bounds = {
        "history_page_limit": (1, 1000),
        "funding_page_limit": (1, 200),
        "funding_page_span_minutes": (1, 10_080),
        "workers": (1, 32),
        "target_rps": (1, 96),
        "max_attempts": (1, 5),
    }
    for name, (minimum, maximum) in optional_integer_bounds.items():
        if name in campaign_request:
            _integer(name, campaign_request[name], minimum=minimum, maximum=maximum)
    if plan.get("campaign_id") != campaign_request.get("campaign_id"):
        raise HistoryCampaignError("campaign identifier differs from the bound request")
    if plan.get("lifecycle_policy") != LIFECYCLE_POLICY:
        raise HistoryCampaignError("campaign lifecycle policy is unsupported")
    expected_source_policy = {
        "funding": "/v5/market/funding/history",
        "mark": "/v5/market/mark-price-kline",
        "trade": "/v5/market/kline",
        "tick_rows_requested": False,
    }
    if plan.get("source_policy") != expected_source_policy:
        raise HistoryCampaignError("campaign source policy is unsupported")
    funding_boundary = plan.get("funding_source_boundary")
    if funding_boundary is not None and (
        not isinstance(funding_boundary, dict)
        or set(funding_boundary)
        != {"manifest_sha256", "plan_sha256", "request_sha256", "software_identity"}
        or any(
            not isinstance(funding_boundary.get(name), str)
            or SHA256_RE.fullmatch(cast(str, funding_boundary[name])) is None
            for name in ("manifest_sha256", "plan_sha256", "request_sha256")
        )
        or not isinstance(funding_boundary.get("software_identity"), str)
        or SOFTWARE_IDENTITY_RE.fullmatch(cast(str, funding_boundary["software_identity"])) is None
        or "funding" not in cast(list[object], campaign_request.get("kinds"))
    ):
        raise HistoryCampaignError("campaign funding source-boundary binding is invalid")
    completed_at_ms = manifest.get("completed_at_ms")
    if (
        isinstance(completed_at_ms, bool)
        or not isinstance(completed_at_ms, int)
        or completed_at_ms < 0
    ):
        raise HistoryCampaignError("campaign completion time is invalid")
    raw_plan_jobs = plan.get("jobs")
    raw_manifest_jobs = manifest.get("jobs")
    if not isinstance(raw_plan_jobs, list) or not isinstance(raw_manifest_jobs, list):
        raise HistoryCampaignError("campaign plan/manifest jobs must be arrays")
    if plan.get("job_count") != len(raw_plan_jobs) or manifest.get("job_count") != len(
        raw_manifest_jobs
    ):
        raise HistoryCampaignError("campaign job count does not match its inventory")
    if len(raw_plan_jobs) != len(raw_manifest_jobs):
        raise HistoryCampaignError("campaign plan and manifest job inventories differ")
    total_pages = 0
    total_rows = 0
    total_http = 0
    for sequence, (raw_plan_job, raw_manifest_job) in enumerate(
        zip(raw_plan_jobs, raw_manifest_jobs, strict=True)
    ):
        if not isinstance(raw_plan_job, dict) or not isinstance(raw_manifest_job, dict):
            raise HistoryCampaignError("campaign child descriptor must be an object")
        if set(raw_plan_job) != {
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
        } or set(raw_manifest_job) != {
            "actual_http_requests",
            "job_id",
            "job_manifest_sha256",
            "job_plan_sha256",
            "job_root",
            "kind",
            "page_count",
            "row_count",
            "sequence",
        }:
            raise HistoryCampaignError("campaign child fields do not match v1")
        if raw_plan_job.get("sequence") != sequence or raw_manifest_job.get("sequence") != sequence:
            raise HistoryCampaignError("campaign child sequences are not contiguous")
        kind = raw_plan_job.get("kind")
        if kind not in _KIND_ORDER or raw_manifest_job.get("kind") != kind:
            raise HistoryCampaignError("campaign child kind is invalid or mismatched")
        request = raw_plan_job.get("request")
        if not isinstance(request, dict) or raw_plan_job.get("request_sha256") != canonical_sha256(
            request
        ):
            raise HistoryCampaignError("campaign child request hash does not verify")
        if request.get("job_id") != raw_plan_job.get("job_id"):
            raise HistoryCampaignError("campaign child request job identifier differs")
        if kind == "funding":
            if request.get("contract") != FUNDING_REQUEST_CONTRACT or "kind" in request:
                raise HistoryCampaignError("campaign funding child request is invalid")
        elif request.get("contract") != HISTORY_REQUEST_CONTRACT or request.get("kind") != kind:
            raise HistoryCampaignError("campaign candle child request is invalid")
        if raw_plan_job.get("job_id") != raw_manifest_job.get("job_id"):
            raise HistoryCampaignError("campaign child job identifiers differ")
        if raw_plan_job.get("job_plan_sha256") != raw_manifest_job.get("job_plan_sha256"):
            raise HistoryCampaignError("campaign child plan hashes differ")
        if raw_plan_job.get("job_root") != raw_manifest_job.get("job_root"):
            raise HistoryCampaignError("campaign child roots differ")
        child_root = _relative_child_root(root, raw_plan_job.get("job_root"))
        expected_parent = ".funding-landing" if kind == "funding" else ".landing"
        plan_sha = raw_plan_job.get("job_plan_sha256")
        job_id = raw_plan_job.get("job_id")
        if not isinstance(plan_sha, str) or not isinstance(job_id, str):
            raise HistoryCampaignError("campaign child identity fields are invalid")
        expected_root = root.parent.parent / expected_parent / f"{job_id}--{plan_sha[:16]}"
        if child_root != expected_root:
            raise HistoryCampaignError("campaign child root is not deterministically derived")
        child = (
            child_verifier(child_root, cast(CampaignKind, kind))
            if child_verifier is not None
            else (
                verify_completed_funding_job(child_root)
                if kind == "funding"
                else verify_completed_history_job(child_root)
            )
        )
        if (kind == "funding") != isinstance(child, CompletedFundingJob):
            raise HistoryCampaignError("campaign child verifier returned the wrong job type")
        if child.manifest_sha256 != raw_manifest_job.get("job_manifest_sha256"):
            raise HistoryCampaignError("campaign child manifest hash does not verify")
        child_plan = _load_canonical_object(child.plan_path)
        if canonical_sha256(child_plan) != plan_sha:
            raise HistoryCampaignError("campaign child plan artifact hash does not verify")
        child_spec = child_plan.get("spec")
        if not isinstance(child_spec, dict) or child_spec.get("request_sha256") != raw_plan_job.get(
            "request_sha256"
        ):
            raise HistoryCampaignError("campaign child request is not bound by its job plan")
        if raw_plan_job.get("planned_page_count") != child.page_count:
            raise HistoryCampaignError("campaign planned page count differs from verified child")
        fields = {
            "page_count": child.page_count,
            "row_count": child.row_count,
        }
        if any(raw_manifest_job.get(name) != value for name, value in fields.items()):
            raise HistoryCampaignError("campaign child aggregate does not match verified job")
        actual_http = raw_manifest_job.get("actual_http_requests")
        if isinstance(actual_http, bool) or not isinstance(actual_http, int) or actual_http < 0:
            raise HistoryCampaignError("campaign child HTTP count is invalid")
        child_manifest = _load_canonical_object(child.manifest_path)
        child_bound = child_manifest.get("request_bound")
        if (
            not isinstance(child_bound, dict)
            or child_bound.get("actual_http_requests") != actual_http
        ):
            raise HistoryCampaignError("campaign child HTTP count differs from verified manifest")
        total_pages += child.page_count
        total_rows += child.row_count
        total_http += actual_http
    totals = {
        "http_request_count": total_http,
        "page_count": total_pages,
        "row_count": total_rows,
    }
    if any(manifest.get(name) != value for name, value in totals.items()):
        raise HistoryCampaignError("campaign manifest totals do not match verified children")
    if manifest.get("campaign_request_sha256") != plan.get("campaign_request_sha256"):
        raise HistoryCampaignError("campaign request hash changed between plan and manifest")
    if manifest.get("campaign_id") != plan.get("campaign_id"):
        raise HistoryCampaignError("campaign identifier changed between plan and manifest")
    if manifest.get("instrument_evidence_sha256") != plan.get("instrument_evidence_sha256"):
        raise HistoryCampaignError("campaign instrument evidence hash changed")
    if manifest.get("capacity_evidence_sha256") != plan.get("capacity_evidence_sha256"):
        raise HistoryCampaignError("campaign capacity evidence hash changed")
    if manifest.get("source_policy") != plan.get("source_policy"):
        raise HistoryCampaignError("campaign source policy changed")
    return CompletedHistoryCampaign(
        campaign_root=root,
        plan_path=root / "plan.json",
        manifest_path=root / "manifest.json",
        receipt_path=root / "completion-receipt.json",
        manifest_sha256=manifest_sha,
        job_count=len(raw_manifest_jobs),
        page_count=total_pages,
        row_count=total_rows,
        http_request_count=total_http,
    )
