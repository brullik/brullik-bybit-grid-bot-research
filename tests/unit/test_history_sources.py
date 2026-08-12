from __future__ import annotations

from datetime import UTC, datetime

import pytest
from grid_bybit_public.historical_catalog import (
    CATALOG_ENDPOINT,
    BybitHistoricalDataCatalog,
    HistoricalCatalogError,
    HistoricalDataProduct,
)
from grid_contracts.canonical import canonical_sha256
from grid_data.history_sources import (
    THEORETICAL_INSTRUMENT_MINUTES,
    build_history_source_assessment,
)


def product(
    product_id: str,
    *,
    business_types: tuple[str, ...],
    name: str | None = None,
) -> HistoricalDataProduct:
    return HistoricalDataProduct(
        product_id=product_id,
        name=name or product_id,
        description=f"{product_id} data",
        category="quote" if "trade" not in product_id else "trade",
        business_types=business_types,
        intervals=("daily",),
        period_count=0,
    )


def catalog_response() -> dict[str, object]:
    return {
        "ret_code": 0,
        "result": {
            "products": [
                {
                    "id": "mark_kline",
                    "productName": "Mark Price Kline",
                    "productDesc": "Bybit history mark price kline data",
                    "intervals": "daily",
                    "category": "quote",
                    "bizTypes": "option",
                    "periods": [],
                },
                {
                    "id": "trade",
                    "productName": "Public Trading History",
                    "productDesc": "Bybit public trading history data",
                    "intervals": "",
                    "category": "trade",
                    "bizTypes": "spot,contract,option",
                    "periods": [],
                },
            ]
        },
    }


def test_historical_catalog_normalizes_and_sorts_official_products() -> None:
    calls: list[str] = []

    def fetch(url: str) -> dict[str, object]:
        calls.append(url)
        return catalog_response()

    products = BybitHistoricalDataCatalog(fetch_json=fetch).products()

    assert calls == [CATALOG_ENDPOINT]
    assert [item.product_id for item in products] == ["mark_kline", "trade"]
    assert products[0].business_types == ("option",)
    assert products[1].business_types == ("contract", "option", "spot")
    assert products[1].intervals == ()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.update(ret_code=10001), "ret_code"),
        (
            lambda payload: payload["result"]["products"].append(  # type: ignore[index,union-attr]
                dict(payload["result"]["products"][0])  # type: ignore[index,union-attr]
            ),
            "duplicate",
        ),
        (
            lambda payload: payload["result"]["products"][0].update(  # type: ignore[index,union-attr]
                bizTypes="option,unknown"
            ),
            "business types",
        ),
    ],
)
def test_historical_catalog_rejects_malformed_responses(mutation: object, message: str) -> None:
    payload = catalog_response()
    assert callable(mutation)
    mutation(payload)

    with pytest.raises(HistoricalCatalogError, match=message):
        BybitHistoricalDataCatalog(fetch_json=lambda _url: payload).products()


def test_history_source_assessment_bounds_per_symbol_rest_pages() -> None:
    end = datetime(2026, 1, 11, tzinfo=UTC)
    end_ms = int(end.timestamp() * 1_000)
    minute = 60_000
    inventory = {
        "evidence_schema": "grid.bybit-public-inventory/v1",
        "fetched_at_utc": end.isoformat().replace("+00:00", "Z"),
        "inventory_status": "partial",
        "records": [
            {
                "contract_type": "LinearPerpetual",
                "delivery_time_ms": 0,
                "funding_interval_minutes": 60,
                "launch_time_ms": end_ms - 2_000 * minute,
                "quote_coin": "USDT",
                "settle_coin": "USDT",
                "status": "Trading",
                "symbol": "AAAUSDT",
            },
            {
                "contract_type": "LinearPerpetual",
                "delivery_time_ms": end_ms - minute,
                "funding_interval_minutes": 480,
                "launch_time_ms": end_ms - 1_001 * minute,
                "quote_coin": "USDT",
                "settle_coin": "USDT",
                "status": "Closed",
                "symbol": "BBBUSDT",
            },
            {
                "contract_type": "LinearPerpetual",
                "delivery_time_ms": None,
                "funding_interval_minutes": 480,
                "launch_time_ms": end_ms + minute,
                "quote_coin": "USDT",
                "settle_coin": "USDT",
                "status": "PreLaunch",
                "symbol": "FUTUREUSDT",
            },
        ],
    }
    payload = build_history_source_assessment(
        (
            product("trade", business_types=("contract", "option", "spot")),
            product(
                "mark_kline",
                business_types=("option",),
                name="Mark Price Kline",
            ),
        ),
        inventory,
        command="grid-data history-source-assessment",
        inventory_artifact="inventory.json",
        inventory_artifact_sha256="a" * 64,
    )

    assert payload["assessment"]["contract_trade_bulk_advertised"] is True
    assert payload["assessment"]["contract_mark_price_bulk_advertised"] is False
    assert payload["assessment"]["contract_funding_bulk_advertised"] is False
    assert payload["assessment"]["required_rest_datasets"] == [
        "funding",
        "linear-contract-mark-price-1m",
    ]
    estimate = payload["inventory_backfill_estimate"]
    assert estimate["instruments_with_observed_duration"] == 2
    assert estimate["mark_price_1m"] == {
        "estimated_requests": 3,
        "estimated_rows": 3_000,
    }
    assert estimate["current_interval_funding"] == {
        "estimated_events": 37,
        "estimated_requests": 2,
    }
    assert estimate["conservative_observed_minimum_funding_interval"] == {
        "estimated_events": 51,
        "estimated_requests": 2,
        "interval_minutes": 60,
    }
    assert payload["theoretical_rest_envelope"]["instrument_minutes"] == (
        THEORETICAL_INSTRUMENT_MINUTES
    )
    hash_input = dict(payload)
    embedded_hash = hash_input.pop("content_sha256")
    assert embedded_hash == canonical_sha256(hash_input)


def test_history_source_assessment_rejects_non_utc_inventory_time() -> None:
    inventory = {
        "evidence_schema": "grid.bybit-public-inventory/v1",
        "fetched_at_utc": "2026-01-01T00:00:00+00:00",
        "records": [
            {
                "contract_type": "LinearPerpetual",
                "delivery_time_ms": 0,
                "funding_interval_minutes": 480,
                "launch_time_ms": 1,
                "quote_coin": "USDT",
                "settle_coin": "USDT",
                "status": "Trading",
                "symbol": "BTCUSDT",
            }
        ],
    }
    with pytest.raises(ValueError, match="UTC text"):
        build_history_source_assessment(
            (product("trade", business_types=("contract",)),),
            inventory,
            command="test",
            inventory_artifact="inventory.json",
            inventory_artifact_sha256="a" * 64,
        )
