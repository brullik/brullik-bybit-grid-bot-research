"""Receipt-bound official lifecycle record matching for a selected candle universe."""

from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, Final, Protocol, cast

from grid_bybit_public import AnnouncementPage
from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file
from grid_contracts.market import InstrumentSnapshot

from grid_data.evidence import verify_evidence
from grid_data.instrument_registry import load_verified_instrument_registry

EVIDENCE_CONTRACT: Final = "grid.phase2-announcement-lifecycle-coverage/v1"
LEGACY_EVIDENCE_CONTRACT: Final = "grid.phase2-legacy-listing-event-evidence/v1"
LEGACY_EVIDENCE_STATUS: Final = "verified-four-exact-and-one-bounded-legacy-listing-event"
CAMPAIGN_REQUEST_CONTRACT: Final = "grid.public-history-campaign-request/v1"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
SYMBOL_RE: Final = re.compile(r"^[A-Z0-9]{2,40}$")
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
PAGE_LIMIT: Final = 20
LOCALE: Final = "en-US"
DAY_MS: Final = 86_400_000
UINT32_MAX: Final = (1 << 32) - 1
MAX_CAMPAIGN_REQUESTS: Final = 16
MAX_SELECTED_INSTRUMENTS: Final = 2048
LIFECYCLE_TYPES: Final = ("new_crypto", "delistings")
_CAMPAIGN_REQUEST_KEYS: Final = frozenset(
    {
        "campaign_id",
        "contract",
        "end_ms",
        "funding_page_limit",
        "funding_page_span_minutes",
        "history_page_limit",
        "kinds",
        "lifecycle_policy",
        "max_attempts",
        "start_ms",
        "symbols",
        "target_rps",
        "workers",
    }
)


class AnnouncementLifecycleCoverageError(ValueError):
    """The official archive cannot produce a deterministic record-matching result."""


class AnnouncementClient(Protocol):
    @property
    def transport_max_attempts(self) -> int | None: ...

    def announcement_page(
        self,
        *,
        announcement_type: str,
        page: int,
        locale: str = LOCALE,
        limit: int = PAGE_LIMIT,
    ) -> AnnouncementPage: ...


def _utc_text(value: str) -> str:
    if not value.endswith("Z"):
        raise AnnouncementLifecycleCoverageError("generated timestamp must use UTC Z")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise AnnouncementLifecycleCoverageError("generated timestamp is invalid") from error
    if parsed.utcoffset() != UTC.utcoffset(parsed):
        raise AnnouncementLifecycleCoverageError("generated timestamp must resolve to UTC")
    return value


def _load_json_object(path: Path, *, label: str) -> tuple[Path, dict[str, Any]]:
    if path.is_symlink():
        raise AnnouncementLifecycleCoverageError(f"{label} cannot be a symlink")
    resolved = path.resolve()
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AnnouncementLifecycleCoverageError(f"{label} is not readable JSON") from error
    if not isinstance(raw, dict):
        raise AnnouncementLifecycleCoverageError(f"{label} must be a JSON object")
    return resolved, cast(dict[str, Any], raw)


def _load_campaign_selection(
    path: Path,
    registry_by_symbol: Mapping[str, InstrumentSnapshot],
) -> tuple[Path, dict[str, Any], tuple[InstrumentSnapshot, ...]]:
    resolved, request = _load_json_object(path, label="campaign request")
    if set(request) - _CAMPAIGN_REQUEST_KEYS:
        raise AnnouncementLifecycleCoverageError("campaign request has unknown fields")
    if request.get("contract") != CAMPAIGN_REQUEST_CONTRACT:
        raise AnnouncementLifecycleCoverageError("campaign request contract is not v1")
    kinds = request.get("kinds")
    if not isinstance(kinds, list) or set(kinds) != {"trade", "mark"} or len(kinds) != 2:
        raise AnnouncementLifecycleCoverageError(
            "campaign request must select trade and mark exactly once"
        )
    symbols = request.get("symbols")
    if (
        not isinstance(symbols, list)
        or not 1 <= len(symbols) <= 700
        or len(symbols) != len(set(symbols))
        or any(
            not isinstance(symbol, str) or SYMBOL_RE.fullmatch(symbol) is None for symbol in symbols
        )
    ):
        raise AnnouncementLifecycleCoverageError(
            "campaign request symbols must be 1..700 unique uppercase identifiers"
        )
    selected: list[InstrumentSnapshot] = []
    for symbol in cast(list[str], symbols):
        instrument = registry_by_symbol.get(symbol)
        if instrument is None:
            raise AnnouncementLifecycleCoverageError("campaign symbol is absent from registry")
        if (
            instrument.category != "linear"
            or instrument.contract_type != "LinearPerpetual"
            or instrument.quote_coin != "USDT"
            or instrument.settle_coin != "USDT"
        ):
            raise AnnouncementLifecycleCoverageError(
                "campaign selection contains a non-USDT linear perpetual"
            )
        selected.append(instrument)
    selected.sort(key=lambda item: item.instrument_id)
    return resolved, request, tuple(selected)


