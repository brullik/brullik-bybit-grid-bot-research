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


def test_each_application_declares_its_own_build_metadata() -> None:
    for application in ("data", "research", "release", "live"):
        assert (ROOT / "apps" / application / "pyproject.toml").is_file()
