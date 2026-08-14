from __future__ import annotations

import pytest
from grid_bybit_public import RateLimitObservation
from grid_data.public_rate_limit import (
    ADAPTIVE_RATE_POLICY,
    IP_BAN_COOLDOWN_MS,
    AdaptiveRateLimitAbort,
    AdaptiveRateLimitError,
    AdaptiveRatePacer,
    verify_adaptive_rate_summary,
)


def observation(
    *,
    http_status: int = 200,
    ret_code: int | None = 0,
    state: str = "complete",
    limit: int | None = 10,
    remaining: int | None = 2,
    reset_at_ms: int | None = 0,
) -> RateLimitObservation:
    return RateLimitObservation(
        http_status=http_status,
        bybit_ret_code=ret_code,
        header_state=state,  # type: ignore[arg-type]
        limit=limit,
        remaining=remaining,
        reset_at_ms=reset_at_ms,
    )


def test_low_headroom_reduces_rate_and_later_capacity_never_increases_it() -> None:
    pacer = AdaptiveRatePacer(15)

    pacer.observe(observation())
    pacer.observe(observation(limit=100, remaining=100))
    summary = pacer.summary()

    assert summary == {
        "automatic_increase_count": 0,
        "complete_header_observation_count": 2,
        "configured_target_rps": 15,
        "cooldown_event_count": 0,
        "final_effective_rps": 8,
        "header_absent_observation_count": 0,
        "invalid_header_observation_count": 0,
        "low_headroom_event_count": 1,
        "maximum_cooldown_ms": 0,
        "minimum_effective_rps": 8,
        "policy": ADAPTIVE_RATE_POLICY,
        "rate_limit_event_count": 0,
        "rate_reduction_count": 1,
        "response_observation_count": 2,
    }
    assert (
        verify_adaptive_rate_summary(
            summary,
            configured_target_rps=15,
            maximum_response_count=2,
        )
        == summary
    )


def test_rate_limit_error_halves_rate_and_403_enforces_official_cooldown() -> None:
    pacer = AdaptiveRatePacer(16)

    pacer.observe(
        observation(
            http_status=403,
            ret_code=None,
            state="absent",
            limit=None,
            remaining=None,
            reset_at_ms=None,
        )
    )
    summary = pacer.summary()

    assert summary["final_effective_rps"] == 8
    assert summary["rate_limit_event_count"] == 1
    assert summary["cooldown_event_count"] == 1
    assert summary["maximum_cooldown_ms"] == IP_BAN_COOLDOWN_MS
    with pytest.raises(AdaptiveRateLimitAbort, match="do not resume before"):
        pacer.wait()


def test_regional_access_block_aborts_without_inventing_ip_ban_cooldown() -> None:
    pacer = AdaptiveRatePacer(16)

    pacer.observe(
        RateLimitObservation(
            http_status=403,
            bybit_ret_code=None,
            header_state="absent",
            limit=None,
            remaining=None,
            reset_at_ms=None,
            failure_class="regional-access-block",
        )
    )
    summary = pacer.summary()

    assert summary["response_observation_count"] == 1
    assert summary["header_absent_observation_count"] == 1
    assert summary["rate_limit_event_count"] == 0
    assert summary["cooldown_event_count"] == 0
    assert summary["maximum_cooldown_ms"] == 0
    with pytest.raises(AdaptiveRateLimitAbort, match="officially supported") as captured:
        pacer.wait()
    assert captured.value.reason == "regional-access-block"


def test_summary_verifier_rejects_tampering_and_automatic_increase() -> None:
    summary = AdaptiveRatePacer(10).summary()
    summary["automatic_increase_count"] = 1

    with pytest.raises(AdaptiveRateLimitError, match="inconsistent"):
        verify_adaptive_rate_summary(
            summary,
            configured_target_rps=10,
            maximum_response_count=0,
        )
