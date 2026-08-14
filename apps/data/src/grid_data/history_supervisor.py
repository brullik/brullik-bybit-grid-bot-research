"""Bounded automatic resume for transient public history-campaign failures."""

from __future__ import annotations

import errno
import http.client
import socket
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Literal

from grid_bybit_public.transport import TransportError

from grid_data.public_rate_limit import AdaptiveRateLimitAbort

SUPERVISOR_EVENT_CONTRACT: Final = "grid.history-campaign-supervisor-event/v1"
MAX_SUPERVISOR_INVOCATIONS: Final = 16
MAX_SUPERVISOR_COOLDOWN_SECONDS: Final = 600

ResumeFailureClass = Literal[
    "non-retryable",
    "transient-dns",
    "transient-network",
    "transient-upstream",
]

_TRANSIENT_ERRNOS: Final = frozenset(
    {
        errno.ECONNABORTED,
        errno.ECONNREFUSED,
        errno.ECONNRESET,
        errno.EHOSTUNREACH,
        errno.ENETDOWN,
        errno.ENETUNREACH,
        errno.EPIPE,
        errno.ETIMEDOUT,
    }
)
_TRANSIENT_WINERRORS: Final = frozenset(
    {
        10050,  # network is down
        10051,  # network is unreachable
        10052,  # network dropped connection
        10053,  # connection aborted
        10054,  # connection reset
        10060,  # timed out
        10061,  # connection refused
        10064,  # host is down
        10065,  # no route to host
        11001,  # host not found
        11002,  # non-authoritative host not found
        11004,  # valid name, no requested record
    }
)


class HistoryCampaignSupervisorError(ValueError):
    """The bounded supervisor configuration is invalid."""


@dataclass(frozen=True, slots=True)
class HistoryCampaignSupervisorPolicy:
    max_invocations: int = 8
    base_cooldown_seconds: int = 30

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_invocations, bool)
            or not isinstance(self.max_invocations, int)
            or not 1 <= self.max_invocations <= MAX_SUPERVISOR_INVOCATIONS
        ):
            raise HistoryCampaignSupervisorError(
                f"max_invocations must be in [1, {MAX_SUPERVISOR_INVOCATIONS}]"
            )
        if (
            isinstance(self.base_cooldown_seconds, bool)
            or not isinstance(self.base_cooldown_seconds, int)
            or not 10 <= self.base_cooldown_seconds <= MAX_SUPERVISOR_COOLDOWN_SECONDS
        ):
            raise HistoryCampaignSupervisorError(
                f"base_cooldown_seconds must be in [10, {MAX_SUPERVISOR_COOLDOWN_SECONDS}]"
            )

    def cooldown_seconds(self, failed_invocation: int) -> int:
        if not 1 <= failed_invocation <= self.max_invocations:
            raise HistoryCampaignSupervisorError("failed_invocation escapes the policy bound")
        return min(
            MAX_SUPERVISOR_COOLDOWN_SECONDS,
            self.base_cooldown_seconds * (1 << (failed_invocation - 1)),
        )


def _exception_chain(error: BaseException) -> tuple[BaseException, ...]:
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen and len(chain) < 32:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ if current.__cause__ is not None else current.__context__
    return tuple(chain)


def classify_history_campaign_failure(error: BaseException) -> ResumeFailureClass:
    """Classify only narrowly allowed transient causes; everything else fails closed."""

    chain = _exception_chain(error)
    if any(isinstance(item, AdaptiveRateLimitAbort) for item in chain):
        return "non-retryable"
    if any(isinstance(item, TransportError) and item.failure_class != "none" for item in chain):
        return "non-retryable"
    if any(isinstance(item, socket.gaierror) for item in chain):
        return "transient-dns"
    if any(
        isinstance(item, http.client.HTTPException) and str(item).startswith("HTTP status 5")
        for item in chain
    ):
        return "transient-upstream"
    if any(
        isinstance(
            item,
            (
                ConnectionError,
                TimeoutError,
                http.client.IncompleteRead,
                http.client.RemoteDisconnected,
                ssl.SSLEOFError,
            ),
        )
        for item in chain
    ):
        return "transient-network"
    for item in chain:
        if not isinstance(item, OSError):
            continue
        winerror = getattr(item, "winerror", None)
        if item.errno in _TRANSIENT_ERRNOS or winerror in _TRANSIENT_WINERRORS:
            return "transient-network"
    return "non-retryable"


def run_history_campaign_supervisor(
    operation: Callable[[], int],
    policy: HistoryCampaignSupervisorPolicy,
    *,
    emit: Callable[[dict[str, object]], None],
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Run one campaign command repeatedly only for explicitly classified transient failures."""

    for invocation in range(1, policy.max_invocations + 1):
        emit(
            {
                "contract": SUPERVISOR_EVENT_CONTRACT,
                "event": "invocation-started",
                "invocation": invocation,
                "max_invocations": policy.max_invocations,
            }
        )
        try:
            result = operation()
        except Exception as error:
            failure_class = classify_history_campaign_failure(error)
            retry_scheduled = (
                failure_class != "non-retryable" and invocation < policy.max_invocations
            )
            cooldown_seconds = policy.cooldown_seconds(invocation) if retry_scheduled else 0
            emit(
                {
                    "contract": SUPERVISOR_EVENT_CONTRACT,
                    "cooldown_seconds": cooldown_seconds,
                    "event": "invocation-failed",
                    "failure_class": failure_class,
                    "invocation": invocation,
                    "max_invocations": policy.max_invocations,
                    "retry_scheduled": retry_scheduled,
                }
            )
            if not retry_scheduled:
                raise
            sleep(float(cooldown_seconds))
        else:
            emit(
                {
                    "contract": SUPERVISOR_EVENT_CONTRACT,
                    "event": "supervisor-complete",
                    "invocation": invocation,
                    "max_invocations": policy.max_invocations,
                }
            )
            return result
    raise AssertionError("bounded supervisor loop exhausted without returning or raising")
