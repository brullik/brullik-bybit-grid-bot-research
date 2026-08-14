"""Offline measured evidence for bounded incremental catalog exact-key selection."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
from datetime import UTC, datetime
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter_ns
from typing import Any, Final

import duckdb
import psutil  # type: ignore[import-untyped]
import pyarrow as pa  # type: ignore[import-untyped]
from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_contracts.market import MINUTE_MS, Candle1m, DatasetType
from grid_data.evidence import publish_evidence
from grid_market_store import (
    MIN_OPERATING_RESERVE_BYTES,
    CandleDatasetSpec,
    CapacityBudget,
    HostSnapshot,
    build_canonical_candle_batch,
    preflight_candle_dataset,
    publish_candle_dataset,
)
from grid_market_store.catalog import (
    EXACT_KEY_BATCH_ROWS,
    MAX_EXACT_KEY_STREAMS,
    CatalogSelection,
    CatalogSelectionRequest,
    CatalogSnapshot,
    preflight_catalog_registration,
    register_catalog_datasets,
    select_catalog_range,
)

EVIDENCE_CONTRACT: Final = "grid.phase2-incremental-catalog-selection-performance/v1"
SOFTWARE_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
JANUARY_1_2026_MS: Final = 1_767_225_600_000
MAX_FRAGMENT_COUNT: Final = 64
MAX_INSTRUMENT_COUNT: Final = 128
MAX_MINUTES_PER_FRAGMENT: Final = 1_440
MAX_TOTAL_MINUTES: Final = 31 * 24 * 60
MAX_TOTAL_ROWS: Final = 5_000_000


class IncrementalCatalogSelectionBenchmarkError(RuntimeError):
    """The offline incremental selection benchmark did not preserve its invariants."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise IncrementalCatalogSelectionBenchmarkError(message)