def _mapping(parent: Mapping[str, Any], key: str, *, label: str) -> Mapping[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise AnnouncementLifecycleCoverageError(f"{label}.{key} must be an object")
    return cast(Mapping[str, Any], value)


def _integer(parent: Mapping[str, Any], key: str, *, label: str) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AnnouncementLifecycleCoverageError(f"{label}.{key} must be non-negative integer")
    return value


def _sha(parent: Mapping[str, Any], key: str, *, label: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise AnnouncementLifecycleCoverageError(f"{label}.{key} must be SHA-256")
    return value


def _load_legacy_evidence(
    path: Path,
    *,
    registry_artifact_sha256: str,
    registry_content_sha256: str,
    selected_ids: tuple[int, ...],
) -> tuple[dict[str, Any], dict[str, str]]:
    if not selected_ids or len(selected_ids) > 700 or len(selected_ids) != len(set(selected_ids)):
        raise AnnouncementLifecycleCoverageError("legacy instrument IDs must be unique")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= UINT32_MAX
        for value in selected_ids
    ):
        raise AnnouncementLifecycleCoverageError("legacy instrument ID is outside UInt32")
    resolved, payload = _load_json_object(path, label="legacy evidence")
    if not verify_evidence(resolved):
        raise AnnouncementLifecycleCoverageError("legacy evidence receipt does not verify")
    try:
        artifact_bytes = resolved.read_bytes()
    except OSError as error:
        raise AnnouncementLifecycleCoverageError("legacy evidence cannot be read") from error
    if artifact_bytes != canonical_json_bytes(payload) + b"\n":
        raise AnnouncementLifecycleCoverageError("legacy evidence is not canonical JSON plus LF")
    if payload.get("contract") != LEGACY_EVIDENCE_CONTRACT:
        raise AnnouncementLifecycleCoverageError("legacy evidence contract differs")
    if payload.get("status") != LEGACY_EVIDENCE_STATUS:
        raise AnnouncementLifecycleCoverageError("legacy evidence status differs")
    embedded = payload.get("content_sha256")
    hash_input = dict(payload)
    hash_input.pop("content_sha256", None)
    if embedded != canonical_sha256(hash_input):
        raise AnnouncementLifecycleCoverageError("legacy evidence content hash differs")
    bindings = _mapping(payload, "bindings", label="legacy evidence")
    if (
        bindings.get("instrument_registry_artifact_sha256") != registry_artifact_sha256
        or bindings.get("instrument_registry_content_sha256") != registry_content_sha256
        or bindings.get("selected_instrument_set_sha256")
        != canonical_sha256({"instrument_ids": selected_ids})
    ):
        raise AnnouncementLifecycleCoverageError(
            "legacy evidence registry/selection binding differs"
        )
    quality = _mapping(payload, "quality", label="legacy evidence")
    if _integer(quality, "selected_instrument_count", label="legacy evidence.quality") != len(
        selected_ids
    ):
        raise AnnouncementLifecycleCoverageError("legacy evidence selection count differs")
    return payload, {
        "artifact": resolved.name,
        "artifact_sha256": sha256_file(resolved),
        "content_sha256": cast(str, embedded),
        "contract": LEGACY_EVIDENCE_CONTRACT,
        "status": LEGACY_EVIDENCE_STATUS,
    }


def _expected_item_count(total: int, page: int) -> int:
    first_index = (page - 1) * PAGE_LIMIT
    return max(0, min(PAGE_LIMIT, total - first_index))


def _announcement_text(item: Mapping[str, Any]) -> str:
    title = item.get("title", "")
    description = item.get("description", "")
    tags = item.get("tags", [])
    url = item.get("url")
    if title is None:
        title = ""
    if description is None:
        description = ""
    if tags is None:
        tags = []
    if not isinstance(title, str):
        raise AnnouncementLifecycleCoverageError("announcement title is invalid")
    if not isinstance(description, str):
        raise AnnouncementLifecycleCoverageError("announcement description is invalid")
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise AnnouncementLifecycleCoverageError("announcement tags are invalid")
    if url is not None and (not isinstance(url, str) or not url):
        raise AnnouncementLifecycleCoverageError("announcement URL is invalid")
    if isinstance(url, str):
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "announcements.bybit.com":
            raise AnnouncementLifecycleCoverageError(
                "announcement URL is outside the official host"
            )
    return " ".join((title, description, *cast(list[str], tags))).upper()


def _matches_instrument_text(text: str, instrument: InstrumentSnapshot) -> bool:
    symbol = re.escape(instrument.symbol.upper())
    base = re.escape(instrument.base_coin.upper())
    pair = rf"(?<![A-Z0-9]){base}(?:[\s/_-]*USDT)(?![A-Z0-9])"
    symbol_match = re.search(rf"(?<![A-Z0-9]){symbol}(?![A-Z0-9])", text) is not None
    pair_match = re.search(pair, text) is not None
    derivative_scope = (
        "PERPETUAL" in text
        or "DERIVATIVE" in text
        or re.search(r"(?<![A-Z])CONTRACTS?(?![A-Z])", text) is not None
    )
    return (symbol_match or pair_match) and derivative_scope


def _read_archive_type(
    client: AnnouncementClient,
    announcement_type: str,
) -> tuple[tuple[Mapping[str, Any], ...], dict[str, object]]:
    first = client.announcement_page(
        announcement_type=announcement_type,
        page=1,
        locale=LOCALE,
        limit=PAGE_LIMIT,
    )
    if first.total < 1:
        raise AnnouncementLifecycleCoverageError("lifecycle announcement archive is empty")
    page_count = (first.total + PAGE_LIMIT - 1) // PAGE_LIMIT
    pages = [first]
    for page_number in range(2, page_count + 1):
        pages.append(
            client.announcement_page(
                announcement_type=announcement_type,
                page=page_number,
                locale=LOCALE,
                limit=PAGE_LIMIT,
            )
        )
    for page in pages:
        if (
            page.announcement_type != announcement_type
            or page.total != first.total
            or len(page.items) != _expected_item_count(first.total, page.page)
        ):
            raise AnnouncementLifecycleCoverageError(
                "announcement archive changed or returned an incomplete page"
            )
    items = tuple(item for page in pages for item in page.items)
    if len(items) != first.total:
        raise AnnouncementLifecycleCoverageError("announcement archive total did not reconcile")
    date_times = tuple(_integer(item, "dateTimestamp", label="announcement") for item in items)
    adjacent_date_inversion_count = sum(
        current > previous for previous, current in pairwise(date_times)
    )
    item_hashes: list[str] = []
    urls: list[str] = []
    blank_or_missing_description_count = 0
    blank_or_missing_title_count = 0
    missing_tags_count = 0
    missing_url_count = 0
    for item in items:
        _announcement_text(item)
        item_hashes.append(canonical_sha256(item))
        raw_url = item.get("url")
        if isinstance(raw_url, str):
            urls.append(raw_url)
        else:
            missing_url_count += 1
        title = item.get("title")
        description = item.get("description")
        blank_or_missing_title_count += int(not isinstance(title, str) or not title.strip())
        blank_or_missing_description_count += int(
            not isinstance(description, str) or not description.strip()
        )
        missing_tags_count += int(item.get("tags") is None)
    if len(item_hashes) != len(set(item_hashes)):
        raise AnnouncementLifecycleCoverageError("announcement archive repeats an exact item")
    if len(urls) != len(set(urls)):
        raise AnnouncementLifecycleCoverageError("announcement archive repeats a URL")
    return items, {
        "announcement_type": announcement_type,
        "adjacent_date_inversion_count": adjacent_date_inversion_count,
        "archive_result_sha256": canonical_sha256({"list": items, "total": first.total}),
        "blank_or_missing_description_count": blank_or_missing_description_count,
        "blank_or_missing_title_count": blank_or_missing_title_count,
        "item_count": len(items),
        "latest_date_timestamp_ms": max(date_times),
        "missing_tags_count": missing_tags_count,
        "missing_url_count": missing_url_count,
        "oldest_date_timestamp_ms": min(date_times),
        "page_count": page_count,
        "total_announcements": first.total,
    }


def _relation_summary(
    matches: Sequence[tuple[InstrumentSnapshot, Mapping[str, Any]]],
    *,
    registry_time: str,
) -> dict[str, int]:
    before = 0
    same = 0
    after = 0
    max_abs = 0
    for instrument, item in matches:
        event_day = _integer(item, "dateTimestamp", label="announcement") // DAY_MS
        reference_ms = (
            instrument.launch_time_ms
            if registry_time == "launch"
            else cast(int, instrument.delivery_time_ms)
        )
        delta = event_day - reference_ms // DAY_MS
        before += int(delta < 0)
        same += int(delta == 0)
        after += int(delta > 0)
        max_abs = max(max_abs, abs(delta))
    return {
        "announcement_after_registry_date_count": after,
        "announcement_before_registry_date_count": before,
        "maximum_absolute_utc_date_delta_days": max_abs,
        "same_utc_date_count": same,
    }


def _match_type(
    instruments: Sequence[InstrumentSnapshot],
    items: Sequence[Mapping[str, Any]],
    *,
    archive_oldest_ms: int,
    registry_time: str,
) -> dict[str, object]:
    texts = tuple(_announcement_text(item) for item in items)
    eligible: list[InstrumentSnapshot] = []
    outside = 0
    for instrument in instruments:
        reference = (
            instrument.launch_time_ms if registry_time == "launch" else instrument.delivery_time_ms
        )
        if reference is None:
            continue
        if reference < archive_oldest_ms:
            outside += 1
        else:
            eligible.append(instrument)
    unique: list[tuple[InstrumentSnapshot, Mapping[str, Any]]] = []
    unmatched = 0
    ambiguous = 0
    candidate_event_count = 0
    for instrument in eligible:
        candidates = tuple(
            item
            for item, text in zip(items, texts, strict=True)
            if _matches_instrument_text(text, instrument)
        )
        candidate_event_count += len(candidates)
        if not candidates:
            unmatched += 1
        elif len(candidates) == 1:
            unique.append((instrument, candidates[0]))
        else:
            ambiguous += 1
    return {
        "ambiguous_instrument_count": ambiguous,
        "candidate_event_count": candidate_event_count,
        "eligible_instrument_count": len(eligible),
        "outside_archive_instrument_count": outside,
        "registry_relation": _relation_summary(unique, registry_time=registry_time),
        "unique_match_instrument_count": len(unique),
        "unmatched_instrument_count": unmatched,
    }


def build_announcement_lifecycle_coverage_evidence(
    client: AnnouncementClient,
    *,
    instrument_registry_path: Path,
    campaign_request_paths: Sequence[Path],
    legacy_evidence_path: Path,
    legacy_instrument_ids: Sequence[int],
    generated_at_utc: str,
    software_identity: str,
) -> dict[str, object]:
    """Scan official lifecycle pages once and publish only sanitized match aggregates."""

    if SOFTWARE_IDENTITY_RE.fullmatch(software_identity) is None:
        raise AnnouncementLifecycleCoverageError("software identity must be git:<40 hex>")
    if client.transport_max_attempts != 1:
        raise AnnouncementLifecycleCoverageError(
            "announcement lifecycle coverage requires exactly one transport attempt"
        )
    registry = load_verified_instrument_registry(instrument_registry_path)
    registry_content_sha256 = registry.payload.get("content_sha256")
    if not isinstance(registry_content_sha256, str):
        raise AnnouncementLifecycleCoverageError("registry content binding is unavailable")
    if not 1 <= len(campaign_request_paths) <= MAX_CAMPAIGN_REQUESTS or len(
        {str(path.resolve()) for path in campaign_request_paths}
    ) != len(campaign_request_paths):
        raise AnnouncementLifecycleCoverageError("campaign requests must be 1..16 unique paths")
    selected_buffer: list[InstrumentSnapshot] = []
    selected_campaign_ids: set[int] = set()
    campaign_sources: list[dict[str, object]] = []
    for campaign_request_path in campaign_request_paths:
        request_path, request, campaign_selected = _load_campaign_selection(
            campaign_request_path, registry.by_symbol()
        )
        campaign_ids = {item.instrument_id for item in campaign_selected}
        if selected_campaign_ids & campaign_ids:
            raise AnnouncementLifecycleCoverageError("campaign request selections must be disjoint")
        selected_campaign_ids.update(campaign_ids)
        selected_buffer.extend(campaign_selected)
        campaign_sources.append(
            {
                "artifact_sha256": sha256_file(request_path),
                "content_sha256": canonical_sha256(request),
                "selected_instrument_count": len(campaign_selected),
            }
        )
    legacy_ids = tuple(sorted(legacy_instrument_ids))
    if selected_campaign_ids & set(legacy_ids):
        raise AnnouncementLifecycleCoverageError(
            "legacy selection must be disjoint from campaign requests"
        )
    registry_by_id = {item.instrument_id: item for item in registry.snapshots}
    if any(value not in registry_by_id for value in legacy_ids):
        raise AnnouncementLifecycleCoverageError("legacy selection is absent from registry")
    legacy_selected = tuple(registry_by_id[value] for value in legacy_ids)
    if any(
        item.category != "linear"
        or item.contract_type != "LinearPerpetual"
        or item.quote_coin != "USDT"
        or item.settle_coin != "USDT"
        for item in legacy_selected
    ):
        raise AnnouncementLifecycleCoverageError(
            "legacy selection contains a non-USDT linear perpetual"
        )
    selected_buffer.extend(legacy_selected)
    selected = tuple(sorted(selected_buffer, key=lambda item: item.instrument_id))
    if not 1 <= len(selected) <= MAX_SELECTED_INSTRUMENTS:
        raise AnnouncementLifecycleCoverageError("combined selection exceeds 2048 instruments")
    selected_ids = tuple(item.instrument_id for item in selected)
    legacy_payload, legacy_source = _load_legacy_evidence(
        legacy_evidence_path,
        registry_artifact_sha256=registry.artifact_sha256,
        registry_content_sha256=registry_content_sha256,
        selected_ids=legacy_ids,
    )

    archives: dict[str, tuple[Mapping[str, Any], ...]] = {}
    archive_summaries: list[dict[str, object]] = []
    for announcement_type in LIFECYCLE_TYPES:
        items, summary = _read_archive_type(client, announcement_type)
        archives[announcement_type] = items
        archive_summaries.append(summary)
    summaries_by_type = {cast(str, item["announcement_type"]): item for item in archive_summaries}
    listing_oldest = cast(int, summaries_by_type["new_crypto"]["oldest_date_timestamp_ms"])
    delisting_oldest = cast(int, summaries_by_type["delistings"]["oldest_date_timestamp_ms"])

    listing = _match_type(
        selected,
        archives["new_crypto"],
        archive_oldest_ms=listing_oldest,
        registry_time="launch",
    )
    delivered = tuple(item for item in selected if item.delivery_time_ms is not None)
    delisting = _match_type(
        delivered,
        archives["delistings"],
        archive_oldest_ms=delisting_oldest,
        registry_time="delivery",
    )
    if any(registry_by_id[value].launch_time_ms >= listing_oldest for value in legacy_ids):
        raise AnnouncementLifecycleCoverageError(
            "legacy evidence selection is not wholly before the API listing archive"
        )
    legacy_quality = _mapping(legacy_payload, "quality", label="legacy evidence")
    legacy_trade = _mapping(legacy_quality, "trade_first_candle", label="legacy evidence.quality")
    legacy_count = _integer(
        legacy_quality, "selected_instrument_count", label="legacy evidence.quality"
    )
    remaining_pre_archive = max(
        0, cast(int, listing["outside_archive_instrument_count"]) - legacy_count
    )

    blockers = ["historical-point-in-time-metadata-still-incomplete"]
    if remaining_pre_archive:
        blockers.append("remaining-pre-archive-listing-evidence-missing")
    if cast(int, listing["unmatched_instrument_count"]):
        blockers.append("eligible-listing-announcement-match-missing")
    if cast(int, listing["ambiguous_instrument_count"]):
        blockers.append("listing-announcement-match-ambiguous")
    if cast(int, delisting["unmatched_instrument_count"]):
        blockers.append("eligible-delisting-announcement-match-missing")
    if cast(int, delisting["ambiguous_instrument_count"]):
        blockers.append("delisting-announcement-match-ambiguous")
    blockers.sort()
    record_matching_complete = len(blockers) == 1

    status = (
        "verified-record-matched-official-lifecycle-evidence"
        if record_matching_complete
        else "verified-partial-official-lifecycle-evidence"
    )
    payload: dict[str, object] = {
        "archive_sources": archive_summaries,
        "bindings": {
            "campaign_request_sources": campaign_sources,
            "instrument_registry_artifact_sha256": registry.artifact_sha256,
            "instrument_registry_content_sha256": registry_content_sha256,
            "selected_instrument_set_sha256": canonical_sha256({"instrument_ids": selected_ids}),
        },
        "blocker_codes": blockers,
        "contract": EVIDENCE_CONTRACT,
        "generated_at_utc": _utc_text(generated_at_utc),
        "legacy_evidence": {
            "trade_event_day_match_count": _integer(
                legacy_trade,
                "event_day_match_count",
                label="legacy evidence.quality.trade_first_candle",
            ),
            "trade_first_candle_before_event_day_count": _integer(
                legacy_trade,
                "first_candle_before_event_day_count",
                label="legacy evidence.quality.trade_first_candle",
            ),
            "remaining_pre_archive_listing_instrument_count": remaining_pre_archive,
            "selected_instrument_count": legacy_count,
            "source": legacy_source,
        },
        "limitations": [
            "Record matching covers only the official API archive and one separately verified "
            "legacy selected set; it does not invent events before either source.",
            "Announcement text is processed only in memory and is absent from the artifact.",
            "Current registry lifecycle fields remain ex-post data-quality evidence and cannot "
            "be exposed to historical strategy decisions.",
            "A matched listing or delisting does not reconstruct historical tick, quantity, fee, "
            "risk, suspension, or status metadata.",
            "This evidence does not remove a blocker, accept an absence reason, close Gate 2, "
            "authorize Phase 3, or enable private/live execution.",
        ],
        "matching": {
            "delisting": delisting,
            "listing": listing,
            "record_matching_complete": record_matching_complete,
        },
        "process": {
            "announcement_text_persisted": False,
            "lifecycle_type_count": len(LIFECYCLE_TYPES),
            "market_data_request_count": 0,
            "private_endpoint_request_count": 0,
            "response_count": sum(cast(int, item["page_count"]) for item in archive_summaries),
            "software_identity": software_identity,
            "transport_max_attempts": 1,
        },
        "scope": {
            "campaign_request_count": len(campaign_sources),
            "closed_instrument_count": sum(item.status == "Closed" for item in selected),
            "delivered_instrument_count": len(delivered),
            "prelaunch_instrument_count": sum(item.status == "PreLaunch" for item in selected),
            "selected_instrument_count": len(selected),
            "trading_instrument_count": sum(item.status == "Trading" for item in selected),
        },
        "source_policy": {
            "authentication": "none",
            "base_url": "https://api.bybit.com",
            "endpoint": "/v5/announcements/index",
            "lifecycle_types": list(LIFECYCLE_TYPES),
            "locale": LOCALE,
            "page_limit": PAGE_LIMIT,
            "query_policy": "every-declared-page-once-per-lifecycle-type-v1",
            "raw_announcement_bodies_persisted": False,
        },
        "status": status,
        "storage_policy": {
            "account_data_included": False,
            "announcement_text_or_urls_included": False,
            "credentials_included": False,
            "instrument_identities_included": False,
            "market_values_included": False,
            "runtime_paths_included": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload
