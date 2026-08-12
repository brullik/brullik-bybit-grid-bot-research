from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from grid_bybit_public import BybitPublicError
from grid_data.history_acquisition import (
    MAX_PAGE_ARTIFACT_BYTES,
    STAGING_METADATA_BYTES,
    HistoryAcquisitionError,
    HistoryJobSpec,
    HistorySeries,
    execute_history_job,
    load_completed_history_batch,
    preflight_history_job,
)
from grid_data.host_probe import probe_host_snapshot
from grid_market_store import MIN_OPERATING_RESERVE_BYTES, CapacityBudget, HostSnapshot
from jsonschema import Draft202012Validator

JANUARY_1_2026_MS = 1_767_225_600_000
ROOT = Path(__file__).parents[2]


class FakeKlineClient:
    def __init__(
        self,
        *,
        fail_once: set[tuple[str, int]] | None = None,
        empty: set[tuple[str, int]] | None = None,
        out_of_range: bool = False,
    ) -> None:
        self.fail_once = set(fail_once or ())
        self.empty = set(empty or ())
        self.out_of_range = out_of_range
        self.calls: list[tuple[str, int, int, str, int]] = []

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
        self.calls.append((symbol, start_ms, end_ms, kind, limit))
        identity = (symbol, start_ms)
        if identity in self.fail_once:
            self.fail_once.remove(identity)
            raise BybitPublicError("injected transient failure")
        if identity in self.empty:
            return ()
        timestamps = list(range(start_ms, end_ms + 1, 60_000))
        if self.out_of_range:
            timestamps[-1] = end_ms + 60_000
        rows = []
        for index, timestamp in enumerate(reversed(timestamps)):
            base = 100 + index
            row = (
                str(timestamp),
                str(base),
                str(base + 2),
                str(base - 1),
                str(base + 1),
            )
            if kind == "trade":
                row += ("10.5000", "1050.000000000001")
            rows.append(row)
        return tuple(rows)


class AlwaysFailClient(FakeKlineClient):
    def kline_page(self, **kwargs: Any) -> tuple[tuple[str, ...], ...]:
        self.calls.append(
            (
                kwargs["symbol"],
                kwargs["start_ms"],
                kwargs["end_ms"],
                kwargs["kind"],
                kwargs["limit"],
            )
        )
        raise BybitPublicError("injected persistent failure")


def series(
    *,
    instrument_id: int = 1,
    symbol: str = "AAAUSDT",
    start_ms: int = JANUARY_1_2026_MS,
    end_ms: int = JANUARY_1_2026_MS + 120_000,
    kind: str = "trade",
) -> HistorySeries:
    return HistorySeries(
        kind=kind,  # type: ignore[arg-type]
        category="linear",
        symbol=symbol,
        instrument_id=instrument_id,
        start_ms=start_ms,
        end_ms=end_ms,
    )


def spec(**overrides: object) -> HistoryJobSpec:
    values: dict[str, object] = {
        "job_id": "trade-2026-01-b01-fixture",
        "series": (
            series(instrument_id=1, symbol="AAAUSDT"),
            series(instrument_id=9, symbol="BBBUSDT"),
        ),
        "request_sha256": "c" * 64,
        "instrument_evidence_sha256": "a" * 64,
        "capacity_evidence_sha256": "b" * 64,
        "page_limit": 2,
        "workers": 1,
        "target_rps": 96,
        "max_attempts": 1,
        "max_http_requests": 10,
    }
    values.update(overrides)
    return HistoryJobSpec(**values)  # type: ignore[arg-type]


def budget(page_count: int = 4) -> CapacityBudget:
    return CapacityBudget(
        active_and_building_bytes=0,
        rest_staging_bytes=STAGING_METADATA_BYTES + page_count * MAX_PAGE_ARTIFACT_BYTES,
        operating_reserve_bytes=MIN_OPERATING_RESERVE_BYTES,
    )


def snapshot(root: Path, *, observed_at_ms: int = 1_000, free_bytes: int = 20 * 1024**3):
    return HostSnapshot(
        observed_at_ms=observed_at_ms,
        memory_total_bytes=16 * 1024**3,
        memory_available_bytes=8 * 1024**3,
        storage_kind="nvme",
        storage_device_id="fixture-nvme",
        volume_root=root.resolve(),
        volume_free_bytes=free_bytes,
    )


def preflight(tmp_path: Path, job_spec: HistoryJobSpec | None = None):  # type: ignore[no-untyped-def]
    return preflight_history_job(
        tmp_path / "history",
        job_spec or spec(),
        budget(),
        snapshot(tmp_path),
        now_ms=1_001,
        closed_before_ms=JANUARY_1_2026_MS + 180_000,
    )


def execute(plan, client):  # type: ignore[no-untyped-def]
    return execute_history_job(
        plan,
        lambda: client,
        lambda: snapshot(plan.paths.staging_root.parent, observed_at_ms=1_001),
        now_ms=lambda: 1_002,
    )


