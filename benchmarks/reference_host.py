"""Fail-closed admission of a receipt-verified Gate 1 reference workstation."""

from __future__ import annotations

import json
import platform
from collections.abc import Mapping
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import psutil  # type: ignore[import-untyped]
from grid_contracts.canonical import sha256_file
from grid_data.evidence import verify_evidence

from benchmarks.workstation_snapshot import (
    GIB,
    TIB,
    cpu_model,
    storage_identity,
    volume_root_for_path,
)

WORKSTATION_SCHEMA = "grid.workstation-snapshot/v1"


def current_hardware() -> dict[str, Any]:
    """Return stable host fields that must match the captured snapshot exactly."""

    memory = psutil.virtual_memory()
    return {
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "machine": platform.machine(),
        "platform": platform.platform(),
        "ram_bytes": memory.total,
    }


def _load_snapshot(path: Path) -> dict[str, Any]:
    path = path.resolve()
    if not verify_evidence(path):
        raise ValueError(f"evidence receipt does not verify: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"workstation evidence is not valid JSON: {path}") from error
    if not isinstance(payload, dict) or payload.get("evidence_schema") != WORKSTATION_SCHEMA:
        raise ValueError(f"unsupported workstation evidence schema in {path}")
    return payload


def admit_reference_host(
    path: Path,
    *,
    required_volume_path: Path | None = None,
) -> dict[str, Any]:
    """Verify profile, current host identity, measured volume, and snapshot runtime."""

    path = path.resolve()
    payload = _load_snapshot(path)
    assessment = payload.get("assessment")
    hardware = payload.get("hardware")
    software = payload.get("software")
    full_profile = (
        assessment.get("documented_full_research_profile")
        if isinstance(assessment, Mapping)
        else None
    )
    if (
        payload.get("status") != "meets-documented-full-research-profile"
        or not isinstance(full_profile, Mapping)
        or full_profile.get("meets") is not True
        or not isinstance(hardware, Mapping)
        or not isinstance(software, Mapping)
    ):
        raise ValueError("reference host evidence does not meet the documented full profile")

    logical_cores = hardware.get("cpu_count_logical")
    physical_cores = hardware.get("cpu_count_physical")
    ram_bytes = hardware.get("ram_bytes")
    volume_total_bytes = hardware.get("volume_total_bytes")
    volume_root = hardware.get("volume_root")
    required_text_fields = (
        "cpu_model",
        "machine",
        "platform",
        "storage_model",
    )
    if (
        isinstance(logical_cores, bool)
        or not isinstance(logical_cores, int)
        or logical_cores < 1
        or isinstance(physical_cores, bool)
        or not isinstance(physical_cores, int)
        or physical_cores < 16
        or isinstance(ram_bytes, bool)
        or not isinstance(ram_bytes, int)
        or ram_bytes < 64 * GIB
        or hardware.get("storage_kind") != "nvme"
        or isinstance(volume_total_bytes, bool)
        or not isinstance(volume_total_bytes, int)
        or volume_total_bytes < 2 * TIB
        or not isinstance(volume_root, str)
        or not volume_root
        or any(
            not isinstance(hardware.get(field), str) or not hardware.get(field)
            for field in required_text_fields
        )
    ):
        raise ValueError("reference host evidence has invalid full-profile hardware values")

    evidence_volume = Path(volume_root).resolve()
    if required_volume_path is not None:
        work_volume = volume_root_for_path(required_volume_path)
        if work_volume != evidence_volume:
            raise ValueError("reference work directory is not on the measured workstation volume")

    current = current_hardware()
    identity_fields = (
        "cpu_count_logical",
        "cpu_count_physical",
        "machine",
        "platform",
        "ram_bytes",
    )
    if any(hardware.get(field) != current.get(field) for field in identity_fields):
        raise ValueError("reference workstation evidence does not match the current host")
    current_storage_kind, current_storage_model = storage_identity(evidence_volume)
    if (
        hardware.get("cpu_model") != cpu_model()
        or hardware.get("storage_kind") != current_storage_kind
        or hardware.get("storage_model") != current_storage_model
        or psutil.disk_usage(str(evidence_volume)).total != volume_total_bytes
    ):
        raise ValueError("reference workstation identity or measured volume changed")

    if software.get("python") != platform.python_version() or software.get("psutil") != version(
        "psutil"
    ):
        raise ValueError("reference workstation snapshot runtime does not match the current run")

    observed_at_utc = payload.get("observed_at_utc")
    try:
        observed_at = datetime.fromisoformat(str(observed_at_utc).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("reference workstation evidence timestamp is invalid") from error
    if observed_at.tzinfo is None or observed_at > datetime.now(UTC):
        raise ValueError("reference workstation evidence timestamp is naive or in the future")

    return {
        "artifact": path.name,
        "artifact_sha256": sha256_file(path),
        "evidence_schema": WORKSTATION_SCHEMA,
        "hardware": {
            "cpu_count_logical": logical_cores,
            "cpu_count_physical": physical_cores,
            "cpu_model": hardware["cpu_model"],
            "machine": hardware["machine"],
            "platform": hardware["platform"],
            "ram_bytes": ram_bytes,
            "storage_kind": hardware["storage_kind"],
            "storage_model": hardware["storage_model"],
            "volume_root": volume_root,
            "volume_total_bytes": volume_total_bytes,
        },
        "observed_at_utc": observed_at_utc,
        "status": payload["status"],
    }
