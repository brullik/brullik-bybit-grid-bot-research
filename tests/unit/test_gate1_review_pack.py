from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from grid_contracts.canonical import sha256_file
from grid_data.evidence import publish_evidence, verify_evidence

from benchmarks.gate1_review_pack import publish_qualified_review_pack, publish_review_pack
from benchmarks.measured_host_qualification import qualification_summary

ROW_COUNT = 99_999_900
INSTRUMENTS = 700
SINGLE_ROWS = 142_857
UNIVERSE_MONTH_ROWS = 31_248_000
SOFTWARE = {
    "duckdb": "1.4.3",
    "polars": "1.43.2",
    "psutil": "7.2.2",
    "pyarrow": "22.0.0",
    "python": "3.12.11",
}
FEATURE_COLUMNS = [
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
]
ROOT = Path(__file__).resolve().parents[2]
DECISION_PATH = ROOT / "benchmarks" / "results" / "m1-layout-exact-decision-candidate.json"
REAL_MARKET_PATH = ROOT / "benchmarks" / "results" / "m1-real-market-layout-skew.json"
QUALIFICATION_PATH = (
    ROOT / "benchmarks" / "results" / "m1-owner-measured-host-qualification-20260812.json"
)


def host_summary(*, artifact_hash: str = "a" * 64) -> dict[str, Any]:
    return {
        "artifact": "reference-host.json",
        "artifact_sha256": artifact_hash,
        "evidence_schema": "grid.workstation-snapshot/v1",
        "hardware": {
            "cpu_count_logical": 32,
            "cpu_count_physical": 16,
            "cpu_model": "Reference CPU",
            "machine": "x86_64",
            "platform": "Reference Linux",
            "ram_bytes": 64 * 1024**3,
            "storage_kind": "nvme",
            "storage_model": "Reference NVMe",
            "volume_root": "/mnt/reference",
            "volume_total_bytes": 2 * 1024**4,
        },
        "observed_at_utc": "2026-08-12T00:00:00Z",
        "status": "meets-documented-full-research-profile",
    }


def workstation_payload() -> dict[str, Any]:
    hardware = {
        **host_summary()["hardware"],
        "volume_free_bytes": 1024**4,
    }
    return {
        "assessment": {
            "documented_full_research_profile": {
                "meets": True,
                "observed_shortfalls": [],
                "requirements": {
                    "minimum_physical_cores": 16,
                    "minimum_ram_bytes": 64 * 1024**3,
                    "minimum_volume_bytes": 2 * 1024**4,
                    "storage_kind": "nvme",
                },
            },
            "documented_local_feasibility_profile": {
                "meets": True,
                "observed_shortfalls": [],
                "requirements": {
                    "minimum_physical_cores": 8,
                    "minimum_ram_bytes": 32 * 1024**3,
                    "minimum_volume_bytes": 1024**4,
                    "storage_kind": "nvme",
                },
            },
        },
        "command": "workstation snapshot",
        "evidence_schema": "grid.workstation-snapshot/v1",
        "hardware": hardware,
        "observed_at_utc": "2026-08-12T00:00:00Z",
        "recommendation": ["reference host", "separate backup", "owner review"],
        "software": {"psutil": SOFTWARE["psutil"], "python": SOFTWARE["python"]},
        "status": "meets-documented-full-research-profile",
    }


def decision_summary() -> dict[str, Any]:
    payload = json.loads(DECISION_PATH.read_text(encoding="utf-8"))
    return {
        "artifact": DECISION_PATH.name,
        "artifact_sha256": sha256_file(DECISION_PATH),
        "benchmark_schema": payload["benchmark_schema"],
        "status": payload["status"],
    }


def real_market_summary() -> dict[str, Any]:
    payload = json.loads(REAL_MARKET_PATH.read_text(encoding="utf-8"))
    return {
        "artifact": REAL_MARKET_PATH.name,
        "artifact_sha256": sha256_file(REAL_MARKET_PATH),
        "evidence_schema": payload["evidence_schema"],
        "layouts": [
            {key: item[key] for key in ("bytes_per_row", "layout", "total_bytes", "tree_sha256")}
            for item in payload["layouts"]
        ],
        "source_content_sha256": payload["source_content_sha256"],
        "total_row_count": payload["total_row_count"],
    }


