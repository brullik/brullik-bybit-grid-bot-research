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
  --row-group-rows 10000 `
  --output benchmarks/results/m1-layout-smoke.json --force
```

Full-matrix scaled test without a representative claim:

```powershell
python benchmarks/layout_benchmark.py `
  --profile scaled --rows 10000000 --instruments 700 `
  --output benchmarks/results/m1-layout-scaled.json --force
```

Representative candidate run (the row count is a minimum, not proof that the requested files
were reached):

```powershell
python benchmarks/layout_benchmark.py `
  --profile full --rows 100000000 --instruments 700 `
  --output benchmarks/results/m1-layout-full.json --force
```

The harness reports first and repeated reads but does not pretend to flush the Windows OS
filesystem cache. It calibrates rows-per-file from an observed compressed sample and records the
smallest/largest actual Parquet file. A full run becomes `representative-run` only when every
layout produces a file at least 80% of its requested target; otherwise it is
`full-matrix-insufficient-file-scale`. Any Gate 1 decision must state how cold-cache evidence was
obtained.

To bound disk use, generated layouts are deleted after their scan by default. Pass
`--retain-layouts` only when the files themselves are required for a separate diagnostic. Float64
and scaled-Int64 frames are built sequentially rather than retained together.

## Acceptance interpretation

- `smoke-only` proves harness correctness, not layout suitability.
- `scaled-only` exercises all combinations but cannot support a full-scale choice.
- `representative-run` is evidence only when the hardware, row count, file sizes, and cache
  conditions are representative and the receipt verifies.
- The canonical physical representation and partition layout remain provisional until the
  owner/PM accepts the full result.
