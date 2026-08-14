from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from grid_contracts.canonical import canonical_json_bytes, canonical_sha256, sha256_file
from grid_data.cli import parser as command_parser
from grid_data.history_campaign_progress import (
    CAMPAIGN_RECEIPT_CONTRACT,
    CHILD_RECEIPT_CONTRACT,
    HistoryCampaignProgressError,
    build_history_campaign_progress,
)
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[2]


def _write_receipted(
    path: Path,
    payload: dict[str, object],
    *,
    contract: str,
    duplicate_manifest_receipt: bool = False,
) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(payload))
    digest = sha256_file(path)
    receipt_name = (
        "completion-receipt.json" if path.name == "manifest.json" else "plan.receipt.json"
    )
    receipt = {
        "artifact": path.name,
        "artifact_sha256": digest,
        "contract": contract,
        "status": "complete",
    }
    (path.parent / receipt_name).write_bytes(canonical_json_bytes(receipt))
    if duplicate_manifest_receipt:
        (path.parent / "manifest.receipt.json").write_bytes(canonical_json_bytes(receipt))
    return digest


def _campaign_fixture(
    tmp_path: Path,
    *,
    campaign_id: str = "progress-campaign",
    completed_count: int = 2,
    aggregate_complete: bool = False,
) -> Path:
    staging = tmp_path / "history"
    page_counts = (10, 20, 30)
    timings = ((1_000, 2_000), (3_000, 6_000), (6_500, 8_000))
    descriptors: list[dict[str, object]] = []
    child_facts: list[dict[str, object]] = []
    for sequence, page_count in enumerate(page_counts):
        job_id = f"{campaign_id}-trade-2026-0{sequence + 1}-b00"
        request = {"contract": "grid.bybit-1m-history-request/v1", "job_id": job_id}
        request_sha256 = canonical_sha256(request)
        child_plan = {
            "capacity_budget": {
                "active_and_building_bytes": 1,
                "operating_reserve_bytes": 1,
                "rest_staging_bytes": 1,
            },
            "contract": "grid.bybit-1m-history-plan/v1",
            "spec": {
                "job_id": job_id,
                "request_sha256": request_sha256,
            },
            "tasks": [{"sequence": item} for item in range(page_count)],
        }
        child_plan_sha256 = canonical_sha256(child_plan)
        relative_root = f".landing/{job_id}--{child_plan_sha256[:16]}"
        child_root = staging.joinpath(*relative_root.split("/"))
        _write_receipted(child_root / "plan.json", child_plan, contract=CHILD_RECEIPT_CONTRACT)
        descriptors.append(
            {
                "bucket": 0,
                "job_id": job_id,
                "job_plan_sha256": child_plan_sha256,
                "job_root": relative_root,
                "kind": "trade",
                "month": f"2026-0{sequence + 1}",
                "planned_page_count": page_count,
                "request": request,
                "request_sha256": request_sha256,
                "sequence": sequence,
            }
        )
        if sequence >= completed_count:
            continue
        started_at_ms, completed_at_ms = timings[sequence]
        row_count = page_count * 100
        manifest = {
            "completed_at_ms": completed_at_ms,
            "contract": "grid.bybit-1m-history-acquisition/v1",
            "job_id": job_id,
            "page_count": page_count,
            "pages": [
                {"attempt_count": 1, "row_count": 100, "sequence": item}
                for item in range(page_count)
            ],
            "plan_sha256": child_plan_sha256,
            "request_bound": {"actual_http_requests": page_count},
            "request_sha256": request_sha256,
            "row_count": row_count,
            "started_at_ms": started_at_ms,
            "status": "complete",
        }
        manifest_sha256 = _write_receipted(
            child_root / "manifest.json",
            manifest,
            contract=CHILD_RECEIPT_CONTRACT,
            duplicate_manifest_receipt=True,
        )
        pages = child_root / "pages"
        pages.mkdir()
        (pages / "ignored-invalid-page.json").write_text("not JSON", encoding="utf-8")
        child_facts.append(
            {
                "actual_http_requests": page_count,
                "job_id": job_id,
                "job_manifest_sha256": manifest_sha256,
                "job_plan_sha256": child_plan_sha256,
                "job_root": relative_root,
                "kind": "trade",
                "page_count": page_count,
                "row_count": row_count,
                "sequence": sequence,
            }
        )
    campaign_request = {
        "campaign_id": campaign_id,
        "contract": "grid.public-history-campaign-request/v1",
    }
    campaign_plan = {
        "campaign_id": campaign_id,
        "campaign_request": campaign_request,
        "campaign_request_sha256": canonical_sha256(campaign_request),
        "capacity_evidence_sha256": "1" * 64,
        "contract": "grid.public-history-campaign-plan/v1",
        "instrument_evidence_sha256": "2" * 64,
        "job_count": len(descriptors),
        "jobs": descriptors,
        "lifecycle_policy": "registry-lifecycle-intersection-v1",
        "source_policy": {
            "funding": "/v5/market/funding/history",
            "mark": "/v5/market/mark-price-kline",
            "tick_rows_requested": False,
            "trade": "/v5/market/kline",
        },
    }
    campaign_plan_sha256 = canonical_sha256(campaign_plan)
    campaign_root = staging / ".campaigns" / f"{campaign_id}--{campaign_plan_sha256[:16]}"
    _write_receipted(
        campaign_root / "plan.json",
        campaign_plan,
        contract=CAMPAIGN_RECEIPT_CONTRACT,
    )
    if aggregate_complete:
        assert completed_count == len(descriptors)
        campaign_manifest = {
            "campaign_id": campaign_id,
            "campaign_plan_sha256": campaign_plan_sha256,
            "campaign_request_sha256": canonical_sha256(campaign_request),
            "capacity_evidence_sha256": "1" * 64,
            "completed_at_ms": 9_000,
            "contract": "grid.public-history-campaign-manifest/v1",
            "http_request_count": sum(page_counts),
            "instrument_evidence_sha256": "2" * 64,
            "job_count": len(child_facts),
            "jobs": child_facts,
            "page_count": sum(page_counts),
            "row_count": sum(item * 100 for item in page_counts),
            "status": "complete",
        }
        _write_receipted(
            campaign_root / "manifest.json",
            campaign_manifest,
            contract=CAMPAIGN_RECEIPT_CONTRACT,
        )
    return campaign_root


