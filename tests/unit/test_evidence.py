from __future__ import annotations

from pathlib import Path

import pytest
from grid_data.evidence import (
    EvidencePublicationError,
    preflight_evidence,
    publish_evidence,
    verify_evidence,
)


def test_receipt_is_written_and_verifies(tmp_path: Path) -> None:
    output = tmp_path / "inventory.json"
    artifact, receipt = publish_evidence(output, {"count": 2})
    assert artifact == output.resolve()
    assert receipt.is_file()
    assert verify_evidence(output)


def test_existing_evidence_is_not_silently_overwritten(tmp_path: Path) -> None:
    output = tmp_path / "inventory.json"
    publish_evidence(output, {"count": 2})
    with pytest.raises(EvidencePublicationError, match="overwrite"):
        publish_evidence(output, {"count": 3})


def test_tampering_invalidates_receipt(tmp_path: Path) -> None:
    output = tmp_path / "inventory.json"
    publish_evidence(output, {"count": 2})
    output.write_text("{}\n", encoding="utf-8")
    assert not verify_evidence(output)


def test_preflight_rejects_a_directory_target_even_with_force(tmp_path: Path) -> None:
    output = tmp_path / "inventory.json"
    output.mkdir()

    with pytest.raises(EvidencePublicationError, match="not a file"):
        preflight_evidence(output, force=True)
