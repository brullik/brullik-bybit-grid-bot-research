"""Receipt-bound evidence for Bybit's dated automatic funding-cadence policy."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from html.parser import HTMLParser
from itertools import pairwise
from pathlib import Path
from typing import Final, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from grid_contracts.canonical import canonical_sha256, sha256_file

from grid_data.evidence import verify_evidence
from grid_data.funding_acquisition import (
    load_verified_completed_funding_batch,
)

EVIDENCE_CONTRACT: Final = "grid.phase2-funding-cadence-policy-evidence/v1"
AUDIT_CONTRACT: Final = "grid.canonical-funding-coverage-audit/v1"
POLICY_URL: Final = (
    "https://announcements.bybit.com/en/article/"
    "important-update-to-perpetual-contract-funding-settlement-frequency-"
    "blt9e1f8c588fe457c7/"
)
POLICY_TITLE: Final = "Important update to Perpetual Contract funding settlement frequency"
POLICY_DATE_TEXT: Final = "Feb 23, 2026"
POLICY_EFFECTIVE_TEXT: Final = "Feb 26, 2026, 3AM UTC"
POLICY_EFFECTIVE_AT_MS: Final = 1_772_074_800_000
HOURLY_INTERVAL_MINUTES: Final = 60
DEFAULT_INTERVALS_MINUTES: Final = (120, 240, 480)
QUALIFYING_RATE_THRESHOLD: Final = Decimal("0.00025")
QUALIFYING_SETTLEMENT_COUNT: Final = 16
RESTORATION_PERIOD_ORDINAL: Final = 17
MAX_POLICY_RESPONSE_BYTES: Final = 2 * 1024 * 1024
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")

POLICY_MARKERS: Final = (
    POLICY_TITLE,
    POLICY_DATE_TEXT,
    POLICY_EFFECTIVE_TEXT,
    "absolute value of the funding rate remains less than or equal to 0.025% for 16 "
    "consecutive settlement periods",
    "restore the default settlement interval at the 17th period",
    "funding rate caps and settlement frequency may be adjusted dynamically without further notice",
    "Every 8 hours",
    "Every 4 hours",
    "Every 2 hours",
)


class FundingCadencePolicyError(ValueError):
    """The official policy or retained chronology cannot support the evidence claim."""


@dataclass(frozen=True, slots=True)
class OfficialPolicyPage:
    body: bytes
    content_type: str
    final_url: str
    status_code: int


class OfficialPolicyClient(Protocol):
    @property
    def transport_max_attempts(self) -> int: ...

    def fetch_policy_page(self) -> OfficialPolicyPage: ...


class UrllibOfficialPolicyClient:
    """One-attempt, credential-free reader for the exact accepted announcement page."""

    transport_max_attempts: Final = 1

    def fetch_policy_page(self) -> OfficialPolicyPage:
        request = Request(
            POLICY_URL,
            headers={
                "Accept": "text/html; charset=utf-8",
                "Accept-Encoding": "identity",
                "User-Agent": "grid-data-funding-cadence-policy/1",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read(MAX_POLICY_RESPONSE_BYTES + 1)
                status_code = response.getcode()
                final_url = response.geturl()
                content_type = response.headers.get_content_type()
        except (HTTPError, URLError, OSError) as error:
            raise FundingCadencePolicyError(
                "official funding policy page request failed"
            ) from error
        if (
            status_code != 200
            or final_url != POLICY_URL
            or content_type != "text/html"
            or len(body) > MAX_POLICY_RESPONSE_BYTES
        ):
            raise FundingCadencePolicyError("official funding policy page response is invalid")
        return OfficialPolicyPage(
            body=body,
            content_type=content_type,
            final_url=final_url,
            status_code=status_code,
        )


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fragments: list[str] = []

    def handle_data(self, data: str) -> None:
        self.fragments.append(data)


@dataclass(frozen=True, slots=True)
class _Observation:
    funding_time_ms: int
    funding_rate: Decimal
    interval_minutes: int


@dataclass(frozen=True, slots=True)
class _SeriesPolicyResult:
    completed_hourly_episode_count: int
    explained_interval_change_count: int
    hourly_episode_count: int
    open_hourly_episode_count: int
    open_nonqualifying_hourly_episode_count: int
    qualifying_count_histogram: tuple[tuple[int, int], ...]
    unexplained_interval_change_count: int


def _normalize_policy_text(body: bytes) -> str:
    try:
        source = body.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise FundingCadencePolicyError("official funding policy page is not UTF-8") from error
    parser = _TextExtractor()
    try:
        parser.feed(source)
        parser.close()
    except ValueError as error:
        raise FundingCadencePolicyError("official funding policy page HTML is invalid") from error
    return " ".join(" ".join(parser.fragments).split())


def _verify_policy_page(
    client: OfficialPolicyClient,
) -> tuple[OfficialPolicyPage, str]:
    if client.transport_max_attempts != 1:
        raise FundingCadencePolicyError("official policy evidence requires exactly one attempt")
    page = client.fetch_policy_page()
    if (
        page.status_code != 200
        or page.final_url != POLICY_URL
        or page.content_type != "text/html"
        or not page.body
        or len(page.body) > MAX_POLICY_RESPONSE_BYTES
    ):
        raise FundingCadencePolicyError("official funding policy page response is invalid")
    text = _normalize_policy_text(page.body)
    if any(marker not in text for marker in POLICY_MARKERS):
        raise FundingCadencePolicyError("official funding policy statements do not verify")
    return page, text


def _json_object(path: Path, *, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FundingCadencePolicyError(f"{label} cannot be loaded") from error
    if not isinstance(value, dict):
        raise FundingCadencePolicyError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _utc_text(value: str) -> str:
    if not value.endswith("Z"):
        raise FundingCadencePolicyError("generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise FundingCadencePolicyError("generated_at_utc is invalid") from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise FundingCadencePolicyError("generated_at_utc must resolve to UTC")
    return value


def _mapping(parent: Mapping[str, object], key: str) -> dict[str, object]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise FundingCadencePolicyError(f"verified funding audit field must be an object: {key}")
    return cast(dict[str, object], value)


def _array(parent: Mapping[str, object], key: str) -> list[object]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise FundingCadencePolicyError(f"verified funding audit field must be an array: {key}")
    return cast(list[object], value)


def _nonnegative_integer(parent: Mapping[str, object], key: str) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FundingCadencePolicyError(f"verified funding audit field must be non-negative: {key}")
    return value


def _verify_coverage_audit(path: Path) -> tuple[dict[str, object], str]:
    resolved = path.resolve()
    if not verify_evidence(resolved):
        raise FundingCadencePolicyError("funding coverage audit receipt does not verify")
    payload = _json_object(resolved, label="funding coverage audit")
    content = dict(payload)
    embedded_hash = content.pop("content_sha256", None)
    if embedded_hash != canonical_sha256(content):
        raise FundingCadencePolicyError("funding coverage audit content hash does not verify")
    if payload.get("contract") != AUDIT_CONTRACT or payload.get("status") != "blocked":
        raise FundingCadencePolicyError("funding coverage audit contract/status is incompatible")

    quality = _mapping(payload, "quality")
    for field in (
        "conflicting_key_count",
        "duplicate_key_count",
        "empty_range_page_count",
        "internal_interval_mismatch_count",
        "lifecycle_failure_count",
        "predecessor_interval_mismatch_count",
        "unexpected_timestamp_count",
        "unrequested_row_count",
    ):
        if _nonnegative_integer(quality, field) != 0:
            raise FundingCadencePolicyError(
                "funding cadence evidence cannot reinterpret non-cadence audit blockers"
            )
    if quality.get("canonical_source_table_equal") is not True:
        raise FundingCadencePolicyError("funding coverage audit source equality is unavailable")
    change_count = _nonnegative_integer(quality, "interval_change_count")
    reason_policy = _mapping(payload, "reason_policy")
    if (
        reason_policy.get("accepted_reason_codes") != []
        or reason_policy.get("unaccepted_reason_codes") != ["unexplained_interval_change"]
        or reason_policy.get("unknown_reason_count") != 0
        or reason_policy.get("observed_reason_counts")
        != {"unexplained_interval_change": change_count}
    ):
        raise FundingCadencePolicyError(
            "funding coverage audit contains reasons outside the cadence-policy scope"
        )
    return payload, sha256_file(resolved)


def _observations_by_instrument(table: object) -> dict[int, tuple[_Observation, ...]]:
    try:
        instrument_ids = table.column("instrument_id").to_pylist()  # type: ignore[attr-defined]
        funding_times = table.column("funding_time_ms").to_pylist()  # type: ignore[attr-defined]
        funding_rates = table.column("funding_rate").to_pylist()  # type: ignore[attr-defined]
        intervals = table.column("funding_interval_minutes").to_pylist()  # type: ignore[attr-defined]
    except (AttributeError, KeyError) as error:
        raise FundingCadencePolicyError("verified funding batch columns are unavailable") from error
    grouped: dict[int, list[_Observation]] = defaultdict(list)
    for instrument_id, funding_time, funding_rate, interval in zip(
        instrument_ids,
        funding_times,
        funding_rates,
        intervals,
        strict=True,
    ):
        if (
            isinstance(instrument_id, bool)
            or not isinstance(instrument_id, int)
            or isinstance(funding_time, bool)
            or not isinstance(funding_time, int)
            or not isinstance(funding_rate, Decimal)
            or isinstance(interval, bool)
            or not isinstance(interval, int)
        ):
            raise FundingCadencePolicyError("verified funding batch lost exact field types")
        grouped[instrument_id].append(
            _Observation(
                funding_time_ms=funding_time,
                funding_rate=funding_rate,
                interval_minutes=interval,
            )
        )
    result: dict[int, tuple[_Observation, ...]] = {}
    for instrument_id, rows in grouped.items():
        ordered = tuple(sorted(rows, key=lambda item: item.funding_time_ms))
        if len(ordered) != len({item.funding_time_ms for item in ordered}):
            raise FundingCadencePolicyError("verified funding batch contains duplicate times")
        result[instrument_id] = ordered
    return result


def _interval_change_count(rows: Sequence[_Observation]) -> int:
    return sum(
        current.interval_minutes != previous.interval_minutes
        for previous, current in pairwise(rows)
    )


def _trailing_qualifying_count(rows: Sequence[_Observation]) -> int:
    count = 0
    for item in reversed(rows):
        if abs(item.funding_rate) > QUALIFYING_RATE_THRESHOLD:
            break
        count += 1
    return count


class _PolicyMismatch(ValueError):
    pass


def _analyze_series_strict(rows: Sequence[_Observation]) -> _SeriesPolicyResult:
    if not rows or any(item.funding_time_ms < POLICY_EFFECTIVE_AT_MS for item in rows):
        raise _PolicyMismatch("series is outside the dated policy window")
    intervals = tuple(item.interval_minutes for item in rows)
    change_count = _interval_change_count(rows)
    hourly_runs: list[tuple[int, int]] = []
    index = 0
    while index < len(rows):
        if intervals[index] != HOURLY_INTERVAL_MINUTES:
            index += 1
            continue
        start = index
        while index + 1 < len(rows) and intervals[index + 1] == HOURLY_INTERVAL_MINUTES:
            index += 1
        hourly_runs.append((start, index))
        index += 1

    if not hourly_runs:
        if change_count:
            raise _PolicyMismatch("non-hourly cadence changes are not policy-explained")
        if intervals[0] not in DEFAULT_INTERVALS_MINUTES or len(set(intervals)) != 1:
            raise _PolicyMismatch("stable cadence is outside documented schedules")
        return _SeriesPolicyResult(0, 0, 0, 0, 0, (), 0)

    explained_changes = 0
    completed_count = 0
    open_count = 0
    open_nonqualifying_count = 0
    qualifying_counts: Counter[int] = Counter()
    previous_run_end = -1
    for run_index, (start, end) in enumerate(hourly_runs):
        preceding = intervals[previous_run_end + 1 : start]
        if start > 0:
            if not preceding:
                raise _PolicyMismatch("hourly entry has no preceding default cadence")
            if preceding[0] not in DEFAULT_INTERVALS_MINUTES or len(set(preceding)) != 1:
                raise _PolicyMismatch("pre-hourly cadence is not one documented default")
            explained_changes += 1

        hourly_rows = rows[start : end + 1]
        if end == len(rows) - 1:
            open_count += 1
            trailing = _trailing_qualifying_count(hourly_rows)
            if trailing > RESTORATION_PERIOD_ORDINAL:
                raise _PolicyMismatch("open hourly episode exceeds the restoration boundary")
            if trailing < QUALIFYING_SETTLEMENT_COUNT:
                open_nonqualifying_count += 1
            previous_run_end = end
            continue

        if run_index + 1 < len(hourly_runs):
            next_start = hourly_runs[run_index + 1][0]
        else:
            next_start = len(rows)
        post = intervals[end + 1 : next_start]
        if len(post) < 2:
            raise _PolicyMismatch("completed hourly episode lacks stable default evidence")
        default_interval = post[1]
        alignment_interval = post[0]
        if (
            default_interval not in DEFAULT_INTERVALS_MINUTES
            or any(value != default_interval for value in post[1:])
            or alignment_interval <= HOURLY_INTERVAL_MINUTES
            or alignment_interval > default_interval
            or alignment_interval % HOURLY_INTERVAL_MINUTES
        ):
            raise _PolicyMismatch("hourly restoration does not align to a documented schedule")
        trailing = _trailing_qualifying_count(hourly_rows)
        if not QUALIFYING_SETTLEMENT_COUNT <= trailing <= RESTORATION_PERIOD_ORDINAL:
            raise _PolicyMismatch("hourly restoration does not meet the exact rate threshold")
        qualifying_counts[trailing] += 1
        completed_count += 1
        explained_changes += 1
        if alignment_interval != default_interval:
            explained_changes += 1
        previous_run_end = end
    if explained_changes != change_count:
        raise _PolicyMismatch("not every observed interval change is policy-explained")
    return _SeriesPolicyResult(
        completed_hourly_episode_count=completed_count,
        explained_interval_change_count=explained_changes,
        hourly_episode_count=len(hourly_runs),
        open_hourly_episode_count=open_count,
        open_nonqualifying_hourly_episode_count=open_nonqualifying_count,
        qualifying_count_histogram=tuple(sorted(qualifying_counts.items())),
        unexplained_interval_change_count=0,
    )


def _analyze_series(rows: Sequence[_Observation]) -> _SeriesPolicyResult:
    change_count = _interval_change_count(rows)
    try:
        return _analyze_series_strict(rows)
    except _PolicyMismatch:
        return _SeriesPolicyResult(
            completed_hourly_episode_count=0,
            explained_interval_change_count=0,
            hourly_episode_count=0,
            open_hourly_episode_count=0,
            open_nonqualifying_hourly_episode_count=0,
            qualifying_count_histogram=(),
            unexplained_interval_change_count=change_count,
        )


def _validate_audit_series(
    audit: Mapping[str, object],
    observations: Mapping[int, tuple[_Observation, ...]],
) -> tuple[int, int, list[_SeriesPolicyResult]]:
    raw_series = _array(audit, "series")
    if not raw_series or any(not isinstance(item, dict) for item in raw_series):
        raise FundingCadencePolicyError("funding coverage audit series inventory is invalid")
    series = tuple(cast(dict[str, object], item) for item in raw_series)
    instrument_ids = tuple(_nonnegative_integer(item, "instrument_id") for item in series)
    if (
        len(instrument_ids) != len(set(instrument_ids))
        or set(instrument_ids) != set(observations)
        or any(instrument_id == 0 for instrument_id in instrument_ids)
    ):
        raise FundingCadencePolicyError("funding audit and Landing instrument sets differ")

    affected_count = 0
    results: list[_SeriesPolicyResult] = []
    audit_change_count = 0
    for item, instrument_id in zip(series, instrument_ids, strict=True):
        rows = observations[instrument_id]
        expected_rows = _nonnegative_integer(item, "observed_event_count")
        expected_changes = _nonnegative_integer(item, "interval_change_count")
        if len(rows) != expected_rows or _interval_change_count(rows) != expected_changes:
            raise FundingCadencePolicyError("funding audit series no longer matches Landing rows")
        raw_histogram = _array(item, "interval_histogram")
        expected_histogram = sorted(
            (
                _nonnegative_integer(cast(dict[str, object], entry), "interval_minutes"),
                _nonnegative_integer(cast(dict[str, object], entry), "event_count"),
            )
            for entry in raw_histogram
            if isinstance(entry, dict)
        )
        observed_histogram = sorted(Counter(row.interval_minutes for row in rows).items())
        if (
            len(expected_histogram) != len(raw_histogram)
            or expected_histogram != observed_histogram
        ):
            raise FundingCadencePolicyError("funding audit interval histogram does not verify")
        audit_change_count += expected_changes
        if expected_changes:
            affected_count += 1
            results.append(_analyze_series(rows))

    quality = _mapping(audit, "quality")
    if _nonnegative_integer(quality, "interval_change_count") != audit_change_count:
        raise FundingCadencePolicyError("funding audit aggregate interval changes do not verify")
    return len(series), affected_count, results


def build_funding_cadence_policy_evidence(
    client: OfficialPolicyClient,
    *,
    coverage_audit_paths: Sequence[Path],
    funding_job_roots: Sequence[Path],
    generated_at_utc: str,
    software_identity: str,
) -> dict[str, object]:
    """Verify dated policy against receipt-bound funding anomalies without exposing raw rows."""

    if SOFTWARE_IDENTITY_RE.fullmatch(software_identity) is None:
        raise FundingCadencePolicyError("software identity must be git:<40 hex>")
    if (
        not coverage_audit_paths
        or len(coverage_audit_paths) != len(funding_job_roots)
        or len(coverage_audit_paths) > 32
    ):
        raise FundingCadencePolicyError(
            "coverage audits and funding jobs must be paired 1..32 inputs"
        )

    page, normalized_policy_text = _verify_policy_page(client)
    source_bindings: list[dict[str, object]] = []
    total_series_count = 0
    affected_series_count = 0
    results: list[_SeriesPolicyResult] = []
    seen_audits: set[str] = set()
    seen_manifests: set[str] = set()
    for audit_path, job_root in zip(coverage_audit_paths, funding_job_roots, strict=True):
        audit, audit_artifact_sha256 = _verify_coverage_audit(audit_path)
        completed, batch = load_verified_completed_funding_batch(job_root.resolve())
        bindings = _mapping(audit, "bindings")
        if bindings.get("funding_manifest_sha256") != completed.manifest_sha256:
            raise FundingCadencePolicyError("funding audit does not bind the supplied Landing job")
        if audit_artifact_sha256 in seen_audits or completed.manifest_sha256 in seen_manifests:
            raise FundingCadencePolicyError("funding cadence inputs must be unique")
        seen_audits.add(audit_artifact_sha256)
        seen_manifests.add(completed.manifest_sha256)
        observations = _observations_by_instrument(batch.table)
        series_count, affected_count, source_results = _validate_audit_series(
            audit,
            observations,
        )
        total_series_count += series_count
        affected_series_count += affected_count
        results.extend(source_results)
        source_bindings.append(
            {
                "coverage_audit_artifact_sha256": audit_artifact_sha256,
                "coverage_audit_content_sha256": audit["content_sha256"],
                "funding_manifest_sha256": completed.manifest_sha256,
                "interval_change_count": _nonnegative_integer(
                    _mapping(audit, "quality"), "interval_change_count"
                ),
            }
        )

    source_bindings.sort(key=lambda item: cast(str, item["coverage_audit_artifact_sha256"]))
    explained_changes = sum(item.explained_interval_change_count for item in results)
    unexplained_changes = sum(item.unexplained_interval_change_count for item in results)
    observed_changes = explained_changes + unexplained_changes
    completed_episodes = sum(item.completed_hourly_episode_count for item in results)
    open_episodes = sum(item.open_hourly_episode_count for item in results)
    open_nonqualifying = sum(item.open_nonqualifying_hourly_episode_count for item in results)
    qualifying_histogram: Counter[int] = Counter()
    for item in results:
        qualifying_histogram.update(dict(item.qualifying_count_histogram))

    status = (
        "verified-official-funding-cadence-policy-consistency"
        if observed_changes > 0
        and unexplained_changes == 0
        and affected_series_count == len(results)
        else "blocked-unexplained-funding-cadence"
    )
    payload: dict[str, object] = {
        "assurances": {
            "canonical_market_data_mutated": False,
            "coverage_audit_receipts_verified": True,
            "funding_landing_receipts_verified": True,
            "market_data_network_request_performed": False,
            "official_announcement_response_count": 1,
            "private_endpoint_called": False,
        },
        "bindings": {
            "official_article_response_sha256": sha256(page.body).hexdigest(),
            "official_policy_marker_sha256": canonical_sha256(
                {"normalized_markers": POLICY_MARKERS}
            ),
            "software_identity": software_identity,
            "sources": source_bindings,
        },
        "content_sha256": "",
        "contract": EVIDENCE_CONTRACT,
        "generated_at_utc": _utc_text(generated_at_utc),
        "limitations": [
            "The dated policy is applied only to retained settlements at or after its effective "
            "time; it does not explain earlier cadence changes.",
            "This evidence verifies consistency with the official mechanism, not an independent "
            "venue settlement ledger.",
            "The immutable blocked coverage audits are not rewritten or reclassified.",
            "This evidence does not remove a Gate 2 blocker, accept Gate 2, authorize Phase 3, "
            "or permit private/live operations without a separate owner/governance decision.",
        ],
        "official_policy": {
            "announcement_date": "2026-02-23",
            "documented_default_interval_minutes": list(DEFAULT_INTERVALS_MINUTES),
            "dynamic_adjustment_without_further_notice": True,
            "effective_at_ms": POLICY_EFFECTIVE_AT_MS,
            "hourly_interval_minutes": HOURLY_INTERVAL_MINUTES,
            "qualifying_rate_threshold_decimal": format(QUALIFYING_RATE_THRESHOLD, "f"),
            "qualifying_settlement_count": QUALIFYING_SETTLEMENT_COUNT,
            "restoration_period_ordinal": RESTORATION_PERIOD_ORDINAL,
            "source_url": POLICY_URL,
        },
        "quality": {
            "affected_series_count": affected_series_count,
            "completed_hourly_episode_count": completed_episodes,
            "coverage_audit_count": len(source_bindings),
            "explained_interval_change_count": explained_changes,
            "hourly_episode_count": sum(item.hourly_episode_count for item in results),
            "observed_interval_change_count": observed_changes,
            "open_hourly_episode_count": open_episodes,
            "open_nonqualifying_hourly_episode_count": open_nonqualifying,
            "policy_consistent_series_count": sum(
                item.unexplained_interval_change_count == 0 for item in results
            ),
            "qualifying_settlement_count_histogram": [
                {"episode_count": count, "qualifying_settlement_count": qualifying_count}
                for qualifying_count, count in sorted(qualifying_histogram.items())
            ],
            "series_count": total_series_count,
            "unexplained_interval_change_count": unexplained_changes,
        },
        "source_policy": {
            "authentication": "none",
            "exact_url_only": True,
            "maximum_response_bytes": MAX_POLICY_RESPONSE_BYTES,
            "normalized_policy_text_sha256": sha256(
                normalized_policy_text.encode("utf-8")
            ).hexdigest(),
            "private_endpoints_called": False,
            "transport_max_attempts": 1,
        },
        "status": status,
        "storage_policy": {
            "account_data_included": False,
            "announcement_body_included": False,
            "credentials_included": False,
            "funding_rates_included": False,
            "instrument_identifiers_included": False,
            "observed_settlement_timestamps_included": False,
            "runtime_paths_included": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    return payload
