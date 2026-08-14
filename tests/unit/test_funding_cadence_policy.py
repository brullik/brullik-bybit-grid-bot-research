from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa  # type: ignore[import-untyped]
import pytest
from grid_contracts.canonical import canonical_sha256
from grid_data.cli import parser
from grid_data.evidence import publish_evidence
from grid_data.funding_cadence_policy import (
    POLICY_EFFECTIVE_AT_MS,
    POLICY_MARKERS,
    POLICY_URL,
    FundingCadencePolicyError,
    OfficialPolicyPage,
    _analyze_series,
    _Observation,
    _verify_policy_page,
    build_funding_cadence_policy_evidence,
)
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[2]
SOFTWARE_IDENTITY = "git:" + "9" * 40
MANIFEST_SHA256 = "8" * 64


class FakePolicyClient:
    transport_max_attempts = 1

    def __init__(self, *, omit_marker: bool = False) -> None:
        markers = list(POLICY_MARKERS)
        if omit_marker:
            markers.pop()
        self.page = OfficialPolicyPage(
            body=("<html><body>" + " ".join(markers) + "</body></html>").encode(),
            content_type="text/html",
            final_url=POLICY_URL,
            status_code=200,
        )
        self.calls = 0

    def fetch_policy_page(self) -> OfficialPolicyPage:
        self.calls += 1
        return self.page


def _observations(
    intervals: list[int],
    *,
    low_rate_indexes: set[int] | None = None,
) -> tuple[_Observation, ...]:
    low_rate_indexes = low_rate_indexes or set()
    timestamp = POLICY_EFFECTIVE_AT_MS + 86_400_000
    result: list[_Observation] = []
    for index, interval in enumerate(intervals):
        timestamp += interval * 60_000
        result.append(
            _Observation(
                funding_time_ms=timestamp,
                funding_rate=(Decimal("0.0001") if index in low_rate_indexes else Decimal("0.001")),
                interval_minutes=interval,
            )
        )
    return tuple(result)


def test_policy_state_machine_accepts_threshold_restoration_bridge_and_open_episode() -> None:
    direct_intervals = [240] * 3 + [60] * 20 + [240] * 3
    direct = _analyze_series(_observations(direct_intervals, low_rate_indexes=set(range(6, 23))))
    assert direct.explained_interval_change_count == 2
    assert direct.unexplained_interval_change_count == 0
    assert direct.completed_hourly_episode_count == 1
    assert direct.qualifying_count_histogram == ((17, 1),)

    bridge_intervals = [60] * 20 + [120] + [480] * 3
    bridge = _analyze_series(_observations(bridge_intervals, low_rate_indexes=set(range(4, 20))))
    assert bridge.explained_interval_change_count == 2
    assert bridge.completed_hourly_episode_count == 1
    assert bridge.qualifying_count_histogram == ((16, 1),)

    open_intervals = [480] * 3 + [60] * 10
    open_episode = _analyze_series(_observations(open_intervals))
    assert open_episode.explained_interval_change_count == 1
    assert open_episode.open_hourly_episode_count == 1
    assert open_episode.open_nonqualifying_hourly_episode_count == 1


def test_policy_state_machine_does_not_hide_missing_or_unqualified_settlement() -> None:
    missing_like_change = _analyze_series(_observations([240] * 3 + [480] + [240] * 3))
    assert missing_like_change.explained_interval_change_count == 0
    assert missing_like_change.unexplained_interval_change_count == 2

    unqualified_exit = _analyze_series(_observations([240] * 3 + [60] * 20 + [240] * 3))
    assert unqualified_exit.explained_interval_change_count == 0
    assert unqualified_exit.unexplained_interval_change_count == 2


def test_official_policy_page_requires_every_exact_marker_and_one_attempt() -> None:
    client = FakePolicyClient()
    page, text = _verify_policy_page(client)
    assert page.final_url == POLICY_URL
    assert all(marker in text for marker in POLICY_MARKERS)
    assert client.calls == 1

    with pytest.raises(FundingCadencePolicyError, match="statements do not verify"):
        _verify_policy_page(FakePolicyClient(omit_marker=True))


