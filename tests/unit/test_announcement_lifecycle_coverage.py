from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from grid_bybit_public import AnnouncementPage
from grid_contracts.canonical import canonical_sha256
from grid_data.announcement_lifecycle_coverage import (
    AnnouncementLifecycleCoverageError,
    build_announcement_lifecycle_coverage_evidence,
)
from grid_data.cli import parser
from grid_data.evidence import publish_evidence
from grid_data.instrument_registry import (
    build_instrument_registry,
    load_verified_instrument_registry,
)
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[2]
SOFTWARE_IDENTITY = "git:" + "9" * 40


def _inventory_record(
    symbol: str,
    instrument_id: int,
    launch_time_ms: int,
    *,
    status: str = "Trading",
    delivery_time_ms: int = 0,
) -> dict[str, object]:
    return {
        "base_coin": symbol.removesuffix("USDT"),
        "contract_type": "LinearPerpetual",
        "delivery_time_ms": delivery_time_ms,
        "funding_interval_minutes": 480,
        "launch_time_ms": launch_time_ms,
        "max_leverage": "50",
        "max_order_quantity": "100000",
        "min_leverage": "1",
        "min_order_quantity": "0.1",
        "quantity_step": "0.1",
        "quote_coin": "USDT",
        "settle_coin": "USDT",
        "source_payload_sha256": f"{instrument_id:064x}",
        "source_symbol_id": instrument_id,
        "status": status,
        "symbol": symbol,
        "tick_size": "0.001",
    }


def _registry(tmp_path: Path) -> Path:
    inventory: dict[str, object] = {
        "content_sha256": "a" * 64,
        "evidence_schema": "grid.bybit-public-inventory/v1",
        "fetched_at_utc": "2026-08-14T00:00:00Z",
        "inventory_status": "complete",
        "records": [
            _inventory_record("AAAUSDT", 1, 1_600_000_000_000),
            _inventory_record("BBBUSDT", 2, 1_700_200_000_000),
            _inventory_record(
                "CCCUSDT",
                3,
                1_700_300_000_000,
                status="Closed",
                delivery_time_ms=1_700_500_000_000,
            ),
            _inventory_record("DDDUSDT", 4, 1_600_100_000_000),
        ],
    }
    payload = build_instrument_registry(inventory, inventory_artifact_sha256="b" * 64)
    artifact, _receipt = publish_evidence(tmp_path / "registry.json", payload)
    return artifact


