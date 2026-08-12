"""Build immutable evidence describing official Bybit bulk archive coverage."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import Any

from grid_bybit_public import BybitArchiveIndex
from grid_contracts.canonical import canonical_sha256


def build_archive_inventory(index: BybitArchiveIndex, symbols: tuple[str, ...]) -> dict[str, Any]:
    products = index.products()
    archive_symbols = index.trading_symbols()
    archive_symbol_set = set(archive_symbols)
    coverage = [dataclasses.asdict(index.trade_coverage(symbol)) for symbol in symbols]
    payload: dict[str, Any] = {
        "archive_symbol_count": len(archive_symbols),
        "coverage": coverage,
        "evidence_schema": "grid.bybit-archive-inventory/v1",
        "fetched_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "products": list(products),
        "requested_symbols": list(symbols),
        "requested_symbols_present": {symbol: symbol in archive_symbol_set for symbol in symbols},
        "source": "https://public.bybit.com/",
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload
