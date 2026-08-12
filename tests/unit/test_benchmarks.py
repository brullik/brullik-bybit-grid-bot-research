from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest
from grid_data.evidence import verify_evidence
from polars.testing import assert_frame_equal

from benchmarks.capacity_projection import projected_bytes
from benchmarks.feature_benchmark import (
    build_market_frame,
    feature_plan,
)
from benchmarks.feature_benchmark import (
    validate_configuration as validate_feature_configuration,
)
from benchmarks.layout_benchmark import (
    Layout,
    TimePartition,
    _prepare_work_dir,
    build_bucket_chunk,
    build_frame,
    classify_run,
    scan_layout,
    time_partitions,
    validate_configuration,
    write_layout,
)
from benchmarks.mainnet_validate_candidates import build_shortlist
from benchmarks.redact_mainnet_validate_discovery import build_mainnet_conclusion
from benchmarks.redact_validate_probe import build_redacted_conclusion
from benchmarks.workstation_snapshot import storage_identity


def test_feature_halo_matches_unsharded_history() -> None:
    window = 100
    full = feature_plan(build_market_frame(0, 300, 3), window).collect()
    with_halo = feature_plan(build_market_frame(50, 250, 3), window).collect()

    expected = full.filter((pl.col("minute_index") >= 150) & (pl.col("minute_index") < 250))
    actual = with_halo.filter(pl.col("minute_index") >= 150)

    assert_frame_equal(actual, expected)


def test_feature_plan_does_not_change_when_only_future_rows_change() -> None:
    original = build_market_frame(0, 300, 2)
    changed_future = original.with_columns(
        close=pl.when(pl.col("minute_index") >= 200)
        .then(pl.col("close") * 10)
        .otherwise(pl.col("close")),
        high=pl.when(pl.col("minute_index") >= 200)
        .then(pl.col("high") * 10)
        .otherwise(pl.col("high")),
        low=pl.when(pl.col("minute_index") >= 200)
        .then(pl.col("low") * 10)
        .otherwise(pl.col("low")),
    )

    original_features = feature_plan(original, 100).collect().filter(pl.col("minute_index") < 200)
    changed_features = (
        feature_plan(changed_future, 100).collect().filter(pl.col("minute_index") < 200)
    )

    assert_frame_equal(original_features, changed_features)


def test_full_layout_profile_cannot_claim_a_small_run() -> None:
    with pytest.raises(ValueError, match="full profile requires"):
        validate_configuration("full", 200_000, 50, 10_000)
    assert validate_configuration("scaled", 200_001, 50, 10_000) == 200_000
    assert validate_configuration("full", 100_000_000, 700, 100_000) == 99_999_900


def test_layout_generation_chunk_preserves_requested_row_groups() -> None:
    with pytest.raises(ValueError, match="at least row-group"):
        validate_configuration("smoke", 200_000, 50, 10_000, 5_000)
    with pytest.raises(ValueError, match="multiple of row-group"):
        validate_configuration("smoke", 200_000, 50, 10_000, 15_000)


def test_time_partitions_follow_real_utc_calendar_boundaries() -> None:
    partitions = time_partitions(31 * 24 * 60 + 2)

    assert partitions == (
        TimePartition(year=2026, month=1, start_minute=0, minute_count=44_640),
        TimePartition(year=2026, month=2, start_minute=44_640, minute_count=2),
    )


def test_bucket_chunk_matches_deterministic_full_frame() -> None:
    full = build_frame(40, 8, "scaled_int64")
    chunk = build_bucket_chunk(
        partition=TimePartition(year=2026, month=1, start_minute=0, minute_count=5),
        instrument_count=8,
        bucket_count=4,
        bucket=0,
        position_start=0,
        row_count=10,
        representation="scaled_int64",
    )

    expected = full.filter((pl.col("instrument_id") % 4) == 0)
    assert_frame_equal(chunk, expected)


def test_reference_feature_profile_accepts_its_documented_command_scale() -> None:
    assert (
        validate_feature_configuration("reference", 100_000_000, 700, 2_880, 1_440, 70)
        == 99_999_900
    )


