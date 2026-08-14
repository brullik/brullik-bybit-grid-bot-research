from __future__ import annotations

import http.client
import socket
from collections.abc import Callable

import pytest
from grid_bybit_public.transport import TransportError
from grid_data.cli import parser as command_parser
from grid_data.history_supervisor import (
    HistoryCampaignSupervisorError,
    HistoryCampaignSupervisorPolicy,
    classify_history_campaign_failure,
    run_history_campaign_supervisor,
)
from grid_data.public_rate_limit import AdaptiveRateLimitAbort


def nested_failure(root: Exception, wrapper: Exception) -> RuntimeError:
    wrapper.__cause__ = root
    outer = RuntimeError("campaign failed")
    outer.__cause__ = wrapper
    return outer


def transient_dns_failure() -> RuntimeError:
    return nested_failure(
        socket.gaierror(11001, "host not found"),
        TransportError("Bybit request failed after 1 attempts"),
    )


def test_failure_classification_is_narrow_and_rate_limits_remain_explicit() -> None:
    assert classify_history_campaign_failure(transient_dns_failure()) == "transient-dns"
    assert (
        classify_history_campaign_failure(
            nested_failure(
                http.client.HTTPException("HTTP status 503"),
                TransportError("Bybit request failed after 1 attempts"),
            )
        )
        == "transient-upstream"
    )
    assert (
        classify_history_campaign_failure(
            TransportError("Bybit HTTP error 429", failure_class="rate-limit")
        )
        == "non-retryable"
    )
    assert (
        classify_history_campaign_failure(
            AdaptiveRateLimitAbort(1_000, reason="regional-access-block")
        )
        == "non-retryable"
    )
    assert classify_history_campaign_failure(ValueError("contract mismatch")) == "non-retryable"


@pytest.mark.parametrize(
    ("maximum", "cooldown"),
    ((0, 30), (17, 30), (True, 30), (8, 9), (8, 601), (8, False)),
)
def test_policy_rejects_unbounded_or_invalid_values(maximum: object, cooldown: object) -> None:
    with pytest.raises(HistoryCampaignSupervisorError):
        HistoryCampaignSupervisorPolicy(  # type: ignore[arg-type]
            max_invocations=maximum,
            base_cooldown_seconds=cooldown,
        )


def test_cli_exposes_bounded_supervisor_without_changing_standard_campaign() -> None:
    supervised = command_parser().parse_args(
        [
            "supervise-history-campaign",
            "--request",
            "request.json",
            "--instrument-registry",
            "registry.json",
            "--capacity-evidence",
            "capacity.json",
            "--staging-root",
            "history",
            "--max-invocations",
            "4",
            "--base-cooldown-seconds",
            "20",
            "--execute",
        ]
    )
    standard = command_parser().parse_args(
        [
            "history-campaign",
            "--request",
            "request.json",
            "--instrument-registry",
            "registry.json",
            "--capacity-evidence",
            "capacity.json",
            "--staging-root",
            "history",
        ]
    )

    assert supervised.handler.__name__ == "_supervise_history_campaign"
    assert supervised.max_invocations == 4
    assert supervised.base_cooldown_seconds == 20
    assert supervised.execute is True
    assert standard.handler.__name__ == "_history_campaign"
    assert standard.execute is False


def test_supervisor_resumes_dns_failures_with_bounded_exponential_cooldown() -> None:
    calls = 0
    events: list[dict[str, object]] = []
    sleeps: list[float] = []

    def operation() -> int:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise transient_dns_failure()
        return 0

    result = run_history_campaign_supervisor(
        operation,
        HistoryCampaignSupervisorPolicy(max_invocations=4, base_cooldown_seconds=30),
        emit=events.append,
        sleep=sleeps.append,
    )

    assert result == 0
    assert calls == 3
    assert sleeps == [30.0, 60.0]
    failures = [event for event in events if event["event"] == "invocation-failed"]
    assert [event["failure_class"] for event in failures] == [
        "transient-dns",
        "transient-dns",
    ]
    assert [event["cooldown_seconds"] for event in failures] == [30, 60]
    assert events[-1]["event"] == "supervisor-complete"


@pytest.mark.parametrize(
    "failure_factory",
    (
        lambda: ValueError("contract mismatch"),
        lambda: TransportError("Bybit HTTP error 403", failure_class="rate-limit"),
        lambda: AdaptiveRateLimitAbort(1_000, reason="regional-access-block"),
    ),
)
def test_supervisor_never_retries_non_transient_failures(
    failure_factory: Callable[[], Exception],
) -> None:
    events: list[dict[str, object]] = []
    sleeps: list[float] = []

    def operation() -> int:
        raise failure_factory()

    with pytest.raises((ValueError, TransportError, AdaptiveRateLimitAbort)):
        run_history_campaign_supervisor(
            operation,
            HistoryCampaignSupervisorPolicy(),
            emit=events.append,
            sleep=sleeps.append,
        )

    assert sleeps == []
    assert events[-1] == {
        "contract": "grid.history-campaign-supervisor-event/v1",
        "cooldown_seconds": 0,
        "event": "invocation-failed",
        "failure_class": "non-retryable",
        "invocation": 1,
        "max_invocations": 8,
        "retry_scheduled": False,
    }


def test_supervisor_stops_at_invocation_budget() -> None:
    events: list[dict[str, object]] = []
    sleeps: list[float] = []

    def operation() -> int:
        raise transient_dns_failure()

    with pytest.raises(RuntimeError, match="campaign failed"):
        run_history_campaign_supervisor(
            operation,
            HistoryCampaignSupervisorPolicy(max_invocations=2, base_cooldown_seconds=10),
            emit=events.append,
            sleep=sleeps.append,
        )

    assert sleeps == [10.0]
    failures = [event for event in events if event["event"] == "invocation-failed"]
    assert failures[-1]["retry_scheduled"] is False
    assert failures[-1]["cooldown_seconds"] == 0
