from __future__ import annotations

import json
from pathlib import Path

from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_data.evidence import verify_evidence
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[2]
ARTIFACT = ROOT / "benchmarks/results/m2-legacy-listing-event-evidence-20260815.json"
SCHEMA = ROOT / "schemas/evidence/v1/phase2-legacy-listing-event-evidence.schema.json"


def test_measured_legacy_listing_event_evidence_is_bound_verified_and_redacted() -> None:
    payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    assert verify_evidence(ARTIFACT)

    content = dict(payload)
    embedded_hash = content.pop("content_sha256")
    assert embedded_hash == canonical_sha256(content)
    assert embedded_hash == "b0d151ca78014ed2017f8ba34968df749271b4fa560c22fbcdce6489741494d7"
    assert sha256_file(ARTIFACT) == (
        "6a243bde1c5051151d22f90eb73af7692ae66bc381fa4a5bf43c484cc6cf7b24"
    )
    assert payload["status"] == "verified-four-exact-and-one-bounded-legacy-listing-event"
    assert payload["bindings"] == {
        "instrument_registry_artifact_sha256": (
            "9e78d2db1cebb33d1b1bf328df2dee3ee3ad9f7c3db6b42ae916c9017a0fa733"
        ),
        "instrument_registry_content_sha256": (
            "6b2c83a87e3fbb9921b89f25aca9d35f7f138c9a58c3d94ac8d0dad133495322"
        ),
        "official_document_contract_sha256": (
            "04e7f2c56cdcbd92abb0a2dc197440a88a823a22bb65a1d6dd00acfd20477543"
        ),
        "publication_manifest_sha256": (
            "ac7991b8cbbe249d8b299b91664a414aa81644a52f3ce4b87876eddf92d9e611"
        ),
        "selected_instrument_set_sha256": (
            "fe4d83f755b9db451a63ba0343a49370c50dc18d5240d85b1ca686da22e360de"
        ),
        "software_identity": "git:7e5708a47b18896c694eb239da26a68232d0f4d0",
        "source_campaign_manifest_sha256": (
            "ae272dff8101577707af5f73785c8243381f7e97b335ffbc232db8b43f3a5379"
        ),
        "source_campaign_plan_sha256": (
            "d7b1eb16ed5e0a44c9749d7d2da7a8675506baf4186c7e75d0ddfc59cbb0343f"
        ),
    }
    selected_counts = [
        item["matched_selected_instrument_count"] for item in payload["official_documents"]
    ]
    assert selected_counts == [1, 3, 1]
    assert [item["official_message_at_ms"] for item in payload["official_documents"]] == [
        1_585_152_190_000,
        1_603_277_098_000,
        1_608_101_734_000,
    ]
    assert payload["quality"] == {
        "mark_first_candle": {
            "event_day_match_count": 2,
            "event_month_match_count": 5,
            "first_candle_after_event_day_count": 0,
            "first_candle_before_event_day_count": 3,
            "maximum_post_event_lag_days": 0,
            "maximum_pre_event_lead_days": 2,
        },
        "official_document_count": 3,
        "official_document_selected_match_count": 5,
        "registry_launch_before_official_message_count": 5,
        "selected_instrument_count": 5,
        "trade_first_candle": {
            "event_day_match_count": 4,
            "event_month_match_count": 5,
            "first_candle_after_event_day_count": 0,
            "first_candle_before_event_day_count": 1,
            "maximum_post_event_lag_days": 0,
            "maximum_pre_event_lead_days": 2,
        },
    }
    receipt = json.loads(ARTIFACT.with_name(f"{ARTIFACT.name}.receipt.json").read_text())
    assert receipt == {
        "artifact": ARTIFACT.name,
        "artifact_sha256": "6a243bde1c5051151d22f90eb73af7692ae66bc381fa4a5bf43c484cc6cf7b24",
        "receipt_schema": "grid.evidence-receipt/v1",
        "status": "complete",
    }
    rendered = json.dumps(payload).lower()
    for forbidden in (
        "btcusdt",
        "linkusdt",
        "ltcusdt",
        "xtzusdt",
        "bchusdt",
        "c:\\",
        '"instrument_id"',
        '"open_time_ms"',
        '"market_value"',
        "api_key",
        "api_secret",
    ):
        assert forbidden not in rendered
