from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest
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
    build_frame,
    classify_run,
    validate_configuration,
    write_layout,
)
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
    frame = build_frame(20_000, 10, "scaled_int64")
    result = write_layout(
        frame,
        tmp_path,
        Layout(8, "zstd", 3, "scaled_int64", 1),
        row_group_rows=1_000,
    )

    assert result["bytes"] >= result["largest_file_bytes"] > 0
    assert result["smallest_file_bytes"] > 0
    assert result["target_file_bytes"] == 1024 * 1024
    assert isinstance(result["target_file_exercised"], bool)
    assert not tuple(tmp_path.rglob(".calibration.parquet"))


def test_capacity_projection_rounds_up_partial_bytes() -> None:
    assert projected_bytes(3, Decimal("1.1")) == 4


def test_workstation_snapshot_removes_device_instance_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "benchmarks.workstation_snapshot.windows_registry_value",
        lambda _path, _name: r"SCSI\Disk&Ven_NVMe&Prod_EXAMPLE_MODEL\instance-specific-suffix",
    )

    assert storage_identity() == ("nvme", "NVMe EXAMPLE MODEL")
