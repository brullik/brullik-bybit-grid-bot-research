from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[2]


def imports_under(path: Path) -> set[str]:
    imports: set[str] = set()
    for source in path.rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
    return imports


def test_live_has_no_research_data_or_private_adapter_import() -> None:
    imported = imports_under(ROOT / "apps" / "live" / "src")
    forbidden_prefixes = (
        "grid_research",
        "grid_data",
        "grid_market_store",
        "grid_bybit_private",
        "duckdb",
        "polars",
        "pyarrow",
    )
    assert not {name for name in imported if name.startswith(forbidden_prefixes)}


def test_data_has_no_private_or_live_import() -> None:
    imported = imports_under(ROOT / "apps" / "data" / "src")
    forbidden_prefixes = ("grid_live", "grid_bybit_private")
    assert not {name for name in imported if name.startswith(forbidden_prefixes)}


def test_history_acquisition_is_public_one_minute_only() -> None:
    source_path = ROOT / "apps" / "data" / "src" / "grid_data" / "history_acquisition.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    endpoint_literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("/v5/")
    }
    assert endpoint_literals == {"/v5/market/kline", "/v5/market/mark-price-kline"}
    assert "recent-trade" not in source_path.read_text(encoding="utf-8").lower()


def test_funding_acquisition_is_public_history_only() -> None:
    source_path = ROOT / "apps" / "data" / "src" / "grid_data" / "funding_acquisition.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    endpoint_literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("/v5/")
    }
    assert endpoint_literals == {"/v5/market/funding/history"}
    source = source_path.read_text(encoding="utf-8").lower()
    assert "api_key" not in source
    assert "api_secret" not in source


def test_market_store_has_no_network_research_private_or_live_import() -> None:
    imported = imports_under(ROOT / "packages" / "market-store" / "src")
    forbidden_prefixes = (
        "grid_bybit_public",
        "grid_bybit_private",
        "grid_research",
        "grid_live",
        "urllib",
        "requests",
        "httpx",
    )
    assert not {name for name in imported if name.startswith(forbidden_prefixes)}


def test_research_and_release_have_no_private_import() -> None:
    for application in ("research", "release"):
        imported = imports_under(ROOT / "apps" / application / "src")
        assert not {name for name in imported if name.startswith("grid_bybit_private")}


def test_private_adapter_exposes_only_the_validate_endpoint() -> None:
    source_root = ROOT / "packages" / "bybit-private" / "src"
    endpoint_literals: set[str] = set()
    for source in source_root.rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        endpoint_literals.update(
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.startswith("/v5/")
        )
    assert endpoint_literals == {"/v5/fgridbot/validate"}


def test_mainnet_discovery_is_validate_only_and_uta_gated() -> None:
    source = (ROOT / "scripts" / "discover_mainnet_validate_minimum.ps1").read_text(
        encoding="utf-8"
    )

    assert "[switch]$AcknowledgeUnifiedAccount" in source
    assert "--environment mainnet" in source
    assert "--acknowledge-mainnet-validate-only" in source
    assert source.count("& $cli probe") == 1
    assert "/v5/" not in source
    assert "Remove-Item Env:BYBIT_MAINNET_API_KEY" in source
    assert "Remove-Item Env:BYBIT_MAINNET_API_SECRET" in source
    assert "exit $exitCode" in source
    for symbol in ("XRPUSDT", "DOGEUSDT", "LINKUSDT"):
        assert symbol in source


def test_each_application_declares_its_own_build_metadata() -> None:
    for application in ("data", "research", "release", "live"):
        assert (ROOT / "apps" / application / "pyproject.toml").is_file()


def test_each_bybit_adapter_declares_its_own_build_metadata() -> None:
    for adapter in ("bybit-public", "bybit-private"):
        assert (ROOT / "packages" / adapter / "pyproject.toml").is_file()


def test_market_store_declares_its_own_build_metadata() -> None:
    assert (ROOT / "packages" / "market-store" / "pyproject.toml").is_file()
