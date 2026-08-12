"""Project exact v3 layout candidates onto the documented capacity envelope."""

from __future__ import annotations

import argparse
import shlex
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from grid_data.evidence import preflight_evidence, publish_evidence

from benchmarks.capacity_projection import (
    TRADE_AND_MARK_ROWS,
    TRADE_ROWS,
    decimal_metric,
    feature_projection,
    layout_projection,
    load_verified_evidence,
    planning_envelopes,
    provenance,
)


def selected_layout_projections(layout: dict[str, Any]) -> list[dict[str, Any]]:
    shortlist = layout["decision"]["reference_rerun_shortlist"]
    by_layout = {tuple(sorted(result["layout"].items())): result for result in layout["results"]}
    selected: list[dict[str, Any]] = []
    row_count = int(layout["input"]["row_count"])
    for candidate in shortlist:
        result = by_layout.get(tuple(sorted(candidate.items())))
        if result is None:
            raise ValueError("decision shortlist references a missing layout result")
        write = result["write"]
        if write.get("numeric_schema_verified") is not True or not write.get(
            "target_file_exercised"
        ):
            raise ValueError("decision shortlist references an ineligible layout")
        write_seconds = Decimal(write["write_seconds"])
        rows_per_second = Decimal(row_count) / write_seconds
        projection = layout_projection({"input": {"row_count": row_count}, "results": [result]})[0]
        projection.update(
            {
                "observed_write_rows_per_second": decimal_metric(rows_per_second),
                "projected_trade_and_mark_write_seconds": decimal_metric(
                    Decimal(TRADE_AND_MARK_ROWS) / rows_per_second
                ),
                "projected_trade_write_seconds": decimal_metric(
                    Decimal(TRADE_ROWS) / rows_per_second
                ),
            }
        )
        selected.append(projection)
    if len(selected) != 2:
        raise ValueError("exact capacity projection requires two bucket-count shortlist entries")
    return selected


def build_projection(
    layout: dict[str, Any],
    feature: dict[str, Any],
    workstation: dict[str, Any],
    *,
    command: str,
    sources: dict[str, dict[str, str]],
) -> dict[str, Any]:
    if (
        layout.get("benchmark_schema") != "grid.layout-benchmark/v3"
        or layout.get("profile") != "decision"
        or layout.get("status") != "decision-matrix-candidate"
    ):
        raise ValueError("exact projection requires eligible v3 decision evidence")
    if feature.get("status") != "reference-scale-candidate":
        raise ValueError("exact projection requires reference-scale feature evidence")
    if not isinstance(workstation.get("status"), str):
        raise ValueError("workstation evidence has no status")
    return {
        "capacity": {
            "theoretical_trade_and_mark_rows": TRADE_AND_MARK_ROWS,
            "theoretical_trade_rows": TRADE_ROWS,
        },
        "command": command,
        "evidence_schema": "grid.capacity-projection/v2",
        "feature_runtime_linear_projection": feature_projection(feature),
        "limitations": [
            (
                "Exact layout input is deterministic synthetic data and can compress more "
                "than real market data."
            ),
            (
                "The decision matrix ran on a below-reference workstation without a "
                "forced cold cache."
            ),
            (
                "Linear projections exclude ingestion, audits, compaction, concurrency, "
                "backup, filesystem overhead, raw archives, derived stores, and "
                "real-market skew."
            ),
            (
                "Observed exact-layout projections do not replace the independent "
                "24/40/64-byte planning envelopes."
            ),
            (
                "The result shortlists a reference-hardware rerun and cannot self-approve "
                "P-001 through P-005 or Gate 1."
            ),
        ],
        "planning_storage_envelopes": planning_envelopes(),
        "provenance": sources,
        "recommendation": {
            "backup_capacity": "sized separately from the research volume",
            "cpu": "16-32 physical/high-performance cores",
            "nvme_bytes_minimum": 2 * 1024**4,
            "ram_bytes_range": [64 * 1024**3, 128 * 1024**3],
            "status": "provisional-until-reference-benchmark-and-owner-acceptance",
        },
        "selected_exact_layout_projections": selected_layout_projections(layout),
        "source_workstation_status": workstation["status"],
        "status": "provisional-exact-decision-extrapolation",
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--layout",
        type=Path,
        default=Path("benchmarks/results/m1-layout-exact-decision-candidate.json"),
    )
    parser.add_argument(
        "--feature",
        type=Path,
        default=Path("benchmarks/results/m1-feature-reference-candidate.json"),
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
    sources = {
        "feature": provenance(args.feature),
        "layout": provenance(args.layout),
        "workstation": provenance(args.workstation),
    }
    payload = build_projection(
        layout,
        feature,
        workstation,
        command=shlex.join(sys.argv),
        sources=sources,
    )
    publish_evidence(output, payload, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
