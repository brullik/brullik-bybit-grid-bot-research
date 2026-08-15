from __future__ import annotations

import json
from pathlib import Path

from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_data.evidence import verify_evidence
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[2]
ARTIFACT = ROOT / "benchmarks/results/m2-announcement-lifecycle-coverage-20260815.json"
SCHEMA = ROOT / "schemas/evidence/v1/phase2-announcement-lifecycle-coverage.schema.json"


def test_measured_announcement_lifecycle_coverage_is_bound_verified_and_redacted() -> None:
    payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    assert verify_evidence(ARTIFACT)

    content = dict(payload)
    embedded_hash = content.pop("content_sha256")
    assert embedded_hash == canonical_sha256(content)
    assert embedded_hash == "be94ef61b78b4c536907aa0f552418c8628c3163ce3a1f80297c0d64774ced7e"
    artifact_hash = "1d320e030f0aca19eb8455a5de90008b318e11e76269f7feee0af16850b37c06"
    assert sha256_file(ARTIFACT) == artifact_hash

    assert payload["status"] == "verified-partial-official-lifecycle-evidence"
    assert payload["scope"] == {
        "campaign_request_count": 3,
        "closed_instrument_count": 303,
        "delivered_instrument_count": 303,
        "prelaunch_instrument_count": 3,
        "selected_instrument_count": 981,
        "trading_instrument_count": 675,
    }
    assert payload["process"] == {
        "announcement_text_persisted": False,
        "lifecycle_type_count": 2,
        "market_data_request_count": 0,
        "private_endpoint_request_count": 0,
        "response_count": 108,
        "software_identity": "git:a3ebfe9e1fc0ca78220812970343eebf465010e1",
        "transport_max_attempts": 1,
    }
    assert [source["item_count"] for source in payload["archive_sources"]] == [1692, 460]
    assert [source["page_count"] for source in payload["archive_sources"]] == [85, 23]
    assert [
        source["blank_or_missing_description_count"] for source in payload["archive_sources"]
    ] == [101, 13]
    assert payload["matching"]["record_matching_complete"] is False
    assert payload["matching"]["listing"] == {
        "ambiguous_instrument_count": 91,
        "candidate_event_count": 816,
        "eligible_instrument_count": 808,
        "outside_archive_instrument_count": 173,
        "registry_relation": {
            "announcement_after_registry_date_count": 17,
            "announcement_before_registry_date_count": 9,
            "maximum_absolute_utc_date_delta_days": 53,
            "same_utc_date_count": 607,
        },
        "unique_match_instrument_count": 633,
        "unmatched_instrument_count": 84,
    }
    assert payload["matching"]["delisting"] == {
        "ambiguous_instrument_count": 2,
        "candidate_event_count": 259,
        "eligible_instrument_count": 297,
        "outside_archive_instrument_count": 6,
        "registry_relation": {
            "announcement_after_registry_date_count": 0,
            "announcement_before_registry_date_count": 253,
            "maximum_absolute_utc_date_delta_days": 15,
            "same_utc_date_count": 2,
        },
        "unique_match_instrument_count": 255,
        "unmatched_instrument_count": 40,
    }
    assert payload["legacy_evidence"]["remaining_pre_archive_listing_instrument_count"] == 168
    assert payload["blocker_codes"] == [
        "delisting-announcement-match-ambiguous",
        "eligible-delisting-announcement-match-missing",
        "eligible-listing-announcement-match-missing",
        "historical-point-in-time-metadata-still-incomplete",
        "listing-announcement-match-ambiguous",
        "remaining-pre-archive-listing-evidence-missing",
    ]

    receipt = json.loads(ARTIFACT.with_name(f"{ARTIFACT.name}.receipt.json").read_text())
    assert receipt == {
        "artifact": ARTIFACT.name,
        "artifact_sha256": artifact_hash,
        "receipt_schema": "grid.evidence-receipt/v1",
        "status": "complete",
    }
    rendered = json.dumps(payload).lower()
    for forbidden in (
        "announcements.bybit.com",
        '"instrument_id"',
        '"symbol"',
        '"title"',
        '"description"',
        '"tags"',
        "c:\\",
        "api_key",
        "api_secret",
    ):
        assert forbidden not in rendered
