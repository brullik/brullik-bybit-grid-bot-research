from pathlib import Path

import pytest

from scripts import update_manifest


def write_text(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(relative, encoding="utf-8")


def test_source_manifest_keeps_data_app_but_excludes_local_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(update_manifest, "ROOT", tmp_path)
    monkeypatch.setattr(update_manifest, "MANIFEST", tmp_path / "MANIFEST.sha256")

    for relative in (
        "apps/data/source.py",
        ".env.example",
        "data/candles.parquet",
        "reports/private/probe.json",
        ".env.local",
        "generated.egg-info/PKG-INFO",
    ):
        write_text(tmp_path, relative)

    included = {path.relative_to(tmp_path).as_posix() for path in update_manifest.source_files()}

    assert included == {".env.example", "apps/data/source.py"}


def test_manifest_difference_is_bounded_and_deterministic() -> None:
    actual = "bbbb  stale.py\naaaa  same.py\n"
    expected = "cccc  current.py\naaaa  same.py\n"

    assert update_manifest.manifest_difference(actual, expected) == (
        ("cccc  current.py",),
        ("bbbb  stale.py",),
    )
