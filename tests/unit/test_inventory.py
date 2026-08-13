from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

import pytest
from grid_bybit_public import BybitPublicError
from grid_data.inventory import (
    INSTRUMENT_STATUS_DOCUMENTATION,
    INSTRUMENT_STATUS_POLICY,
    STATUSES,
    build_public_inventory,
)


def _instrument(status: str, *, symbol_id: int) -> dict[str, object]:
    return {
        "baseCoin": f"BASE{symbol_id}",
        "contractType": "LinearPerpetual",
        "deliveryTime": "0",
        "fundingInterval": "480",
        "launchTime": "1704067200000",
        "leverageFilter": {"maxLeverage": "25", "minLeverage": "1"},
        "lotSizeFilter": {
            "maxOrderQty": "100000",
            "minOrderQty": "1",
            "qtyStep": "1",
        },
        "priceFilter": {"tickSize": "0.0001"},
        "quoteCoin": "USDT",
        "settleCoin": "USDT",
        "status": status,
        "symbol": f"BASE{symbol_id}USDT",
        "symbolId": symbol_id,
    }


class InventoryClient:
    def __init__(
        self,
        *,
        rejected: frozenset[str] = frozenset(),
        response_status: Mapping[str, str] | None = None,
    ) -> None:
        self.rejected = rejected
        self.response_status = dict(response_status or {})
        self.calls: list[str] = []

    def iter_instrument_pages(
        self,
        *,
        category: str = "linear",
        status: str | None = None,
        limit: int = 1000,
        max_pages: int = 10_000,
    ) -> Iterator[tuple[Mapping[str, Any], ...]]:
        del category, limit, max_pages
        assert status is not None
        self.calls.append(status)
        if status in self.rejected:
            raise BybitPublicError(f"rejected {status}")
        actual_status = self.response_status.get(status, status)
        yield (_instrument(actual_status, symbol_id=self.calls.index(status) + 1),)


def test_inventory_queries_exact_current_official_linear_status_enum() -> None:
    client = InventoryClient()

    payload = build_public_inventory(client)

    assert STATUSES == ("PreLaunch", "Trading", "Delivering", "Closed")
    assert client.calls == list(STATUSES)
    assert "Settling" not in client.calls
    assert payload["inventory_status"] == "complete"
    assert payload["source"] == {
        "category": "linear",
        "endpoint": "/v5/market/instruments-info",
        "page_limit": 1000,
        "status_policy": {
            "documentation": INSTRUMENT_STATUS_DOCUMENTATION,
            "identity": INSTRUMENT_STATUS_POLICY,
        },
        "statuses": list(STATUSES),
    }


def test_inventory_remains_partial_when_a_policy_status_is_rejected() -> None:
    payload = build_public_inventory(InventoryClient(rejected=frozenset({"Delivering"})))

    assert payload["inventory_status"] == "partial"
    assert payload["summary"]["status_queries"]["Delivering"]["result"] == "rejected"


def test_inventory_rejects_status_filter_leakage() -> None:
    with pytest.raises(ValueError, match="outside the requested"):
        build_public_inventory(InventoryClient(response_status={"Trading": "Closed"}))
