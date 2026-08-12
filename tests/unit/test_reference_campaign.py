from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from grid_contracts.canonical import sha256_file
from grid_data.evidence import publish_evidence, verify_evidence

import benchmarks.reference_campaign as campaign
from benchmarks.gate1_review_pack import load_verified_evidence
from benchmarks.measured_host_qualification import qualification_summary

ROOT = Path(__file__).parents[2]
DECISION = ROOT / "benchmarks" / "results" / "m1-layout-exact-decision-candidate.json"
REAL_MARKET = ROOT / "benchmarks" / "results" / "m1-real-market-layout-skew.json"
BELOW_PROFILE = ROOT / "benchmarks" / "results" / "m1-workstation-snapshot.json"
QUALIFICATION = (
    ROOT / "benchmarks" / "results" / "m1-owner-measured-host-qualification-20260812.json"
)


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


def environment_report() -> dict[str, Any]:
    checks = {
        name: True
        for name in (
            "canonical_origin",
            "clean_worktree",
            "constraint_contract",
            "constrained_versions_match",
            "exact_python_3_12",
            "head_matches_origin_main",
            "isolated_virtual_environment",
            "main_branch_checked_out",
            "monorepo_distributions_installed",
            "pip_dependencies_consistent",
            "private_exchange_environment_absent",
            "required_modules_importable",
            "source_manifest_verified",
            "working_directory_is_repository_root",
        )
    }
    pins = {f"pin-{index}": "1.0" for index in range(9)}
    installed = {f"distribution-{index}": "1.0" for index in range(17)}
    return {
        "checks": checks,
        "constraints": {
            "artifact": "requirements/reference-campaign.txt",
            "artifact_sha256": "9" * 64,
            "pins": pins,
        },
        "failures": [],
        "observed": {
            "git_branch": "main",
            "git_head": "8" * 40,
            "installed_versions": installed,
            "private_exchange_environment_names": [],
            "python": "3.12.10",
        },
        "status": "ready-for-reference-campaign",
    }


def publish_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict[str, Any]]:
    host_path = tmp_path / "reference-host.json"
    publish_evidence(host_path, workstation_payload())
    admitted = admitted_host(host_path)
    monkeypatch.setattr(campaign, "admit_reference_host", lambda *_args, **_kwargs: admitted)
    monkeypatch.setattr(
        campaign,
        "_require_reference_environment",
        lambda: {"failures": [], "status": "ready-for-reference-campaign"},
    )
    monkeypatch.setattr(campaign, "_source_manifest_summary", manifest_summary)
    campaign_root = tmp_path / "campaign"
    payload = campaign.publish_campaign_plan(
        campaign_root=campaign_root,
        reference_host_path=host_path,
        decision_path=DECISION,
        real_market_path=REAL_MARKET,
    )
    return campaign_root / campaign.PLAN_NAME, payload


