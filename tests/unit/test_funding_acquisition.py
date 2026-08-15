from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import grid_data.funding_acquisition as funding_acquisition
import pytest
from grid_bybit_public import BybitPublicError, RateLimitObservation
from grid_bybit_public.transport import TransportError
from grid_data.funding_acquisition import (
    MAX_PAGE_ARTIFACT_BYTES,
    STAGING_METADATA_BYTES,
    FundingAcquisitionError,
    FundingJobSpec,
    FundingSeries,
    execute_funding_job,
    load_completed_funding_batch,
    preflight_funding_job,
    verify_completed_funding_job_integrity,
)
from grid_market_store import MIN_OPERATING_RESERVE_BYTES, CapacityBudget, HostSnapshot
from jsonschema import Draft202012Validator

JANUARY_1_2026_MS = 1_767_225_600_000
ROOT = Path(__file__).parents[2]


class FakeFundingClient:
    def __init__(
        self,
        *,
        fail_once: set[tuple[str, int]] | None = None,
        saturated: bool = False,
        missing_boundary: bool = False,
        out_of_range: bool = False,
    ) -> None:
        self.fail_once = set(fail_once or ())
        self.saturated = saturated
        self.missing_boundary = missing_boundary
        self.out_of_range = out_of_range
        self.calls: list[tuple[str, int, int, int]] = []

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
        self.calls.append((symbol, start_ms, end_ms, limit))
        identity = (symbol, start_ms)
        if identity in self.fail_once:
            self.fail_once.remove(identity)
            raise BybitPublicError("injected transient failure")
        if limit == 1:
            if self.missing_boundary:
                return ()
            timestamp = end_ms // (60 * 60_000) * (60 * 60_000)
            return (
                {
                    "symbol": symbol,
                    "fundingRate": "0.0001000",
                    "fundingRateTimestamp": str(timestamp),
                },
            )
        if self.saturated:
            timestamps = [start_ms + index * 60_000 for index in range(limit)]
        else:
            first = ((start_ms + 60 * 60_000 - 1) // (60 * 60_000)) * (60 * 60_000)
            timestamps = list(range(first, end_ms + 1, 60 * 60_000))
        if self.out_of_range and timestamps:
            timestamps[-1] = end_ms + 60_000
        return tuple(
            {
                "symbol": symbol,
                "fundingRate": "-0.0002000" if index % 2 else "0.0001000",
                "fundingRateTimestamp": str(timestamp),
            }
            for index, timestamp in enumerate(reversed(timestamps))
        )


class AlwaysFailFundingClient(FakeFundingClient):
    def funding_page(self, **kwargs: Any) -> tuple[dict[str, str], ...]:
        self.calls.append((kwargs["symbol"], kwargs["start_ms"], kwargs["end_ms"], kwargs["limit"]))
        raise BybitPublicError("injected persistent failure")


class RegionBlockedFundingClient(FakeFundingClient):
    def __init__(self) -> None:
        super().__init__()
        self._observation: RateLimitObservation | None = None

    def funding_page(self, **kwargs: Any) -> tuple[dict[str, str], ...]:
        self.calls.append((kwargs["symbol"], kwargs["start_ms"], kwargs["end_ms"], kwargs["limit"]))
        self._observation = RateLimitObservation(
            http_status=403,
            bybit_ret_code=None,
            header_state="absent",
            limit=None,
            remaining=None,
            reset_at_ms=None,
            failure_class="regional-access-block",
        )
        raise TransportError(
            "Bybit public API is unavailable from the current region",
            failure_class="regional-access-block",
        )

    def take_rate_limit_observation(self) -> RateLimitObservation | None:
        observed = self._observation
        self._observation = None
        return observed


def series(
    *,
    instrument_id: int = 1,
    symbol: str = "AAAUSDT",
    start_ms: int = JANUARY_1_2026_MS,
    end_ms: int = JANUARY_1_2026_MS + 180 * 60_000,
) -> FundingSeries:
    return FundingSeries(
        category="linear",
        symbol=symbol,
        instrument_id=instrument_id,
        launch_time_ms=JANUARY_1_2026_MS - 24 * 60 * 60_000,
        start_ms=start_ms,
        end_ms=end_ms,
    )


def spec(**overrides: object) -> FundingJobSpec:
    values: dict[str, object] = {
        "job_id": "funding-2026-01-b01-fixture",
        "series": (
            series(instrument_id=1, symbol="AAAUSDT"),
            series(instrument_id=9, symbol="BBBUSDT"),
        ),
        "request_sha256": "c" * 64,
        "instrument_evidence_sha256": "a" * 64,
        "capacity_evidence_sha256": "b" * 64,
        "page_span_minutes": 120,
        "page_limit": 3,
        "workers": 1,
        "target_rps": 96,
        "max_attempts": 1,
        "max_http_requests": 10,
    }
    values.update(overrides)
    return FundingJobSpec(**values)  # type: ignore[arg-type]


def budget(page_count: int = 6) -> CapacityBudget:
    return CapacityBudget(
        active_and_building_bytes=0,
        rest_staging_bytes=STAGING_METADATA_BYTES + page_count * MAX_PAGE_ARTIFACT_BYTES,
        operating_reserve_bytes=MIN_OPERATING_RESERVE_BYTES,
    )


def snapshot(
    root: Path,
    *,
    observed_at_ms: int = 1_000,
    free_bytes: int = 20 * 1024**3,
) -> HostSnapshot:
    return HostSnapshot(
        observed_at_ms=observed_at_ms,
        memory_total_bytes=16 * 1024**3,
        memory_available_bytes=8 * 1024**3,
        storage_kind="nvme",
        storage_device_id="fixture-nvme",
        volume_root=root.resolve(),
        volume_free_bytes=free_bytes,
    )


def preflight(tmp_path: Path, job_spec: FundingJobSpec | None = None):  # type: ignore[no-untyped-def]
    return preflight_funding_job(
        tmp_path / "history",
        job_spec or spec(),
        budget(),
        snapshot(tmp_path),
        now_ms=1_001,
        closed_before_ms=JANUARY_1_2026_MS + 181 * 60_000,
    )


def execute(plan, client):  # type: ignore[no-untyped-def]
    return execute_funding_job(
        plan,
        lambda: client,
        lambda: snapshot(plan.paths.staging_root.parent, observed_at_ms=1_001),
        now_ms=lambda: 1_002,
    )


def test_fixed_plan_predecessor_evidence_and_exact_batch(tmp_path: Path) -> None:
    plan = preflight(tmp_path)
    assert not plan.paths.staging_root.exists()
    assert [(item.instrument_id, item.scope, item.limit) for item in plan.tasks] == [
        (1, "boundary", 1),
        (1, "range", 3),
        (1, "range", 3),
        (9, "boundary", 1),
        (9, "range", 3),
        (9, "range", 3),
    ]

    client = FakeFundingClient()
    completed = execute(plan, client)
    assert completed.page_count == 6
    assert completed.row_count == 8
    assert len(client.calls) == 6
    manifest = json.loads(completed.manifest_path.read_text(encoding="utf-8"))
    assert manifest["boundary_row_count"] == 2
    assert manifest["boundary_evidence_sha256"] == completed.boundary_evidence_sha256
    assert manifest["source_policy"] == {
        "endpoint": "/v5/market/funding/history",
        "page_limit": 3,
        "page_span_minutes": 120,
        "private_credentials_used": False,
        "saturated_range_pages_accepted": False,
    }
    schema_root = ROOT / "schemas" / "market" / "v1"
    for schema_name, artifact in (
        ("bybit-funding-history-plan.schema.json", completed.plan_path),
        ("bybit-funding-history-page.schema.json", completed.job_root / "pages/00000000.json"),
        ("bybit-funding-history-acquisition.schema.json", completed.manifest_path),
        ("history-acquisition-receipt.schema.json", completed.receipt_path),
    ):
        schema = json.loads((schema_root / schema_name).read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(json.loads(artifact.read_text(encoding="utf-8")))
    batch = load_completed_funding_batch(completed.job_root)
    assert batch.table.num_rows == 8
    assert batch.table.column("instrument_id").to_pylist() == [1, 1, 1, 1, 9, 9, 9, 9]
    assert batch.table.column("funding_interval_minutes").to_pylist() == [60] * 8
    assert all(
        value.startswith("bybit-funding-page-sha256:")
        for value in batch.table.column("ingestion_id").to_pylist()
    )


def test_failed_run_resumes_only_missing_pages_and_complete_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = preflight(tmp_path)
    failing = FakeFundingClient(fail_once={("AAAUSDT", JANUARY_1_2026_MS)})
    with pytest.raises(FundingAcquisitionError, match="failed after"):
        execute(plan, failing)
    resumed = preflight(tmp_path)
    assert 0 < len(resumed.pending_tasks) < len(resumed.tasks)
    replacement = FakeFundingClient()
    completed = execute(resumed, replacement)
    assert len(replacement.calls) == len(resumed.pending_tasks)

    monkeypatch.setattr(
        "grid_data.funding_acquisition._validate_page_payload",
        lambda *_args: (_ for _ in ()).throw(AssertionError("semantic decode was called")),
    )
    complete_plan = preflight(tmp_path)
    assert complete_plan.existing_complete is True
    never_called = AlwaysFailFundingClient()
    same = execute(complete_plan, never_called)
    assert same.manifest_sha256 == completed.manifest_sha256
    assert never_called.calls == []


def test_new_completion_semantically_admits_pages_once_then_reverifies_integrity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = preflight(tmp_path)
    original = funding_acquisition._validate_page_payload
    original_integrity = funding_acquisition.verify_completed_funding_job_integrity
    semantic_admission_count = 0
    integrity_verification_count = 0

    def counted(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal semantic_admission_count
        semantic_admission_count += 1
        return original(*args, **kwargs)

    def counted_integrity(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal integrity_verification_count
        integrity_verification_count += 1
        return original_integrity(*args, **kwargs)

    monkeypatch.setattr(funding_acquisition, "_validate_page_payload", counted)
    monkeypatch.setattr(
        funding_acquisition,
        "verify_completed_funding_job_integrity",
        counted_integrity,
    )

    completed = execute(plan, FakeFundingClient())

    assert semantic_admission_count == len(plan.tasks)
    assert integrity_verification_count == 1
    assert verify_completed_funding_job_integrity(completed.job_root).manifest_sha256 == (
        completed.manifest_sha256
    )


def test_regional_403_aborts_funding_once_without_retrying(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    one_page_spec = spec(
        series=(series(end_ms=JANUARY_1_2026_MS),),
        workers=1,
        max_attempts=3,
        max_http_requests=6,
    )
    plan = preflight_funding_job(
        tmp_path / "history",
        one_page_spec,
        budget(page_count=2),
        snapshot(tmp_path),
        now_ms=1_001,
        closed_before_ms=JANUARY_1_2026_MS + 60_000,
    )
    client = RegionBlockedFundingClient()
    monkeypatch.setattr("grid_data.funding_acquisition.time.sleep", lambda _seconds: None)

    with pytest.raises(FundingAcquisitionError, match="officially supported network and region"):
        execute(plan, client)

    assert len(client.calls) == 1
    assert plan.paths.plan_path.is_file()
    assert not plan.paths.receipt_path.exists()
    assert not plan.paths.run_lock.exists()


@pytest.mark.parametrize(
    ("client", "message"),
    [
        (FakeFundingClient(saturated=True), "saturated"),
        (FakeFundingClient(missing_boundary=True), "exactly one"),
        (FakeFundingClient(out_of_range=True), "escapes"),
    ],
)
def test_ambiguous_or_malformed_source_fails_without_completion(
    tmp_path: Path,
    client: FakeFundingClient,
    message: str,
) -> None:
    plan = preflight(tmp_path)
    with pytest.raises(FundingAcquisitionError, match=message):
        execute(plan, client)
    assert not plan.paths.receipt_path.exists()


def test_preflight_blocks_future_cross_partition_and_underbudget(tmp_path: Path) -> None:
    root = tmp_path / "history"
    with pytest.raises(FundingAcquisitionError, match="only closed"):
        preflight_funding_job(
            root,
            spec(),
            budget(),
            snapshot(tmp_path),
            now_ms=1_001,
            closed_before_ms=JANUARY_1_2026_MS + 180 * 60_000,
        )
    with pytest.raises(FundingAcquisitionError, match="staging budget"):
        preflight_funding_job(
            root,
            spec(),
            CapacityBudget(
                active_and_building_bytes=0,
                rest_staging_bytes=STAGING_METADATA_BYTES,
                operating_reserve_bytes=MIN_OPERATING_RESERVE_BYTES,
            ),
            snapshot(tmp_path),
            now_ms=1_001,
            closed_before_ms=JANUARY_1_2026_MS + 181 * 60_000,
        )
    with pytest.raises(FundingAcquisitionError, match="month/bucket"):
        spec(series=(series(end_ms=1_769_904_000_000),))
    assert not root.exists()


def test_tamper_or_stale_lock_blocks_resume(tmp_path: Path) -> None:
    plan = preflight(tmp_path)
    with pytest.raises(FundingAcquisitionError):
        execute(plan, FakeFundingClient(fail_once={("AAAUSDT", JANUARY_1_2026_MS)}))
    staged = next(
        path
        for path in plan.paths.pages_root.glob("*.json")
        if not path.name.endswith(".receipt.json")
    )
    staged.write_bytes(staged.read_bytes() + b" ")
    with pytest.raises(FundingAcquisitionError, match=r"canonical|receipt"):
        preflight(tmp_path)

    second = preflight(tmp_path, spec(job_id="funding-2026-01-b01-lock"))
    second.paths.pages_root.mkdir(parents=True)
    second.paths.run_lock.mkdir()
    with pytest.raises(FundingAcquisitionError, match="run directory"):
        preflight(tmp_path, spec(job_id="funding-2026-01-b01-lock"))


def test_integrity_verifier_hashes_pages_without_semantic_decode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    completed = execute(preflight(tmp_path), FakeFundingClient())
    monkeypatch.setattr(
        funding_acquisition,
        "_validate_page_payload",
        lambda *_args: (_ for _ in ()).throw(AssertionError("semantic decode was called")),
    )

    assert verify_completed_funding_job_integrity(completed.job_root).manifest_sha256 == (
        completed.manifest_sha256
    )
    page = next(
        path
        for path in (completed.job_root / "pages").glob("*.json")
        if not path.name.endswith(".receipt.json")
    )
    page.write_bytes(page.read_bytes() + b" ")
    with pytest.raises(FundingAcquisitionError, match="receipt"):
        verify_completed_funding_job_integrity(completed.job_root)