def basic_hardware(host: dict[str, Any]) -> dict[str, Any]:
    return {
        key: host["hardware"][key]
        for key in (
            "cpu_count_logical",
            "cpu_count_physical",
            "machine",
            "platform",
            "ram_bytes",
        )
    }


def layout(bucket_count: int) -> dict[str, Any]:
    return {
        "bucket_count": bucket_count,
        "compression": "zstd",
        "compression_level": 3,
        "numeric_representation": "hybrid_int64_decimal",
        "target_file_mb": 32 if bucket_count == 4 else 16,
    }


def dataset(candidate: dict[str, Any]) -> dict[str, Any]:
    bucket_count = candidate["bucket_count"]
    return {
        "dataset_path": f"datasets/candidate-{bucket_count}",
        "layout": candidate,
        "maintenance": {
            "compaction": {
                "elapsed_seconds": "2.000000000",
                "input_fragment_count": 8,
                "numeric_schema_verified": True,
                "row_count": 1_000_000,
            },
            "logical_parity_verified": True,
            "repair": {
                "elapsed_seconds": "1.000000000",
                "numeric_schema_verified": True,
                "row_count": 1_000_000,
            },
            "source_tree_unchanged": True,
        },
        "manifest": {
            "file_count": bucket_count,
            "total_bytes": ROW_COUNT * (7 if bucket_count == 4 else 8),
            "tree_sha256": ("b" if bucket_count == 4 else "c") * 64,
        },
        "write": {
            "bytes": ROW_COUNT * (7 if bucket_count == 4 else 8),
            "numeric_schema_verified": True,
            "row_count": ROW_COUNT,
            "target_file_exercised": True,
            "write_seconds": "600.000000000",
        },
    }


def timed_result(
    source: dict[str, Any],
    *,
    query: str,
    first_single_seconds: str,
) -> dict[str, Any]:
    bucket = int(source["layout"]["bucket_count"])
    single = query == "single-symbol"
    hash_character = {4: ("d" if single else "e"), 8: ("f" if single else "1")}[bucket]
    return {
        "dataset_path": source["dataset_path"],
        "first_seconds": first_single_seconds if single else "1.000000000",
        "observed_row_count": SINGLE_ROWS if single else UNIVERSE_MONTH_ROWS,
        "post_scan_content_verified": True,
        "pre_scan_metadata_verified": True,
        "result_sha256": hash_character * 64,
        "warm_seconds": "0.050000000" if single else "0.500000000",
    }


def layout_payload(
    host: dict[str, Any],
    *,
    decision_evidence: dict[str, Any],
    real_market_evidence: dict[str, Any],
    first_single_seconds: str = "0.200000000",
) -> dict[str, Any]:
    datasets = [dataset(layout(4)), dataset(layout(8))]
    preparation_hash = "2" * 64
    measurements = []
    boot_number = 1
    for engine in ("duckdb", "polars"):
        for query in ("single-symbol", "universe-month"):
            measurements.append(
                {
                    "boot_marker": f"2026-08-12T0{boot_number}:00:00Z",
                    "cache_proof": "reboot",
                    "command": f"measure {engine} {query}",
                    "engine": engine,
                    "hardware": basic_hardware(host),
                    "measurement_schema": "grid.reference-layout-measurement/v2",
                    "measurements": [
                        timed_result(
                            source,
                            query=query,
                            first_single_seconds=first_single_seconds,
                        )
                        for source in datasets
                    ],
                    "preparation": {
                        "artifact": "preparation.json",
                        "artifact_sha256": preparation_hash,
                        "preparation_schema": "grid.reference-layout-preparation/v2",
                    },
                    "profile": "reference",
                    "query_shape": query,
                    "software": SOFTWARE,
                    "status": "reboot-separated-first-read",
                }
            )
            boot_number += 1
    return {
        "benchmark_schema": "grid.reference-layout-benchmark/v2",
        "cache_semantics": "each first read followed a distinct reboot",
        "command": "reference layout finalize",
        "hardware": basic_hardware(host),
        "limitations": ["synthetic timing", "owner decision required", "cache caveat"],
        "measurements": measurements,
        "preparation": {
            "artifact": "preparation.json",
            "artifact_sha256": preparation_hash,
            "boot_marker": "2026-08-11T23:00:00Z",
            "datasets": datasets,
            "decision_evidence": decision_evidence,
            "input": {
                "generation_chunk_rows": 1_000_000,
                "instrument_count": INSTRUMENTS,
                "row_count": ROW_COUNT,
                "row_group_rows": 100_000,
            },
            "preparation_schema": "grid.reference-layout-preparation/v2",
            "real_market_evidence": real_market_evidence,
            "reference_host_evidence": host,
            "software": SOFTWARE,
            "source_semantics": (
                "deterministic-exact-synthetic-v1+bounded-real-market-layout-skew-v1"
            ),
        },
        "profile": "reference",
        "software": SOFTWARE,
        "status": "reference-protocol-candidate",
    }


