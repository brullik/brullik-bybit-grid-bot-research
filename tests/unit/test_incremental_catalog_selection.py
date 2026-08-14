from __future__ import annotations

import json
from pathlib import Path

import pytest
from grid_contracts.canonical import canonical_sha256
from grid_market_store.catalog import select_catalog_range
from jsonschema import Draft202012Validator, FormatChecker

from benchmarks.incremental_catalog_selection import (
    IncrementalCatalogSelectionBenchmarkError,
    build_incremental_catalog_selection_performance_evidence,
)

ROOT = Path(__file__).parents[2]


def test_incremental_catalog_selection_benchmark_is_bounded_and_sanitized() -> None:
    evidence = build_incremental_catalog_selection_performance_evidence(
        implementation_identity=f"git:{'a' * 40}",
        generated_at_utc="2026-08-14T03:00:00Z",
        fragment_count=2,
        instrument_count=2,
        minutes_per_fragment=2,
    )
    schema = json.loads(
        (
            ROOT
            / "schemas/evidence/v1/phase2-incremental-catalog-selection-performance.schema.json"
        ).read_text(encoding="utf-8")
    )

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(evidence)
    hash_input = dict(evidence)
    content_sha256 = hash_input.pop("content_sha256")
    assert content_sha256 == canonical_sha256(hash_input)
    assert evidence["configuration"] == {
        "exact_key_batch_rows": 4_096,
        "fragment_count": 2,
        "instrument_count": 2,
        "max_exact_key_streams": 128,
        "minutes_per_fragment": 2,
        "total_row_count": 8,
    }
    assert evidence["correctness"]["ambiguous_adjacent_bound_count"] == 1
    assert evidence["correctness"]["deterministic_repeat_equal"] is True
    assert evidence["correctness"]["selected_object_count"] == 2
    assert evidence["correctness"]["selected_row_count"] == 8
    assert evidence["correctness"]["store_fingerprint_equal_before_after"] is True
    assert evidence["environment"]["cache_state"] == ("uncontrolled-first-then-immediate-repeat")
    assert evidence["environment"]["logical_cpu_count"] > 0
    assert evidence["environment"]["memory_total_bytes"] > 0
    assert evidence["environment"]["python_version"]
    assert evidence["environment"]["duckdb_version"]
    assert evidence["environment"]["pyarrow_version"]
    assert evidence["measurement"]["first_selection_elapsed_ns"] > 0
    assert evidence["measurement"]["repeat_selection_elapsed_ns"] > 0
    rendered = json.dumps(evidence).lower()
    for forbidden in (
        "c:\\",
        "/home/",
        "api_key",
        "api_secret",
        '"symbol"',
        '"instrument_id"',
        '"dataset_id"',
        '"runtime_path"',
        '"open"',
        '"volume"',
        "funding_rate",
    ):
        assert forbidden not in rendered


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"implementation_identity": "dev"}, "implementation identity"),
        ({"fragment_count": 1}, "fragment_count"),
        ({"instrument_count": 1}, "instrument_count"),
        ({"minutes_per_fragment": 1_441}, "minutes_per_fragment"),
        (
            {"fragment_count": 64, "instrument_count": 128, "minutes_per_fragment": 1_440},
            "one UTC month",
        ),
    ],
)
def test_incremental_catalog_selection_benchmark_rejects_unbounded_scope(
    overrides: dict[str, object],
    message: str,
) -> None:
    arguments: dict[str, object] = {
        "implementation_identity": f"git:{'a' * 40}",
        "generated_at_utc": "2026-08-14T03:00:00Z",
        "fragment_count": 2,
        "instrument_count": 2,
        "minutes_per_fragment": 2,
    }
    arguments.update(overrides)
    with pytest.raises(IncrementalCatalogSelectionBenchmarkError, match=message):
        build_incremental_catalog_selection_performance_evidence(**arguments)  # type: ignore[arg-type]


def test_incremental_catalog_selection_benchmark_rejects_selector_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutating_selection(request, store_root, catalog_path):  # type: ignore[no-untyped-def]
        selected = select_catalog_range(request, store_root, catalog_path)
        (store_root / "unsafe-selection-mutation").write_text("unsafe", encoding="utf-8")
        return selected

    monkeypatch.setattr(
        "benchmarks.incremental_catalog_selection.select_catalog_range",
        mutating_selection,
    )
    with pytest.raises(IncrementalCatalogSelectionBenchmarkError, match="mutated"):
        build_incremental_catalog_selection_performance_evidence(
            implementation_identity=f"git:{'a' * 40}",
            generated_at_utc="2026-08-14T03:00:00Z",
            fragment_count=2,
            instrument_count=2,
            minutes_per_fragment=2,
        )
