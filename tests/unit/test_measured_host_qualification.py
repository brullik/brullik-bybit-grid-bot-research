from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from grid_data.evidence import publish_evidence, verify_evidence
from jsonschema import Draft202012Validator, FormatChecker

import benchmarks.measured_host_qualification as qualification

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "benchmarks" / "results"
LAYOUT = RESULTS / "m1-layout-exact-decision-candidate.json"
FEATURE = RESULTS / "m1-feature-reference-candidate.json"
CAPACITY = RESULTS / "m1-owner-storage-review-capacity-20260812.json"
WORKSTATION = RESULTS / "m1-owner-storage-review-workstation-20260812.json"
QUALIFIED_AT = datetime(2026, 8, 12, 16, 0, tzinfo=UTC)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def source(artifact: str, schema: str, status: str) -> dict[str, str]:
    return {
        "artifact": artifact,
        "artifact_sha256": "a" * 64,
        "schema": schema,
        "status": status,
    }


def sources() -> dict[str, dict[str, str]]:
    return {
        "capacity": source(
            CAPACITY.name,
            "grid.current-universe-capacity/v1",
            "provisional-current-universe-capacity",
        ),
        "feature": source(
            FEATURE.name,
            "grid.feature-benchmark/v1",
            "reference-scale-candidate",
        ),
        "layout": source(
            LAYOUT.name,
            "grid.layout-benchmark/v3",
            "decision-matrix-candidate",
        ),
        "workstation": source(
            WORKSTATION.name,
            "grid.workstation-snapshot/v1",
            "below-documented-full-research-profile",
        ),
    }


def observed_hardware(*, free_bytes: int = 193_679_237_120) -> dict[str, Any]:
    hardware = dict(load_json(WORKSTATION)["hardware"])
    hardware["volume_free_bytes"] = free_bytes
    return hardware


def build(*, free_bytes: int = 193_679_237_120) -> dict[str, Any]:
    return qualification.build_qualification(
        layout=load_json(LAYOUT),
        feature=load_json(FEATURE),
        capacity=load_json(CAPACITY),
        hardware=observed_hardware(free_bytes=free_bytes),
        sources=sources(),
        command="measured qualification test",
        qualified_at=QUALIFIED_AT,
    )


def test_measured_host_qualification_uses_evidence_derived_requirements() -> None:
    payload = build()

    assert payload["status"] == "qualified-measured-reference-host"
    assert payload["qualification"] == {
        "campaign_scratch_required_bytes": 1_642_763_483,
        "canonical_rebuild_required_bytes": 89_995_614_938,
        "feature_peak_rss_bytes": 1_511_342_080,
        "feature_peak_rss_percent_of_ram": "9.172865938",
        "free_space_headroom_bytes": 93_450_924_107,
        "free_space_shortfall_bytes": 0,
        "maximum_layout_peak_rss_bytes": 1_108_500_480,
        "observed_free_bytes": 193_679_237_120,
        "qualified": True,
        "required_free_bytes": 100_228_313_013,
        "same_host_full_scale_evidence": True,
    }
    schema = load_json(qualification.OUTPUT_SCHEMA)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


def test_measured_host_qualification_publishes_auditable_free_space_rejection() -> None:
    payload = build(free_bytes=100_000_000_000)

    assert payload["status"] == "rejected-insufficient-current-free-space"
    assert payload["qualification"]["qualified"] is False
    assert payload["qualification"]["free_space_headroom_bytes"] == 0
    assert payload["qualification"]["free_space_shortfall_bytes"] == 228_313_013


def test_measured_host_qualification_accepts_exact_free_space_boundary() -> None:
    payload = build(free_bytes=100_228_313_013)

    assert payload["qualification"]["qualified"] is True
    assert payload["qualification"]["free_space_headroom_bytes"] == 0
    assert payload["qualification"]["free_space_shortfall_bytes"] == 0


def test_measured_host_qualification_rejects_stale_capacity() -> None:
    with pytest.raises(ValueError, match="older than 24 hours"):
        qualification.build_qualification(
            layout=load_json(LAYOUT),
            feature=load_json(FEATURE),
            capacity=load_json(CAPACITY),
            hardware=observed_hardware(),
            sources=sources(),
            command="stale qualification test",
            qualified_at=datetime(2026, 8, 14, 16, 0, tzinfo=UTC),
        )


def test_source_binding_rejects_cross_host_full_scale_evidence() -> None:
    feature = load_json(FEATURE)
    feature["hardware"]["ram_bytes"] += 1

    with pytest.raises(ValueError, match="does not bind the supplied workstation"):
        qualification._validate_source_bindings(
            layout=load_json(LAYOUT),
            feature=feature,
            capacity=load_json(CAPACITY),
            workstation=load_json(WORKSTATION),
            workstation_path=WORKSTATION,
        )