def feature_payload(host: dict[str, Any], *, memory_passed: bool = True) -> dict[str, Any]:
    peak_rss = 8 * 1024**3 if memory_passed else 50 * 1024**3
    return {
        "benchmark_schema": "grid.feature-benchmark/v2",
        "command": "reference feature",
        "correctness": {
            "core_rows_written_once": True,
            "future_rows_read": 0,
            "halo_minutes": 1_440,
            "semantics": "rolling window uses only the current and prior closed rows",
        },
        "hardware": basic_hardware(host),
        "input": {
            "core_minutes_per_shard": 2_880,
            "feature_columns": FEATURE_COLUMNS,
            "instrument_count": INSTRUMENTS,
            "row_count": ROW_COUNT,
            "synthetic_generator": "deterministic-range-v1",
            "window_minutes": 1_440,
        },
        "limitations": ["synthetic", "no publication", "scaled caveat", "owner decision"],
        "memory_gate": {
            "configured_limit_percent": 70,
            "passed": memory_passed,
            "peak_rss_percent_of_ram": "12.500000000" if memory_passed else "78.125000000",
        },
        "profile": "reference",
        "reference_host_evidence": host,
        "result": {
            "aggregate_sums": {
                name: "1.000000000"
                for name in (
                    "range_position",
                    "range_width",
                    "rolling_atr",
                    "rolling_high",
                    "rolling_low",
                    "rolling_mid",
                    "rolling_volume_mean",
                )
            },
            "elapsed_seconds": "30.000000000",
            "input_rows_including_halos": 149_391_900,
            "maximum_shard_input_rows": 3_024_000,
            "output_rows": ROW_COUNT,
            "peak_rss_bytes": peak_rss,
            "rss_baseline_bytes": 1_000_000,
            "rss_peak_delta_bytes": peak_rss - 1_000_000,
            "shards": [
                {
                    "core_end_minute_exclusive": SINGLE_ROWS,
                    "core_start_minute": 0,
                    "elapsed_seconds": "30.000000000",
                    "halo_start_minute": 0,
                    "input_rows": 149_391_900,
                    "output_rows": ROW_COUNT,
                }
            ],
            "throughput_core_rows_per_second": "3333330.000000000",
            "warmup_null_rows": 1_007_300,
        },
        "software": {name: SOFTWARE[name] for name in ("polars", "psutil", "python")},
        "status": (
            "reference-host-feature-candidate"
            if memory_passed
            else "reference-feature-rejected-memory"
        ),
    }


def publish_sources(
    tmp_path: Path,
    *,
    first_single_seconds: str = "0.200000000",
    memory_passed: bool = True,
    feature_host_hash_override: str | None = None,
) -> tuple[Path, Path, Path, Path, Path]:
    workstation_path = tmp_path / "reference-host.json"
    publish_evidence(workstation_path, workstation_payload())
    host = host_summary(artifact_hash=sha256_file(workstation_path))
    feature_host = (
        host
        if feature_host_hash_override is None
        else host_summary(artifact_hash=feature_host_hash_override)
    )
    layout_path = tmp_path / "reference-layout.json"
    feature_path = tmp_path / "reference-feature.json"
    publish_evidence(
        layout_path,
        layout_payload(
            host,
            decision_evidence=decision_summary(),
            real_market_evidence=real_market_summary(),
            first_single_seconds=first_single_seconds,
        ),
    )
    publish_evidence(feature_path, feature_payload(feature_host, memory_passed=memory_passed))
    return layout_path, feature_path, DECISION_PATH, REAL_MARKET_PATH, workstation_path


