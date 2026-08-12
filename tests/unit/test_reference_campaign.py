from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from grid_contracts.canonical import sha256_file
from grid_data.evidence import publish_evidence, verify_evidence

import benchmarks.reference_campaign as campaign
from benchmarks.gate1_review_pack import load_verified_evidence

ROOT = Path(__file__).parents[2]
DECISION = ROOT / "benchmarks" / "results" / "m1-layout-exact-decision-candidate.json"
REAL_MARKET = ROOT / "benchmarks" / "results" / "m1-real-market-layout-skew.json"
BELOW_PROFILE = ROOT / "benchmarks" / "results" / "m1-workstation-snapshot.json"


def workstation_payload() -> dict[str, Any]:
    gib = 1024**3
    tib = 1024**4
    return {
        "assessment": {
            "documented_full_research_profile": {
                "meets": True,
                "observed_shortfalls": [],
                "requirements": {
                    "minimum_physical_cores": 16,
                    "minimum_ram_bytes": 64 * gib,
                    "minimum_volume_bytes": 2 * tib,
                    "storage_kind": "nvme",
                },
            },
            "documented_local_feasibility_profile": {
                "meets": True,
                "observed_shortfalls": [],
                "requirements": {
                    "minimum_physical_cores": 8,
                    "minimum_ram_bytes": 32 * gib,
                    "minimum_volume_bytes": 1 * tib,
                    "storage_kind": "nvme",
                },
            },
        },
        "command": "reference snapshot",
        "evidence_schema": "grid.workstation-snapshot/v1",
        "hardware": {
            "cpu_count_logical": 32,
            "cpu_count_physical": 16,
            "cpu_model": "Reference CPU",
            "machine": "AMD64",
            "platform": "Reference OS",
            "ram_bytes": 64 * gib,
            "storage_kind": "nvme",
            "storage_model": "Reference NVMe",
            "volume_free_bytes": 2 * tib,
            "volume_root": "D:\\",
            "volume_total_bytes": 2 * tib,
        },
        "observed_at_utc": "2026-08-12T12:00:00Z",
        "recommendation": ["reference", "separate backup", "owner review"],
        "software": {"psutil": "7.0.0", "python": "3.12.0"},
        "status": "meets-documented-full-research-profile",
    }


def admitted_host(host_path: Path) -> dict[str, Any]:
    payload = workstation_payload()
    hardware = payload["hardware"]
    return {
        "artifact": host_path.name,
        "artifact_sha256": sha256_file(host_path),
        "evidence_schema": "grid.workstation-snapshot/v1",
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
        "observed_at_utc": payload["observed_at_utc"],
        "status": "meets-documented-full-research-profile",
    }


def manifest_summary() -> dict[str, Any]:
    return {
        "artifact": "MANIFEST.sha256",
        "artifact_sha256": "a" * 64,
        "path": str((ROOT / "MANIFEST.sha256").resolve()),
        "source_file_count": 250,
    }


def publish_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict[str, Any]]:
    host_path = tmp_path / "reference-host.json"
    publish_evidence(host_path, workstation_payload())
    admitted = admitted_host(host_path)
    monkeypatch.setattr(campaign, "admit_reference_host", lambda *_args, **_kwargs: admitted)
    monkeypatch.setattr(campaign, "_source_manifest_summary", manifest_summary)
    campaign_root = tmp_path / "campaign"
    payload = campaign.publish_campaign_plan(
        campaign_root=campaign_root,
        reference_host_path=host_path,
        decision_path=DECISION,
        real_market_path=REAL_MARKET,
    )
    return campaign_root / campaign.PLAN_NAME, payload


def test_campaign_plan_rejects_below_profile_before_mutation(tmp_path: Path) -> None:
    campaign_root = tmp_path / "rejected-campaign"

    with pytest.raises(ValueError, match="does not meet"):
        campaign.publish_campaign_plan(
            campaign_root=campaign_root,
            reference_host_path=BELOW_PROFILE,
            decision_path=DECISION,
            real_market_path=REAL_MARKET,
        )

    assert not campaign_root.exists()


def test_campaign_plan_pins_eight_ordered_commands_and_never_accepts_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_path, payload = publish_plan(tmp_path, monkeypatch)

    assert verify_evidence(plan_path)
    load_verified_evidence(plan_path, campaign.PLAN_SCHEMA)
    assert payload["gate_1"] == {
        "automatic_acceptance": False,
        "owner_decision_required": True,
        "status": "pending-owner-decision",
    }
    assert [step["id"] for step in payload["steps"]] == [
        "layout-prepare",
        "layout-measure-duckdb-single-symbol",
        "layout-measure-duckdb-universe-month",
        "layout-measure-polars-single-symbol",
        "layout-measure-polars-universe-month",
        "layout-finalize",
        "feature-reference",
        "gate1-review-pack",
    ]
    assert sum(step["requires_reboot_before"] for step in payload["steps"]) == 4
    assert all("--force" not in step["argv"] for step in payload["steps"])
    prepare = payload["steps"][0]["argv"]
    assert prepare[prepare.index("--profile") + 1] == "reference"
    assert prepare[prepare.index("--rows") + 1] == "100000000"
    assert prepare[prepare.index("--instruments") + 1] == "700"


def test_campaign_status_returns_prepare_then_requires_reboot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_path, payload = publish_plan(tmp_path, monkeypatch)

    initial = campaign.campaign_status(plan_path)
    assert initial["campaign_status"] == "ready"
    assert initial["next_action"]["step"]["id"] == "layout-prepare"

    preparation_path = Path(payload["steps"][0]["expected_artifact"])
    publish_evidence(
        preparation_path,
        {
            "boot_marker": "2026-08-12T10:00:00Z",
            "decision_evidence": {
                "artifact_sha256": payload["sources"]["decision"]["artifact_sha256"]
            },
            "input": {
                "generation_chunk_rows": 1_000_000,
                "instrument_count": 700,
                "row_count": 99_999_900,
                "row_group_rows": 100_000,
            },
            "preparation_schema": "grid.reference-layout-preparation/v2",
            "profile": "reference",
            "real_market_evidence": {
                "artifact_sha256": payload["sources"]["real_market"]["artifact_sha256"]
            },
            "reference_host_evidence": payload["reference_host"],
            "status": "prepared-for-separated-measurement",
        },
    )
    monkeypatch.setattr(campaign, "_current_boot_marker", lambda: "2026-08-12T10:00:00Z")

    after_prepare = campaign.campaign_status(plan_path)
    assert after_prepare["campaign_status"] == "reboot-required"
    assert after_prepare["next_action"]["action"] == "reboot"
    assert after_prepare["next_action"]["then"]["id"] == ("layout-measure-duckdb-single-symbol")


def test_campaign_status_blocks_unreceipted_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_path, payload = publish_plan(tmp_path, monkeypatch)
    preparation_path = Path(payload["steps"][0]["expected_artifact"])
    preparation_path.parent.mkdir(parents=True)
    preparation_path.write_text("{}\n", encoding="utf-8")

    status = campaign.campaign_status(plan_path)

    assert status["campaign_status"] == "blocked-invalid-artifact"
    assert status["next_action"] is None
    assert status["invalid_reasons"] == ["layout-prepare: completion receipt does not verify"]
