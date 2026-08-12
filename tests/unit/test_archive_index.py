from __future__ import annotations

from grid_bybit_public.archive import (
    BybitArchiveIndex,
    parse_directory_links,
    summarize_trade_files,
)


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