def publish_qualified_sources(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    qualification_path = tmp_path / "qualification.json"
    qualification = json.loads(QUALIFICATION_PATH.read_text(encoding="utf-8"))
    publish_evidence(qualification_path, qualification)
    host = qualification_summary(qualification_path, qualification)
    qualified_layout = layout_payload(
        host,
        decision_evidence=decision_summary(),
        real_market_evidence=real_market_summary(),
    )
    qualified_layout["benchmark_schema"] = "grid.reference-layout-benchmark/v3"
    qualified_layout["status"] = "qualified-reference-protocol-candidate"
    preparation = qualified_layout["preparation"]
    preparation["preparation_schema"] = "grid.reference-layout-preparation/v3"
    preparation["reference_host_qualification"] = preparation.pop("reference_host_evidence")
    for measurement in qualified_layout["measurements"]:
        measurement["measurement_schema"] = "grid.reference-layout-measurement/v3"
        measurement["preparation"]["preparation_schema"] = "grid.reference-layout-preparation/v3"
    qualified_feature = feature_payload(host)
    qualified_feature["benchmark_schema"] = "grid.feature-benchmark/v3"
    qualified_feature["reference_host_qualification"] = qualified_feature.pop(
        "reference_host_evidence"
    )
    qualified_feature["status"] = "qualified-host-feature-candidate"
    layout_path = tmp_path / "qualified-layout.json"
    feature_path = tmp_path / "qualified-feature.json"
    publish_evidence(layout_path, qualified_layout)
    publish_evidence(feature_path, qualified_feature)
    return layout_path, feature_path, DECISION_PATH, REAL_MARKET_PATH, qualification_path


def test_gate1_pack_is_ready_but_cannot_approve_owner_decisions(tmp_path: Path) -> None:
    layout_path, feature_path, decision_path, real_market_path, workstation_path = publish_sources(
        tmp_path
    )
    output = tmp_path / "gate1-review.json"

    payload = publish_review_pack(
        layout_path=layout_path,
        feature_path=feature_path,
        decision_path=decision_path,
        real_market_path=real_market_path,
        workstation_path=workstation_path,
        output=output,
        command="gate1 review test",
    )

    assert payload["status"] == "ready-for-owner-review"
    assert payload["gate_1"] == {
        "automatic_promotion": False,
        "blockers": [],
        "owner_decision_required": True,
        "status": "pending-owner-decision",
    }
    assert payload["decisions"]["P-001"]["candidate_values"] == ["hybrid_int64_decimal"]
    assert payload["decisions"]["P-002"]["candidate_values"] == ["4", "8"]
    assert all(
        candidate["gates"]["provisional_performance_passed"]
        for candidate in payload["layout_candidates"]
    )
    assert verify_evidence(output)


def test_qualified_gate1_pack_binds_v3_workloads_without_accepting_gate(tmp_path: Path) -> None:
    layout_path, feature_path, decision_path, real_market_path, qualification_path = (
        publish_qualified_sources(tmp_path)
    )
    output = tmp_path / "qualified-gate1-review.json"

    payload = publish_qualified_review_pack(
        layout_path=layout_path,
        feature_path=feature_path,
        decision_path=decision_path,
        real_market_path=real_market_path,
        qualification_path=qualification_path,
        output=output,
        command="qualified gate1 review test",
    )

    assert payload["evidence_schema"] == "grid.gate1-review-pack/v2"
    assert payload["status"] == "ready-for-owner-review"
    assert payload["gate_1"]["status"] == "pending-owner-decision"
    assert payload["reference_host_qualification"]["artifact"] == qualification_path.name
    assert payload["sources"]["qualification"]["artifact"] == qualification_path.name
    assert payload["capacity"]["required_free_bytes"] == 100_228_313_013
    assert verify_evidence(output)


def test_gate1_pack_preserves_negative_reference_results(tmp_path: Path) -> None:
    layout_path, feature_path, decision_path, real_market_path, workstation_path = publish_sources(
        tmp_path,
        first_single_seconds="1.000000000",
        memory_passed=False,
    )

    payload = publish_review_pack(
        layout_path=layout_path,
        feature_path=feature_path,
        decision_path=decision_path,
        real_market_path=real_market_path,
        workstation_path=workstation_path,
        output=tmp_path / "gate1-blocked.json",
        command="gate1 blocked test",
    )

    assert payload["status"] == "blocked-by-reference-results"
    assert payload["gate_1"]["blockers"] == [
        "no-layout-meets-provisional-performance-targets",
        "feature-memory-gate-failed",
    ]
    assert payload["decisions"]["P-001"]["candidate_values"] == []
    assert payload["decisions"]["P-005"]["status"] == "owner-decision-required"


def test_gate1_pack_rejects_cross_host_evidence_before_replacing_output(tmp_path: Path) -> None:
    layout_path, feature_path, decision_path, real_market_path, workstation_path = publish_sources(
        tmp_path,
        feature_host_hash_override="9" * 64,
    )
    output = tmp_path / "gate1-review.json"
    publish_evidence(output, {"preserved": True})

    with pytest.raises(ValueError, match="same reference host"):
        publish_review_pack(
            layout_path=layout_path,
            feature_path=feature_path,
            decision_path=decision_path,
            real_market_path=real_market_path,
            workstation_path=workstation_path,
            output=output,
            force=True,
            command="gate1 cross-host test",
        )

    assert json.loads(output.read_text(encoding="utf-8")) == {"preserved": True}
    assert verify_evidence(output)


def test_gate1_pack_rejects_tampered_source_receipt(tmp_path: Path) -> None:
    layout_path, feature_path, decision_path, real_market_path, workstation_path = publish_sources(
        tmp_path
    )
    feature_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="receipt does not verify"):
        publish_review_pack(
            layout_path=layout_path,
            feature_path=feature_path,
            decision_path=decision_path,
            real_market_path=real_market_path,
            workstation_path=workstation_path,
            output=tmp_path / "gate1-review.json",
            command="gate1 tamper test",
        )


