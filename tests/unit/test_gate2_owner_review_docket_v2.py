from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from grid_contracts.canonical import canonical_sha256
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

import benchmarks.gate2_owner_review_docket_v2 as docket_module
from benchmarks.gate2_owner_review_docket_v2 import (
    EXPECTED_BLOCKERS,
    EXPECTED_GATE,
    Gate2OwnerReviewDocketV2Error,
    build_gate2_owner_review_docket_v2,
)
from tests.unit.test_gate2_readiness_pack_v6 import _build as build_v6

ROOT = Path(__file__).parents[2]
IMPLEMENTATION = f"git:{'c' * 40}"


def _build(
    monkeypatch: pytest.MonkeyPatch,
    *,
    mutate: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    source = build_v6(monkeypatch)
    if mutate is not None:
        mutate(source)
    source_record = {
        "artifact": "m2-gate2-readiness-pack-v6.json",
        "artifact_sha256": "d" * 64,
        "content_sha256": "e" * 64,
        "contract": "grid.gate2-readiness-pack/v6",
        "status": "blocked-terminal-funding-evidence-awaiting-owner-decision",
    }
    monkeypatch.setattr(
        docket_module,
        "_verify_source",
        lambda *_arguments, **_keywords: (source, source_record),
    )
    return build_gate2_owner_review_docket_v2(
        implementation_identity=IMPLEMENTATION,
        generated_at_utc="2026-08-24T22:00:00Z",
        readiness_v6_path=Path("readiness-v6.json"),
        repo_root=ROOT,
    )


def test_owner_docket_v2_is_pending_and_assigns_all_blockers_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _build(monkeypatch)
    schema = json.loads(
        (ROOT / "schemas/evidence/v2/gate2-owner-review-docket.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    hash_input = dict(payload)
    embedded = hash_input.pop("content_sha256")
    assert embedded == canonical_sha256(hash_input)
    assert payload["gate_2"] == EXPECTED_GATE
    assert payload["decision_state"] == {
        "data_quality_owner_decision_recorded": False,
        "gate_opening_authorized": False,
        "owner_decision_required": True,
        "phase3_implementation_authorized": False,
        "required_review_item_count": 4,
        "status": "pending",
    }
    items = payload["review_items"]
    assigned = [blocker for item in items.values() for blocker in item["blocker_codes"]]
    assert sorted(assigned) == EXPECTED_BLOCKERS
    assert len(assigned) == len(set(assigned)) == 7
    assert items["deterministic_repair"]["evidence_summary"] == {
        "candle_instrument_count": 2,
        "funding_full_scope_exact": False,
        "funding_predecessor_proven_count": 1,
        "funding_terminal_insufficient_count": 1,
    }
    assert all(item["owner_disposition"] == "pending" for item in items.values())
    assert payload["assurances"]["phase3_authorized"] is False


def test_owner_docket_v2_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    rendered = json.dumps(_build(monkeypatch)).lower()
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        '"symbol"',
        '"instrument_id"',
        '"dataset_id"',
        '"runtime_path"',
        '"funding_rate"',
        '"market_value"',
    ):
        assert forbidden not in rendered


def test_owner_docket_v2_rejects_funding_availability_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(source: dict[str, Any]) -> None:
        source["observations"]["current_universe"]["funding_terminal_insufficient_count"] = 2

    with pytest.raises(Gate2OwnerReviewDocketV2Error, match="do not reconcile"):
        _build(monkeypatch, mutate=mutate)


def test_owner_docket_v2_rejects_prior_owner_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(source: dict[str, Any]) -> None:
        source["observations"]["owner_review"]["funding_availability_owner_disposition"] = (
            "accepted"
        )

    with pytest.raises(Gate2OwnerReviewDocketV2Error, match="owner-review state changed"):
        _build(monkeypatch, mutate=mutate)


def test_owner_docket_v2_cli_returns_two_after_pending_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "owner-review-docket-v2.json"
    published = False

    def publish(**_arguments: object) -> dict[str, Any]:
        nonlocal published
        published = True
        return {
            "decision_state": {"required_review_item_count": 4},
            "status": "pending-terminal-funding-data-quality-owner-decision",
        }

    monkeypatch.setattr(docket_module, "publish_gate2_owner_review_docket_v2", publish)
    monkeypatch.setattr(
        "sys.argv",
        [
            "gate2-owner-review-docket-v2",
            "--implementation-identity",
            IMPLEMENTATION,
            "--readiness-v6",
            "readiness-v6.json",
            "--output",
            str(output),
        ],
    )
    assert docket_module.main() == 2
    assert published
