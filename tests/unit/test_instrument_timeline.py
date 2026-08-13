from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from grid_contracts.canonical import canonical_sha256
from grid_data.evidence import publish_evidence
from grid_data.instrument_registry import build_instrument_registry
from grid_data.instrument_timeline import (
    InstrumentTimelineError,
    build_instrument_timeline,
    build_instrument_timeline_summary,
    load_verified_instrument_timeline,
    select_instruments_as_of,
)
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[2]


def _inventory_record(
    symbol: str,
    source_symbol_id: int,
    *,
    status: str = "Trading",
    launch_time_ms: int = 1_600_000_000_000,
    delivery_time_ms: int = 0,
    tick_size: str = "0.0001",
) -> dict[str, object]:
    return {
        "base_coin": symbol.removesuffix("USDT"),
        "contract_type": "LinearPerpetual",
        "delivery_time_ms": delivery_time_ms,
        "funding_interval_minutes": 480,
        "launch_time_ms": launch_time_ms,
        "max_leverage": "100",
        "max_order_quantity": "1000000",
        "min_leverage": "1",
        "min_order_quantity": "0.001",
        "quantity_step": "0.001",
        "quote_coin": "USDT",
        "settle_coin": "USDT",
        "source_payload_sha256": f"{source_symbol_id:064x}",
        "source_symbol_id": source_symbol_id,
        "status": status,
        "symbol": symbol,
        "tick_size": tick_size,
    }


