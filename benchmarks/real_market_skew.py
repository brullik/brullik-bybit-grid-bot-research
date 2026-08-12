"""Bounded public real-market layout-skew evidence for the ADR-0010 shortlist."""

from __future__ import annotations

import argparse
import json
import platform
import shlex
import shutil
import sys
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, Protocol

import duckdb
import polars as pl
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from grid_bybit_public import BybitPublicClient, UrllibJsonTransport
from grid_contracts.canonical import canonical_sha256, decimal_text, sha256_file
from grid_data.archive_inventory import load_verified_public_inventory
from grid_data.evidence import preflight_evidence, publish_evidence, verify_evidence

from benchmarks.layout_benchmark import (
    PRICE_SCALE,
    TURNOVER_SCALE,
    VOLUME_SCALE,
    Layout,
    _table_with_numeric_metadata,
    _verify_exact_numeric_schema,
)
from benchmarks.reference_layout_benchmark import (
    _canonical_scalar,
    _parquet_manifest,
    _shortlist,
)

EVIDENCE_SCHEMA = "grid.real-market-layout-skew/v1"
OWNERSHIP_SCHEMA = "grid.real-market-layout-skew-work/v1"
MINUTE_MS = 60_000
MAX_SPAN_MS = 7 * 24 * 60 * MINUTE_MS - MINUTE_MS
MIN_SAMPLE_SIZE = 3
MAX_SAMPLE_SIZE = 12
MIN_LIQUID_POOL = 50


class MarketClient(Protocol):
    def tickers(
        self, *, category: Literal["linear", "inverse"] = "linear"
    ) -> tuple[Mapping[str, Any], ...]: ...

    def iter_klines_backward(
        self,
        *,
        kind: Literal["trade", "mark"],
        symbol: str,
        start_ms: int,
        end_ms: int,
        category: Literal["linear", "inverse"] = "linear",
        limit: int = 1000,
        max_pages: int = 1_000_000,
    ) -> Iterator[tuple[str, ...]]: ...