def test_publish_qualification_writes_receipt_after_all_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "qualification.json"
    monkeypatch.setattr(
        qualification,
        "current_host_observation",
        lambda _workstation, _output: observed_hardware(),
    )

    payload = qualification.publish_qualification(
        layout_path=LAYOUT,
        feature_path=FEATURE,
        capacity_path=CAPACITY,
        workstation_path=WORKSTATION,
        output=output,
        command="publish qualification test",
        qualified_at=QUALIFIED_AT,
    )

    assert payload["status"] == "qualified-measured-reference-host"
    assert verify_evidence(output)


def test_publish_qualification_preserves_auditable_insufficient_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "qualification.json"
    monkeypatch.setattr(
        qualification,
        "current_host_observation",
        lambda _workstation, _output: observed_hardware(free_bytes=100_000_000_000),
    )

    payload = qualification.publish_qualification(
        layout_path=LAYOUT,
        feature_path=FEATURE,
        capacity_path=CAPACITY,
        workstation_path=WORKSTATION,
        output=output,
        command="insufficient qualification test",
        qualified_at=QUALIFIED_AT,
    )

    assert payload["status"] == "rejected-insufficient-current-free-space"
    assert verify_evidence(output)


def test_invalid_source_does_not_replace_existing_qualification(tmp_path: Path) -> None:
    feature_path = tmp_path / "feature.json"
    feature = load_json(FEATURE)
    feature["hardware"]["ram_bytes"] += 1
    publish_evidence(feature_path, feature)
    output = tmp_path / "qualification.json"
    publish_evidence(output, {"preserved": True})

    with pytest.raises(ValueError, match="does not bind the supplied workstation"):
        qualification.publish_qualification(
            layout_path=LAYOUT,
            feature_path=feature_path,
            capacity_path=CAPACITY,
            workstation_path=WORKSTATION,
            output=output,
            force=True,
            command="invalid source test",
            qualified_at=QUALIFIED_AT,
        )

    assert load_json(output) == {"preserved": True}
    assert verify_evidence(output)


def test_admit_measured_qualification_rechecks_current_identity_and_free_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "qualification.json"
    publish_evidence(artifact, build())
    hardware = observed_hardware()
    monkeypatch.setattr(
        qualification,
        "current_hardware",
        lambda: qualification._basic_hardware(hardware),
    )
    monkeypatch.setattr(qualification, "cpu_model", lambda: hardware["cpu_model"])
    monkeypatch.setattr(
        qualification,
        "storage_identity",
        lambda _volume: (hardware["storage_kind"], hardware["storage_model"]),
    )
    monkeypatch.setattr(
        qualification.psutil,
        "disk_usage",
        lambda _volume: SimpleNamespace(
            free=hardware["volume_free_bytes"],
            total=hardware["volume_total_bytes"],
        ),
    )
    monkeypatch.setattr(
        qualification,
        "volume_root_for_path",
        lambda _path: Path(hardware["volume_root"]).resolve(),
    )

    admitted = qualification.admit_measured_host_qualification(
        artifact,
        required_volume_path=tmp_path,
        admitted_at=QUALIFIED_AT,
    )

    assert admitted["artifact_sha256"]
    assert admitted["status"] == "qualified-measured-reference-host"


def test_admit_measured_qualification_rejects_free_space_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "qualification.json"
    publish_evidence(artifact, build())
    hardware = observed_hardware()
    monkeypatch.setattr(
        qualification,
        "current_hardware",
        lambda: qualification._basic_hardware(hardware),
    )
    monkeypatch.setattr(qualification, "cpu_model", lambda: hardware["cpu_model"])
    monkeypatch.setattr(
        qualification,
        "storage_identity",
        lambda _volume: (hardware["storage_kind"], hardware["storage_model"]),
    )
    monkeypatch.setattr(
        qualification.psutil,
        "disk_usage",
        lambda _volume: SimpleNamespace(
            free=100_000_000_000,
            total=hardware["volume_total_bytes"],
        ),
    )

    with pytest.raises(ValueError, match="no longer has the required"):
        qualification.admit_measured_host_qualification(
            artifact,
            admitted_at=QUALIFIED_AT,
        )


def test_admit_measured_qualification_rejects_stale_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "qualification.json"
    publish_evidence(artifact, build())

    with pytest.raises(ValueError, match="older than 24 hours"):
        qualification.admit_measured_host_qualification(
            artifact,
            admitted_at=datetime(2026, 8, 14, 16, 0, tzinfo=UTC),
        )
