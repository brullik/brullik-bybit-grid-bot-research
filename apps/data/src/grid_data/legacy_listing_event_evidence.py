"""Receipt-bound legacy listing-event evidence from exact official Bybit posts."""

from __future__ import annotations

import json
import re
from calendar import timegm
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from typing import Final, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file

from grid_data.history_campaign_publication import (
    verify_completed_history_campaign_publication,
)
from grid_data.instrument_registry import load_verified_instrument_registry

EVIDENCE_CONTRACT: Final = "grid.phase2-legacy-listing-event-evidence/v1"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
MAX_RESPONSE_BYTES: Final = 1024 * 1024
SELECTED_INSTRUMENT_COUNT: Final = 5
UINT32_MAX: Final = (1 << 32) - 1


@dataclass(frozen=True, slots=True)
class OfficialListingDocument:
    source_url: str
    fetch_url: str
    data_post: str
    expected_published_at_utc: str
    expected_selected_instrument_count: int
    required_markers: tuple[str, ...]


OFFICIAL_DOCUMENTS: Final = (
    OfficialListingDocument(
        source_url="https://t.me/Bybit_Announcements/72",
        fetch_url="https://t.me/s/Bybit_Announcements?before=73",
        data_post="Bybit_Announcements/72",
        expected_published_at_utc="2020-03-25T16:03:10+00:00",
        expected_selected_instrument_count=1,
        required_markers=("USDT Perpetual Contracts", "Now Live", "starting today"),
    ),
    OfficialListingDocument(
        source_url="https://t.me/Bybit_Announcements/312",
        fetch_url="https://t.me/s/Bybit_Announcements?before=313",
        data_post="Bybit_Announcements/312",
        expected_published_at_utc="2020-10-21T10:44:58+00:00",
        expected_selected_instrument_count=3,
        required_markers=("4 new", "now live", "LINK", "XTZ", "LTC"),
    ),
    OfficialListingDocument(
        source_url="https://t.me/Bybit_Announcements/347",
        fetch_url="https://t.me/s/Bybit_Announcements?before=348",
        data_post="Bybit_Announcements/347",
        expected_published_at_utc="2020-12-16T06:55:34+00:00",
        expected_selected_instrument_count=1,
        required_markers=("BCH", "now available for trading"),
    ),
)


class LegacyListingEventEvidenceError(ValueError):
    """Official posts and verified canonical lineage cannot support the claim."""


@dataclass(frozen=True, slots=True)
class OfficialListingPage:
    body: bytes
    content_type: str
    final_url: str
    status_code: int


class OfficialListingClient(Protocol):
    @property
    def transport_max_attempts(self) -> int: ...

    def fetch_document(self, document: OfficialListingDocument) -> OfficialListingPage: ...


