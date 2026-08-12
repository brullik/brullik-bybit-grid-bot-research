"""Project measured M1 smoke/scaled evidence onto the documented capacity envelope."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Any

from grid_contracts.canonical import sha256_file
from grid_data.evidence import preflight_evidence, publish_evidence, verify_evidence

TRADE_ROWS = 3_681_644_400
TRADE_AND_MARK_ROWS = 7_363_288_800
PLANNING_BYTES_PER_ROW = (24, 40, 64)


def load_verified_evidence(path: Path) -> dict[str, Any]:
    path = path.resolve()
    if not verify_evidence(path):
        raise ValueError(f"source evidence or receipt does not verify: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"source evidence is not a JSON object: {path}")
    return payload


def decimal_metric(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000000001")), "f")


def projected_bytes(rows: int, bytes_per_row: Decimal) -> int:
    return int((Decimal(rows) * bytes_per_row).to_integral_value(rounding=ROUND_CEILING))


def layout_projection(layout: dict[str, Any]) -> list[dict[str, Any]]:
    row_count = int(layout["input"]["row_count"])
    projections: list[dict[str, Any]] = []
    for result in layout["results"]:
        measured_bytes = int(result["write"]["bytes"])
        bytes_per_row = Decimal(measured_bytes) / Decimal(row_count)
        projections.append(
            {
                "layout": result["layout"],
                "observed_bytes_per_row": decimal_metric(bytes_per_row),
                "projected_trade_and_mark_bytes": projected_bytes(
                    TRADE_AND_MARK_ROWS, bytes_per_row
                ),
                "projected_trade_bytes": projected_bytes(TRADE_ROWS, bytes_per_row),
            }
        )
    return projections


def feature_projection(feature: dict[str, Any]) -> dict[str, Any]:
    throughput = Decimal(feature["result"]["throughput_core_rows_per_second"])
    return {
        "observed_core_rows_per_second": decimal_metric(throughput),
        "projected_trade_and_mark_seconds": decimal_metric(
            Decimal(TRADE_AND_MARK_ROWS) / throughput
        ),
        "projected_trade_seconds": decimal_metric(Decimal(TRADE_ROWS) / throughput),
    }


def planning_envelopes() -> list[dict[str, int]]:
    return [
        {
            "bytes_per_row": bytes_per_row,
            "trade_and_mark_bytes": TRADE_AND_MARK_ROWS * bytes_per_row,
            "trade_bytes": TRADE_ROWS * bytes_per_row,
        }
        for bytes_per_row in PLANNING_BYTES_PER_ROW
    ]


def provenance(path: Path) -> dict[str, str]:
    resolved = path.resolve()
    return {"artifact": resolved.name, "artifact_sha256": sha256_file(resolved)}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--layout", type=Path, default=Path("benchmarks/results/m1-layout-smoke.json")
    )
    parser.add_argument(
        "--feature", type=Path, default=Path("benchmarks/results/m1-feature-scaled.json")
    )
    parser.add_argument(
        "--workstation",
        type=Path,
        default=Path("benchmarks/results/m1-workstation-snapshot.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    output, _receipt = preflight_evidence(args.output, force=args.force)
    layout = load_verified_evidence(args.layout)
    feature = load_verified_evidence(args.feature)
    workstation = load_verified_evidence(args.workstation)
    if layout.get("status") != "smoke-only" or feature.get("status") != "scaled-only":
        raise ValueError("this projection requires explicitly smoke/scaled source evidence")

    payload = {
        "capacity": {
            "theoretical_trade_and_mark_rows": TRADE_AND_MARK_ROWS,
            "theoretical_trade_rows": TRADE_ROWS,
        },
        "command": shlex.join(sys.argv),
        "evidence_schema": "grid.capacity-projection/v1",
        "feature_runtime_linear_projection": feature_projection(feature),
        "layout_synthetic_linear_projections": layout_projection(layout),
        "limitations": [
            "Layout input is a small, highly regular synthetic smoke dataset.",
            "Feature runtime is a linear projection from a 9,999,500-row synthetic scaled run.",
            "Projections exclude ingestion, Parquet feature publication, audits, compaction, "
            "concurrency, backup, filesystem overhead, and real-market skew.",
            "The result cannot decide P-001 through P-005 or close Gate 1.",
        ],
        "planning_storage_envelopes": planning_envelopes(),
        "provenance": {
            "feature": provenance(args.feature),
            "layout": provenance(args.layout),
            "workstation": provenance(args.workstation),
        },
        "recommendation": {
            "backup_capacity": "sized separately from the research volume",
            "cpu": "16-32 physical/high-performance cores",
            "nvme_bytes_minimum": 2 * 1024**4,
            "ram_bytes_range": [64 * 1024**3, 128 * 1024**3],
            "status": "provisional-until-reference-benchmark-and-owner-acceptance",
        },
        "source_workstation_status": workstation["status"],
        "status": "provisional-scaled-extrapolation",
    }
    publish_evidence(output, payload, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
