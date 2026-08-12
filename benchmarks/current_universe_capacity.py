"""Project the current Bybit lifecycle envelope onto measured M1 storage evidence."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_data.evidence import preflight_evidence, publish_evidence, verify_evidence
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

from benchmarks.workstation_snapshot import volume_root_for_path

ROOT = Path(__file__).resolve().parents[1]
HISTORY_SCHEMA = (
    ROOT / "schemas" / "evidence" / "v1" / "bybit-history-source-assessment.schema.json"
)
CAPACITY_SCHEMA = ROOT / "schemas" / "evidence" / "v3" / "capacity-projection.schema.json"
WORKSTATION_SCHEMA = ROOT / "schemas" / "evidence" / "v1" / "workstation-snapshot.schema.json"
OUTPUT_SCHEMA = ROOT / "schemas" / "evidence" / "v1" / "current-universe-capacity.schema.json"
MINUTES_PER_DAY = 1_440
MAXIMUM_PARTITION_DAYS = 31
FUTURE_CLOCK_TOLERANCE = timedelta(minutes=5)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"evidence is not valid JSON: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"evidence is not a JSON object: {path}")
    return payload


def _validate(payload: dict[str, Any], schema_path: Path, *, label: str) -> None:
    try:
        Draft202012Validator(
            _load_json(schema_path),
            format_checker=FormatChecker(),
        ).validate(payload)
    except Exception as error:
        raise ValueError(f"{label} does not match {schema_path.name}") from error


def load_verified_evidence(path: Path, schema_path: Path) -> dict[str, Any]:
    """Verify a receipt and then the full versioned evidence contract."""

    resolved = path.resolve()
    if not verify_evidence(resolved):
        raise ValueError(f"source evidence receipt does not verify: {resolved}")
    payload = _load_json(resolved)
    _validate(payload, schema_path, label=str(resolved))
    return payload


def _verify_history_content(history: dict[str, Any]) -> None:
    content = dict(history)
    embedded_hash = content.pop("content_sha256", None)
    if not isinstance(embedded_hash, str) or embedded_hash != canonical_sha256(content):
        raise ValueError("history-source assessment content hash does not verify")


def _decimal(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"{label} is not an exact decimal") from error
    if not result.is_finite() or result < 0:
        raise ValueError(f"{label} must be finite and non-negative")
    return result


def _metric(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000000001")), "f")


def _projected_bytes(rows: int, bytes_per_row: Decimal) -> int:
    return int((Decimal(rows) * bytes_per_row).to_integral_value(rounding=ROUND_CEILING))


def _projection_matches(observed: object, expected: int, rows: int) -> bool:
    """Allow only the error implied by a bytes/row metric rounded to nine decimals."""

    if not isinstance(observed, int):
        return False
    rounding_bound = int(
        (Decimal(rows) * Decimal("0.0000000005")).to_integral_value(rounding=ROUND_CEILING)
    )
    return abs(observed - expected) <= rounding_bound


def _parse_time(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a UTC offset")
    return parsed.astimezone(UTC)


def _freshness(
    observed_at: object,
    *,
    generated_at: datetime,
    max_age_hours: int,
    label: str,
) -> dict[str, Any]:
    observed = _parse_time(observed_at, label)
    if observed > generated_at + FUTURE_CLOCK_TOLERANCE:
        raise ValueError(f"{label} is in the future")
    age = max(timedelta(), generated_at - observed)
    maximum_age = timedelta(hours=max_age_hours)
    if age > maximum_age:
        raise ValueError(f"{label} is stale: age exceeds {max_age_hours} hours")
    return {
        "age_hours": _metric(Decimal(str(age.total_seconds())) / Decimal(3_600)),
        "observed_at_utc": observed.isoformat().replace("+00:00", "Z"),
    }


def _source(
    path: Path,
    payload: dict[str, Any],
    *,
    schema_key: str,
    observed_at: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "artifact": path.resolve().name,
        "artifact_sha256": sha256_file(path.resolve()),
        "schema": payload[schema_key],
        "status": payload["status"],
    }
    if observed_at is not None:
        result["observed_at_utc"] = observed_at
    return result


def _layout_key(layout: dict[str, Any]) -> str:
    return json.dumps(layout, sort_keys=True, separators=(",", ":"))


def _scenario(identifier: str, required_bytes: int, free_bytes: int) -> dict[str, Any]:
    if required_bytes <= 0 or free_bytes <= 0:
        raise ValueError("disk scenario requires positive required and free bytes")
    fits = required_bytes <= free_bytes
    return {
        "fits_observed_free": fits,
        "id": identifier,
        "remaining_bytes": free_bytes - required_bytes if fits else 0,
        "required_bytes": required_bytes,
        "required_percent_of_observed_free": _metric(
            Decimal(required_bytes) * Decimal(100) / Decimal(free_bytes)
        ),
        "shortfall_bytes": 0 if fits else required_bytes - free_bytes,
    }


def _layout_projections(
    capacity: dict[str, Any],
    *,
    per_dataset_rows: int,
    active_instruments: int,
) -> list[dict[str, Any]]:
    formal_trade_rows = int(capacity["capacity"]["theoretical_trade_rows"])
    formal_combined_rows = int(capacity["capacity"]["theoretical_trade_and_mark_rows"])
    synthetic = {
        _layout_key(item["layout"]): item for item in capacity["selected_exact_layout_projections"]
    }
    real = {
        _layout_key(item["layout"]): item for item in capacity["real_market_layout_projections"]
    }
    if synthetic.keys() != real.keys() or len(synthetic) != 2:
        raise ValueError("capacity evidence does not bind the same two synthetic/real layouts")

    combined_rows = per_dataset_rows * 2
    daily_rows = active_instruments * MINUTES_PER_DAY * 2
    maximum_partition_rows = daily_rows * MAXIMUM_PARTITION_DAYS
    projections: list[dict[str, Any]] = []
    for key in sorted(synthetic):
        synthetic_item = synthetic[key]
        real_item = real[key]
        synthetic_bpr = _decimal(synthetic_item["observed_bytes_per_row"], "synthetic bpr")
        real_bpr = _decimal(real_item["observed_real_bytes_per_row"], "real-market bpr")
        if synthetic_bpr <= 0 or real_bpr <= 0:
            raise ValueError("capacity bytes-per-row metrics must be positive")
        if _decimal(real_item["synthetic_bytes_per_row"], "real-market synthetic bpr") != (
            synthetic_bpr
        ):
            raise ValueError("real-market projection is not bound to its synthetic layout metric")
        expected_values = (
            (
                synthetic_item["projected_trade_bytes"],
                _projected_bytes(formal_trade_rows, synthetic_bpr),
                formal_trade_rows,
            ),
            (
                synthetic_item["projected_trade_and_mark_bytes"],
                _projected_bytes(formal_combined_rows, synthetic_bpr),
                formal_combined_rows,
            ),
            (
                real_item["projected_trade_bytes"],
                _projected_bytes(formal_trade_rows, real_bpr),
                formal_trade_rows,
            ),
            (
                real_item["projected_trade_and_mark_bytes_at_trade_row_width"],
                _projected_bytes(formal_combined_rows, real_bpr),
                formal_combined_rows,
            ),
        )
        if any(
            not _projection_matches(observed, expected, rows)
            for observed, expected, rows in expected_values
        ):
            raise ValueError("capacity projection bytes do not match their rows and exact metrics")
        projections.append(
            {
                "bootstrap": {
                    "current_trade_and_mark_bytes_real_width": _projected_bytes(
                        combined_rows, real_bpr
                    ),
                    "current_trade_and_mark_bytes_synthetic": _projected_bytes(
                        combined_rows, synthetic_bpr
                    ),
                    "current_trade_bytes_real_width": _projected_bytes(per_dataset_rows, real_bpr),
                    "current_trade_bytes_synthetic": _projected_bytes(
                        per_dataset_rows, synthetic_bpr
                    ),
                },
                "incremental": {
                    "maximum_31_day_partition_bytes_real_width": _projected_bytes(
                        maximum_partition_rows, real_bpr
                    ),
                    "maximum_31_day_partition_bytes_synthetic": _projected_bytes(
                        maximum_partition_rows, synthetic_bpr
                    ),
                    "one_day_bytes_real_width": _projected_bytes(daily_rows, real_bpr),
                    "one_day_bytes_synthetic": _projected_bytes(daily_rows, synthetic_bpr),
                },
                "layout": synthetic_item["layout"],
                "observed_real_bytes_per_row": _metric(real_bpr),
                "synthetic_bytes_per_row": _metric(synthetic_bpr),
            }
        )
    return projections


def build_projection(
    history: dict[str, Any],
    capacity: dict[str, Any],
    workstation: dict[str, Any],
    *,
    command: str,
    generated_at: datetime,
    max_source_age_hours: int,
    source_paths: dict[str, Path],
) -> dict[str, Any]:
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    generated_at = generated_at.astimezone(UTC)
    if not 1 <= max_source_age_hours <= 168:
        raise ValueError("max_source_age_hours must be in [1, 168]")
    _verify_history_content(history)
    if capacity.get("status") != "provisional-real-market-calibrated-extrapolation":
        raise ValueError("current-universe projection requires v3 real-market capacity evidence")

    history_freshness = _freshness(
        history["fetched_at_utc"],
        generated_at=generated_at,
        max_age_hours=max_source_age_hours,
        label="history fetched_at_utc",
    )
    workstation_freshness = _freshness(
        workstation["observed_at_utc"],
        generated_at=generated_at,
        max_age_hours=max_source_age_hours,
        label="workstation observed_at_utc",
    )
    estimate = history["inventory_backfill_estimate"]
    per_dataset_rows = int(estimate["mark_price_1m"]["estimated_rows"])
    theoretical_rows = int(capacity["capacity"]["theoretical_trade_and_mark_rows"])
    if per_dataset_rows <= 0 or theoretical_rows <= 0:
        raise ValueError("lifecycle and theoretical row estimates must be positive")
    combined_rows = per_dataset_rows * 2
    if combined_rows > theoretical_rows:
        raise ValueError("current lifecycle estimate exceeds the formal capacity envelope")

    statuses = estimate["status_counts"]
    active_instruments = int(statuses.get("Trading", 0))
    universe_records = int(estimate["usdt_linear_perpetual_records"])
    if sum(int(value) for value in statuses.values()) != universe_records:
        raise ValueError("history status counts do not sum to the current universe")
    if active_instruments <= 0 or active_instruments > universe_records:
        raise ValueError("current lifecycle estimate has no Trading instruments")
    layout_projections = _layout_projections(
        capacity,
        per_dataset_rows=per_dataset_rows,
        active_instruments=active_instruments,
    )
    real_bootstrap_upper = max(
        item["bootstrap"]["current_trade_and_mark_bytes_real_width"] for item in layout_projections
    )
    real_daily_upper = max(
        item["incremental"]["one_day_bytes_real_width"] for item in layout_projections
    )
    real_partition_upper = max(
        item["incremental"]["maximum_31_day_partition_bytes_real_width"]
        for item in layout_projections
    )
    free_bytes = int(workstation["hardware"]["volume_free_bytes"])
    if free_bytes <= 0:
        raise ValueError("workstation snapshot has no observed free disk headroom")
    scenarios = [
        _scenario("bootstrap-canonical-building", real_bootstrap_upper, free_bytes),
        _scenario(
            "full-rebuild-active-plus-building",
            real_bootstrap_upper * 2,
            free_bytes,
        ),
        _scenario("incremental-one-day", real_daily_upper, free_bytes),
        _scenario("incremental-maximum-31-day-partition", real_partition_upper, free_bytes),
        _scenario(
            "planning-64-byte-active-plus-building",
            combined_rows * 64 * 2,
            free_bytes,
        ),
    ]
    measured_ids = {
        "bootstrap-canonical-building",
        "full-rebuild-active-plus-building",
        "incremental-one-day",
        "incremental-maximum-31-day-partition",
    }
    measured_fit = all(
        scenario["fits_observed_free"] for scenario in scenarios if scenario["id"] in measured_ids
    )
    planning_fit = next(
        scenario["fits_observed_free"]
        for scenario in scenarios
        if scenario["id"] == "planning-64-byte-active-plus-building"
    )

    payload = {
        "command": command,
        "disk_headroom": {
            "measured_canonical_scenarios_fit": measured_fit,
            "planning_64_byte_rebuild_scenario_fits": planning_fit,
            "raw_source_archives": {
                "measured": False,
                "safe_full_bootstrap_conclusion": False,
                "status": "unknown-headroom-requires-downloader-preflight",
            },
            "scenarios": scenarios,
            "volume": {
                key: workstation["hardware"][key]
                for key in (
                    "storage_kind",
                    "storage_model",
                    "volume_free_bytes",
                    "volume_root",
                    "volume_total_bytes",
                )
            },
        },
        "evidence_schema": "grid.current-universe-capacity/v1",
        "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
        "incremental_projection": {
            "active_trading_instruments": active_instruments,
            "maximum_partition_days": MAXIMUM_PARTITION_DAYS,
            "maximum_partition_trade_and_mark_rows": (
                active_instruments * MINUTES_PER_DAY * 2 * MAXIMUM_PARTITION_DAYS
            ),
            "one_day_trade_and_mark_rows": active_instruments * MINUTES_PER_DAY * 2,
        },
        "layout_projections": layout_projections,
        "limitations": [
            (
                "Lifecycle rows use current launch/delivery metadata and are an estimate, not a "
                "downloaded gap-audited corpus."
            ),
            (
                "The current inventory remains partial because Bybit rejected the documented "
                "Settling status filter."
                if history["inventory_source"]["inventory_status"] == "partial"
                else "Current instrument metadata is not a dated historical universe registry."
            ),
            (
                "Trade rows are assumed to share the mark lifecycle-minute count; actual archive "
                "availability and candle gaps can reduce it."
            ),
            (
                "Real-market bytes per row come from a bounded seven-day sample and apply the "
                "wider trade schema to mark rows."
            ),
            (
                "Bootstrap canonical-building excludes compressed tick-trade archives, download "
                "staging, HTTP retry fragments, filesystem overhead, and backup."
            ),
            (
                "Incremental projections assume only current Trading instruments and bound one "
                "rewritten calendar partition to 31 days."
            ),
            (
                "A normal update appends closed intervals and repairs detected gaps; it must not "
                "rescan or replace unaffected immutable partitions."
            ),
            (
                "This evidence does not implement or authorize sync-history, select P-001 through "
                "P-005, close Gate 1, or open Phase 2."
            ),
        ],
        "parameters": {
            "maximum_partition_days": MAXIMUM_PARTITION_DAYS,
            "max_source_age_hours": max_source_age_hours,
            "minutes_per_day": MINUTES_PER_DAY,
        },
        "sources": {
            "capacity": _source(source_paths["capacity"], capacity, schema_key="evidence_schema"),
            "history": _source(
                source_paths["history"],
                history,
                schema_key="evidence_schema",
                observed_at=history_freshness["observed_at_utc"],
            ),
            "workstation": _source(
                source_paths["workstation"],
                workstation,
                schema_key="evidence_schema",
                observed_at=workstation_freshness["observed_at_utc"],
            ),
        },
        "source_freshness": {
            "history": history_freshness,
            "workstation": workstation_freshness,
        },
        "status": "provisional-current-universe-capacity",
        "universe": {
            "current_interval_funding_events": estimate["current_interval_funding"][
                "estimated_events"
            ],
            "current_interval_funding_requests": estimate["current_interval_funding"][
                "estimated_requests"
            ],
            "formal_trade_and_mark_capacity_rows": theoretical_rows,
            "horizon_end_ms": estimate["horizon_end_ms"],
            "horizon_start_ms": estimate["horizon_start_ms"],
            "instruments_with_observed_duration": estimate["instruments_with_observed_duration"],
            "lifecycle_per_dataset_rows": per_dataset_rows,
            "lifecycle_trade_and_mark_rows_at_equal_coverage": combined_rows,
            "share_of_formal_trade_and_mark_capacity_percent": _metric(
                Decimal(combined_rows) * Decimal(100) / Decimal(theoretical_rows)
            ),
            "status_counts": statuses,
            "usdt_linear_perpetual_records": universe_records,
        },
    }
    _validate(payload, OUTPUT_SCHEMA, label="current-universe capacity payload")
    return payload


def publish_current_universe_projection(
    *,
    history_path: Path,
    capacity_path: Path,
    workstation_path: Path,
    output: Path,
    command: str,
    generated_at: datetime | None = None,
    max_source_age_hours: int = 24,
    force: bool = False,
) -> dict[str, Any]:
    """Validate every source before atomically replacing an optional prior projection."""

    history = load_verified_evidence(history_path, HISTORY_SCHEMA)
    capacity = load_verified_evidence(capacity_path, CAPACITY_SCHEMA)
    workstation = load_verified_evidence(workstation_path, WORKSTATION_SCHEMA)
    expected_volume = Path(workstation["hardware"]["volume_root"]).resolve()
    actual_volume = volume_root_for_path(output)
    if os.path.normcase(str(actual_volume)) != os.path.normcase(str(expected_volume)):
        raise ValueError(
            "workstation free-space evidence does not describe the output volume: "
            f"expected {expected_volume}, got {actual_volume}"
        )
    payload = build_projection(
        history,
        capacity,
        workstation,
        command=command,
        generated_at=generated_at or datetime.now(UTC),
        max_source_age_hours=max_source_age_hours,
        source_paths={
            "capacity": capacity_path,
            "history": history_path,
            "workstation": workstation_path,
        },
    )
    resolved_output, _receipt = preflight_evidence(output, force=force)
    publish_evidence(resolved_output, payload, force=force)
    return payload


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history-source", type=Path, required=True)
    parser.add_argument(
        "--capacity",
        type=Path,
        default=Path("benchmarks/results/m1-real-market-capacity-projection.json"),
    )
    parser.add_argument("--workstation", type=Path, required=True)
    parser.add_argument("--max-source-age-hours", type=int, default=24)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    publish_current_universe_projection(
        history_path=args.history_source,
        capacity_path=args.capacity,
        workstation_path=args.workstation,
        output=args.output,
        command=shlex.join(sys.argv),
        generated_at=datetime.now(UTC),
        max_source_age_hours=args.max_source_age_hours,
        force=args.force,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
