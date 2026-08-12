"""Bounded-memory, lookahead-safe rolling-feature benchmark for Gate 1 evidence."""

from __future__ import annotations

import argparse
import platform
import shlex
import sys
import threading
import time
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any

import polars as pl
import psutil  # type: ignore[import-untyped]
from grid_data.evidence import preflight_evidence, publish_evidence

from benchmarks.reference_host import admit_reference_host

BASE_TIME_MS = 1_767_225_600_000  # 2026-01-01T00:00:00Z
DEFAULT_WINDOW_MINUTES = 1_440
REFERENCE_MINIMUM_ROWS = 100_000_000
REFERENCE_INSTRUMENTS = 700
FEATURE_COLUMNS = (
    "rolling_mid",
    "rolling_high",
    "rolling_low",
    "rolling_atr",
    "rolling_volume_mean",
    "range_width",
    "range_position",
    "lower_touch",
    "upper_touch",
    "mid_crossing",
)
FEATURE_SCHEMA_V1 = "grid.feature-benchmark/v1"
FEATURE_SCHEMA_V2 = "grid.feature-benchmark/v2"


@dataclass(frozen=True, slots=True)
class FeatureScale:
    rows: int
    instruments: int


class PeakRssSampler:
    """Sample process RSS on a short interval without retaining benchmark data."""

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


def default_scale(profile: str) -> FeatureScale:
    if profile == "smoke":
        return FeatureScale(rows=200_000, instruments=50)
    if profile == "scaled":
        return FeatureScale(rows=10_000_000, instruments=700)
    return FeatureScale(rows=REFERENCE_MINIMUM_ROWS, instruments=REFERENCE_INSTRUMENTS)


def validate_configuration(
    profile: str,
    rows: int,
    instruments: int,
    core_minutes: int,
    window_minutes: int,
    memory_limit_percent: int,
) -> int:
    if rows <= 0 or instruments <= 0 or core_minutes <= 0 or window_minutes <= 1:
        raise ValueError("rows, instruments, core-minutes, and window-minutes must be positive")
    if not 1 <= memory_limit_percent <= 100:
        raise ValueError("memory-limit-percent must be between 1 and 100")
    row_count = rows - rows % instruments
    if row_count < instruments:
        raise ValueError("rows must cover at least one row per instrument")
    if profile == "reference" and (
        rows < REFERENCE_MINIMUM_ROWS
        or instruments != REFERENCE_INSTRUMENTS
        or window_minutes != DEFAULT_WINDOW_MINUTES
        or memory_limit_percent > 70
    ):
        raise ValueError(
            "reference profile requires at least 100,000,000 rows, exactly 700 instruments, "
            "a 1,440-minute window, and a memory limit no greater than 70%; use --profile scaled "
            "for a smaller run"
        )
    return row_count


