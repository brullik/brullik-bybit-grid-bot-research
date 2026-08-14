from __future__ import annotations

import http.client
import json
import ssl
import threading
import time
import urllib.error
import urllib.parse
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Any, ClassVar, cast

import pytest
from grid_bybit_public.transport import (
    PooledHttpsJsonTransport,
    TransportError,
    UrllibJsonTransport,
)


class Response:
    def __init__(
        self,
        payload: Mapping[str, Any],
        *,
        headers: Mapping[str, str] | None = None,
        status: int = 200,
        will_close: bool = False,
    ) -> None:
        self._stream = BytesIO(json.dumps(payload).encode("utf-8"))
        self.headers = dict(headers or {})
        self.status = status
        self.will_close = will_close

    def __enter__(self) -> Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)


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
        ssl.SSLError(ssl.SSL_ERROR_SSL, "decryption failed or bad record mac"),
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
        raise urllib.error.HTTPError(
            "https://api.bybit.com", 400, "bad request", cast(Any, {}), None
        )

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    transport = UrllibJsonTransport(max_attempts=3)

    with pytest.raises(TransportError, match="HTTP error 400"):
        transport.get("/v5/market/kline", {"symbol": "BTCUSDT"})
    assert calls == 1


def test_cloudfront_country_block_is_sanitized_and_not_mislabeled_as_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    body = (
        b"ERROR: The request could not be satisfied. The Amazon CloudFront distribution "
        b"is configured to block access from your country."
    )

    def urlopen(*args: object, **kwargs: object) -> Response:
        nonlocal calls
        del args, kwargs
        calls += 1
        raise urllib.error.HTTPError(
            "https://api.bybit.com/v5/market/time",
            403,
            "Forbidden",
            cast(Any, {}),
            BytesIO(body),
        )

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    transport = UrllibJsonTransport(max_attempts=3)

    with pytest.raises(TransportError, match="unavailable from the current region") as captured:
        transport.get("/v5/market/time", {})
    observed = transport.take_rate_limit_observation()

    assert calls == 1
    assert captured.value.failure_class == "regional-access-block"
    assert str(captured.value) == "Bybit public API is unavailable from the current region"
    assert observed is not None
    assert observed.failure_class == "regional-access-block"
    assert observed.rate_limited is False


def test_non_regional_403_retains_official_ip_rate_limit_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def urlopen(*args: object, **kwargs: object) -> Response:
        del args, kwargs
        raise urllib.error.HTTPError(
            "https://api.bybit.com/v5/market/time",
            403,
            "Forbidden",
            cast(Any, {}),
            BytesIO(b"access too frequent"),
        )

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    transport = UrllibJsonTransport(max_attempts=1)

    with pytest.raises(TransportError, match="HTTP error 403") as captured:
        transport.get("/v5/market/time", {})
    observed = transport.take_rate_limit_observation()

    assert captured.value.failure_class == "rate-limit"
    assert observed is not None
    assert observed.failure_class == "rate-limit"
    assert observed.rate_limited is True


def test_transport_exposes_sanitized_complete_rate_limit_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Response(
        {"retCode": 0, "result": {"list": []}},
        headers={
            "X-Bapi-Limit": "10",
            "X-Bapi-Limit-Status": "2",
            "X-Bapi-Limit-Reset-Timestamp": "1786635000000",
        },
    )
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: response)
    transport = UrllibJsonTransport(max_attempts=1)

    transport.get("/v5/market/kline", {"symbol": "BTCUSDT"})
    observed = transport.take_rate_limit_observation()

    assert observed is not None
    assert observed.header_state == "complete"
    assert observed.limit == 10
    assert observed.remaining == 2
    assert observed.reset_at_ms == 1_786_635_000_000
    assert observed.rate_limited is False
    assert transport.take_rate_limit_observation() is None


def test_transport_marks_bybit_limit_code_and_invalid_partial_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Response(
        {"retCode": 10006, "retMsg": "Too many visits!", "result": {}},
        headers={"X-Bapi-Limit": "10"},
    )
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: response)
    transport = UrllibJsonTransport(max_attempts=1)

    payload = transport.get("/v5/market/kline", {"symbol": "BTCUSDT"})
    observed = transport.take_rate_limit_observation()

    assert payload["retCode"] == 10006
    assert observed is not None
    assert observed.header_state == "invalid"
    assert observed.limit is None
    assert observed.rate_limited is True


def test_transport_allows_exact_announcement_path_and_rejects_adjacent_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Response({"retCode": 0, "result": {"list": [], "total": 0}})
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: response)
    transport = UrllibJsonTransport(max_attempts=1)

    assert transport.get("/v5/announcements/index", {"locale": "en-US"})["retCode"] == 0
    with pytest.raises(TransportError, match="permits only"):
        transport.get("/v5/announcements/private", {})