def _decimal(value: Any, name: str, *, positive: bool = True) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be exact decimal text")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{name} must be exact decimal text") from error
    if not parsed.is_finite() or (positive and parsed <= 0) or (not positive and parsed < 0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{name} must be finite and {qualifier}")
    return parsed


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _validate_request(start_ms: int, end_ms: int, sample_size: int) -> None:
    if start_ms < 0 or end_ms < start_ms:
        raise ValueError("invalid real-market sample range")
    if start_ms % MINUTE_MS or end_ms % MINUTE_MS:
        raise ValueError("real-market sample bounds must be UTC-minute aligned")
    if end_ms - start_ms > MAX_SPAN_MS:
        raise ValueError("real-market sample may not exceed seven inclusive days")
    if not MIN_SAMPLE_SIZE <= sample_size <= MAX_SAMPLE_SIZE:
        raise ValueError(f"sample size must be in [{MIN_SAMPLE_SIZE}, {MAX_SAMPLE_SIZE}]")
    closed_before_ms = int(datetime.now(UTC).timestamp() * 1000) - MINUTE_MS
    if end_ms >= closed_before_ms:
        raise ValueError("real-market sample must contain only closed candles")


def select_symbols(
    inventory: Mapping[str, Any],
    tickers: Sequence[Mapping[str, Any]],
    *,
    start_ms: int,
    sample_size: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records = inventory.get("records")
    if inventory.get("evidence_schema") != "grid.bybit-public-inventory/v1" or not isinstance(
        records, list
    ):
        raise ValueError("unsupported public instrument inventory")
    ticker_by_symbol: dict[str, Mapping[str, Any]] = {}
    for ticker in tickers:
        symbol = ticker.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("ticker symbol must be non-empty text")
        if symbol in ticker_by_symbol:
            raise ValueError(f"duplicate ticker symbol: {symbol}")
        ticker_by_symbol[symbol] = ticker

    candidates: list[tuple[Decimal, Decimal, str, dict[str, Any]]] = []
    seen_ids: set[int] = set()
    for raw_record in records:
        if not isinstance(raw_record, Mapping):
            raise ValueError("inventory records must be objects")
        if (
            raw_record.get("contract_type") != "LinearPerpetual"
            or raw_record.get("quote_coin") != "USDT"
            or raw_record.get("settle_coin") != "USDT"
            or raw_record.get("status") != "Trading"
        ):
            continue
        symbol = raw_record.get("symbol")
        source_symbol_id = raw_record.get("source_symbol_id")
        launch_time_ms = raw_record.get("launch_time_ms")
        if (
            not isinstance(symbol, str)
            or not symbol
            or not isinstance(source_symbol_id, int)
            or source_symbol_id <= 0
            or not isinstance(launch_time_ms, int)
            or launch_time_ms < 0
        ):
            raise ValueError("inventory record has invalid selection metadata")
        if source_symbol_id in seen_ids:
            raise ValueError("inventory source_symbol_id values must be unique")
        seen_ids.add(source_symbol_id)
        selected_ticker = ticker_by_symbol.get(symbol)
        if selected_ticker is None or launch_time_ms > start_ms:
            continue
        mark_price = _decimal(selected_ticker.get("markPrice"), f"{symbol}.markPrice")
        turnover = _decimal(selected_ticker.get("turnover24h"), f"{symbol}.turnover24h")
        entry = {
            "instrument_id": source_symbol_id,
            "launch_time_ms": launch_time_ms,
            "mark_price": decimal_text(mark_price),
            "symbol": symbol,
            "turnover_24h": decimal_text(turnover),
        }
        candidates.append((-turnover, mark_price, symbol, entry))
    pool_size = min(len(candidates), max(MIN_LIQUID_POOL, sample_size * 10))
    if pool_size < sample_size:
        raise ValueError("not enough eligible liquid instruments for real-market sampling")
    liquid_pool = sorted(candidates)[:pool_size]
    price_ranked = sorted(liquid_pool, key=lambda item: (item[1], item[2]))
    indices = [index * (pool_size - 1) // (sample_size - 1) for index in range(sample_size)]
    if len(indices) != len(set(indices)):
        raise RuntimeError("price-stratified selection produced duplicate ranks")
    selected = [price_ranked[index][3] for index in indices]
    return selected, {
        "eligible_instrument_count": len(candidates),
        "liquid_pool_size": pool_size,
        "pool_ranking": "turnover_24h_desc,symbol_asc",
        "selection": "even exact-mark-price ranks across the liquid pool",
        "selected_price_rank_indices": indices,
    }


def _normalize_row(row: Sequence[str], instrument_id: int, symbol: str) -> dict[str, Any]:
    if len(row) != 7:
        raise ValueError("unexpected trade-kline row width")
    timestamp_text, open_text, high_text, low_text, close_text, volume_text, turnover_text = row
    try:
        timestamp = int(timestamp_text)
    except ValueError as error:
        raise ValueError("trade-kline timestamp must be integer text") from error
    if timestamp < 0 or timestamp % MINUTE_MS:
        raise ValueError("trade-kline timestamp must be a non-negative UTC minute")
    open_ = _decimal(open_text, "open")
    high = _decimal(high_text, "high")
    low = _decimal(low_text, "low")
    close = _decimal(close_text, "close")
    volume = _decimal(volume_text, "volume", positive=False)
    turnover = _decimal(turnover_text, "turnover", positive=False)
    if low > high or not low <= open_ <= high or not low <= close <= high:
        raise ValueError("trade-kline OHLC bounds are invalid")
    return {
        "close": decimal_text(close),
        "high": decimal_text(high),
        "instrument_id": instrument_id,
        "low": decimal_text(low),
        "open": decimal_text(open_),
        "open_time_ms": timestamp,
        "symbol": symbol,
        "turnover": decimal_text(turnover),
        "volume": decimal_text(volume),
    }


def _fetch_rows(
    client: MarketClient,
    selected: Sequence[Mapping[str, Any]],
    *,
    start_ms: int,
    end_ms: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    expected_timestamps = tuple(range(start_ms, end_ms + 1, MINUTE_MS))
    page_limit = 1_000
    max_pages = (len(expected_timestamps) + page_limit - 1) // page_limit
    all_rows: list[dict[str, Any]] = []
    per_symbol: list[dict[str, Any]] = []
    for item in selected:
        symbol = str(item["symbol"])
        instrument_id = _positive_int(item["instrument_id"], f"{symbol}.instrument_id")
        raw_rows = tuple(
            client.iter_klines_backward(
                kind="trade",
                symbol=symbol,
                start_ms=start_ms,
                end_ms=end_ms,
                limit=page_limit,
                max_pages=max_pages,
            )
        )
        normalized = [_normalize_row(row, instrument_id, symbol) for row in raw_rows]
        timestamps = [int(row["open_time_ms"]) for row in normalized]
        if timestamps != sorted(timestamps, reverse=True) or len(timestamps) != len(
            set(timestamps)
        ):
            raise ValueError(f"{symbol} rows are not unique reverse-chronological data")
        if tuple(reversed(timestamps)) != expected_timestamps:
            raise ValueError(f"{symbol} does not have complete requested 1m coverage")
        normalized.reverse()
        all_rows.extend(normalized)
        closes = [Decimal(str(row["close"])) for row in normalized]
        per_symbol.append(
            {
                "close_max": decimal_text(max(closes)),
                "close_min": decimal_text(min(closes)),
                "content_sha256": canonical_sha256(normalized),
                "instrument_id": instrument_id,
                "row_count": len(normalized),
                "symbol": symbol,
            }
        )
    all_rows.sort(key=lambda row: (int(row["instrument_id"]), int(row["open_time_ms"])))
    return all_rows, sorted(per_symbol, key=lambda item: item["symbol"])


def _units(value: str, scale: int, name: str) -> int:
    parsed = Decimal(value)
    scaled = parsed * (10**scale)
    integral = scaled.to_integral_value()
    if scaled != integral:
        raise ValueError(f"{name} exceeds the exact physical scale {scale}")
    return int(integral)


def _decimal_places(value: str) -> int:
    exponent = Decimal(value).normalize().as_tuple().exponent
    if not isinstance(exponent, int):
        raise ValueError("non-finite decimal exponent")
    return max(0, -exponent)


def _arrow_table(rows: Sequence[Mapping[str, Any]], layout: Layout) -> pa.Table:
    prices = ("open", "high", "low", "close")
    arrays: dict[str, pa.Array] = {
        "instrument_id": pa.array([row["instrument_id"] for row in rows], type=pa.uint32()),
        "open_time_ms": pa.array([row["open_time_ms"] for row in rows], type=pa.int64()),
    }
    if layout.numeric_representation == "hybrid_int64_decimal":
        for name in prices:
            arrays[name] = pa.array(
                [_units(str(row[name]), PRICE_SCALE, name) for row in rows], type=pa.int64()
            )
    elif layout.numeric_representation == "decimal128":
        for name in prices:
            arrays[name] = pa.array(
                [Decimal(str(row[name])) for row in rows], type=pa.decimal128(38, PRICE_SCALE)
            )
    else:
        raise ValueError("real-market layout must use an exact representation")
    arrays["volume"] = pa.array(
        [Decimal(str(row["volume"])) for row in rows], type=pa.decimal128(38, VOLUME_SCALE)
    )
    arrays["turnover"] = pa.array(
        [Decimal(str(row["turnover"])) for row in rows],
        type=pa.decimal128(38, TURNOVER_SCALE),
    )
    arrays["quality_flags"] = pa.array([0] * len(rows), type=pa.uint8())
    return _table_with_numeric_metadata(pa.table(arrays), layout)


def _logical_summary(root: Path) -> dict[str, Any]:
    glob = (root / "**" / "*.parquet").as_posix()
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
        raise RuntimeError("DuckDB returned no real-market summary")
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
        raise RuntimeError("DuckDB and Polars real-market summaries differ")
    return {
        "duckdb_polars_equal": True,
        "logical_sha256": canonical_sha256(duckdb_values),
        "row_count": int(duckdb_values[0]),
    }


def _write_layout(
    root: Path, rows: Sequence[Mapping[str, Any]], layout: Layout, row_group_rows: int
) -> dict[str, Any]:
    layout_root = root / layout.name
    if layout_root.exists():
        raise FileExistsError(f"real-market layout already exists: {layout_root}")
    groups: dict[tuple[int, int, int], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        timestamp = datetime.fromtimestamp(int(row["open_time_ms"]) / 1000, UTC)
        bucket = int(row["instrument_id"]) % layout.bucket_count
        groups[(timestamp.year, timestamp.month, bucket)].append(row)
    bucket_counts = []
    for file_index, ((year, month, bucket), group) in enumerate(sorted(groups.items())):
        group.sort(key=lambda row: (int(row["instrument_id"]), int(row["open_time_ms"])))
        destination = (
            layout_root
            / "dataset=trade_kline_1m"
            / "schema=v1"
            / f"year={year:04d}"
            / f"month={month:02d}"
            / f"bucket={bucket:02d}"
        )
        destination.mkdir(parents=True)
        table = _arrow_table(group, layout)
        pq.write_table(
            table,
            destination / f"part-{file_index:05d}.parquet",
            compression=layout.compression,
            compression_level=layout.compression_level,
            row_group_size=row_group_rows,
            write_statistics=True,
        )
        bucket_counts.append(len(group))
    paths = sorted(layout_root.rglob("*.parquet"))
    _verify_exact_numeric_schema(paths, layout)
    manifest = _parquet_manifest(layout_root)
    logical = _logical_summary(layout_root)
    if logical["row_count"] != len(rows):
        raise RuntimeError("real-market Parquet layout row count differs from normalized input")
    return {
        "bucket_row_count_max": max(bucket_counts),
        "bucket_row_count_min": min(bucket_counts),
        "bytes_per_row": f"{Decimal(manifest['total_bytes']) / Decimal(len(rows)):.9f}",
        "exact_schema_verified": True,
        "layout": {
            "bucket_count": layout.bucket_count,
            "compression": layout.compression,
            "compression_level": layout.compression_level,
            "numeric_representation": layout.numeric_representation,
            "target_file_mb": layout.target_file_mb,
        },
        "logical_summary": logical,
        "manifest": manifest,
    }


def _distribution(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    price_values = [
        Decimal(str(row[name])) for row in rows for name in ("open", "high", "low", "close")
    ]
    closes = {str(row["close"]) for row in rows}
    volumes = [Decimal(str(row["volume"])) for row in rows]
    turnovers = [Decimal(str(row["turnover"])) for row in rows]
    return {
        "distinct_close_count": len(closes),
        "maximum_price": decimal_text(max(price_values)),
        "maximum_price_decimal_places": max(
            _decimal_places(str(row[name]))
            for row in rows
            for name in ("open", "high", "low", "close")
        ),
        "maximum_turnover": decimal_text(max(turnovers)),
        "maximum_turnover_decimal_places": max(
            _decimal_places(str(row["turnover"])) for row in rows
        ),
        "maximum_volume": decimal_text(max(volumes)),
        "maximum_volume_decimal_places": max(_decimal_places(str(row["volume"])) for row in rows),
        "minimum_price": decimal_text(min(price_values)),
        "minimum_turnover": decimal_text(min(turnovers)),
        "minimum_volume": decimal_text(min(volumes)),
        "price_dynamic_range": decimal_text(max(price_values) / min(price_values)),
        "zero_turnover_count": sum(value == 0 for value in turnovers),
        "zero_volume_count": sum(value == 0 for value in volumes),
    }


def _safe_replace_work_dir(work_dir: Path) -> None:
    work_dir = work_dir.resolve()
    if work_dir in {Path(work_dir.anchor), Path.cwd().resolve(), Path.home().resolve()}:
        raise ValueError("refusing to replace a broad real-market work directory")
    marker = work_dir / "ownership.json"
    if not verify_evidence(marker) or _load_json(marker).get("work_schema") != OWNERSHIP_SCHEMA:
        raise ValueError("refusing to replace work directory without a verified ownership marker")
    shutil.rmtree(work_dir)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"artifact is not a JSON object: {path}")
    return payload


def build_real_market_skew(
    *,
    client: MarketClient,
    inventory: Mapping[str, Any],
    inventory_path: Path,
    decision_path: Path,
    work_dir: Path,
    start_ms: int,
    end_ms: int,
    sample_size: int,
    row_group_rows: int,
) -> dict[str, Any]:
    _validate_request(start_ms, end_ms, sample_size)
    if row_group_rows <= 0:
        raise ValueError("row-group-rows must be positive")
    layouts, decision = _shortlist(decision_path)
    selected, selection = select_symbols(
        inventory, client.tickers(category="linear"), start_ms=start_ms, sample_size=sample_size
    )
    rows, per_symbol = _fetch_rows(client, selected, start_ms=start_ms, end_ms=end_ms)
    layout_results = [
        _write_layout(work_dir / "layouts", rows, layout, row_group_rows) for layout in layouts
    ]
    logical_hashes = {result["logical_summary"]["logical_sha256"] for result in layout_results}
    if len(logical_hashes) != 1:
        raise RuntimeError("shortlisted real-market layouts do not preserve identical values")
    run_payload = {
        "content_sha256": canonical_sha256(rows),
        "decision_evidence": decision,
        "layouts": layout_results,
        "request": {
            "end_ms": end_ms,
            "row_group_rows": row_group_rows,
            "sample_size": sample_size,
            "start_ms": start_ms,
        },
        "work_schema": OWNERSHIP_SCHEMA,
    }
    run_path, _run_receipt = publish_evidence(work_dir / "run.json", run_payload)
    evidence: dict[str, Any] = {
        "content_sha256": "",
        "decision_evidence": decision,
        "distribution": _distribution(rows),
        "evidence_schema": EVIDENCE_SCHEMA,
        "fetched_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "hardware": {
            "machine": platform.machine(),
            "platform": platform.platform(),
        },
        "inventory_evidence": {
            "artifact": inventory_path.name,
            "artifact_sha256": sha256_file(inventory_path),
            "evidence_schema": inventory["evidence_schema"],
            "fetched_at_utc": inventory["fetched_at_utc"],
        },
        "layouts": [
            {
                "bucket_row_count_max": result["bucket_row_count_max"],
                "bucket_row_count_min": result["bucket_row_count_min"],
                "bytes_per_row": result["bytes_per_row"],
                "exact_schema_verified": result["exact_schema_verified"],
                "file_count": result["manifest"]["file_count"],
                "layout": result["layout"],
                "logical_summary": result["logical_summary"],
                "total_bytes": result["manifest"]["total_bytes"],
                "tree_sha256": result["manifest"]["tree_sha256"],
            }
            for result in layout_results
        ],
        "limitations": [
            (
                "Current ticker liquidity selected a bounded historical compression sample and "
                "is not decision-time universe evidence."
            ),
            (
                "The sample covers at most seven days and cannot represent all historical "
                "volatility regimes."
            ),
            (
                "Only trade-price candle physical layouts are measured; mark-price rows have a "
                "different logical column set."
            ),
            (
                "Raw rows and Parquet files remain outside Git; the public artifact retains "
                "content and tree hashes only."
            ),
            (
                "This evidence cannot decide P-001 through P-005 or close Gate 1 without the "
                "reference-host protocol and owner/PM acceptance."
            ),
        ],
        "per_symbol": per_symbol,
        "raw_storage_policy": "ignored operator work directory; never committed",
        "request": {
            "category": "linear",
            "closed_candles_only": True,
            "end_ms": end_ms,
            "endpoint": "/v5/market/kline",
            "expected_rows_per_symbol": (end_ms - start_ms) // MINUTE_MS + 1,
            "interval": "1",
            "start_ms": start_ms,
        },
        "selection": {
            **selection,
            "observed_ticker_endpoint": "/v5/market/tickers",
            "selected": selected,
        },
        "source_content_sha256": canonical_sha256(rows),
        "status": "complete-bounded-real-market-skew",
        "total_row_count": len(rows),
        "work_evidence": {
            "artifact": run_path.name,
            "artifact_sha256": sha256_file(run_path),
            "work_schema": OWNERSHIP_SCHEMA,
        },
    }
    hash_input = dict(evidence)
    hash_input.pop("content_sha256")
    evidence["content_sha256"] = canonical_sha256(hash_input)
    return evidence


def prepare_work_dir(work_dir: Path, ownership: Mapping[str, Any], *, force: bool) -> Path:
    work_dir = work_dir.resolve()
    if work_dir.exists():
        if not force:
            raise FileExistsError(f"work directory exists: {work_dir}")
        _safe_replace_work_dir(work_dir)
    work_dir.mkdir(parents=True)
    marker, _receipt = publish_evidence(
        work_dir / "ownership.json",
        {"configuration": dict(ownership), "work_schema": OWNERSHIP_SCHEMA},
    )
    return marker


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instrument-inventory", type=Path, required=True)
    parser.add_argument(
        "--decision-evidence",
        type=Path,
        default=Path("benchmarks/results/m1-layout-exact-decision-candidate.json"),
    )
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--start-ms", type=int, required=True)
    parser.add_argument("--end-ms", type=int, required=True)
    parser.add_argument("--sample-size", type=int, default=8)
    parser.add_argument("--row-group-rows", type=int, default=100_000)
    parser.add_argument("--base-url", default="https://api.bybit.com")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    output, _receipt = preflight_evidence(args.output, force=args.force)
    _validate_request(args.start_ms, args.end_ms, args.sample_size)
    inventory_path = args.instrument_inventory.resolve()
    inventory = load_verified_public_inventory(inventory_path)
    decision_path = args.decision_evidence.resolve()
    _shortlist(decision_path)
    work_dir = args.work_dir.resolve()
    if output == work_dir or work_dir in output.parents:
        raise ValueError("public evidence output must be outside the raw work directory")
    ownership = {
        "decision_evidence": decision_path.name,
        "end_ms": args.end_ms,
        "instrument_inventory": inventory_path.name,
        "row_group_rows": args.row_group_rows,
        "sample_size": args.sample_size,
        "start_ms": args.start_ms,
    }
    prepare_work_dir(work_dir, ownership, force=args.force)
    payload = build_real_market_skew(
        client=BybitPublicClient(UrllibJsonTransport(base_url=args.base_url)),
        inventory=inventory,
        inventory_path=inventory_path,
        decision_path=decision_path,
        work_dir=work_dir,
        start_ms=args.start_ms,
        end_ms=args.end_ms,
        sample_size=args.sample_size,
        row_group_rows=args.row_group_rows,
    )
    payload["command"] = shlex.join(sys.argv)
    hash_input = dict(payload)
    hash_input.pop("content_sha256")
    payload["content_sha256"] = canonical_sha256(hash_input)
    artifact, receipt = publish_evidence(output, payload, force=args.force)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "layouts": payload["layouts"],
                "receipt": str(receipt),
                "selected_symbols": [item["symbol"] for item in payload["selection"]["selected"]],
                "status": payload["status"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
