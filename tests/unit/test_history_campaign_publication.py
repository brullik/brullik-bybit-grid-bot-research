from __future__ import annotations

import json
from pathlib import Path

import grid_data.funding_acquisition as funding_acquisition
import grid_data.history_acquisition as history_acquisition
import grid_data.history_campaign as history_campaign
import pytest
from grid_contracts.canonical import sha256_file
from grid_data.history_campaign import HistoryCampaignError
from grid_data.history_campaign_publication import (
    HistoryCampaignPublicationError,
    execute_history_campaign_publication,
    preflight_history_campaign_publication,
    verify_completed_history_campaign_publication,
)
from jsonschema import Draft202012Validator

from tests.unit.test_history_campaign import (
    JANUARY_31_2026_2358_MS,
    FakeKlineClient,
    request_payload,
    snapshot,
)
from tests.unit.test_history_campaign import execute as execute_source_campaign
from tests.unit.test_history_campaign import preflight as preflight_source_campaign

ROOT = Path(__file__).parents[2]
SOFTWARE_IDENTITY = "git:" + "7" * 40


class PublishingFundingClient:
    def funding_page(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        category: str = "linear",
        limit: int = 200,
    ) -> tuple[dict[str, str], ...]:
        del category
        timestamp = end_ms // 60_000 * 60_000 if limit == 1 else start_ms
        return (
            {
                "symbol": symbol,
                "fundingRate": "0.0001000",
                "fundingRateTimestamp": str(timestamp),
            },
        )


def completed_source_campaign(tmp_path: Path):  # type: ignore[no-untyped-def]
    source_plan = preflight_source_campaign(
        tmp_path,
        request=request_payload(
            kinds=["trade", "funding"],
            symbols=["AAAUSDT"],
            end_ms=JANUARY_31_2026_2358_MS,
        ),
    )
    return execute_source_campaign(
        source_plan,
        FakeKlineClient(),
        PublishingFundingClient(),
    )


def preflight_publication(
    tmp_path: Path,
    source_campaign_root: Path,
    *,
    observed_at_ms: int = 2_000,
    free_bytes: int = 140 * 1024**3,
    software_identity: str = SOFTWARE_IDENTITY,
):  # type: ignore[no-untyped-def]
    return preflight_history_campaign_publication(
        source_campaign_root,
        instrument_registry_path=tmp_path / "registry.json",
        capacity_evidence_path=tmp_path / "capacity.json",
        store_root=tmp_path / "market-store",
        snapshot=snapshot(
            tmp_path,
            observed_at_ms=observed_at_ms,
            free_bytes=free_bytes,
        ),
        now_ms=observed_at_ms + 1,
        software_identity=software_identity,
    )


def execute_publication(plan, *, progress=None):  # type: ignore[no-untyped-def]
    return execute_history_campaign_publication(
        plan,
        snapshot_provider=lambda: snapshot(
            plan.store_root.parent,
            observed_at_ms=2_002,
        ),
        now_ms=lambda: 2_003,
        progress=progress,
    )


def test_publication_campaign_preflight_is_aggregate_bounded_and_no_mutation(
    tmp_path: Path,
) -> None:
    source = completed_source_campaign(tmp_path)
    store = tmp_path / "market-store"
    plan = preflight_publication(tmp_path, source.campaign_root)

    assert not store.exists()
    assert not plan.publication_root.exists()
    assert [job.kind for job in plan.jobs] == ["trade", "funding"]
    assert [job.dataset_type for job in plan.jobs] == ["trade_kline_1m", "funding_event"]
    assert plan.required_free_bytes == max(job.required_free_bytes for job in plan.jobs)
    assert plan.required_free_bytes < sum(job.required_free_bytes for job in plan.jobs)
    assert plan.planned_peak_memory_bytes == max(job.planned_peak_memory_bytes for job in plan.jobs)
    assert plan.plan_payload["publication_policy"] == {
        "child_order": "source-campaign-sequence-v1",
        "max_concurrent_writers": 1,
        "private_endpoints": False,
        "receipt_resume": True,
        "tick_rows_requested": False,
    }


def test_publication_preflight_uses_one_verified_page_read_per_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = completed_source_campaign(tmp_path)
    history_page_reads: dict[Path, int] = {}
    funding_page_reads: dict[Path, int] = {}
    original_history_verify = history_acquisition._verify_artifact
    original_funding_verify = funding_acquisition._verify_artifact

    def count_history(path: Path):  # type: ignore[no-untyped-def]
        if path.parent.name == "pages" and path.suffix == ".json":
            history_page_reads[path] = history_page_reads.get(path, 0) + 1
        return original_history_verify(path)

    def count_funding(path: Path):  # type: ignore[no-untyped-def]
        if path.parent.name == "pages" and path.suffix == ".json":
            funding_page_reads[path] = funding_page_reads.get(path, 0) + 1
        return original_funding_verify(path)

    monkeypatch.setattr(history_acquisition, "_verify_artifact", count_history)
    monkeypatch.setattr(funding_acquisition, "_verify_artifact", count_funding)
    monkeypatch.setattr(
        history_campaign,
        "verify_completed_history_job",
        lambda _path: (_ for _ in ()).throw(
            AssertionError("campaign bypassed its typed child verifier")
        ),
    )
    monkeypatch.setattr(
        history_campaign,
        "verify_completed_funding_job",
        lambda _path: (_ for _ in ()).throw(
            AssertionError("campaign bypassed its typed child verifier")
        ),
    )

    plan = preflight_publication(tmp_path, source.campaign_root)

    assert len(plan.jobs) == 2
    assert history_page_reads and set(history_page_reads.values()) == {1}
    assert funding_page_reads and set(funding_page_reads.values()) == {1}