def test_pooled_transport_reuses_one_keep_alive_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Connection:
        created = 0
        targets: ClassVar[list[str]] = []

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            type(self).created += 1

        def request(self, _method: str, target: str, *, headers: Mapping[str, str]) -> None:
            assert headers["Accept"] == "application/json"
            type(self).targets.append(target)

        def getresponse(self) -> Response:
            return Response({"retCode": 0, "result": {"list": []}})

        def close(self) -> None:
            return None

    monkeypatch.setattr("grid_bybit_public.transport.http.client.HTTPSConnection", Connection)
    transport = PooledHttpsJsonTransport(max_attempts=1, max_connections=2)

    transport.get("/v5/market/kline", {"symbol": "BTCUSDT", "interval": 1})
    transport.get("/v5/market/mark-price-kline", {"symbol": "ETHUSDT", "interval": 1})

    assert Connection.created == 1
    assert Connection.targets == [
        "/v5/market/kline?symbol=BTCUSDT&interval=1",
        "/v5/market/mark-price-kline?symbol=ETHUSDT&interval=1",
    ]


def test_pooled_transport_discards_failed_connection_before_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Connection:
        created = 0
        closed = 0

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            type(self).created += 1
            self.sequence = type(self).created

        def request(self, *_args: object, **_kwargs: object) -> None:
            return None

        def getresponse(self) -> Response:
            if self.sequence == 1:
                raise http.client.RemoteDisconnected("remote closed without response")
            return Response({"retCode": 0, "result": {"list": []}})

        def close(self) -> None:
            type(self).closed += 1

    monkeypatch.setattr("grid_bybit_public.transport.http.client.HTTPSConnection", Connection)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    transport = PooledHttpsJsonTransport(max_attempts=2, max_connections=1)

    assert transport.get("/v5/market/kline", {"symbol": "BTCUSDT"})["retCode"] == 0
    assert Connection.created == 2
    assert Connection.closed == 1


def test_pooled_transport_preserves_regional_block_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BlockedResponse:
        status = 403
        headers: ClassVar[dict[str, str]] = {}
        will_close = True

        def read(self, _size: int = -1) -> bytes:
            return (
                b"ERROR: The request could not be satisfied. The Amazon CloudFront distribution "
                b"is configured to block access from your country."
            )

    class Connection:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        def request(self, *_args: object, **_kwargs: object) -> None:
            return None

        def getresponse(self) -> BlockedResponse:
            return BlockedResponse()

        def close(self) -> None:
            return None

    monkeypatch.setattr("grid_bybit_public.transport.http.client.HTTPSConnection", Connection)
    transport = PooledHttpsJsonTransport(max_attempts=1, max_connections=1)

    with pytest.raises(TransportError, match="unavailable from the current region") as captured:
        transport.get("/v5/market/kline", {"symbol": "BTCUSDT"})
    observed = transport.take_rate_limit_observation()

    assert captured.value.failure_class == "regional-access-block"
    assert observed is not None
    assert observed.failure_class == "regional-access-block"
    assert observed.rate_limited is False


def test_pooled_transport_bounds_concurrent_connections_and_isolates_observations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = threading.Lock()
    two_active = threading.Event()

    class Connection:
        created = 0
        active = 0
        maximum_active = 0

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            with lock:
                type(self).created += 1
            self.target = ""

        def request(self, _method: str, target: str, *, headers: Mapping[str, str]) -> None:
            del headers
            self.target = target

        def getresponse(self) -> Response:
            with lock:
                type(self).active += 1
                type(self).maximum_active = max(type(self).maximum_active, type(self).active)
                if type(self).active == 2:
                    two_active.set()
            assert two_active.wait(timeout=2)
            time.sleep(0.005)
            symbol = urllib.parse.parse_qs(urllib.parse.urlparse(self.target).query)["symbol"][0]
            remaining = "7" if symbol == "BTCUSDT" else "3"
            with lock:
                type(self).active -= 1
            return Response(
                {"retCode": 0, "result": {"list": []}},
                headers={
                    "X-Bapi-Limit": "10",
                    "X-Bapi-Limit-Status": remaining,
                    "X-Bapi-Limit-Reset-Timestamp": "1786635000000",
                },
            )

        def close(self) -> None:
            return None

    monkeypatch.setattr("grid_bybit_public.transport.http.client.HTTPSConnection", Connection)
    transport = PooledHttpsJsonTransport(max_attempts=1, max_connections=2)

    def request(symbol: str) -> int | None:
        transport.get("/v5/market/kline", {"symbol": symbol})
        observed = transport.take_rate_limit_observation()
        return None if observed is None else observed.remaining

    with ThreadPoolExecutor(max_workers=2) as executor:
        btc = executor.submit(request, "BTCUSDT")
        eth = executor.submit(request, "ETHUSDT")

    assert btc.result() == 7
    assert eth.result() == 3
    assert Connection.created == 2
    assert Connection.maximum_active == 2


def test_pooled_transport_closes_idle_connections_and_rejects_new_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Connection:
        closed = 0

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        def request(self, *_args: object, **_kwargs: object) -> None:
            return None

        def getresponse(self) -> Response:
            return Response({"retCode": 0, "result": {"list": []}})

        def close(self) -> None:
            type(self).closed += 1

    monkeypatch.setattr("grid_bybit_public.transport.http.client.HTTPSConnection", Connection)
    transport = PooledHttpsJsonTransport(max_attempts=1, max_connections=1)
    transport.get("/v5/market/kline", {"symbol": "BTCUSDT"})

    transport.close()
    transport.close()

    assert Connection.closed == 1
    with pytest.raises(TransportError, match="closed"):
        transport.get("/v5/market/kline", {"symbol": "BTCUSDT"})
