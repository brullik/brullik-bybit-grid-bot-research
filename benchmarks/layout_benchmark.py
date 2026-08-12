"""Reproducible Parquet layout/engine benchmark for Gate 1 evidence.

The smoke profile validates the harness, the scaled profile exercises the full
matrix without making a scale claim, and the full profile fails closed unless its
minimum scale is met. No profile claims that the operating-system cache was flushed.
"""

from __future__ import annotations

import argparse
import math
import platform
import shlex
import shutil
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal

import duckdb
import polars as pl
import psutil  # type: ignore[import-untyped]
from grid_data.evidence import preflight_evidence, publish_evidence

BASE_TIME_MS = 1_767_225_600_000  # 2026-01-01T00:00:00Z
FULL_MINIMUM_ROWS = 100_000_000
FULL_INSTRUMENTS = 700
TARGET_EXERCISE_RATIO = 0.8


@dataclass(frozen=True, slots=True)
class Layout:
    bucket_count: int
    compression: Literal["zstd", "snappy"]
    compression_level: int | None
    numeric_representation: Literal["float64", "scaled_int64"]
    target_file_mb: int

    @property
    def name(self) -> str:
        level = "default" if self.compression_level is None else str(self.compression_level)
        return (
            f"repr={self.numeric_representation}__buckets={self.bucket_count}__"
            f"codec={self.compression}-{level}__target={self.target_file_mb}mb"
        )


