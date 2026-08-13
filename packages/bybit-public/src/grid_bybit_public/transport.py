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


class JsonTransport(Protocol):
    def get(self, path: str, params: Mapping[str, str | int]) -> Mapping[str, Any]: ...


class TransportError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RateLimitObservation:
    """One sanitized Bybit response-limit observation; it contains no request identity."""

    http_status: int
    bybit_ret_code: int | None
    header_state: Literal["absent", "complete", "invalid"]
    limit: int | None
    remaining: int | None
    reset_at_ms: int | None

    @property
    def rate_limited(self) -> bool:
        return self.http_status in (403, 429) or self.bybit_ret_code == 10006


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
    return RateLimitObservation(
        http_status=http_status,
        bybit_ret_code=ret_code,
        header_state=state,
        limit=limit,
        remaining=remaining,
        reset_at_ms=reset_at_ms,
    )


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
        if not path.startswith("/v5/market/"):
            raise TransportError("public transport permits only /v5/market/* endpoints")
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
                self._last_rate_limit_observation = _rate_limit_observation(
                    error.headers,
                    http_status=error.code,
                    bybit_ret_code=None,
                )
                last_error = error
                if error.code < 500 and error.code != 429:
                    raise TransportError(f"Bybit HTTP error {error.code}") from error
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