def test_publication_campaign_executes_verifies_schemas_and_is_idempotent(
    tmp_path: Path,
) -> None:
    source = completed_source_campaign(tmp_path)
    plan = preflight_publication(tmp_path, source.campaign_root)
    completed = execute_publication(plan)

    assert completed.dataset_count == 2
    assert completed.row_count == 2
    assert completed.file_count == 2
    assert completed.parquet_bytes > 0
    assert {path.name for path in completed.publication_root.iterdir()} == {
        "completion-receipt.json",
        "manifest.json",
        "plan.json",
        "plan.receipt.json",
    }
    schema_root = ROOT / "schemas/market/v1"
    for schema_name, artifact in (
        ("history-campaign-publication-plan.schema.json", completed.plan_path),
        ("history-campaign-publication-manifest.schema.json", completed.manifest_path),
        (
            "history-campaign-publication-receipt.schema.json",
            completed.publication_root / "plan.receipt.json",
        ),
        ("history-campaign-publication-receipt.schema.json", completed.receipt_path),
    ):
        schema = json.loads((schema_root / schema_name).read_text(encoding="utf-8"))
        artifact_payload = json.loads(artifact.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(artifact_payload)
    verified = verify_completed_history_campaign_publication(
        completed.publication_root,
        source.campaign_root,
    )
    assert verified.manifest_sha256 == completed.manifest_sha256

    first_dataset = plan.store_root / plan.jobs[0].dataset_root
    first_manifest_sha = sha256_file(first_dataset / "manifest.json")
    resumed = preflight_publication(
        tmp_path,
        source.campaign_root,
        observed_at_ms=3_000,
    )
    assert resumed.existing_complete is True
    assert all(job.existing_commit for job in resumed.jobs)
    same = execute_history_campaign_publication(
        resumed,
        snapshot_provider=lambda: (_ for _ in ()).throw(
            AssertionError("completed publication requested a host snapshot")
        ),
        now_ms=lambda: (_ for _ in ()).throw(
            AssertionError("completed publication requested a clock")
        ),
    )
    assert same.manifest_sha256 == completed.manifest_sha256
    assert sha256_file(first_dataset / "manifest.json") == first_manifest_sha


def test_interrupted_publication_resumes_from_canonical_receipts(tmp_path: Path) -> None:
    source = completed_source_campaign(tmp_path)
    plan = preflight_publication(tmp_path, source.campaign_root)

    def interrupt_after_first(child, published):  # type: ignore[no-untyped-def]
        del published
        if child.sequence == 0:
            raise RuntimeError("injected publication interruption")

    with pytest.raises(RuntimeError, match="injected publication interruption"):
        execute_publication(plan, progress=interrupt_after_first)
    assert plan.plan_path.is_file()
    assert plan.plan_receipt_path.is_file()
    assert not plan.manifest_path.exists()
    first_dataset = plan.store_root / plan.jobs[0].dataset_root
    assert (first_dataset / "completion-receipt.json").is_file()
    first_manifest_sha = sha256_file(first_dataset / "manifest.json")

    resumed = preflight_publication(
        tmp_path,
        source.campaign_root,
        observed_at_ms=3_000,
    )
    assert [job.existing_commit for job in resumed.jobs] == [True, False]
    completed = execute_publication(resumed)
    assert completed.dataset_count == 2
    assert sha256_file(first_dataset / "manifest.json") == first_manifest_sha


def test_publication_campaign_detects_outer_and_canonical_tampering(tmp_path: Path) -> None:
    source = completed_source_campaign(tmp_path)
    completed = execute_publication(preflight_publication(tmp_path, source.campaign_root))
    completed.manifest_path.write_bytes(completed.manifest_path.read_bytes() + b" ")
    with pytest.raises(HistoryCampaignPublicationError, match=r"canonical|receipt"):
        verify_completed_history_campaign_publication(
            completed.publication_root,
            source.campaign_root,
        )

    other = tmp_path / "canonical-tamper"
    other.mkdir()
    other_source = completed_source_campaign(other)
    other_plan = preflight_publication(other, other_source.campaign_root)
    other_completed = execute_publication(other_plan)
    canonical_manifest = other_plan.store_root / other_plan.jobs[0].dataset_root / "manifest.json"
    canonical_manifest.write_bytes(canonical_manifest.read_bytes() + b" ")
    with pytest.raises(HistoryCampaignPublicationError, match="canonical dataset"):
        verify_completed_history_campaign_publication(
            other_completed.publication_root,
            other_source.campaign_root,
        )


def test_publication_campaign_rejects_resource_shortfall_and_mutable_identity(
    tmp_path: Path,
) -> None:
    source = completed_source_campaign(tmp_path)
    with pytest.raises(HistoryCampaignPublicationError, match="preflight failed"):
        preflight_publication(
            tmp_path,
            source.campaign_root,
            free_bytes=1,
        )
    assert not (tmp_path / "market-store").exists()

    with pytest.raises(HistoryCampaignPublicationError, match="software identity"):
        preflight_publication(
            tmp_path,
            source.campaign_root,
            software_identity="working-tree",
        )


def test_publication_campaign_detects_source_substitution(tmp_path: Path) -> None:
    source = completed_source_campaign(tmp_path)
    completed = execute_publication(preflight_publication(tmp_path, source.campaign_root))
    source.manifest_path.write_bytes(source.manifest_path.read_bytes() + b" ")
    with pytest.raises((HistoryCampaignError, HistoryCampaignPublicationError)):
        verify_completed_history_campaign_publication(
            completed.publication_root,
            source.campaign_root,
        )
