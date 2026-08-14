from __future__ import annotations

import json
from pathlib import Path

import pytest
from grid_contracts.canonical import canonical_sha256
from grid_data.evidence import publish_evidence, verify_evidence
from jsonschema import Draft202012Validator, FormatChecker

from benchmarks.gate2_readiness_pack import Gate2ReadinessError
from benchmarks.gate2_readiness_pack_v3 import build_gate2_readiness_pack_v3, main

ROOT = Path(__file__).parents[2]
IMPLEMENTATION_IDENTITY = f"git:{'c' * 40}"


def _build(**overrides: object) -> dict[str, object]:
    arguments: dict[str, object] = {
        "generated_at_utc": "2026-08-14T13:00:00Z",
        "implementation_identity": IMPLEMENTATION_IDENTITY,
        "repo_root": ROOT,
    }
    arguments.update(overrides)
    return build_gate2_readiness_pack_v3(**arguments)  # type: ignore[arg-type]


def test_gate2_readiness_pack_v3_replaces_only_stale_repair_blockers() -> None:
    payload = _build()
    schema = json.loads(
        (ROOT / "schemas/evidence/v3/gate2-readiness-pack.schema.json").read_text(encoding="utf-8")
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
    assert "genuine-candle-gap-repair-evidence-missing" not in gate["blocker_codes"]
    assert "measured-funding-repair-evidence-missing" not in gate["blocker_codes"]
    assert "candle-repair-source-gap-remains" in gate["blocker_codes"]
    assert "eligible-funding-repair-candidate-unavailable" in gate["blocker_codes"]
    assert len(payload["sources"]) == 15
    assert payload["observations"]["candle_repair"] == {
        "actual_http_request_count": 1,
        "missing_minute_count": 1,
        "observed_row_count": 0,
        "parent_dataset_mutated": False,
        "replacement_dataset_published": False,
        "source_gap_remains": True,
    }
    assert payload["observations"]["funding_repair_candidates"] == {
        "audit_count": 4,
        "candidate_request_count": 0,
        "candidate_requests_executed": False,
        "candidate_settlement_count": 0,
        "eligible_audit_count": 0,
        "interval_change_count": 11,
        "task_count": 0,
    }
    assert payload["observations"]["full_history_catalog"] == {
        "catalog_revision": 5,
        "dataset_count": 978,
        "empty_dataset_count": 268,
        "object_count": 978,
        "required_partition_count": 978,
        "row_count": 30_832_334,
        "selection_union_matches_registration": True,
        "size_bytes": 529_794_759,
        "topology_segment_count": 2,
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


def test_gate2_readiness_pack_v3_rejects_resealed_new_source_substitution(
    tmp_path: Path,
) -> None:
    original = json.loads(
        (ROOT / "benchmarks/results/m2-funding-repair-candidate-audit-20260814.json").read_text(
            encoding="utf-8"
        )
    )
    original["generated_at_utc"] = "2026-08-14T13:01:00Z"
    original.pop("content_sha256")
    original["content_sha256"] = canonical_sha256(original)
    substituted = tmp_path / "m2-funding-repair-candidate-audit-20260814.json"
    publish_evidence(substituted, original)

    with pytest.raises(Gate2ReadinessError, match="source artifact hash changed"):
        _build(source_paths={"funding-repair-candidate-audit": substituted})


def test_gate2_readiness_pack_v3_rejects_changed_criteria_source(tmp_path: Path) -> None:
    original = (ROOT / "docs/14_ROADMAP_AND_GATES.md").read_text(encoding="utf-8")
    changed = original.replace(
        "- stale building outputs detected;",
        "- stale building outputs may be ignored;",
    )
    criteria_path = tmp_path / "14_ROADMAP_AND_GATES.md"
    criteria_path.write_text(changed, encoding="utf-8")

    with pytest.raises(Gate2ReadinessError, match="criteria source hash changed"):
        _build(criteria_path=criteria_path)


def test_gate2_readiness_pack_v3_cli_publishes_negative_evidence_and_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "gate2-readiness-v3.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "gate2-readiness-pack-v3",
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
