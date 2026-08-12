"""Project exact v3 layout candidates onto the documented capacity envelope."""

from __future__ import annotations

import argparse
import shlex
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from grid_contracts.canonical import canonical_sha256
from grid_data.evidence import preflight_evidence, publish_evidence

from benchmarks.capacity_projection import (
    TRADE_AND_MARK_ROWS,
    TRADE_ROWS,
    decimal_metric,
    feature_projection,
    layout_projection,
    load_verified_evidence,
    planning_envelopes,
    projected_bytes,
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


def real_market_layout_projections(
    layout: dict[str, Any], real_market: dict[str, Any], *, layout_sha256: str
) -> list[dict[str, Any]]:
    if (
        real_market.get("evidence_schema") != "grid.real-market-layout-skew/v1"
        or real_market.get("status") != "complete-bounded-real-market-skew"
    ):
        raise ValueError("real-market projection requires complete v1 skew evidence")
    content = dict(real_market)
    embedded_hash = content.pop("content_sha256", None)
    if not isinstance(embedded_hash, str) or embedded_hash != canonical_sha256(content):
        raise ValueError("real-market skew evidence content hash does not verify")
    if real_market.get("decision_evidence", {}).get("artifact_sha256") != layout_sha256:
        raise ValueError(
            "real-market skew evidence does not reference the selected layout evidence"
        )
    synthetic = {
        tuple(sorted(item["layout"].items())): item for item in selected_layout_projections(layout)
    }
    raw_results = real_market.get("layouts")
    if not isinstance(raw_results, list) or len(raw_results) != 2:
        raise ValueError("real-market skew evidence must contain two layouts")
    observed_row_count = real_market.get("total_row_count")
    if not isinstance(observed_row_count, int) or observed_row_count <= 0:
        raise ValueError("real-market skew evidence row count is invalid")
    projections = []
    logical_hashes = set()
    for result in raw_results:
        candidate = result.get("layout") if isinstance(result, dict) else None
        if not isinstance(candidate, dict):
            raise ValueError("real-market layout is malformed")
        selected = synthetic.get(tuple(sorted(candidate.items())))
        if selected is None or result.get("exact_schema_verified") is not True:
            raise ValueError("real-market layout is not an exact selected candidate")
        logical_summary = result.get("logical_summary")
        if not isinstance(logical_summary, dict):
            raise ValueError("real-market layout has no logical summary")
        logical_hashes.add(logical_summary.get("logical_sha256"))
        if logical_summary.get("row_count") != observed_row_count:
            raise ValueError("real-market layout row count does not match its artifact")
        real_bytes_per_row = Decimal(result["bytes_per_row"])
        if not real_bytes_per_row.is_finite() or real_bytes_per_row <= 0:
            raise ValueError("real-market bytes per row must be positive and finite")
        synthetic_bytes_per_row = Decimal(selected["observed_bytes_per_row"])
        projections.append(
            {
                "layout": candidate,
                "observed_real_bytes_per_row": decimal_metric(real_bytes_per_row),
                "observed_real_row_count": observed_row_count,
                "projected_trade_and_mark_bytes_at_trade_row_width": projected_bytes(
                    TRADE_AND_MARK_ROWS, real_bytes_per_row
                ),
                "projected_trade_bytes": projected_bytes(TRADE_ROWS, real_bytes_per_row),
                "real_to_synthetic_bytes_per_row_ratio": decimal_metric(
                    real_bytes_per_row / synthetic_bytes_per_row
                ),
                "synthetic_bytes_per_row": decimal_metric(synthetic_bytes_per_row),
            }
        )
    if len(projections) != 2 or len(logical_hashes) != 1 or None in logical_hashes:
        raise ValueError("real-market layouts must preserve one exact logical result")
    return projections


def build_projection_v3(
    layout: dict[str, Any],
    feature: dict[str, Any],
    workstation: dict[str, Any],
    real_market: dict[str, Any],
    *,
    command: str,
    sources: dict[str, dict[str, str]],
) -> dict[str, Any]:
    if "real_market" not in sources:
        raise ValueError("v3 capacity projection requires real-market provenance")
    payload = build_projection(
        layout,
        feature,
        workstation,
        command=command,
        sources={key: value for key, value in sources.items() if key != "real_market"},
    )
    payload["evidence_schema"] = "grid.capacity-projection/v3"
    payload["limitations"] = [
        (
            "Real-market bytes per row come from eight current-liquid, price-stratified "
            "contracts over seven days and cannot represent all historical regimes."
        ),
        (
            "The trade-and-mark comparison applies the wider trade-row layout to both row sets; "
            "mark-price rows omit volume and turnover and require a separate physical estimate."
        ),
        (
            "The decision and feature matrices ran on a below-reference workstation without "
            "the reboot-separated reference protocol."
        ),
        (
            "Projections exclude ingestion, audits, compaction headroom, concurrency, backup, "
            "filesystem overhead, raw archives, derived stores, and experiments."
        ),
        (
            "Observed real-market compression does not replace the independent 24/40/64-byte "
            "planning envelopes or provisional 2 TiB recommendation."
        ),
        "The result cannot self-approve P-001 through P-005 or Gate 1.",
    ]
    payload["provenance"] = sources
    payload["real_market_layout_projections"] = real_market_layout_projections(
        layout,
        real_market,
        layout_sha256=sources["layout"]["artifact_sha256"],
    )
    payload["status"] = "provisional-real-market-calibrated-extrapolation"
    return payload


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
    parser.add_argument(
        "--real-market",
        type=Path,
        default=Path("benchmarks/results/m1-real-market-layout-skew.json"),
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
    real_market = load_verified_evidence(args.real_market)
    sources = {
        "feature": provenance(args.feature),
        "layout": provenance(args.layout),
        "real_market": provenance(args.real_market),
        "workstation": provenance(args.workstation),
    }
    payload = build_projection_v3(
        layout,
        feature,
        workstation,
        real_market,
        command=shlex.join(sys.argv),
        sources=sources,
    )
    publish_evidence(output, payload, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
