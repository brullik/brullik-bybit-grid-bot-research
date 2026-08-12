from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_data.evidence import publish_evidence
from grid_data.instrument_registry import (
    IDENTITY_ALGORITHM,
    InstrumentRegistryError,
    build_instrument_registry,
    build_verified_registry_from_inventory,
    load_verified_instrument_registry,
)
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[2]


def inventory_record(symbol: str, source_symbol_id: int) -> dict[str, object]:
    return {
        "base_coin": symbol.removesuffix("USDT"),
        "contract_type": "LinearPerpetual",
        "delivery_time_ms": 0,
        "funding_interval_minutes": 480,
        "launch_time_ms": 1_600_000_000_000,
        "max_leverage": "100",
        "max_order_quantity": "1000000",
        "min_leverage": "1",
        "min_order_quantity": "0.001",
        "quantity_step": "0.001",
        "quote_coin": "USDT",
        "settle_coin": "USDT",
        "source_payload_sha256": f"{source_symbol_id:064x}",
        "source_symbol_id": source_symbol_id,
        "status": "Trading",
        "symbol": symbol,
        "tick_size": "0.0001",
    }


def inventory() -> dict[str, object]:
    payload: dict[str, object] = {
        "evidence_schema": "grid.bybit-public-inventory/v1",
        "fetched_at_utc": "2026-08-12T12:36:49.032806Z",
        "inventory_status": "partial",
        "records": [inventory_record("AAAUSDT", 1), inventory_record("BBBUSDT", 9)],
        "source": {"endpoint": "/v5/market/instruments-info"},
        "summary": {},
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def test_registry_freezes_source_identity_without_renumbering() -> None:
    payload = build_instrument_registry(inventory(), inventory_artifact_sha256="a" * 64)
    schema = json.loads(
        (ROOT / "schemas" / "market" / "v1" / "instrument-registry.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema).validate(payload)
    records = payload["records"]
    assert isinstance(records, list)
    assert [item["instrument_id"] for item in records] == [1, 9]
    assert [item["source_symbol_id"] for item in records] == [1, 9]
    assert all(item["delivery_time_ms"] is None for item in records)
    assert payload["identity_policy"] == {
        "algorithm": IDENTITY_ALGORITHM,
        "category": "linear",
        "instrument_id_expression": "source_symbol_id",
        "range": "uint32-positive",
    }


def test_receipted_inventory_builds_and_loads_verified_registry(tmp_path: Path) -> None:
    inventory_path, _ = publish_evidence(tmp_path / "inventory.json", inventory())
    payload = build_verified_registry_from_inventory(inventory_path)
    registry_path, _ = publish_evidence(tmp_path / "registry.json", payload)

    registry = load_verified_instrument_registry(registry_path)
    assert registry.artifact_sha256 == sha256_file(registry_path)
    assert tuple(item.symbol for item in registry.snapshots) == ("AAAUSDT", "BBBUSDT")
    assert registry.by_symbol()["BBBUSDT"].instrument_id == 9


def test_registry_rejects_duplicate_source_identity_and_tampered_receipt(tmp_path: Path) -> None:
    duplicate = deepcopy(inventory())
    duplicate["records"][1]["source_symbol_id"] = 1  # type: ignore[index]
    with pytest.raises(InstrumentRegistryError, match="not unique"):
        build_instrument_registry(duplicate, inventory_artifact_sha256="a" * 64)

    payload = build_instrument_registry(inventory(), inventory_artifact_sha256="a" * 64)
    registry_path, _ = publish_evidence(tmp_path / "registry.json", payload)
    registry_path.write_bytes(registry_path.read_bytes() + b" ")
    with pytest.raises(InstrumentRegistryError, match="receipt"):
        load_verified_instrument_registry(registry_path)


def test_registry_maps_source_zero_funding_sentinel_to_null() -> None:
    source = inventory()
    source["records"][0]["funding_interval_minutes"] = 0  # type: ignore[index]
    payload = build_instrument_registry(source, inventory_artifact_sha256="a" * 64)
    assert payload["records"][0]["funding_interval_minutes"] is None  # type: ignore[index]
