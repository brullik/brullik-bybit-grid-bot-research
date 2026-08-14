"""Write or verify the repository SHA-256 source manifest."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

MAX_DIAGNOSTIC_ROWS = 20

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "MANIFEST.sha256"
EXCLUDED_PARTS = {
    ".benchmark-work",
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".vscode",
    "__pycache__",
    "htmlcov",
    "venv",
}
EXCLUDED_SUFFIXES = {".arrow", ".bin", ".duckdb", ".feather", ".parquet", ".pyc", ".sqlite"}
EXCLUDED_ROOT_PREFIXES = {
    ("artifacts",),
    ("credentials",),
    ("data",),
    ("logs",),
    ("market-data",),
    ("releases", "private"),
    ("reports", "private"),
    ("runtime",),
    ("secrets",),
    ("state",),
}


def source_files() -> tuple[Path, ...]:
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path == MANIFEST:
            continue
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if any(part.endswith(".egg-info") for part in relative.parts):
            continue
        if any(relative.parts[: len(prefix)] == prefix for prefix in EXCLUDED_ROOT_PREFIXES):
            continue
        if relative.name == ".env" or (
            relative.name.startswith(".env.") and relative.name != ".env.example"
        ):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        # Only small JSON evidence/receipts in results is source-manifest eligible.
        if relative.parts[:2] == ("benchmarks", "results") and path.suffix.lower() != ".json":
            continue
        files.append(path)
    return tuple(sorted(files, key=lambda item: item.relative_to(ROOT).as_posix()))


def rendered_manifest() -> str:
    rows = []
    for path in source_files():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(f"{digest}  {path.relative_to(ROOT).as_posix()}")
    return "\n".join(rows) + "\n"


def manifest_difference(actual: str, expected: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return bounded deterministic rows missing from or unexpected in the manifest."""

    actual_rows = set(actual.splitlines())
    expected_rows = set(expected.splitlines())
    missing_or_changed = tuple(sorted(expected_rows - actual_rows)[:MAX_DIAGNOSTIC_ROWS])
    unexpected_or_stale = tuple(sorted(actual_rows - expected_rows)[:MAX_DIAGNOSTIC_ROWS])
    return missing_or_changed, unexpected_or_stale


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    expected = rendered_manifest()
    if args.write:
        MANIFEST.write_text(expected, encoding="utf-8", newline="\n")
        return 0
    actual = MANIFEST.read_text(encoding="utf-8") if MANIFEST.exists() else ""
    if actual != expected:
        print("MANIFEST.sha256 is stale; run: python scripts/update_manifest.py --write")
        missing_or_changed, unexpected_or_stale = manifest_difference(actual, expected)
        for row in missing_or_changed:
            print(f"missing-or-changed: {row}")
        for row in unexpected_or_stale:
            print(f"unexpected-or-stale: {row}")
        return 1
    print(f"verified {len(source_files())} source files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
