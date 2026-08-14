"""Small stdlib transport for public endpoints; it cannot sign private requests."""

from __future__ import annotations

import http.client
import json
import queue
import random
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

MAX_PUBLIC_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_POOLED_CONNECTIONS = 32

TransportFailureClass = Literal[
    "none",
    "http-client-error",
    "rate-limit",
    "regional-access-block",
]


class JsonTransport(Protocol):
    def get(self, path: str, params: Mapping[str, str | int]) -> Mapping[str, Any]: ...


class TransportError(RuntimeError):
    """Sanitized public-transport failure with a machine-readable safe classification."""

    def __init__(
        self,
        message: str,
        *,
        failure_class: TransportFailureClass = "none",
    ) -> None:
        super().__init__(message)
        self.failure_class = failure_class


@dataclass(frozen=True, slots=True)
class RateLimitObservation:
    """One sanitized Bybit response-limit observation; it contains no request identity."""

    http_status: int
    bybit_ret_code: int | None
    header_state: Literal["absent", "complete", "invalid"]
    limit: int | None
    remaining: int | None
    reset_at_ms: int | None
    failure_class: TransportFailureClass = "none"

    @property
    def rate_limited(self) -> bool:
        if self.failure_class == "regional-access-block":
            return False
        return (
            self.failure_class == "rate-limit"
            or self.http_status in (403, 429)
            or self.bybit_ret_code == 10006
        )


def _optional_integer(value: object) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(str(value))
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _rate_limit_observation(
    headers: object,
    *,
    http_status: int,
    bybit_ret_code: object,
    failure_class: TransportFailureClass | None = None,
) -> RateLimitObservation:
    get_header = getattr(headers, "get", None)
    raw_values = (
        get_header("X-Bapi-Limit") if callable(get_header) else None,
        get_header("X-Bapi-Limit-Status") if callable(get_header) else None,
        get_header("X-Bapi-Limit-Reset-Timestamp") if callable(get_header) else None,
    )
    present_count = sum(value is not None for value in raw_values)
    limit, remaining, reset_at_ms = (_optional_integer(value) for value in raw_values)
    if present_count == 0:
        state: Literal["absent", "complete", "invalid"] = "absent"
    elif (
        present_count == 3
        and limit is not None
        and limit > 0
        and remaining is not None
        and remaining <= limit
        and reset_at_ms is not None
    ):
        state = "complete"
    else:
        state = "invalid"
        limit = remaining = reset_at_ms = None
    ret_code = (
        bybit_ret_code
        if isinstance(bybit_ret_code, int) and not isinstance(bybit_ret_code, bool)
        else None
    )
    if failure_class is None:
        failure_class = "rate-limit" if http_status in (403, 429) or ret_code == 10006 else "none"
    return RateLimitObservation(
        http_status=http_status,
        bybit_ret_code=ret_code,
        header_state=state,
        limit=limit,
        remaining=remaining,
        reset_at_ms=reset_at_ms,
        failure_class=failure_class,
    )


def _http_failure_class(status: int, body: bytes) -> TransportFailureClass:
    """Classify only stable control text; never retain or expose an HTTP error body."""

    normalized = body.lower()
    if (
        status == 403
        and b"cloudfront" in normalized
        and b"block" in normalized
        and b"country" in normalized
    ):
        return "regional-access-block"
    if status in (403, 429):
        return "rate-limit"
    return "http-client-error"


def _bounded_error_body(error: urllib.error.HTTPError) -> bytes:
    try:
        return error.read(64 * 1024)
    except (AttributeError, OSError, ValueError, http.client.HTTPException):
        return b""


@dataclass(slots=True)
class UrllibJsonTransport:
    base_url: str = "https://api.bybit.com"
    timeout_seconds: float = 20.0
    max_attempts: int = 5
    base_backoff_seconds: float = 0.25
    max_backoff_seconds: float = 8.0
    _last_rate_limit_observation: RateLimitObservation | None = field(
        default=None, init=False, repr=False
    )

    def __post_init__(self) -> None:
        parsed = urllib.parse.urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.params or parsed.query:
            raise ValueError("base_url must be an HTTPS origin")
        if self.timeout_seconds <= 0 or self.max_attempts < 1:
            raise ValueError("timeout and attempts must be positive")
        self.base_url = self.base_url.rstrip("/")

    def get(self, path: str, params: Mapping[str, str | int]) -> Mapping[str, Any]:
        if not (path.startswith("/v5/market/") or path == "/v5/announcements/index"):
            raise TransportError(
                "public transport permits only /v5/market/* and /v5/announcements/index"
            )
        query = urllib.parse.urlencode(params)
        request = urllib.request.Request(
            f"{self.base_url}{path}?{query}",
            headers={"Accept": "application/json", "User-Agent": "brullik-grid-data/0.2"},
            method="GET",
        )
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    payload = json.load(response)
                if not isinstance(payload, dict):
                    raise TransportError("Bybit response root is not an object")
                self._last_rate_limit_observation = _rate_limit_observation(
                    getattr(response, "headers", None),
                    http_status=int(getattr(response, "status", 200)),
                    bybit_ret_code=payload.get("retCode"),
                )
                return payload
            except urllib.error.HTTPError as error:
                failure_class = _http_failure_class(error.code, _bounded_error_body(error))
                self._last_rate_limit_observation = _rate_limit_observation(
                    error.headers,
                    http_status=error.code,
                    bybit_ret_code=None,
                    failure_class=failure_class,
                )
                last_error = error
                if error.code < 500 and error.code != 429:
                    message = (
                        "Bybit public API is unavailable from the current region"
                        if failure_class == "regional-access-block"
                        else f"Bybit HTTP error {error.code}"
                    )
                    raise TransportError(message, failure_class=failure_class) from error
            except (
                urllib.error.URLError,
                http.client.HTTPException,
                ssl.SSLError,
                ConnectionError,
                TimeoutError,
                json.JSONDecodeError,
            ) as error:
                last_error = error
            if attempt + 1 < self.max_attempts:
                ceiling = min(self.max_backoff_seconds, self.base_backoff_seconds * (2**attempt))
                time.sleep(random.uniform(ceiling / 2, ceiling))
        raise TransportError(
            f"Bybit request failed after {self.max_attempts} attempts"
        ) from last_error

    def take_rate_limit_observation(self) -> RateLimitObservation | None:
        """Return and clear the latest observation for the calling acquisition worker."""

        observed = self._last_rate_limit_observation
        self._last_rate_limit_observation = None
        return observed