def build_market_frame(start_minute: int, end_minute: int, instrument_count: int) -> pl.DataFrame:
    """Build one deterministic, instrument-sorted input shard including its halo."""

    if start_minute < 0 or end_minute <= start_minute or instrument_count <= 0:
        raise ValueError("invalid synthetic market-frame range")
    minute_count = end_minute - start_minute
    row_count = minute_count * instrument_count
    frame = pl.DataFrame(
        {"row_number": pl.arange(0, row_count, eager=True, dtype=pl.Int64)}
    ).with_columns(
        instrument_id=(pl.col("row_number") // minute_count + 1).cast(pl.UInt32),
        minute_index=(pl.col("row_number") % minute_count + start_minute).cast(pl.Int64),
    )
    frame = frame.with_columns(
        open_scaled=(
            1_000_000
            + pl.col("instrument_id").cast(pl.Int64) * 1_000
            + (pl.col("minute_index") % 5_000)
            - 2_500
        ),
        close_offset=(
            (pl.col("minute_index") * 37 + pl.col("instrument_id").cast(pl.Int64) * 101) % 201 - 100
        ),
    ).with_columns(close_scaled=pl.col("open_scaled") + pl.col("close_offset"))
    frame = frame.with_columns(
        high_scaled=pl.max_horizontal("open_scaled", "close_scaled") + 50,
        low_scaled=pl.min_horizontal("open_scaled", "close_scaled") - 50,
        open_time_ms=pl.lit(BASE_TIME_MS, dtype=pl.Int64) + pl.col("minute_index") * 60_000,
        volume_scaled=(
            100_000
            + (pl.col("minute_index") * 17 + pl.col("instrument_id").cast(pl.Int64) * 13) % 10_000
        ),
    ).with_columns(
        open=(pl.col("open_scaled") / 10_000).cast(pl.Float64),
        high=(pl.col("high_scaled") / 10_000).cast(pl.Float64),
        low=(pl.col("low_scaled") / 10_000).cast(pl.Float64),
        close=(pl.col("close_scaled") / 10_000).cast(pl.Float64),
        volume=(pl.col("volume_scaled") / 1_000).cast(pl.Float64),
    )
    return frame.select(
        "instrument_id",
        "minute_index",
        "open_time_ms",
        "open",
        "high",
        "low",
        "close",
        "volume",
    )


def feature_plan(frame: pl.DataFrame, window_minutes: int) -> pl.LazyFrame:
    """Build features from the current and prior closed rows only."""

    plan = frame.lazy().with_columns(previous_close=pl.col("close").shift(1).over("instrument_id"))
    plan = plan.with_columns(
        true_range=pl.max_horizontal(
            pl.col("high") - pl.col("low"),
            (pl.col("high") - pl.col("previous_close")).abs(),
            (pl.col("low") - pl.col("previous_close")).abs(),
        )
    )
    plan = plan.with_columns(
        rolling_mid=pl.col("close")
        .rolling_mean(window_size=window_minutes, min_samples=window_minutes)
        .over("instrument_id"),
        rolling_high=pl.col("high")
        .rolling_max(window_size=window_minutes, min_samples=window_minutes)
        .over("instrument_id"),
        rolling_low=pl.col("low")
        .rolling_min(window_size=window_minutes, min_samples=window_minutes)
        .over("instrument_id"),
        rolling_atr=pl.col("true_range")
        .rolling_mean(window_size=window_minutes, min_samples=window_minutes)
        .over("instrument_id"),
        rolling_volume_mean=pl.col("volume")
        .rolling_mean(window_size=window_minutes, min_samples=window_minutes)
        .over("instrument_id"),
    )
    plan = plan.with_columns(
        prior_mid=pl.col("rolling_mid").shift(1).over("instrument_id"),
        prior_high=pl.col("rolling_high").shift(1).over("instrument_id"),
        prior_low=pl.col("rolling_low").shift(1).over("instrument_id"),
    )
    width = pl.col("rolling_high") - pl.col("rolling_low")
    plan = plan.with_columns(
        range_width=width,
        range_position=pl.when(width > 0)
        .then((pl.col("close") - pl.col("rolling_low")) / width)
        .otherwise(None),
        lower_touch=(pl.col("low") <= pl.col("prior_low")).fill_null(False),
        upper_touch=(pl.col("high") >= pl.col("prior_high")).fill_null(False),
        mid_crossing=(
            (
                (pl.col("previous_close") <= pl.col("prior_mid"))
                & (pl.col("close") > pl.col("prior_mid"))
            )
            | (
                (pl.col("previous_close") >= pl.col("prior_mid"))
                & (pl.col("close") < pl.col("prior_mid"))
            )
        ).fill_null(False),
    )
    return plan.select(
        "instrument_id",
        "minute_index",
        "open_time_ms",
        *FEATURE_COLUMNS,
    )


def decimal_metric(value: float) -> str:
    return f"{value:.9f}"


def _hardware() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    return {
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "machine": platform.machine(),
        "platform": platform.platform(),
        "ram_bytes": memory.total,
    }


def _software() -> dict[str, str]:
    return {
        "polars": pl.__version__,
        "psutil": version("psutil"),
        "python": platform.python_version(),
    }


def benchmark_shards(
    row_count: int,
    instrument_count: int,
    core_minutes: int,
    window_minutes: int,
) -> dict[str, Any]:
    total_minutes = row_count // instrument_count
    total_output_rows = 0
    total_input_rows = 0
    maximum_input_rows = 0
    warmup_null_rows = 0
    aggregate_sums = {name: 0.0 for name in FEATURE_COLUMNS[:7]}
    shard_results: list[dict[str, Any]] = []

    started = time.perf_counter()
    with PeakRssSampler() as memory_sampler:
        for core_start in range(0, total_minutes, core_minutes):
            core_end = min(total_minutes, core_start + core_minutes)
            # Prior-window boundary features shift a complete rolling value by one row,
            # so the maximum dependency is exactly ``window_minutes`` prior rows.
            halo_start = max(0, core_start - window_minutes)
            shard_started = time.perf_counter()
            input_frame = build_market_frame(halo_start, core_end, instrument_count)
            computed = feature_plan(input_frame, window_minutes).collect(engine="streaming")
            core = computed.filter(pl.col("minute_index") >= core_start)
            summary_expressions: list[pl.Expr] = [
                pl.len().alias("row_count"),
                pl.col("rolling_mid").null_count().alias("warmup_null_rows"),
            ]
            summary_expressions.extend(
                pl.col(name).sum().alias(f"sum_{name}") for name in aggregate_sums
            )
            summary = core.select(summary_expressions).row(0, named=True)
            output_rows = int(summary["row_count"])
            input_rows = input_frame.height
            total_output_rows += output_rows
            total_input_rows += input_rows
            maximum_input_rows = max(maximum_input_rows, input_rows)
            warmup_null_rows += int(summary["warmup_null_rows"])
            for name in aggregate_sums:
                value = summary[f"sum_{name}"]
                aggregate_sums[name] += 0.0 if value is None else float(value)
            shard_results.append(
                {
                    "core_end_minute_exclusive": core_end,
                    "core_start_minute": core_start,
                    "elapsed_seconds": decimal_metric(time.perf_counter() - shard_started),
                    "halo_start_minute": halo_start,
                    "input_rows": input_rows,
                    "output_rows": output_rows,
                }
            )
    elapsed = time.perf_counter() - started
    if total_output_rows != row_count:
        raise RuntimeError("sharded feature output did not preserve every core row exactly once")
    return {
        "aggregate_sums": {
            name: decimal_metric(value) for name, value in sorted(aggregate_sums.items())
        },
        "elapsed_seconds": decimal_metric(elapsed),
        "input_rows_including_halos": total_input_rows,
        "maximum_shard_input_rows": maximum_input_rows,
        "output_rows": total_output_rows,
        "peak_rss_bytes": memory_sampler.peak_bytes,
        "rss_baseline_bytes": memory_sampler.baseline_bytes,
        "rss_peak_delta_bytes": memory_sampler.peak_bytes - memory_sampler.baseline_bytes,
        "shards": shard_results,
        "throughput_core_rows_per_second": decimal_metric(total_output_rows / elapsed),
        "warmup_null_rows": warmup_null_rows,
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["smoke", "scaled", "reference"], default="smoke")
    parser.add_argument("--rows", type=int)
    parser.add_argument("--instruments", type=int)
    parser.add_argument("--core-minutes", type=int, default=2_880)
    parser.add_argument("--window-minutes", type=int, default=DEFAULT_WINDOW_MINUTES)
    parser.add_argument("--memory-limit-percent", type=int, default=70)
    parser.add_argument("--reference-host-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def run_feature_benchmark(
    *,
    profile: str,
    requested_rows: int,
    instruments: int,
    core_minutes: int,
    window_minutes: int,
    memory_limit_percent: int,
    output: Path,
    reference_host_evidence: Path | None,
    force: bool = False,
    command: str | None = None,
) -> dict[str, Any]:
    """Run and atomically publish one feature benchmark after all reference preflights."""

    row_count = validate_configuration(
        profile,
        requested_rows,
        instruments,
        core_minutes,
        window_minutes,
        memory_limit_percent,
    )
    reference_host: dict[str, Any] | None = None
    if profile == "reference":
        if reference_host_evidence is None:
            raise ValueError("reference profile requires --reference-host-evidence")
        reference_host = admit_reference_host(reference_host_evidence)
    elif reference_host_evidence is not None:
        raise ValueError("--reference-host-evidence is allowed only with --profile reference")

    software = _software()
    output, _receipt = preflight_evidence(output, force=force)
    result = benchmark_shards(
        row_count,
        instruments,
        core_minutes,
        window_minutes,
    )
    memory = psutil.virtual_memory()
    peak_ratio = int(result["peak_rss_bytes"]) / memory.total
    memory_limit_ratio = memory_limit_percent / 100
    memory_passed = peak_ratio <= memory_limit_ratio
    if reference_host is not None:
        if reference_host_evidence is None:
            raise RuntimeError("reference host evidence path was lost during the feature run")
        final_reference_host = admit_reference_host(reference_host_evidence)
        if final_reference_host != reference_host:
            raise RuntimeError("reference workstation evidence changed during the feature run")
        if _software() != software:
            raise RuntimeError("feature benchmark software changed during the reference run")

    is_reference = profile == "reference"
    limitations = [
        "Synthetic input is not evidence of production market-data compression or skew.",
        "The benchmark materializes and aggregates features but does not publish a "
        "feature dataset.",
        "A scaled or smoke run does not close the full-scale feature-memory gate.",
    ]
    if is_reference:
        limitations.append(
            "A qualifying host and passing memory limit produce a review candidate, not owner/PM "
            "approval of P-005 or Gate 1."
        )
    payload = {
        "benchmark_schema": FEATURE_SCHEMA_V2 if is_reference else FEATURE_SCHEMA_V1,
        "command": shlex.join(sys.argv) if command is None else command,
        "correctness": {
            "core_rows_written_once": True,
            "future_rows_read": 0,
            "halo_minutes": window_minutes,
            "semantics": "rolling window uses only the current and prior closed rows",
        },
        "hardware": _hardware(),
        "input": {
            "core_minutes_per_shard": core_minutes,
            "feature_columns": list(FEATURE_COLUMNS),
            "instrument_count": instruments,
            "row_count": row_count,
            "synthetic_generator": "deterministic-range-v1",
            "window_minutes": window_minutes,
        },
        "limitations": limitations,
        "memory_gate": {
            "configured_limit_percent": memory_limit_percent,
            "passed": memory_passed,
            "peak_rss_percent_of_ram": decimal_metric(peak_ratio * 100),
        },
        "profile": profile,
        "result": result,
        "software": software,
        "status": (
            "reference-host-feature-candidate"
            if is_reference and memory_passed
            else "reference-feature-rejected-memory"
            if is_reference
            else {
                "scaled": "scaled-only",
                "smoke": "smoke-only",
            }[profile]
        ),
    }
    if reference_host is not None:
        payload["reference_host_evidence"] = reference_host
    publish_evidence(output, payload, force=force)
    return payload


def main() -> int:
    args = arguments()
    scale = default_scale(args.profile)
    instruments = scale.instruments if args.instruments is None else args.instruments
    requested_rows = scale.rows if args.rows is None else args.rows
    payload = run_feature_benchmark(
        profile=args.profile,
        requested_rows=requested_rows,
        instruments=instruments,
        core_minutes=args.core_minutes,
        window_minutes=args.window_minutes,
        memory_limit_percent=args.memory_limit_percent,
        output=args.output,
        reference_host_evidence=args.reference_host_evidence,
        force=args.force,
    )
    return 0 if payload["memory_gate"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