def _inventory(
    fetched_at: str,
    records: list[dict[str, object]],
    *,
    inventory_status: str = "complete",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "evidence_schema": "grid.bybit-public-inventory/v1",
        "fetched_at_utc": fetched_at,
        "inventory_status": inventory_status,
        "records": records,
        "source": {"endpoint": "/v5/market/instruments-info"},
        "summary": {},
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def _registry(
    tmp_path: Path,
    name: str,
    fetched_at: str,
    records: list[dict[str, object]],
    *,
    inventory_status: str = "complete",
) -> Path:
    inventory_path, _ = publish_evidence(
        tmp_path / f"{name}-inventory.json",
        _inventory(fetched_at, records, inventory_status=inventory_status),
    )
    payload = build_instrument_registry(
        json.loads(inventory_path.read_text(encoding="utf-8")),
        inventory_artifact_sha256=(name[0] * 64),
    )
    registry_path, _ = publish_evidence(tmp_path / f"{name}-registry.json", payload)
    return registry_path


def _two_snapshot_timeline(tmp_path: Path, *, partial_first: bool = False) -> Path:
    first = _registry(
        tmp_path,
        "a",
        "2026-01-01T00:00:00Z",
        [_inventory_record("AAAUSDT", 1), _inventory_record("BBBUSDT", 9)],
        inventory_status="partial" if partial_first else "complete",
    )
    second = _registry(
        tmp_path,
        "b",
        "2026-02-01T00:00:00Z",
        [
            _inventory_record(
                "AAAUSDT",
                1,
                status="Closed",
                delivery_time_ms=1_700_000_000_000,
            ),
            _inventory_record("BBBUSDT", 9, tick_size="0.001"),
        ],
    )
    payload = build_instrument_timeline((second, first))
    timeline_path, _ = publish_evidence(tmp_path / "timeline.json", payload)
    return timeline_path


def test_timeline_is_deterministic_schema_valid_and_tracks_normal_close(tmp_path: Path) -> None:
    timeline_path = _two_snapshot_timeline(tmp_path)
    verified = load_verified_instrument_timeline(timeline_path)
    schema = json.loads(
        (ROOT / "schemas" / "market" / "v1" / "instrument-timeline.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema).validate(verified.payload)

    assert tuple(item.snapshot_time_ms for item in verified.snapshots) == (
        1_767_225_600_000,
        1_769_904_000_000,
    )
    aaa = next(item for item in verified.coverage if item.instrument_id == 1)
    assert aaa.delivery_time_ms == 1_700_000_000_000
    assert aaa.blocker_codes == ()
    assert verified.payload["summary"]["coverage_blocker_codes"] == []  # type: ignore[index]


def test_as_of_selection_never_exposes_future_snapshot_fields(tmp_path: Path) -> None:
    verified = load_verified_instrument_timeline(_two_snapshot_timeline(tmp_path))
    first_time = verified.snapshots[0].snapshot_time_ms
    second_time = verified.snapshots[1].snapshot_time_ms

    first = select_instruments_as_of(verified, as_of_ms=first_time, instrument_ids=(1,))
    assert first.snapshot_time_ms == first_time
    assert first.records[0].status == "Trading"
    assert first.records[0].delivery_time_ms is None
    assert str(first.records[0].tick_size) == "0.0001"

    second = select_instruments_as_of(verified, as_of_ms=second_time, instrument_ids=(1, 9))
    assert second.records[0].status == "Closed"
    assert second.records[0].delivery_time_ms == 1_700_000_000_000
    assert str(second.records[1].tick_size) == "0.001"

    with pytest.raises(InstrumentTimelineError, match="no instrument snapshot"):
        select_instruments_as_of(verified, as_of_ms=first_time - 1)
    with pytest.raises(InstrumentTimelineError, match="absent from as-of"):
        select_instruments_as_of(verified, as_of_ms=second_time, instrument_ids=(2,))


def test_partial_inventory_blocks_strict_as_of_and_public_summary(tmp_path: Path) -> None:
    verified = load_verified_instrument_timeline(
        _two_snapshot_timeline(tmp_path, partial_first=True)
    )
    with pytest.raises(InstrumentTimelineError, match="partial"):
        select_instruments_as_of(
            verified,
            as_of_ms=verified.snapshots[0].snapshot_time_ms,
            require_complete_inventory=True,
        )

    summary = build_instrument_timeline_summary(
        verified,
        software_identity="git:" + "c" * 40,
        generated_at=datetime(2026, 2, 2, tzinfo=UTC),
    )
    schema = json.loads(
        (
            ROOT / "schemas" / "evidence" / "v1" / "instrument-timeline-summary.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(summary)
    assert summary["status"] == "blocked"
    assert summary["blocker_codes"] == ["partial_source_inventory"]
    rendered = json.dumps(summary).lower()
    assert "aaausdt" not in rendered
    assert "c:\\" not in rendered


def test_lifecycle_conflicts_are_preserved_as_blockers(tmp_path: Path) -> None:
    first = _registry(
        tmp_path,
        "a",
        "2026-01-01T00:00:00Z",
        [_inventory_record("AAAUSDT", 1)],
    )
    second = _registry(
        tmp_path,
        "b",
        "2026-02-01T00:00:00Z",
        [_inventory_record("AAAUSDT", 1, launch_time_ms=1_600_000_060_000)],
    )
    timeline_path, _ = publish_evidence(
        tmp_path / "timeline.json", build_instrument_timeline((first, second))
    )
    verified = load_verified_instrument_timeline(timeline_path)
    assert verified.coverage[0].launch_time_ms is None
    assert verified.coverage[0].blocker_codes == ("conflicting_launch_time",)


def test_timeline_rejects_duplicate_time_and_tampered_receipt(tmp_path: Path) -> None:
    first = _registry(
        tmp_path,
        "a",
        "2026-01-01T00:00:00Z",
        [_inventory_record("AAAUSDT", 1)],
    )
    duplicate_time = _registry(
        tmp_path,
        "b",
        "2026-01-01T00:00:00Z",
        [_inventory_record("AAAUSDT", 1, tick_size="0.001")],
    )
    with pytest.raises(InstrumentTimelineError, match="strictly increasing"):
        build_instrument_timeline((first, duplicate_time))

    timeline_path = _two_snapshot_timeline(tmp_path / "tamper")
    payload = json.loads(timeline_path.read_text(encoding="utf-8"))
    altered = deepcopy(payload)
    altered["summary"]["snapshot_count"] = 3
    timeline_path.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(InstrumentTimelineError, match="receipt"):
        load_verified_instrument_timeline(timeline_path)


def test_timeline_rejects_rewritten_embedded_registry_even_with_new_outer_receipt(
    tmp_path: Path,
) -> None:
    source = _registry(
        tmp_path,
        "a",
        "2026-01-01T00:00:00Z",
        [_inventory_record("AAAUSDT", 1)],
    )
    timeline = build_instrument_timeline((source,))
    embedded = timeline["snapshots"][0]["registry"]  # type: ignore[index]
    embedded["records"][0]["status"] = "Closed"
    registry_hash_input = dict(embedded)
    registry_hash_input.pop("content_sha256")
    embedded["content_sha256"] = canonical_sha256(registry_hash_input)
    timeline_hash_input = dict(timeline)
    timeline_hash_input.pop("content_sha256")
    timeline["content_sha256"] = canonical_sha256(timeline_hash_input)
    rewritten_path, _ = publish_evidence(tmp_path / "rewritten.json", timeline)

    with pytest.raises(InstrumentTimelineError, match="artifact hash"):
        load_verified_instrument_timeline(rewritten_path)
