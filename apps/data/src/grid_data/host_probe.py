"""Fresh local-memory and storage observation for Phase 2 write preflights."""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import psutil  # type: ignore[import-untyped]
from grid_market_store import HostSnapshot

SYS_BLOCK_ROOT = Path("/sys/class/block")


class HostProbeError(RuntimeError):
    """The current host or target volume cannot be identified safely."""


def _windows_registry_value(key_path: str, value_name: str) -> str | None:
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            value, _value_type = winreg.QueryValueEx(key, value_name)
    except OSError:
        return None
    return str(value).strip()


def _windows_volume_device_number(volume_root: Path) -> int | None:
    if sys.platform != "win32":
        return None
    volume_match = re.fullmatch(r"([A-Za-z]):\\?", str(volume_root))
    if volume_match is None:
        return None

    import ctypes
    from ctypes import wintypes

    class StorageDeviceNumber(ctypes.Structure):
        _fields_ = [
            ("device_type", wintypes.DWORD),
            ("device_number", wintypes.DWORD),
            ("partition_number", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    device_io_control = kernel32.DeviceIoControl
    device_io_control.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    device_io_control.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    handle = create_file(
        rf"\\.\{volume_match.group(1).upper()}:",
        0,
        0x00000001 | 0x00000002,
        None,
        3,
        0,
        None,
    )
    if handle == wintypes.HANDLE(-1).value:
        return None
    try:
        device = StorageDeviceNumber()
        returned = wintypes.DWORD()
        succeeded = device_io_control(
            handle,
            0x002D1080,
            None,
            0,
            ctypes.byref(device),
            ctypes.sizeof(device),
            ctypes.byref(returned),
            None,
        )
        return int(device.device_number) if succeeded else None
    finally:
        close_handle(handle)


def _linux_volume_root(path: Path) -> Path:
    candidates: list[tuple[int, Path]] = []
    for partition in psutil.disk_partitions(all=True):
        mountpoint = Path(partition.mountpoint).resolve()
        if path.is_relative_to(mountpoint):
            candidates.append((len(mountpoint.parts), mountpoint))
    if not candidates:
        raise HostProbeError("cannot resolve the local mount containing the target path")
    return max(candidates)[1]


def volume_root_for_path(path: Path) -> Path:
    """Resolve the mounted volume containing an existing ancestor of the target."""

    resolved = path.resolve()
    existing = resolved
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    if not existing.is_dir() or existing.is_symlink():
        raise HostProbeError("target requires an existing non-symlink directory ancestor")
    if sys.platform.startswith("linux"):
        return _linux_volume_root(existing)
    if sys.platform == "win32":
        root = Path(existing.anchor).resolve()
        if root.is_dir():
            return root
    raise HostProbeError(f"unsupported platform for stable storage probing: {sys.platform}")


def _linux_storage_identity(volume_root: Path) -> tuple[str, str]:
    matching = [
        partition
        for partition in psutil.disk_partitions(all=True)
        if Path(partition.mountpoint).resolve() == volume_root
    ]
    if len(matching) != 1:
        raise HostProbeError("target volume does not map to one Linux block device")
    device_name = Path(matching[0].device).name
    partition_match = re.fullmatch(
        r"(?P<base>nvme\d+n\d+|mmcblk\d+)p\d+|(?P<disk>[a-zA-Z]+)\d+",
        device_name,
    )
    block_name = (
        (partition_match.group("base") or partition_match.group("disk"))
        if partition_match
        else device_name
    )
    if not block_name:
        raise HostProbeError("cannot identify the Linux block device")
    block_root = SYS_BLOCK_ROOT / block_name
    try:
        model = (block_root / "device" / "model").read_text(encoding="utf-8").strip()
    except OSError:
        model = block_name
    if block_name.startswith("nvme"):
        kind = "nvme"
    else:
        try:
            rotational = (block_root / "queue" / "rotational").read_text(encoding="utf-8").strip()
        except OSError:
            rotational = "unknown"
        kind = "ssd" if rotational == "0" else "unknown"
    return kind, f"{block_name}:{model or block_name}"


def _windows_storage_identity(volume_root: Path) -> tuple[str, str]:
    device_number = _windows_volume_device_number(volume_root)
    if device_number is None:
        raise HostProbeError("cannot resolve the Windows physical device number")
    raw_identity = _windows_registry_value(
        r"SYSTEM\CurrentControlSet\Services\disk\Enum", str(device_number)
    )
    if not raw_identity:
        raise HostProbeError("cannot read the Windows storage device identity")
    normalized = raw_identity.casefold()
    if "nvme" in normalized:
        kind = "nvme"
    elif "ssd" in normalized:
        kind = "ssd"
    else:
        kind = "unknown"
    return kind, f"physical-drive-{device_number}:{raw_identity}"


def probe_host_snapshot(target: Path) -> HostSnapshot:
    """Capture fresh RAM, local device identity, and current free bytes for target."""

    volume_root = volume_root_for_path(target)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(str(volume_root))
    if sys.platform == "win32":
        storage_kind, device_id = _windows_storage_identity(volume_root)
    elif sys.platform.startswith("linux"):
        storage_kind, device_id = _linux_storage_identity(volume_root)
    else:
        raise HostProbeError(f"unsupported platform for storage identity: {sys.platform}")
    return HostSnapshot(
        observed_at_ms=time.time_ns() // 1_000_000,
        memory_total_bytes=int(memory.total),
        memory_available_bytes=int(memory.available),
        storage_kind=storage_kind,
        storage_device_id=device_id,
        volume_root=volume_root,
        volume_free_bytes=int(disk.free),
    )