def test_gate1_pack_rejects_valid_but_unbound_transitive_evidence(tmp_path: Path) -> None:
    layout_path, feature_path, _decision_path, real_market_path, workstation_path = publish_sources(
        tmp_path
    )
    wrong_decision_path = tmp_path / "m1-layout-exact-decision-candidate.json"
    wrong_decision = json.loads(DECISION_PATH.read_text(encoding="utf-8"))
    wrong_decision["command"] = "different but schema-valid decision evidence"
    publish_evidence(wrong_decision_path, wrong_decision)

    with pytest.raises(ValueError, match="does not bind the supplied decision"):
        publish_review_pack(
            layout_path=layout_path,
            feature_path=feature_path,
            decision_path=wrong_decision_path,
            real_market_path=real_market_path,
            workstation_path=workstation_path,
            output=tmp_path / "gate1-review.json",
            command="gate1 transitive mismatch test",
        )


def test_gate1_pack_rejects_schema_valid_internal_write_mismatch(tmp_path: Path) -> None:
    layout_path, feature_path, decision_path, real_market_path, workstation_path = publish_sources(
        tmp_path
    )
    mismatched_layout = json.loads(layout_path.read_text(encoding="utf-8"))
    mismatched_layout["preparation"]["datasets"][0]["write"]["row_count"] -= 1
    publish_evidence(layout_path, mismatched_layout, force=True)

    with pytest.raises(ValueError, match="write row count"):
        publish_review_pack(
            layout_path=layout_path,
            feature_path=feature_path,
            decision_path=decision_path,
            real_market_path=real_market_path,
            workstation_path=workstation_path,
            output=tmp_path / "gate1-review.json",
            command="gate1 internal mismatch test",
        )
