# M1 staged reference-layout benchmark protocol

## Purpose

Measure the ADR-0010 shortlist without falsely treating a process-local first query as cold cache.
The protocol also measures immutable monthly-bucket repair and fragmented-input compaction while
proving that source content and exact logical aggregates do not change.

The current v1 source is deterministic exact synthetic data. A successful reference-profile run
still remains a candidate until real-market-skew evidence and owner/PM acceptance exist.

## Local protocol smoke

```powershell
python -m benchmarks.reference_layout_benchmark prepare `
  --work-dir .benchmark-work/reference-layout-smoke `
  --profile smoke --rows 200000 --instruments 50 `
  --row-group-rows 10000 --generation-chunk-rows 20000

python -m benchmarks.reference_layout_benchmark measure `
  --work-dir .benchmark-work/reference-layout-smoke `
  --engine duckdb --query-shape single-symbol --cache-proof unverified-smoke
```

Repeat `measure` for the Cartesian product of:

- `--engine duckdb|polars`; and
- `--query-shape single-symbol|universe-month`.

Then finalize:

```powershell
python -m benchmarks.reference_layout_benchmark finalize `
  --work-dir .benchmark-work/reference-layout-smoke `
  --output benchmarks/results/m1-reference-layout-protocol-smoke.json
```

`local-smoke-only` proves harness behavior. Its timing is not cold-cache evidence.

## Reference-hardware protocol

Prepare the retained 100-million-row shortlist once:

```powershell
python -m benchmarks.reference_layout_benchmark prepare `
  --work-dir .benchmark-work/reference-layout-reference `
  --profile reference --rows 100000000 --instruments 700 `
  --row-group-rows 100000 --generation-chunk-rows 1000000
```

For each of the four engine/query combinations:

1. reboot the declared reference host;
2. do not open, hash, index, or inspect the retained Parquet files;
3. run exactly one `measure` command with `--cache-proof reboot`;
4. retain the measurement and its receipt;
5. reboot again before the next combination.

The finalizer requires four distinct post-preparation boot markers. It checks only path, size, and
modification time before the timed first query, then verifies every content hash afterward. It
also requires unchanged hardware and matching DuckDB/Polars query-result hashes.

## Maintenance semantics

Preparation selects the first UTC calendar-month/symbol-bucket unit of each shortlisted layout.
It performs two non-mutating probes:

- repair rewrites the complete unit into a new target;
- compaction creates eight deterministic small-file fragments and compacts them into a new target.

Both outputs reopen with the exact physical schema. DuckDB and Polars must agree on row count,
timestamp bounds, instrument sum, and exact OHLC/volume/turnover sums. The source tree is hashed
before and after and must remain identical. Temporary maintenance outputs are removed after their
evidence is captured; prepared shortlist datasets stay retained for the reboot-separated scans.

## Interpretation limits

- Reboot separation is stronger than process-local wording but cannot prevent unrelated host
  services from reading the files.
- The v1 generator does not prove real-market compression or skew.
- The smoke artifact does not choose P-001 through P-005 or close Gate 1.
- Scratch Parquet and intermediate evidence remain under `.benchmark-work/` and outside Git.
