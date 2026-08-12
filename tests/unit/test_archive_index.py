from __future__ import annotations

import urllib.error
from pathlib import Path

import pytest
from grid_bybit_public.archive import (
    ArchivePathNotFound,
    BybitArchiveIndex,
    ProductIndexSummary,
    TradeArchiveCoverage,
    parse_directory_links,
    summarize_trade_files,
)
from grid_data.archive_inventory import (
    build_archive_coverage_matrix,
    load_verified_public_inventory,
)
from grid_data.evidence import publish_evidence


def test_parse_directory_links_extracts_only_hrefs() -> None:
    html = '<html><a href="BTCUSDT/">BTC</a><a href="ETHUSDT/">ETH</a></html>'
    assert parse_directory_links(html) == ("BTCUSDT/", "ETHUSDT/")


def test_trade_coverage_detects_internal_calendar_gaps() -> None:
    coverage = summarize_trade_files(
        "BTCUSDT",
        (
            "BTCUSDT2026-01-01.csv.gz",
            "BTCUSDT2026-01-03.csv.gz",
            "unrelated.txt",
        ),
    )
    assert coverage.file_count == 2
    assert coverage.first_date == "2026-01-01"
    assert coverage.last_date == "2026-01-03"
    assert coverage.missing_dates == ("2026-01-02",)


def test_index_filters_non_symbol_directories() -> None:
    responses = {
        "https://public.bybit.com/": '<a href="trading/">trading</a><a href="spot/">spot</a>',
        "https://public.bybit.com/trading/": '<a href="BTCUSDT/">BTC</a><a href="../">up</a>',
    }
    index = BybitArchiveIndex(fetch_text=responses.__getitem__)
    assert index.products() == ("spot", "trading")
    assert index.trading_symbols() == ("BTCUSDT",)


def test_product_summary_is_bounded_and_ignores_parent_link() -> None:
    responses = {
        "https://public.bybit.com/trading/": (
            '<a href="../">up</a><a href="BTCUSDT/">BTC</a><a href="ETHUSDT/">ETH</a>'
        )
    }
    index = BybitArchiveIndex(fetch_text=responses.__getitem__)

    assert index.product_summary("trading", sample_limit=1) == ProductIndexSummary(
        product="trading",
        child_link_count=2,
        trailing_slash_child_count=2,
        sample_links=("BTCUSDT/",),
    )


def test_missing_archive_path_has_a_distinct_fail_closed_result() -> None:
    def missing(url: str) -> str:
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)

    index = BybitArchiveIndex(fetch_text=missing)

    with pytest.raises(ArchivePathNotFound, match="does not exist"):
        index.trade_coverage("MISSINGUSDT")


class FakeArchiveIndex:
    def products(self) -> tuple[str, ...]:
        return ("premium_index", "trading")

    def product_summary(self, product: str, *, sample_limit: int) -> ProductIndexSummary:
        assert sample_limit == 20
        return ProductIndexSummary(product, 1, 1, ("EXAMPLE/",))

    def trading_symbols(self) -> tuple[str, ...]:
        return ("EXTRAUSDT", "OLDUSDT", "PREUSDT")

    def trade_coverage(self, symbol: str) -> TradeArchiveCoverage:
        first_dates = {
            "HIDDENUSDT": "2021-01-01",
            "PREUSDT": "2026-01-01",
        }
        first_date = first_dates[symbol]
        return TradeArchiveCoverage(symbol, first_date, first_date, 1, ())


def test_archive_matrix_probes_index_exceptions_and_prelaunch_metadata() -> None:
    inventory = {
        "evidence_schema": "grid.bybit-public-inventory/v1",
        "fetched_at_utc": "2026-08-12T00:00:00Z",
        "records": [
            {
                "contract_type": "LinearPerpetual",
                "launch_time_ms": 1_640_995_200_000,
                "quote_coin": "USDT",
                "settle_coin": "USDT",
                "status": "Closed",
                "symbol": "HIDDENUSDT",
            },
            {
                "contract_type": "LinearPerpetual",
                "launch_time_ms": 1_798_761_600_000,
                "quote_coin": "USDT",
                "settle_coin": "USDT",
                "status": "PreLaunch",
                "symbol": "PREUSDT",
            },
            {
                "contract_type": "LinearPerpetual",
                "launch_time_ms": 1_577_836_800_000,
                "quote_coin": "USDT",
                "settle_coin": "USDT",
                "status": "Trading",
                "symbol": "OLDUSDT",
            },
        ],
    }

    report = build_archive_coverage_matrix(
        FakeArchiveIndex(),  # type: ignore[arg-type]
        inventory,
        inventory_artifact_sha256="a" * 64,
        sample_size=1,
    )

    assert report["universe_comparison"]["current_usdt_linear_perpetual_count"] == 3
    assert report["universe_comparison"]["archive_only_symbol_count"] == 1
    assert report["coverage_findings"]["direct_paths_with_files_but_not_listed_symbols"] == [
        "HIDDENUSDT"
    ]
    assert report["coverage_findings"]["archive_first_date_before_current_launch_date_symbols"] == [
        "HIDDENUSDT",
        "PREUSDT",
    ]
    assert len(report["detailed_trade_coverage"]) == 2


def test_archive_matrix_rejects_receipted_inventory_with_bad_embedded_hash(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "inventory.json"
    publish_evidence(
        artifact,
        {
            "content_sha256": "0" * 64,
            "evidence_schema": "grid.bybit-public-inventory/v1",
            "fetched_at_utc": "2026-08-12T00:00:00Z",
            "records": [],
        },
    )

    with pytest.raises(ValueError, match="embedded content hash"):
        load_verified_public_inventory(artifact)
