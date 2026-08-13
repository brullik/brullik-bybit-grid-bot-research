from __future__ import annotations

import http.client
import json
import urllib.error
from collections.abc import Mapping
from io import BytesIO
from typing import Any

import pytest
from grid_bybit_public.transport import TransportError, UrllibJsonTransport


class Response:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self._stream = BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self) -> BytesIO:
        return self._stream

    def __exit__(self, *args: object) -> None:
        return None


def test_remote_disconnect_is_retried_and_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def urlopen(*args: object, **kwargs: object) -> Response:
        nonlocal calls
        del args, kwargs
        calls += 1
        if calls == 1:
            raise http.client.RemoteDisconnected("remote closed without response")
        return Response({"retCode": 0, "result": {"list": []}})

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    transport = UrllibJsonTransport(max_attempts=2)

    assert transport.get("/v5/market/kline", {"symbol": "BTCUSDT"})["retCode"] == 0
    assert calls == 2


@pytest.mark.parametrize(
    "failure",
    [
        http.client.IncompleteRead(b"partial"),
        ConnectionResetError("connection reset"),
    ],
)
def test_connection_protocol_failures_exhaust_bounded_attempts(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    calls = 0

    def urlopen(*args: object, **kwargs: object) -> Response:
        nonlocal calls
        del args, kwargs
        calls += 1
        raise failure

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    transport = UrllibJsonTransport(max_attempts=2)

    with pytest.raises(TransportError, match="failed after 2 attempts") as captured:
        transport.get("/v5/market/kline", {"symbol": "BTCUSDT"})
    assert captured.value.__cause__ is failure
    assert calls == 2


def test_non_retryable_http_error_remains_immediate(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def urlopen(*args: object, **kwargs: object) -> Response:
        nonlocal calls
        del args, kwargs
        calls += 1
        raise urllib.error.HTTPError("https://api.bybit.com", 400, "bad request", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    transport = UrllibJsonTransport(max_attempts=3)

    with pytest.raises(TransportError, match="HTTP error 400"):
        transport.get("/v5/market/kline", {"symbol": "BTCUSDT"})
    assert calls == 1
