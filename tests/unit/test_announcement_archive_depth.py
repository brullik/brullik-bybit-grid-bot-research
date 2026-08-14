from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from grid_bybit_public import ANNOUNCEMENT_TYPES, AnnouncementPage
from grid_contracts.canonical import canonical_sha256
from grid_data.announcement_archive_depth import (
    AnnouncementArchiveDepthError,
    build_announcement_archive_depth_evidence,
)
from grid_data.cli import parser
from grid_data.evidence import publish_evidence
from grid_data.instrument_registry import build_instrument_registry
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[2]
SOFTWARE_IDENTITY = "git:" + "7" * 40


def _inventory_record(symbol: str, instrument_id: int, launch_time_ms: int) -> dict[str, object]:
    return {
        "base_coin": symbol.removesuffix("USDT"),
        "contract_type": "LinearPerpetual",
        "delivery_time_ms": 0,
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
        "status": "Trading",
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
            _inventory_record("BBBUSDT", 2, 1_610_000_000_000),
        ],
    }
    payload = build_instrument_registry(inventory, inventory_artifact_sha256="b" * 64)
    artifact, _receipt = publish_evidence(tmp_path / "registry.json", payload)
    return artifact


class FakeAnnouncementClient:
    def __init__(self, *, mutate_last_total: bool = False) -> None:
        self.calls: list[tuple[str, int]] = []
        self.mutate_last_total = mutate_last_total
        self.transport_max_attempts = 1

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
        self.calls.append((announcement_type, page))
        type_index = ANNOUNCEMENT_TYPES.index(announcement_type)
        if page == 1:
            times = tuple(
                1_700_000_000_000 + type_index * 1_000_000 - offset for offset in range(20)
            )
            total = 21
        elif page == 2:
            times = (1_650_000_000_000 + type_index * 1_000_000,)
            total = 22 if self.mutate_last_total else 21
        else:
            raise AssertionError(f"unexpected page {page}")
        items_buffer: list[Mapping[str, Any]] = []
        for value in times:
            item: dict[str, Any] = {
                "dateTimestamp": value,
                "description": "must not escape",
                "title": "must not escape",
                "type": {"key": announcement_type, "title": "type title"},
                "url": "https://announcements.bybit.com/private-shape-only",
            }
            if page == 1:
                item["publishTime"] = value
            items_buffer.append(item)
        items = tuple(items_buffer)
        return AnnouncementPage(
            announcement_type=announcement_type,
            page=page,
            limit=limit,
            total=total,
            items=items,
        )


