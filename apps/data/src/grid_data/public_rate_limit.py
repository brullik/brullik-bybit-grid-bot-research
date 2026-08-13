"""Decrease-only global pacing from sanitized Bybit V5 response-limit observations."""

from __future__ import annotations

import math
import time
from threading import Condition
from typing import Final, cast

from grid_bybit_public import RateLimitObservation

ADAPTIVE_RATE_POLICY: Final = "bybit-v5-response-header-decrease-only-v1"
IP_BAN_COOLDOWN_MS: Final = 10 * 60 * 1000
RATE_LIMIT_COOLDOWN_MS: Final = 1000
MAX_RESET_COOLDOWN_MS: Final = IP_BAN_COOLDOWN_MS

_SUMMARY_FIELDS: Final = frozenset(
    {
        "automatic_increase_count",
        "complete_header_observation_count",
        "configured_target_rps",
        "cooldown_event_count",
        "final_effective_rps",
        "header_absent_observation_count",
        "invalid_header_observation_count",
        "low_headroom_event_count",
        "maximum_cooldown_ms",
        "minimum_effective_rps",
        "policy",
        "rate_limit_event_count",
        "rate_reduction_count",
        "response_observation_count",
    }
)


class AdaptiveRateLimitError(ValueError):
    """Adaptive pacing evidence is malformed or internally inconsistent."""


class AdaptiveRateLimitAbort(RuntimeError):
    """The current run must stop rather than retry through an IP-ban response."""