def _exact_integer(name: str, value: int, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise IncrementalCatalogSelectionBenchmarkError(
            f"{name} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _verify_generated_at(generated_at_utc: str) -> None:
    _require(generated_at_utc.endswith("Z"), "generated_at_utc must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(generated_at_utc.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise IncrementalCatalogSelectionBenchmarkError("generated_at_utc is invalid") from error
    offset = parsed.utcoffset()
    _require(offset is not None and offset.total_seconds() == 0, "generated_at_utc must be UTC")


def _snapshot(root: Path, *, observed_at_ms: int) -> HostSnapshot:
    return HostSnapshot(
        observed_at_ms=observed_at_ms,
        memory_total_bytes=16 * 1024**3,
        memory_available_bytes=8 * 1024**3,
        storage_kind="nvme",
        storage_device_id="offline-incremental-selection-fixture",
        volume_root=root.resolve(),
        volume_free_bytes=64 * 1024**3,
    )


def _budget() -> CapacityBudget:
    return CapacityBudget(
        active_and_building_bytes=0,
        rest_staging_bytes=0,
        operating_reserve_bytes=MIN_OPERATING_RESERVE_BYTES,
    )


def _candle(instrument_id: int, timestamp_ms: int, *, fragment: int) -> Candle1m:
    return Candle1m(
        category="linear",
        instrument_id=instrument_id,
        open_time_ms=timestamp_ms,
        open=Decimal("100"),
        high=Decimal("102"),
        low=Decimal("99"),
        close=Decimal("101"),
        volume=Decimal("10"),
        turnover=Decimal("1000"),
        source_id="offline-incremental-selection-fixture/v1",
        ingestion_id=f"fragment-{fragment:03d}-{instrument_id}-{timestamp_ms}",
    )


def _tree_fingerprint(root: Path) -> str:
    entries: list[dict[str, object]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            entries.append({"kind": "directory", "path": relative})
        elif path.is_file():
            entries.append(
                {
                    "kind": "file",
                    "path": relative,
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
            )
        else:
            raise IncrementalCatalogSelectionBenchmarkError(
                "temporary fixture contains an unsafe path type"
            )
    return canonical_sha256(entries)


def _publish_fragments(
    root: Path,
    *,
    fragment_count: int,
    instrument_ids: tuple[int, ...],
    minutes_per_fragment: int,
) -> tuple[Path, tuple[str, ...]]:
    store = root / "market-store"
    dataset_ids: list[str] = []
    for fragment in range(fragment_count):
        dataset_id = f"trade-incremental-benchmark-{fragment:03d}"
        start_ms = JANUARY_1_2026_MS + fragment * minutes_per_fragment * MINUTE_MS
        batch = build_canonical_candle_batch(
            tuple(
                _candle(
                    instrument_id,
                    start_ms + minute * MINUTE_MS,
                    fragment=fragment,
                )
                for instrument_id in instrument_ids
                for minute in range(minutes_per_fragment)
            ),
            DatasetType.TRADE_KLINE_1M,
        )
        source_hash = canonical_sha256(
            {
                "fragment": fragment,
                "instrument_count": len(instrument_ids),
                "minutes_per_fragment": minutes_per_fragment,
            }
        )
        plan = preflight_candle_dataset(
            store,
            CandleDatasetSpec(
                dataset_id=dataset_id,
                semantic_version="1.0.0",
                parent_dataset_ids=(),
                source_evidence_sha256=(source_hash,),
                coverage_evidence_sha256=source_hash,
                capacity_evidence_sha256="b" * 64,
                build_config_sha256=canonical_sha256(
                    {"benchmark": EVIDENCE_CONTRACT, "fragment": fragment}
                ),
                software_identity="offline-incremental-selection-fixture@1",
            ),
            batch,
            _budget(),
            _snapshot(root, observed_at_ms=1_000 + fragment * 10),
            now_ms=1_001 + fragment * 10,
        )
        publish_candle_dataset(
            plan,
            _snapshot(root, observed_at_ms=1_002 + fragment * 10),
            committed_at_ms=1_003 + fragment * 10,
        )
        dataset_ids.append(dataset_id)
    return store, tuple(dataset_ids)


def _ambiguous_adjacent_bound_count(snapshot: CatalogSnapshot) -> int:
    files = sorted(
        ((record, item) for record in snapshot.datasets for item in record.files),
        key=lambda value: (
            value[0].partition_path,
            value[1].first_instrument_id,
            value[1].first_time_ms,
            value[0].dataset_id,
            value[1].ordinal,
        ),
    )
    count = 0
    for left, right in pairwise(files):
        if left[0].partition_path != right[0].partition_path:
            continue
        if (left[1].last_instrument_id, left[1].last_time_ms) >= (
            right[1].first_instrument_id,
            right[1].first_time_ms,
        ):
            count += 1
    return count


def _selection_fingerprint(selection: CatalogSelection) -> str:
    return canonical_sha256(
        [
            {
                "file_sha256": item.file_sha256,
                "row_count": item.row_count,
                "size_bytes": item.size_bytes,
            }
            for item in selection.objects
        ]
    )


def build_incremental_catalog_selection_performance_evidence(
    *,
    implementation_identity: str,
    generated_at_utc: str,
    fragment_count: int = 16,
    instrument_count: int = 32,
    minutes_per_fragment: int = 720,
) -> dict[str, Any]:
    """Measure the production exact-key selector against automatically removed fixtures."""

    _require(
        SOFTWARE_IDENTITY_RE.fullmatch(implementation_identity) is not None,
        "implementation identity must be git:<40-character-lowercase-commit-sha>",
    )
    _verify_generated_at(generated_at_utc)
    fragments = _exact_integer(
        "fragment_count", fragment_count, minimum=2, maximum=MAX_FRAGMENT_COUNT
    )
    instruments = _exact_integer(
        "instrument_count", instrument_count, minimum=2, maximum=MAX_INSTRUMENT_COUNT
    )
    minutes = _exact_integer(
        "minutes_per_fragment",
        minutes_per_fragment,
        minimum=1,
        maximum=MAX_MINUTES_PER_FRAGMENT,
    )
    total_minutes = fragments * minutes
    total_rows = fragments * instruments * minutes
    _require(total_minutes <= MAX_TOTAL_MINUTES, "benchmark scope must fit one UTC month")
    _require(total_rows <= MAX_TOTAL_ROWS, "benchmark exceeds the bounded synthetic-row ceiling")
    _require(
        fragments <= MAX_EXACT_KEY_STREAMS,
        "benchmark fragment count exceeds the production exact-key stream ceiling",
    )
    instrument_ids = tuple(9 + 8 * index for index in range(instruments))

    fixture_path: Path | None = None
    with TemporaryDirectory(prefix="grid-incremental-selection-") as temporary:
        root = Path(temporary)
        fixture_path = root
        store, dataset_ids = _publish_fragments(
            root,
            fragment_count=fragments,
            instrument_ids=instrument_ids,
            minutes_per_fragment=minutes,
        )
        catalog = store / "catalog" / "canonical.duckdb"
        registration = preflight_catalog_registration(
            dataset_ids,
            store,
            catalog,
            software_identity=implementation_identity,
        )
        snapshot = register_catalog_datasets(registration, registered_at_ms=20_000)
        ambiguous_bounds = _ambiguous_adjacent_bound_count(snapshot)
        _require(ambiguous_bounds > 0, "fixture did not exercise the exact-key fallback")
        request = CatalogSelectionRequest(
            catalog_revision=snapshot.revision,
            catalog_content_sha256=snapshot.content_sha256,
            dataset_ids=tuple(sorted(dataset_ids)),
            dataset_type=DatasetType.TRADE_KLINE_1M,
            start_time_ms=JANUARY_1_2026_MS,
            end_time_ms=JANUARY_1_2026_MS + (total_minutes - 1) * MINUTE_MS,
            instrument_ids=instrument_ids,
            consumer_software_identity=implementation_identity,
        )
        before = _tree_fingerprint(store)
        started = perf_counter_ns()
        first = select_catalog_range(request, store, catalog)
        first_elapsed_ns = max(1, perf_counter_ns() - started)
        started = perf_counter_ns()
        repeated = select_catalog_range(request, store, catalog)
        repeat_elapsed_ns = max(1, perf_counter_ns() - started)
        after = _tree_fingerprint(store)

        selected_rows = sum(item.row_count for item in first.objects)
        _require(selected_rows == total_rows, "selection row inventory differs from the fixture")
        _require(
            len(first.objects) == snapshot.file_count,
            "selection did not return every registered fixture object",
        )
        _require(first == repeated, "repeated selection is not deterministic")
        _require(before == after, "catalog selection mutated the temporary market store")
        selection_fingerprint = _selection_fingerprint(first)

    _require(
        fixture_path is not None and not fixture_path.exists(),
        "temporary benchmark fixture was not removed",
    )
    payload: dict[str, Any] = {
        "assurances": {
            "catalog_and_dataset_state_preserved": True,
            "network_request_performed": False,
            "private_or_live_capability_used": False,
            "production_catalog_selector_exercised": True,
            "retained_market_store_accessed": False,
            "temporary_fixture_removed": True,
        },
        "bindings": {"implementation_identity": implementation_identity},
        "configuration": {
            "exact_key_batch_rows": EXACT_KEY_BATCH_ROWS,
            "fragment_count": fragments,
            "instrument_count": instruments,
            "max_exact_key_streams": MAX_EXACT_KEY_STREAMS,
            "minutes_per_fragment": minutes,
            "total_row_count": total_rows,
        },
        "correctness": {
            "ambiguous_adjacent_bound_count": ambiguous_bounds,
            "catalog_revision": snapshot.revision,
            "deterministic_repeat_equal": True,
            "selected_object_count": len(first.objects),
            "selected_row_count": selected_rows,
            "selection_fingerprint_sha256": selection_fingerprint,
            "store_fingerprint_equal_before_after": True,
        },
        "environment": {
            "cache_state": "uncontrolled-first-then-immediate-repeat",
            "duckdb_version": duckdb.__version__,
            "logical_cpu_count": os.cpu_count() or 1,
            "memory_total_bytes": int(psutil.virtual_memory().total),
            "platform_machine": platform.machine() or "unknown",
            "platform_system": platform.system() or "unknown",
            "pyarrow_version": pa.__version__,
            "python_version": platform.python_version(),
        },
        "evidence_schema": EVIDENCE_CONTRACT,
        "generated_at_utc": generated_at_utc,
        "limitations": [
            "Synthetic exact-key selection is measured evidence, not full-history performance.",
            "The result does not prove coverage, accept Gate 2, or authorize Phase 3 or live use.",
            "Elapsed time includes receipt/file reverification and may reflect host cache state.",
        ],
        "measurement": {
            "first_selection_elapsed_ns": first_elapsed_ns,
            "first_selection_rows_per_second": max(
                1, total_rows * 1_000_000_000 // first_elapsed_ns
            ),
            "repeat_selection_elapsed_ns": repeat_elapsed_ns,
            "repeat_selection_rows_per_second": max(
                1, total_rows * 1_000_000_000 // repeat_elapsed_ns
            ),
        },
        "status": "measured-incremental-catalog-selection",
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_dataset_or_instrument_identities": False,
            "evidence_contains_market_values": False,
            "evidence_contains_runtime_paths": False,
            "runtime_fixture_committed_to_git": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation-identity", required=True)
    parser.add_argument("--fragment-count", type=int, default=16)
    parser.add_argument("--instrument-count", type=int, default=32)
    parser.add_argument("--minutes-per-fragment", type=int, default=720)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_incremental_catalog_selection_performance_evidence(
        implementation_identity=args.implementation_identity,
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        fragment_count=args.fragment_count,
        instrument_count=args.instrument_count,
        minutes_per_fragment=args.minutes_per_fragment,
    )
    artifact, receipt = publish_evidence(args.output, payload)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "first_selection_elapsed_ns": payload["measurement"]["first_selection_elapsed_ns"],
                "receipt": str(receipt),
                "status": payload["status"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
