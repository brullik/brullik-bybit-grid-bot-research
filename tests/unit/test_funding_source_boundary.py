from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from grid_bybit_public import BybitPublicError
from grid_contracts.canonical import canonical_sha256
from grid_data.cli import parser
from grid_data.evidence import publish_evidence
from grid_data.funding_source_boundary import (
    FundingSourceBoundaryError,
    execute_funding_source_boundary,
    preflight_funding_source_boundary,
    verify_completed_funding_source_boundary,
)
from grid_data.instrument_registry import build_instrument_registry
from grid_market_store import HostSnapshot
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[2]
START_MS = 1_600_000_020_000
END_MS = 1_600_002_000_000
EVENTS = (
    1_600_000_080_000,
    1_600_000_560_000,
    1_600_001_040_000,
    1_600_001_520_000,
)
SOFTWARE_IDENTITY = "git:" + "8" * 40


class FakeClient:
    def __init__(self, *, fail_after_calls: int | None = None) -> None:
        self.calls: list[int] = []
        self.fail_after_calls = fail_after_calls

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
        self.calls.append(end_ms)
        if self.fail_after_calls is not None and len(self.calls) > self.fail_after_calls:
            raise BybitPublicError("injected boundary interruption")
        values = [value for value in EVENTS if start_ms <= value <= end_ms]
        return tuple(
            {
                "fundingRate": "0.0001",
                "fundingRateTimestamp": str(value),
                "symbol": symbol,
            }
            for value in sorted(values, reverse=True)[:limit]
        )


def registry_payload() -> dict[str, object]:
    inventory: dict[str, object] = {
        "content_sha256": "a" * 64,
        "evidence_schema": "grid.bybit-public-inventory/v1",
        "fetched_at_utc": "2026-08-13T00:00:00Z",
        "inventory_status": "partial",
        "records": [
            {
                "base_coin": "AAA",
                "contract_type": "LinearPerpetual",
                "delivery_time_ms": 0,
                "funding_interval_minutes": 480,
                "launch_time_ms": START_MS,
                "max_leverage": "100",
                "max_order_quantity": "1000000",
                "min_leverage": "1",
                "min_order_quantity": "0.001",
                "quantity_step": "0.001",
                "quote_coin": "USDT",
                "settle_coin": "USDT",
                "source_payload_sha256": "1" * 64,
                "source_symbol_id": 1,
                "status": "Trading",
                "symbol": "AAAUSDT",
                "tick_size": "0.0001",
            }
        ],
    }
    return build_instrument_registry(inventory, inventory_artifact_sha256="b" * 64)


def files(tmp_path: Path) -> tuple[Path, Path]:
    registry, _receipt = publish_evidence(tmp_path / "registry.json", registry_payload())
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "contract": "grid.bybit-funding-source-boundary-request/v1",
                "discovery_id": "funding-boundary-fixture",
                "end_ms": END_MS,
                "max_attempts": 1,
                "max_pages_per_symbol": 10,
                "page_limit": 2,
                "start_ms": START_MS,
                "symbols": ["AAAUSDT"],
                "target_rps": 96,
                "workers": 1,
            }
        ),
        encoding="utf-8",
    )
    return registry, request


def snapshot(tmp_path: Path) -> HostSnapshot:
    return HostSnapshot(
        observed_at_ms=1_700_000_000_000,
        memory_total_bytes=16 * 1024**3,
        memory_available_bytes=8 * 1024**3,
        storage_kind="nvme",
        storage_device_id="fixture-nvme",
        volume_root=tmp_path.resolve(),
        volume_free_bytes=140 * 1024**3,
    )


def preflight(tmp_path: Path):  # type: ignore[no-untyped-def]
    registry, request = files(tmp_path)
    return preflight_funding_source_boundary(
        request,
        instrument_registry_path=registry,
        output_root=tmp_path / "boundary",
        snapshot=snapshot(tmp_path),
        now_ms=1_700_000_000_001,
        software_identity=SOFTWARE_IDENTITY,
    )


def execute(plan, client):  # type: ignore[no-untyped-def]
    return execute_funding_source_boundary(
        plan,
        client_factory=lambda: client,
        snapshot_provider=lambda: snapshot(plan.output_root.parent),
        now_ms=lambda: 1_700_000_000_002,
    )