class UrllibOfficialListingClient:
    """One-attempt, credential-free reader for the three exact official posts."""

    transport_max_attempts: Final = 1

    def fetch_document(self, document: OfficialListingDocument) -> OfficialListingPage:
        request = Request(
            document.fetch_url,
            headers={
                "Accept": "text/html; charset=utf-8",
                "Accept-Encoding": "identity",
                "User-Agent": "grid-data-legacy-listing-event-evidence/1",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
                status_code = response.getcode()
                final_url = response.geturl()
                content_type = response.headers.get_content_type()
        except (HTTPError, URLError, OSError) as error:
            raise LegacyListingEventEvidenceError(
                "official legacy listing document request failed"
            ) from error
        page = OfficialListingPage(
            body=body,
            content_type=content_type,
            final_url=final_url,
            status_code=status_code,
        )
        _validate_page_response(page, document)
        return page


class _TelegramPostParser(HTMLParser):
    def __init__(self, target_data_post: str) -> None:
        super().__init__(convert_charrefs=True)
        self._target_data_post = target_data_post
        self._captured_div_depth = 0
        self.fragments: list[str] = []
        self.datetimes: list[str] = []
        self.match_count = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = dict(attrs)
        if tag == "div" and values.get("data-post") == self._target_data_post:
            if self._captured_div_depth != 0:
                raise LegacyListingEventEvidenceError("official post HTML has nested target posts")
            self._captured_div_depth = 1
            self.match_count += 1
            return
        if self._captured_div_depth == 0:
            return
        if tag == "div":
            self._captured_div_depth += 1
        if tag == "time":
            value = values.get("datetime")
            if value is not None:
                self.datetimes.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._captured_div_depth > 0:
            self._captured_div_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._captured_div_depth > 0:
            self.fragments.append(data)


def _validate_page_response(
    page: OfficialListingPage,
    document: OfficialListingDocument,
) -> None:
    if (
        page.status_code != 200
        or page.final_url != document.fetch_url
        or page.content_type != "text/html"
        or not page.body
        or len(page.body) > MAX_RESPONSE_BYTES
    ):
        raise LegacyListingEventEvidenceError(
            "official legacy listing document response is invalid"
        )


def _parse_utc(value: str, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise LegacyListingEventEvidenceError(f"{label} is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise LegacyListingEventEvidenceError(f"{label} must resolve to UTC")
    return parsed


def _timestamp_ms(value: datetime) -> int:
    return timegm(value.utctimetuple()) * 1000 + value.microsecond // 1000


def _parse_document(
    page: OfficialListingPage,
    document: OfficialListingDocument,
) -> tuple[int, str]:
    _validate_page_response(page, document)
    try:
        source = page.body.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise LegacyListingEventEvidenceError(
            "official legacy listing document is not UTF-8"
        ) from error
    parser = _TelegramPostParser(document.data_post)
    try:
        parser.feed(source)
        parser.close()
    except ValueError as error:
        raise LegacyListingEventEvidenceError(
            "official legacy listing document HTML is invalid"
        ) from error
    if parser.match_count != 1 or len(parser.datetimes) != 1:
        raise LegacyListingEventEvidenceError(
            "official legacy listing document target is missing or ambiguous"
        )
    text = " ".join(" ".join(parser.fragments).split())
    if not text or any(
        marker.casefold() not in text.casefold() for marker in document.required_markers
    ):
        raise LegacyListingEventEvidenceError(
            "official legacy listing document statements do not verify"
        )
    observed = _parse_utc(parser.datetimes[0], label="official post timestamp")
    expected = _parse_utc(
        document.expected_published_at_utc,
        label="expected official post timestamp",
    )
    if observed != expected:
        raise LegacyListingEventEvidenceError("official legacy listing document timestamp changed")
    return _timestamp_ms(observed), text


def _canonical_object(path: Path, *, label: str) -> dict[str, object]:
    try:
        data = path.read_bytes()
        value = json.loads(data)
    except (OSError, json.JSONDecodeError) as error:
        raise LegacyListingEventEvidenceError(f"cannot load {label}") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != data:
        raise LegacyListingEventEvidenceError(f"{label} is not canonical JSON")
    return cast(dict[str, object], value)


def _selected_ids(instrument_ids: Sequence[int]) -> tuple[int, ...]:
    selected = tuple(sorted(instrument_ids))
    if (
        len(selected) != SELECTED_INSTRUMENT_COUNT
        or len(selected) != len(set(selected))
        or any(
            isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= UINT32_MAX
            for value in selected
        )
    ):
        raise LegacyListingEventEvidenceError(
            "instrument IDs must be exactly five unique positive UInt32 values"
        )
    return selected


def _symbol_token(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


def _message_matches_instrument(text: str, *, symbol: str, base_coin: str) -> bool:
    if _symbol_token(symbol) in _symbol_token(text):
        return True
    base_pattern = rf"(?<![A-Z0-9]){re.escape(base_coin.upper())}(?![A-Z0-9])"
    return re.search(base_pattern, text.upper()) is not None


def _verified_first_times(
    *,
    source_plan: dict[str, object],
    published_datasets: Sequence[object],
    selected_symbols: frozenset[str],
) -> dict[tuple[str, str], int]:
    raw_jobs = source_plan.get("jobs")
    if not isinstance(raw_jobs, list) or len(raw_jobs) != len(published_datasets):
        raise LegacyListingEventEvidenceError("source campaign and publication inventories differ")
    observed_symbols: set[str] = set()
    observed_kinds: set[str] = set()
    first_times: dict[tuple[str, str], int] = {}
    for sequence, (raw_job, published) in enumerate(zip(raw_jobs, published_datasets, strict=True)):
        if not isinstance(raw_job, dict) or raw_job.get("sequence") != sequence:
            raise LegacyListingEventEvidenceError("source campaign jobs are not contiguous")
        kind = raw_job.get("kind")
        request = raw_job.get("request")
        if kind not in ("trade", "mark") or not isinstance(request, dict):
            raise LegacyListingEventEvidenceError("source campaign has an unsupported job")
        raw_series = request.get("series")
        if not isinstance(raw_series, list) or len(raw_series) != 1:
            raise LegacyListingEventEvidenceError(
                "legacy listing evidence requires one series per source job"
            )
        raw_item = raw_series[0]
        symbol = raw_item.get("symbol") if isinstance(raw_item, dict) else None
        if not isinstance(symbol, str) or symbol not in selected_symbols:
            raise LegacyListingEventEvidenceError(
                "source campaign symbol inventory differs from selection"
            )
        observed_symbols.add(symbol)
        observed_kinds.add(kind)
        manifest = getattr(published, "manifest", None)
        row_count = getattr(manifest, "row_count", None)
        min_time_ms = getattr(manifest, "min_time_ms", None)
        max_time_ms = getattr(manifest, "max_time_ms", None)
        if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count < 0:
            raise LegacyListingEventEvidenceError("published dataset row count is invalid")
        if row_count == 0:
            if min_time_ms is not None or max_time_ms is not None:
                raise LegacyListingEventEvidenceError(
                    "empty published dataset has nonempty time bounds"
                )
            continue
        if (
            isinstance(min_time_ms, bool)
            or not isinstance(min_time_ms, int)
            or isinstance(max_time_ms, bool)
            or not isinstance(max_time_ms, int)
            or min_time_ms < 0
            or min_time_ms > max_time_ms
        ):
            raise LegacyListingEventEvidenceError(
                "nonempty published dataset has invalid time bounds"
            )
        key = (symbol, kind)
        first_times[key] = min(first_times.get(key, min_time_ms), min_time_ms)
    expected_pairs = {(symbol, kind) for symbol in selected_symbols for kind in ("trade", "mark")}
    if (
        observed_symbols != set(selected_symbols)
        or observed_kinds != {"trade", "mark"}
        or set(first_times) != expected_pairs
    ):
        raise LegacyListingEventEvidenceError(
            "source campaign does not contain complete nonempty trade and mark coverage"
        )
    return first_times


def _utc_day(value_ms: int) -> date:
    return datetime.fromtimestamp(value_ms // 1000, tz=UTC).date()


def _month_equal(left_ms: int, right_ms: int) -> bool:
    left = _utc_day(left_ms)
    right = _utc_day(right_ms)
    return (left.year, left.month) == (right.year, right.month)


def _kind_quality(
    kind: str,
    *,
    selected_symbols: frozenset[str],
    first_times: dict[tuple[str, str], int],
    event_times: dict[str, int],
) -> dict[str, int]:
    deltas = [
        (_utc_day(first_times[(symbol, kind)]) - _utc_day(event_times[symbol])).days
        for symbol in selected_symbols
    ]
    return {
        "event_day_match_count": sum(value == 0 for value in deltas),
        "event_month_match_count": sum(
            _month_equal(first_times[(symbol, kind)], event_times[symbol])
            for symbol in selected_symbols
        ),
        "first_candle_before_event_day_count": sum(value < 0 for value in deltas),
        "first_candle_after_event_day_count": sum(value > 0 for value in deltas),
        "maximum_pre_event_lead_days": max((-value for value in deltas if value < 0), default=0),
        "maximum_post_event_lag_days": max((value for value in deltas if value > 0), default=0),
    }


def build_legacy_listing_event_evidence(
    client: OfficialListingClient,
    *,
    instrument_registry_path: Path,
    instrument_ids: Sequence[int],
    publication_root: Path,
    source_campaign_root: Path,
    generated_at_utc: str,
    software_identity: str,
) -> dict[str, object]:
    """Verify exact official posts against fully verified oldest-five canonical bounds."""

    if SOFTWARE_IDENTITY_RE.fullmatch(software_identity) is None:
        raise LegacyListingEventEvidenceError("software identity must be git:<40 hex>")
    _parse_utc(generated_at_utc, label="generated timestamp")
    if not generated_at_utc.endswith("Z"):
        raise LegacyListingEventEvidenceError("generated timestamp must use UTC Z")
    if client.transport_max_attempts != 1:
        raise LegacyListingEventEvidenceError(
            "legacy listing evidence requires exactly one transport attempt"
        )

    selected_ids = _selected_ids(instrument_ids)
    registry = load_verified_instrument_registry(instrument_registry_path)
    records_by_id = {item.instrument_id: item for item in registry.snapshots}
    if any(value not in records_by_id for value in selected_ids):
        raise LegacyListingEventEvidenceError("selected instrument is absent from the registry")
    selected = tuple(records_by_id[value] for value in selected_ids)
    if any(
        item.category != "linear"
        or item.contract_type != "LinearPerpetual"
        or item.quote_coin != "USDT"
        or item.settle_coin != "USDT"
        for item in selected
    ):
        raise LegacyListingEventEvidenceError("selected instruments must be USDT linear perpetuals")
    selected_symbols = frozenset(item.symbol for item in selected)
    if len(selected_symbols) != SELECTED_INSTRUMENT_COUNT:
        raise LegacyListingEventEvidenceError("selected symbols are not unique")
    base_by_symbol = {item.symbol: item.base_coin for item in selected}
    if any(not value or value.strip() != value for value in base_by_symbol.values()):
        raise LegacyListingEventEvidenceError("selected base coins are invalid")

    publication = verify_completed_history_campaign_publication(
        publication_root,
        source_campaign_root,
    )
    source_plan = _canonical_object(
        source_campaign_root.resolve() / "plan.json",
        label="source campaign plan",
    )
    if source_plan.get("instrument_evidence_sha256") != registry.artifact_sha256:
        raise LegacyListingEventEvidenceError(
            "source campaign does not bind the supplied instrument registry"
        )
    first_times = _verified_first_times(
        source_plan=source_plan,
        published_datasets=publication.published_datasets,
        selected_symbols=selected_symbols,
    )

    document_results: list[dict[str, object]] = []
    event_times: dict[str, int] = {}
    for document in OFFICIAL_DOCUMENTS:
        page = client.fetch_document(document)
        event_time_ms, text = _parse_document(page, document)
        matched = tuple(
            sorted(
                symbol
                for symbol in selected_symbols
                if _message_matches_instrument(
                    text,
                    symbol=symbol,
                    base_coin=base_by_symbol[symbol],
                )
            )
        )
        if len(matched) != document.expected_selected_instrument_count:
            raise LegacyListingEventEvidenceError(
                "official legacy listing document selection match differs from contract"
            )
        if any(symbol in event_times for symbol in matched):
            raise LegacyListingEventEvidenceError(
                "selected instrument matches more than one official document"
            )
        event_times.update(dict.fromkeys(matched, event_time_ms))
        document_results.append(
            {
                "matched_selected_instrument_count": len(matched),
                "fetch_url": document.fetch_url,
                "official_message_at_ms": event_time_ms,
                "official_message_text_sha256": sha256(text.encode("utf-8")).hexdigest(),
                "response_sha256": sha256(page.body).hexdigest(),
                "source_url": document.source_url,
            }
        )
    if set(event_times) != set(selected_symbols):
        raise LegacyListingEventEvidenceError(
            "official document mapping does not cover the selected set exactly once"
        )

    trade_quality = _kind_quality(
        "trade",
        selected_symbols=selected_symbols,
        first_times=first_times,
        event_times=event_times,
    )
    mark_quality = _kind_quality(
        "mark",
        selected_symbols=selected_symbols,
        first_times=first_times,
        event_times=event_times,
    )
    registry_launch_before_event_count = sum(
        item.launch_time_ms < event_times[item.symbol] for item in selected
    )
    verified_bounded_result = (
        trade_quality["event_month_match_count"] == SELECTED_INSTRUMENT_COUNT
        and trade_quality["event_day_match_count"] == 4
        and trade_quality["first_candle_before_event_day_count"] == 1
        and trade_quality["first_candle_after_event_day_count"] == 0
        and trade_quality["maximum_pre_event_lead_days"] == 2
    )
    registry_content_sha256 = registry.payload.get("content_sha256")
    if not isinstance(registry_content_sha256, str):
        raise LegacyListingEventEvidenceError("registry content binding is unavailable")

    document_contract = [
        {
            "data_post": item.data_post,
            "expected_published_at_utc": item.expected_published_at_utc,
            "expected_selected_instrument_count": item.expected_selected_instrument_count,
            "fetch_url": item.fetch_url,
            "required_markers": list(item.required_markers),
            "source_url": item.source_url,
        }
        for item in OFFICIAL_DOCUMENTS
    ]
    payload: dict[str, object] = {
        "assurances": {
            "canonical_market_data_mutated": False,
            "canonical_publication_fully_verified": True,
            "history_campaign_receipts_verified": True,
            "instrument_registry_receipt_verified": True,
            "market_data_network_request_performed": False,
            "official_announcement_response_count": len(document_results),
            "private_endpoint_called": False,
        },
        "bindings": {
            "instrument_registry_artifact_sha256": registry.artifact_sha256,
            "instrument_registry_content_sha256": registry_content_sha256,
            "official_document_contract_sha256": canonical_sha256(document_contract),
            "publication_manifest_sha256": publication.manifest_sha256,
            "selected_instrument_set_sha256": canonical_sha256({"instrument_ids": selected_ids}),
            "software_identity": software_identity,
            "source_campaign_manifest_sha256": sha256_file(
                source_campaign_root.resolve() / "manifest.json"
            ),
            "source_campaign_plan_sha256": sha256_file(
                source_campaign_root.resolve() / "plan.json"
            ),
        },
        "content_sha256": "",
        "contract": EVIDENCE_CONTRACT,
        "generated_at_utc": generated_at_utc,
        "limitations": [
            "Official post timestamps are publication times, not guaranteed product "
            "activation times.",
            "A first canonical candle is observed market-data coverage, not listing metadata.",
            "One selected trade series begins two UTC dates before its related official post.",
            "The current registry remains ex-post evidence, not historical point-in-time metadata.",
            "This evidence does not accept absence, reclassify audits, remove blockers, "
            "open Gate 2, or authorize Phase 3.",
        ],
        "official_documents": document_results,
        "quality": {
            "mark_first_candle": mark_quality,
            "official_document_count": len(document_results),
            "official_document_selected_match_count": sum(
                cast(int, item["matched_selected_instrument_count"]) for item in document_results
            ),
            "registry_launch_before_official_message_count": (registry_launch_before_event_count),
            "selected_instrument_count": len(selected),
            "trade_first_candle": trade_quality,
        },
        "source_policy": {
            "authentication": "none",
            "exact_url_only": True,
            "maximum_response_bytes": MAX_RESPONSE_BYTES,
            "official_channel": "Bybit_Announcements",
            "private_endpoints_called": False,
            "source_type": "official-public-telegram-post",
            "transport_max_attempts_per_document": 1,
        },
        "status": (
            "verified-four-exact-and-one-bounded-legacy-listing-event"
            if verified_bounded_result
            else "blocked-legacy-listing-event-date-mismatch"
        ),
        "storage_policy": {
            "account_data_included": False,
            "credentials_included": False,
            "instrument_identifiers_included": False,
            "market_timestamps_included": False,
            "market_values_included": False,
            "official_announcement_text_included": False,
            "official_announcement_timestamps_included": True,
            "official_announcement_urls_included": True,
            "runtime_paths_included": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    return payload
