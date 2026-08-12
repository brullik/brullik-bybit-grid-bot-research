"""Assess official Bybit bulk products and bound required REST backfill work."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from grid_bybit_public import CATALOG_ENDPOINT, HistoricalDataProduct
from grid_contracts.canonical import canonical_sha256

THEORETICAL_INSTRUMENTS = 700
THEORETICAL_INSTRUMENT_MINUTES = 3_681_644_400
TEN_YEAR_MINUTES_PER_INSTRUMENT = THEORETICAL_INSTRUMENT_MINUTES // THEORETICAL_INSTRUMENTS
MINUTE_MS = 60_000
MARK_PAGE_LIMIT = 1_000
FUNDING_PAGE_LIMIT = 200
MIN_OBSERVED_FUNDING_INTERVAL_MINUTES = 60
PLANNING_REQUESTS_PER_SECOND = 10
DEFAULT_HTTP_IP_REQUESTS_PER_SECOND = 120


def _ceil_div(numerator: int, denominator: int) -> int:
    if numerator < 0 or denominator <= 0:
        raise ValueError("ceil-div inputs must be non-negative with a positive denominator")
    return (numerator + denominator - 1) // denominator


def _snapshot_end_ms(inventory: Mapping[str, Any]) -> int:
    raw = inventory.get("fetched_at_utc")
    if not isinstance(raw, str) or not raw.endswith("Z"):
        raise ValueError("inventory fetched_at_utc must be UTC text")
    try:
        value = datetime.fromisoformat(raw.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise ValueError("inventory fetched_at_utc is invalid") from error
    if value.tzinfo != UTC:
        raise ValueError("inventory fetched_at_utc must resolve to UTC")
    return int(value.timestamp() * 1_000)


def _inventory_backfill(inventory: Mapping[str, Any]) -> dict[str, Any]:
    raw_records = inventory.get("records")
    if inventory.get("evidence_schema") != "grid.bybit-public-inventory/v1" or not isinstance(
        raw_records, list
    ):
        raise ValueError("unsupported instrument inventory evidence")
    if any(not isinstance(record, Mapping) for record in raw_records):
        raise ValueError("instrument inventory records must be objects")
    records = [
        record
        for record in raw_records
        if record.get("contract_type") == "LinearPerpetual"
        and record.get("quote_coin") == "USDT"
        and record.get("settle_coin") == "USDT"
    ]
    if not records:
        raise ValueError("instrument inventory contains no USDT linear perpetual records")
    symbols = [record.get("symbol") for record in records]
    if any(not isinstance(symbol, str) or not symbol for symbol in symbols) or len(symbols) != len(
        set(symbols)
    ):
        raise ValueError("inventory USDT perpetual symbols must be unique non-empty text")

    end_ms = _snapshot_end_ms(inventory)
    start_ms = end_ms - TEN_YEAR_MINUTES_PER_INSTRUMENT * MINUTE_MS
    mark_rows = 0
    mark_requests = 0
    current_funding_events = 0
    current_funding_requests = 0
    conservative_funding_events = 0
    conservative_funding_requests = 0
    instruments_with_duration = 0
    interval_counts: Counter[int] = Counter()
    status_counts: Counter[str] = Counter()
    for record in records:
        launch_ms = record.get("launch_time_ms")
        delivery_ms = record.get("delivery_time_ms")
        funding_interval = record.get("funding_interval_minutes")
        status = record.get("status")
        if (
            not isinstance(launch_ms, int)
            or (delivery_ms is not None and not isinstance(delivery_ms, int))
            or not isinstance(funding_interval, int)
            or funding_interval <= 0
            or not isinstance(status, str)
            or not status
        ):
            raise ValueError("inventory record has invalid lifecycle or funding metadata")
        interval_counts[funding_interval] += 1
        status_counts[status] += 1
        active_start = max(start_ms, launch_ms)
        active_end = min(end_ms, delivery_ms) if delivery_ms not in (None, 0) else end_ms
        duration_minutes = (
            _ceil_div(active_end - active_start, MINUTE_MS) if active_end > active_start else 0
        )
        if not duration_minutes:
            continue
        instruments_with_duration += 1
        mark_rows += duration_minutes
        mark_requests += _ceil_div(duration_minutes, MARK_PAGE_LIMIT)
        funding_events = _ceil_div(duration_minutes, funding_interval)
        current_funding_events += funding_events
        current_funding_requests += _ceil_div(funding_events, FUNDING_PAGE_LIMIT)
        conservative_events = _ceil_div(duration_minutes, MIN_OBSERVED_FUNDING_INTERVAL_MINUTES)
        conservative_funding_events += conservative_events
        conservative_funding_requests += _ceil_div(conservative_events, FUNDING_PAGE_LIMIT)

    return {
        "conservative_observed_minimum_funding_interval": {
            "estimated_events": conservative_funding_events,
            "estimated_requests": conservative_funding_requests,
            "interval_minutes": MIN_OBSERVED_FUNDING_INTERVAL_MINUTES,
        },
        "current_interval_funding": {
            "estimated_events": current_funding_events,
            "estimated_requests": current_funding_requests,
        },
        "horizon_end_ms": end_ms,
        "horizon_start_ms": start_ms,
        "instruments_with_observed_duration": instruments_with_duration,
        "mark_price_1m": {
            "estimated_requests": mark_requests,
            "estimated_rows": mark_rows,
        },
        "observed_funding_interval_counts": {
            str(interval): count for interval, count in sorted(interval_counts.items())
        },
        "status_counts": dict(sorted(status_counts.items())),
        "usdt_linear_perpetual_records": len(records),
    }


def _theoretical_rest_envelope() -> dict[str, Any]:
    mark_requests = THEORETICAL_INSTRUMENTS * _ceil_div(
        TEN_YEAR_MINUTES_PER_INSTRUMENT, MARK_PAGE_LIMIT
    )
    funding_events_per_instrument = _ceil_div(
        TEN_YEAR_MINUTES_PER_INSTRUMENT, MIN_OBSERVED_FUNDING_INTERVAL_MINUTES
    )
    funding_requests = THEORETICAL_INSTRUMENTS * _ceil_div(
        funding_events_per_instrument, FUNDING_PAGE_LIMIT
    )
    combined_requests = mark_requests + funding_requests
    return {
        "combined_requests": combined_requests,
        "funding": {
            "estimated_events": funding_events_per_instrument * THEORETICAL_INSTRUMENTS,
            "estimated_requests": funding_requests,
            "interval_minutes": MIN_OBSERVED_FUNDING_INTERVAL_MINUTES,
            "page_limit": FUNDING_PAGE_LIMIT,
        },
        "instrument_count": THEORETICAL_INSTRUMENTS,
        "instrument_minutes": THEORETICAL_INSTRUMENT_MINUTES,
        "mark_price_1m": {
            "estimated_requests": mark_requests,
            "page_limit": MARK_PAGE_LIMIT,
            "rows": THEORETICAL_INSTRUMENT_MINUTES,
        },
        "minimum_request_only_seconds_at_default_ip_limit": _ceil_div(
            combined_requests, DEFAULT_HTTP_IP_REQUESTS_PER_SECOND
        ),
        "planning_request_only_seconds_at_10_per_second": _ceil_div(
            combined_requests, PLANNING_REQUESTS_PER_SECOND
        ),
    }


def _normalized_products(products: Sequence[HistoricalDataProduct]) -> list[dict[str, Any]]:
    if not products:
        raise ValueError("historical product catalog must not be empty")
    product_ids = [product.product_id for product in products]
    if len(product_ids) != len(set(product_ids)):
        raise ValueError("historical product catalog contains duplicate IDs")
    return [
        {
            "business_types": list(product.business_types),
            "category": product.category,
            "description": product.description,
            "intervals": list(product.intervals),
            "name": product.name,
            "period_count": product.period_count,
            "product_id": product.product_id,
        }
        for product in sorted(products, key=lambda product: product.product_id)
    ]


def build_history_source_assessment(
    products: Sequence[HistoricalDataProduct],
    inventory: Mapping[str, Any],
    *,
    command: str,
    inventory_artifact: str,
    inventory_artifact_sha256: str,
) -> dict[str, Any]:
    normalized = _normalized_products(products)

    def product_matches(term: str, business_type: str) -> bool:
        return any(
            term in f"{product['product_id']} {product['name']}".casefold()
            and business_type in product["business_types"]
            for product in normalized
        )

    funding_products = [
        product["product_id"]
        for product in normalized
        if "fund" in f"{product['product_id']} {product['name']}".casefold()
    ]
    contract_mark_bulk = product_matches("mark", "contract")
    contract_funding_bulk = product_matches("fund", "contract")
    required_rest_datasets = []
    if not contract_funding_bulk:
        required_rest_datasets.append("funding")
    if not contract_mark_bulk:
        required_rest_datasets.append("linear-contract-mark-price-1m")
    payload: dict[str, Any] = {
        "assessment": {
            "any_funding_bulk_advertised": bool(funding_products),
            "contract_funding_bulk_advertised": contract_funding_bulk,
            "contract_mark_price_bulk_advertised": contract_mark_bulk,
            "contract_trade_bulk_advertised": product_matches("trad", "contract"),
            "funding_product_ids": funding_products,
            "option_mark_price_bulk_advertised": product_matches("mark", "option"),
            "required_rest_datasets": required_rest_datasets,
            "semantics": (
                "The observed official catalog advertises mark-price klines for options only "
                "and advertises no funding product. Linear-contract mark-price 1m and funding "
                "therefore remain REST backfill/update datasets unless a later catalog version "
                "adds an explicit compatible bulk product."
            ),
        },
        "catalog": {
            "product_count": len(normalized),
            "products": normalized,
        },
        "command": command,
        "content_sha256": "",
        "evidence_schema": "grid.bybit-history-source-assessment/v1",
        "fetched_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "inventory_backfill_estimate": _inventory_backfill(inventory),
        "inventory_source": {
            "artifact": inventory_artifact,
            "artifact_sha256": inventory_artifact_sha256,
            "evidence_schema": inventory["evidence_schema"],
            "fetched_at_utc": inventory["fetched_at_utc"],
            "inventory_status": inventory.get("inventory_status"),
        },
        "limitations": [
            (
                "The frontend catalog endpoint is public and official but is not a versioned "
                "V5 API contract."
            ),
            (
                "Catalog absence proves not-advertised-at-observation-time, not permanent "
                "nonexistence."
            ),
            (
                "The current inventory is partial and omits historical symbols absent from "
                "the snapshot."
            ),
            "Current funding intervals and lifecycle fields are not dated historical metadata.",
            (
                "Request-only time excludes latency, throttling headroom, retry, validation, "
                "and publication."
            ),
        ],
        "sources": {
            "catalog_endpoint": CATALOG_ENDPOINT,
            "funding_history_documentation": (
                "https://bybit-exchange.github.io/docs/v5/market/history-fund-rate"
            ),
            "historical_data_page": "https://www.bybit.com/en/derivative-activity/history-data",
            "mark_price_documentation": (
                "https://bybit-exchange.github.io/docs/v5/market/mark-kline"
            ),
            "rate_limit_documentation": "https://bybit-exchange.github.io/docs/v5/rate-limit",
        },
        "status": "catalog-observed-rest-capacity-bounded",
        "theoretical_rest_envelope": _theoretical_rest_envelope(),
    }
    hash_input = dict(payload)
    hash_input.pop("content_sha256")
    payload["content_sha256"] = canonical_sha256(hash_input)
    return payload