class AdaptiveRatePacer:
    """Serialize launch slots globally and only reduce rate from venue observations."""

    def __init__(self, target_rps: int) -> None:
        if isinstance(target_rps, bool) or not isinstance(target_rps, int) or target_rps < 1:
            raise AdaptiveRateLimitError("target_rps must be a positive integer")
        self._configured_target_rps = target_rps
        self._effective_rps = target_rps
        self._minimum_effective_rps = target_rps
        self._next_ns = time.monotonic_ns()
        self._cooldown_until_ns = 0
        self._abort_until_epoch_ms: int | None = None
        self._condition = Condition()
        self._response_observation_count = 0
        self._complete_header_observation_count = 0
        self._header_absent_observation_count = 0
        self._invalid_header_observation_count = 0
        self._low_headroom_event_count = 0
        self._rate_limit_event_count = 0
        self._rate_reduction_count = 0
        self._cooldown_event_count = 0
        self._maximum_cooldown_ms = 0

    def wait(self) -> None:
        """Claim one launch only when the latest shared rate/cooldown policy permits it."""

        with self._condition:
            while True:
                if self._abort_until_epoch_ms is not None:
                    raise AdaptiveRateLimitAbort(
                        "Bybit HTTP 403 requires all public acquisition launches to stop; "
                        f"do not resume before epoch_ms={self._abort_until_epoch_ms}"
                    )
                now_ns = time.monotonic_ns()
                ready_ns = max(self._next_ns, self._cooldown_until_ns)
                if ready_ns <= now_ns:
                    interval_ns = math.ceil(1_000_000_000 / self._effective_rps)
                    self._next_ns = now_ns + interval_ns
                    return
                self._condition.wait((ready_ns - now_ns) / 1_000_000_000)

    def observe_client(self, client: object) -> None:
        take = getattr(client, "take_rate_limit_observation", None)
        if not callable(take):
            return
        observed = take()
        if isinstance(observed, RateLimitObservation):
            self.observe(observed)

    def observe(self, observed: RateLimitObservation) -> None:
        with self._condition:
            self._response_observation_count += 1
            if observed.header_state == "complete":
                self._complete_header_observation_count += 1
            elif observed.header_state == "absent":
                self._header_absent_observation_count += 1
            else:
                self._invalid_header_observation_count += 1

            reduced_rps = self._effective_rps
            if observed.header_state == "complete":
                assert observed.limit is not None and observed.remaining is not None
                headroom_floor = math.ceil(observed.limit * 0.20)
                if observed.remaining <= headroom_floor:
                    self._low_headroom_event_count += 1
                    reduced_rps = min(reduced_rps, max(1, math.floor(observed.limit * 0.80)))

            cooldown_ms = 0
            if observed.rate_limited:
                self._rate_limit_event_count += 1
                reduced_rps = min(reduced_rps, max(1, self._effective_rps // 2))
                cooldown_ms = (
                    IP_BAN_COOLDOWN_MS if observed.http_status == 403 else RATE_LIMIT_COOLDOWN_MS
                )
                if observed.header_state == "complete" and observed.reset_at_ms is not None:
                    reset_delta_ms = observed.reset_at_ms - time.time_ns() // 1_000_000
                    if 0 < reset_delta_ms <= MAX_RESET_COOLDOWN_MS:
                        cooldown_ms = max(cooldown_ms, reset_delta_ms)
                if observed.http_status == 403:
                    self._abort_until_epoch_ms = time.time_ns() // 1_000_000 + IP_BAN_COOLDOWN_MS

            if reduced_rps < self._effective_rps:
                self._effective_rps = reduced_rps
                self._minimum_effective_rps = min(self._minimum_effective_rps, self._effective_rps)
                self._rate_reduction_count += 1
                self._next_ns = max(self._next_ns, time.monotonic_ns())
            if cooldown_ms:
                self._cooldown_event_count += 1
                self._maximum_cooldown_ms = max(self._maximum_cooldown_ms, cooldown_ms)
                self._cooldown_until_ns = max(
                    self._cooldown_until_ns,
                    time.monotonic_ns() + cooldown_ms * 1_000_000,
                )
            self._condition.notify_all()

    def summary(self) -> dict[str, object]:
        with self._condition:
            return {
                "automatic_increase_count": 0,
                "complete_header_observation_count": self._complete_header_observation_count,
                "configured_target_rps": self._configured_target_rps,
                "cooldown_event_count": self._cooldown_event_count,
                "final_effective_rps": self._effective_rps,
                "header_absent_observation_count": self._header_absent_observation_count,
                "invalid_header_observation_count": self._invalid_header_observation_count,
                "low_headroom_event_count": self._low_headroom_event_count,
                "maximum_cooldown_ms": self._maximum_cooldown_ms,
                "minimum_effective_rps": self._minimum_effective_rps,
                "policy": ADAPTIVE_RATE_POLICY,
                "rate_limit_event_count": self._rate_limit_event_count,
                "rate_reduction_count": self._rate_reduction_count,
                "response_observation_count": self._response_observation_count,
            }


def verify_adaptive_rate_summary(
    raw: object,
    *,
    configured_target_rps: int,
    maximum_response_count: int,
) -> dict[str, object]:
    """Verify a new summary while allowing callers to handle legacy missing summaries."""

    if not isinstance(raw, dict) or set(raw) != _SUMMARY_FIELDS:
        raise AdaptiveRateLimitError("adaptive throttling summary fields do not match v1")
    summary = cast(dict[str, object], raw)
    if summary.get("policy") != ADAPTIVE_RATE_POLICY:
        raise AdaptiveRateLimitError("adaptive throttling policy is unsupported")
    integer_fields = _SUMMARY_FIELDS - {"policy"}
    if any(
        isinstance(summary.get(name), bool)
        or not isinstance(summary.get(name), int)
        or cast(int, summary[name]) < 0
        for name in integer_fields
    ):
        raise AdaptiveRateLimitError("adaptive throttling counters must be non-negative integers")
    if summary["configured_target_rps"] != configured_target_rps:
        raise AdaptiveRateLimitError("adaptive throttling target does not bind the request")
    response_count = cast(int, summary["response_observation_count"])
    classified_count = sum(
        cast(int, summary[name])
        for name in (
            "complete_header_observation_count",
            "header_absent_observation_count",
            "invalid_header_observation_count",
        )
    )
    minimum_rps = cast(int, summary["minimum_effective_rps"])
    final_rps = cast(int, summary["final_effective_rps"])
    reduction_count = cast(int, summary["rate_reduction_count"])
    cooldown_count = cast(int, summary["cooldown_event_count"])
    maximum_cooldown_ms = cast(int, summary["maximum_cooldown_ms"])
    if (
        response_count != classified_count
        or response_count > maximum_response_count
        or not 1 <= minimum_rps == final_rps <= configured_target_rps
        or cast(int, summary["rate_limit_event_count"]) > response_count
        or cast(int, summary["low_headroom_event_count"])
        > (cast(int, summary["complete_header_observation_count"]))
        or reduction_count > response_count
        or (final_rps < configured_target_rps) != (reduction_count > 0)
        or cooldown_count > (cast(int, summary["rate_limit_event_count"]))
        or (maximum_cooldown_ms > 0) != (cooldown_count > 0)
        or maximum_cooldown_ms > MAX_RESET_COOLDOWN_MS
        or summary["automatic_increase_count"] != 0
    ):
        raise AdaptiveRateLimitError("adaptive throttling summary is internally inconsistent")
    return summary
