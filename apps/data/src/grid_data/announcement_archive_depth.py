"""Bounded official-announcement archive depth evidence for lifecycle review."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Final, Protocol, cast

from grid_bybit_public import ANNOUNCEMENT_TYPES, AnnouncementPage
from grid_contracts.canonical import canonical_sha256

from grid_data.instrument_registry import load_verified_instrument_registry

EVIDENCE_CONTRACT: Final = "grid.phase2-announcement-archive-depth/v1"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
PAGE_LIMIT: Final = 20
LOCALE: Final = "en-US"
UINT32_MAX: Final = (1 << 32) - 1
LIFECYCLE_DEPTH_TYPES: Final = frozenset(("new_crypto", "delistings"))


class AnnouncementArchiveDepthError(ValueError):
    """The official source cannot support a deterministic bounded depth assessment."""


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
        raise AnnouncementArchiveDepthError("generated timestamp must use UTC Z")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise AnnouncementArchiveDepthError("generated timestamp is invalid") from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise AnnouncementArchiveDepthError("generated timestamp must resolve to UTC")
    return value


def _page_result_sha256(page: AnnouncementPage) -> str:
    return canonical_sha256({"list": page.items, "total": page.total})


def _expected_item_count(total: int, page: int) -> int:
    first_index = (page - 1) * PAGE_LIMIT
    return max(0, min(PAGE_LIMIT, total - first_index))


def _integer_times(page: AnnouncementPage, field: str) -> tuple[int, ...]:
    values = tuple(item[field] for item in page.items)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise AnnouncementArchiveDepthError(f"validated announcement page lost {field} times")
    return cast(tuple[int, ...], values)


def _optional_integer_times(page: AnnouncementPage, field: str) -> tuple[int, ...]:
    values = tuple(item.get(field) for item in page.items)
    if any(
        value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0)
        for value in values
    ):
        raise AnnouncementArchiveDepthError(
            f"validated announcement page has invalid optional {field} times"
        )
    return tuple(cast(int, value) for value in values if value is not None)


def _adjacent_inversion_count(values: Sequence[int]) -> int:
    return sum(current > previous for previous, current in pairwise(values))


def build_announcement_archive_depth_evidence(
    client: AnnouncementClient,
    *,
    instrument_registry_path: Path,
    instrument_ids: Sequence[int],
    generated_at_utc: str,
    software_identity: str,
) -> dict[str, object]:
    """Probe only the first/last page per documented type and publish no announcement body."""

    if SOFTWARE_IDENTITY_RE.fullmatch(software_identity) is None:
        raise AnnouncementArchiveDepthError("software identity must be git:<40 hex>")
    if client.transport_max_attempts != 1:
        raise AnnouncementArchiveDepthError(
            "announcement depth requires exactly one transport attempt"
        )
    selected_ids = tuple(sorted(instrument_ids))
    if (
        not 1 <= len(selected_ids) <= 700
        or len(selected_ids) != len(set(selected_ids))
        or any(
            isinstance(instrument_id, bool)
            or not isinstance(instrument_id, int)
            or not 1 <= instrument_id <= UINT32_MAX
            for instrument_id in selected_ids
        )
    ):
        raise AnnouncementArchiveDepthError(
            "instrument IDs must be 1..700 unique positive UInt32 values"
        )

    registry = load_verified_instrument_registry(instrument_registry_path)
    records_by_id = {item.instrument_id: item for item in registry.snapshots}
    if any(instrument_id not in records_by_id for instrument_id in selected_ids):
        raise AnnouncementArchiveDepthError("selected instrument is absent from the registry")
    selected = tuple(records_by_id[instrument_id] for instrument_id in selected_ids)
    if any(
        item.category != "linear"
        or item.contract_type != "LinearPerpetual"
        or item.quote_coin != "USDT"
        or item.settle_coin != "USDT"
        for item in selected
    ):
        raise AnnouncementArchiveDepthError("selected instruments must be USDT linear perpetuals")

    response_count = 0
    reused_page_count = 0
    type_probes: list[dict[str, object]] = []
    for announcement_type in ANNOUNCEMENT_TYPES:
        first = client.announcement_page(
            announcement_type=announcement_type,
            page=1,
            locale=LOCALE,
            limit=PAGE_LIMIT,
        )
        response_count += 1
        if first.total < 1 or len(first.items) != _expected_item_count(first.total, 1):
            raise AnnouncementArchiveDepthError(
                f"announcement type {announcement_type} has no complete first page"
            )
        last_page_number = (first.total + PAGE_LIMIT - 1) // PAGE_LIMIT
        if last_page_number == 1:
            last = first
            reused_page_count += 1
        else:
            last = client.announcement_page(
                announcement_type=announcement_type,
                page=last_page_number,
                locale=LOCALE,
                limit=PAGE_LIMIT,
            )
            response_count += 1
        if (
            last.total != first.total
            or last.page != last_page_number
            or last.announcement_type != announcement_type
            or len(last.items) != _expected_item_count(last.total, last_page_number)
        ):
            raise AnnouncementArchiveDepthError(
                f"announcement type {announcement_type} changed during bounded probing"
            )
        first_date_times = _integer_times(first, "dateTimestamp")
        last_date_times = _integer_times(last, "dateTimestamp")
        first_publish_times = _optional_integer_times(first, "publishTime")
        last_publish_times = _optional_integer_times(last, "publishTime")
        latest_date_timestamp_ms = max(first_date_times)
        oldest_date_timestamp_ms = min(last_date_times)
        latest_publish_time_ms = max(first_publish_times) if first_publish_times else None
        oldest_publish_time_ms = min(last_publish_times) if last_publish_times else None
        if oldest_date_timestamp_ms > latest_date_timestamp_ms:
            raise AnnouncementArchiveDepthError(
                f"announcement type {announcement_type} has inverted source bounds"
            )
        first_date_inversion_count = _adjacent_inversion_count(first_date_times)
        last_date_inversion_count = _adjacent_inversion_count(last_date_times)
        cross_page_date_order_consistent = last_page_number == 1 or min(first_date_times) >= max(
            last_date_times
        )
        declared_page_date_order_consistent = (
            first_date_inversion_count == 0
            and last_date_inversion_count == 0
            and cross_page_date_order_consistent
        )
        lifecycle_depth_type = announcement_type in LIFECYCLE_DEPTH_TYPES
        if lifecycle_depth_type and not declared_page_date_order_consistent:
            raise AnnouncementArchiveDepthError(
                f"lifecycle announcement type {announcement_type} has unordered bounds"
            )
        type_probes.append(
            {
                "announcement_type": announcement_type,
                "declared_page_date_order_consistent": declared_page_date_order_consistent,
                "first_page_adjacent_date_inversion_count": first_date_inversion_count,
                "first_page_item_count": len(first.items),
                "first_page_publish_time_present_count": len(first_publish_times),
                "first_page_result_sha256": _page_result_sha256(first),
                "last_page_adjacent_date_inversion_count": last_date_inversion_count,
                "last_page_item_count": len(last.items),
                "last_page_number": last_page_number,
                "last_page_publish_time_present_count": len(last_publish_times),
                "last_page_result_sha256": _page_result_sha256(last),
                "latest_date_timestamp_ms": latest_date_timestamp_ms,
                "latest_publish_time_ms": latest_publish_time_ms,
                "lifecycle_depth_type": lifecycle_depth_type,
                "oldest_date_timestamp_ms": oldest_date_timestamp_ms,
                "oldest_publish_time_ms": oldest_publish_time_ms,
                "total_announcements": first.total,
            }
        )

    by_type = {str(item["announcement_type"]): item for item in type_probes}
    new_crypto_start = cast(int, by_type["new_crypto"]["oldest_date_timestamp_ms"])
    delistings_start = cast(int, by_type["delistings"]["oldest_date_timestamp_ms"])
    global_start = min(cast(int, item["oldest_date_timestamp_ms"]) for item in type_probes)
    launch_times = tuple(item.launch_time_ms for item in selected)
    launch_before_listing_archive_count = sum(value < new_crypto_start for value in launch_times)
    archive_covers_all = launch_before_listing_archive_count == 0
    blockers = ["archive-depth-does-not-prove-instrument-lifecycle"]
    if not archive_covers_all:
        blockers.append("official-new-listing-declared-last-page-starts-after-selected-launch")
    blockers.sort()

    registry_content_sha256 = registry.payload.get("content_sha256")
    if not isinstance(registry_content_sha256, str):
        raise AnnouncementArchiveDepthError("registry content binding is unavailable")
    payload: dict[str, object] = {
        "archive_depth": {
            "all_selected_registry_launches_within_new_listing_archive": archive_covers_all,
            "delistings_declared_last_page_min_date_timestamp_ms": delistings_start,
            "documented_types_declared_last_page_min_date_timestamp_ms": global_start,
            "new_crypto_declared_last_page_min_date_timestamp_ms": new_crypto_start,
            "selected_launch_before_new_listing_archive_count": (
                launch_before_listing_archive_count
            ),
            "selected_registry_launch_max_ms": max(launch_times),
            "selected_registry_launch_min_ms": min(launch_times),
        },
        "bindings": {
            "instrument_registry_artifact_sha256": registry.artifact_sha256,
            "instrument_registry_content_sha256": registry_content_sha256,
            "selected_instrument_set_sha256": canonical_sha256({"instrument_ids": selected_ids}),
        },
        "blocker_codes": blockers,
        "evidence_schema": EVIDENCE_CONTRACT,
        "generated_at_utc": _utc_text(generated_at_utc),
        "limitations": [
            "Archive depth does not prove that any announcement belongs to a selected instrument.",
            "Current registry launchTime remains ex-post lifecycle evidence, not a historical "
            "point-in-time strategy feature.",
            "No listing, delisting, suspension, or source absence is inferred from candles.",
            "This diagnostic does not close Gate 2 or authorize Phase 3, private, or live work.",
        ],
        "process": {
            "documented_announcement_type_count": len(ANNOUNCEMENT_TYPES),
            "first_and_last_page_only": True,
            "lifecycle_depth_type_count": len(LIFECYCLE_DEPTH_TYPES),
            "maximum_response_count": 2 * len(ANNOUNCEMENT_TYPES),
            "response_count": response_count,
            "reused_single_page_count": reused_page_count,
            "software_identity": software_identity,
        },
        "scope": {
            "selected_instrument_count": len(selected),
        },
        "source_policy": {
            "authentication": "none",
            "base_url": "https://api.bybit.com",
            "endpoint": "/v5/announcements/index",
            "locale": LOCALE,
            "legacy_publish_time_may_be_absent": True,
            "lifecycle_depth_types": sorted(LIFECYCLE_DEPTH_TYPES),
            "page_limit": PAGE_LIMIT,
            "private_endpoints_called": False,
            "query_policy": "first-and-declared-last-page-per-documented-type-v1",
            "raw_announcement_bodies_persisted": False,
            "transport_max_attempts": 1,
        },
        "status": (
            "source-depth-compatible-needs-record-matching"
            if archive_covers_all
            else "blocked-insufficient-official-announcement-history"
        ),
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_announcement_text_or_urls": False,
            "evidence_contains_credentials": False,
            "evidence_contains_instrument_identifiers": False,
            "evidence_contains_market_values": False,
            "evidence_contains_runtime_paths": False,
        },
        "type_probes": type_probes,
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload
