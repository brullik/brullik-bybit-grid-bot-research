"""Small stdlib transport for public endpoints; it cannot sign private requests."""

from __future__ import annotations

import http.client
import json
import random
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

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
