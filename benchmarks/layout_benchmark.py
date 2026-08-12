"""Reproducible, bounded-memory Parquet layout benchmark for Gate 1 evidence.

The smoke profile validates the harness, the scaled profile exercises the original
matrix without making a scale claim, and the full profile fails closed unless its
minimum scale is met. The decision profile evaluates density-derived exact physical
contracts without changing any v1/v2 artifact semantics. Synthetic rows are written
into their real calendar month partitions; no profile claims that the operating-system
cache was flushed.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import shlex
import shutil
import sys
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal

import duckdb
import polars as pl
import psutil  # type: ignore[import-untyped]
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from grid_contracts.canonical import sha256_file
from grid_data.evidence import preflight_evidence, publish_evidence, verify_evidence

BASE_TIME_MS = 1_767_225_600_000  # 2026-01-01T00:00:00Z
FULL_MINIMUM_ROWS = 100_000_000
FULL_INSTRUMENTS = 700
FULL_MINIMUM_EFFECTIVE_ROWS = FULL_MINIMUM_ROWS - FULL_MINIMUM_ROWS % FULL_INSTRUMENTS
TARGET_EXERCISE_RATIO = 0.8
DEFAULT_GENERATION_CHUNK_ROWS = 1_000_000
SCRATCH_RESERVE_BYTES = 1024**3
RUN_CONFIGURATION_SCHEMA = "grid.layout-benchmark-run/v1"
DECISION_RUN_CONFIGURATION_SCHEMA = "grid.layout-benchmark-run/v2"
CHECKPOINT_SCHEMA = "grid.layout-benchmark-checkpoint/v1"
EXACT_PHYSICAL_CONTRACT = "grid.candle-exact-physical/v1"
EXACT_REPRESENTATIONS = frozenset({"decimal128", "hybrid_int64_decimal"})
PRICE_COLUMNS = ("open", "high", "low", "close")
PRICE_SCALE = 8
VOLUME_SCALE = 4
TURNOVER_SCALE = 12


@dataclass(frozen=True, slots=True)
class Layout:
    bucket_count: int
    compression: Literal["zstd", "snappy"]
    compression_level: int | None
    numeric_representation: Literal["decimal128", "float64", "hybrid_int64_decimal", "scaled_int64"]
    target_file_mb: int

    @property
    def name(self) -> str:
        level = "default" if self.compression_level is None else str(self.compression_level)
        return (
            f"repr={self.numeric_representation}__buckets={self.bucket_count}__"
            f"codec={self.compression}-{level}__target={self.target_file_mb}mb"
        )


@dataclass(frozen=True, slots=True)
class TimePartition:
    year: int
    month: int
    start_minute: int
    minute_count: int


class PeakRssSampler:
    def __init__(self, interval_seconds: float = 0.01) -> None:
        self._interval_seconds = interval_seconds
        self._process = psutil.Process()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.baseline_bytes = self._process.memory_info().rss
        self.peak_bytes = self.baseline_bytes

    def __enter__(self) -> PeakRssSampler:
        self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._stop.set()
        self._thread.join()
        self._sample()

    def _sample(self) -> None:
        self.peak_bytes = max(self.peak_bytes, self._process.memory_info().rss)

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            self._sample()


def _decimal_from_units(column: str, scale: int) -> pl.Expr:
    decimal_type = pl.Decimal(precision=38, scale=scale)
    return (pl.col(column).cast(decimal_type) / pl.lit(10**scale).cast(decimal_type)).cast(
        decimal_type
    )


def _finish_synthetic_frame(frame: pl.DataFrame, representation: str) -> pl.DataFrame:
    frame = (
        frame.with_columns(
            row_number=(
                pl.col("minute_index") * pl.col("instrument_count")
                + pl.col("instrument_id").cast(pl.Int64)
                - 1
            )
        )
        .with_columns(
            open_time_ms=(pl.lit(BASE_TIME_MS, dtype=pl.Int64) + pl.col("minute_index") * 60_000),
            open_scaled=(1_000_000 + (pl.col("row_number") % 50_000)).cast(pl.Int64),
            volume_scaled=(100_000 + (pl.col("row_number") % 10_000)).cast(pl.Int64),
        )
        .with_columns(
            high_scaled=pl.col("open_scaled") + 100,
            low_scaled=pl.col("open_scaled") - 100,
            close_scaled=pl.col("open_scaled") + (pl.col("row_number") % 101) - 50,
            turnover_scaled=(pl.col("volume_scaled") * pl.col("open_scaled") // 1_000_000),
            open_e8=(pl.col("open_scaled") * 100).cast(pl.Int64),
            volume_e4=(1_000 + (pl.col("row_number") % 1_000)).cast(pl.Int64),
            quality_flags=pl.lit(0, dtype=pl.UInt8),
        )
        .with_columns(
            high_e8=pl.col("open_e8") + 10_000,
            low_e8=pl.col("open_e8") - 10_000,
            close_e8=pl.col("open_e8") + ((pl.col("row_number") % 101) - 50) * 100,
            turnover_e12=(pl.col("volume_e4") * pl.col("open_e8")).cast(pl.Int64),
        )
    )
    columns = ["instrument_id", "open_time_ms", "quality_flags"]
    if representation == "scaled_int64":
        price_columns = ["open_scaled", "high_scaled", "low_scaled", "close_scaled"]
        frame = frame.rename({name: name.removesuffix("_scaled") for name in price_columns})
        columns.extend(["open", "high", "low", "close", "volume_scaled", "turnover_scaled"])
    elif representation == "hybrid_int64_decimal":
        frame = frame.with_columns(
            open=pl.col("open_e8"),
            high=pl.col("high_e8"),
            low=pl.col("low_e8"),
            close=pl.col("close_e8"),
            volume=_decimal_from_units("volume_e4", VOLUME_SCALE),
            turnover=_decimal_from_units("turnover_e12", TURNOVER_SCALE),
        )
        columns.extend(["open", "high", "low", "close", "volume", "turnover"])
    elif representation == "decimal128":
        frame = frame.with_columns(
            open=_decimal_from_units("open_e8", PRICE_SCALE),
            high=_decimal_from_units("high_e8", PRICE_SCALE),
            low=_decimal_from_units("low_e8", PRICE_SCALE),
            close=_decimal_from_units("close_e8", PRICE_SCALE),
            volume=_decimal_from_units("volume_e4", VOLUME_SCALE),
            turnover=_decimal_from_units("turnover_e12", TURNOVER_SCALE),
        )
        columns.extend(["open", "high", "low", "close", "volume", "turnover"])
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
    return frame.select(columns)


def build_frame(row_count: int, instrument_count: int, representation: str) -> pl.DataFrame:
    """Build a small instrument/time-sorted frame with deterministic-v1 values."""

    if row_count < instrument_count or row_count % instrument_count:
        raise ValueError("row_count must be a positive multiple of instrument_count")
    minute_count = row_count // instrument_count
    frame = pl.DataFrame(
        {"position": pl.arange(0, row_count, eager=True, dtype=pl.Int64)}
    ).with_columns(
        instrument_id=(pl.col("position") // minute_count + 1).cast(pl.UInt32),
        instrument_count=pl.lit(instrument_count, dtype=pl.Int64),
        minute_index=(pl.col("position") % minute_count).cast(pl.Int64),
    )
    return _finish_synthetic_frame(frame, representation)


def time_partitions(total_minutes: int) -> tuple[TimePartition, ...]:
    if total_minutes <= 0:
        raise ValueError("total_minutes must be positive")
    partitions: list[TimePartition] = []
    minute_offset = 0
    current = datetime.fromtimestamp(BASE_TIME_MS / 1000, UTC)
    while minute_offset < total_minutes:
        if current.month == 12:
            following_month = current.replace(
                year=current.year + 1, month=1, day=1, hour=0, minute=0
            )
        else:
            following_month = current.replace(month=current.month + 1, day=1, hour=0, minute=0)
        available_minutes = int((following_month - current).total_seconds() // 60)
        minute_count = min(available_minutes, total_minutes - minute_offset)
        partitions.append(
            TimePartition(
                year=current.year,
                month=current.month,
                start_minute=minute_offset,
                minute_count=minute_count,
            )
        )
        minute_offset += minute_count
        current = following_month
    return tuple(partitions)


def bucket_instrument_count(
    instrument_count: int, bucket_count: int, bucket: int
) -> tuple[int, int]:
    first_instrument = bucket_count if bucket == 0 else bucket
    if first_instrument > instrument_count:
        return first_instrument, 0
    count = (instrument_count - first_instrument) // bucket_count + 1
    return first_instrument, count


def build_bucket_chunk(
    *,
    partition: TimePartition,
    instrument_count: int,
    bucket_count: int,
    bucket: int,
    position_start: int,
    row_count: int,
    representation: str,
) -> pl.DataFrame:
    first_instrument, instruments_in_bucket = bucket_instrument_count(
        instrument_count, bucket_count, bucket
    )
    partition_rows = instruments_in_bucket * partition.minute_count
    if row_count <= 0 or position_start < 0 or position_start + row_count > partition_rows:
        raise ValueError("bucket chunk falls outside its calendar partition")
    frame = pl.DataFrame(
        {
            "position": pl.arange(
                position_start,
                position_start + row_count,
                eager=True,
                dtype=pl.Int64,
            )
        }
    ).with_columns(
        instrument_id=(
            pl.lit(first_instrument, dtype=pl.Int64)
            + (pl.col("position") // partition.minute_count) * bucket_count
        ).cast(pl.UInt32),
        instrument_count=pl.lit(instrument_count, dtype=pl.Int64),
        minute_index=(
            pl.lit(partition.start_minute, dtype=pl.Int64)
            + pl.col("position") % partition.minute_count
        ),
    )
    return _finish_synthetic_frame(frame, representation)


def numeric_contracts() -> dict[str, Any]:
    return {
        "decimal128": {
            "contract_id": EXACT_PHYSICAL_CONTRACT,
            "exact": True,
            "fields": {
                "ohlc": {"physical_type": "decimal128(38,8)", "scale": PRICE_SCALE},
                "turnover": {
                    "physical_type": "decimal128(38,12)",
                    "scale": TURNOVER_SCALE,
                },
                "volume": {"physical_type": "decimal128(38,4)", "scale": VOLUME_SCALE},
            },
            "self_describing": True,
        },
        "hybrid_int64_decimal": {
            "contract_id": EXACT_PHYSICAL_CONTRACT,
            "exact": True,
            "fields": {
                "ohlc": {
                    "field_metadata_required": True,
                    "physical_type": "int64",
                    "scale": PRICE_SCALE,
                    "unit": "1e-8",
                },
                "turnover": {
                    "physical_type": "decimal128(38,12)",
                    "scale": TURNOVER_SCALE,
                },
                "volume": {"physical_type": "decimal128(38,4)", "scale": VOLUME_SCALE},
            },
            "self_describing": True,
        },
    }


def _table_with_numeric_metadata(table: pa.Table, layout: Layout) -> pa.Table:
    representation = layout.numeric_representation
    if representation not in EXACT_REPRESENTATIONS:
        return table
    schema_metadata = dict(table.schema.metadata or {})
    schema_metadata.update(
        {
            b"grid.numeric_contract": EXACT_PHYSICAL_CONTRACT.encode("ascii"),
            b"grid.numeric_representation": representation.encode("ascii"),
        }
    )
    fields: list[pa.Field] = []
    for field in table.schema:
        field_metadata = dict(field.metadata or {})
        if representation == "hybrid_int64_decimal" and field.name in PRICE_COLUMNS:
            field_metadata.update(
                {
                    b"grid.logical_type": b"decimal",
                    b"grid.scale": str(PRICE_SCALE).encode("ascii"),
                    b"grid.unit": b"1e-8",
                }
            )
        fields.append(
            pa.field(
                field.name,
                field.type,
                nullable=field.nullable,
                metadata=field_metadata or None,
            )
        )
    schema = pa.schema(fields, metadata=schema_metadata)
    return pa.Table.from_arrays(table.columns, schema=schema)


def _write_parquet_frames(
    destination: Path | pa.BufferOutputStream,
    frames: Iterable[pl.DataFrame],
    layout: Layout,
    row_group_rows: int,
) -> None:
    writer: pq.ParquetWriter | None = None
    try:
        for frame in frames:
            table = _table_with_numeric_metadata(frame.to_arrow(), layout)
            if writer is None:
                writer = pq.ParquetWriter(
                    destination,
                    table.schema,
                    compression=layout.compression,
                    compression_level=layout.compression_level,
                    write_statistics=True,
                )
            writer.write_table(table, row_group_size=row_group_rows)
    finally:
        if writer is not None:
            writer.close()
    if writer is None:
        raise ValueError("cannot write an empty Parquet file")


def _verify_exact_numeric_schema(paths: Iterable[Path], layout: Layout) -> None:
    representation = layout.numeric_representation
    if representation not in EXACT_REPRESENTATIONS:
        return
    expected_price_type = (
        pa.int64() if representation == "hybrid_int64_decimal" else pa.decimal128(38, PRICE_SCALE)
    )
    for path in paths:
        schema = pq.ParquetFile(path).schema_arrow
        metadata = schema.metadata or {}
        if metadata.get(b"grid.numeric_contract") != EXACT_PHYSICAL_CONTRACT.encode("ascii"):
            raise RuntimeError(f"numeric contract metadata is missing: {path}")
        if metadata.get(b"grid.numeric_representation") != representation.encode("ascii"):
            raise RuntimeError(f"numeric representation metadata does not match: {path}")
        for name in PRICE_COLUMNS:
            field = schema.field(name)
            if field.type != expected_price_type:
                raise RuntimeError(f"unexpected {name} physical type in {path}: {field.type}")
            if representation == "hybrid_int64_decimal":
                field_metadata = field.metadata or {}
                if field_metadata.get(b"grid.logical_type") != b"decimal":
                    raise RuntimeError(f"{name} logical type metadata is missing: {path}")
                if field_metadata.get(b"grid.scale") != b"8":
                    raise RuntimeError(f"{name} scale metadata is missing: {path}")
                if field_metadata.get(b"grid.unit") != b"1e-8":
                    raise RuntimeError(f"{name} unit metadata is missing: {path}")
        if schema.field("volume").type != pa.decimal128(38, VOLUME_SCALE):
            raise RuntimeError(f"unexpected volume physical type in {path}")
        if schema.field("turnover").type != pa.decimal128(38, TURNOVER_SCALE):
            raise RuntimeError(f"unexpected turnover physical type in {path}")


def _calibrate_compressed_bytes(frame: pl.DataFrame, layout: Layout, row_group_rows: int) -> int:
    sink = pa.BufferOutputStream()
    _write_parquet_frames(sink, (frame,), layout, row_group_rows)
    return int(sink.getvalue().size)


def _chunk_frames(
    *,
    partition: TimePartition,
    instrument_count: int,
    layout: Layout,
    bucket: int,
    position_start: int,
    row_count: int,
    generation_chunk_rows: int,
) -> Iterable[pl.DataFrame]:
    for offset in range(0, row_count, generation_chunk_rows):
        chunk_rows = min(generation_chunk_rows, row_count - offset)
        yield build_bucket_chunk(
            partition=partition,
            instrument_count=instrument_count,
            bucket_count=layout.bucket_count,
            bucket=bucket,
            position_start=position_start + offset,
            row_count=chunk_rows,
            representation=layout.numeric_representation,
        )


def write_layout(
    *,
    row_count: int,
    instrument_count: int,
    root: Path,
    layout: Layout,
    row_group_rows: int,
    generation_chunk_rows: int,
    calibration_mode: Literal["legacy-all-instruments", "month-bucket"] = (
        "legacy-all-instruments"
    ),
) -> dict[str, Any]:
    if row_count < instrument_count or row_count % instrument_count:
        raise ValueError("row_count must be a positive multiple of instrument_count")
    if min(row_group_rows, generation_chunk_rows, layout.bucket_count, layout.target_file_mb) <= 0:
        raise ValueError("layout sizing values must be positive")
    if layout.bucket_count > instrument_count:
        raise ValueError("layout bucket count must not exceed instrument count")
    if generation_chunk_rows < row_group_rows:
        raise ValueError("generation-chunk-rows must be at least row-group-rows")
    if generation_chunk_rows % row_group_rows:
        raise ValueError("generation-chunk-rows must be a multiple of row-group-rows")

    layout_root = root / layout.name
    dataset_root = layout_root / "dataset=trade_kline_1m" / "schema=v1"
    if layout_root.exists():
        raise FileExistsError(f"benchmark layout already exists: {layout_root}")
    if calibration_mode not in {"legacy-all-instruments", "month-bucket"}:
        raise ValueError(f"unsupported calibration mode: {calibration_mode}")
    partitions = time_partitions(row_count // instrument_count)
    with PeakRssSampler() as memory_sampler:
        if calibration_mode == "month-bucket":
            calibration_partition = partitions[0]
            _first, calibration_instruments = bucket_instrument_count(
                instrument_count, layout.bucket_count, 0
            )
            calibration_available_rows = (
                calibration_instruments * calibration_partition.minute_count
            )
            calibration_rows = min(calibration_available_rows, max(row_group_rows, 1_000_000))
            calibration_frame = build_bucket_chunk(
                partition=calibration_partition,
                instrument_count=instrument_count,
                bucket_count=layout.bucket_count,
                bucket=0,
                position_start=0,
                row_count=calibration_rows,
                representation=layout.numeric_representation,
            )
        else:
            calibration_rows = min(row_count, max(row_group_rows, 1_000_000))
            calibration_rows -= calibration_rows % instrument_count
            calibration_rows = max(instrument_count, calibration_rows)
            calibration_frame = build_frame(
                calibration_rows, instrument_count, layout.numeric_representation
            )
        calibration_started = time.perf_counter()
        calibration_bytes = _calibrate_compressed_bytes(calibration_frame, layout, row_group_rows)
        calibration_seconds = time.perf_counter() - calibration_started
        compressed_bytes_per_row = calibration_bytes / calibration_rows
        target_file_bytes = layout.target_file_mb * 1024 * 1024
        raw_rows_per_file = max(1, int(target_file_bytes / compressed_bytes_per_row))
        rows_per_file = max(
            row_group_rows,
            math.ceil(raw_rows_per_file / row_group_rows) * row_group_rows,
        )

        disk_free_before = shutil.disk_usage(root).free
        estimated_layout_bytes = math.ceil(row_count * compressed_bytes_per_row * 1.25)
        required_free_bytes = estimated_layout_bytes + SCRATCH_RESERVE_BYTES
        if disk_free_before < required_free_bytes:
            raise OSError(
                "insufficient scratch space for one bounded layout: "
                f"need {required_free_bytes} bytes, have {disk_free_before}"
            )

        dataset_root.mkdir(parents=True)
        started = time.perf_counter()
        file_rows: dict[Path, int] = {}
        file_count = 0
        for partition in partitions:
            partition_root = (
                dataset_root / f"year={partition.year:04d}" / f"month={partition.month:02d}"
            )
            for bucket in range(layout.bucket_count):
                _first, instruments_in_bucket = bucket_instrument_count(
                    instrument_count, layout.bucket_count, bucket
                )
                bucket_rows = instruments_in_bucket * partition.minute_count
                if not bucket_rows:
                    continue
                bucket_root = partition_root / f"bucket={bucket:02d}"
                bucket_root.mkdir(parents=True)
                for file_offset in range(0, bucket_rows, rows_per_file):
                    rows_in_file = min(rows_per_file, bucket_rows - file_offset)
                    file_path = bucket_root / f"part-{file_count:05d}.parquet"
                    _write_parquet_frames(
                        file_path,
                        _chunk_frames(
                            partition=partition,
                            instrument_count=instrument_count,
                            layout=layout,
                            bucket=bucket,
                            position_start=file_offset,
                            row_count=rows_in_file,
                            generation_chunk_rows=generation_chunk_rows,
                        ),
                        layout,
                        row_group_rows,
                    )
                    file_rows[file_path] = rows_in_file
                    file_count += 1
        elapsed = time.perf_counter() - started
    file_sizes = {path: path.stat().st_size for path in file_rows}
    _verify_exact_numeric_schema(file_sizes, layout)
    largest_file_bytes = max(file_sizes.values())
    smallest_file_bytes = min(file_sizes.values())
    non_tail_sizes = [file_sizes[path] for path, rows in file_rows.items() if rows == rows_per_file]
    largest_non_tail_file_bytes = max(non_tail_sizes) if non_tail_sizes else None
    target_exercised = bool(
        largest_non_tail_file_bytes is not None
        and largest_non_tail_file_bytes >= target_file_bytes * TARGET_EXERCISE_RATIO
    )
    result = {
        "bytes": sum(file_sizes.values()),
        "calendar_partition_count": len(partitions),
        "calibration_bytes": calibration_bytes,
        "calibration_bytes_per_row": decimal_metric(compressed_bytes_per_row),
        "calibration_rows": calibration_rows,
        "calibration_seconds": decimal_metric(calibration_seconds),
        "file_count": file_count,
        "generation_chunk_rows": generation_chunk_rows,
        "largest_file_bytes": largest_file_bytes,
        "largest_file_target_ratio": decimal_metric(largest_file_bytes / target_file_bytes),
        "largest_non_tail_file_bytes": largest_non_tail_file_bytes,
        "non_tail_file_count": len(non_tail_sizes),
        "peak_rss_bytes": memory_sampler.peak_bytes,
        "rss_baseline_bytes": memory_sampler.baseline_bytes,
        "rss_peak_delta_bytes": memory_sampler.peak_bytes - memory_sampler.baseline_bytes,
        "rows_per_file_target": rows_per_file,
        "scratch_estimated_layout_bytes": estimated_layout_bytes,
        "scratch_free_bytes_before": disk_free_before,
        "scratch_required_free_bytes": required_free_bytes,
        "smallest_file_bytes": smallest_file_bytes,
        "target_exercise_criterion": (
            "at least one non-tail file is at least 80% of requested target"
        ),
        "target_file_bytes": target_file_bytes,
        "target_file_exercised": target_exercised,
        "write_seconds": decimal_metric(elapsed),
        "writer": "pyarrow-parquet-writer",
    }
    if layout.numeric_representation in EXACT_REPRESENTATIONS:
        result.update(
            {
                "numeric_contract_id": EXACT_PHYSICAL_CONTRACT,
                "numeric_schema_verified": True,
            }
        )
    return result


def _timed_value(operation: Callable[[], Any]) -> tuple[str, Any]:
    started = time.perf_counter()
    value = operation()
    return decimal_metric(time.perf_counter() - started), value


def scan_layout(root: Path, row_count: int, instrument_count: int) -> dict[str, Any]:
    glob = (root / "**" / "*.parquet").as_posix()
    one_symbol = 1
    month_start = BASE_TIME_MS
    first_month_minutes = 31 * 24 * 60
    month_end = month_start + first_month_minutes * 60_000
    expected_symbol_rows = row_count // instrument_count
    expected_universe_month_rows = min(expected_symbol_rows, first_month_minutes) * instrument_count
    connection = duckdb.connect(":memory:")
    try:
        single_symbol_query = (
            "SELECT count(*), min(open_time_ms), max(close) "
            "FROM read_parquet(?, hive_partitioning=true) WHERE instrument_id = ?"
        )
        universe_month_query = (
            "SELECT count(*), min(low), max(high) "
            "FROM read_parquet(?, hive_partitioning=true) "
            "WHERE open_time_ms >= ? AND open_time_ms < ?"
        )
        duckdb_symbol_first, duckdb_symbol_value = _timed_value(
            lambda: connection.execute(single_symbol_query, [glob, one_symbol]).fetchone()
        )
        duckdb_symbol_warm, duckdb_symbol_warm_value = _timed_value(
            lambda: connection.execute(single_symbol_query, [glob, one_symbol]).fetchone()
        )
        duckdb_slice, duckdb_slice_value = _timed_value(
            lambda: connection.execute(
                universe_month_query, [glob, month_start, month_end]
            ).fetchone()
        )
    finally:
        connection.close()

    lazy = pl.scan_parquet(glob, hive_partitioning=True)
    polars_symbol_first, polars_symbol_value = _timed_value(
        lambda: (
            lazy.filter(pl.col("instrument_id") == one_symbol)
            .select(pl.len(), pl.col("open_time_ms").min(), pl.col("close").max())
            .collect()
            .row(0)
        )
    )
    polars_symbol_warm, polars_symbol_warm_value = _timed_value(
        lambda: (
            lazy.filter(pl.col("instrument_id") == one_symbol)
            .select(pl.len(), pl.col("open_time_ms").min(), pl.col("close").max())
            .collect()
            .row(0)
        )
    )
    polars_slice, polars_slice_value = _timed_value(
        lambda: (
            lazy.filter(
                (pl.col("open_time_ms") >= month_start) & (pl.col("open_time_ms") < month_end)
            )
            .select(pl.len(), pl.col("low").min(), pl.col("high").max())
            .collect()
            .row(0)
        )
    )
    observed_counts = {
        "duckdb_single_symbol_first": int(duckdb_symbol_value[0]),
        "duckdb_single_symbol_warm": int(duckdb_symbol_warm_value[0]),
        "duckdb_universe_month": int(duckdb_slice_value[0]),
        "polars_single_symbol_first": int(polars_symbol_value[0]),
        "polars_single_symbol_warm": int(polars_symbol_warm_value[0]),
        "polars_universe_month": int(polars_slice_value[0]),
    }
    expected_counts = {
        "duckdb_single_symbol_first": expected_symbol_rows,
        "duckdb_single_symbol_warm": expected_symbol_rows,
        "duckdb_universe_month": expected_universe_month_rows,
        "polars_single_symbol_first": expected_symbol_rows,
        "polars_single_symbol_warm": expected_symbol_rows,
        "polars_universe_month": expected_universe_month_rows,
    }
    if observed_counts != expected_counts:
        raise RuntimeError(
            f"layout scan validation failed: expected={expected_counts}, observed={observed_counts}"
        )
    aggregate_pairs = (
        ("single-symbol first/warm DuckDB", duckdb_symbol_value, duckdb_symbol_warm_value),
        ("single-symbol DuckDB/Polars", duckdb_symbol_value, polars_symbol_value),
        ("universe-month DuckDB/Polars", duckdb_slice_value, polars_slice_value),
    )
    for label, left, right in aggregate_pairs:
        if tuple(left) != tuple(right):
            raise RuntimeError(
                f"layout scan aggregate validation failed for {label}: {left!r} != {right!r}"
            )
    if int(duckdb_symbol_value[1]) != BASE_TIME_MS:
        raise RuntimeError("single-symbol scan did not start at the synthetic corpus boundary")
    return {
        "duckdb_single_symbol_first_seconds": duckdb_symbol_first,
        "duckdb_single_symbol_warm_seconds": duckdb_symbol_warm,
        "duckdb_universe_month_seconds": duckdb_slice,
        "polars_single_symbol_first_seconds": polars_symbol_first,
        "polars_single_symbol_warm_seconds": polars_symbol_warm,
        "polars_universe_month_seconds": polars_slice,
        "validation": {
            "engines_match_aggregate_values": True,
            "engines_match_expected_row_counts": True,
            "expected_single_symbol_rows": expected_symbol_rows,
            "expected_universe_month_rows": expected_universe_month_rows,
            "universe_window_end_ms_exclusive": month_end,
            "universe_window_start_ms": month_start,
        },
    }


def decimal_metric(value: float) -> str:
    return f"{value:.9f}"


def layouts(profile: str) -> tuple[Layout, ...]:
    bucket_counts: tuple[int, ...]
    targets: tuple[int, ...]
    codecs: tuple[tuple[Literal["zstd", "snappy"], int | None], ...]
    representations: tuple[
        Literal["decimal128", "float64", "hybrid_int64_decimal", "scaled_int64"], ...
    ]
    if profile == "smoke":
        bucket_counts = (8, 16)
        targets = (1,)
        codecs = (("zstd", 3), ("snappy", None))
        representations = ("float64", "scaled_int64")
    elif profile == "decision":
        bucket_counts = (4, 8)
        targets = (16, 32)
        codecs = (("zstd", 3), ("snappy", None))
        representations = ("hybrid_int64_decimal", "decimal128")
    else:
        bucket_counts = (8, 16, 32)
        targets = (128, 256, 512)
        codecs = (("zstd", 3), ("zstd", 9), ("snappy", None))
        representations = ("float64", "scaled_int64")
    return tuple(
        Layout(bucket_count, codec, level, representation, target)
        for representation in representations
        for bucket_count in bucket_counts
        for target in targets
        for codec, level in codecs
    )


def validate_configuration(
    profile: str,
    rows: int,
    instruments: int,
    row_group_rows: int,
    generation_chunk_rows: int = DEFAULT_GENERATION_CHUNK_ROWS,
) -> int:
    if min(rows, instruments, row_group_rows, generation_chunk_rows) <= 0:
        raise ValueError(
            "rows, instruments, row-group-rows, and generation-chunk-rows must be positive"
        )
    if generation_chunk_rows < row_group_rows:
        raise ValueError("generation-chunk-rows must be at least row-group-rows")
    if generation_chunk_rows % row_group_rows:
        raise ValueError("generation-chunk-rows must be a multiple of row-group-rows")
    row_count = rows - rows % instruments
    if row_count < instruments:
        raise ValueError("rows must cover at least one row per instrument")
    if profile in {"decision", "full"} and (
        rows < FULL_MINIMUM_ROWS or instruments != FULL_INSTRUMENTS
    ):
        raise ValueError(
            f"{profile} profile requires at least 100,000,000 rows and exactly 700 instruments; "
            "use --profile scaled for a smaller full-matrix run"
        )
    return row_count


def classify_run(profile: str, results: list[dict[str, Any]]) -> str:
    if profile == "smoke":
        return "smoke-only"
    if profile == "scaled":
        return "scaled-only"
    if profile == "decision":
        eligible = [
            result
            for result in results
            if result["write"].get("numeric_schema_verified") is True
            and result["write"]["target_file_exercised"] is True
        ]
        return "decision-matrix-candidate" if eligible else "decision-matrix-no-eligible-layout"
    if all(bool(result["write"]["target_file_exercised"]) for result in results):
        return "representative-run"
    return "full-matrix-insufficient-file-scale"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"checkpoint is not a JSON object: {path}")
    return payload


def _remove_work_dir(work_dir: Path) -> None:
    default_work_dir = (Path.cwd() / ".benchmark-work" / "layout").resolve()
    run_file = work_dir / "run.json"
    has_owned_marker = False
    if verify_evidence(run_file):
        has_owned_marker = _load_json(run_file).get("benchmark_schema") in {
            RUN_CONFIGURATION_SCHEMA,
            DECISION_RUN_CONFIGURATION_SCHEMA,
        }
    if work_dir != default_work_dir and not has_owned_marker:
        raise ValueError(
            "refusing to replace a custom work directory without a verified benchmark marker"
        )
    if work_dir == Path(work_dir.anchor) or work_dir == Path.cwd().resolve():
        raise ValueError("refusing to replace a broad work directory")
    shutil.rmtree(work_dir)


def _remove_layout(layout_root: Path, work_dir: Path, layout: Layout) -> None:
    expected = (work_dir / layout.name).resolve()
    if layout_root.resolve() != expected or layout_root.parent.resolve() != work_dir.resolve():
        raise ValueError("refusing to delete a layout outside the benchmark work directory")
    shutil.rmtree(layout_root)


def _checkpoint_result(checkpoint: Path, layout: Layout) -> dict[str, Any]:
    checkpoint_payload = _load_json(checkpoint)
    if checkpoint_payload.get("checkpoint_schema") != CHECKPOINT_SCHEMA:
        raise ValueError(f"checkpoint schema is not supported: {checkpoint}")
    result = checkpoint_payload.get("result")
    if not isinstance(result, dict):
        raise ValueError(f"checkpoint result is not an object: {checkpoint}")
    if result.get("layout") != asdict(layout):
        raise ValueError(f"checkpoint layout does not match its filename: {checkpoint}")
    if result.get("checkpoint_reused") is not False:
        raise ValueError(f"checkpoint was not committed from a fresh layout result: {checkpoint}")
    if not isinstance(result.get("scan"), dict) or not isinstance(result.get("write"), dict):
        raise ValueError(f"checkpoint is missing scan/write evidence: {checkpoint}")
    return dict(result)


def _run_configuration(
    args: argparse.Namespace,
    row_count: int,
    decision_inputs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    configuration = {
        "benchmark_schema": (
            DECISION_RUN_CONFIGURATION_SCHEMA
            if args.profile == "decision"
            else RUN_CONFIGURATION_SCHEMA
        ),
        "input": {
            "generation_chunk_rows": args.generation_chunk_rows,
            "instrument_count": args.instruments,
            "row_count": row_count,
            "row_group_rows": args.row_group_rows,
            "synthetic_generator": "deterministic-v1",
        },
        "layouts": [asdict(layout) for layout in layouts(args.profile)],
        "profile": args.profile,
        "retain_layouts": args.retain_layouts,
    }
    if decision_inputs is not None:
        configuration["decision_inputs"] = dict(decision_inputs)
    return configuration


def _prepare_work_dir(
    work_dir: Path, run_configuration: dict[str, Any], *, force: bool, resume: bool
) -> None:
    run_file = work_dir / "run.json"
    if resume and not work_dir.is_dir():
        raise FileNotFoundError(f"cannot resume a missing benchmark work directory: {work_dir}")
    if work_dir.exists():
        if force:
            _remove_work_dir(work_dir)
        elif not resume:
            raise FileExistsError(f"work directory exists; pass --force or --resume: {work_dir}")
    work_dir.mkdir(parents=True, exist_ok=True)
    if resume:
        if not verify_evidence(run_file):
            raise ValueError("resume run configuration receipt does not verify")
        if _load_json(run_file) != run_configuration:
            raise ValueError("resume configuration does not match the existing benchmark run")
    else:
        publish_evidence(run_file, run_configuration)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile", choices=["smoke", "scaled", "full", "decision"], default="smoke"
    )
    parser.add_argument("--rows", type=int, default=200_000)
    parser.add_argument("--instruments", type=int, default=50)
    parser.add_argument("--row-group-rows", type=int, default=100_000)
    parser.add_argument("--generation-chunk-rows", type=int, default=DEFAULT_GENERATION_CHUNK_ROWS)
    parser.add_argument("--work-dir", type=Path, default=Path(".benchmark-work/layout"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--predecessor-evidence",
        type=Path,
        default=Path("benchmarks/results/m1-layout-out-of-core-full-candidate.json"),
    )
    parser.add_argument(
        "--precision-evidence",
        type=Path,
        default=Path("benchmarks/results/m1-bybit-public-inventory.json"),
    )
    lifecycle = parser.add_mutually_exclusive_group()
    lifecycle.add_argument("--force", action="store_true")
    lifecycle.add_argument("--resume", action="store_true")
    parser.add_argument("--retain-layouts", action="store_true")
    return parser.parse_args()


def _decimal_places(value: Any, name: str) -> int:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be exact decimal text")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{name} must be exact decimal text") from error
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{name} must be finite and positive")
    exponent = parsed.normalize().as_tuple().exponent
    if not isinstance(exponent, int):
        raise ValueError(f"{name} exponent is not finite")
    return max(0, -exponent)


def decision_input_evidence(predecessor_path: Path, precision_path: Path) -> dict[str, Any]:
    predecessor_path = predecessor_path.resolve()
    precision_path = precision_path.resolve()
    for path in (predecessor_path, precision_path):
        if not verify_evidence(path):
            raise ValueError(f"decision input evidence receipt does not verify: {path}")

    predecessor = _load_json(predecessor_path)
    predecessor_input = predecessor.get("input")
    predecessor_results = predecessor.get("results")
    if (
        predecessor.get("benchmark_schema") != "grid.layout-benchmark/v2"
        or predecessor.get("profile") != "full"
        or predecessor.get("status") != "full-matrix-insufficient-file-scale"
        or not isinstance(predecessor_input, Mapping)
        or predecessor_input.get("instrument_count") != FULL_INSTRUMENTS
        or int(predecessor_input.get("row_count", 0)) < FULL_MINIMUM_EFFECTIVE_ROWS
        or not isinstance(predecessor_results, list)
        or len(predecessor_results) != 54
    ):
        raise ValueError("predecessor is not the complete failed-target v2 full matrix")

    precision = _load_json(precision_path)
    records = precision.get("records")
    if precision.get("evidence_schema") != "grid.bybit-public-inventory/v1" or not isinstance(
        records, list
    ):
        raise ValueError("precision input is not the public Bybit inventory evidence")
    relevant = [
        record
        for record in records
        if isinstance(record, Mapping)
        and record.get("contract_type") == "LinearPerpetual"
        and record.get("quote_coin") == "USDT"
    ]
    if not relevant:
        raise ValueError("precision evidence has no USDT LinearPerpetual records")
    price_places = max(_decimal_places(record.get("tick_size"), "tick_size") for record in relevant)
    quantity_places = max(
        _decimal_places(record.get("quantity_step"), "quantity_step") for record in relevant
    )
    if price_places > PRICE_SCALE or quantity_places > VOLUME_SCALE:
        raise ValueError("observed instrument precision exceeds the exact physical contract")
    return {
        "precision_basis": {
            "artifact": precision_path.name,
            "artifact_sha256": sha256_file(precision_path),
            "derived_turnover_scale": price_places + quantity_places,
            "max_observed_price_decimal_places": price_places,
            "max_observed_quantity_decimal_places": quantity_places,
            "relevant_record_count": len(relevant),
            "semantics": "current public snapshot; future wider precision requires a new contract",
        },
        "predecessor": {
            "artifact": predecessor_path.name,
            "artifact_sha256": sha256_file(predecessor_path),
            "layout_count": len(predecessor_results),
            "status": predecessor["status"],
        },
    }


def decision_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [
        result
        for result in results
        if result["write"].get("numeric_schema_verified") is True
        and result["write"]["target_file_exercised"] is True
    ]

    def ranking_key(result: dict[str, Any]) -> tuple[Any, ...]:
        scan = result["scan"]
        scan_total = sum(
            Decimal(scan[name])
            for name in (
                "duckdb_single_symbol_first_seconds",
                "duckdb_single_symbol_warm_seconds",
                "duckdb_universe_month_seconds",
                "polars_single_symbol_first_seconds",
                "polars_single_symbol_warm_seconds",
                "polars_universe_month_seconds",
            )
        )
        layout = result["layout"]
        return (
            int(result["write"]["bytes"]),
            Decimal(result["write"]["write_seconds"]),
            scan_total,
            int(result["write"]["file_count"]),
            layout["numeric_representation"],
            layout["compression"],
            int(layout["target_file_mb"]),
        )

    shortlist = []
    for bucket_count in (4, 8):
        candidates = [
            result for result in eligible if result["layout"]["bucket_count"] == bucket_count
        ]
        if candidates:
            shortlist.append(min(candidates, key=ranking_key)["layout"])
    return {
        "eligible_layout_count": len(eligible),
        "eligibility": (
            "verified exact numeric schema and at least one non-tail file at or above "
            "80% of the requested target"
        ),
        "owner_approval_required": True,
        "ranking_policy": (
            "within each bucket count: total bytes, write seconds, aggregate scan seconds, "
            "file count, then stable layout fields"
        ),
        "reference_rerun_shortlist": shortlist,
    }


def main() -> int:
    args = arguments()
    row_count = validate_configuration(
        args.profile,
        args.rows,
        args.instruments,
        args.row_group_rows,
        args.generation_chunk_rows,
    )
    work_dir = args.work_dir.resolve()
    output, _receipt = preflight_evidence(args.output, force=args.force)
    if output == work_dir or work_dir in output.parents:
        raise ValueError("evidence output must be outside the disposable benchmark work directory")
    decision_inputs = (
        decision_input_evidence(args.predecessor_evidence, args.precision_evidence)
        if args.profile == "decision"
        else None
    )
    run_configuration = _run_configuration(args, row_count, decision_inputs)
    _prepare_work_dir(
        work_dir,
        run_configuration,
        force=args.force,
        resume=args.resume,
    )

    checkpoint_root = work_dir / ".checkpoints"
    checkpoint_root.mkdir(exist_ok=True)
    results: list[dict[str, Any]] = []
    for layout in layouts(args.profile):
        layout_root = work_dir / layout.name
        checkpoint = checkpoint_root / f"{layout.name}.json"
        if args.resume and verify_evidence(checkpoint):
            result = _checkpoint_result(checkpoint, layout)
            result["checkpoint_reused"] = True
            if layout_root.exists() and not args.retain_layouts:
                _remove_layout(layout_root, work_dir, layout)
            elif args.retain_layouts and not layout_root.is_dir():
                raise ValueError(f"retained layout is missing during resume: {layout_root}")
            results.append(result)
            continue
        if checkpoint.exists() or checkpoint.with_suffix(".json.receipt.json").exists():
            raise ValueError(f"invalid or partial checkpoint blocks resume: {checkpoint}")
        if layout_root.exists():
            if not args.resume:
                raise FileExistsError(f"benchmark layout already exists: {layout_root}")
            _remove_layout(layout_root, work_dir, layout)

        write_result = write_layout(
            row_count=row_count,
            instrument_count=args.instruments,
            root=work_dir,
            layout=layout,
            row_group_rows=args.row_group_rows,
            generation_chunk_rows=args.generation_chunk_rows,
            calibration_mode=(
                "month-bucket" if args.profile == "decision" else "legacy-all-instruments"
            ),
        )
        scan_result = scan_layout(layout_root, row_count, args.instruments)
        result = {
            "checkpoint_reused": False,
            "layout": asdict(layout),
            "scan": scan_result,
            "write": write_result,
        }
        publish_evidence(
            checkpoint,
            {"checkpoint_schema": CHECKPOINT_SCHEMA, "result": result},
        )
        results.append(result)
        if not args.retain_layouts:
            _remove_layout(layout_root, work_dir, layout)

    memory = psutil.virtual_memory()
    payload = {
        "benchmark_schema": (
            "grid.layout-benchmark/v3" if args.profile == "decision" else "grid.layout-benchmark/v2"
        ),
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
        "input": run_configuration["input"],
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
    if args.profile == "decision":
        payload["decision"] = decision_summary(results)
        payload["decision_inputs"] = decision_inputs
        payload["numeric_contracts"] = numeric_contracts()
    publish_evidence(output, payload, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
