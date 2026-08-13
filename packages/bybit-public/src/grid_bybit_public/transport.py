"""Small stdlib transport for public endpoints; it cannot sign private requests."""

from __future__ import annotations

import http.client
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


class JsonTransport(Protocol):
    def get(self, path: str, params: Mapping[str, str | int]) -> Mapping[str, Any]: ...


class TransportError(RuntimeError):
    pass


@dataclass(slots=True)
class UrllibJsonTransport:
    base_url: str = "https://api.bybit.com"
    timeout_seconds: float = 20.0
    max_attempts: int = 5
    base_backoff_seconds: float = 0.25
    max_backoff_seconds: float = 8.0

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
                return payload
            except urllib.error.HTTPError as error:
                last_error = error
                if error.code < 500 and error.code != 429:
                    raise TransportError(f"Bybit HTTP error {error.code}") from error
            except (
                urllib.error.URLError,
                http.client.HTTPException,
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
