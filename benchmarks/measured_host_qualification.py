"""Build append-only ADR-0019 evidence for a measured Gate 1 host candidate."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import psutil  # type: ignore[import-untyped]
from grid_contracts.canonical import sha256_file
from grid_data.evidence import preflight_evidence, publish_evidence, verify_evidence
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

from benchmarks.reference_host import current_hardware
from benchmarks.workstation_snapshot import GIB, cpu_model, storage_identity, volume_root_for_path

ROOT = Path(__file__).resolve().parents[1]
LAYOUT_SCHEMA = ROOT / "schemas" / "evidence" / "v3" / "layout-benchmark.schema.json"
FEATURE_SCHEMA = ROOT / "schemas" / "evidence" / "v1" / "feature-benchmark.schema.json"
CAPACITY_SCHEMA = ROOT / "schemas" / "evidence" / "v1" / "current-universe-capacity.schema.json"
WORKSTATION_SCHEMA = ROOT / "schemas" / "evidence" / "v1" / "workstation-snapshot.schema.json"
OUTPUT_SCHEMA = ROOT / "schemas" / "evidence" / "v1" / "reference-host-qualification.schema.json"
MINIMUM_ROWS = 99_999_900
MINIMUM_INSTRUMENTS = 700
MAXIMUM_FEATURE_MEMORY_PERCENT = Decimal("70")
OPERATING_RESERVE_BYTES = 8 * GIB
ALLOWED_STORAGE_KINDS = ("nvme", "ssd")
MAXIMUM_CAPACITY_AGE = timedelta(hours=24)


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
    resolved = path.resolve()
    if not verify_evidence(resolved):
        raise ValueError(f"source evidence receipt does not verify: {resolved}")
    payload = _load_json(resolved)
    _validate(payload, schema_path, label=str(resolved))
    return payload


def _decimal(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"{label} is not an exact decimal") from error
    if not result.is_finite() or result < 0:
        raise ValueError(f"{label} must be finite and non-negative")
    return result


def _source(path: Path, payload: dict[str, Any], schema_key: str) -> dict[str, str]:
    resolved = path.resolve()
    return {
        "artifact": resolved.name,
        "artifact_sha256": sha256_file(resolved),
        "schema": str(payload[schema_key]),
        "status": str(payload["status"]),
    }


def _basic_hardware(hardware: dict[str, Any]) -> dict[str, Any]:
    return {
        key: hardware[key]
        for key in (
            "cpu_count_logical",
            "cpu_count_physical",
            "machine",
            "platform",
            "ram_bytes",
        )
    }


def _layout_key(layout: dict[str, Any]) -> str:
    return json.dumps(layout, sort_keys=True, separators=(",", ":"))


def _campaign_scratch(layout: dict[str, Any]) -> tuple[int, int]:
    by_layout = {_layout_key(item["layout"]): item for item in layout["results"]}
    if len(by_layout) != len(layout["results"]):
        raise ValueError("layout result matrix contains duplicate layout identities")
    shortlist = layout["decision"]["reference_rerun_shortlist"]
    if len(shortlist) != 2:
        raise ValueError("layout qualification requires the complete two-layout shortlist")
    scratch = 0
    peak_rss = 0
    for candidate in shortlist:
        result = by_layout.get(_layout_key(candidate))
        if result is None:
            raise ValueError("layout shortlist is not present in the measured result matrix")
        write = result["write"]
        if (
            write["numeric_schema_verified"] is not True
            or write["target_file_exercised"] is not True
        ):
            raise ValueError("layout shortlist did not verify its exact schema and target scale")
        scratch += int(write["scratch_estimated_layout_bytes"])
        peak_rss = max(peak_rss, int(write["peak_rss_bytes"]))
    return scratch, peak_rss


def _rebuild_requirement(capacity: dict[str, Any]) -> int:
    matches = [
        item
        for item in capacity["disk_headroom"]["scenarios"]
        if item["id"] == "full-rebuild-active-plus-building"
    ]
    if len(matches) != 1:
        raise ValueError("capacity evidence has no unique active-plus-building scenario")
    required = matches[0]["required_bytes"]
    if isinstance(required, bool) or not isinstance(required, int) or required <= 0:
        raise ValueError("capacity rebuild requirement is invalid")
    return required


def _require_fresh_capacity(capacity: dict[str, Any], qualified_at: datetime) -> None:
    if qualified_at.tzinfo is None:
        raise ValueError("qualification timestamp must include a UTC offset")
    try:
        generated_at = datetime.fromisoformat(
            str(capacity["generated_at_utc"]).replace("Z", "+00:00")
        )
    except ValueError as error:
        raise ValueError("capacity evidence timestamp is invalid") from error
    age = qualified_at.astimezone(UTC) - generated_at.astimezone(UTC)
    if age < timedelta() or age > MAXIMUM_CAPACITY_AGE:
        raise ValueError("capacity evidence is future-dated or older than 24 hours")


def _validate_source_bindings(
    *,
    layout: dict[str, Any],
    feature: dict[str, Any],
    capacity: dict[str, Any],
    workstation: dict[str, Any],
    workstation_path: Path,
) -> None:
    expected_hardware = _basic_hardware(workstation["hardware"])
    if layout["hardware"] != expected_hardware or feature["hardware"] != expected_hardware:
        raise ValueError("full-scale evidence does not bind the supplied workstation hardware")
    if (
        layout["status"] != "decision-matrix-candidate"
        or layout["input"]["row_count"] < MINIMUM_ROWS
        or layout["input"]["instrument_count"] != MINIMUM_INSTRUMENTS
    ):
        raise ValueError("layout evidence does not meet the ADR-0019 qualification scale")
    if (
        feature["status"] != "reference-scale-candidate"
        or feature["profile"] != "reference"
        or feature["input"]["row_count"] < MINIMUM_ROWS
        or feature["input"]["instrument_count"] != MINIMUM_INSTRUMENTS
        or feature["result"]["output_rows"] < MINIMUM_ROWS
        or feature["memory_gate"]["passed"] is not True
        or feature["memory_gate"]["configured_limit_percent"] > MAXIMUM_FEATURE_MEMORY_PERCENT
        or _decimal(
            feature["memory_gate"]["peak_rss_percent_of_ram"],
            "feature peak RSS percent",
        )
        > MAXIMUM_FEATURE_MEMORY_PERCENT
    ):
        raise ValueError("feature evidence does not meet the ADR-0019 scale and memory gates")
    workstation_source = capacity["sources"]["workstation"]
    if (
        workstation_source["artifact"] != workstation_path.resolve().name
        or workstation_source["artifact_sha256"] != sha256_file(workstation_path.resolve())
        or workstation_source["schema"] != workstation["evidence_schema"]
        or workstation_source["status"] != workstation["status"]
    ):
        raise ValueError("capacity evidence does not bind the supplied workstation snapshot")
    volume = capacity["disk_headroom"]["volume"]
    if any(
        volume[key] != workstation["hardware"][key]
        for key in (
            "storage_kind",
            "storage_model",
            "volume_free_bytes",
            "volume_root",
            "volume_total_bytes",
        )
    ):
        raise ValueError("capacity evidence and workstation describe different measured volumes")


def current_host_observation(workstation: dict[str, Any], output: Path) -> dict[str, Any]:
    hardware = workstation["hardware"]
    evidence_volume = Path(hardware["volume_root"]).resolve()
    if volume_root_for_path(output) != evidence_volume:
        raise ValueError("qualification output is not on the measured workstation volume")
    if current_hardware() != _basic_hardware(hardware):
        raise ValueError("workstation evidence does not match the current host")
    current_kind, current_model = storage_identity(evidence_volume)
    disk = psutil.disk_usage(str(evidence_volume))
    if (
        hardware["cpu_model"] != cpu_model()
        or current_kind not in ALLOWED_STORAGE_KINDS
        or hardware["storage_kind"] != current_kind
        or hardware["storage_model"] != current_model
        or hardware["volume_total_bytes"] != disk.total
    ):
        raise ValueError("current host or local non-rotating volume identity changed")
    return {
        **_basic_hardware(hardware),
        "cpu_model": hardware["cpu_model"],
        "storage_kind": current_kind,
        "storage_model": current_model,
        "volume_free_bytes": disk.free,
        "volume_root": hardware["volume_root"],
        "volume_total_bytes": disk.total,
    }


def build_qualification(
    *,
    layout: dict[str, Any],
    feature: dict[str, Any],
    capacity: dict[str, Any],
    hardware: dict[str, Any],
    sources: dict[str, dict[str, str]],
    command: str,
    qualified_at: datetime,
) -> dict[str, Any]:
    _require_fresh_capacity(capacity, qualified_at)
    scratch_bytes, layout_peak_rss = _campaign_scratch(layout)
    rebuild_bytes = _rebuild_requirement(capacity)
    required_free = rebuild_bytes + scratch_bytes + OPERATING_RESERVE_BYTES
    observed_free = int(hardware["volume_free_bytes"])
    qualified = observed_free >= required_free
    payload = {
        "command": command,
        "evidence_schema": "grid.reference-host-qualification/v1",
        "gate_1": {
            "automatic_acceptance": False,
            "owner_decision_required": True,
            "status": "pending-owner-decision",
        },
        "hardware": hardware,
        "limitations": [
            "Qualification does not prove the pinned Python 3.12 environment; the environment "
            "doctor remains mandatory.",
            "Qualification does not run the reboot-separated cold-cache reference measurements.",
            "Phase 2 downloader staging is not included and requires its own bounded free-space "
            "addition.",
            "This artifact cannot accept Gate 1, authorize Phase 2, or select P-001 through P-005.",
        ],
        "policy": {
            "allowed_storage_kinds": list(ALLOWED_STORAGE_KINDS),
            "free_space_formula": (
                "canonical-active-plus-building + retained-reference-layout-scratch + "
                "operating-reserve"
            ),
            "maximum_feature_memory_percent": 70,
            "minimum_instruments": MINIMUM_INSTRUMENTS,
            "minimum_rows": MINIMUM_ROWS,
            "operating_reserve_bytes": OPERATING_RESERVE_BYTES,
        },
        "qualified_at_utc": qualified_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "qualification": {
            "campaign_scratch_required_bytes": scratch_bytes,
            "canonical_rebuild_required_bytes": rebuild_bytes,
            "feature_peak_rss_bytes": int(feature["result"]["peak_rss_bytes"]),
            "feature_peak_rss_percent_of_ram": str(
                feature["memory_gate"]["peak_rss_percent_of_ram"]
            ),
            "free_space_headroom_bytes": max(0, observed_free - required_free),
            "free_space_shortfall_bytes": max(0, required_free - observed_free),
            "maximum_layout_peak_rss_bytes": layout_peak_rss,
            "observed_free_bytes": observed_free,
            "qualified": qualified,
            "required_free_bytes": required_free,
            "same_host_full_scale_evidence": True,
        },
        "sources": sources,
        "status": (
            "qualified-measured-reference-host"
            if qualified
            else "rejected-insufficient-current-free-space"
        ),
    }
    _validate(payload, OUTPUT_SCHEMA, label="measured host qualification")
    return payload


def publish_qualification(
    *,
    layout_path: Path,
    feature_path: Path,
    capacity_path: Path,
    workstation_path: Path,
    output: Path,
    force: bool = False,
    command: str | None = None,
    qualified_at: datetime | None = None,
) -> dict[str, Any]:
    layout = load_verified_evidence(layout_path, LAYOUT_SCHEMA)
    feature = load_verified_evidence(feature_path, FEATURE_SCHEMA)
    capacity = load_verified_evidence(capacity_path, CAPACITY_SCHEMA)
    workstation = load_verified_evidence(workstation_path, WORKSTATION_SCHEMA)
    _validate_source_bindings(
        layout=layout,
        feature=feature,
        capacity=capacity,
        workstation=workstation,
        workstation_path=workstation_path,
    )
    hardware = current_host_observation(workstation, output)
    payload = build_qualification(
        layout=layout,
        feature=feature,
        capacity=capacity,
        hardware=hardware,
        sources={
            "capacity": _source(capacity_path, capacity, "evidence_schema"),
            "feature": _source(feature_path, feature, "benchmark_schema"),
            "layout": _source(layout_path, layout, "benchmark_schema"),
            "workstation": _source(workstation_path, workstation, "evidence_schema"),
        },
        command=shlex.join(sys.argv) if command is None else command,
        qualified_at=datetime.now(UTC) if qualified_at is None else qualified_at,
    )
    output, _receipt = preflight_evidence(output, force=force)
    publish_evidence(output, payload, force=force)
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
        "--capacity",
        type=Path,
        default=Path("benchmarks/results/m1-owner-storage-review-capacity-20260812.json"),
    )
    parser.add_argument(
        "--workstation",
        type=Path,
        default=Path("benchmarks/results/m1-owner-storage-review-workstation-20260812.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    payload = publish_qualification(
        layout_path=args.layout,
        feature_path=args.feature,
        capacity_path=args.capacity,
        workstation_path=args.workstation,
        output=args.output,
        force=args.force,
    )
    return 0 if payload["status"] == "qualified-measured-reference-host" else 2


if __name__ == "__main__":
    raise SystemExit(main())
