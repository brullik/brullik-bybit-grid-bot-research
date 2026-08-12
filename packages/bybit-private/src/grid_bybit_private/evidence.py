"""Private probe evidence stays under ignored reports/private and commits with a receipt."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from grid_contracts.canonical import canonical_json_bytes, sha256_file


class PrivateEvidenceError(RuntimeError):
    pass


def resolve_private_output(output: Path, *, root: Path | None = None) -> Path:
    workspace = (root or Path.cwd()).resolve()
    allowed = (workspace / "reports" / "private").resolve()
    resolved = (workspace / output).resolve() if not output.is_absolute() else output.resolve()
    if not resolved.is_relative_to(allowed) or resolved.suffix != ".json":
        raise PrivateEvidenceError("probe output must be a JSON file under reports/private")
    receipt = _receipt_path(resolved)
    if resolved.exists() or receipt.exists():
        raise PrivateEvidenceError("refusing to overwrite existing private probe evidence")
    return resolved


def publish_private_report(output: Path, report: Any) -> tuple[Path, Path]:
    output = resolve_private_output(output)
    receipt = _receipt_path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(output, canonical_json_bytes(report) + b"\n")
    _atomic_write(
        receipt,
        canonical_json_bytes(
            {
                "artifact": output.name,
                "artifact_sha256": sha256_file(output),
                "receipt_schema": "grid.private-evidence-receipt/v1",
                "status": "complete",
            }
        )
        + b"\n",
    )
    return output, receipt


def verify_private_report(output: Path) -> bool:
    output = output.resolve()
    receipt = _receipt_path(output)
    if not output.is_file() or not receipt.is_file():
        return False
    try:
        raw = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(
        raw.get("receipt_schema") == "grid.private-evidence-receipt/v1"
        and raw.get("status") == "complete"
        and raw.get("artifact") == output.name
        and raw.get("artifact_sha256") == sha256_file(output)
    )


def _receipt_path(output: Path) -> Path:
    return output.with_suffix(output.suffix + ".receipt.json")


def _atomic_write(target: Path, data: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".building",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
