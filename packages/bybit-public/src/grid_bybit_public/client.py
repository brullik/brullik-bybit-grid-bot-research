"""Typed pagination and response validation for Bybit V5 public market data."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Literal, cast

from grid_bybit_public.transport import JsonTransport


class BybitPublicError(RuntimeError):
    pass


class BybitPublicClient:
    def __init__(self, transport: JsonTransport) -> None:
        self._transport = transport

    def _request(self, path: str, params: Mapping[str, str | int]) -> Mapping[str, Any]:
        payload = self._transport.get(path, params)
        ret_code = payload.get("retCode")
        if ret_code != 0:
            raise BybitPublicError(f"Bybit retCode={ret_code!r}: {payload.get('retMsg')!r}")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise BybitPublicError("Bybit response has no object result")
        return result

    def iter_instrument_pages(
        self,
        *,
        category: Literal["linear", "inverse"] = "linear",
        status: str | None = None,
        limit: int = 1000,
        max_pages: int = 10_000,
    ) -> Iterator[tuple[Mapping[str, Any], ...]]:
        if not 1 <= limit <= 1000:
            raise ValueError("instrument page limit must be in [1, 1000]")
        cursor = ""
        seen_cursors: set[str] = set()
        for _page_number in range(max_pages):
            params: dict[str, str | int] = {"category": category, "limit": limit}
            if status is not None:
                params["status"] = status
            if cursor:
                params["cursor"] = cursor
            result = self._request("/v5/market/instruments-info", params)
            raw_items = result.get("list")
            if not isinstance(raw_items, list) or any(
                not isinstance(item, dict) for item in raw_items
            ):
                raise BybitPublicError("instrument result.list must contain objects")
            yield tuple(raw_items)
            next_cursor = result.get("nextPageCursor") or ""
            if not isinstance(next_cursor, str):
                raise BybitPublicError("nextPageCursor must be text")
            if not next_cursor:
                return
            if next_cursor in seen_cursors:
                raise BybitPublicError("pagination cursor cycle detected")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        raise BybitPublicError(f"instrument pagination exceeded max_pages={max_pages}")

    def list_instruments(
        self,
        *,
        category: Literal["linear", "inverse"] = "linear",
        status: str | None = None,
    ) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            item
            for page in self.iter_instrument_pages(category=category, status=status)
            for item in page
        )

    def instrument(
        self,
        *,
        symbol: str,
        category: Literal["linear", "inverse"] = "linear",
    ) -> Mapping[str, Any]:
        if not symbol or symbol != symbol.upper() or not symbol.isalnum():
            raise ValueError("symbol must be non-empty uppercase alphanumeric text")
        result = self._request(
            "/v5/market/instruments-info",
            {"category": category, "symbol": symbol},
        )
        raw_items = result.get("list")
        if not isinstance(raw_items, list) or any(not isinstance(item, dict) for item in raw_items):
            raise BybitPublicError("instrument result.list must contain objects")
        matching = tuple(item for item in raw_items if item.get("symbol") == symbol)
        if len(matching) != 1:
            raise BybitPublicError(
                f"expected exactly one instrument for {symbol}, got {len(matching)}"
            )
        return cast(Mapping[str, Any], matching[0])

    def tickers(
        self,
        *,
        category: Literal["linear", "inverse"] = "linear",
    ) -> tuple[Mapping[str, Any], ...]:
        result = self._request("/v5/market/tickers", {"category": category})
        raw_items = result.get("list")
        if not isinstance(raw_items, list) or any(not isinstance(item, dict) for item in raw_items):
            raise BybitPublicError("ticker result.list must contain objects")
        symbols = [item.get("symbol") for item in raw_items]
        if any(not isinstance(symbol, str) or not symbol for symbol in symbols):
            raise BybitPublicError("every ticker must have a non-empty symbol")
        if len(symbols) != len(set(symbols)):
            raise BybitPublicError("ticker response contains duplicate symbols")
        return tuple(raw_items)

    def kline_page(
        self,
        *,
        kind: Literal["trade", "mark"],
        symbol: str,
        start_ms: int,
        end_ms: int,
        category: Literal["linear", "inverse"] = "linear",
        limit: int = 1000,
    ) -> tuple[tuple[str, ...], ...]:
        if start_ms < 0 or end_ms < start_ms:
            raise ValueError("invalid kline time range")
        if not 1 <= limit <= 1000:
            raise ValueError("kline page limit must be in [1, 1000]")
        path = "/v5/market/kline" if kind == "trade" else "/v5/market/mark-price-kline"
        result = self._request(
            path,
            {
                "category": category,
                "symbol": symbol,
                "interval": "1",
                "start": start_ms,
                "end": end_ms,
                "limit": limit,
            },
        )
        rows = _string_rows(result.get("list"), name=f"{kind} kline")
        expected_width = 7 if kind == "trade" else 5
        if any(len(row) != expected_width for row in rows):
            raise BybitPublicError(f"unexpected {kind} kline row width")
        return rows

    def iter_klines_backward(
        self,
        *,
        kind: Literal["trade", "mark"],
        symbol: str,
        start_ms: int,
        end_ms: int,
        category: Literal["linear", "inverse"] = "linear",
        limit: int = 1000,
        max_pages: int = 1_000_000,
    ) -> Iterator[tuple[str, ...]]:
        """Yield newest-to-oldest rows, advancing the inclusive end bound safely."""

        next_end = end_ms
        last_timestamp: int | None = None
        for _page_number in range(max_pages):
            rows = self.kline_page(
                kind=kind,
                symbol=symbol,
                start_ms=start_ms,
                end_ms=next_end,
                category=category,
                limit=limit,
            )
            if not rows:
                return
            timestamps = [int(row[0]) for row in rows]
            if timestamps != sorted(timestamps, reverse=True) or len(timestamps) != len(
                set(timestamps)
            ):
                raise BybitPublicError("kline page is not unique reverse chronological data")
            if last_timestamp is not None and timestamps[0] >= last_timestamp:
                raise BybitPublicError("kline pagination did not move backward")
            yield from rows
            oldest = timestamps[-1]
            if oldest <= start_ms:
                return
            last_timestamp = oldest
            next_end = oldest - 1
        raise BybitPublicError(f"kline pagination exceeded max_pages={max_pages}")

    def funding_page(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        category: Literal["linear", "inverse"] = "linear",
        limit: int = 200,
    ) -> tuple[Mapping[str, Any], ...]:
        if start_ms < 0 or end_ms < start_ms:
            raise ValueError("invalid funding time range")
        if not 1 <= limit <= 200:
            raise ValueError("funding page limit must be in [1, 200]")
        result = self._request(
            "/v5/market/funding/history",
            {
                "category": category,
                "symbol": symbol,
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": limit,
            },
        )
        items = result.get("list")
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise BybitPublicError("funding result.list must contain objects")
        return tuple(items)

    def iter_funding_backward(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        category: Literal["linear", "inverse"] = "linear",
        limit: int = 200,
        max_pages: int = 1_000_000,
    ) -> Iterator[Mapping[str, Any]]:
        """Yield newest-to-oldest funding events without overlapping inclusive pages."""

        next_end = end_ms
        last_timestamp: int | None = None
        for _page_number in range(max_pages):
            items = self.funding_page(
                symbol=symbol,
                start_ms=start_ms,
                end_ms=next_end,
                category=category,
                limit=limit,
            )
            if not items:
                return
            timestamps = [_funding_timestamp(item) for item in items]
            if timestamps != sorted(timestamps, reverse=True) or len(timestamps) != len(
                set(timestamps)
            ):
                raise BybitPublicError("funding page is not unique reverse chronological data")
            if last_timestamp is not None and timestamps[0] >= last_timestamp:
                raise BybitPublicError("funding pagination did not move backward")
            yield from items
            oldest = timestamps[-1]
            if oldest <= start_ms:
                return
            last_timestamp = oldest
            next_end = oldest - 1
        raise BybitPublicError(f"funding pagination exceeded max_pages={max_pages}")


def _string_rows(value: Any, *, name: str) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, list):
        raise BybitPublicError(f"{name} result.list must be an array")
    rows: list[tuple[str, ...]] = []
    for row in value:
        if not isinstance(row, list) or any(not isinstance(item, str) for item in row):
            raise BybitPublicError(f"{name} rows must be arrays of strings")
        rows.append(tuple(row))
    return tuple(rows)


def _funding_timestamp(item: Mapping[str, Any]) -> int:
    raw = item.get("fundingRateTimestamp")
    if not isinstance(raw, str):
        raise BybitPublicError("fundingRateTimestamp must be text")
    try:
        timestamp = int(raw)
    except ValueError as error:
        raise BybitPublicError("fundingRateTimestamp must be integer text") from error
    if timestamp < 0:
        raise BybitPublicError("fundingRateTimestamp must be non-negative")
    return timestamp