def build_frame(row_count: int, instrument_count: int, representation: str) -> pl.DataFrame:
    if row_count < instrument_count or row_count % instrument_count:
        raise ValueError("row_count must be a positive multiple of instrument_count")
    frame = pl.DataFrame({"row_number": pl.arange(0, row_count, eager=True, dtype=pl.Int64)})
    frame = frame.with_columns(
        instrument_id=(pl.col("row_number") % instrument_count + 1).cast(pl.UInt32),
        open_time_ms=(
            pl.lit(BASE_TIME_MS, dtype=pl.Int64)
            + (pl.col("row_number") // instrument_count) * 60_000
        ),
        open_scaled=(1_000_000 + (pl.col("row_number") % 50_000)).cast(pl.Int64),
        volume_scaled=(100_000 + (pl.col("row_number") % 10_000)).cast(pl.Int64),
    ).with_columns(
        high_scaled=pl.col("open_scaled") + 100,
        low_scaled=pl.col("open_scaled") - 100,
        close_scaled=pl.col("open_scaled") + (pl.col("row_number") % 101) - 50,
        turnover_scaled=(pl.col("volume_scaled") * pl.col("open_scaled") // 1_000_000),
        quality_flags=pl.lit(0, dtype=pl.UInt8),
    )
    columns = ["instrument_id", "open_time_ms", "quality_flags"]
    if representation == "scaled_int64":
        price_columns = ["open_scaled", "high_scaled", "low_scaled", "close_scaled"]
        frame = frame.rename({name: name.removesuffix("_scaled") for name in price_columns})
        columns.extend(["open", "high", "low", "close", "volume_scaled", "turnover_scaled"])
    elif representation == "float64":
        frame = frame.with_columns(
            open=(pl.col("open_scaled") / 1_000_000).cast(pl.Float64),
            high=(pl.col("high_scaled") / 1_000_000).cast(pl.Float64),
            low=(pl.col("low_scaled") / 1_000_000).cast(pl.Float64),
            close=(pl.col("close_scaled") / 1_000_000).cast(pl.Float64),
            volume=(pl.col("volume_scaled") / 1_000_000).cast(pl.Float64),
            turnover=(pl.col("turnover_scaled") / 1_000_000).cast(pl.Float64),
        )
        columns.extend(["open", "high", "low", "close", "volume", "turnover"])
    else:
        raise ValueError(f"unknown representation: {representation}")
    return frame.select(columns).sort("instrument_id", "open_time_ms")


def write_layout(
    frame: pl.DataFrame, root: Path, layout: Layout, row_group_rows: int
) -> dict[str, Any]:
    layout_root = (
        root / layout.name / "dataset=trade_kline_1m" / "schema=v1" / "year=2026" / "month=01"
    )
    if layout_root.exists():
        raise FileExistsError(f"benchmark layout already exists: {layout_root}")
    layout_root.mkdir(parents=True)
    calibration_rows = min(frame.height, max(row_group_rows, 1_000_000))
    calibration_path = layout_root / ".calibration.parquet"
    frame.head(calibration_rows).write_parquet(
        calibration_path,
        compression=layout.compression,
        compression_level=layout.compression_level,
        row_group_size=row_group_rows,
        statistics="full",
    )
    calibration_bytes = calibration_path.stat().st_size
    calibration_path.unlink()
    compressed_bytes_per_row = calibration_bytes / calibration_rows
    target_file_bytes = layout.target_file_mb * 1024 * 1024
    raw_rows_per_file = max(1, int(target_file_bytes / compressed_bytes_per_row))
    rows_per_file = max(
        row_group_rows,
        math.ceil(raw_rows_per_file / row_group_rows) * row_group_rows,
    )
    started = time.perf_counter()
    file_count = 0
    for bucket in range(layout.bucket_count):
        bucket_frame = frame.filter(
            (pl.col("instrument_id").cast(pl.UInt64) % layout.bucket_count) == bucket
        )
        if bucket_frame.is_empty():
            continue
        bucket_root = layout_root / f"bucket={bucket:02d}"
        bucket_root.mkdir()
        for offset in range(0, bucket_frame.height, rows_per_file):
            part = bucket_frame.slice(offset, rows_per_file)
            part.write_parquet(
                bucket_root / f"part-{file_count:05d}.parquet",
                compression=layout.compression,
                compression_level=layout.compression_level,
                row_group_size=row_group_rows,
                statistics="full",
            )
            file_count += 1
    elapsed = time.perf_counter() - started
    files = tuple(layout_root.rglob("*.parquet"))
    file_sizes = tuple(path.stat().st_size for path in files)
    largest_file_bytes = max(file_sizes)
    smallest_file_bytes = min(file_sizes)
    target_exercised = largest_file_bytes >= target_file_bytes * TARGET_EXERCISE_RATIO
    return {
        "bytes": sum(file_sizes),
        "calibration_bytes_per_row": decimal_seconds(compressed_bytes_per_row),
        "file_count": file_count,
        "largest_file_bytes": largest_file_bytes,
        "largest_file_target_ratio": decimal_seconds(largest_file_bytes / target_file_bytes),
        "rows_per_file_target": rows_per_file,
        "smallest_file_bytes": smallest_file_bytes,
        "target_exercise_criterion": "largest file is at least 80% of requested target",
        "target_file_bytes": target_file_bytes,
        "target_file_exercised": target_exercised,
        "write_seconds": decimal_seconds(elapsed),
    }


def scan_layout(root: Path, frame: pl.DataFrame) -> dict[str, str]:
    glob = (root / "**" / "*.parquet").as_posix()
    one_symbol = 1
    month_start_value = frame["open_time_ms"].min()
    if not isinstance(month_start_value, int):
        raise ValueError("benchmark frame has no integer open_time_ms minimum")
    month_start = month_start_value
    one_day_end = month_start + 86_400_000
    connection = duckdb.connect(":memory:")
    try:
        single_symbol_query = (
            "SELECT count(*), min(open_time_ms), max(close) "
            "FROM read_parquet(?, hive_partitioning=true) WHERE instrument_id = ?"
        )
        universe_day_query = (
            "SELECT count(*), min(low), max(high) "
            "FROM read_parquet(?, hive_partitioning=true) "
            "WHERE open_time_ms >= ? AND open_time_ms < ?"
        )
        duckdb_symbol_first = timed(
            lambda: connection.execute(
                single_symbol_query,
                [glob, one_symbol],
            ).fetchone()
        )
        duckdb_symbol_warm = timed(
            lambda: connection.execute(
                single_symbol_query,
                [glob, one_symbol],
            ).fetchone()
        )
        duckdb_slice = timed(
            lambda: connection.execute(
                universe_day_query,
                [glob, month_start, one_day_end],
            ).fetchone()
        )
    finally:
        connection.close()

    lazy = pl.scan_parquet(glob, hive_partitioning=True)
    polars_symbol_first = timed(
        lambda: (
            lazy.filter(pl.col("instrument_id") == one_symbol)
            .select(pl.len(), pl.col("open_time_ms").min(), pl.col("close").max())
            .collect()
        )
    )
    polars_symbol_warm = timed(
        lambda: (
            lazy.filter(pl.col("instrument_id") == one_symbol)
            .select(pl.len(), pl.col("open_time_ms").min(), pl.col("close").max())
            .collect()
        )
    )
    polars_slice = timed(
        lambda: (
            lazy.filter(
                (pl.col("open_time_ms") >= month_start) & (pl.col("open_time_ms") < one_day_end)
            )
            .select(pl.len(), pl.col("low").min(), pl.col("high").max())
            .collect()
        )
    )
    return {
        "duckdb_single_symbol_first_seconds": duckdb_symbol_first,
        "duckdb_single_symbol_warm_seconds": duckdb_symbol_warm,
        "duckdb_universe_day_seconds": duckdb_slice,
        "polars_single_symbol_first_seconds": polars_symbol_first,
        "polars_single_symbol_warm_seconds": polars_symbol_warm,
        "polars_universe_day_seconds": polars_slice,
    }


def timed(operation: Callable[[], object]) -> str:
    started = time.perf_counter()
    operation()
    return decimal_seconds(time.perf_counter() - started)


def decimal_seconds(value: float) -> str:
    return f"{value:.9f}"


def layouts(profile: str) -> tuple[Layout, ...]:
    bucket_counts: tuple[int, ...]
    targets: tuple[int, ...]
    codecs: tuple[tuple[Literal["zstd", "snappy"], int | None], ...]
    if profile == "smoke":
        bucket_counts = (8, 16)
        targets = (1,)
        codecs = (
            ("zstd", 3),
            ("snappy", None),
        )
    else:
        bucket_counts = (8, 16, 32)
        targets = (128, 256, 512)
        codecs = (("zstd", 3), ("zstd", 9), ("snappy", None))
    return tuple(
        Layout(bucket_count, codec, level, representation, target)
        for representation in ("float64", "scaled_int64")
        for bucket_count in bucket_counts
        for target in targets
        for codec, level in codecs
    )


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["smoke", "scaled", "full"], default="smoke")
    parser.add_argument("--rows", type=int, default=200_000)
    parser.add_argument("--instruments", type=int, default=50)
    parser.add_argument("--row-group-rows", type=int, default=100_000)
    parser.add_argument("--work-dir", type=Path, default=Path(".benchmark-work/layout"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--retain-layouts", action="store_true")
    return parser.parse_args()


def validate_configuration(profile: str, rows: int, instruments: int, row_group_rows: int) -> int:
    if rows <= 0 or instruments <= 0 or row_group_rows <= 0:
        raise ValueError("rows, instruments, and row-group-rows must be positive")
    row_count = rows - rows % instruments
    if row_count < instruments:
        raise ValueError("rows must cover at least one row per instrument")
    if profile == "full" and (rows < FULL_MINIMUM_ROWS or instruments != FULL_INSTRUMENTS):
        raise ValueError(
            "full profile requires at least 100,000,000 rows and exactly 700 instruments; "
            "use --profile scaled for a smaller full-matrix run"
        )
    return row_count


def classify_run(profile: str, results: list[dict[str, Any]]) -> str:
    if profile == "smoke":
        return "smoke-only"
    if profile == "scaled":
        return "scaled-only"
    if all(bool(result["write"]["target_file_exercised"]) for result in results):
        return "representative-run"
    return "full-matrix-insufficient-file-scale"


def main() -> int:
    args = arguments()
    row_count = validate_configuration(
        args.profile, args.rows, args.instruments, args.row_group_rows
    )
    work_dir = args.work_dir.resolve()
    output, _receipt = preflight_evidence(args.output, force=args.force)
    if output == work_dir or work_dir in output.parents:
        raise ValueError("evidence output must be outside the disposable benchmark work directory")
    if work_dir.exists():
        if not args.force:
            raise FileExistsError(f"work directory exists; pass --force to rebuild: {work_dir}")
        if work_dir.name != "layout" or work_dir.parent.name != ".benchmark-work":
            raise ValueError("refusing to delete a work directory outside .benchmark-work/layout")
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)

    results: list[dict[str, Any]] = []
    for representation in ("float64", "scaled_int64"):
        frame = build_frame(row_count, args.instruments, representation)
        for layout in (
            item for item in layouts(args.profile) if item.numeric_representation == representation
        ):
            layout_root = work_dir / layout.name
            write_result = write_layout(frame, work_dir, layout, args.row_group_rows)
            scan_result = scan_layout(layout_root, frame)
            results.append(
                {
                    "layout": {
                        "bucket_count": layout.bucket_count,
                        "compression": layout.compression,
                        "compression_level": layout.compression_level,
                        "numeric_representation": layout.numeric_representation,
                        "target_file_mb": layout.target_file_mb,
                    },
                    "scan": scan_result,
                    "write": write_result,
                }
            )
            if not args.retain_layouts:
                shutil.rmtree(layout_root)

    memory = psutil.virtual_memory()
    payload = {
        "benchmark_schema": "grid.layout-benchmark/v1",
        "cache_semantics": (
            "First and repeated reads are reported; OS cache was not forcibly flushed."
        ),
        "command": shlex.join(sys.argv),
        "hardware": {
            "cpu_count_logical": psutil.cpu_count(logical=True),
            "cpu_count_physical": psutil.cpu_count(logical=False),
            "machine": platform.machine(),
            "platform": platform.platform(),
            "ram_bytes": memory.total,
        },
        "input": {
            "instrument_count": args.instruments,
            "row_count": row_count,
            "row_group_rows": args.row_group_rows,
            "synthetic_generator": "deterministic-v1",
        },
        "profile": args.profile,
        "results": results,
        "scratch_policy": (
            "retained by explicit request" if args.retain_layouts else "deleted after each layout"
        ),
        "software": {
            "duckdb": duckdb.__version__,
            "polars": pl.__version__,
            "pyarrow": version("pyarrow"),
            "python": platform.python_version(),
        },
        "status": classify_run(args.profile, results),
    }
    publish_evidence(output, payload, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
