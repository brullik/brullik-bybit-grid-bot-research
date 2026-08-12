# Performance and Capacity Plan

## Capacity model

The theoretical full-coverage trade-price dataset is:

```text
700 instruments × 10 years × 365.2425 days/year × 1,440 minutes/day
= 3,681,644,400 1m candles
```

If trade-price and mark-price 1m candles are both stored:

```text
3,681,644,400 × 2 = 7,363,288,800 candle rows
```

Funding and metadata add comparatively few rows but remain essential for honest backtests.

Actual row count will be lower for instruments listed later than the ten-year horizon, suspended, or delisted. The platform must nevertheless handle the stated capacity envelope without redesign.

## API-page implication

At 1,000 candles per REST page, each theoretical candle dataset requires 3,682,000 per-symbol
requests. Trade-price plus mark-price therefore requires 7,364,000 requests. Conservative
60-minute funding adds 307,300 requests, for 7,671,300 total.

ADR-0016 accepts this REST-intensive initial bootstrap because V1 does not download or retain
tick-trade archives. The request-only lower bound is 63,928 seconds at the documented default IP
limit of 120 requests/second, or 767,130 seconds at the 10 requests/second planning rate. Both
exclude latency, throttling headroom, retry, validation, and publication. The downloader must use
bounded concurrency and receipt-based resume; a later verified one-minute bulk product may replace
matching REST ranges.

## Storage model

Storage depends on schema, encoding, compression, cardinality, and value distributions. Illustrative trade-price estimates:

| Effective stored bytes per row | Approximate size for 3.681B rows |
|---:|---:|
| 24 | 88.4 GB |
| 40 | 147.3 GB |
| 64 | 235.6 GB |

Trade + mark at 40 bytes/row is roughly 294.5 GB before REST staging, feature stores, outcomes,
experiments, compaction headroom, backups, and filesystem overhead. Tick-archive storage is not
part of the V1 plan.

### Planning recommendation

- Minimum development: 1 TB NVMe with disciplined cleanup.
- Comfortable full research workstation: 2 TB or more NVMe for canonical data, derived datasets, experiments, and safe compaction headroom.
- Backup/object storage sized separately.

These are planning envelopes, not guaranteed final sizes. A representative compression benchmark must be completed before hardware purchase is treated as final.

### Current-universe operational sizing

The formal capacity envelope and a point-in-time operating estimate answer different questions.
The former protects the architecture from future growth; the latter helps preflight a concrete
bootstrap on a concrete volume.

The receipt-pinned 2026-08-12 owner storage review observed 1,770,106,722 equal-coverage
trade+mark lifecycle rows, `24.039621018%` of the formal row envelope. Applying the larger bounded
real-market row width projected about 41.907 GiB for the first canonical build, 83.815 GiB for a
full active-plus-building replacement, about 49 MiB for one day of current `Trading` instruments,
and 1.484 GiB for a maximum 31-day partition rewrite.

Tick-trade archive headroom is no longer required by ADR-0016. These values still do not size
bounded REST-page staging, derived data, experiments, compaction, or backup. Normal operation must
append new closed intervals and repair only detected gaps; immutable replacement rewrites only
affected monthly partitions. See
[M1 current-universe capacity](../benchmarks/specifications/M1_CURRENT_UNIVERSE_CAPACITY.md).

## Reference execution profiles

### Profile A — local feasibility

- 8+ CPU cores;
- 32 GB RAM;
- NVMe SSD;
- 10–50 instruments for representative pipeline validation.

### Profile B — full-scale research workstation

- 16–32 physical/high-performance CPU cores;
- 64–128 GB RAM;
- fast local NVMe, preferably separate working and backup volumes;
- sufficient cooling and sustained I/O capability.

### Profile C — live host

- 2–4 CPU cores;
- 2–8 GB RAM;
- durable SSD;
- stable network and clock synchronization;
- no historical corpus.

## Performance architecture

### 1. Columnar scans

Parquet enables compression and column-level access. DuckDB and Polars can push selected columns and filters into scans, avoiding unnecessary reads.

### 2. Partition pruning

Time predicates prune year/month directories. Symbol predicates map to one stable bucket. Sorted row groups enable additional skipping.

### 3. Lazy and streaming execution

Use Polars lazy scans and streaming sinks for datasets larger than memory. Avoid eager materialization unless the result is demonstrably bounded.

### 4. Materialize reusable features

Rolling ATR, range position, touches, crossings, volatility, volume, and regime inputs are parameter-independent or shared across many experiments. Compute them once per feature version, not once per parameter trial.

### 5. Candidate sparsification

Do not simulate every grid parameter on every minute. First build a compact candidate/event dataset. Expensive path-dependent simulation runs only on candidates that pass cheap structural filters.

### 6. Deterministic sharding

Jobs are partitioned by dataset/time/bucket with a read-only lookback halo equal to the maximum feature warmup. Each shard writes only its core interval, preventing duplicates while preserving rolling correctness.

### 7. Avoid Python row loops

Core transforms are vectorized in Polars/DuckDB/Arrow or compiled kernels. Python orchestrates jobs and contracts.

### 8. Cache by content identity

A derived partition cache key includes parent dataset ID, feature/outcome contract version, and configuration hash. Identical work is reused; changed inputs produce new outputs.

### 9. Compact files

Compaction targets a measured file-size range. Too-small files waste metadata time; too-large files make repair and parallelism inflexible.

### 10. Profile before native extensions

Rust/native kernels are permitted only behind stable interfaces after profiling shows that storage layout, query planning, and vectorized execution are not the dominant bottlenecks.

## Provisional benchmark gates

Final thresholds must be set after the benchmark spike. Initial targets on documented reference hardware:

| Benchmark | Provisional target |
|---|---:|
| Scan one symbol, ten-year 1m OHLC subset | ≤ 5 s warm cache; ≤ 15 s cold cache |
| Scan one month across full universe, selected columns | ≤ 15 s cold cache |
| Data-quality audit for one canonical month | ≤ 5 min |
| Canonicalize and write 100 million candles | ≤ 20 min |
| Full feature build memory | bounded to ≤ 70% configured RAM |
| Full-scale job restart | resumes committed shards; no full restart |
| Live closed-candle to signal decision | p99 ≤ 5 s |
| Live startup and reconciliation | ≤ 60 s under normal API conditions |
| Live steady-state memory | ≤ 2 GB target |

These are acceptance hypotheses, not guarantees. The benchmark report must state hardware, versions, cache status, input layout, and exact commands.

## Benchmark matrix before full build

Test at least:

- bucket counts 8, 16, 32;
- file targets 128, 256, 512 MB;
- row-group sizes appropriate to observed row width;
- ZSTD compression levels versus Snappy if useful;
- Float64 versus scaled integer canonical representation;
- DuckDB and Polars scan plans;
- all-universe time slices;
- single-symbol full-history scans;
- feature build with 1,440-minute halo;
- cold and warm cache;
- local NVMe and optional S3-compatible storage.

## Performance anti-patterns

- CSV as the research store;
- one Parquet file per day or per tiny symbol segment;
- repeated symbol strings on every row when a stable integer ID is available;
- loading the full corpus into pandas;
- cross-joining raw minutes with the full parameter grid;
- using notebooks as the production data pipeline;
- recomputing shared rolling features for each experiment;
- sharing the research workstation load with live trading;
- claiming speed without reproducible benchmark evidence.
