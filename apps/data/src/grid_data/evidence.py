"""Atomic publication of small public feasibility evidence bundles."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from grid_contracts.canonical import canonical_json_bytes, sha256_file


class EvidencePublicationError(RuntimeError):
    pass


def preflight_evidence(output: Path, *, force: bool = False) -> tuple[Path, Path]:
    """Resolve an evidence target and reject conflicting committed output before work starts."""

    output = output.resolve()
    receipt = output.with_suffix(output.suffix + ".receipt.json")
    if output.exists() and not force:
        raise EvidencePublicationError(f"refusing to overwrite existing evidence: {output}")
    if receipt.exists() and not force:
        raise EvidencePublicationError(f"refusing to overwrite existing receipt: {receipt}")
    if output.exists() and not output.is_file():
        raise EvidencePublicationError(f"evidence target is not a file: {output}")
    if receipt.exists() and not receipt.is_file():
        raise EvidencePublicationError(f"receipt target is not a file: {receipt}")
    return output, receipt


def publish_evidence(output: Path, payload: Any, *, force: bool = False) -> tuple[Path, Path]:
    """Preflight, atomically publish evidence, then write its receipt last."""

    output, receipt = preflight_evidence(output, force=force)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.parent.is_dir():
        raise EvidencePublicationError("evidence parent is not a directory")

    _atomic_write(output, canonical_json_bytes(payload) + b"\n")
    evidence_hash = sha256_file(output)
    receipt_payload = {
        "artifact": output.name,
        "artifact_sha256": evidence_hash,
        "receipt_schema": "grid.evidence-receipt/v1",
        "status": "complete",
    }
    _atomic_write(receipt, canonical_json_bytes(receipt_payload) + b"\n")
    return output, receipt


def verify_evidence(output: Path) -> bool:
    output = output.resolve()
    receipt = output.with_suffix(output.suffix + ".receipt.json")
    if not output.is_file() or not receipt.is_file():
        return False
    try:
        raw = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(
        raw.get("receipt_schema") == "grid.evidence-receipt/v1"
        and raw.get("status") == "complete"
        and raw.get("artifact") == output.name
        and raw.get("artifact_sha256") == sha256_file(output)
    )


def _atomic_write(target: Path, data: bytes) -> None:
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".building",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
