from __future__ import annotations

import json
from pathlib import Path
from threading import local
from typing import Any

import pytest
from grid_bybit_public import BybitPublicError, RateLimitObservation
from grid_contracts.canonical import canonical_sha256
from grid_data.evidence import publish_evidence
from grid_data.history_acquisition import HistoryAcquisitionError
from grid_data.history_campaign import (
    CAMPAIGN_REQUEST_CONTRACT,
    LIFECYCLE_POLICY,
    HistoryCampaignError,
    execute_history_campaign,
    preflight_history_campaign,
    verify_completed_history_campaign,
)
from grid_data.history_campaign_evidence import build_history_campaign_evidence
from grid_data.instrument_registry import build_instrument_registry
from grid_market_store import HostSnapshot
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[2]
JANUARY_31_2026_2358_MS = 1_769_903_880_000
FEBRUARY_1_2026_0001_MS = JANUARY_31_2026_2358_MS + 3 * 60_000


class FakeKlineClient:
    def __init__(self, *, fail_once: bool = False) -> None:
        self.fail_once = fail_once
        self.calls: list[tuple[str, int, int, str]] = []
        self._thread_state = local()

    def kline_page(
        self,
        *,
        kind: str,
        symbol: str,
        start_ms: int,
        end_ms: int,
        category: str = "linear",
        limit: int = 1000,
    ) -> tuple[tuple[str, ...], ...]:
        del category, limit
        self._thread_state.observation = RateLimitObservation(200, 0, "absent", None, None, None)
        self.calls.append((symbol, start_ms, end_ms, kind))
        if self.fail_once:
            self.fail_once = False
            raise BybitPublicError("injected campaign interruption")
        rows = []
        for timestamp in reversed(range(start_ms, end_ms + 1, 60_000)):
            row = (str(timestamp), "10", "11", "9", "10")
            if kind == "trade":
                row += ("100", "1000")
            rows.append(row)
        return tuple(rows)

    def take_rate_limit_observation(self) -> RateLimitObservation | None:
        observed = getattr(self._thread_state, "observation", None)
        self._thread_state.observation = None
        return observed


class FakeFundingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int, int]] = []
        self._thread_state = local()

    def funding_page(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        category: str = "linear",
        limit: int = 200,
    ) -> tuple[dict[str, str], ...]:
        del category
        self._thread_state.observation = RateLimitObservation(200, 0, "absent", None, None, None)
        self.calls.append((symbol, start_ms, end_ms, limit))
        if limit != 1:
            return ()
        return (
            {
                "symbol": symbol,
                "fundingRate": "0.0001",
                "fundingRateTimestamp": str(end_ms // 60_000 * 60_000),
            },
        )

    def take_rate_limit_observation(self) -> RateLimitObservation | None:
        observed = getattr(self._thread_state, "observation", None)
        self._thread_state.observation = None
        return observed


class NeverKlineClient(FakeKlineClient):
    def kline_page(self, **kwargs: Any) -> tuple[tuple[str, ...], ...]:
        raise AssertionError(f"completed campaign called kline client: {kwargs}")


class NeverFundingClient(FakeFundingClient):
    def funding_page(self, **kwargs: Any) -> tuple[dict[str, str], ...]:
        raise AssertionError(f"completed campaign called funding client: {kwargs}")


class UnobservedKlineClient:
    def __init__(self) -> None:
        self._delegate = FakeKlineClient()

    def kline_page(self, **kwargs: Any) -> tuple[tuple[str, ...], ...]:
        return self._delegate.kline_page(**kwargs)


class UnobservedFundingClient:
    def __init__(self) -> None:
        self._delegate = FakeFundingClient()

    def funding_page(self, **kwargs: Any) -> tuple[dict[str, str], ...]:
        return self._delegate.funding_page(**kwargs)


class RetryWithoutResponseKlineClient(FakeKlineClient):
    def __init__(self) -> None:
        super().__init__()
        self._fail_once_without_response = True

    def kline_page(self, **kwargs: Any) -> tuple[tuple[str, ...], ...]:
        if self._fail_once_without_response:
            self._fail_once_without_response = False
            raise BybitPublicError("injected transport failure without response")
        return super().kline_page(**kwargs)


def inventory_record(
    symbol: str,
    source_symbol_id: int,
    *,
    launch_time_ms: int = 1_600_000_000_000,
    delivery_time_ms: int = 0,
) -> dict[str, object]:
    return {
        "base_coin": symbol.removesuffix("USDT"),
        "contract_type": "LinearPerpetual",
        "delivery_time_ms": delivery_time_ms,
        "funding_interval_minutes": 480,
        "launch_time_ms": launch_time_ms,
        "max_leverage": "100",
        "max_order_quantity": "1000000",
        "min_leverage": "1",
        "min_order_quantity": "0.001",
        "quantity_step": "0.001",
        "quote_coin": "USDT",
        "settle_coin": "USDT",
        "source_payload_sha256": f"{source_symbol_id:064x}",
        "source_symbol_id": source_symbol_id,
        "status": "Trading" if delivery_time_ms == 0 else "Closed",
        "symbol": symbol,
        "tick_size": "0.0001",
    }


def registry_payload(*, records: list[dict[str, object]] | None = None) -> dict[str, object]:
    inventory: dict[str, object] = {
        "content_sha256": "a" * 64,
        "evidence_schema": "grid.bybit-public-inventory/v1",
        "fetched_at_utc": "2026-08-13T00:00:00Z",
        "inventory_status": "partial",
        "records": records or [inventory_record("AAAUSDT", 1), inventory_record("BBBUSDT", 2)],
    }
    return build_instrument_registry(inventory, inventory_artifact_sha256="b" * 64)


def capacity_payload() -> dict[str, object]:
    return {
        "disk_headroom": {
            "scenarios": [
                {
                    "id": "full-rebuild-active-plus-building",
                    "required_bytes": 90_000_000_000,
                }
            ]
        },
        "evidence_schema": "grid.current-universe-capacity/v1",
        "layout_projections": [
            {
                "layout": {
                    "bucket_count": 8,
                    "compression": "zstd",
                    "compression_level": 3,
                    "numeric_representation": "hybrid_int64_decimal",
                    "target_file_mb": 16,
                }
            }
        ],
    }


def evidence_files(
    tmp_path: Path,
    *,
    records: list[dict[str, object]] | None = None,
) -> tuple[Path, Path]:
    registry, _ = publish_evidence(tmp_path / "registry.json", registry_payload(records=records))
    capacity, _ = publish_evidence(tmp_path / "capacity.json", capacity_payload())
    return registry, capacity


def request_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "contract": CAMPAIGN_REQUEST_CONTRACT,
        "campaign_id": "fixture-campaign",
        "kinds": ["trade", "mark", "funding"],
        "symbols": ["BBBUSDT", "AAAUSDT"],
        "start_ms": JANUARY_31_2026_2358_MS,
        "end_ms": FEBRUARY_1_2026_0001_MS,
        "lifecycle_policy": LIFECYCLE_POLICY,
        "history_page_limit": 1,
        "funding_page_limit": 200,
        "funding_page_span_minutes": 1,
        "workers": 1,
        "target_rps": 96,
        "max_attempts": 1,
    }
    payload.update(overrides)
    return payload


def write_request(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "campaign-request.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def snapshot(
    tmp_path: Path,
    *,
    observed_at_ms: int = 1_000,
    free_bytes: int = 140 * 1024**3,
) -> HostSnapshot:
    return HostSnapshot(
        observed_at_ms=observed_at_ms,
        memory_total_bytes=16 * 1024**3,
        memory_available_bytes=8 * 1024**3,
        storage_kind="nvme",
        storage_device_id="fixture-nvme",
        volume_root=tmp_path.resolve(),
        volume_free_bytes=free_bytes,
    )


def preflight(
    tmp_path: Path,
    *,
    request: dict[str, object] | None = None,
    records: list[dict[str, object]] | None = None,
    free_bytes: int = 140 * 1024**3,
):  # type: ignore[no-untyped-def]
    registry, capacity = evidence_files(tmp_path, records=records)
    return preflight_history_campaign(
        write_request(tmp_path, request or request_payload()),
        instrument_registry_path=registry,
        capacity_evidence_path=capacity,
        staging_root=tmp_path / "history",
        snapshot=snapshot(tmp_path, free_bytes=free_bytes),
        now_ms=1_001,
        closed_before_ms=FEBRUARY_1_2026_0001_MS + 60_000,
    )


