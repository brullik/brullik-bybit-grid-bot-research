# M1 staged reference-layout benchmark protocol

## Purpose

Measure the ADR-0010 shortlist without falsely treating a process-local first query as cold cache.
The protocol also measures immutable monthly-bucket repair and fragmented-input compaction while
proving that source content and exact logical aggregates do not change.

Preparation uses deterministic exact synthetic data so the 100-million-row scan is reproducible.
The v2 reference contract additionally binds the verified bounded real-market-skew artifact. A
successful reference-profile run remains a candidate until owner/PM acceptance.

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

First capture a receipt-verified workstation snapshot on the same volume that will retain the
datasets. The example keeps both outside Git on `D:`:

```powershell
python benchmarks/workstation_snapshot.py `
  --output D:\grid-reference\reference-host.json --force
```

The snapshot must report `meets-documented-full-research-profile`: at least 16 observed physical
cores, 64 GiB RAM, and a 2 TiB NVMe volume. A below-profile, malformed, different-host, or
different-volume snapshot is rejected before the work directory is created or replaced. On
Windows, the snapshot resolves the physical device backing that drive; it does not assume that
the benchmark volume is `PhysicalDrive0`.

Prepare the retained 100-million-row shortlist once:

```powershell
python -m benchmarks.reference_layout_benchmark prepare `
  --work-dir D:\grid-reference\reference-layout-reference `
  --profile reference --rows 100000000 --instruments 700 `
  --row-group-rows 100000 --generation-chunk-rows 1000000 `
  --real-market-evidence benchmarks/results/m1-real-market-layout-skew.json `
  --reference-host-evidence D:\grid-reference\reference-host.json
```

For each of the four engine/query combinations:

1. reboot the declared reference host;
2. do not open, hash, index, or inspect the retained Parquet files;
3. run exactly one `measure` command with `--cache-proof reboot`;
4. retain the measurement and its receipt;
5. reboot again before the next combination.

The finalizer requires four distinct post-preparation boot markers. It checks only path, size, and
modification time before the timed first query, then verifies every content hash afterward. It
also requires unchanged hardware and matching DuckDB/Polars query-result hashes. The reference
profile fails closed unless the real-market artifact and receipt verify, reference the same exact
shortlist, retain two schema-verified logical-equivalent layouts, and have a valid embedded hash.
Preparation also fails closed unless each 100-million-row shortlist dataset actually exercises
its declared target file size. Python, DuckDB, Polars, PyArrow, and psutil versions are captured at
preparation and must remain identical in all four legs.

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
- The synthetic reference generator is reproducible but does not reproduce real price paths; the
  linked bounded artifact calibrates compression only for its stated sample.
- The smoke artifact does not choose P-001 through P-005 or close Gate 1.
- Scratch Parquet and intermediate evidence remain under `.benchmark-work/` and outside Git.