def test_bounded_archive_depth_is_schema_valid_hashed_and_redacted(tmp_path: Path) -> None:
    client = FakeAnnouncementClient()
    payload = build_announcement_archive_depth_evidence(
        client,
        instrument_registry_path=_registry(tmp_path),
        instrument_ids=(2, 1),
        generated_at_utc="2026-08-14T12:00:00Z",
        software_identity=SOFTWARE_IDENTITY,
    )
    schema = json.loads(
        (
            ROOT / "schemas" / "evidence" / "v1" / "phase2-announcement-archive-depth.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == canonical_sha256(hash_input)
    assert len(client.calls) == 16
    assert payload["status"] == "blocked-insufficient-official-announcement-history"
    assert payload["archive_depth"] == {
        "all_selected_registry_launches_within_new_listing_archive": False,
        "delistings_declared_last_page_min_date_timestamp_ms": 1_650_002_000_000,
        "documented_types_declared_last_page_min_date_timestamp_ms": 1_650_000_000_000,
        "new_crypto_declared_last_page_min_date_timestamp_ms": 1_650_000_000_000,
        "selected_launch_before_new_listing_archive_count": 2,
        "selected_registry_launch_max_ms": 1_610_000_000_000,
        "selected_registry_launch_min_ms": 1_600_000_000_000,
    }
    first_probe = payload["type_probes"][0]
    assert first_probe["declared_page_date_order_consistent"] is True
    assert first_probe["first_page_adjacent_date_inversion_count"] == 0
    assert first_probe["first_page_publish_time_present_count"] == 20
    assert first_probe["lifecycle_depth_type"] is True
    assert first_probe["last_page_publish_time_present_count"] == 0
    assert first_probe["oldest_publish_time_ms"] is None
    rendered = json.dumps(payload).lower()
    for forbidden in (
        "aaausdt",
        "bbbusdt",
        "must not escape",
        "announcements.bybit.com",
        "instrument_ids",
        "c:\\",
        "api_key",
        "api_secret",
    ):
        assert forbidden not in rendered


def _client_with_first_page_inversion(announcement_type: str) -> FakeAnnouncementClient:
    class InvertedClient(FakeAnnouncementClient):
        def announcement_page(self, **kwargs: Any) -> AnnouncementPage:
            page = super().announcement_page(**kwargs)
            if page.announcement_type == announcement_type and page.page == 1:
                items = list(page.items)
                items[8], items[9] = items[9], items[8]
                return AnnouncementPage(
                    announcement_type=page.announcement_type,
                    page=page.page,
                    limit=page.limit,
                    total=page.total,
                    items=tuple(items),
                )
            return page

    return InvertedClient()


def test_non_lifecycle_page_inversion_is_recorded_without_becoming_depth_proof(
    tmp_path: Path,
) -> None:
    payload = build_announcement_archive_depth_evidence(
        _client_with_first_page_inversion("latest_activities"),
        instrument_registry_path=_registry(tmp_path),
        instrument_ids=(1, 2),
        generated_at_utc="2026-08-14T12:00:00Z",
        software_identity=SOFTWARE_IDENTITY,
    )
    probe = next(
        item for item in payload["type_probes"] if item["announcement_type"] == "latest_activities"
    )
    assert probe["lifecycle_depth_type"] is False
    assert probe["declared_page_date_order_consistent"] is False
    assert probe["first_page_adjacent_date_inversion_count"] == 1


def test_lifecycle_page_inversion_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(AnnouncementArchiveDepthError, match="unordered bounds"):
        build_announcement_archive_depth_evidence(
            _client_with_first_page_inversion("new_crypto"),
            instrument_registry_path=_registry(tmp_path),
            instrument_ids=(1, 2),
            generated_at_utc="2026-08-14T12:00:00Z",
            software_identity=SOFTWARE_IDENTITY,
        )


def test_archive_depth_fails_if_total_changes_between_bound_pages(tmp_path: Path) -> None:
    with pytest.raises(AnnouncementArchiveDepthError, match="changed during"):
        build_announcement_archive_depth_evidence(
            FakeAnnouncementClient(mutate_last_total=True),
            instrument_registry_path=_registry(tmp_path),
            instrument_ids=(1, 2),
            generated_at_utc="2026-08-14T12:00:00Z",
            software_identity=SOFTWARE_IDENTITY,
        )


def test_archive_depth_rejects_duplicate_or_missing_registry_selection(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    with pytest.raises(AnnouncementArchiveDepthError, match="unique"):
        build_announcement_archive_depth_evidence(
            FakeAnnouncementClient(),
            instrument_registry_path=registry,
            instrument_ids=(1, 1),
            generated_at_utc="2026-08-14T12:00:00Z",
            software_identity=SOFTWARE_IDENTITY,
        )
    with pytest.raises(AnnouncementArchiveDepthError, match="absent"):
        build_announcement_archive_depth_evidence(
            FakeAnnouncementClient(),
            instrument_registry_path=registry,
            instrument_ids=(3,),
            generated_at_utc="2026-08-14T12:00:00Z",
            software_identity=SOFTWARE_IDENTITY,
        )


def test_cli_exposes_bounded_announcement_depth_command(tmp_path: Path) -> None:
    args = parser().parse_args(
        [
            "announcement-archive-depth",
            "--instrument-registry",
            str(tmp_path / "registry.json"),
            "--instrument-id",
            "5",
            "--software-identity",
            SOFTWARE_IDENTITY,
            "--output",
            str(tmp_path / "evidence.json"),
        ]
    )
    assert args.instrument_id == [5]
