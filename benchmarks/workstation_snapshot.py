"""Publish a small, reproducible workstation-capacity snapshot for Gate 1."""

from __future__ import annotations

import argparse
import platform
import re
import shlex
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import psutil  # type: ignore[import-untyped]
from grid_data.evidence import preflight_evidence, publish_evidence

GIB = 1024**3
TIB = 1024**4


def windows_registry_value(key_path: str, value_name: str) -> str | None:
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            value, _value_type = winreg.QueryValueEx(key, value_name)
    except OSError:
        return None
    return str(value).strip()


def cpu_model() -> str:
    registry_model = windows_registry_value(
        r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString"
    )
    return registry_model or platform.processor() or platform.machine()


def storage_identity() -> tuple[str, str]:
    registry_identity = windows_registry_value(r"SYSTEM\CurrentControlSet\Services\disk\Enum", "0")
    raw_identity = registry_identity or "not-observed"
    normalized = raw_identity.casefold()
    if "nvme" in normalized:
        storage_kind = "nvme"
    elif "ssd" in normalized:
        storage_kind = "ssd"
    elif "usb" in normalized:
        storage_kind = "usb"
    else:
        storage_kind = "unknown"
    model_match = re.search(r"Ven_([^&\\]+)&Prod_([^\\]+)", raw_identity)
    if model_match:
        vendor, product = model_match.groups()
        public_model = f"{vendor} {product}".replace("_", " ").strip()
    else:
        public_model = "not-observed"
    return storage_kind, public_model


def profile_assessment(
    physical_cores: int | None,
    ram_bytes: int,
    disk_total_bytes: int,
    storage_kind: str,
) -> dict[str, Any]:
    core_count = physical_cores or 0
    local_failures: list[str] = []
    if core_count < 8:
        local_failures.append("fewer than 8 observed physical CPU cores")
    if ram_bytes < 32 * GIB:
        local_failures.append("less than 32 GiB RAM")
    if storage_kind != "nvme":
        local_failures.append("NVMe storage was not observed")
    if disk_total_bytes < TIB:
        local_failures.append("less than 1 TiB on the measured volume")

    reference_failures: list[str] = []
    if core_count < 16:
        reference_failures.append("fewer than 16 observed physical CPU cores")
    if ram_bytes < 64 * GIB:
        reference_failures.append("less than 64 GiB RAM")
    if storage_kind != "nvme":
        reference_failures.append("NVMe storage was not observed")
    if disk_total_bytes < 2 * TIB:
        reference_failures.append("less than 2 TiB on the measured volume")

    return {
        "documented_local_feasibility_profile": {
            "meets": not local_failures,
            "observed_shortfalls": local_failures,
            "requirements": {
                "minimum_physical_cores": 8,
                "minimum_ram_bytes": 32 * GIB,
                "minimum_volume_bytes": TIB,
                "storage_kind": "nvme",
            },
        },
        "documented_full_research_profile": {
            "meets": not reference_failures,
            "observed_shortfalls": reference_failures,
            "requirements": {
                "minimum_physical_cores": 16,
                "minimum_ram_bytes": 64 * GIB,
                "minimum_volume_bytes": 2 * TIB,
                "storage_kind": "nvme",
            },
        },
    }


def build_snapshot(output: Path) -> dict[str, Any]:
    memory = psutil.virtual_memory()
    volume_root = output.anchor or Path.cwd().anchor
    disk = psutil.disk_usage(volume_root)
    physical_cores = psutil.cpu_count(logical=False)
    storage_kind, storage_model = storage_identity()
    assessment = profile_assessment(
        physical_cores,
        memory.total,
        disk.total,
        storage_kind,
    )
    return {
        "assessment": assessment,
        "evidence_schema": "grid.workstation-snapshot/v1",
        "hardware": {
            "cpu_count_logical": psutil.cpu_count(logical=True),
            "cpu_count_physical": physical_cores,
            "cpu_model": cpu_model(),
            "machine": platform.machine(),
            "platform": platform.platform(),
            "ram_bytes": memory.total,
            "storage_kind": storage_kind,
            "storage_model": storage_model,
            "volume_free_bytes": disk.free,
            "volume_root": volume_root,
            "volume_total_bytes": disk.total,
        },
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "recommendation": [
            "Use this machine only for smoke/scaled evidence when either documented profile fails.",
            "Run the Gate 1 full matrix on 16-32 physical/high-performance cores, 64-128 GiB "
            "RAM, and at least 2 TiB NVMe with separate backup capacity.",
            "Do not treat synthetic compression ratios as a hardware-purchase guarantee.",
        ],
        "software": {
            "psutil": version("psutil"),
            "python": platform.python_version(),
        },
        "status": (
            "meets-documented-full-research-profile"
            if assessment["documented_full_research_profile"]["meets"]
            else "below-documented-full-research-profile"
        ),
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    output, _receipt = preflight_evidence(args.output, force=args.force)
    payload = build_snapshot(output)
    payload["command"] = shlex.join(sys.argv)
    publish_evidence(output, payload, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
