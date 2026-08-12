"""Build a receipt-linked Gate 1 owner-review pack from reference-only M1 evidence."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_data.evidence import preflight_evidence, publish_evidence, verify_evidence
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

from benchmarks.measured_host_qualification import qualification_summary

TRADE_ROWS = 3_681_644_400
TRADE_AND_MARK_ROWS = 7_363_288_800
TEN_YEAR_MINUTES = 5_259_492
REFERENCE_ROWS = 99_999_900
REFERENCE_INSTRUMENTS = 700
FIRST_MONTH_MINUTES = 44_640
SINGLE_SYMBOL_COLD_SECONDS_MAX = Decimal("15")
SINGLE_SYMBOL_WARM_SECONDS_MAX = Decimal("5")
UNIVERSE_MONTH_COLD_SECONDS_MAX = Decimal("15")
WRITE_100M_SECONDS_MAX = Decimal("1200")
ROOT = Path(__file__).resolve().parents[1]
LAYOUT_SCHEMA = ROOT / "schemas" / "evidence" / "v2" / "reference-layout-benchmark.schema.json"
FEATURE_SCHEMA = ROOT / "schemas" / "evidence" / "v2" / "feature-benchmark.schema.json"
REVIEW_SCHEMA = ROOT / "schemas" / "evidence" / "v1" / "gate1-review-pack.schema.json"
DECISION_SCHEMA = ROOT / "schemas" / "evidence" / "v3" / "layout-benchmark.schema.json"
REAL_MARKET_SCHEMA = ROOT / "schemas" / "evidence" / "v1" / "real-market-layout-skew.schema.json"
WORKSTATION_SCHEMA = ROOT / "schemas" / "evidence" / "v1" / "workstation-snapshot.schema.json"
LAYOUT_SCHEMA_V3 = ROOT / "schemas" / "evidence" / "v3" / "reference-layout-benchmark.schema.json"
FEATURE_SCHEMA_V3 = ROOT / "schemas" / "evidence" / "v3" / "feature-benchmark.schema.json"
REVIEW_SCHEMA_V2 = ROOT / "schemas" / "evidence" / "v2" / "gate1-review-pack.schema.json"
QUALIFICATION_SCHEMA = (
    ROOT / "schemas" / "evidence" / "v1" / "reference-host-qualification.schema.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"evidence is not valid JSON: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"evidence is not a JSON object: {path}")
    return payload


def _schema(path: Path) -> dict[str, Any]:
    return _load_json(path)


def load_verified_evidence(path: Path, schema_path: Path) -> dict[str, Any]:
    """Verify the completion receipt and the complete versioned JSON contract."""

    path = path.resolve()
    if not verify_evidence(path):
        raise ValueError(f"source evidence receipt does not verify: {path}")
    payload = _load_json(path)
    try:
        Draft202012Validator(
            _schema(schema_path),
            format_checker=FormatChecker(),
        ).validate(payload)
    except Exception as error:
        raise ValueError(f"source evidence does not match {schema_path.name}: {path}") from error
    return payload


def _decimal(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"{label} is not an exact decimal metric") from error
    if not result.is_finite() or result < 0:
        raise ValueError(f"{label} must be finite and non-negative")
    return result


def _metric(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000000001")), "f")


def _projected_bytes(rows: int, bytes_per_row: Decimal) -> int:
    return int((Decimal(rows) * bytes_per_row).to_integral_value(rounding=ROUND_CEILING))


def _layout_key(layout: dict[str, Any]) -> str:
    return json.dumps(layout, sort_keys=True, separators=(",", ":"))


def _source(path: Path, payload: dict[str, Any], schema_key: str) -> dict[str, str]:
    resolved = path.resolve()
    return {
        "artifact": resolved.name,
        "artifact_sha256": sha256_file(resolved),
        "schema": str(payload[schema_key]),
        "status": str(payload["status"]),
    }


def _workstation_summary(path: Path, workstation: dict[str, Any]) -> dict[str, Any]:
    hardware = workstation["hardware"]
    return {
        "artifact": path.resolve().name,
        "artifact_sha256": sha256_file(path.resolve()),
        "evidence_schema": workstation["evidence_schema"],
        "hardware": {
            key: hardware[key]
            for key in (
                "cpu_count_logical",
                "cpu_count_physical",
                "cpu_model",
                "machine",
                "platform",
                "ram_bytes",
                "storage_kind",
                "storage_model",
                "volume_root",
                "volume_total_bytes",
            )
        },
        "observed_at_utc": workstation["observed_at_utc"],
        "status": workstation["status"],
    }


def _real_market_summary(path: Path, real_market: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact": path.resolve().name,
        "artifact_sha256": sha256_file(path.resolve()),
        "evidence_schema": real_market["evidence_schema"],
        "layouts": [
            {key: item[key] for key in ("bytes_per_row", "layout", "total_bytes", "tree_sha256")}
            for item in real_market["layouts"]
        ],
        "source_content_sha256": real_market["source_content_sha256"],
        "total_row_count": real_market["total_row_count"],
    }


def _feature_capacity(feature: dict[str, Any]) -> dict[str, Any]:
    throughput = _decimal(
        feature["result"]["throughput_core_rows_per_second"],
        "feature throughput",
    )
    if throughput <= 0:
        raise ValueError("feature throughput must be positive")
    return {
        "configured_memory_limit_percent": feature["memory_gate"]["configured_limit_percent"],
        "memory_gate_passed": feature["memory_gate"]["passed"],
        "observed_core_rows_per_second": _metric(throughput),
        "peak_rss_bytes": feature["result"]["peak_rss_bytes"],
        "peak_rss_percent_of_ram": feature["memory_gate"]["peak_rss_percent_of_ram"],
        "projected_trade_and_mark_seconds": _metric(Decimal(TRADE_AND_MARK_ROWS) / throughput),
        "projected_trade_seconds": _metric(Decimal(TRADE_ROWS) / throughput),
    }


def _measurement_index(layout: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    expected_legs = {
        (engine, query)
        for engine in ("duckdb", "polars")
        for query in ("single-symbol", "universe-month")
    }
    observed_legs: set[tuple[str, str]] = set()
    preparation_hash = layout["preparation"]["artifact_sha256"]
    preparation_boot = layout["preparation"]["boot_marker"]
    boots: set[str] = set()
    for leg in layout["measurements"]:
        engine = str(leg["engine"])
        query = str(leg["query_shape"])
        observed_legs.add((engine, query))
        boots.add(str(leg["boot_marker"]))
        if (
            leg["hardware"] != layout["hardware"]
            or leg["software"] != layout["software"]
            or leg["preparation"]["artifact_sha256"] != preparation_hash
        ):
            raise ValueError(
                "reference layout stages do not bind one hardware/software/preparation"
            )
        for result in leg["measurements"]:
            key = (str(result["dataset_path"]), engine, query)
            if key in index:
                raise ValueError("reference layout contains a duplicate timed result")
            index[key] = result
    if observed_legs != expected_legs or len(boots) != 4 or preparation_boot in boots:
        raise ValueError("reference layout does not contain four distinct reboot-separated legs")
    return index


def _candidate(
    dataset: dict[str, Any],
    *,
    real_layout: dict[str, Any],
    measurements: dict[tuple[str, str, str], dict[str, Any]],
    reference_rows: int,
    instrument_count: int,
) -> dict[str, Any]:
    dataset_path = str(dataset["dataset_path"])
    expected_single_rows = reference_rows // instrument_count
    expected_universe_month_rows = min(expected_single_rows, FIRST_MONTH_MINUTES) * instrument_count
    first_seconds: dict[str, str] = {}
    warm_seconds: dict[str, str] = {}
    cold_projection: dict[str, str] = {}
    warm_projection: dict[str, str] = {}
    query_hashes: dict[str, str] = {}
    for query, expected_rows in (
        ("single-symbol", expected_single_rows),
        ("universe-month", expected_universe_month_rows),
    ):
        hashes: set[str] = set()
        for engine in ("duckdb", "polars"):
            key = (dataset_path, engine, query)
            if key not in measurements:
                raise ValueError(f"missing timed result for {dataset_path} {engine} {query}")
            measured = measurements[key]
            if measured["observed_row_count"] != expected_rows:
                raise ValueError(f"unexpected observed row count for {dataset_path} {query}")
            first = _decimal(measured["first_seconds"], f"{engine} {query} first seconds")
            warm = _decimal(measured["warm_seconds"], f"{engine} {query} warm seconds")
            metric_key = f"{engine}_{query.replace('-', '_')}"
            first_seconds[metric_key] = _metric(first)
            warm_seconds[metric_key] = _metric(warm)
            hashes.add(str(measured["result_sha256"]))
            if query == "single-symbol":
                scale = Decimal(TEN_YEAR_MINUTES) / Decimal(expected_rows)
                cold_projection[engine] = _metric(first * scale)
                warm_projection[engine] = _metric(warm * scale)
        if len(hashes) != 1:
            raise ValueError(f"DuckDB and Polars hashes differ for {dataset_path} {query}")
        query_hashes[query.replace("-", "_")] = hashes.pop()

    if dataset["write"].get("row_count") != reference_rows:
        raise ValueError("reference layout write row count does not match the declared input")
    synthetic_bytes = int(dataset["manifest"]["total_bytes"])
    if dataset["write"].get("bytes") != synthetic_bytes:
        raise ValueError("reference layout write bytes do not match its dataset manifest")
    write_seconds = _decimal(dataset["write"].get("write_seconds"), "layout write seconds")
    synthetic_bytes_per_row = Decimal(synthetic_bytes) / Decimal(reference_rows)
    real_bytes_per_row = _decimal(real_layout["bytes_per_row"], "real-market bytes per row")
    gates = {
        "single_symbol_cold_10y_under_15_seconds": max(
            _decimal(value, "projected cold single-symbol seconds")
            for value in cold_projection.values()
        )
        <= SINGLE_SYMBOL_COLD_SECONDS_MAX,
        "single_symbol_warm_10y_under_5_seconds": max(
            _decimal(value, "projected warm single-symbol seconds")
            for value in warm_projection.values()
        )
        <= SINGLE_SYMBOL_WARM_SECONDS_MAX,
        "universe_month_cold_under_15_seconds": max(
            _decimal(first_seconds[f"{engine}_universe_month"], "universe-month first seconds")
            for engine in ("duckdb", "polars")
        )
        <= UNIVERSE_MONTH_COLD_SECONDS_MAX,
        "write_100m_under_20_minutes": write_seconds <= WRITE_100M_SECONDS_MAX,
    }
    gates["provisional_performance_passed"] = all(gates.values())
    maintenance = dataset["maintenance"]
    return {
        "gates": gates,
        "layout": dataset["layout"],
        "maintenance": {
            "compaction_seconds": _metric(
                _decimal(maintenance["compaction"].get("elapsed_seconds"), "compaction seconds")
            ),
            "logical_parity_verified": maintenance["logical_parity_verified"],
            "repair_seconds": _metric(
                _decimal(maintenance["repair"].get("elapsed_seconds"), "repair seconds")
            ),
            "source_tree_unchanged": maintenance["source_tree_unchanged"],
        },
        "observed": {
            "first_seconds": first_seconds,
            "query_hashes": query_hashes,
            "single_symbol_rows": expected_single_rows,
            "synthetic_bytes_per_row": _metric(synthetic_bytes_per_row),
            "synthetic_total_bytes": synthetic_bytes,
            "universe_month_rows": expected_universe_month_rows,
            "warm_seconds": warm_seconds,
            "write_seconds": _metric(write_seconds),
        },
        "projections": {
            "real_trade_bytes": _projected_bytes(TRADE_ROWS, real_bytes_per_row),
            "real_trade_and_mark_bytes_at_trade_row_width": _projected_bytes(
                TRADE_AND_MARK_ROWS, real_bytes_per_row
            ),
            "real_trade_bytes_per_row": _metric(real_bytes_per_row),
            "single_symbol_10y_cold_seconds": cold_projection,
            "single_symbol_10y_warm_seconds": warm_projection,
        },
    }


def _decision(status: str, values: list[str]) -> dict[str, Any]:
    return {"candidate_values": values, "status": status}


def build_review_pack(
    layout: dict[str, Any],
    feature: dict[str, Any],
    real_market: dict[str, Any],
    workstation: dict[str, Any],
    *,
    command: str,
    real_market_path: Path,
    workstation_path: Path,
    layout_source: dict[str, str],
    feature_source: dict[str, str],
    decision_source: dict[str, str],
    real_market_source: dict[str, str],
    workstation_source: dict[str, str],
) -> dict[str, Any]:
    """Cross-bind two already schema-validated reference artifacts and calculate review gates."""

    layout_host = layout["preparation"]["reference_host_evidence"]
    feature_host = feature["reference_host_evidence"]
    if layout_host != feature_host:
        raise ValueError("layout and feature evidence do not bind the same reference host snapshot")
    if layout["hardware"] != feature["hardware"]:
        raise ValueError("layout and feature evidence report different current hardware")
    expected_hardware = {
        key: layout_host["hardware"][key]
        for key in (
            "cpu_count_logical",
            "cpu_count_physical",
            "machine",
            "platform",
            "ram_bytes",
        )
    }
    if layout["hardware"] != expected_hardware:
        raise ValueError("reference benchmark hardware does not match its workstation snapshot")
    if layout["preparation"]["software"] != layout["software"]:
        raise ValueError("reference layout preparation and final software differ")
    shared_versions = ("polars", "psutil", "python")
    if any(layout["software"][name] != feature["software"][name] for name in shared_versions):
        raise ValueError("layout and feature evidence use incompatible shared software versions")

    reference_rows = int(layout["preparation"]["input"]["row_count"])
    instrument_count = int(layout["preparation"]["input"]["instrument_count"])
    if (
        reference_rows != REFERENCE_ROWS
        or feature["input"]["row_count"] != reference_rows
        or feature["input"]["instrument_count"] != instrument_count
    ):
        raise ValueError("layout and feature evidence do not bind the same reference row scale")

    expected_decision = {
        "artifact": decision_source["artifact"],
        "artifact_sha256": decision_source["artifact_sha256"],
        "benchmark_schema": decision_source["schema"],
        "status": decision_source["status"],
    }
    if layout["preparation"]["decision_evidence"] != expected_decision:
        raise ValueError("reference layout does not bind the supplied decision evidence")
    expected_real_market = _real_market_summary(real_market_path, real_market)
    if layout["preparation"]["real_market_evidence"] != expected_real_market:
        raise ValueError("reference layout does not bind the supplied real-market evidence")
    expected_workstation = _workstation_summary(workstation_path, workstation)
    if layout_host != expected_workstation:
        raise ValueError("reference benchmarks do not bind the supplied workstation evidence")
    if workstation["assessment"]["documented_full_research_profile"]["meets"] is not True:
        raise ValueError("supplied workstation does not meet the documented full profile")
    if any(
        workstation["software"][name] != layout["software"][name] for name in ("psutil", "python")
    ):
        raise ValueError("workstation snapshot runtime differs from the reference benchmarks")
    real_market_content = dict(real_market)
    embedded_real_market_hash = real_market_content.pop("content_sha256", None)
    if embedded_real_market_hash != canonical_sha256(real_market_content):
        raise ValueError("real-market evidence embedded content hash does not verify")

    measurement_index = _measurement_index(layout)
    real_by_layout = {
        _layout_key(item["layout"]): item
        for item in layout["preparation"]["real_market_evidence"]["layouts"]
    }
    candidates = []
    for dataset in layout["preparation"]["datasets"]:
        key = _layout_key(dataset["layout"])
        if key not in real_by_layout:
            raise ValueError("reference dataset has no matching real-market layout evidence")
        candidates.append(
            _candidate(
                dataset,
                real_layout=real_by_layout[key],
                measurements=measurement_index,
                reference_rows=reference_rows,
                instrument_count=instrument_count,
            )
        )
    candidates.sort(key=lambda item: int(item["layout"]["bucket_count"]))
    if len(candidates) != 2 or {item["layout"]["bucket_count"] for item in candidates} != {4, 8}:
        raise ValueError("Gate 1 review requires the complete two-layout reference shortlist")

    feature_capacity = _feature_capacity(feature)
    eligible = [item for item in candidates if item["gates"]["provisional_performance_passed"]]
    blockers: list[str] = []
    if not eligible:
        blockers.append("no-layout-meets-provisional-performance-targets")
    if not feature_capacity["memory_gate_passed"]:
        blockers.append("feature-memory-gate-failed")
    ready = not blockers
    decision_status = "owner-decision-required" if ready else "blocked-by-reference-results"
    decision_layouts = eligible if ready else []
    p005_value = (
        f"{layout_host['hardware']['cpu_count_physical']} physical cores; "
        f"{layout_host['hardware']['ram_bytes']} RAM bytes; "
        f"{layout_host['hardware']['storage_model']}; "
        f"{layout_host['hardware']['volume_total_bytes']} volume bytes"
    )
    payload = {
        "capacity": {
            "feature": feature_capacity,
            "reference_volume_bytes": layout_host["hardware"]["volume_total_bytes"],
            "theoretical_trade_and_mark_rows": TRADE_AND_MARK_ROWS,
            "theoretical_trade_rows": TRADE_ROWS,
        },
        "command": command,
        "decisions": {
            "P-001": _decision(
                decision_status,
                sorted(
                    {str(item["layout"]["numeric_representation"]) for item in decision_layouts}
                ),
            ),
            "P-002": _decision(
                decision_status,
                [str(item["layout"]["bucket_count"]) for item in decision_layouts],
            ),
            "P-003": _decision(
                decision_status,
                [f"{item['layout']['target_file_mb']} MiB" for item in decision_layouts],
            ),
            "P-004": _decision(
                decision_status,
                sorted(
                    {
                        f"{item['layout']['compression']}-{item['layout']['compression_level']}"
                        for item in decision_layouts
                    }
                ),
            ),
            "P-005": _decision("owner-decision-required", [p005_value]),
        },
        "evidence_schema": "grid.gate1-review-pack/v1",
        "gate_1": {
            "automatic_promotion": False,
            "blockers": blockers,
            "owner_decision_required": True,
            "status": "pending-owner-decision",
        },
        "layout_candidates": candidates,
        "limitations": [
            "Single-symbol ten-year timings are linear projections from the observed reference "
            "row span, not direct ten-year scans.",
            "Real-market row width is a bounded current trade-price sample and is applied to mark "
            "rows only as a conservative like-width comparison.",
            "Storage projections exclude raw archives, features, outcomes, experiments, compaction "
            "headroom, filesystem overhead, and backup.",
            "Reboot separation reduces cache ambiguity but cannot prevent unrelated host reads.",
            "This pack cannot approve P-001 through P-005, close Gate 1, or authorize Phase 2.",
        ],
        "owner_decision_required": True,
        "reference_host": layout_host,
        "software": layout["software"],
        "sources": {
            "decision_layout": {
                key: decision_source[key]
                for key in ("artifact", "artifact_sha256", "schema", "status")
            },
            "feature": feature_source,
            "layout": layout_source,
            "real_market": {
                key: real_market_source[key]
                for key in ("artifact", "artifact_sha256", "schema", "status")
            },
            "workstation": {
                key: workstation_source[key]
                for key in ("artifact", "artifact_sha256", "schema", "status")
            },
        },
        "status": "ready-for-owner-review" if ready else "blocked-by-reference-results",
    }
    Draft202012Validator(
        _schema(REVIEW_SCHEMA),
        format_checker=FormatChecker(),
    ).validate(payload)
    return payload


def publish_review_pack(
    *,
    layout_path: Path,
    feature_path: Path,
    decision_path: Path,
    real_market_path: Path,
    workstation_path: Path,
    output: Path,
    force: bool = False,
    command: str | None = None,
) -> dict[str, Any]:
    """Verify every input before allowing replacement of the public review artifact."""

    layout = load_verified_evidence(layout_path, LAYOUT_SCHEMA)
    feature = load_verified_evidence(feature_path, FEATURE_SCHEMA)
    decision = load_verified_evidence(decision_path, DECISION_SCHEMA)
    real_market = load_verified_evidence(real_market_path, REAL_MARKET_SCHEMA)
    workstation = load_verified_evidence(workstation_path, WORKSTATION_SCHEMA)
    decision_source = _source(decision_path, decision, "benchmark_schema")
    real_market_source = _source(real_market_path, real_market, "evidence_schema")
    workstation_source = _source(workstation_path, workstation, "evidence_schema")
    payload = build_review_pack(
        layout,
        feature,
        real_market,
        workstation,
        command=shlex.join(sys.argv) if command is None else command,
        real_market_path=real_market_path,
        workstation_path=workstation_path,
        layout_source=_source(layout_path, layout, "benchmark_schema"),
        feature_source=_source(feature_path, feature, "benchmark_schema"),
        decision_source=decision_source,
        real_market_source=real_market_source,
        workstation_source=workstation_source,
    )
    output, _receipt = preflight_evidence(output, force=force)
    publish_evidence(output, payload, force=force)
    return payload


def build_qualified_review_pack(
    layout: dict[str, Any],
    feature: dict[str, Any],
    real_market: dict[str, Any],
    qualification: dict[str, Any],
    *,
    command: str,
    real_market_path: Path,
    qualification_path: Path,
    layout_source: dict[str, str],
    feature_source: dict[str, str],
    decision_source: dict[str, str],
    real_market_source: dict[str, str],
    qualification_source: dict[str, str],
) -> dict[str, Any]:
    """Cross-bind ADR-0019 v3 workloads without reinterpreting the legacy review pack."""

    layout_host = layout["preparation"]["reference_host_qualification"]
    feature_host = feature["reference_host_qualification"]
    expected_host = qualification_summary(qualification_path, qualification)
    if layout_host != feature_host or layout_host != expected_host:
        raise ValueError("layout and feature evidence do not bind the supplied host qualification")
    if layout["hardware"] != feature["hardware"]:
        raise ValueError("layout and feature evidence report different current hardware")
    expected_hardware = {
        key: layout_host["hardware"][key]
        for key in (
            "cpu_count_logical",
            "cpu_count_physical",
            "machine",
            "platform",
            "ram_bytes",
        )
    }
    if layout["hardware"] != expected_hardware:
        raise ValueError("reference benchmark hardware does not match its host qualification")
    if layout["preparation"]["software"] != layout["software"]:
        raise ValueError("reference layout preparation and final software differ")
    shared_versions = ("polars", "psutil", "python")
    if any(layout["software"][name] != feature["software"][name] for name in shared_versions):
        raise ValueError("layout and feature evidence use incompatible shared software versions")

    reference_rows = int(layout["preparation"]["input"]["row_count"])
    instrument_count = int(layout["preparation"]["input"]["instrument_count"])
    if (
        reference_rows != REFERENCE_ROWS
        or feature["input"]["row_count"] != reference_rows
        or feature["input"]["instrument_count"] != instrument_count
    ):
        raise ValueError("layout and feature evidence do not bind the same reference row scale")
    expected_decision = {
        "artifact": decision_source["artifact"],
        "artifact_sha256": decision_source["artifact_sha256"],
        "benchmark_schema": decision_source["schema"],
        "status": decision_source["status"],
    }
    if layout["preparation"]["decision_evidence"] != expected_decision:
        raise ValueError("reference layout does not bind the supplied decision evidence")
    expected_real_market = _real_market_summary(real_market_path, real_market)
    if layout["preparation"]["real_market_evidence"] != expected_real_market:
        raise ValueError("reference layout does not bind the supplied real-market evidence")
    real_market_content = dict(real_market)
    embedded_real_market_hash = real_market_content.pop("content_sha256", None)
    if embedded_real_market_hash != canonical_sha256(real_market_content):
        raise ValueError("real-market evidence embedded content hash does not verify")

    measurement_index = _measurement_index(layout)
    real_by_layout = {
        _layout_key(item["layout"]): item
        for item in layout["preparation"]["real_market_evidence"]["layouts"]
    }
    candidates = []
    for dataset in layout["preparation"]["datasets"]:
        key = _layout_key(dataset["layout"])
        if key not in real_by_layout:
            raise ValueError("reference dataset has no matching real-market layout evidence")
        candidates.append(
            _candidate(
                dataset,
                real_layout=real_by_layout[key],
                measurements=measurement_index,
                reference_rows=reference_rows,
                instrument_count=instrument_count,
            )
        )
    candidates.sort(key=lambda item: int(item["layout"]["bucket_count"]))
    if len(candidates) != 2 or {item["layout"]["bucket_count"] for item in candidates} != {4, 8}:
        raise ValueError("Gate 1 review requires the complete two-layout reference shortlist")

    feature_capacity = _feature_capacity(feature)
    eligible = [item for item in candidates if item["gates"]["provisional_performance_passed"]]
    blockers: list[str] = []
    if not eligible:
        blockers.append("no-layout-meets-provisional-performance-targets")
    if not feature_capacity["memory_gate_passed"]:
        blockers.append("feature-memory-gate-failed")
    ready = not blockers
    decision_status = "owner-decision-required" if ready else "blocked-by-reference-results"
    decision_layouts = eligible if ready else []
    hardware = layout_host["hardware"]
    p005_value = (
        f"{hardware['cpu_count_physical']} physical cores; "
        f"{hardware['ram_bytes']} RAM bytes; "
        f"{hardware['storage_model']}; "
        f"{hardware['volume_total_bytes']} volume bytes; "
        f"{layout_host['qualification']['required_free_bytes']} required free bytes"
    )
    payload = {
        "capacity": {
            "feature": feature_capacity,
            "reference_volume_bytes": hardware["volume_total_bytes"],
            "required_free_bytes": layout_host["qualification"]["required_free_bytes"],
            "theoretical_trade_and_mark_rows": TRADE_AND_MARK_ROWS,
            "theoretical_trade_rows": TRADE_ROWS,
        },
        "command": command,
        "decisions": {
            "P-001": _decision(
                decision_status,
                sorted(
                    {str(item["layout"]["numeric_representation"]) for item in decision_layouts}
                ),
            ),
            "P-002": _decision(
                decision_status,
                [str(item["layout"]["bucket_count"]) for item in decision_layouts],
            ),
            "P-003": _decision(
                decision_status,
                [f"{item['layout']['target_file_mb']} MiB" for item in decision_layouts],
            ),
            "P-004": _decision(
                decision_status,
                sorted(
                    {
                        f"{item['layout']['compression']}-{item['layout']['compression_level']}"
                        for item in decision_layouts
                    }
                ),
            ),
            "P-005": _decision("owner-decision-required", [p005_value]),
        },
        "evidence_schema": "grid.gate1-review-pack/v2",
        "gate_1": {
            "automatic_promotion": False,
            "blockers": blockers,
            "owner_decision_required": True,
            "status": "pending-owner-decision",
        },
        "layout_candidates": candidates,
        "limitations": [
            "Single-symbol ten-year timings are linear projections from the observed reference "
            "row span, not direct ten-year scans.",
            "Real-market row width is a bounded current trade-price sample and is applied to mark "
            "rows only as a conservative like-width comparison.",
            "Storage projections exclude raw archives, features, outcomes, experiments, compaction "
            "headroom, filesystem overhead, and backup.",
            "Reboot separation reduces cache ambiguity but cannot prevent unrelated host reads.",
            "This pack cannot approve P-001 through P-005, close Gate 1, or authorize Phase 2.",
        ],
        "owner_decision_required": True,
        "reference_host_qualification": layout_host,
        "software": layout["software"],
        "sources": {
            "decision_layout": {
                key: decision_source[key]
                for key in ("artifact", "artifact_sha256", "schema", "status")
            },
            "feature": feature_source,
            "layout": layout_source,
            "qualification": qualification_source,
            "real_market": {
                key: real_market_source[key]
                for key in ("artifact", "artifact_sha256", "schema", "status")
            },
        },
        "status": "ready-for-owner-review" if ready else "blocked-by-reference-results",
    }
    Draft202012Validator(
        _schema(REVIEW_SCHEMA_V2),
        format_checker=FormatChecker(),
    ).validate(payload)
    return payload


def publish_qualified_review_pack(
    *,
    layout_path: Path,
    feature_path: Path,
    decision_path: Path,
    real_market_path: Path,
    qualification_path: Path,
    output: Path,
    force: bool = False,
    command: str | None = None,
) -> dict[str, Any]:
    """Publish the append-only ADR-0019 owner-review pack."""

    layout = load_verified_evidence(layout_path, LAYOUT_SCHEMA_V3)
    feature = load_verified_evidence(feature_path, FEATURE_SCHEMA_V3)
    decision = load_verified_evidence(decision_path, DECISION_SCHEMA)
    real_market = load_verified_evidence(real_market_path, REAL_MARKET_SCHEMA)
    qualification = load_verified_evidence(qualification_path, QUALIFICATION_SCHEMA)
    payload = build_qualified_review_pack(
        layout,
        feature,
        real_market,
        qualification,
        command=shlex.join(sys.argv) if command is None else command,
        real_market_path=real_market_path,
        qualification_path=qualification_path,
        layout_source=_source(layout_path, layout, "benchmark_schema"),
        feature_source=_source(feature_path, feature, "benchmark_schema"),
        decision_source=_source(decision_path, decision, "benchmark_schema"),
        real_market_source=_source(real_market_path, real_market, "evidence_schema"),
        qualification_source=_source(qualification_path, qualification, "evidence_schema"),
    )
    output, _receipt = preflight_evidence(output, force=force)
    publish_evidence(output, payload, force=force)
    return payload


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layout", type=Path, required=True)
    parser.add_argument("--feature", type=Path, required=True)
    parser.add_argument(
        "--decision",
        type=Path,
        default=Path("benchmarks/results/m1-layout-exact-decision-candidate.json"),
    )
    parser.add_argument(
        "--real-market",
        type=Path,
        default=Path("benchmarks/results/m1-real-market-layout-skew.json"),
    )
    parser.add_argument("--workstation", type=Path)
    parser.add_argument("--reference-host-qualification", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    admission_count = sum(
        path is not None for path in (args.workstation, args.reference_host_qualification)
    )
    if admission_count != 1:
        raise ValueError(
            "exactly one of --workstation or --reference-host-qualification is required"
        )
    if args.reference_host_qualification is not None:
        payload = publish_qualified_review_pack(
            layout_path=args.layout,
            feature_path=args.feature,
            decision_path=args.decision,
            real_market_path=args.real_market,
            qualification_path=args.reference_host_qualification,
            output=args.output,
            force=args.force,
        )
    else:
        payload = publish_review_pack(
            layout_path=args.layout,
            feature_path=args.feature,
            decision_path=args.decision,
            real_market_path=args.real_market,
            workstation_path=args.workstation,
            output=args.output,
            force=args.force,
        )
    return 0 if payload["status"] == "ready-for-owner-review" else 2


if __name__ == "__main__":
    raise SystemExit(main())