def _audit_payload(intervals: list[int]) -> dict[str, object]:
    histogram = Counter(intervals)
    changes = sum(current != previous for previous, current in pairwise(intervals))
    payload: dict[str, object] = {
        "bindings": {"funding_manifest_sha256": MANIFEST_SHA256},
        "content_sha256": "",
        "contract": "grid.canonical-funding-coverage-audit/v1",
        "quality": {
            "canonical_source_table_equal": True,
            "conflicting_key_count": 0,
            "duplicate_key_count": 0,
            "empty_range_page_count": 0,
            "internal_interval_mismatch_count": 0,
            "interval_change_count": changes,
            "lifecycle_failure_count": 0,
            "predecessor_interval_mismatch_count": 0,
            "unexpected_timestamp_count": 0,
            "unrequested_row_count": 0,
        },
        "reason_policy": {
            "accepted_reason_codes": [],
            "observed_reason_counts": {"unexplained_interval_change": changes},
            "unaccepted_reason_codes": ["unexplained_interval_change"],
            "unknown_reason_count": 0,
        },
        "series": [
            {
                "instrument_id": 7,
                "interval_change_count": changes,
                "interval_histogram": [
                    {"event_count": count, "interval_minutes": interval}
                    for interval, count in sorted(histogram.items())
                ],
                "observed_event_count": len(intervals),
                "symbol": "PRIVATEUSDT",
            }
        ],
        "status": "blocked",
    }
    payload["content_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    return payload


def test_builder_binds_receipts_is_schema_valid_and_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intervals = [240] * 3 + [60] * 20 + [240] * 3
    low_indexes = set(range(6, 23))
    rows = _observations(intervals, low_rate_indexes=low_indexes)
    table = pa.table(
        {
            "funding_interval_minutes": pa.array(
                [row.interval_minutes for row in rows], type=pa.uint32()
            ),
            "funding_rate": pa.array(
                [row.funding_rate for row in rows], type=pa.decimal128(38, 18)
            ),
            "funding_time_ms": pa.array([row.funding_time_ms for row in rows], type=pa.int64()),
            "instrument_id": pa.array([7] * len(rows), type=pa.uint32()),
        }
    )
    monkeypatch.setattr(
        "grid_data.funding_cadence_policy.load_verified_completed_funding_batch",
        lambda _path: (
            SimpleNamespace(manifest_sha256=MANIFEST_SHA256),
            SimpleNamespace(table=table),
        ),
    )
    audit, _receipt = publish_evidence(tmp_path / "audit.json", _audit_payload(intervals))
    payload = build_funding_cadence_policy_evidence(
        FakePolicyClient(),
        coverage_audit_paths=(audit,),
        funding_job_roots=(tmp_path / "job",),
        generated_at_utc="2026-08-15T00:00:00Z",
        software_identity=SOFTWARE_IDENTITY,
    )
    schema = json.loads(
        (
            ROOT
            / "schemas"
            / "evidence"
            / "v1"
            / "phase2-funding-cadence-policy-evidence.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    content = dict(payload)
    embedded_hash = content.pop("content_sha256")
    assert embedded_hash == canonical_sha256(content)
    assert payload["status"] == "verified-official-funding-cadence-policy-consistency"
    assert payload["quality"] == {
        "affected_series_count": 1,
        "completed_hourly_episode_count": 1,
        "coverage_audit_count": 1,
        "explained_interval_change_count": 2,
        "hourly_episode_count": 1,
        "observed_interval_change_count": 2,
        "open_hourly_episode_count": 0,
        "open_nonqualifying_hourly_episode_count": 0,
        "policy_consistent_series_count": 1,
        "qualifying_settlement_count_histogram": [
            {"episode_count": 1, "qualifying_settlement_count": 17}
        ],
        "series_count": 1,
        "unexplained_interval_change_count": 0,
    }
    rendered = json.dumps(payload).lower()
    for forbidden in (
        "privateusdt",
        str(tmp_path).lower(),
        '"funding_rate":',
        '"funding_time_ms":',
        '"instrument_id":',
        "api_key",
        "api_secret",
    ):
        assert forbidden not in rendered


def test_cli_exposes_funding_cadence_policy_evidence_command(tmp_path: Path) -> None:
    args = parser().parse_args(
        [
            "funding-cadence-policy-evidence",
            "--coverage-audit",
            str(tmp_path / "audit.json"),
            "--funding-job-root",
            str(tmp_path / "job"),
            "--software-identity",
            SOFTWARE_IDENTITY,
            "--output",
            str(tmp_path / "evidence.json"),
        ]
    )
    assert args.coverage_audit == [tmp_path / "audit.json"]
    assert args.funding_job_root == [tmp_path / "job"]