def test_representative_status_requires_every_file_target() -> None:
    exercised = {"write": {"target_file_exercised": True}}
    insufficient = {"write": {"target_file_exercised": False}}

    assert classify_run("scaled", [exercised]) == "scaled-only"
    assert classify_run("full", [exercised, insufficient]) == (
        "full-matrix-insufficient-file-scale"
    )
    assert classify_run("full", [exercised]) == "representative-run"


def test_layout_reports_observed_file_sizes(tmp_path: Path) -> None:
    result = write_layout(
        row_count=20_000,
        instrument_count=10,
        root=tmp_path,
        layout=Layout(8, "zstd", 3, "scaled_int64", 1),
        row_group_rows=1_000,
        generation_chunk_rows=2_000,
    )

    assert result["bytes"] >= result["largest_file_bytes"] > 0
    assert result["smallest_file_bytes"] > 0
    assert result["target_file_bytes"] == 1024 * 1024
    assert isinstance(result["target_file_exercised"], bool)
    assert result["writer"] == "pyarrow-parquet-writer"
    assert result["rss_peak_delta_bytes"] >= 0
    assert not tuple(tmp_path.rglob(".calibration.parquet"))

    scan = scan_layout(tmp_path / Layout(8, "zstd", 3, "scaled_int64", 1).name, 20_000, 10)
    assert scan["validation"]["engines_match_aggregate_values"] is True
    assert scan["validation"]["expected_single_symbol_rows"] == 2_000
    assert scan["validation"]["expected_universe_month_rows"] == 20_000


def test_layout_work_directory_resume_requires_identical_receipted_run(
    tmp_path: Path,
) -> None:
    work_dir = tmp_path / "scratch"
    configuration = {"benchmark_schema": "grid.layout-benchmark-run/v1", "profile": "smoke"}
    with pytest.raises(FileNotFoundError, match="missing benchmark work directory"):
        _prepare_work_dir(work_dir, configuration, force=False, resume=True)
    _prepare_work_dir(work_dir, configuration, force=False, resume=False)

    assert verify_evidence(work_dir / "run.json")
    _prepare_work_dir(work_dir, configuration, force=False, resume=True)
    with pytest.raises(ValueError, match="does not match"):
        _prepare_work_dir(
            work_dir,
            {"benchmark_schema": "grid.layout-benchmark-run/v1", "profile": "scaled"},
            force=False,
            resume=True,
        )
    _prepare_work_dir(work_dir, configuration, force=True, resume=False)
    assert verify_evidence(work_dir / "run.json")


def test_capacity_projection_rounds_up_partial_bytes() -> None:
    assert projected_bytes(3, Decimal("1.1")) == 4


def test_validate_conclusion_redacts_prices_and_requires_safe_demo_result() -> None:
    private_report = {
        "created_at_utc": "2026-08-12T12:00:00Z",
        "endpoint": "/v5/fgridbot/validate",
        "environment": "demo",
        "request": {
            "symbol": "BTCUSDT",
            "min_price": "62000",
            "max_price": "65000",
        },
        "response": {"retCode": 10032, "retMsg": "Demo trading are not supported."},
        "safety": {"credentials_persisted": False, "mutating_endpoint_called": False},
    }

    conclusion = build_redacted_conclusion(private_report)

    assert conclusion["status"] == "demo-unsupported"
    assert "62000" not in repr(conclusion)
    assert conclusion["safety"]["mainnet_fallback"] is False
    unsafe_report = dict(private_report)
    unsafe_report["safety"] = {
        "credentials_persisted": False,
        "mutating_endpoint_called": True,
    }
    with pytest.raises(ValueError, match="validate-only"):
        build_redacted_conclusion(unsafe_report)