def _campaign_request(tmp_path: Path) -> Path:
    path = tmp_path / "campaign-request.json"
    path.write_text(
        json.dumps(
            {
                "campaign_id": "selected-three",
                "contract": "grid.public-history-campaign-request/v1",
                "end_ms": 1_800_000_000_000,
                "history_page_limit": 1000,
                "kinds": ["trade", "mark"],
                "lifecycle_policy": "registry-lifecycle-intersection-v1",
                "max_attempts": 3,
                "start_ms": 1_500_000_000_000,
                "symbols": ["BBBUSDT", "CCCUSDT"],
                "target_rps": 10,
                "workers": 2,
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _legacy_evidence(tmp_path: Path, registry_path: Path) -> Path:
    registry = load_verified_instrument_registry(registry_path)
    payload: dict[str, object] = {
        "bindings": {
            "instrument_registry_artifact_sha256": registry.artifact_sha256,
            "instrument_registry_content_sha256": registry.payload["content_sha256"],
            "selected_instrument_set_sha256": canonical_sha256({"instrument_ids": (1,)}),
        },
        "contract": "grid.phase2-legacy-listing-event-evidence/v1",
        "quality": {
            "selected_instrument_count": 1,
            "trade_first_candle": {
                "event_day_match_count": 1,
                "first_candle_before_event_day_count": 0,
            },
        },
        "status": "verified-four-exact-and-one-bounded-legacy-listing-event",
    }
    payload["content_sha256"] = canonical_sha256(payload)
    artifact, _receipt = publish_evidence(tmp_path / "legacy.json", payload)
    return artifact


def _item(
    announcement_type: str,
    timestamp_ms: int,
    title: str,
    sequence: int,
    *,
    description: str = "",
    tags: list[str] | None = None,
) -> Mapping[str, Any]:
    return {
        "dateTimestamp": timestamp_ms,
        "description": description,
        "publishTime": timestamp_ms,
        "tags": [] if tags is None else tags,
        "title": title,
        "type": {"key": announcement_type, "title": "Lifecycle"},
        "url": f"https://announcements.bybit.com/en/article/event-{sequence}/",
    }


class FakeAnnouncementClient:
    transport_max_attempts = 1

    def __init__(
        self,
        *,
        duplicate_listing: bool = False,
        invert_listing: bool = False,
        legacy_optional_shape: bool = False,
    ) -> None:
        self.calls: list[tuple[str, int]] = []
        self.duplicate_listing = duplicate_listing
        self.invert_listing = invert_listing
        self.legacy_optional_shape = legacy_optional_shape

    def announcement_page(
        self,
        *,
        announcement_type: str,
        page: int,
        locale: str = "en-US",
        limit: int = 20,
    ) -> AnnouncementPage:
        assert locale == "en-US"
        assert limit == 20
        assert page == 1
        self.calls.append((announcement_type, page))
        if announcement_type == "new_crypto":
            items = [
                _item(
                    announcement_type,
                    1_700_300_000_000,
                    "Launch CCC/USDT Perpetual Contract",
                    1,
                ),
                _item(
                    announcement_type,
                    1_700_200_000_000,
                    "New BBBUSDT Perpetual Contract",
                    2,
                ),
                _item(
                    announcement_type,
                    1_700_100_000_000,
                    "BBB/USDT Spot listing",
                    3,
                ),
            ]
            if self.duplicate_listing:
                items.insert(
                    2,
                    _item(
                        announcement_type,
                        1_700_150_000_000,
                        "Second BBBUSDT Derivatives launch",
                        4,
                    ),
                )
            if self.invert_listing:
                items[0], items[1] = items[1], items[0]
            if self.legacy_optional_shape:
                items[2] = {
                    "dateTimestamp": 1_700_100_000_000,
                    "description": None,
                    "publishTime": 1_700_100_000_000,
                    "tags": None,
                    "title": None,
                    "type": {"key": announcement_type, "title": "Lifecycle"},
                }
        elif announcement_type == "delistings":
            items = [
                _item(
                    announcement_type,
                    1_700_500_000_000,
                    "Delist CCCUSDT Perpetual Contract",
                    5,
                ),
                _item(
                    announcement_type,
                    1_700_400_000_000,
                    "Unrelated Spot delisting",
                    6,
                ),
            ]
        else:
            raise AssertionError(announcement_type)
        return AnnouncementPage(
            announcement_type=announcement_type,
            page=page,
            limit=limit,
            total=len(items),
            items=tuple(items),
        )


def _build(
    tmp_path: Path,
    client: FakeAnnouncementClient,
) -> dict[str, object]:
    registry = _registry(tmp_path)
    return build_announcement_lifecycle_coverage_evidence(
        client,
        instrument_registry_path=registry,
        campaign_request_paths=(_campaign_request(tmp_path),),
        legacy_evidence_path=_legacy_evidence(tmp_path, registry),
        legacy_instrument_ids=(1,),
        generated_at_utc="2026-08-15T00:00:00Z",
        software_identity=SOFTWARE_IDENTITY,
    )


def test_full_lifecycle_archive_matching_is_schema_valid_hashed_and_redacted(
    tmp_path: Path,
) -> None:
    client = FakeAnnouncementClient()
    payload = _build(tmp_path, client)
    schema = json.loads(
        (
            ROOT
            / "schemas"
            / "evidence"
            / "v1"
            / "phase2-announcement-lifecycle-coverage.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded = hash_input.pop("content_sha256")
    assert embedded == canonical_sha256(hash_input)
    assert client.calls == [("new_crypto", 1), ("delistings", 1)]
    assert payload["status"] == "verified-record-matched-official-lifecycle-evidence"
    assert payload["blocker_codes"] == ["historical-point-in-time-metadata-still-incomplete"]
    assert payload["scope"] == {
        "closed_instrument_count": 1,
        "campaign_request_count": 1,
        "delivered_instrument_count": 1,
        "prelaunch_instrument_count": 0,
        "selected_instrument_count": 3,
        "trading_instrument_count": 2,
    }
    matching = payload["matching"]
    assert matching["record_matching_complete"] is True
    assert matching["listing"]["eligible_instrument_count"] == 2
    assert matching["listing"]["outside_archive_instrument_count"] == 1
    assert matching["listing"]["unique_match_instrument_count"] == 2
    assert matching["delisting"]["unique_match_instrument_count"] == 1
    assert payload["legacy_evidence"]["remaining_pre_archive_listing_instrument_count"] == 0
    rendered = json.dumps(payload).lower()
    for forbidden in (
        "aaausdt",
        "bbbusdt",
        "cccusdt",
        "launch ccc",
        "announcements.bybit.com",
        "instrument_ids",
        "c:\\",
        "api_key",
        "api_secret",
    ):
        assert forbidden not in rendered


def test_multiple_official_candidates_remain_ambiguous_and_blocked(tmp_path: Path) -> None:
    payload = _build(tmp_path, FakeAnnouncementClient(duplicate_listing=True))
    assert payload["status"] == "verified-partial-official-lifecycle-evidence"
    assert "listing-announcement-match-ambiguous" in payload["blocker_codes"]
    assert payload["matching"]["listing"]["ambiguous_instrument_count"] == 1
    assert payload["matching"]["record_matching_complete"] is False


def test_lifecycle_archive_order_inversion_is_visible_without_reordering(tmp_path: Path) -> None:
    payload = _build(tmp_path, FakeAnnouncementClient(invert_listing=True))
    listing_source = payload["archive_sources"][0]
    assert listing_source["adjacent_date_inversion_count"] == 1


def test_legacy_optional_fields_are_hash_bound_and_counted(tmp_path: Path) -> None:
    payload = _build(tmp_path, FakeAnnouncementClient(legacy_optional_shape=True))
    listing_source = payload["archive_sources"][0]
    assert listing_source["blank_or_missing_title_count"] == 1
    assert listing_source["blank_or_missing_description_count"] == 3
    assert listing_source["missing_tags_count"] == 1
    assert listing_source["missing_url_count"] == 1
    assert payload["matching"]["record_matching_complete"] is True


def test_legacy_selection_binding_fails_closed(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    with pytest.raises(AnnouncementLifecycleCoverageError, match="selection binding differs"):
        build_announcement_lifecycle_coverage_evidence(
            FakeAnnouncementClient(),
            instrument_registry_path=registry,
            campaign_request_paths=(_campaign_request(tmp_path),),
            legacy_evidence_path=_legacy_evidence(tmp_path, registry),
            legacy_instrument_ids=(4,),
            generated_at_utc="2026-08-15T00:00:00Z",
            software_identity=SOFTWARE_IDENTITY,
        )


def test_cli_exposes_announcement_lifecycle_coverage_command(tmp_path: Path) -> None:
    args = parser().parse_args(
        [
            "announcement-lifecycle-coverage",
            "--instrument-registry",
            str(tmp_path / "registry.json"),
            "--campaign-request",
            str(tmp_path / "campaign.json"),
            "--legacy-evidence",
            str(tmp_path / "legacy.json"),
            "--legacy-instrument-id",
            "5",
            "--software-identity",
            SOFTWARE_IDENTITY,
            "--output",
            str(tmp_path / "evidence.json"),
        ]
    )
    assert args.campaign_request == [tmp_path / "campaign.json"]
    assert args.legacy_instrument_id == [5]