class PooledHttpsJsonTransport:
    """Thread-safe bounded HTTPS/1.1 pool for high-volume public REST acquisition."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.bybit.com",
        timeout_seconds: float = 20.0,
        max_attempts: int = 5,
        base_backoff_seconds: float = 0.25,
        max_backoff_seconds: float = 8.0,
        max_connections: int = MAX_POOLED_CONNECTIONS,
    ) -> None:
        parsed = urllib.parse.urlparse(base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("base_url must be an HTTPS origin")
        if timeout_seconds <= 0 or max_attempts < 1:
            raise ValueError("timeout and attempts must be positive")
        if base_backoff_seconds < 0 or max_backoff_seconds < base_backoff_seconds:
            raise ValueError("transport backoff bounds are invalid")
        if (
            isinstance(max_connections, bool)
            or not isinstance(max_connections, int)
            or not 1 <= max_connections <= MAX_POOLED_CONNECTIONS
        ):
            raise ValueError(f"max_connections must be in [1, {MAX_POOLED_CONNECTIONS}]")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.max_connections = max_connections
        self._hostname = parsed.hostname
        self._port = parsed.port
        self._ssl_context = ssl.create_default_context()
        self._pool: queue.LifoQueue[http.client.HTTPSConnection] = queue.LifoQueue(max_connections)
        self._slots = threading.BoundedSemaphore(max_connections)
        self._thread_state = threading.local()
        self._closed = False
        self._close_lock = threading.Lock()

    @staticmethod
    def _validate_path(path: str) -> None:
        if not (path.startswith("/v5/market/") or path == "/v5/announcements/index"):
            raise TransportError(
                "public transport permits only /v5/market/* and /v5/announcements/index"
            )

    def _new_connection(self) -> http.client.HTTPSConnection:
        return http.client.HTTPSConnection(
            self._hostname,
            self._port,
            timeout=self.timeout_seconds,
            context=self._ssl_context,
        )

    def _take_connection(self) -> http.client.HTTPSConnection:
        with self._close_lock:
            if self._closed:
                raise TransportError("public transport is closed")
        try:
            return self._pool.get_nowait()
        except queue.Empty:
            return self._new_connection()

    def _release_connection(
        self, connection: http.client.HTTPSConnection, *, reusable: bool
    ) -> None:
        with self._close_lock:
            closed = self._closed
        if reusable and not closed:
            try:
                self._pool.put_nowait(connection)
                return
            except queue.Full:
                pass
        connection.close()

    def _request_once(self, target: str) -> tuple[int, object, bytes, bool]:
        connection: http.client.HTTPSConnection | None = None
        reusable = False
        self._slots.acquire()
        try:
            connection = self._take_connection()
            connection.request(
                "GET",
                target,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "brullik-grid-data/0.2",
                },
            )
            response = connection.getresponse()
            body = response.read(MAX_PUBLIC_RESPONSE_BYTES + 1)
            if len(body) > MAX_PUBLIC_RESPONSE_BYTES:
                raise TransportError("Bybit response exceeds the bounded public JSON limit")
            status = int(response.status)
            reusable = not response.will_close and 200 <= status < 300
            return status, response.headers, body, reusable
        finally:
            if connection is not None:
                self._release_connection(connection, reusable=reusable)
            self._slots.release()

    def _set_observation(self, observed: RateLimitObservation) -> None:
        self._thread_state.last_rate_limit_observation = observed

    def get(self, path: str, params: Mapping[str, str | int]) -> Mapping[str, Any]:
        self._validate_path(path)
        query = urllib.parse.urlencode(params)
        target = f"{path}?{query}"
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                status, headers, body, _reusable = self._request_once(target)
                if not 200 <= status < 300:
                    failure_class = _http_failure_class(status, body[: 64 * 1024])
                    self._set_observation(
                        _rate_limit_observation(
                            headers,
                            http_status=status,
                            bybit_ret_code=None,
                            failure_class=failure_class,
                        )
                    )
                    last_error = http.client.HTTPException(f"HTTP status {status}")
                    if status < 500 and status != 429:
                        message = (
                            "Bybit public API is unavailable from the current region"
                            if failure_class == "regional-access-block"
                            else f"Bybit HTTP error {status}"
                        )
                        raise TransportError(message, failure_class=failure_class) from last_error
                else:
                    payload = json.loads(body)
                    if not isinstance(payload, dict):
                        raise TransportError("Bybit response root is not an object")
                    self._set_observation(
                        _rate_limit_observation(
                            headers,
                            http_status=status,
                            bybit_ret_code=payload.get("retCode"),
                        )
                    )
                    return payload
            except TransportError as error:
                if (
                    error.failure_class != "none"
                    or str(error).startswith("Bybit HTTP error")
                    or str(error) == "public transport is closed"
                ):
                    raise
                last_error = error
            except (
                http.client.HTTPException,
                ssl.SSLError,
                OSError,
                TimeoutError,
                UnicodeDecodeError,
                json.JSONDecodeError,
            ) as error:
                last_error = error
            if attempt + 1 < self.max_attempts:
                ceiling = min(
                    self.max_backoff_seconds,
                    self.base_backoff_seconds * (2**attempt),
                )
                time.sleep(random.uniform(ceiling / 2, ceiling))
        raise TransportError(
            f"Bybit request failed after {self.max_attempts} attempts"
        ) from last_error

    def take_rate_limit_observation(self) -> RateLimitObservation | None:
        """Return and clear the current worker's sanitized response observation."""

        observed = getattr(self._thread_state, "last_rate_limit_observation", None)
        self._thread_state.last_rate_limit_observation = None
        return observed if isinstance(observed, RateLimitObservation) else None

    def close(self) -> None:
        """Close idle pooled connections and reject later requests."""

        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        while True:
            try:
                connection = self._pool.get_nowait()
            except queue.Empty:
                return
            connection.close()

    def __enter__(self) -> PooledHttpsJsonTransport:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
