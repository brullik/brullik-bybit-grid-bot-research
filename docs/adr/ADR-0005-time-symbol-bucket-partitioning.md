# ADR-0005: Time Plus Stable Symbol-Bucket Partitioning

- Status: proposed; benchmark-gated
- Date: 2026-07-28

## Context

Typical queries include:

- a time slice across the full universe;
- one or several symbols over long history;
- monthly incremental update/audit/repair;
- deterministic parallel feature shards.

Partitioning by symbol/year/month risks tens of thousands of directories/files and small-file overhead. Time-only partitions may read unnecessary symbols.

## Decision

Benchmark and prefer physical partitions by:

```text
dataset_type / year / month / symbol_bucket
```

where `symbol_bucket` is a stable hash of internal instrument ID. Rows inside files are sorted by instrument ID and time. Candidate bucket counts are 8, 16, and 32. Target file sizes are benchmarked at 128, 256, and 512 MB.

The final choice requires measured cold/warm performance, file count, compaction, repair, and single-symbol scans.

## Consequences

- bounded directory/file count;
- efficient month-level pruning and parallelism;
- symbol filter touches one bucket per month, then relies on row-group/statistics pruning;
- changing bucket count requires a new physical dataset version;
- internal instrument identity must be stable.

## Rejected alternatives

- One partition per symbol/day: severe small-file/metadata cost.
- No partitioning: poor incremental repair and time pruning.
- Exchange symbol text as hash identity: renames/migrations complicate stability.
