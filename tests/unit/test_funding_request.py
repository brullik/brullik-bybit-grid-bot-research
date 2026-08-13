from __future__ import annotations

import json
from pathlib import Path

import pytest
from grid_contracts.canonical import canonical_sha256
from grid_data.evidence import publish_evidence
from grid_data.funding_acquisition import (
    MAX_PAGE_ARTIFACT_BYTES,
    STAGING_METADATA_BYTES,
    FundingAcquisitionError,
)
from grid_data.funding_request import (
    FUNDING_REQUEST_CONTRACT,
    resolve_funding_request,
)
from grid_data.instrument_registry import build_instrument_registry
from jsonschema import Draft202012Validator

JANUARY_1_2026_MS = 1_767_225_600_000
ROOT = Path(__file__).parents[2]


def inventory_record(symbol: str, source_symbol_id: int) -> dict[str, object]:
    return {
        "base_coin": symbol.removesuffix("USDT"),
        "contract_type": "LinearPerpetual",
        "delivery_time_ms": 0,
        "funding_interval_minutes": 480,
        "launch_time_ms": 1_600_000_000_000,
        "max_leverage": "100",
        "max_order_quantity": "1000000",
        "min_leverage": "1",
        "min_order_quantity": "0.001",
        "quantity_step": "0.001",
        "quote_coin": "USDT",
        "settle_coin": "USDT",
        "source_payload_sha256": f"{source_symbol_id:064x}",
        "source_symbol_id": source_symbol_id,
        "status": "Trading",
        "symbol": symbol,
        "tick_size": "0.0001",
    }


def registry_payload() -> dict[str, object]:
    inventory: dict[str, object] = {
        "content_sha256": "a" * 64,
        "evidence_schema": "grid.bybit-public-inventory/v1",
        "fetched_at_utc": "2026-08-12T12:36:49Z",
        "inventory_status": "partial",
        "records": [inventory_record("AAAUSDT", 1), inventory_record("BBBUSDT", 9)],
    }
    return build_instrument_registry(inventory, inventory_artifact_sha256="b" * 64)


def capacity_payload(*, bucket_count: int = 8) -> dict[str, object]:
    return {
        "disk_headroom": {
            "scenarios": [
                {
                    "id": "full-rebuild-active-plus-building",
                    "required_bytes": 90_000_000_000,
                }
            ]
        },
        "evidence_schema": "grid.current-universe-capacity/v1",
        "layout_projections": [
            {
                "layout": {
                    "bucket_count": bucket_count,
                    "compression": "zstd",
                    "compression_level": 3,
                    "numeric_representation": "hybrid_int64_decimal",
                    "target_file_mb": 16,
                }
            }
        ],
    }


def request_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "contract": FUNDING_REQUEST_CONTRACT,
        "job_id": "funding-2026-01-b01-fixture",
        "series": [
            {
                "symbol": "BBBUSDT",
                "start_ms": JANUARY_1_2026_MS,
                "end_ms": JANUARY_1_2026_MS + 60_000,
            },
            {
                "symbol": "AAAUSDT",
                "start_ms": JANUARY_1_2026_MS,
                "end_ms": JANUARY_1_2026_MS + 60_000,
            },
        ],
        "page_span_minutes": 120,
        "page_limit": 3,
        "workers": 1,
        "target_rps": 10,
        "max_attempts": 2,
        "max_http_requests": 8,
    }
    payload.update(overrides)
    return payload


def evidence_files(tmp_path: Path, *, bucket_count: int = 8) -> tuple[Path, Path]:
    registry, _ = publish_evidence(tmp_path / "registry.json", registry_payload())
    capacity, _ = publish_evidence(
        tmp_path / "capacity.json", capacity_payload(bucket_count=bucket_count)
    )
    return registry, capacity


def write_request(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "request.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_request_derives_ids_launch_evidence_and_staging_budget(tmp_path: Path) -> None:
    registry, capacity = evidence_files(tmp_path)
    request = request_payload()
    schema = json.loads(
        (ROOT / "schemas/market/v1/bybit-funding-history-request.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema).validate(request)
    resolved = resolve_funding_request(
        write_request(tmp_path, request),
        instrument_registry_path=registry,
        capacity_evidence_path=capacity,
    )

    assert tuple(
        (item.instrument_id, item.symbol, item.launch_time_ms) for item in resolved.spec.series
    ) == (
        (1, "AAAUSDT", 1_600_000_000_000),
        (9, "BBBUSDT", 1_600_000_000_000),
    )
    assert resolved.request_sha256 == canonical_sha256(request)
    assert resolved.spec.instrument_evidence_sha256 == resolved.registry.artifact_sha256
    assert resolved.spec.capacity_evidence_sha256 == resolved.capacity_artifact_sha256
    assert resolved.budget.active_and_building_bytes == 90_000_000_000
    assert resolved.budget.rest_staging_bytes == (
        STAGING_METADATA_BYTES + 4 * MAX_PAGE_ARTIFACT_BYTES
    )


def test_request_rejects_caller_identity_wrong_layout_and_no_predecessor_window(
    tmp_path: Path,
) -> None:
    registry, capacity = evidence_files(tmp_path)
    raw = request_payload()
    raw["series"][0]["instrument_id"] = 123  # type: ignore[index]
    with pytest.raises(FundingAcquisitionError, match="series fields"):
        resolve_funding_request(
            write_request(tmp_path, raw),
            instrument_registry_path=registry,
            capacity_evidence_path=capacity,
        )

    other = tmp_path / "other"
    other.mkdir()
    other_registry, other_capacity = evidence_files(other, bucket_count=4)
    with pytest.raises(FundingAcquisitionError, match="accepted canonical layout"):
        resolve_funding_request(
            write_request(other, request_payload()),
            instrument_registry_path=other_registry,
            capacity_evidence_path=other_capacity,
        )

    at_launch = request_payload(
        series=[
            {
                "symbol": "AAAUSDT",
                "start_ms": 1_600_000_000_000,
                "end_ms": 1_600_000_000_000,
            }
        ]
    )
    with pytest.raises(FundingAcquisitionError, match="predecessor"):
        resolve_funding_request(
            write_request(tmp_path, at_launch),
            instrument_registry_path=registry,
            capacity_evidence_path=capacity,
        )


def test_request_rejects_cross_bucket_or_month_job(tmp_path: Path) -> None:
    registry, capacity = evidence_files(tmp_path)
    cross_bucket = request_payload()
    cross_bucket["series"][1]["symbol"] = "BBBUSDT"  # type: ignore[index]
    with pytest.raises(FundingAcquisitionError, match=r"unique|month/bucket"):
        resolve_funding_request(
            write_request(tmp_path, cross_bucket),
            instrument_registry_path=registry,
            capacity_evidence_path=capacity,
        )

    cross_month = request_payload(
        series=[
            {
                "symbol": "AAAUSDT",
                "start_ms": JANUARY_1_2026_MS,
                "end_ms": 1_769_904_000_000,
            }
        ]
    )
    with pytest.raises(FundingAcquisitionError, match="month/bucket"):
        resolve_funding_request(
            write_request(tmp_path, cross_month),
            instrument_registry_path=registry,
            capacity_evidence_path=capacity,
        )
