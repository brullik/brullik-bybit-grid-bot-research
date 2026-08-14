from __future__ import annotations

import json
from pathlib import Path

import pytest
from grid_contracts.canonical import canonical_sha256
from grid_data.evidence import publish_evidence, verify_evidence
from jsonschema import Draft202012Validator, FormatChecker

from benchmarks.gate2_readiness_pack import Gate2ReadinessError
from benchmarks.gate2_readiness_pack_v2 import build_gate2_readiness_pack_v2, main

ROOT = Path(__file__).parents[2]
IMPLEMENTATION_IDENTITY = f"git:{'b' * 40}"


def _build(**overrides: object) -> dict[str, object]:
    arguments: dict[str, object] = {
        "generated_at_utc": "2026-08-14T12:00:00Z",
        "implementation_identity": IMPLEMENTATION_IDENTITY,
        "repo_root": ROOT,
    }
    arguments.update(overrides)
    return build_gate2_readiness_pack_v2(**arguments)  # type: ignore[arg-type]


def test_gate2_readiness_pack_v2_retires_only_obsolete_blockers() -> None:
    payload = _build()
    schema = json.loads(
        (ROOT / "schemas/evidence/v2/gate2-readiness-pack.schema.json").read_text(encoding="utf-8")
    )

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    content_sha256 = hash_input.pop("content_sha256")
    assert content_sha256 == canonical_sha256(hash_input)
    assert payload["status"] == "blocked-pending-gate2-evidence-and-policy"
    assert payload["readiness_counts"] == {
        "blocked_criterion_count": 3,
        "criterion_count": 6,
        "evidence_ready_criterion_count": 3,
    }
    gate = payload["gate_2"]
    assert gate["status"] == "closed-pending-data-quality-owner"
    assert gate["automatic_phase3_authorization"] is False
    assert gate["data_quality_owner_decision_required"] is True
    assert len(gate["blocker_codes"]) == 7
    assert "full-history-campaign-incomplete" not in gate["blocker_codes"]
    assert "full-history-canonical-publication-and-audit-missing" not in gate["blocker_codes"]
    assert set(payload["sources"]) == {
        "announcement-archive-depth",
        "canonical-integrity-fault-injection",
        "coverage-audit-100x31",
        "full-history-boundary-diagnostic",
        "full-history-canonical-publication",
        "full-history-coverage-audit",
        "full-history-landing",
        "full-history-preflight-performance",
        "incremental-catalog-performance",
        "instrument-timeline-current-policy",
        "stale-output-fault-injection",
        "trade-compaction-50x90",
    }
    rendered = json.dumps(payload).lower()
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        '"authorization":',
        '"symbol"',
        '"instrument_id"',
        '"dataset_id"',
        '"runtime_path"',
        '"funding_rate"',
    ):
        assert forbidden not in rendered


def test_gate2_readiness_pack_v2_rejects_resealed_source_substitution(tmp_path: Path) -> None:
    original = json.loads(
        (
            ROOT / "benchmarks/results/m2-announcement-archive-depth-oldest-5-20260814.json"
        ).read_text(encoding="utf-8")
    )
    original["generated_at_utc"] = "2026-08-14T12:01:00Z"
    original.pop("content_sha256")
    original["content_sha256"] = canonical_sha256(original)
    substituted = tmp_path / "m2-announcement-archive-depth-oldest-5-20260814.json"
    publish_evidence(substituted, original)

    with pytest.raises(Gate2ReadinessError, match="source artifact hash changed"):
        _build(source_paths={"announcement-archive-depth": substituted})


def test_gate2_readiness_pack_v2_rejects_changed_criteria_source(tmp_path: Path) -> None:
    original = (ROOT / "docs/14_ROADMAP_AND_GATES.md").read_text(encoding="utf-8")
    changed = original.replace(
        "- stale building outputs detected;",
        "- stale building outputs may be ignored;",
    )
    criteria_path = tmp_path / "14_ROADMAP_AND_GATES.md"
    criteria_path.write_text(changed, encoding="utf-8")

    with pytest.raises(Gate2ReadinessError, match="criteria source hash changed"):
        _build(criteria_path=criteria_path)


def test_gate2_readiness_pack_v2_cli_publishes_negative_evidence_and_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "gate2-readiness-v2.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "gate2-readiness-pack-v2",
            "--implementation-identity",
            IMPLEMENTATION_IDENTITY,
            "--output",
            str(output),
            "--repo-root",
            str(ROOT),
        ],
    )

    assert main() == 2
    assert verify_evidence(output)
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == (
        "blocked-pending-gate2-evidence-and-policy"
    )