def test_progress_is_receipt_bound_fast_read_only_and_schema_valid(tmp_path: Path) -> None:
    campaign_root = _campaign_fixture(tmp_path)
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    payload = build_history_campaign_progress(
        [campaign_root],
        observed_at_ms=10_000,
        window_seconds=60,
    )

    schema = json.loads(
        (ROOT / "schemas/market/v1/history-campaign-progress.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema).validate(payload)
    campaign = payload["campaigns"][0]  # type: ignore[index]
    assert campaign == {
        "campaign_id": "progress-campaign",
        "campaign_plan_sha256": campaign["campaign_plan_sha256"],  # type: ignore[index]
        "completed_job_count": 2,
        "completed_planned_page_count": 30,
        "completed_row_count": 3_000,
        "eta_seconds": 12,
        "job_count": 3,
        "last_completed_at_ms": 6_000,
        "last_completion_age_seconds": 4,
        "pending_job_count": 1,
        "pending_planned_page_count": 30,
        "planned_page_count": 60,
        "progress_millionths": 500_000,
        "rate_sample_completed_job_count": 1,
        "rate_sample_elapsed_ms": 8_000,
        "rate_sample_planned_page_count": 20,
        "recent_rate_milli_pages_per_second": 2_500,
        "status": "in-progress",
    }
    assert payload["summary"]["progress_millionths"] == 500_000  # type: ignore[index]
    assert payload["projection"]["eta_seconds"] == 12  # type: ignore[index]
    assert payload["assurances"] == {
        "authoritative_campaign_verification_performed": False,
        "mutation_performed": False,
        "network_request_performed": False,
        "page_artifact_bytes_read": 0,
        "receipt_bound_metadata_verified": True,
    }
    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_completed_aggregate_is_reconciled_and_has_zero_eta(tmp_path: Path) -> None:
    campaign_root = _campaign_fixture(tmp_path, completed_count=3, aggregate_complete=True)

    payload = build_history_campaign_progress([campaign_root], observed_at_ms=10_000)

    campaign = payload["campaigns"][0]  # type: ignore[index]
    assert campaign["status"] == "complete"  # type: ignore[index]
    assert campaign["progress_millionths"] == 1_000_000  # type: ignore[index]
    assert campaign["eta_seconds"] == 0  # type: ignore[index]
    assert payload["summary"]["completed_campaign_count"] == 1  # type: ignore[index]
    assert payload["projection"]["eta_seconds"] == 0  # type: ignore[index]


def test_multi_campaign_eta_uses_only_incomplete_critical_path(tmp_path: Path) -> None:
    completed = _campaign_fixture(
        tmp_path / "complete",
        campaign_id="completed-campaign",
        completed_count=3,
        aggregate_complete=True,
    )
    active = _campaign_fixture(tmp_path / "active", campaign_id="active-campaign")

    payload = build_history_campaign_progress([completed, active], observed_at_ms=10_000)

    assert payload["campaign_count"] == 2
    assert payload["summary"]["completed_campaign_count"] == 1  # type: ignore[index]
    assert payload["summary"]["pending_campaign_count"] == 1  # type: ignore[index]
    assert payload["projection"]["eta_seconds"] == 12  # type: ignore[index]


def test_progress_rejects_tampered_child_manifest(tmp_path: Path) -> None:
    campaign_root = _campaign_fixture(tmp_path)
    manifest = next((tmp_path / "history" / ".landing").glob("*/manifest.json"))
    raw: dict[str, Any] = json.loads(manifest.read_text(encoding="utf-8"))
    raw["row_count"] += 1
    manifest.write_bytes(canonical_json_bytes(raw))

    with pytest.raises(HistoryCampaignProgressError, match="receipt does not verify"):
        build_history_campaign_progress([campaign_root], observed_at_ms=10_000)


def test_active_run_lock_is_safely_reported_as_pending(tmp_path: Path) -> None:
    campaign_root = _campaign_fixture(tmp_path)
    plan = json.loads((campaign_root / "plan.json").read_text(encoding="utf-8"))
    pending_root = campaign_root.parent.parent.joinpath(*plan["jobs"][2]["job_root"].split("/"))
    (pending_root / ".run-lock").mkdir()
    (pending_root / "pages").mkdir()

    payload = build_history_campaign_progress([campaign_root], observed_at_ms=10_000)

    campaign = payload["campaigns"][0]  # type: ignore[index]
    assert campaign["completed_job_count"] == 2  # type: ignore[index]
    assert campaign["pending_job_count"] == 1  # type: ignore[index]


def test_completion_after_observation_cutoff_is_not_counted(tmp_path: Path) -> None:
    campaign_root = _campaign_fixture(tmp_path)

    payload = build_history_campaign_progress([campaign_root], observed_at_ms=1_500)

    campaign = payload["campaigns"][0]  # type: ignore[index]
    assert campaign["status"] == "not-started"  # type: ignore[index]
    assert campaign["completed_job_count"] == 0  # type: ignore[index]
    assert campaign["progress_millionths"] == 0  # type: ignore[index]


def test_progress_requires_child_manifest_receipt_mirror(tmp_path: Path) -> None:
    campaign_root = _campaign_fixture(tmp_path)
    mirror = next((tmp_path / "history" / ".landing").glob("*/manifest.receipt.json"))
    mirror.unlink()

    with pytest.raises(HistoryCampaignProgressError, match="completion pair is incomplete"):
        build_history_campaign_progress([campaign_root], observed_at_ms=10_000)


def test_progress_rejects_duplicate_roots_and_invalid_window(tmp_path: Path) -> None:
    campaign_root = _campaign_fixture(tmp_path)
    with pytest.raises(HistoryCampaignProgressError, match="must be unique"):
        build_history_campaign_progress([campaign_root, campaign_root], observed_at_ms=10_000)
    with pytest.raises(HistoryCampaignProgressError, match="window_seconds"):
        build_history_campaign_progress(
            [campaign_root],
            observed_at_ms=10_000,
            window_seconds=59,
        )


def test_cli_accepts_multiple_campaign_roots_for_one_snapshot() -> None:
    args = command_parser().parse_args(
        [
            "history-campaign-progress",
            "--campaign-root",
            "campaign-a",
            "--campaign-root",
            "campaign-b",
            "--window-seconds",
            "7200",
        ]
    )
    assert args.handler.__name__ == "_history_campaign_progress"
    assert args.campaign_root == [Path("campaign-a"), Path("campaign-b")]
    assert args.window_seconds == 7_200
