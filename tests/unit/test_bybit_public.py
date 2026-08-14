from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from grid_bybit_public.client import BybitPublicClient, BybitPublicError


class QueueTransport:
    def __init__(self, responses: list[Mapping[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, Mapping[str, str | int]]] = []

    def get(self, path: str, params: Mapping[str, str | int]) -> Mapping[str, Any]:
        self.calls.append((path, params))
        return self.responses.pop(0)


def response(result: Mapping[str, Any]) -> Mapping[str, Any]:
    return {"retCode": 0, "retMsg": "OK", "result": result}


def test_instrument_cursor_pagination_uses_every_page() -> None:
    transport = QueueTransport(
        [
            response({"list": [{"symbol": "BTCUSDT"}], "nextPageCursor": "cursor-2"}),
            response({"list": [{"symbol": "ETHUSDT"}], "nextPageCursor": ""}),
        ]
    )
    client = BybitPublicClient(transport)
    assert [row["symbol"] for row in client.list_instruments()] == ["BTCUSDT", "ETHUSDT"]
    assert transport.calls[0][1] == {"category": "linear", "limit": 1000}
    assert transport.calls[1][1]["cursor"] == "cursor-2"


def test_instrument_cursor_cycle_fails_closed() -> None:
    transport = QueueTransport(
        [
            response({"list": [], "nextPageCursor": "same"}),
            response({"list": [], "nextPageCursor": "same"}),
        ]
    )
    with pytest.raises(BybitPublicError, match="cycle"):
        tuple(BybitPublicClient(transport).iter_instrument_pages())


def test_exact_instrument_lookup_requires_one_matching_symbol() -> None:
    transport = QueueTransport(
        [response({"list": [{"symbol": "BTCUSDT"}], "nextPageCursor": "ignored"})]
    )
    result = BybitPublicClient(transport).instrument(symbol="BTCUSDT")
    assert result["symbol"] == "BTCUSDT"
    assert transport.calls == [
        ("/v5/market/instruments-info", {"category": "linear", "symbol": "BTCUSDT"})
    ]


def test_exact_instrument_lookup_rejects_ambiguous_result() -> None:
    transport = QueueTransport(
        [
            response(
                {
                    "list": [
                        {"symbol": "BTCUSDT"},
                        {"symbol": "BTCUSDT"},
                    ]
                }
            )
        ]
    )
    with pytest.raises(BybitPublicError, match="exactly one"):
        BybitPublicClient(transport).instrument(symbol="BTCUSDT")


def test_tickers_require_unique_non_empty_symbols() -> None:
    transport = QueueTransport([response({"list": [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}]})])
    assert [row["symbol"] for row in BybitPublicClient(transport).tickers()] == [
        "BTCUSDT",
        "ETHUSDT",
    ]
    assert transport.calls == [("/v5/market/tickers", {"category": "linear"})]

    duplicate_transport = QueueTransport(
        [response({"list": [{"symbol": "BTCUSDT"}, {"symbol": "BTCUSDT"}]})]
    )
    with pytest.raises(BybitPublicError, match="duplicate"):
        BybitPublicClient(duplicate_transport).tickers()


def test_announcement_page_uses_exact_public_endpoint_and_validates_lifecycle_fields() -> None:
    transport = QueueTransport(
        [
            response(
                {
                    "list": [
                        {
                            "dateTimestamp": 1_700_000_000_000,
                            "publishTime": 1_700_000_000_001,
                            "type": {"key": "new_crypto", "title": "New Listings"},
                        }
                    ],
                    "total": 1,
                }
            )
        ]
    )
    page = BybitPublicClient(transport).announcement_page(announcement_type="new_crypto", page=1)
    assert page.total == 1
    assert page.items[0]["publishTime"] == 1_700_000_000_001
    assert transport.calls == [
        (
            "/v5/announcements/index",
            {"locale": "en-US", "type": "new_crypto", "page": 1, "limit": 20},
        )
    ]


