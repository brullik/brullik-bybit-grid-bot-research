"""Build immutable evidence describing official Bybit bulk archive coverage."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from grid_bybit_public import (
    ArchivePathNotFound,
    BybitArchiveIndex,
    ProductIndexSummary,
    TradeArchiveCoverage,
)
from grid_contracts.canonical import canonical_sha256

from grid_data.evidence import verify_evidence


def build_archive_inventory(index: BybitArchiveIndex, symbols: tuple[str, ...]) -> dict[str, Any]:
    products = index.products()
    archive_symbols = index.trading_symbols()
    archive_symbol_set = set(archive_symbols)
    coverage = [dataclasses.asdict(index.trade_coverage(symbol)) for symbol in symbols]
    payload: dict[str, Any] = {
        "archive_symbol_count": len(archive_symbols),
        "coverage": coverage,
        "evidence_schema": "grid.bybit-archive-inventory/v1",
        "fetched_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "products": list(products),
        "requested_symbols": list(symbols),
        "requested_symbols_present": {symbol: symbol in archive_symbol_set for symbol in symbols},
        "source": "https://public.bybit.com/",
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def load_verified_public_inventory(path: Path) -> dict[str, Any]:
    path = path.resolve()
    if not verify_evidence(path):
        raise ValueError(f"instrument inventory or receipt does not verify: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("evidence_schema") != (
        "grid.bybit-public-inventory/v1"
    ):
        raise ValueError("instrument inventory has an unsupported evidence schema")
    embedded_hash = payload.get("content_sha256")
    hash_input = dict(payload)
    hash_input.pop("content_sha256", None)
    if embedded_hash != canonical_sha256(hash_input):
        raise ValueError("instrument inventory embedded content hash does not verify")
    return payload


def _usdt_perpetual_records(inventory: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    raw_records = inventory.get("records")
    if not isinstance(raw_records, list):
        raise ValueError("instrument inventory records must be an array")
    selected: list[dict[str, Any]] = []
    symbols: set[str] = set()
    for raw in raw_records:
        if not isinstance(raw, dict):
            raise ValueError("instrument inventory record must be an object")
        if not (
            raw.get("contract_type") == "LinearPerpetual"
            and raw.get("quote_coin") == "USDT"
            and raw.get("settle_coin") == "USDT"
        ):
            continue
        symbol = raw.get("symbol")
        if not isinstance(symbol, str) or symbol in symbols:
            raise ValueError("USDT perpetual inventory symbols must be unique strings")
        if not isinstance(raw.get("launch_time_ms"), int) or not isinstance(raw.get("status"), str):
            raise ValueError("instrument inventory record is missing launch/status metadata")
        symbols.add(symbol)
        selected.append(raw)
    if not selected:
        raise ValueError("instrument inventory contains no USDT linear perpetual records")
    return tuple(sorted(selected, key=lambda item: (item["launch_time_ms"], item["symbol"])))


def _sample_reasons(
    records: tuple[dict[str, Any], ...], archive_symbols: set[str], sample_size: int
) -> dict[str, tuple[str, ...]]:
    if not 1 <= sample_size <= 100:
        raise ValueError("sample_size must be between 1 and 100")
    reasons: dict[str, set[str]] = {}
    for record in records:
        symbol = record["symbol"]
        if symbol not in archive_symbols:
            reasons.setdefault(symbol, set()).add("absent-from-trading-index")
        if record["status"] == "PreLaunch":
            reasons.setdefault(symbol, set()).add("current-status-prelaunch")

    remaining_slots = max(0, sample_size - len(reasons))
    candidates = [record for record in records if record["symbol"] not in reasons]
    if remaining_slots and candidates:
        positions: tuple[int, ...]
        if remaining_slots == 1:
            positions = (len(candidates) // 2,)
        else:
            positions = tuple(
                index * (len(candidates) - 1) // (remaining_slots - 1)
                for index in range(remaining_slots)
            )
        for position in positions:
            reasons.setdefault(candidates[position]["symbol"], set()).add(
                "launch-time-stratified-sample"
            )
    return {symbol: tuple(sorted(values)) for symbol, values in sorted(reasons.items())}


def _product_summary(index: BybitArchiveIndex, product: str) -> ProductIndexSummary:
    return index.product_summary(product, sample_limit=20)


def _coverage(index: BybitArchiveIndex, symbol: str) -> TradeArchiveCoverage:
    return index.trade_coverage(symbol)


def _bounded_coverage(coverage: TradeArchiveCoverage) -> dict[str, Any]:
    return {
        "file_count": coverage.file_count,
        "first_date": coverage.first_date,
        "last_date": coverage.last_date,
        "missing_date_count": len(coverage.missing_dates),
        "missing_dates_sample": list(coverage.missing_dates[:20]),
        "symbol": coverage.symbol,
    }


def build_archive_coverage_matrix(
    index: BybitArchiveIndex,
    inventory: Mapping[str, Any],
    *,
    inventory_artifact_sha256: str,
    sample_size: int = 20,
) -> dict[str, Any]:
    """Compare the current USDT-perpetual snapshot with bounded official archive evidence."""

    records = _usdt_perpetual_records(inventory)
    record_by_symbol = {record["symbol"]: record for record in records}
    products = index.products()
    archive_symbols = set(index.trading_symbols())
    sample_reasons = _sample_reasons(records, archive_symbols, sample_size)

    product_summaries = [
        dataclasses.asdict(_product_summary(index, product)) for product in products
    ]
    detailed: list[dict[str, Any]] = []
    direct_paths_not_listed: list[str] = []
    direct_paths_without_files: list[str] = []
    direct_paths_not_found: list[str] = []
    archive_before_launch: list[str] = []
    for symbol, reasons in sample_reasons.items():
        record = record_by_symbol[symbol]
        try:
            coverage = _coverage(index, symbol)
        except ArchivePathNotFound:
            coverage = None
        launch_date = (
            datetime.fromtimestamp(record["launch_time_ms"] / 1000, UTC).date().isoformat()
        )
        starts_before_launch = (
            None
            if coverage is None
            else bool(coverage.first_date is not None and coverage.first_date < launch_date)
        )
        listed = symbol in archive_symbols
        if coverage is None:
            direct_paths_not_found.append(symbol)
        elif coverage.file_count and not listed:
            direct_paths_not_listed.append(symbol)
        elif not coverage.file_count and not listed:
            direct_paths_without_files.append(symbol)
        if starts_before_launch:
            archive_before_launch.append(symbol)
        detailed.append(
            {
                "archive_coverage": None if coverage is None else _bounded_coverage(coverage),
                "archive_first_date_before_current_launch_date": starts_before_launch,
                "archive_path_status": "not-found" if coverage is None else "found",
                "current_metadata": {
                    "launch_date_utc": launch_date,
                    "launch_time_ms": record["launch_time_ms"],
                    "status": record["status"],
                },
                "present_in_trading_index": listed,
                "selection_reasons": list(reasons),
                "symbol": symbol,
            }
        )

    by_status: dict[str, dict[str, int]] = {}
    for status in sorted({record["status"] for record in records}):
        status_records = [record for record in records if record["status"] == status]
        present = sum(record["symbol"] in archive_symbols for record in status_records)
        by_status[status] = {
            "absent_from_trading_index": len(status_records) - present,
            "present_in_trading_index": present,
            "records": len(status_records),
        }
    current_symbols = set(record_by_symbol)
    product_names = set(products)
    payload: dict[str, Any] = {
        "coverage_findings": {
            "archive_first_date_before_current_launch_date_count": len(archive_before_launch),
            "archive_first_date_before_current_launch_date_symbols": sorted(archive_before_launch),
            "direct_paths_with_files_but_not_listed_count": len(direct_paths_not_listed),
            "direct_paths_with_files_but_not_listed_symbols": sorted(direct_paths_not_listed),
            "sampled_direct_paths_without_daily_files_count": len(direct_paths_without_files),
            "sampled_direct_paths_without_daily_files_symbols": sorted(direct_paths_without_files),
            "sampled_direct_paths_not_found_count": len(direct_paths_not_found),
            "sampled_direct_paths_not_found_symbols": sorted(direct_paths_not_found),
            "interpretation": (
                "The observed /trading/ index is not a complete historical symbol registry. "
                "Current launchTime is undated-current metadata and requires dated snapshots "
                "before historical eligibility decisions."
            ),
        },
        "detailed_trade_coverage": detailed,
        "evidence_schema": "grid.bybit-archive-coverage/v1",
        "fetched_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "instrument_inventory": {
            "artifact_sha256": inventory_artifact_sha256,
            "evidence_schema": inventory["evidence_schema"],
            "fetched_at_utc": inventory["fetched_at_utc"],
        },
        "observed_root_index": {
            "funding_top_level_matches": sorted(
                product for product in products if "fund" in product.casefold()
            ),
            "mark_price_top_level_matches": sorted(
                product for product in products if "mark" in product.casefold()
            ),
            "products": list(products),
            "semantics": (
                "No mark-price or funding dataset is advertised by name in the observed root "
                "index; this does not prove that no unlisted path exists."
            ),
            "trading_raw_trade_directory_advertised": "trading" in product_names,
        },
        "product_index_summaries": product_summaries,
        "source": "https://public.bybit.com/",
        "universe_comparison": {
            "archive_only_symbol_count": len(archive_symbols - current_symbols),
            "archive_trading_index_symbol_count": len(archive_symbols),
            "by_current_status": by_status,
            "current_usdt_linear_perpetual_count": len(records),
            "current_symbols_absent_from_trading_index": sorted(current_symbols - archive_symbols),
            "current_symbols_present_in_trading_index_count": len(
                current_symbols & archive_symbols
            ),
            "semantics": "current instrument snapshot compared with the observed archive index",
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload
