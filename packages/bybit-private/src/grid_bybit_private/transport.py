"""HMAC transport with one hard-coded read/validate endpoint and no retries."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any, cast

from grid_contracts.canonical import canonical_json_bytes

from grid_bybit_private.fgrid_validate import VALIDATE_ENDPOINT

ORIGINS = {
    "mainnet": "https://api.bybit.com",
    "testnet": "https://api-testnet.bybit.com",
}


class ValidateTransportError(RuntimeError):
    pass


ResponseReader = Callable[[urllib.request.Request, float], bytes]


class HmacValidateTransport:
    __slots__ = (
        "_api_key",
        "_api_secret",
        "_clock_ms",
        "_read_response",
        "_recv_window",
        "_timeout_seconds",
        "environment",
    )

    def __init__(
        self,
        *,
        environment: str,
        api_key: str,
        api_secret: str,
        recv_window: int = 5_000,
        timeout_seconds: float = 10.0,
        clock_ms: Callable[[], int] | None = None,
        read_response: ResponseReader | None = None,
    ) -> None:
        if environment not in ORIGINS:
            raise ValueError("environment must be testnet or mainnet")
        if not api_key or not api_secret:
            raise ValueError("API key and secret must be non-empty")
        if not 1_000 <= recv_window <= 5_000:
            raise ValueError("recv_window must be in [1000, 5000] milliseconds")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.environment = environment
        self._api_key = api_key
        self._api_secret = api_secret
        self._recv_window = recv_window
        self._timeout_seconds = timeout_seconds
        self._clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        self._read_response = read_response or _urllib_read

    def __repr__(self) -> str:
        return f"HmacValidateTransport(environment={self.environment!r}, credentials=<redacted>)"

    def validate(self, payload: Mapping[str, str]) -> Mapping[str, Any]:
        body = canonical_json_bytes(payload)
        timestamp = self._clock_ms()
        if timestamp < 0:
            raise ValidateTransportError("clock returned a negative Unix timestamp")
        headers = signed_headers(
            body=body,
            timestamp_ms=timestamp,
            api_key=self._api_key,
            api_secret=self._api_secret,
            recv_window=self._recv_window,
        )
        request = urllib.request.Request(
            f"{ORIGINS[self.environment]}{VALIDATE_ENDPOINT}",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            raw = self._read_response(request, self._timeout_seconds)
            if self._api_key.encode() in raw or self._api_secret.encode() in raw:
                raise ValidateTransportError("Bybit response unexpectedly echoed credentials")
            response = json.loads(raw, parse_float=Decimal)
        except urllib.error.HTTPError as error:
            raise ValidateTransportError(f"Bybit validate HTTP error {error.code}") from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise ValidateTransportError("Bybit validate request failed") from error
        if not isinstance(response, dict):
            raise ValidateTransportError("Bybit validate response root must be an object")
        return response


def signed_headers(
    *,
    body: bytes,
    timestamp_ms: int,
    api_key: str,
    api_secret: str,
    recv_window: int,
) -> dict[str, str]:
    timestamp = str(timestamp_ms)
    window = str(recv_window)
    body_text = body.decode("utf-8")
    message = f"{timestamp}{api_key}{window}{body_text}".encode()
    signature = hmac.new(api_secret.encode(), message, hashlib.sha256).hexdigest()
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "brullik-grid-validate-probe/0.2",
        "X-Bapi-Api-Key": api_key,
        "X-Bapi-Recv-Window": window,
        "X-Bapi-Sign": signature,
        "X-Bapi-Timestamp": timestamp,
    }


def _urllib_read(request: urllib.request.Request, timeout_seconds: float) -> bytes:
    opener = urllib.request.build_opener(_RejectRedirects())
    with opener.open(request, timeout=timeout_seconds) as response:
        if response.geturl() != request.full_url:
            raise ValidateTransportError("validate request redirected unexpectedly")
        return cast(bytes, response.read())


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None
