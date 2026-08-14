"""Fast, receipt-bound topology diagnostics for canonical candle campaigns."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from pathlib import Path, PurePosixPath
from typing import Final, cast

import pyarrow.parquet as pq  # type: ignore[import-untyped]
from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file
from grid_market_store import PublishedDataset

from grid_data.evidence import verify_evidence
from grid_data.history_acquisition import HISTORY_PLAN_CONTRACT
from grid_data.history_campaign_coverage_audit import CAMPAIGN_COVERAGE_AUDIT_CONTRACT
from grid_data.history_campaign_publication import (
    CAMPAIGN_PUBLICATION_PLAN_CONTRACT,
    HistoryCampaignPublicationError,
    verify_completed_history_campaign_publication,
)
from grid_data.instrument_registry import load_verified_instrument_registry

BOUNDARY_DIAGNOSTIC_CONTRACT: Final = "grid.phase2-candle-boundary-diagnostic/v1"
MINUTE_MS: Final = 60_000
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
_KINDS: Final = ("trade", "mark")


@dataclass(slots=True)
class _SeriesState:
    kind: str
    instrument_id: int
    symbol: str
    registry_launch_ms: int
    registry_delivery_ms: int | None
    requested_start_ms: int | None = None
    requested_end_ms: int | None = None
    first_observed_ms: int | None = None
    last_observed_ms: int | None = None
    expected_minute_count: int = 0
    observed_row_count: int = 0
    internal_missing_minute_count: int = 0
    internal_gap_range_count: int = 0
    child_gap_range_count: int = 0
    segment_count: int = 0

    def add_segment(self, start_ms: int, end_ms: int, times: list[int]) -> None:
        if start_ms < 0 or end_ms < start_ms or start_ms % MINUTE_MS or end_ms % MINUTE_MS:
            raise HistoryCampaignPublicationError("candle diagnostic series bounds are invalid")
        if self.requested_end_ms is not None and start_ms != self.requested_end_ms + MINUTE_MS:
            raise HistoryCampaignPublicationError(
                "candle diagnostic requires contiguous chronological series segments"
            )
        if times != sorted(set(times)):
            raise HistoryCampaignPublicationError(
                "candle diagnostic observed keys are not sorted unique"
            )
        if times and (times[0] < start_ms or times[-1] > end_ms):
            raise HistoryCampaignPublicationError(
                "candle diagnostic observed key escapes requested series"
            )

        self.requested_start_ms = (
            start_ms if self.requested_start_ms is None else self.requested_start_ms
        )
        self.requested_end_ms = end_ms
        self.segment_count += 1
        self.expected_minute_count += ((end_ms - start_ms) // MINUTE_MS) + 1
        self.observed_row_count += len(times)
        self.child_gap_range_count += _gap_range_count(times, start_ms, end_ms)

        if not times:
            return
        if self.first_observed_ms is None:
            self.first_observed_ms = times[0]
        elif self.last_observed_ms is not None:
            gap = (times[0] - self.last_observed_ms) // MINUTE_MS - 1
            if gap > 0:
                self.internal_missing_minute_count += gap
                self.internal_gap_range_count += 1
        for previous, current in pairwise(times):
            gap = (current - previous) // MINUTE_MS - 1
            if gap > 0:
                self.internal_missing_minute_count += gap
                self.internal_gap_range_count += 1
        self.last_observed_ms = times[-1]

    def topology(self) -> dict[str, int]:
        if self.requested_start_ms is None or self.requested_end_ms is None:
            raise HistoryCampaignPublicationError("candle diagnostic series has no scope")
        if self.first_observed_ms is None or self.last_observed_ms is None:
            return {
                "fully_absent_minute_count": self.expected_minute_count,
                "fully_absent_range_count": 1,
                "internal_gap_range_count": 0,
                "internal_missing_minute_count": 0,
                "leading_gap_range_count": 0,
                "leading_missing_minute_count": 0,
                "trailing_gap_range_count": 0,
                "trailing_missing_minute_count": 0,
            }
        leading = (self.first_observed_ms - self.requested_start_ms) // MINUTE_MS
        trailing = (self.requested_end_ms - self.last_observed_ms) // MINUTE_MS
        missing = self.expected_minute_count - self.observed_row_count
        if leading + self.internal_missing_minute_count + trailing != missing:
            raise HistoryCampaignPublicationError(
                "candle diagnostic topology does not reconcile to observed rows"
            )
        return {
            "fully_absent_minute_count": 0,
            "fully_absent_range_count": 0,
            "internal_gap_range_count": self.internal_gap_range_count,
            "internal_missing_minute_count": self.internal_missing_minute_count,
            "leading_gap_range_count": int(leading > 0),
            "leading_missing_minute_count": leading,
            "trailing_gap_range_count": int(trailing > 0),
            "trailing_missing_minute_count": trailing,
        }


@dataclass(frozen=True, slots=True)
class HistoryCampaignBoundaryDiagnostic:
    payload: dict[str, object]
    unresolved: bool


def _gap_range_count(times: list[int], start_ms: int, end_ms: int) -> int:
    cursor = start_ms
    count = 0
    for observed in times:
        if observed > cursor:
            count += 1
        cursor = observed + MINUTE_MS
    return count + int(cursor <= end_ms)


def _canonical_object(path: Path) -> dict[str, object]:
    try:
        data = path.read_bytes()
        raw = json.loads(data)
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryCampaignPublicationError(
            f"cannot load candle diagnostic input: {path}"
        ) from error
    if not isinstance(raw, dict) or canonical_json_bytes(raw) != data:
        raise HistoryCampaignPublicationError(
            f"candle diagnostic input is not canonical JSON: {path}"
        )
    return cast(dict[str, object], raw)


def _evidence_object(path: Path) -> dict[str, object]:
    resolved = path.resolve()
    if not verify_evidence(resolved):
        raise HistoryCampaignPublicationError("campaign coverage evidence receipt does not verify")
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryCampaignPublicationError(
            "campaign coverage evidence is invalid JSON"
        ) from error
    if not isinstance(raw, dict):
        raise HistoryCampaignPublicationError("campaign coverage evidence must be an object")
    payload = cast(dict[str, object], raw)
    embedded = payload.get("content_sha256")
    hash_input = dict(payload)
    hash_input.pop("content_sha256", None)
    if embedded != canonical_sha256(hash_input):
        raise HistoryCampaignPublicationError(
            "campaign coverage evidence content hash does not verify"
        )
    return payload


def _generated_at(value: str) -> str:
    if not value.endswith("Z"):
        raise HistoryCampaignPublicationError("generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise HistoryCampaignPublicationError("generated_at_utc is invalid") from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise HistoryCampaignPublicationError("generated_at_utc must be UTC")
    return value


def _integer(parent: dict[str, object], key: str) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HistoryCampaignPublicationError(f"candle diagnostic field is invalid: {key}")
    return value


def _series(parent: dict[str, object]) -> list[dict[str, object]]:
    spec = parent.get("spec")
    if not isinstance(spec, dict) or not isinstance(spec.get("series"), list):
        raise HistoryCampaignPublicationError("candle diagnostic child plan has no series")
    raw = cast(list[object], spec["series"])
    if not raw or any(not isinstance(item, dict) for item in raw):
        raise HistoryCampaignPublicationError("candle diagnostic child series are invalid")
    return cast(list[dict[str, object]], raw)


def _observed_by_instrument(published: PublishedDataset) -> dict[int, list[int]]:
    observed: dict[int, list[int]] = {}
    for file in published.manifest.files:
        pure = PurePosixPath(file.path)
        parquet_path = published.dataset_root.joinpath(*pure.parts)
        table = pq.ParquetFile(parquet_path).read(columns=["instrument_id", "open_time_ms"])
        identifiers = cast(list[int], table.column("instrument_id").to_pylist())
        times = cast(list[int], table.column("open_time_ms").to_pylist())
        for instrument_id, open_time_ms in zip(identifiers, times, strict=True):
            observed.setdefault(instrument_id, []).append(open_time_ms)
    if sum(len(values) for values in observed.values()) != published.manifest.row_count:
        raise HistoryCampaignPublicationError("candle diagnostic Parquet row count differs")
    return observed


def _coverage_bindings(
    coverage: dict[str, object],
    plan: dict[str, object],
    *,
    publication_manifest_sha256: str,
) -> None:
    if coverage.get("contract") != CAMPAIGN_COVERAGE_AUDIT_CONTRACT:
        raise HistoryCampaignPublicationError("unsupported campaign coverage evidence")
    bindings = coverage.get("bindings")
    if not isinstance(bindings, dict):
        raise HistoryCampaignPublicationError("campaign coverage bindings are invalid")
    expected = {
        "capacity_evidence_sha256": plan.get("capacity_evidence_sha256"),
        "instrument_registry_sha256": plan.get("instrument_evidence_sha256"),
        "publication_manifest_sha256": publication_manifest_sha256,
        "publication_plan_sha256": canonical_sha256(plan),
        "publisher_software_identity": plan.get("publisher_software_identity"),
        "source_campaign_manifest_sha256": plan.get("source_campaign_manifest_sha256"),
        "source_campaign_plan_sha256": plan.get("source_campaign_plan_sha256"),
    }
    if any(bindings.get(key) != value for key, value in expected.items()):
        raise HistoryCampaignPublicationError(
            "campaign coverage evidence does not bind the verified publication"
        )


def build_history_campaign_boundary_diagnostic(
    publication_root: Path,
    source_campaign_root: Path,
    instrument_registry_path: Path,
    campaign_coverage_audit_path: Path,
    *,
    diagnostic_software_identity: str,
    generated_at_utc: str,
) -> HistoryCampaignBoundaryDiagnostic:
    """Classify canonical gaps without network calls or a second Landing semantic decode."""

    if SOFTWARE_IDENTITY_RE.fullmatch(diagnostic_software_identity) is None:
        raise HistoryCampaignPublicationError("diagnostic identity must be git:<40 hex>")
    generated_at = _generated_at(generated_at_utc)
    started_ns = time.perf_counter_ns()
    completed = verify_completed_history_campaign_publication(
        publication_root,
        source_campaign_root,
    )
    plan = _canonical_object(completed.plan_path)
    if plan.get("contract") != CAMPAIGN_PUBLICATION_PLAN_CONTRACT:
        raise HistoryCampaignPublicationError("unsupported publication plan for diagnostic")
    raw_jobs = plan.get("jobs")
    if not isinstance(raw_jobs, list) or len(raw_jobs) != completed.dataset_count:
        raise HistoryCampaignPublicationError("candle diagnostic publication inventory differs")
    jobs = cast(list[dict[str, object]], raw_jobs)
    if any(job.get("kind") not in _KINDS for job in jobs):
        raise HistoryCampaignPublicationError(
            "candle boundary diagnostic accepts candle-only campaigns"
        )

    registry = load_verified_instrument_registry(instrument_registry_path)
    if registry.artifact_sha256 != plan.get("instrument_evidence_sha256"):
        raise HistoryCampaignPublicationError("candle diagnostic registry binding differs")
    registry_by_id = {item.instrument_id: item for item in registry.snapshots}
    coverage = _evidence_object(campaign_coverage_audit_path)
    _coverage_bindings(
        coverage,
        plan,
        publication_manifest_sha256=completed.manifest_sha256,
    )

    staging_root = source_campaign_root.resolve().parent.parent
    states: dict[tuple[str, int], _SeriesState] = {}
    by_kind_dataset_count = {kind: 0 for kind in _KINDS}
    scanned_rows = 0
    for sequence, (job, published) in enumerate(
        zip(jobs, completed.published_datasets, strict=True)
    ):
        kind = job.get("kind")
        relative = job.get("source_job_root")
        if kind not in _KINDS or not isinstance(relative, str):
            raise HistoryCampaignPublicationError("candle diagnostic child identity is invalid")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or "\\" in relative:
            raise HistoryCampaignPublicationError("candle diagnostic child root is unsafe")
        child_plan_path = staging_root.joinpath(*pure.parts) / "plan.json"
        if sha256_file(child_plan_path) != job.get("source_job_plan_sha256"):
            raise HistoryCampaignPublicationError("candle diagnostic child plan hash differs")
        child_plan = _canonical_object(child_plan_path)
        if child_plan.get("contract") != HISTORY_PLAN_CONTRACT:
            raise HistoryCampaignPublicationError("unsupported candle child plan")
        planned_series = _series(child_plan)
        observed = _observed_by_instrument(published)
        expected_ids: set[int] = set()
        for raw_series in planned_series:
            series_kind = raw_series.get("kind")
            instrument_id = raw_series.get("instrument_id")
            symbol = raw_series.get("symbol")
            start_ms = raw_series.get("start_ms")
            end_ms = raw_series.get("end_ms")
            if (
                series_kind != kind
                or isinstance(instrument_id, bool)
                or not isinstance(instrument_id, int)
                or not isinstance(symbol, str)
                or isinstance(start_ms, bool)
                or not isinstance(start_ms, int)
                or isinstance(end_ms, bool)
                or not isinstance(end_ms, int)
                or instrument_id in expected_ids
            ):
                raise HistoryCampaignPublicationError(
                    "candle diagnostic planned series identity is invalid"
                )
            expected_ids.add(instrument_id)
            snapshot = registry_by_id.get(instrument_id)
            if snapshot is None or snapshot.symbol != symbol:
                raise HistoryCampaignPublicationError(
                    "candle diagnostic planned series differs from registry"
                )
            key = (kind, instrument_id)
            state = states.get(key)
            if state is None:
                state = _SeriesState(
                    kind=kind,
                    instrument_id=instrument_id,
                    symbol=symbol,
                    registry_launch_ms=snapshot.launch_time_ms,
                    registry_delivery_ms=snapshot.delivery_time_ms,
                )
                states[key] = state
            elif state.symbol != symbol:
                raise HistoryCampaignPublicationError("candle diagnostic symbol changed")
            state.add_segment(start_ms, end_ms, observed.get(instrument_id, []))
        if set(observed) - expected_ids:
            raise HistoryCampaignPublicationError(
                "candle diagnostic canonical rows are outside the child request"
            )
        job_rows = sum(len(values) for values in observed.values())
        if job_rows != _integer(job, "row_count"):
            raise HistoryCampaignPublicationError(
                f"candle diagnostic child {sequence} row count differs"
            )
        scanned_rows += job_rows
        by_kind_dataset_count[kind] += 1

    if scanned_rows != completed.row_count:
        raise HistoryCampaignPublicationError("candle diagnostic campaign row count differs")
    if not states:
        raise HistoryCampaignPublicationError("candle diagnostic has no candle series")

    topology_fields = (
        "fully_absent_minute_count",
        "fully_absent_range_count",
        "internal_gap_range_count",
        "internal_missing_minute_count",
        "leading_gap_range_count",
        "leading_missing_minute_count",
        "trailing_gap_range_count",
        "trailing_missing_minute_count",
    )
    totals = {name: 0 for name in topology_fields}
    totals.update(
        {
            "child_gap_range_count": 0,
            "expected_minute_count": 0,
            "observed_row_count": 0,
        }
    )
    by_kind: list[dict[str, object]] = []
    registry_clipped_series_count = 0
    registry_clipped_leading_gap_series_count = 0
    for kind in _KINDS:
        selected = [state for state in states.values() if state.kind == kind]
        if not selected:
            continue
        kind_topology = {name: 0 for name in topology_fields}
        expected = observed_rows = child_ranges = 0
        for state in selected:
            topology = state.topology()
            for name in topology_fields:
                kind_topology[name] += topology[name]
                totals[name] += topology[name]
            expected += state.expected_minute_count
            observed_rows += state.observed_row_count
            child_ranges += state.child_gap_range_count
            if state.requested_start_ms == state.registry_launch_ms:
                registry_clipped_series_count += 1
                if topology["leading_missing_minute_count"]:
                    registry_clipped_leading_gap_series_count += 1
        totals["expected_minute_count"] += expected
        totals["observed_row_count"] += observed_rows
        totals["child_gap_range_count"] += child_ranges
        by_kind.append(
            {
                "dataset_count": by_kind_dataset_count[kind],
                "expected_minute_count": expected,
                "gap_topology": kind_topology,
                "kind": kind,
                "missing_minute_count": expected - observed_rows,
                "observed_row_count": observed_rows,
                "series_count": len(selected),
                "source_child_gap_range_count": child_ranges,
            }
        )

    missing_total = totals["expected_minute_count"] - totals["observed_row_count"]
    topology_missing = sum(
        totals[name]
        for name in (
            "fully_absent_minute_count",
            "internal_missing_minute_count",
            "leading_missing_minute_count",
            "trailing_missing_minute_count",
        )
    )
    if topology_missing != missing_total:
        raise HistoryCampaignPublicationError("candle diagnostic aggregate topology differs")
    quality = coverage.get("quality")
    if not isinstance(quality, dict) or not isinstance(quality.get("candle"), dict):
        raise HistoryCampaignPublicationError("campaign coverage candle quality is invalid")
    candle_quality = cast(dict[str, object], quality["candle"])
    expected_quality = {
        "expected_minute_count": totals["expected_minute_count"],
        "gap_range_count": totals["child_gap_range_count"],
        "missing_minute_count": missing_total,
        "observed_row_count": totals["observed_row_count"],
    }
    if any(candle_quality.get(key) != value for key, value in expected_quality.items()):
        raise HistoryCampaignPublicationError(
            "candle diagnostic does not reconcile to semantic coverage evidence"
        )
    reason_policy = coverage.get("reason_policy")
    if not isinstance(reason_policy, dict) or not isinstance(
        reason_policy.get("observed_reason_counts"), dict
    ):
        raise HistoryCampaignPublicationError("campaign coverage reason policy is invalid")
    reason_counts = cast(dict[str, object], reason_policy["observed_reason_counts"])
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in reason_counts.values()
    ):
        raise HistoryCampaignPublicationError("campaign coverage reason counts are invalid")
    if sum(cast(int, value) for value in reason_counts.values()) != missing_total:
        raise HistoryCampaignPublicationError(
            "candle diagnostic reasons do not reconcile to missing minutes"
        )

    elapsed_ms = (time.perf_counter_ns() - started_ns) // 1_000_000
    unresolved = missing_total > 0
    payload: dict[str, object] = {
        "bindings": {
            "campaign_coverage_artifact_sha256": sha256_file(
                campaign_coverage_audit_path.resolve()
            ),
            "campaign_coverage_content_sha256": coverage["content_sha256"],
            "instrument_registry_sha256": registry.artifact_sha256,
            "publication_manifest_sha256": completed.manifest_sha256,
            "publication_plan_sha256": canonical_sha256(plan),
            "publisher_software_identity": plan["publisher_software_identity"],
            "source_campaign_manifest_sha256": plan["source_campaign_manifest_sha256"],
            "source_campaign_plan_sha256": plan["source_campaign_plan_sha256"],
        },
        "contract": BOUNDARY_DIAGNOSTIC_CONTRACT,
        "diagnostic_software_identity": diagnostic_software_identity,
        "generated_at_utc": generated_at,
        "inventory": {
            "by_kind": by_kind,
            "dataset_count": completed.dataset_count,
            "expected_minute_count": totals["expected_minute_count"],
            "missing_minute_count": missing_total,
            "observed_row_count": totals["observed_row_count"],
            "series_count": len(states),
        },
        "limitations": [
            "First source-returned candle is an availability observation, not proof of venue "
            "listing time or a historical point-in-time metadata record.",
            "Current registry lifecycle metadata is ex-post acquisition scope and may contain "
            "coarse legacy launch boundaries.",
            "Topology does not accept leading, internal, trailing, or fully absent minutes; "
            "ADR-0026 coverage status and reason policy remain unchanged.",
            "This diagnostic does not download, repair, compact, register, select, close Gate 2, "
            "authorize Phase 3, or call a private/live endpoint.",
        ],
        "process": {
            "canonical_projection": "instrument-and-open-time-columns-once-v1",
            "canonical_rows_scanned": scanned_rows,
            "elapsed_ms": elapsed_ms,
            "network_request_count": 0,
            "publication_integrity_verified": True,
            "published_dataset_verification_reused": True,
            "source_market_rows_decoded": False,
        },
        "reason_policy": {
            "accepted_reason_codes": [],
            "observed_reason_counts": reason_counts,
            "unaccepted_reason_codes": sorted(reason_counts),
        },
        "result": {
            "coverage_reconciled": True,
            "fully_absent_minute_count": totals["fully_absent_minute_count"],
            "fully_absent_range_count": totals["fully_absent_range_count"],
            "internal_gap_range_count": totals["internal_gap_range_count"],
            "internal_missing_minute_count": totals["internal_missing_minute_count"],
            "leading_gap_range_count": totals["leading_gap_range_count"],
            "leading_missing_minute_count": totals["leading_missing_minute_count"],
            "registry_clipped_leading_gap_series_count": (
                registry_clipped_leading_gap_series_count
            ),
            "registry_clipped_series_count": registry_clipped_series_count,
            "source_child_gap_range_count": totals["child_gap_range_count"],
            "trailing_gap_range_count": totals["trailing_gap_range_count"],
            "trailing_missing_minute_count": totals["trailing_missing_minute_count"],
        },
        "status": (
            "diagnosed-unaccepted-candle-boundaries"
            if unresolved
            else "verified-no-candle-boundary-gap"
        ),
        "storage_policy": {
            "account_data_included": False,
            "dataset_or_instrument_identities_included": False,
            "market_values_included": False,
            "observed_timestamps_included": False,
            "runtime_paths_included": False,
            "runtime_market_artifacts_committed_to_git": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return HistoryCampaignBoundaryDiagnostic(payload=payload, unresolved=unresolved)