def test_fixed_page_plan_is_no_mutation_and_completed_job_loads_exact_batch(tmp_path: Path) -> None:
    plan = preflight(tmp_path)
    assert len(plan.tasks) == 4
    assert len(plan.pending_tasks) == 4
    assert not plan.paths.staging_root.exists()
    assert [(item.instrument_id, item.start_ms, item.end_ms) for item in plan.tasks] == [
        (1, JANUARY_1_2026_MS, JANUARY_1_2026_MS + 60_000),
        (1, JANUARY_1_2026_MS + 120_000, JANUARY_1_2026_MS + 120_000),
        (9, JANUARY_1_2026_MS, JANUARY_1_2026_MS + 60_000),
        (9, JANUARY_1_2026_MS + 120_000, JANUARY_1_2026_MS + 120_000),
    ]

    client = FakeKlineClient()
    completed = execute(plan, client)
    assert completed.page_count == 4
    assert completed.row_count == 6
    assert len(client.calls) == 4
    assert all(call[3:] in (("trade", 2),) for call in client.calls)
    manifest = json.loads(completed.manifest_path.read_text(encoding="utf-8"))
    schema_root = ROOT / "schemas" / "market" / "v1"
    schema_artifacts = (
        ("bybit-1m-history-plan.schema.json", completed.plan_path),
        ("bybit-1m-history-page.schema.json", completed.job_root / "pages" / "00000000.json"),
        ("bybit-1m-history-acquisition.schema.json", completed.manifest_path),
        ("history-acquisition-receipt.schema.json", completed.receipt_path),
    )
    for schema_name, artifact in schema_artifacts:
        schema = json.loads((schema_root / schema_name).read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(json.loads(artifact.read_text(encoding="utf-8")))
    assert manifest["source_policy"]["tick_rows_requested"] is False
    assert manifest["instrument_evidence_sha256"] == "a" * 64
    assert manifest["capacity_evidence_sha256"] == "b" * 64
    assert manifest["request_sha256"] == "c" * 64
    assert all(
        item["ingestion_id"] == f"bybit-page-sha256:{item['artifact_sha256']}"
        for item in manifest["pages"]
    )
    assert manifest["request_bound"] == {
        "actual_http_requests": 4,
        "max_attempts_per_page": 1,
        "max_http_requests_per_run": 10,
        "target_rps": 96,
        "workers": 1,
    }
    batch = load_completed_history_batch(completed.job_root)
    assert batch.table.num_rows == 6
    assert batch.table.column("instrument_id").to_pylist() == [1, 1, 1, 9, 9, 9]
    assert all(
        value.startswith("bybit-page-sha256:")
        for value in batch.table.column("ingestion_id").to_pylist()
    )
    assert (
        batch.table.column("open_time_ms").to_pylist()
        == [
            JANUARY_1_2026_MS,
            JANUARY_1_2026_MS + 60_000,
            JANUARY_1_2026_MS + 120_000,
        ]
        * 2
    )


def test_failed_run_keeps_verified_pages_and_resume_fetches_only_missing(tmp_path: Path) -> None:
    plan = preflight(tmp_path)
    failing = FakeKlineClient(fail_once={("AAAUSDT", JANUARY_1_2026_MS)})
    with pytest.raises(HistoryAcquisitionError, match="failed after"):
        execute(plan, failing)
    existing_pages = sorted(
        path
        for path in plan.paths.pages_root.glob("*.json")
        if not path.name.endswith(".receipt.json")
    )
    assert len(existing_pages) == 3

    resumed = preflight(tmp_path)
    assert 0 < len(resumed.pending_tasks) < len(resumed.tasks)
    replacement = FakeKlineClient()
    completed = execute(resumed, replacement)
    assert len(replacement.calls) == len(resumed.pending_tasks)
    assert completed.row_count == 6

    complete_plan = preflight(tmp_path)
    assert complete_plan.existing_complete is True
    never_called = AlwaysFailClient()
    same = execute(complete_plan, never_called)
    assert same.manifest_sha256 == completed.manifest_sha256
    assert never_called.calls == []


def test_transient_retry_is_bounded_and_recorded(tmp_path: Path) -> None:
    one_page_spec = spec(
        series=(series(end_ms=JANUARY_1_2026_MS),),
        max_attempts=2,
        max_http_requests=2,
    )
    plan = preflight_history_job(
        tmp_path / "history",
        one_page_spec,
        budget(page_count=1),
        snapshot(tmp_path),
        now_ms=1_001,
        closed_before_ms=JANUARY_1_2026_MS + 60_000,
    )
    client = FakeKlineClient(fail_once={("AAAUSDT", JANUARY_1_2026_MS)})
    completed = execute(plan, client)
    manifest = json.loads(completed.manifest_path.read_text(encoding="utf-8"))
    assert len(client.calls) == 2
    assert manifest["pages"][0]["attempt_count"] == 2


def test_empty_pages_are_explicit_coverage_evidence(tmp_path: Path) -> None:
    plan = preflight(tmp_path)
    client = FakeKlineClient(empty={("AAAUSDT", JANUARY_1_2026_MS)})
    completed = execute(plan, client)
    manifest = json.loads(completed.manifest_path.read_text(encoding="utf-8"))
    assert manifest["empty_page_count"] == 1
    assert completed.row_count == 4


def test_out_of_range_response_fails_without_completion_receipt(tmp_path: Path) -> None:
    plan = preflight(tmp_path)
    with pytest.raises(HistoryAcquisitionError, match="escapes"):
        execute(plan, FakeKlineClient(out_of_range=True))
    assert not plan.paths.receipt_path.exists()


def test_preflight_blocks_future_pages_request_bound_and_underbudget_before_mutation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "history"
    with pytest.raises(HistoryAcquisitionError, match="only closed"):
        preflight_history_job(
            root,
            spec(),
            budget(),
            snapshot(tmp_path),
            now_ms=1_001,
            closed_before_ms=JANUARY_1_2026_MS + 120_000,
        )
    with pytest.raises(HistoryAcquisitionError, match="retry bound"):
        preflight_history_job(
            root,
            spec(max_attempts=3, max_http_requests=10),
            budget(),
            snapshot(tmp_path),
            now_ms=1_001,
            closed_before_ms=JANUARY_1_2026_MS + 180_000,
        )
    small_budget = CapacityBudget(
        active_and_building_bytes=0,
        rest_staging_bytes=STAGING_METADATA_BYTES,
        operating_reserve_bytes=MIN_OPERATING_RESERVE_BYTES,
    )
    with pytest.raises(HistoryAcquisitionError, match="staging budget"):
        preflight_history_job(
            root,
            spec(),
            small_budget,
            snapshot(tmp_path),
            now_ms=1_001,
            closed_before_ms=JANUARY_1_2026_MS + 180_000,
        )
    assert not root.exists()


def test_tampered_page_or_stale_lock_blocks_resume(tmp_path: Path) -> None:
    plan = preflight(tmp_path)
    with pytest.raises(HistoryAcquisitionError):
        execute(plan, FakeKlineClient(fail_once={("AAAUSDT", JANUARY_1_2026_MS)}))
    staged = next(
        path
        for path in plan.paths.pages_root.glob("*.json")
        if not path.name.endswith(".receipt.json")
    )
    staged.write_bytes(staged.read_bytes() + b" ")
    with pytest.raises(HistoryAcquisitionError, match=r"canonical|receipt"):
        preflight(tmp_path)

    # Restore by starting an independent job identity, then prove lock detection.
    second = preflight(tmp_path, spec(job_id="trade-2026-01-b01-lock"))
    second.paths.pages_root.mkdir(parents=True)
    second.paths.run_lock.mkdir()
    with pytest.raises(HistoryAcquisitionError, match="run directory"):
        preflight(tmp_path, spec(job_id="trade-2026-01-b01-lock"))


def test_series_cannot_cross_physical_month_or_bucket() -> None:
    february_1_2026_ms = 1_769_904_000_000
    with pytest.raises(HistoryAcquisitionError, match="month/bucket"):
        spec(series=(series(end_ms=february_1_2026_ms),))
    with pytest.raises(HistoryAcquisitionError, match="month/bucket"):
        spec(
            series=(
                series(instrument_id=1, symbol="AAAUSDT"),
                series(instrument_id=2, symbol="BBBUSDT"),
            )
        )


def test_host_probe_builds_fresh_snapshot_from_platform_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory = SimpleNamespace(total=16 * 1024**3, available=8 * 1024**3)
    disk = SimpleNamespace(free=20 * 1024**3)
    monkeypatch.setattr("grid_data.host_probe.volume_root_for_path", lambda _path: tmp_path)
    monkeypatch.setattr("grid_data.host_probe.sys.platform", "win32")
    monkeypatch.setattr(
        "grid_data.host_probe._windows_storage_identity",
        lambda _root: ("nvme", "physical-drive-0:fixture"),
    )
    monkeypatch.setattr("grid_data.host_probe.psutil.virtual_memory", lambda: memory)
    monkeypatch.setattr("grid_data.host_probe.psutil.disk_usage", lambda _root: disk)
    monkeypatch.setattr("grid_data.host_probe.time.time_ns", lambda: 1_234_000_000)

    observed = probe_host_snapshot(tmp_path / "not-created")
    assert observed.observed_at_ms == 1_234
    assert observed.storage_kind == "nvme"
    assert observed.volume_root == tmp_path
    assert observed.volume_free_bytes == 20 * 1024**3
