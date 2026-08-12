"""Staged cold-read, repair, and compaction benchmark for the ADR-0010 shortlist."""

from __future__ import annotations

import argparse
import json
import math
import platform
import shlex
import shutil
import sys
import time
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import duckdb
import polars as pl
import psutil  # type: ignore[import-untyped]
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_data.evidence import preflight_evidence, publish_evidence, verify_evidence

from benchmarks.layout_benchmark import (
    BASE_TIME_MS,
    FULL_INSTRUMENTS,
    FULL_MINIMUM_EFFECTIVE_ROWS,
    Layout,
    _verify_exact_numeric_schema,
    write_layout,
)

PREPARATION_SCHEMA = "grid.reference-layout-preparation/v1"
RUN_SCHEMA = "grid.reference-layout-run/v1"
MEASUREMENT_SCHEMA = "grid.reference-layout-measurement/v1"
FINAL_SCHEMA = "grid.reference-layout-benchmark/v1"
DECISION_SCHEMA = "grid.layout-benchmark/v3"
SOURCE_SEMANTICS = "deterministic-exact-synthetic-v1"
Engine = Literal["duckdb", "polars"]
QueryShape = Literal["single-symbol", "universe-month"]
CacheProof = Literal["reboot", "unverified-smoke"]


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"artifact is not a JSON object: {path}")
    return payload


def _load_verified(path: Path, schema_key: str, schema: str) -> dict[str, Any]:
    path = path.resolve()
    if not verify_evidence(path):
        raise ValueError(f"evidence receipt does not verify: {path}")
    payload = _load_json(path)
    if payload.get(schema_key) != schema:
        raise ValueError(f"unsupported evidence schema in {path}")
    return payload


def _hardware() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    return {
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "machine": platform.machine(),
        "platform": platform.platform(),
        "ram_bytes": memory.total,
    }


def _boot_marker() -> str:
    return datetime.fromtimestamp(int(psutil.boot_time()), UTC).isoformat().replace("+00:00", "Z")


def _safe_replace_work_dir(work_dir: Path) -> None:
    work_dir = work_dir.resolve()
    cwd = Path.cwd().resolve()
    home = Path.home().resolve()
    preparation = work_dir / "preparation.json"
    run_marker = work_dir / "run.json"
    if work_dir in {Path(work_dir.anchor), cwd, home}:
        raise ValueError("refusing to replace a broad reference benchmark work directory")
    preparation_owned = (
        verify_evidence(preparation)
        and _load_json(preparation).get("preparation_schema") == PREPARATION_SCHEMA
    )
    run_owned = (
        verify_evidence(run_marker) and _load_json(run_marker).get("run_schema") == RUN_SCHEMA
    )
    if not preparation_owned and not run_owned:
        raise ValueError("refusing to replace work directory without a verified benchmark marker")
    shutil.rmtree(work_dir)


def _validate_scale(profile: str, rows: int, instruments: int) -> int:
    if rows <= 0 or instruments <= 0:
        raise ValueError("rows and instruments must be positive")
    row_count = rows - rows % instruments
    if row_count < instruments:
        raise ValueError("rows must cover at least one row per instrument")
    if profile == "reference" and (
        row_count < FULL_MINIMUM_EFFECTIVE_ROWS or instruments != FULL_INSTRUMENTS
    ):
        raise ValueError("reference profile requires at least 99,999,900 rows and 700 instruments")
    return row_count


