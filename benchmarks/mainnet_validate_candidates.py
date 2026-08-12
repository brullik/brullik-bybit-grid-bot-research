"""Build a public-data-only shortlist for minimum-capital mainnet validation."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from grid_bybit_public.client import BybitPublicClient
from grid_bybit_public.transport import UrllibJsonTransport
from grid_contracts.canonical import decimal_text
from grid_data.evidence import preflight_evidence, publish_evidence

MAX_CANDIDATES = 3
MAX_MARK_PRICE = Decimal("10")
MAX_MINIMUM_ORDER_VALUE = Decimal("5")
MAX_SPREAD_BPS = Decimal("5")
MAX_24H_RANGE_RATIO = Decimal("0.15")
MIN_MARK_PRICE = Decimal("0.01")
MIN_TURNOVER_24H = Decimal("50000000")
RANGE_PADDING = Decimal("0.01")


def _decimal(value: Any, name: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be exact decimal text")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{name} is not decimal text") from error
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return parsed


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _tick_round(value: Decimal, tick: Decimal, rounding: str) -> Decimal:
    steps = (value / tick).to_integral_value(rounding=rounding)
    return steps * tick


def _candidate(
    instrument: Mapping[str, Any], ticker: Mapping[str, Any]
) -> tuple[tuple[Decimal, Decimal, str], dict[str, Any]] | None:
    symbol = instrument.get("symbol")
    if not isinstance(symbol, str) or not symbol:
        raise ValueError("instrument symbol must be non-empty text")
    if (
        instrument.get("quoteCoin") != "USDT"
        or instrument.get("contractType") != "LinearPerpetual"
        or instrument.get("status") != "Trading"
    ):
        return None
    price_filter = _mapping(instrument.get("priceFilter"), f"{symbol}.priceFilter")
    lot_filter = _mapping(instrument.get("lotSizeFilter"), f"{symbol}.lotSizeFilter")
    tick_size = _decimal(price_filter.get("tickSize"), f"{symbol}.tickSize")
    min_notional = _decimal(lot_filter.get("minNotionalValue"), f"{symbol}.minNotionalValue")
    min_order_qty = _decimal(lot_filter.get("minOrderQty"), f"{symbol}.minOrderQty")
    mark_price = _decimal(ticker.get("markPrice"), f"{symbol}.markPrice")
    low_24h = _decimal(ticker.get("lowPrice24h"), f"{symbol}.lowPrice24h")
    high_24h = _decimal(ticker.get("highPrice24h"), f"{symbol}.highPrice24h")
    bid = _decimal(ticker.get("bid1Price"), f"{symbol}.bid1Price")
    ask = _decimal(ticker.get("ask1Price"), f"{symbol}.ask1Price")
    turnover = _decimal(ticker.get("turnover24h"), f"{symbol}.turnover24h")
    if high_24h < low_24h or ask < bid:
        raise ValueError(f"{symbol} ticker bounds are inverted")
    minimum_order_value = max(min_notional, min_order_qty * mark_price)
    spread_bps = (ask - bid) / mark_price * Decimal(10_000)
    range_ratio = (high_24h - low_24h) / mark_price
    if not (
        MIN_MARK_PRICE <= mark_price <= MAX_MARK_PRICE
        and minimum_order_value <= MAX_MINIMUM_ORDER_VALUE
        and turnover >= MIN_TURNOVER_24H
        and spread_bps <= MAX_SPREAD_BPS
        and range_ratio <= MAX_24H_RANGE_RATIO
    ):
        return None

    lower = _tick_round(low_24h * (Decimal(1) - RANGE_PADDING), tick_size, ROUND_FLOOR)
    upper = _tick_round(high_24h * (Decimal(1) + RANGE_PADDING), tick_size, ROUND_CEILING)
    stop = _tick_round(lower * (Decimal(1) - RANGE_PADDING), tick_size, ROUND_FLOOR)
    take = _tick_round(upper * (Decimal(1) + RANGE_PADDING), tick_size, ROUND_CEILING)
    if min(stop, lower) <= 0 or not stop < lower < upper < take:
        raise ValueError(f"{symbol} rounded validation range is not strictly ordered")

    result = {
        "market_observation": {
            "high_price_24h": decimal_text(high_24h),
            "low_price_24h": decimal_text(low_24h),
            "mark_price": decimal_text(mark_price),
            "minimum_order_value": decimal_text(minimum_order_value),
            "range_24h_ratio": decimal_text(range_ratio),
            "spread_bps": decimal_text(spread_bps),
            "tick_size": decimal_text(tick_size),
            "turnover_24h": decimal_text(turnover),
        },
        "symbol": symbol,
        "validate_request": {
            "cell_number": 2,
            "leverage": "1",
            "max_price": decimal_text(upper),
            "min_price": decimal_text(lower),
            "stop_loss_price": decimal_text(stop),
            "take_profit_price": decimal_text(take),
        },
    }
    return (minimum_order_value, -turnover, symbol), result


def build_shortlist(
    instruments: Sequence[Mapping[str, Any]],
    tickers: Sequence[Mapping[str, Any]],
    *,
    observed_at_utc: str,
) -> dict[str, Any]:
    tickers_by_symbol: dict[str, Mapping[str, Any]] = {}
    for ticker in tickers:
        symbol = ticker.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("ticker symbol must be non-empty text")
        if symbol in tickers_by_symbol:
            raise ValueError(f"duplicate ticker symbol: {symbol}")
        tickers_by_symbol[symbol] = ticker

    ranked: list[tuple[tuple[Decimal, Decimal, str], dict[str, Any]]] = []
    for instrument in instruments:
        symbol = instrument.get("symbol")
        matched_ticker = tickers_by_symbol.get(symbol) if isinstance(symbol, str) else None
        if matched_ticker is None:
            continue
        candidate = _candidate(instrument, matched_ticker)
        if candidate is not None:
            ranked.append(candidate)
    ranked.sort(key=lambda item: item[0])
    selected = [candidate for _rank, candidate in ranked[:MAX_CANDIDATES]]
    if len(selected) != MAX_CANDIDATES:
        raise ValueError(
            f"public filter produced {len(selected)} candidates; expected {MAX_CANDIDATES}"
        )
    return {
        "candidate_count": len(selected),
        "candidates": selected,
        "evidence_schema": "grid.mainnet-validate-candidates/v1",
        "filter": {
            "candidate_limit": MAX_CANDIDATES,
            "maximum_24h_range_ratio": decimal_text(MAX_24H_RANGE_RATIO),
            "maximum_mark_price": decimal_text(MAX_MARK_PRICE),
            "maximum_minimum_order_value": decimal_text(MAX_MINIMUM_ORDER_VALUE),
            "maximum_spread_bps": decimal_text(MAX_SPREAD_BPS),
            "minimum_mark_price": decimal_text(MIN_MARK_PRICE),
            "minimum_turnover_24h": decimal_text(MIN_TURNOVER_24H),
            "ranking": "minimum_order_value_asc,turnover_24h_desc,symbol_asc",
        },
        "observed_at_utc": observed_at_utc,
        "source": {
            "authentication": "none",
            "instrument_endpoint": "/v5/market/instruments-info",
            "ticker_endpoint": "/v5/market/tickers",
        },
        "status": "public-shortlist-only",
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    output, _receipt = preflight_evidence(args.output, force=args.force)
    client = BybitPublicClient(UrllibJsonTransport())
    instruments = client.list_instruments(category="linear")
    tickers = client.tickers(category="linear")
    payload = build_shortlist(
        instruments,
        tickers,
        observed_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    publish_evidence(output, payload, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