def test_boundary_discovery_is_receipted_resumable_and_schema_valid(tmp_path: Path) -> None:
    plan = preflight(tmp_path)
    assert not plan.job_root.exists()
    completed = execute(plan, FakeClient())
    verified = verify_completed_funding_source_boundary(completed.job_root)
    assert verified.page_count == 3
    assert verified.event_count == 4
    manifest = json.loads(verified.manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_policy"] == {
        "category": "linear",
        "endpoint": "/v5/market/funding/history",
        "pagination": "inclusive-end-oldest-minus-one-v1",
        "persisted_fields": ["fundingRateTimestamp"],
        "private_credentials_used": False,
        "source_rates_validated_not_retained": True,
    }
    assert manifest["results"] == [
        {
            "canonical_start_ms": EVENTS[1],
            "event_count": 4,
            "first_observed_settlement_ms": EVENTS[0],
            "instrument_id": 1,
            "page_count": 3,
            "predecessor_settlement_ms": EVENTS[0],
            "symbol": "AAAUSDT",
        }
    ]
    schema_root = ROOT / "schemas/market/v1"
    for name, artifact in (
        ("funding-source-boundary-request.schema.json", plan.request_path),
        ("funding-source-boundary-plan.schema.json", completed.job_root / "plan.json"),
        (
            "funding-source-boundary-page.schema.json",
            completed.job_root / "pages/0000000001-0000.json",
        ),
        ("funding-source-boundary-manifest.schema.json", completed.manifest_path),
        ("funding-source-boundary-receipt.schema.json", completed.receipt_path),
    ):
        Draft202012Validator(json.loads((schema_root / name).read_text())).validate(
            json.loads(artifact.read_text())
        )
    plan_hash = canonical_sha256(json.loads((completed.job_root / "plan.json").read_text()))
    assert completed.job_root.name.endswith(plan_hash[:16])
    for artifact in completed.job_root.rglob("*.json"):
        body = artifact.read_bytes()
        assert b'"fundingRate":' not in body
        assert b'"funding_rate":' not in body


def test_boundary_discovery_resumes_and_detects_tampering(tmp_path: Path) -> None:
    plan = preflight(tmp_path)
    interrupted = FakeClient(fail_after_calls=1)
    with pytest.raises(FundingSourceBoundaryError, match="failed after"):
        execute(plan, interrupted)
    first_page = plan.job_root / "pages/0000000001-0000.json"
    assert first_page.is_file()

    resumed = preflight_funding_source_boundary(
        plan.request_path,
        instrument_registry_path=tmp_path / "registry.json",
        output_root=plan.output_root,
        snapshot=snapshot(tmp_path),
        now_ms=1_700_000_000_001,
        software_identity=SOFTWARE_IDENTITY,
    )
    client = FakeClient()
    completed = execute(resumed, client)
    assert client.calls[0] < END_MS

    page = completed.job_root / "pages/0000000001-0001.json"
    page.write_bytes(page.read_bytes() + b" ")
    with pytest.raises(FundingSourceBoundaryError, match=r"invalid|receipt"):
        verify_completed_funding_source_boundary(completed.job_root)


def test_boundary_discovery_rejects_missing_second_settlement(tmp_path: Path) -> None:
    plan = preflight(tmp_path)

    class OneEventClient(FakeClient):
        def funding_page(self, **kwargs: Any) -> tuple[dict[str, str], ...]:
            result = super().funding_page(**kwargs)
            return tuple(item for item in result if int(item["fundingRateTimestamp"]) == EVENTS[0])

    with pytest.raises(FundingSourceBoundaryError, match="at least two"):
        execute(plan, OneEventClient())


def test_boundary_discovery_validates_but_does_not_retain_rates(tmp_path: Path) -> None:
    plan = preflight(tmp_path)

    class InvalidRateClient(FakeClient):
        def funding_page(self, **kwargs: Any) -> tuple[dict[str, str], ...]:
            rows = list(super().funding_page(**kwargs))
            if rows:
                rows[0]["fundingRate"] = "NaN"
            return tuple(rows)

    with pytest.raises(FundingSourceBoundaryError, match="rate is invalid"):
        execute(plan, InvalidRateClient())


def test_boundary_discovery_cli_exposes_execute_and_independent_verify() -> None:
    command_parser = parser()
    execute_args = command_parser.parse_args(
        [
            "funding-source-boundary",
            "--request",
            "request.json",
            "--instrument-registry",
            "registry.json",
            "--output-root",
            "boundary",
            "--software-identity",
            SOFTWARE_IDENTITY,
            "--execute",
        ]
    )
    verify_args = command_parser.parse_args(["verify-funding-source-boundary", "boundary/job"])
    assert execute_args.execute is True
    assert verify_args.job_root == Path("boundary/job")