def _shortlist(decision_path: Path) -> tuple[list[Layout], dict[str, Any]]:
    decision_path = decision_path.resolve()
    decision = _load_verified(decision_path, "benchmark_schema", DECISION_SCHEMA)
    raw = decision.get("decision")
    if decision.get("status") != "decision-matrix-candidate" or not isinstance(raw, Mapping):
        raise ValueError("decision evidence is not an eligible layout candidate")
    raw_shortlist = raw.get("reference_rerun_shortlist")
    if not isinstance(raw_shortlist, list) or len(raw_shortlist) != 2:
        raise ValueError("decision evidence must contain the two-layout reference shortlist")
    raw_results = decision.get("results")
    if not isinstance(raw_results, list):
        raise ValueError("decision evidence is missing its measured layout results")
    layouts: list[Layout] = []
    for item in raw_shortlist:
        if not isinstance(item, Mapping):
            raise ValueError("shortlist layout must be an object")
        try:
            layout = Layout(
                bucket_count=int(item["bucket_count"]),
                compression=str(item["compression"]),  # type: ignore[arg-type]
                compression_level=(
                    None if item["compression_level"] is None else int(item["compression_level"])
                ),
                numeric_representation=str(item["numeric_representation"]),  # type: ignore[arg-type]
                target_file_mb=int(item["target_file_mb"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("shortlist layout is malformed") from error
        if layout.numeric_representation not in {"decimal128", "hybrid_int64_decimal"}:
            raise ValueError("reference shortlist must use an exact numeric representation")
        if (
            layout.compression not in {"zstd", "snappy"}
            or layout.target_file_mb not in {16, 32}
            or (layout.compression == "zstd" and layout.compression_level != 3)
            or (layout.compression == "snappy" and layout.compression_level is not None)
        ):
            raise ValueError("reference shortlist contains an unsupported layout")
        matching_results = [
            result
            for result in raw_results
            if isinstance(result, Mapping)
            and result.get("layout") == dict(item)
            and isinstance(result.get("write"), Mapping)
            and result["write"].get("numeric_schema_verified") is True
            and result["write"].get("target_file_exercised") is True
        ]
        if len(matching_results) != 1:
            raise ValueError("shortlist layout is not backed by one eligible measured result")
        layouts.append(layout)
    if len(set(layouts)) != 2 or {layout.bucket_count for layout in layouts} != {4, 8}:
        raise ValueError("reference shortlist must contain one 4-bucket and one 8-bucket layout")
    return layouts, {
        "artifact": decision_path.name,
        "artifact_sha256": sha256_file(decision_path),
        "benchmark_schema": decision["benchmark_schema"],
        "status": decision["status"],
    }


def _parquet_manifest(root: Path) -> dict[str, Any]:
    paths = sorted(root.rglob("*.parquet"))
    if not paths:
        raise ValueError(f"dataset contains no Parquet files: {root}")
    files: list[dict[str, Any]] = []
    total_bytes = 0
    for path in paths:
        stat = path.stat()
        files.append(
            {
                "modified_ns": stat.st_mtime_ns,
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
                "size": stat.st_size,
            }
        )
        total_bytes += stat.st_size
    return {
        "file_count": len(files),
        "files": files,
        "total_bytes": total_bytes,
        "tree_sha256": canonical_sha256(files),
    }


def _metadata_matches(root: Path, expected: Mapping[str, Any]) -> bool:
    raw_files = expected.get("files")
    if not isinstance(raw_files, list):
        return False
    observed_paths = sorted(path.relative_to(root).as_posix() for path in root.rglob("*.parquet"))
    if any(
        not isinstance(item, Mapping) or not isinstance(item.get("path"), str) for item in raw_files
    ):
        return False
    expected_paths = sorted(str(item["path"]) for item in raw_files)
    if observed_paths != expected_paths:
        return False
    for item in raw_files:
        if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
            return False
        stat = (root / item["path"]).stat()
        if stat.st_size != item.get("size") or stat.st_mtime_ns != item.get("modified_ns"):
            return False
    return True


def _content_matches(root: Path, expected: Mapping[str, Any]) -> bool:
    observed = _parquet_manifest(root)
    return bool(
        observed["tree_sha256"] == expected.get("tree_sha256")
        and observed["total_bytes"] == expected.get("total_bytes")
    )


def _canonical_scalar(value: Any) -> str:
    if value is None:
        raise ValueError("logical summary cannot contain null aggregates")
    if isinstance(value, Decimal):
        if value == 0:
            return "0"
        return format(value.normalize(), "f")
    if isinstance(value, int):
        return str(value)
    raise TypeError(f"unexpected aggregate type: {type(value).__name__}")


def _logical_summary(root: Path) -> dict[str, Any]:
    glob = (root / "*.parquet").as_posix()
    columns = ("open", "high", "low", "close", "volume", "turnover")
    aggregate_sql = ", ".join(f"sum({column})" for column in columns)
    connection = duckdb.connect(":memory:")
    try:
        duckdb_row = connection.execute(
            "SELECT count(*), min(open_time_ms), max(open_time_ms), sum(instrument_id), "
            f"{aggregate_sql} FROM read_parquet(?)",
            [glob],
        ).fetchone()
    finally:
        connection.close()
    if duckdb_row is None:
        raise RuntimeError("DuckDB returned no maintenance summary")
    polars_row = (
        pl.scan_parquet(glob)
        .select(
            pl.len().alias("row_count"),
            pl.col("open_time_ms").min().alias("minimum_open_time_ms"),
            pl.col("open_time_ms").max().alias("maximum_open_time_ms"),
            pl.col("instrument_id").sum().alias("instrument_id_sum"),
            *(pl.col(column).sum().alias(f"{column}_sum") for column in columns),
        )
        .collect()
        .row(0)
    )
    duckdb_values = [_canonical_scalar(value) for value in duckdb_row]
    polars_values = [_canonical_scalar(value) for value in polars_row]
    if duckdb_values != polars_values:
        raise RuntimeError("DuckDB and Polars maintenance summaries do not match")
    names = (
        "row_count",
        "minimum_open_time_ms",
        "maximum_open_time_ms",
        "instrument_id_sum",
        *(f"{column}_sum" for column in columns),
    )
    values = dict(zip(names, duckdb_values, strict=True))
    return {
        "duckdb_polars_equal": True,
        "logical_sha256": canonical_sha256(values),
        "values": values,
    }


def _source_bucket(dataset_root: Path) -> Path:
    candidates = sorted(dataset_root.glob("dataset=*/schema=*/year=*/month=*/bucket=*"))
    if not candidates:
        raise ValueError("prepared dataset has no monthly bucket")
    return candidates[0]


def _row_count(paths: Iterable[Path]) -> int:
    return sum(pq.ParquetFile(path).metadata.num_rows for path in paths)


def _rewrite(
    sources: list[Path],
    destination: Path,
    layout: Layout,
    *,
    rows_per_file: int,
) -> dict[str, Any]:
    if rows_per_file <= 0:
        raise ValueError("rows per maintenance file must be positive")
    destination.mkdir(parents=True)
    started = time.perf_counter()
    file_index = 0
    writer: pq.ParquetWriter | None = None
    rows_in_file = 0
    try:
        for source in sources:
            for batch in pq.ParquetFile(source).iter_batches(batch_size=100_000):
                table = pa.Table.from_batches([batch])
                offset = 0
                while offset < table.num_rows:
                    if writer is None:
                        target = destination / f"part-{file_index:05d}.parquet"
                        writer = pq.ParquetWriter(
                            target,
                            table.schema,
                            compression=layout.compression,
                            compression_level=layout.compression_level,
                            write_statistics=True,
                        )
                        file_index += 1
                    available = rows_per_file - rows_in_file
                    chunk = table.slice(offset, min(available, table.num_rows - offset))
                    writer.write_table(chunk, row_group_size=min(100_000, rows_per_file))
                    rows_in_file += chunk.num_rows
                    offset += chunk.num_rows
                    if rows_in_file == rows_per_file:
                        writer.close()
                        writer = None
                        rows_in_file = 0
    finally:
        if writer is not None:
            writer.close()
    paths = sorted(destination.glob("*.parquet"))
    if not paths:
        raise RuntimeError("maintenance rewrite produced no Parquet files")
    _verify_exact_numeric_schema(paths, layout)
    return {
        "elapsed_seconds": f"{time.perf_counter() - started:.9f}",
        "manifest": _parquet_manifest(destination),
        "numeric_schema_verified": True,
        "row_count": _row_count(paths),
    }


def _maintenance_probe(dataset_root: Path, layout: Layout, scratch: Path) -> dict[str, Any]:
    source_manifest_before = _parquet_manifest(dataset_root)
    source_bucket = _source_bucket(dataset_root)
    source_paths = sorted(source_bucket.glob("*.parquet"))
    source_rows = _row_count(source_paths)
    if source_rows < 8:
        raise ValueError("maintenance probe requires at least eight source rows")
    source_summary = _logical_summary(source_bucket)

    repair_root = scratch / "repair"
    fragment_root = scratch / "fragments"
    compact_root = scratch / "compact"
    repair = _rewrite(source_paths, repair_root, layout, rows_per_file=source_rows)
    fragment_rows = math.ceil(source_rows / 8)
    fragmentation = _rewrite(source_paths, fragment_root, layout, rows_per_file=fragment_rows)
    compaction = _rewrite(
        sorted(fragment_root.glob("*.parquet")), compact_root, layout, rows_per_file=source_rows
    )
    repair_summary = _logical_summary(repair_root)
    compact_summary = _logical_summary(compact_root)
    parity = (
        source_summary["logical_sha256"]
        == repair_summary["logical_sha256"]
        == compact_summary["logical_sha256"]
    )
    if not parity or repair["row_count"] != source_rows or compaction["row_count"] != source_rows:
        raise RuntimeError("repair or compaction changed the logical monthly bucket")
    source_manifest_after = _parquet_manifest(dataset_root)
    source_unchanged = source_manifest_after["tree_sha256"] == source_manifest_before["tree_sha256"]
    if not source_unchanged:
        raise RuntimeError("maintenance probe mutated the prepared source dataset")
    source_bytes = sum(path.stat().st_size for path in source_paths)
    compact_to_fragment_ratio = (
        compaction["manifest"]["total_bytes"] / fragmentation["manifest"]["total_bytes"]
    )
    result = {
        "compaction": {
            **compaction,
            "input_fragment_bytes": fragmentation["manifest"]["total_bytes"],
            "input_fragment_count": fragmentation["manifest"]["file_count"],
            "output_to_input_byte_ratio": f"{compact_to_fragment_ratio:.9f}",
        },
        "fragmentation": fragmentation,
        "logical_parity_verified": True,
        "repair": {
            **repair,
            "output_to_source_byte_ratio": (
                f"{repair['manifest']['total_bytes'] / source_bytes:.9f}"
            ),
        },
        "source_bucket": source_bucket.relative_to(dataset_root).as_posix(),
        "source_logical_summary": source_summary,
        "source_row_count": source_rows,
        "source_tree_unchanged": True,
    }
    shutil.rmtree(scratch)
    return result


def prepare_reference_workdir(
    *,
    work_dir: Path,
    decision_path: Path,
    profile: Literal["smoke", "reference"],
    rows: int,
    instruments: int,
    row_group_rows: int,
    generation_chunk_rows: int,
    force: bool = False,
) -> Path:
    work_dir = work_dir.resolve()
    preparation_path = work_dir / "preparation.json"
    preflight_evidence(preparation_path, force=force)
    if work_dir.exists():
        if not force:
            raise FileExistsError(f"work directory exists: {work_dir}")
        _safe_replace_work_dir(work_dir)
    row_count = _validate_scale(profile, rows, instruments)
    shortlist, decision = _shortlist(decision_path)
    work_dir.mkdir(parents=True)
    publish_evidence(
        work_dir / "run.json",
        {
            "decision_evidence": decision,
            "input": {
                "generation_chunk_rows": generation_chunk_rows,
                "instrument_count": instruments,
                "row_count": row_count,
                "row_group_rows": row_group_rows,
            },
            "profile": profile,
            "run_schema": RUN_SCHEMA,
        },
    )
    datasets = []
    for index, layout in enumerate(shortlist):
        candidate_root = work_dir / "datasets" / f"candidate-{index}"
        candidate_root.mkdir(parents=True)
        write = write_layout(
            row_count=row_count,
            instrument_count=instruments,
            root=candidate_root,
            layout=layout,
            row_group_rows=row_group_rows,
            generation_chunk_rows=generation_chunk_rows,
            calibration_mode="month-bucket",
        )
        dataset_root = candidate_root / layout.name
        manifest = _parquet_manifest(dataset_root)
        maintenance = _maintenance_probe(
            dataset_root,
            layout,
            work_dir / "maintenance" / f"candidate-{index}",
        )
        if not _content_matches(dataset_root, manifest):
            raise RuntimeError("maintenance changed a prepared shortlist dataset")
        datasets.append(
            {
                "dataset_path": dataset_root.relative_to(work_dir).as_posix(),
                "layout": {
                    "bucket_count": layout.bucket_count,
                    "compression": layout.compression,
                    "compression_level": layout.compression_level,
                    "numeric_representation": layout.numeric_representation,
                    "target_file_mb": layout.target_file_mb,
                },
                "maintenance": maintenance,
                "manifest": manifest,
                "write": write,
            }
        )
    payload = {
        "boot_marker": _boot_marker(),
        "command": shlex.join(sys.argv),
        "decision_evidence": decision,
        "hardware": _hardware(),
        "input": {
            "generation_chunk_rows": generation_chunk_rows,
            "instrument_count": instruments,
            "row_count": row_count,
            "row_group_rows": row_group_rows,
        },
        "preparation_schema": PREPARATION_SCHEMA,
        "profile": profile,
        "source_semantics": SOURCE_SEMANTICS,
        "datasets": datasets,
        "status": "prepared-for-separated-measurement",
    }
    publish_evidence(preparation_path, payload)
    return preparation_path


def _query_value(
    root: Path, engine: Engine, query_shape: QueryShape, instrument_count: int
) -> tuple[Any, ...]:
    glob = (root / "**" / "*.parquet").as_posix()
    if query_shape == "single-symbol":
        if engine == "duckdb":
            connection = duckdb.connect(":memory:")
            try:
                value = connection.execute(
                    "SELECT count(*), min(open_time_ms), max(close) FROM read_parquet(?) "
                    "WHERE instrument_id = 1",
                    [glob],
                ).fetchone()
            finally:
                connection.close()
            if value is None:
                raise RuntimeError("DuckDB returned no single-symbol result")
            return tuple(value)
        return tuple(
            pl.scan_parquet(glob, hive_partitioning=True)
            .filter(pl.col("instrument_id") == 1)
            .select(pl.len(), pl.col("open_time_ms").min(), pl.col("close").max())
            .collect()
            .row(0)
        )
    month_end = BASE_TIME_MS + 31 * 24 * 60 * 60_000
    if engine == "duckdb":
        connection = duckdb.connect(":memory:")
        try:
            value = connection.execute(
                "SELECT count(*), min(low), max(high) FROM read_parquet(?) "
                "WHERE open_time_ms >= ? AND open_time_ms < ?",
                [glob, BASE_TIME_MS, month_end],
            ).fetchone()
        finally:
            connection.close()
        if value is None:
            raise RuntimeError("DuckDB returned no universe-month result")
        return tuple(value)
    return tuple(
        pl.scan_parquet(glob, hive_partitioning=True)
        .filter((pl.col("open_time_ms") >= BASE_TIME_MS) & (pl.col("open_time_ms") < month_end))
        .select(pl.len(), pl.col("low").min(), pl.col("high").max())
        .collect()
        .row(0)
    )


def _timed_query(
    root: Path, engine: Engine, query_shape: QueryShape, instrument_count: int
) -> tuple[str, tuple[Any, ...]]:
    started = time.perf_counter()
    value = _query_value(root, engine, query_shape, instrument_count)
    return f"{time.perf_counter() - started:.9f}", value


def measure_leg(
    *,
    work_dir: Path,
    engine: Engine,
    query_shape: QueryShape,
    cache_proof: CacheProof,
) -> Path:
    work_dir = work_dir.resolve()
    preparation_path = work_dir / "preparation.json"
    preparation = _load_verified(preparation_path, "preparation_schema", PREPARATION_SCHEMA)
    profile = preparation.get("profile")
    if profile == "reference" and cache_proof != "reboot":
        raise ValueError("reference measurement requires reboot cache proof")
    current_boot = _boot_marker()
    if cache_proof == "reboot" and current_boot == preparation.get("boot_marker"):
        raise ValueError("reboot cache proof requires a boot after preparation")
    output = work_dir / f"measurement-{engine}-{query_shape}.json"
    preflight_evidence(output)
    raw_datasets = preparation.get("datasets")
    raw_input = preparation.get("input")
    if not isinstance(raw_datasets, list) or not isinstance(raw_input, Mapping):
        raise ValueError("preparation evidence is malformed")
    measurements = []
    for dataset in raw_datasets:
        if not isinstance(dataset, Mapping) or not isinstance(dataset.get("dataset_path"), str):
            raise ValueError("preparation dataset entry is malformed")
        root = work_dir / dataset["dataset_path"]
        manifest = dataset.get("manifest")
        if not isinstance(manifest, Mapping) or not _metadata_matches(root, manifest):
            raise ValueError("prepared dataset metadata changed before first timed read")
        first_seconds, first_value = _timed_query(
            root, engine, query_shape, int(raw_input["instrument_count"])
        )
        warm_seconds, warm_value = _timed_query(
            root, engine, query_shape, int(raw_input["instrument_count"])
        )
        canonical_first = [_canonical_scalar(value) for value in first_value]
        canonical_warm = [_canonical_scalar(value) for value in warm_value]
        if canonical_first != canonical_warm:
            raise RuntimeError("first and warm query results differ")
        minutes_per_instrument = int(raw_input["row_count"]) // int(raw_input["instrument_count"])
        expected_row_count = (
            minutes_per_instrument
            if query_shape == "single-symbol"
            else min(minutes_per_instrument, 31 * 24 * 60) * int(raw_input["instrument_count"])
        )
        if int(canonical_first[0]) != expected_row_count:
            raise RuntimeError("timed query returned an unexpected row count")
        if not _content_matches(root, manifest):
            raise ValueError("prepared dataset content changed")
        measurements.append(
            {
                "dataset_path": dataset["dataset_path"],
                "first_seconds": first_seconds,
                "observed_row_count": expected_row_count,
                "post_scan_content_verified": True,
                "pre_scan_metadata_verified": True,
                "result_sha256": canonical_sha256(canonical_first),
                "warm_seconds": warm_seconds,
            }
        )
    payload = {
        "boot_marker": current_boot,
        "cache_proof": cache_proof,
        "command": shlex.join(sys.argv),
        "engine": engine,
        "hardware": _hardware(),
        "measurement_schema": MEASUREMENT_SCHEMA,
        "measurements": measurements,
        "preparation": {
            "artifact": preparation_path.name,
            "artifact_sha256": sha256_file(preparation_path),
        },
        "profile": profile,
        "query_shape": query_shape,
        "status": (
            "reboot-separated-first-read" if cache_proof == "reboot" else "unverified-smoke-read"
        ),
    }
    publish_evidence(output, payload)
    return output


def finalize_reference_evidence(*, work_dir: Path, output: Path, force: bool = False) -> Path:
    work_dir = work_dir.resolve()
    output, _receipt = preflight_evidence(output, force=force)
    preparation_path = work_dir / "preparation.json"
    preparation = _load_verified(preparation_path, "preparation_schema", PREPARATION_SCHEMA)
    measurement_paths = [
        work_dir / f"measurement-{engine}-{query}.json"
        for engine in ("duckdb", "polars")
        for query in ("single-symbol", "universe-month")
    ]
    measurements = [
        _load_verified(path, "measurement_schema", MEASUREMENT_SCHEMA) for path in measurement_paths
    ]
    expected_legs = {
        (engine, query)
        for engine in ("duckdb", "polars")
        for query in ("single-symbol", "universe-month")
    }
    if {(item.get("engine"), item.get("query_shape")) for item in measurements} != expected_legs:
        raise ValueError("reference benchmark measurement legs are incomplete")
    for query_shape in ("single-symbol", "universe-month"):
        query_measurements = [
            item for item in measurements if item.get("query_shape") == query_shape
        ]
        result_sets = [
            [
                (entry.get("dataset_path"), entry.get("result_sha256"))
                for entry in item.get("measurements", [])
                if isinstance(entry, Mapping)
            ]
            for item in query_measurements
        ]
        if len(result_sets) != 2 or result_sets[0] != result_sets[1]:
            raise ValueError(f"DuckDB and Polars results differ for {query_shape}")
    preparation_hash = sha256_file(preparation_path)
    if any(
        item.get("preparation", {}).get("artifact_sha256") != preparation_hash
        for item in measurements
    ):
        raise ValueError("measurement does not reference the current preparation")
    hardware = preparation.get("hardware")
    if any(item.get("hardware") != hardware for item in measurements):
        raise ValueError("reference benchmark hardware changed between stages")
    profile = preparation.get("profile")
    boot_markers = [str(item.get("boot_marker")) for item in measurements]
    if profile == "reference":
        if any(item.get("cache_proof") != "reboot" for item in measurements):
            raise ValueError("reference benchmark contains an unverified cache leg")
        if len(set(boot_markers)) != 4 or preparation.get("boot_marker") in boot_markers:
            raise ValueError("reference measurements require four distinct post-preparation boots")
    raw_datasets = preparation.get("datasets")
    if not isinstance(raw_datasets, list) or any(
        not isinstance(dataset, Mapping)
        or dataset.get("maintenance", {}).get("logical_parity_verified") is not True
        or dataset.get("maintenance", {}).get("source_tree_unchanged") is not True
        for dataset in raw_datasets
    ):
        raise ValueError("preparation lacks complete immutable maintenance evidence")
    payload = {
        "benchmark_schema": FINAL_SCHEMA,
        "cache_semantics": (
            "unverified local smoke; no cold-cache claim"
            if profile == "smoke"
            else (
                "each engine/query first read followed a distinct reboot; "
                "content verified after timing"
            )
        ),
        "command": shlex.join(sys.argv),
        "hardware": hardware,
        "limitations": [
            "The input is deterministic exact synthetic data, not real-market-skew evidence.",
            "Owner/PM acceptance is still required for P-001 through P-005 and Gate 1.",
            (
                "Smoke cache timing is not cold-cache evidence."
                if profile == "smoke"
                else "A reboot reduces cache ambiguity but cannot prevent unrelated host reads."
            ),
        ],
        "measurements": measurements,
        "preparation": {
            "artifact": preparation_path.name,
            "artifact_sha256": preparation_hash,
            "boot_marker": preparation["boot_marker"],
            "datasets": raw_datasets,
            "decision_evidence": preparation["decision_evidence"],
            "input": preparation["input"],
            "source_semantics": preparation["source_semantics"],
        },
        "profile": profile,
        "status": (
            "local-smoke-only" if profile == "smoke" else "reference-synthetic-protocol-candidate"
        ),
    }
    publish_evidence(output, payload, force=force)
    return output


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command_name", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--work-dir", type=Path, required=True)
    prepare.add_argument(
        "--decision-evidence",
        type=Path,
        default=Path("benchmarks/results/m1-layout-exact-decision-candidate.json"),
    )
    prepare.add_argument("--profile", choices=["smoke", "reference"], required=True)
    prepare.add_argument("--rows", type=int, required=True)
    prepare.add_argument("--instruments", type=int, required=True)
    prepare.add_argument("--row-group-rows", type=int, default=100_000)
    prepare.add_argument("--generation-chunk-rows", type=int, default=1_000_000)
    prepare.add_argument("--force", action="store_true")

    measure = commands.add_parser("measure")
    measure.add_argument("--work-dir", type=Path, required=True)
    measure.add_argument("--engine", choices=["duckdb", "polars"], required=True)
    measure.add_argument(
        "--query-shape", choices=["single-symbol", "universe-month"], required=True
    )
    measure.add_argument("--cache-proof", choices=["reboot", "unverified-smoke"], required=True)

    finalize = commands.add_parser("finalize")
    finalize.add_argument("--work-dir", type=Path, required=True)
    finalize.add_argument("--output", type=Path, required=True)
    finalize.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    if args.command_name == "prepare":
        path = prepare_reference_workdir(
            work_dir=args.work_dir,
            decision_path=args.decision_evidence,
            profile=args.profile,
            rows=args.rows,
            instruments=args.instruments,
            row_group_rows=args.row_group_rows,
            generation_chunk_rows=args.generation_chunk_rows,
            force=args.force,
        )
    elif args.command_name == "measure":
        path = measure_leg(
            work_dir=args.work_dir,
            engine=args.engine,
            query_shape=args.query_shape,
            cache_proof=args.cache_proof,
        )
    else:
        path = finalize_reference_evidence(
            work_dir=args.work_dir,
            output=args.output,
            force=args.force,
        )
    print(json.dumps({"artifact": str(path.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
