from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from grid_contracts.canonical import canonical_sha256
from grid_data.evidence import publish_evidence, verify_evidence

from benchmarks.current_universe_capacity import publish_current_universe_projection

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ROOT / "benchmarks" / "results" / "m1-bybit-history-source-assessment.json"
CAPACITY = ROOT / "benchmarks" / "results" / "m1-real-market-capacity-projection.json"
WORKSTATION = ROOT / "benchmarks" / "results" / "m1-workstation-snapshot.json"
GENERATED_AT = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def scenario(payload: dict[str, Any], identifier: str) -> dict[str, Any]:
    return next(item for item in payload["disk_headroom"]["scenarios"] if item["id"] == identifier)


def test_projection_separates_one_time_bootstrap_from_bounded_updates(tmp_path: Path) -> None:
    output = tmp_path / "current-universe.json"

    payload = publish_current_universe_projection(
        history_path=HISTORY,
        capacity_path=CAPACITY,
        workstation_path=WORKSTATION,
        output=output,
        command="current universe test",
        generated_at=GENERATED_AT,
    )

    universe = payload["universe"]
    assert universe["lifecycle_per_dataset_rows"] == 884_733_307
    assert universe["lifecycle_trade_and_mark_rows_at_equal_coverage"] == 1_769_466_614
    assert universe["share_of_formal_trade_and_mark_capacity_percent"] == "24.030927783"
    assert payload["incremental_projection"] == {
        "active_trading_instruments": 699,
        "maximum_partition_days": 31,
        "maximum_partition_trade_and_mark_rows": 62_406_720,
        "one_day_trade_and_mark_rows": 2_013_120,
    }

    bootstrap = scenario(payload, "bootstrap-canonical-building")
    rebuild = scenario(payload, "full-rebuild-active-plus-building")
    one_day = scenario(payload, "incremental-one-day")
    partition = scenario(payload, "incremental-maximum-31-day-partition")
    assert one_day["required_bytes"] < partition["required_bytes"] < bootstrap["required_bytes"]
    assert rebuild["required_bytes"] == bootstrap["required_bytes"] * 2
    assert all(item["fits_observed_free"] for item in (bootstrap, rebuild, one_day, partition))
    assert payload["disk_headroom"]["measured_canonical_scenarios_fit"] is True
    assert payload["disk_headroom"]["planning_64_byte_rebuild_scenario_fits"] is False
    assert payload["disk_headroom"]["raw_source_archives"] == {
        "measured": False,
        "safe_full_bootstrap_conclusion": False,
        "status": "unknown-headroom-requires-downloader-preflight",
    }
    assert verify_evidence(output)


def test_projection_binds_exact_layout_metrics_and_fresh_sources(tmp_path: Path) -> None:
    payload = publish_current_universe_projection(
        history_path=HISTORY,
        capacity_path=CAPACITY,
        workstation_path=WORKSTATION,
        output=tmp_path / "current-universe.json",
        command="current universe binding test",
        generated_at=GENERATED_AT,
    )

    assert len(payload["layout_projections"]) == 2
    assert {item["layout"]["bucket_count"] for item in payload["layout_projections"]} == {4, 8}
    assert payload["sources"]["history"]["schema"] == ("grid.bybit-history-source-assessment/v1")
    assert payload["sources"]["capacity"]["schema"] == "grid.capacity-projection/v3"
    assert 0 < float(payload["source_freshness"]["history"]["age_hours"]) < 24
    assert 0 < float(payload["source_freshness"]["workstation"]["age_hours"]) < 24


def test_projection_rejects_stale_operational_sources(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="history fetched_at_utc is stale"):
        publish_current_universe_projection(
            history_path=HISTORY,
            capacity_path=CAPACITY,
            workstation_path=WORKSTATION,
            output=tmp_path / "current-universe.json",
            command="stale current universe test",
            generated_at=datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
        )


def test_projection_rejects_tampered_source_receipt(tmp_path: Path) -> None:
    history_path = tmp_path / "history.json"
    publish_evidence(history_path, load_json(HISTORY))
    history_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="receipt does not verify"):
        publish_current_universe_projection(
            history_path=history_path,
            capacity_path=CAPACITY,
            workstation_path=WORKSTATION,
            output=tmp_path / "current-universe.json",
            command="tampered receipt test",
            generated_at=GENERATED_AT,
        )


def test_projection_rejects_schema_valid_bad_embedded_hash_before_replacement(
    tmp_path: Path,
) -> None:
    history_path = tmp_path / "history.json"
    modified = load_json(HISTORY)
    modified["command"] = "schema-valid but content hash is stale"
    publish_evidence(history_path, modified)
    output = tmp_path / "current-universe.json"
    publish_evidence(output, {"preserved": True})

    with pytest.raises(ValueError, match="content hash does not verify"):
        publish_current_universe_projection(
            history_path=history_path,
            capacity_path=CAPACITY,
            workstation_path=WORKSTATION,
            output=output,
            force=True,
            command="bad embedded hash test",
            generated_at=GENERATED_AT,
        )

    assert load_json(output) == {"preserved": True}
    assert verify_evidence(output)


def test_projection_rejects_schema_valid_cross_layout_capacity(tmp_path: Path) -> None:
    capacity_path = tmp_path / "capacity.json"
    modified = load_json(CAPACITY)
    modified["real_market_layout_projections"][0]["layout"]["target_file_mb"] = 16
    publish_evidence(capacity_path, modified)

    with pytest.raises(ValueError, match="same two synthetic/real layouts"):
        publish_current_universe_projection(
            history_path=HISTORY,
            capacity_path=capacity_path,
            workstation_path=WORKSTATION,
            output=tmp_path / "current-universe.json",
            command="cross-layout capacity test",
            generated_at=GENERATED_AT,
        )


def test_projection_rejects_schema_valid_internal_capacity_math(tmp_path: Path) -> None:
    capacity_path = tmp_path / "capacity.json"
    modified = load_json(CAPACITY)
    modified["real_market_layout_projections"][0][
        "projected_trade_and_mark_bytes_at_trade_row_width"
    ] += 100
    publish_evidence(capacity_path, modified)

    with pytest.raises(ValueError, match="do not match their rows"):
        publish_current_universe_projection(
            history_path=HISTORY,
            capacity_path=capacity_path,
            workstation_path=WORKSTATION,
            output=tmp_path / "current-universe.json",
            command="capacity math mismatch test",
            generated_at=GENERATED_AT,
        )


def test_projection_rejects_cross_volume_snapshot_before_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "current-universe.json"
    publish_evidence(output, {"preserved": True})
    monkeypatch.setattr(
        "benchmarks.current_universe_capacity.volume_root_for_path",
        lambda _path: Path("Z:\\"),
    )

    with pytest.raises(ValueError, match="does not describe the output volume"):
        publish_current_universe_projection(
            history_path=HISTORY,
            capacity_path=CAPACITY,
            workstation_path=WORKSTATION,
            output=output,
            force=True,
            command="cross-volume test",
            generated_at=GENERATED_AT,
        )

    assert load_json(output) == {"preserved": True}
    assert verify_evidence(output)


def test_history_content_hash_fixture_remains_canonical() -> None:
    payload = load_json(HISTORY)
    embedded = payload.pop("content_sha256")
    assert embedded == canonical_sha256(payload)
