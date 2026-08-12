# M1 layout benchmark specification

## Purpose

Measure the provisional choices in ADR-0002 and ADR-0005 without claiming that a small
synthetic smoke test closes Gate 1.

The full matrix compares:

- Float64 and scaled Int64 analytical price/volume columns;
- 8, 16, and 32 stable instrument buckets;
- 128, 256, and 512 MiB target files;
- ZSTD levels 3 and 9, plus Snappy;
- DuckDB and Polars single-symbol and cross-universe scans.

## Commands

Harness smoke test:

```powershell
python benchmarks/layout_benchmark.py `
  --profile smoke --rows 200000 --instruments 50 `
  --output benchmarks/results/m1-layout-smoke.json --force
```

Representative run (choose a row count large enough to exercise the requested target files):

```powershell
python benchmarks/layout_benchmark.py `
  --profile full --rows 100000000 --instruments 700 `
  --output benchmarks/results/m1-layout-full.json --force
```

The harness reports first and repeated reads but does not pretend to flush the Windows OS
filesystem cache. Any Gate 1 decision must state how cold-cache evidence was obtained.

## Acceptance interpretation

- `smoke-only` proves harness correctness, not layout suitability.
- `representative-run` is evidence only when the hardware, row count, file sizes, and cache
  conditions are representative and the receipt verifies.
- The canonical physical representation and partition layout remain provisional until the
  owner/PM accepts the full result.