def _mainnet_report(symbol: str, minimum: str) -> dict[str, object]:
    ranges = {
        "DOGEUSDT": ("0.069", "0.074", "0.068", "0.075"),
        "LINKUSDT": ("8.4", "8.9", "8.3", "9"),
        "XRPUSDT": ("0.99", "1.04", "0.98", "1.05"),
    }
    lower, upper, stop, take = ranges[symbol]
    return {
        "created_at_utc": "2026-08-12T12:00:00Z",
        "endpoint": "/v5/fgridbot/validate",
        "environment": "mainnet",
        "request": {
            "cell_number": "2",
            "grid_mode": "1",
            "grid_type": "2",
            "leverage": "1",
            "max_price": upper,
            "min_price": lower,
            "stop_loss_price": stop,
            "symbol": symbol,
            "take_profit_price": take,
        },
        "response": {"retCode": 0, "result": {"investment": {"from": minimum}}},
        "result": {
            "check_code": "FGRID_CHECK_CODE_UNSPECIFIED",
            "ret_code": 0,
            "successful": True,
        },
        "safety": {
            "credentials_persisted": False,
            "mutating_endpoint_called": False,
            "validate_only": True,
        },
    }


def test_mainnet_conclusion_is_ranked_redacted_and_keeps_create_unexercised() -> None:
    reports = [
        _mainnet_report("XRPUSDT", "0.1389"),
        _mainnet_report("DOGEUSDT", "0.0989"),
        _mainnet_report("LINKUSDT", "1.1887"),
    ]

    conclusion = build_mainnet_conclusion(reports)

    assert [row["symbol"] for row in conclusion["candidates"]] == [
        "DOGEUSDT",
        "XRPUSDT",
        "LINKUSDT",
    ]
    assert conclusion["create_capability"]["exercised"] is False
    assert conclusion["safety"]["mutating_endpoint_called"] is False
    assert "retMsg" not in repr(conclusion)
    assert "retExtInfo" not in repr(conclusion)
    unsafe = list(reports)
    unsafe[0] = dict(unsafe[0])
    unsafe[0]["safety"] = {
        "credentials_persisted": False,
        "mutating_endpoint_called": True,
        "validate_only": True,
    }
    with pytest.raises(ValueError, match="validate-only"):
        build_mainnet_conclusion(unsafe)


def _instrument(symbol: str, *, minimum_notional: str = "5") -> dict[str, object]:
    return {
        "contractType": "LinearPerpetual",
        "lotSizeFilter": {"minNotionalValue": minimum_notional, "minOrderQty": "0.1"},
        "priceFilter": {"tickSize": "0.001"},
        "quoteCoin": "USDT",
        "status": "Trading",
        "symbol": symbol,
    }


def _ticker(symbol: str, *, mark: str, turnover: str) -> dict[str, str]:
    return {
        "ask1Price": mark,
        "bid1Price": mark,
        "highPrice24h": str(Decimal(mark) * Decimal("1.02")),
        "lowPrice24h": str(Decimal(mark) * Decimal("0.98")),
        "markPrice": mark,
        "symbol": symbol,
        "turnover24h": turnover,
    }


def test_public_mainnet_shortlist_filters_ranks_and_tick_rounds() -> None:
    instruments = [
        _instrument("AAAUSDT", minimum_notional="1"),
        _instrument("BBBUSDT", minimum_notional="2"),
        _instrument("CCCUSDT", minimum_notional="3"),
        _instrument("ILLIQUIDUSDT", minimum_notional="1"),
    ]
    tickers = [
        _ticker("AAAUSDT", mark="1", turnover="60000000"),
        _ticker("BBBUSDT", mark="1", turnover="90000000"),
        _ticker("CCCUSDT", mark="1", turnover="80000000"),
        _ticker("ILLIQUIDUSDT", mark="1", turnover="1000"),
    ]

    result = build_shortlist(
        instruments,
        tickers,
        observed_at_utc="2026-08-12T12:00:00Z",
    )

    assert [row["symbol"] for row in result["candidates"]] == [
        "AAAUSDT",
        "BBBUSDT",
        "CCCUSDT",
    ]
    assert result["candidates"][0]["validate_request"] == {
        "cell_number": 2,
        "leverage": "1",
        "max_price": "1.031",
        "min_price": "0.97",
        "stop_loss_price": "0.96",
        "take_profit_price": "1.042",
    }


def test_workstation_snapshot_removes_device_instance_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "benchmarks.workstation_snapshot.windows_registry_value",
        lambda _path, _name: r"SCSI\Disk&Ven_NVMe&Prod_EXAMPLE_MODEL\instance-specific-suffix",
    )

    assert storage_identity() == ("nvme", "NVMe EXAMPLE MODEL")
