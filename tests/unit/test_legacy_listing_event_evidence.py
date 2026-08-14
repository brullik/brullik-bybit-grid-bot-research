from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file
from grid_data.cli import parser
from grid_data.evidence import publish_evidence
from grid_data.instrument_registry import build_instrument_registry
from grid_data.legacy_listing_event_evidence import (
    OFFICIAL_DOCUMENTS,
    LegacyListingEventEvidenceError,
    OfficialListingDocument,
    OfficialListingPage,
    _parse_document,
    build_legacy_listing_event_evidence,
)
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[2]
SOFTWARE_IDENTITY = "git:" + "6" * 40
SYMBOLS = ("BTCUSDT", "LINKUSDT", "LTCUSDT", "XTZUSDT", "BCHUSDT")


def _utc_ms(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp()) * 1000


def _inventory_record(symbol: str, instrument_id: int) -> dict[str, object]:
    return {
        "base_coin": symbol.removesuffix("USDT"),
        "contract_type": "LinearPerpetual",
        "delivery_time_ms": 0,
        "funding_interval_minutes": 480,
        "launch_time_ms": _utc_ms("2018-01-01T00:00:00+00:00"),
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
        "fetched_at_utc": "2026-08-15T00:00:00Z",
        "inventory_status": "complete",
        "records": [
            _inventory_record(symbol, instrument_id)
            for instrument_id, symbol in enumerate(SYMBOLS, start=1)
        ],
    }
    payload = build_instrument_registry(inventory, inventory_artifact_sha256="b" * 64)
    artifact, _receipt = publish_evidence(tmp_path / "registry.json", payload)
    return artifact


def _official_text(document: OfficialListingDocument) -> str:
    if document.data_post.endswith("/72"):
        return "USDT Perpetual Contracts — Now Live. Starting today: BTC/USDT."
    if document.data_post.endswith("/312"):
        return "4 new USDT trading pairs now live: ETH, LINK, XTZ and LTC."
    if document.data_post.endswith("/347"):
        return "BCH/USDT is now available for trading."
    raise AssertionError("unexpected document")


def _page(document: OfficialListingDocument, *, omit_text: bool = False) -> OfficialListingPage:
    text = "marker removed" if omit_text else _official_text(document)
    body = (
        "<html><body>"
        f'<div class="post" data-post="{document.data_post}">'
        f'<div><time datetime="{document.expected_published_at_utc}"></time>{text}</div>'
        "</div></body></html>"
    ).encode()
    return OfficialListingPage(
        body=body,
        content_type="text/html",
        final_url=document.fetch_url,
        status_code=200,
    )


class FakeOfficialListingClient:
    transport_max_attempts = 1

    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch_document(self, document: OfficialListingDocument) -> OfficialListingPage:
        self.calls.append(document.fetch_url)
        return _page(document)


def _campaign_fixture(
    tmp_path: Path,
    *,
    registry_artifact_sha256: str,
) -> tuple[Path, Path, SimpleNamespace]:
    trade_times = {
        "BTCUSDT": "2020-03-25T10:36:00+00:00",
        "LINKUSDT": "2020-10-21T09:29:00+00:00",
        "LTCUSDT": "2020-10-21T09:27:00+00:00",
        "XTZUSDT": "2020-10-21T09:30:00+00:00",
        "BCHUSDT": "2020-12-14T06:51:00+00:00",
    }
    mark_times = {
        "BTCUSDT": "2020-03-25T08:41:00+00:00",
        "LINKUSDT": "2020-10-21T06:47:00+00:00",
        "LTCUSDT": "2020-10-19T09:34:00+00:00",
        "XTZUSDT": "2020-10-20T08:44:00+00:00",
        "BCHUSDT": "2020-12-14T06:51:00+00:00",
    }
    jobs: list[dict[str, object]] = []
    published: list[SimpleNamespace] = []
    for symbol in SYMBOLS:
        for kind, values in (("trade", trade_times), ("mark", mark_times)):
            sequence = len(jobs)
            timestamp = _utc_ms(values[symbol])
            jobs.append(
                {
                    "kind": kind,
                    "request": {"series": [{"symbol": symbol}]},
                    "sequence": sequence,
                }
            )
            published.append(
                SimpleNamespace(
                    manifest=SimpleNamespace(
                        row_count=1,
                        min_time_ms=timestamp,
                        max_time_ms=timestamp,
                    )
                )
            )
    campaign_root = tmp_path / "campaign"
    publication_root = tmp_path / "publication"
    campaign_root.mkdir()
    publication_root.mkdir()
    (campaign_root / "plan.json").write_bytes(
        canonical_json_bytes(
            {
                "instrument_evidence_sha256": registry_artifact_sha256,
                "jobs": jobs,
            }
        )
    )
    (campaign_root / "manifest.json").write_bytes(canonical_json_bytes({"status": "complete"}))
    return (
        campaign_root,
        publication_root,
        SimpleNamespace(
            manifest_sha256="e" * 64,
            published_datasets=tuple(published),
        ),
    )