def test_announcement_page_rejects_wrong_type_and_forward_order() -> None:
    wrong_type = QueueTransport(
        [
            response(
                {
                    "list": [
                        {
                            "dateTimestamp": 1,
                            "publishTime": 1,
                            "type": {"key": "other"},
                        }
                    ],
                    "total": 1,
                }
            )
        ]
    )
    with pytest.raises(BybitPublicError, match="lifecycle fields"):
        BybitPublicClient(wrong_type).announcement_page(announcement_type="new_crypto", page=1)

    forward_order = QueueTransport(
        [
            response(
                {
                    "list": [
                        {"dateTimestamp": 1, "publishTime": 1, "type": {"key": "other"}},
                        {"dateTimestamp": 2, "publishTime": 2, "type": {"key": "other"}},
                    ],
                    "total": 2,
                }
            )
        ]
    )
    with pytest.raises(BybitPublicError, match="reverse chronological"):
        BybitPublicClient(forward_order).announcement_page(announcement_type="other", page=1)


def test_kline_pagination_moves_inclusive_end_backward_without_duplicates() -> None:
    transport = QueueTransport(
        [
            response(
                {
                    "list": [
                        ["180000", "1", "2", "1", "2", "10", "20"],
                        ["120000", "1", "2", "1", "2", "10", "20"],
                    ]
                }
            ),
            response({"list": [["60000", "1", "2", "1", "2", "10", "20"]]}),
        ]
    )
    rows = tuple(
        BybitPublicClient(transport).iter_klines_backward(
            kind="trade", symbol="BTCUSDT", start_ms=60_000, end_ms=180_000, limit=2
        )
    )
    assert [row[0] for row in rows] == ["180000", "120000", "60000"]
    assert transport.calls[1][1]["end"] == 119_999


def test_kline_page_rejects_non_reverse_order() -> None:
    transport = QueueTransport(
        [
            response({"list": [["60000", "1", "2", "1", "2"], ["120000", "1", "2", "1", "2"]]}),
        ]
    )
    with pytest.raises(BybitPublicError, match="reverse chronological"):
        tuple(
            BybitPublicClient(transport).iter_klines_backward(
                kind="mark", symbol="BTCUSDT", start_ms=60_000, end_ms=120_000
            )
        )


def test_funding_pagination_moves_inclusive_end_backward_without_duplicates() -> None:
    transport = QueueTransport(
        [
            response(
                {
                    "list": [
                        {
                            "symbol": "BTCUSDT",
                            "fundingRate": "0.0001",
                            "fundingRateTimestamp": "180000",
                        },
                        {
                            "symbol": "BTCUSDT",
                            "fundingRate": "0.0002",
                            "fundingRateTimestamp": "120000",
                        },
                    ]
                }
            ),
            response(
                {
                    "list": [
                        {
                            "symbol": "BTCUSDT",
                            "fundingRate": "0.0003",
                            "fundingRateTimestamp": "60000",
                        }
                    ]
                }
            ),
        ]
    )
    rows = tuple(
        BybitPublicClient(transport).iter_funding_backward(
            symbol="BTCUSDT", start_ms=60_000, end_ms=180_000, limit=2
        )
    )
    assert [row["fundingRateTimestamp"] for row in rows] == ["180000", "120000", "60000"]
    assert transport.calls[1][1]["endTime"] == 119_999


def test_funding_page_rejects_non_reverse_order() -> None:
    transport = QueueTransport(
        [
            response(
                {
                    "list": [
                        {
                            "symbol": "BTCUSDT",
                            "fundingRate": "0.0001",
                            "fundingRateTimestamp": "60000",
                        },
                        {
                            "symbol": "BTCUSDT",
                            "fundingRate": "0.0002",
                            "fundingRateTimestamp": "120000",
                        },
                    ]
                }
            )
        ]
    )
    with pytest.raises(BybitPublicError, match="reverse chronological"):
        tuple(
            BybitPublicClient(transport).iter_funding_backward(
                symbol="BTCUSDT", start_ms=60_000, end_ms=120_000
            )
        )