def publish_qualified_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, dict[str, Any]]:
    qualification_path = tmp_path / "qualification.json"
    qualification = json.loads(QUALIFICATION.read_text(encoding="utf-8"))
    publish_evidence(qualification_path, qualification)
    admitted = qualification_summary(qualification_path, qualification)
    monkeypatch.setattr(
        campaign,
        "admit_measured_host_qualification",
        lambda *_args, **_kwargs: admitted,
    )
    monkeypatch.setattr(campaign, "recheck_admitted_qualification", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(campaign, "_require_reference_environment", environment_report)
    monkeypatch.setattr(campaign, "_source_manifest_summary", manifest_summary)
    campaign_root = tmp_path / "qualified-campaign"
    payload = campaign.publish_qualified_campaign_plan(
        campaign_root=campaign_root,
        qualification_path=qualification_path,
        decision_path=DECISION,
        real_market_path=REAL_MARKET,
    )
    return campaign_root / campaign.PLAN_NAME, payload


def final_payloads(
    plan: dict[str, Any],
    *,
    preparation_hash: str,
    layout_hash: str = "b" * 64,
    feature_hash: str = "c" * 64,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    sources = plan["sources"]
    layout = {
        "benchmark_schema": "grid.reference-layout-benchmark/v2",
        "preparation": {
            "artifact_sha256": preparation_hash,
            "decision_evidence": {
                "artifact": sources["decision"]["artifact"],
                "artifact_sha256": sources["decision"]["artifact_sha256"],
                "benchmark_schema": sources["decision"]["schema"],
                "status": sources["decision"]["status"],
            },
            "input": campaign._expected_reference_input(),
            "real_market_evidence": {
                "artifact": sources["real_market"]["artifact"],
                "artifact_sha256": sources["real_market"]["artifact_sha256"],
                "evidence_schema": sources["real_market"]["schema"],
            },
            "reference_host_evidence": plan["reference_host"],
        },
        "profile": "reference",
        "status": "reference-protocol-candidate",
    }
    feature = {
        "benchmark_schema": "grid.feature-benchmark/v2",
        "input": {
            "core_minutes_per_shard": 2880,
            "instrument_count": 700,
            "row_count": 99_999_900,
            "window_minutes": 1440,
        },
        "memory_gate": {"configured_limit_percent": 70, "passed": True},
        "profile": "reference",
        "reference_host_evidence": plan["reference_host"],
        "status": "reference-host-feature-candidate",
    }

    def compact(source: dict[str, Any]) -> dict[str, str]:
        return {key: source[key] for key in ("artifact", "artifact_sha256", "schema", "status")}

    review = {
        "gate_1": {
            "automatic_promotion": False,
            "blockers": [],
            "owner_decision_required": True,
            "status": "pending-owner-decision",
        },
        "owner_decision_required": True,
        "reference_host": plan["reference_host"],
        "sources": {
            "decision_layout": compact(sources["decision"]),
            "feature": {
                "artifact": campaign.FEATURE_OUTPUT_NAME,
                "artifact_sha256": feature_hash,
                "schema": feature["benchmark_schema"],
                "status": feature["status"],
            },
            "layout": {
                "artifact": campaign.LAYOUT_OUTPUT_NAME,
                "artifact_sha256": layout_hash,
                "schema": layout["benchmark_schema"],
                "status": layout["status"],
            },
            "real_market": compact(sources["real_market"]),
            "workstation": compact(sources["workstation"]),
        },
        "status": "ready-for-owner-review",
    }
    return layout, feature, review


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


def test_qualified_campaign_plan_pins_v3_commands_and_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_path, payload = publish_qualified_plan(tmp_path, monkeypatch)

    assert verify_evidence(plan_path)
    load_verified_evidence(plan_path, campaign.PLAN_SCHEMA_V2)
    assert payload["evidence_schema"] == "grid.reference-campaign-plan/v2"
    assert payload["environment"]["status"] == "ready-for-reference-campaign"
    assert payload["gate_1"]["status"] == "pending-owner-decision"
    assert payload["sources"]["qualification"]["schema"] == ("grid.reference-host-qualification/v1")
    prepare = payload["steps"][0]["argv"]
    feature = payload["steps"][6]["argv"]
    review = payload["steps"][7]["argv"]
    assert "--reference-host-qualification" in prepare
    assert "--reference-host-qualification" in feature
    assert "--reference-host-qualification" in review
    assert "--reference-host-evidence" not in prepare
    assert "--workstation" not in review

    status = campaign.campaign_status(plan_path)
    assert status["campaign_status"] == "ready"
    assert status["next_action"]["step"]["id"] == "layout-prepare"


def test_qualified_layout_accepts_contract_real_market_summary_without_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plan_path, plan = publish_qualified_plan(tmp_path, monkeypatch)
    preparation_hash = "a" * 64
    sources = plan["sources"]
    layout = {
        "preparation": {
            "artifact_sha256": preparation_hash,
            "decision_evidence": {
                "artifact": sources["decision"]["artifact"],
                "artifact_sha256": sources["decision"]["artifact_sha256"],
                "benchmark_schema": sources["decision"]["schema"],
                "status": sources["decision"]["status"],
            },
            "input": campaign._expected_reference_input(),
            "real_market_evidence": {
                "artifact": sources["real_market"]["artifact"],
                "artifact_sha256": sources["real_market"]["artifact_sha256"],
                "evidence_schema": sources["real_market"]["schema"],
                "layouts": [],
                "source_content_sha256": "b" * 64,
                "total_row_count": 1,
            },
            "reference_host_qualification": plan["reference_host_qualification"],
        },
        "profile": "reference",
        "status": "qualified-reference-protocol-candidate",
    }

    assert (
        campaign._qualified_layout_completion_reason(
            layout,
            plan,
            preparation_hash=preparation_hash,
        )
        is None
    )

    foreign_layout = deepcopy(layout)
    foreign_layout["preparation"]["real_market_evidence"]["artifact_sha256"] = "c" * 64
    assert "does not bind" in str(
        campaign._qualified_layout_completion_reason(
            foreign_layout,
            plan,
            preparation_hash=preparation_hash,
        )
    )


def test_campaign_plan_rejects_environment_drift_before_root_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host_path = tmp_path / "reference-host.json"
    publish_evidence(host_path, workstation_payload())
    admitted = admitted_host(host_path)
    monkeypatch.setattr(campaign, "admit_reference_host", lambda *_args, **_kwargs: admitted)
    monkeypatch.setattr(
        campaign,
        "_require_reference_environment",
        lambda: (_ for _ in ()).throw(
            ValueError("reference environment preflight failed: constrained_versions_match")
        ),
    )
    campaign_root = tmp_path / "rejected-environment"

    with pytest.raises(ValueError, match="constrained_versions_match"):
        campaign.publish_campaign_plan(
            campaign_root=campaign_root,
            reference_host_path=host_path,
            decision_path=DECISION,
            real_market_path=REAL_MARKET,
        )

    assert not campaign_root.exists()


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


def test_campaign_status_rejects_measurement_from_preparation_boot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_path, plan = publish_plan(tmp_path, monkeypatch)
    preparation_path = Path(plan["steps"][0]["expected_artifact"])
    preparation_boot = "2026-08-12T10:00:00Z"
    publish_evidence(
        preparation_path,
        {
            "boot_marker": preparation_boot,
            "decision_evidence": {
                "artifact_sha256": plan["sources"]["decision"]["artifact_sha256"]
            },
            "input": campaign._expected_reference_input(),
            "preparation_schema": "grid.reference-layout-preparation/v2",
            "profile": "reference",
            "real_market_evidence": {
                "artifact_sha256": plan["sources"]["real_market"]["artifact_sha256"]
            },
            "reference_host_evidence": plan["reference_host"],
            "status": "prepared-for-separated-measurement",
        },
    )
    measurement_path = preparation_path.parent / "measurement-duckdb-single-symbol.json"
    publish_evidence(
        measurement_path,
        {
            "boot_marker": preparation_boot,
            "cache_proof": "reboot",
            "engine": "duckdb",
            "measurement_schema": "grid.reference-layout-measurement/v2",
            "preparation": {"artifact_sha256": sha256_file(preparation_path)},
            "profile": "reference",
            "query_shape": "single-symbol",
            "status": "reboot-separated-first-read",
        },
    )

    status = campaign.campaign_status(plan_path)

    assert status["campaign_status"] == "blocked-invalid-artifact"
    assert status["invalid_reasons"] == [
        "layout-measure-duckdb-single-symbol: measurement boot marker is missing or not "
        "distinct from prior stages"
    ]


def test_final_artifact_bindings_reject_other_campaign_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plan_path, plan = publish_plan(tmp_path, monkeypatch)
    layout_path = tmp_path / campaign.LAYOUT_OUTPUT_NAME
    feature_path = tmp_path / campaign.FEATURE_OUTPUT_NAME
    layout_path.write_text("layout\n", encoding="utf-8")
    feature_path.write_text("feature\n", encoding="utf-8")
    layout_hash = sha256_file(layout_path)
    feature_hash = sha256_file(feature_path)
    layout, feature, review = final_payloads(
        plan,
        preparation_hash="a" * 64,
        layout_hash=layout_hash,
        feature_hash=feature_hash,
    )

    assert campaign._layout_completion_reason(layout, plan, preparation_hash="a" * 64) is None
    assert campaign._feature_completion_reason(feature, plan) is None
    assert (
        campaign._review_completion_reason(
            review,
            plan,
            layout_path=layout_path,
            layout_payload=layout,
            feature_path=feature_path,
            feature_payload=feature,
        )
        is None
    )

    foreign_layout = deepcopy(layout)
    foreign_layout["preparation"]["decision_evidence"]["artifact_sha256"] = "d" * 64
    assert "does not bind" in str(
        campaign._layout_completion_reason(
            foreign_layout,
            plan,
            preparation_hash="a" * 64,
        )
    )

    foreign_feature = deepcopy(feature)
    foreign_feature["reference_host_evidence"]["artifact_sha256"] = "e" * 64
    assert "does not bind" in str(campaign._feature_completion_reason(foreign_feature, plan))

    foreign_review = deepcopy(review)
    foreign_review["sources"]["layout"]["artifact_sha256"] = "f" * 64
    assert "does not bind" in str(
        campaign._review_completion_reason(
            foreign_review,
            plan,
            layout_path=layout_path,
            layout_payload=layout,
            feature_path=feature_path,
            feature_payload=feature,
        )
    )


def test_campaign_status_blocks_cross_campaign_final_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_path, plan = publish_plan(tmp_path, monkeypatch)
    preparation_path = Path(plan["steps"][0]["expected_artifact"])
    publish_evidence(
        preparation_path,
        {
            "boot_marker": "2026-08-12T10:00:00Z",
            "decision_evidence": {
                "artifact_sha256": plan["sources"]["decision"]["artifact_sha256"]
            },
            "input": campaign._expected_reference_input(),
            "preparation_schema": "grid.reference-layout-preparation/v2",
            "profile": "reference",
            "real_market_evidence": {
                "artifact_sha256": plan["sources"]["real_market"]["artifact_sha256"]
            },
            "reference_host_evidence": plan["reference_host"],
            "status": "prepared-for-separated-measurement",
        },
    )
    preparation_hash = sha256_file(preparation_path)
    for index, (engine, query_shape) in enumerate(campaign.MEASUREMENT_LEGS, start=1):
        measurement_path = preparation_path.parent / f"measurement-{engine}-{query_shape}.json"
        publish_evidence(
            measurement_path,
            {
                "boot_marker": f"2026-08-2{index}T10:00:00Z",
                "cache_proof": "reboot",
                "engine": engine,
                "measurement_schema": "grid.reference-layout-measurement/v2",
                "preparation": {"artifact_sha256": preparation_hash},
                "profile": "reference",
                "query_shape": query_shape,
                "status": "reboot-separated-first-read",
            },
        )

    layout, _feature, _review = final_payloads(plan, preparation_hash=preparation_hash)
    layout["preparation"]["decision_evidence"]["artifact_sha256"] = "d" * 64

    def schema_state(_path: Path, schema: Path) -> tuple[str, dict[str, Any] | None, str | None]:
        if schema == campaign.LAYOUT_SCHEMA:
            return "complete", layout, None
        return "pending", None, None

    monkeypatch.setattr(campaign, "_schema_artifact_state", schema_state)

    status = campaign.campaign_status(plan_path)

    assert status["campaign_status"] == "blocked-invalid-artifact"
    assert status["next_action"] is None
    assert status["invalid_reasons"] == [
        "layout-finalize: final layout does not bind the campaign preparation, scale, host, "
        "or sources"
    ]