def test_builder_is_schema_valid_receipt_bound_and_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry(tmp_path)
    campaign_root, publication_root, completed = _campaign_fixture(
        tmp_path,
        registry_artifact_sha256=sha256_file(registry),
    )
    monkeypatch.setattr(
        "grid_data.legacy_listing_event_evidence.verify_completed_history_campaign_publication",
        lambda _publication, _campaign: completed,
    )
    client = FakeOfficialListingClient()
    payload = build_legacy_listing_event_evidence(
        client,
        instrument_registry_path=registry,
        instrument_ids=(5, 3, 1, 4, 2),
        publication_root=publication_root,
        source_campaign_root=campaign_root,
        generated_at_utc="2026-08-15T01:00:00Z",
        software_identity=SOFTWARE_IDENTITY,
    )
    schema = json.loads(
        (
            ROOT
            / "schemas"
            / "evidence"
            / "v1"
            / "phase2-legacy-listing-event-evidence.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    content = dict(payload)
    embedded_hash = content.pop("content_sha256")
    assert embedded_hash == canonical_sha256(content)
    assert client.calls == [item.fetch_url for item in OFFICIAL_DOCUMENTS]
    assert payload["status"] == "verified-four-exact-and-one-bounded-legacy-listing-event"
    assert payload["quality"] == {
        "mark_first_candle": {
            "event_day_match_count": 2,
            "event_month_match_count": 5,
            "first_candle_after_event_day_count": 0,
            "first_candle_before_event_day_count": 3,
            "maximum_post_event_lag_days": 0,
            "maximum_pre_event_lead_days": 2,
        },
        "official_document_count": 3,
        "official_document_selected_match_count": 5,
        "registry_launch_before_official_message_count": 5,
        "selected_instrument_count": 5,
        "trade_first_candle": {
            "event_day_match_count": 4,
            "event_month_match_count": 5,
            "first_candle_after_event_day_count": 0,
            "first_candle_before_event_day_count": 1,
            "maximum_post_event_lag_days": 0,
            "maximum_pre_event_lead_days": 2,
        },
    }
    rendered = json.dumps(payload).lower()
    for forbidden in (
        *[symbol.lower() for symbol in SYMBOLS],
        str(tmp_path).lower(),
        '"instrument_id"',
        '"open_time_ms"',
        '"market_value"',
        "api_key",
        "api_secret",
    ):
        assert forbidden not in rendered


def test_parser_rejects_missing_markers_and_timestamp_drift() -> None:
    document = OFFICIAL_DOCUMENTS[0]
    with pytest.raises(LegacyListingEventEvidenceError, match="statements do not verify"):
        _parse_document(_page(document, omit_text=True), document)

    changed = OfficialListingPage(
        body=_page(document).body.replace(b"16:03:10", b"16:03:11"),
        content_type="text/html",
        final_url=document.fetch_url,
        status_code=200,
    )
    with pytest.raises(LegacyListingEventEvidenceError, match="timestamp changed"):
        _parse_document(changed, document)


def test_cli_exposes_legacy_listing_event_evidence_command(tmp_path: Path) -> None:
    args = parser().parse_args(
        [
            "legacy-listing-event-evidence",
            "--instrument-registry",
            str(tmp_path / "registry.json"),
            "--instrument-id",
            "5",
            "--publication-root",
            str(tmp_path / "publication"),
            "--source-campaign-root",
            str(tmp_path / "campaign"),
            "--software-identity",
            SOFTWARE_IDENTITY,
            "--output",
            str(tmp_path / "evidence.json"),
        ]
    )
    assert args.instrument_id == [5]
    assert args.publication_root == tmp_path / "publication"
