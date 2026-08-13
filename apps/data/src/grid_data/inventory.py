"""Bybit public-universe feasibility inventory."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any, Protocol

from grid_bybit_public import BybitPublicError
from grid_contracts.canonical import canonical_sha256

INSTRUMENT_STATUS_POLICY = "bybit-v5-linear-status-enum-2026-08-13"
INSTRUMENT_STATUS_DOCUMENTATION = "https://bybit-exchange.github.io/docs/v5/enum#status"
STATUSES = ("PreLaunch", "Trading", "Delivering", "Closed")


class InstrumentPageClient(Protocol):
    def iter_instrument_pages(
        self,
        *,
        status: str | None = None,
    ) -> Iterator[tuple[Mapping[str, Any], ...]]: ...


def build_public_inventory(client: InstrumentPageClient) -> dict[str, Any]:
    records: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    status_queries: dict[str, dict[str, Any]] = {}
    for status in STATUSES:
        page_count = 0
        record_count = 0
        try:
            for page in client.iter_instrument_pages(status=status):
                page_count += 1
                record_count += len(page)
                for item in page:
                    symbol = _required_text(item, "symbol")
                    source_symbol_id = str(item.get("symbolId", ""))
                    actual_status = _required_text(item, "status")
                    if actual_status != status:
                        raise ValueError(
                            "Bybit instrument status filter returned a row outside the "
                            f"requested {status!r} partition: {actual_status!r}"
                        )
                    key = (symbol, source_symbol_id, actual_status)
                    records[key] = item
        except BybitPublicError as error:
            # An unsupported category/status combination is itself feasibility evidence.
            status_queries[status] = {
                "error": str(error),
                "pages": page_count,
                "records": record_count,
                "result": "rejected",
            }
        else:
            status_queries[status] = {
                "pages": page_count,
                "records": record_count,
                "result": "accepted",
            }

    normalized = [_normalize_instrument(item) for item in records.values()]
    normalized.sort(key=lambda item: (item["symbol"], item["status"], item["source_symbol_id"]))
    usdt_perpetual = [
        item
        for item in normalized
        if item["settle_coin"] == "USDT" and item["contract_type"] == "LinearPerpetual"
    ]
    summary = {
        "contract_type_counts": dict(
            sorted(Counter(item["contract_type"] for item in normalized).items())
        ),
        "status_queries": status_queries,
        "status_counts": dict(sorted(Counter(item["status"] for item in normalized).items())),
        "total_linear_records": len(normalized),
        "usdt_linear_perpetual_records": len(usdt_perpetual),
    }
    evidence: dict[str, Any] = {
        "evidence_schema": "grid.bybit-public-inventory/v1",
        "fetched_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "inventory_status": (
            "partial"
            if any(query["result"] == "rejected" for query in status_queries.values())
            else "complete"
        ),
        "records": normalized,
        "source": {
            "category": "linear",
            "endpoint": "/v5/market/instruments-info",
            "page_limit": 1000,
            "status_policy": {
                "documentation": INSTRUMENT_STATUS_DOCUMENTATION,
                "identity": INSTRUMENT_STATUS_POLICY,
            },
            "statuses": list(STATUSES),
        },
        "summary": summary,
    }
    evidence["content_sha256"] = canonical_sha256(evidence)
    return evidence


def _normalize_instrument(item: Mapping[str, Any]) -> dict[str, Any]:
    price_filter = _mapping(item, "priceFilter")
    lot_filter = _mapping(item, "lotSizeFilter")
    leverage_filter = _mapping(item, "leverageFilter")
    return {
        "base_coin": _required_text(item, "baseCoin"),
        "contract_type": _required_text(item, "contractType"),
        "delivery_time_ms": _optional_int(item.get("deliveryTime")),
        "funding_interval_minutes": _optional_int(item.get("fundingInterval")),
        "launch_time_ms": _required_int(item, "launchTime"),
        "max_leverage": _required_text(leverage_filter, "maxLeverage"),
        "max_order_quantity": _required_text(lot_filter, "maxOrderQty"),
        "min_leverage": _required_text(leverage_filter, "minLeverage"),
        "min_order_quantity": _required_text(lot_filter, "minOrderQty"),
        "quantity_step": _required_text(lot_filter, "qtyStep"),
        "quote_coin": _required_text(item, "quoteCoin"),
        "settle_coin": _required_text(item, "settleCoin"),
        "source_payload_sha256": canonical_sha256(item),
        "source_symbol_id": _required_int(item, "symbolId"),
        "status": _required_text(item, "status"),
        "symbol": _required_text(item, "symbol"),
        "tick_size": _required_text(price_filter, "tickSize"),
    }


def _mapping(item: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = item.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Bybit instrument field {key!r} must be an object")
    return value


def _required_text(item: Mapping[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Bybit instrument field {key!r} must be non-empty text")
    return value


def _required_int(item: Mapping[str, Any], key: str) -> int:
    value = _optional_int(item.get(key))
    if value is None:
        raise ValueError(f"Bybit instrument field {key!r} must be an integer string")
    return value


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("expected an integer-compatible Bybit value") from error
    if result < 0:
        raise ValueError("timestamps and identifiers must be non-negative")
    return result