def execute(plan, kline, funding):  # type: ignore[no-untyped-def]
    return execute_history_campaign(
        plan,
        kline_client_factory=lambda: kline,
        funding_client_factory=lambda: funding,
        snapshot_provider=lambda: snapshot(plan.staging_root.parent, observed_at_ms=1_001),
        now_ms=lambda: 1_002,
    )


def test_campaign_schema_split_order_and_no_mutation(tmp_path: Path) -> None:
    request = request_payload()
    schema = json.loads(
        (ROOT / "schemas/market/v1/public-history-campaign-request.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema).validate(request)
    plan = preflight(tmp_path, request=request)

    assert len(plan.jobs) == 12
    assert not plan.campaign_root.exists()
    assert not plan.staging_root.exists()
    assert [(job.year, job.month, job.kind, job.bucket) for job in plan.jobs] == [
        (2026, 1, "trade", 1),
        (2026, 1, "trade", 2),
        (2026, 1, "mark", 1),
        (2026, 1, "mark", 2),
        (2026, 1, "funding", 1),
        (2026, 1, "funding", 2),
        (2026, 2, "trade", 1),
        (2026, 2, "trade", 2),
        (2026, 2, "mark", 1),
        (2026, 2, "mark", 2),
        (2026, 2, "funding", 1),
        (2026, 2, "funding", 2),
    ]
    assert all(
        job.request_payload["max_http_requests"]
        == job.planned_page_count * job.request_payload["max_attempts"]
        for job in plan.jobs
    )
    assert plan.plan_payload["source_policy"]["tick_rows_requested"] is False  # type: ignore[index]
    assert plan.required_free_bytes > 98_000_000_000


def test_campaign_executes_verifies_and_complete_rerun_is_idempotent(tmp_path: Path) -> None:
    plan = preflight(tmp_path)
    kline = FakeKlineClient()
    funding = FakeFundingClient()
    completed = execute(plan, kline, funding)

    assert completed.job_count == 12
    assert completed.page_count == sum(job.planned_page_count for job in plan.jobs)
    assert completed.row_count == 16
    assert completed.http_request_count == completed.page_count
    assert set(path.name for path in completed.campaign_root.iterdir()) == {
        "plan.json",
        "plan.receipt.json",
        "manifest.json",
        "completion-receipt.json",
    }
    schema_root = ROOT / "schemas/market/v1"
    for name, artifact in (
        ("public-history-campaign-plan.schema.json", completed.plan_path),
        ("public-history-campaign-manifest.schema.json", completed.manifest_path),
        (
            "history-campaign-receipt.schema.json",
            completed.campaign_root / "plan.receipt.json",
        ),
        ("history-campaign-receipt.schema.json", completed.receipt_path),
    ):
        schema = json.loads((schema_root / name).read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(json.loads(artifact.read_text(encoding="utf-8")))
    verified = verify_completed_history_campaign(completed.campaign_root)
    assert verified.manifest_sha256 == completed.manifest_sha256

    registry = tmp_path / "registry.json"
    capacity = tmp_path / "capacity.json"
    resumed = preflight_history_campaign(
        tmp_path / "campaign-request.json",
        instrument_registry_path=registry,
        capacity_evidence_path=capacity,
        staging_root=tmp_path / "history",
        snapshot=snapshot(tmp_path, observed_at_ms=1_001),
        now_ms=1_002,
        closed_before_ms=FEBRUARY_1_2026_0001_MS + 60_000,
    )
    assert resumed.existing_complete is True
    same = execute(resumed, NeverKlineClient(), NeverFundingClient())
    assert same.manifest_sha256 == completed.manifest_sha256


def test_interrupted_child_is_resumed_without_refetching_receipted_pages(tmp_path: Path) -> None:
    plan = preflight(tmp_path)
    with pytest.raises(HistoryAcquisitionError, match="failed after"):
        execute(plan, FakeKlineClient(fail_once=True), FakeFundingClient())
    assert plan.plan_path.is_file()
    existing_pages = list((plan.jobs[0].plan.paths.pages_root).glob("[0-9]*.json"))
    assert existing_pages

    registry = tmp_path / "registry.json"
    capacity = tmp_path / "capacity.json"
    resumed = preflight_history_campaign(
        tmp_path / "campaign-request.json",
        instrument_registry_path=registry,
        capacity_evidence_path=capacity,
        staging_root=tmp_path / "history",
        snapshot=snapshot(tmp_path, observed_at_ms=1_001),
        now_ms=1_002,
        closed_before_ms=FEBRUARY_1_2026_0001_MS + 60_000,
    )
    assert sum(job.pending_page_count for job in resumed.jobs) < sum(
        job.planned_page_count for job in resumed.jobs
    )
    completed = execute(resumed, FakeKlineClient(), FakeFundingClient())
    assert completed.job_count == len(resumed.jobs)


def test_campaign_clips_each_series_to_registry_lifecycle(tmp_path: Path) -> None:
    records = [
        inventory_record(
            "AAAUSDT",
            1,
            launch_time_ms=JANUARY_31_2026_2358_MS + 60_000,
            delivery_time_ms=FEBRUARY_1_2026_0001_MS - 60_000,
        )
    ]
    plan = preflight(
        tmp_path,
        request=request_payload(kinds=["trade"], symbols=["AAAUSDT"]),
        records=records,
    )
    assert len(plan.jobs) == 2
    january = plan.jobs[0].request_payload["series"][0]  # type: ignore[index]
    february = plan.jobs[1].request_payload["series"][0]  # type: ignore[index]
    assert january["start_ms"] == JANUARY_31_2026_2358_MS + 60_000
    assert january["end_ms"] == JANUARY_31_2026_2358_MS + 60_000
    assert february["start_ms"] == FEBRUARY_1_2026_0001_MS - 60_000
    assert february["end_ms"] == FEBRUARY_1_2026_0001_MS - 60_000


def test_campaign_rejects_aggregate_disk_shortfall_before_mutation(tmp_path: Path) -> None:
    with pytest.raises(HistoryCampaignError, match="aggregate pending campaign"):
        preflight(tmp_path, free_bytes=99_000_000_000)
    assert not (tmp_path / "history").exists()


def test_campaign_rejects_unbounded_or_empty_lifecycle_scope(tmp_path: Path) -> None:
    with pytest.raises(HistoryCampaignError, match="120-month"):
        preflight(
            tmp_path,
            request=request_payload(start_ms=1_420_070_400_000),
        )

    other = tmp_path / "empty"
    other.mkdir()
    delivered = JANUARY_31_2026_2358_MS - 60_000
    with pytest.raises(HistoryCampaignError, match="no lifecycle intersection"):
        preflight(
            other,
            request=request_payload(kinds=["trade"], symbols=["AAAUSDT"]),
            records=[inventory_record("AAAUSDT", 1, delivery_time_ms=delivered)],
        )


def test_campaign_detects_tampered_outer_or_child_artifact(tmp_path: Path) -> None:
    completed = execute(preflight(tmp_path), FakeKlineClient(), FakeFundingClient())
    manifest = json.loads(completed.manifest_path.read_text(encoding="utf-8"))
    assert manifest["campaign_plan_sha256"] == canonical_sha256(
        json.loads(completed.plan_path.read_text(encoding="utf-8"))
    )
    completed.manifest_path.write_bytes(completed.manifest_path.read_bytes() + b" ")
    with pytest.raises(HistoryCampaignError, match=r"canonical|receipt"):
        verify_completed_history_campaign(completed.campaign_root)

    child_root = tmp_path / "child-tamper"
    child_root.mkdir()
    child_completed = execute(preflight(child_root), FakeKlineClient(), FakeFundingClient())
    first_child = child_completed.campaign_root.parent.parent.joinpath(
        *json.loads(child_completed.plan_path.read_text(encoding="utf-8"))["jobs"][0][
            "job_root"
        ].split("/")
    )
    child_manifest = first_child / "manifest.json"
    child_manifest.write_bytes(child_manifest.read_bytes() + b" ")
    with pytest.raises(HistoryAcquisitionError, match=r"canonical|receipt"):
        verify_completed_history_campaign(child_completed.campaign_root)


def test_campaign_evidence_is_schema_valid_aggregate_only_and_redacted(tmp_path: Path) -> None:
    completed = execute(preflight(tmp_path), FakeKlineClient(), FakeFundingClient())
    payload = build_history_campaign_evidence(
        completed.campaign_root,
        generated_at_utc="2026-08-13T12:00:00Z",
        software_identity="git:" + "1" * 40,
        require_complete_throttling_evidence=True,
    )
    schema = json.loads(
        (ROOT / "schemas/evidence/v1/phase2-public-history-campaign.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema).validate(payload)
    hash_input = dict(payload)
    embedded = hash_input.pop("content_sha256")
    assert embedded == canonical_sha256(hash_input)
    assert payload["landing"]["job_count"] == 12  # type: ignore[index]
    assert payload["landing"]["row_count"] == 16  # type: ignore[index]
    assert payload["landing"]["retry_count"] == 0  # type: ignore[index]
    assert payload["adaptive_throttling"] == {  # type: ignore[index]
        "automatic_increase_count": 0,
        "child_job_count": 12,
        "completed_page_response_coverage_complete": True,
        "complete_header_observation_count": 0,
        "configured_target_rps": 96,
        "cooldown_event_count": 0,
        "header_absent_observation_count": payload["landing"]["http_request_count"],  # type: ignore[index]
        "invalid_header_observation_count": 0,
        "low_headroom_event_count": 0,
        "maximum_child_final_effective_rps": 96,
        "maximum_cooldown_ms": 0,
        "minimum_child_effective_rps": 96,
        "minimum_child_final_effective_rps": 96,
        "policy": "bybit-v5-response-header-decrease-only-v1",
        "rate_limit_event_count": 0,
        "rate_reduction_count": 0,
        "response_observation_count": payload["landing"]["http_request_count"],  # type: ignore[index]
        "response_observation_classification_complete": True,
        "transport_attempt_accounting_complete": True,
        "transport_attempt_count": payload["landing"]["http_request_count"],  # type: ignore[index]
        "transport_attempt_without_response_count": 0,
    }
    assert payload["timing"] == {  # type: ignore[index]
        "campaign_completed_at_ms": 1_002,
        "campaign_elapsed_ms": 0,
        "campaign_started_at_ms": 1_002,
        "summed_child_elapsed_ms": 0,
        "timed_child_count": 12,
    }
    assert payload["scope"] == {  # type: ignore[index]
        "bucket_count": 2,
        "end_ms": FEBRUARY_1_2026_0001_MS,
        "kind_count": 3,
        "month_count": 2,
        "start_ms": JANUARY_31_2026_2358_MS,
        "symbol_count": 2,
    }
    rendered = json.dumps(payload).lower()
    for forbidden in (
        "aaausdt",
        "bbbusdt",
        "c:\\",
        "/home/",
        '"open"',
        "fundingrate",
        "api_key",
        "device_identity",
    ):
        assert forbidden not in rendered


def test_campaign_evidence_rejects_mutable_software_identity(tmp_path: Path) -> None:
    completed = execute(preflight(tmp_path), FakeKlineClient(), FakeFundingClient())
    with pytest.raises(HistoryCampaignError, match="software identity"):
        build_history_campaign_evidence(
            completed.campaign_root,
            generated_at_utc="2026-08-13T12:00:00Z",
            software_identity="working-tree",
        )


def test_campaign_evidence_strict_throttling_rejects_unobserved_responses(
    tmp_path: Path,
) -> None:
    completed = execute(preflight(tmp_path), UnobservedKlineClient(), UnobservedFundingClient())
    with pytest.raises(HistoryCampaignError, match="every completed page response"):
        build_history_campaign_evidence(
            completed.campaign_root,
            generated_at_utc="2026-08-13T12:00:00Z",
            software_identity="git:" + "1" * 40,
            require_complete_throttling_evidence=True,
        )


def test_campaign_evidence_accounts_retry_without_http_response(tmp_path: Path) -> None:
    completed = execute(
        preflight(tmp_path, request=request_payload(max_attempts=2)),
        RetryWithoutResponseKlineClient(),
        FakeFundingClient(),
    )
    payload = build_history_campaign_evidence(
        completed.campaign_root,
        generated_at_utc="2026-08-13T12:00:00Z",
        software_identity="git:" + "1" * 40,
        require_complete_throttling_evidence=True,
    )
    adaptive = payload["adaptive_throttling"]  # type: ignore[assignment]
    assert adaptive["completed_page_response_coverage_complete"] is True
    assert adaptive["transport_attempt_accounting_complete"] is True
    assert adaptive["transport_attempt_without_response_count"] == 1
    assert adaptive["transport_attempt_count"] == payload["landing"]["http_request_count"]  # type: ignore[index]
    assert adaptive["response_observation_count"] == payload["landing"]["page_count"]  # type: ignore[index]
