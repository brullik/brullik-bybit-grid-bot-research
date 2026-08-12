# ADR-0010: Density-Derived Exact Monthly Layout Matrix

- Status: proposed; Gate 1 benchmark-gated
- Date: 2026-08-12

## Context

The completed `grid.layout-benchmark/v2` full-profile candidate wrote 99,999,900 rows for 700
instruments through all 54 combinations in ADR-0005. Every DuckDB/Polars count and aggregate
comparison passed, but the largest file was only 45,730,398 bytes. No month × 8/16/32-bucket
layout could exercise a 128, 256, or 512 MiB target. For the scaled-Int64/ZSTD-3 candidate, the
largest file fell from about 24.1 MiB at 8 buckets to 12.2 MiB at 16 and 6.1 MiB at 32.

This is a structural density constraint, not a reason to relabel the failed targets as passing.
A calendar month contains a bounded number of instrument-minutes; dividing it into more buckets
places an upper bound on the file size before compression.

The earlier scaled-Int64 benchmark also did not prove a self-describing exact physical contract.
An integer column is ambiguous unless its unit/scale is carried by a versioned dataset schema and
verified in every file. The current public instrument inventory observes price tick precision up
to 8 decimal places and quantity-step precision up to 4. Exact turnover may therefore require up
to 12 decimal places when quantity and price are multiplied.

## Decision

Keep immutable UTC calendar-month partitions, but add a revised decision matrix instead of
weakening the original v2 acceptance semantics. The revised matrix compares:

- 4 and 8 stable instrument buckets;
- 16 and 32 MiB requested file targets;
- ZSTD level 3 and Snappy;
- an exact hybrid encoding:
  - OHLC as signed Int64 units of `1e-8`, with embedded Arrow field metadata;
  - volume as Decimal128(38, 4);
  - turnover as Decimal128(38, 12); and
- an exact all-decimal encoding:
  - OHLC as Decimal128(38, 8);
  - volume as Decimal128(38, 4);
  - turnover as Decimal128(38, 12).

Both exact encodings carry the versioned schema identifier
`grid.candle-exact-physical/v1` in Parquet Arrow metadata. The benchmark must reopen every file
and verify the physical types, scale metadata, and schema identifier before recording success.

New evidence uses `grid.layout-benchmark/v3`. V1 and V2 artifacts and receipts remain immutable.
The decision profile requires at least 100 million rows and exactly 700 instruments. It produces
a deterministic reference-hardware rerun shortlist; it does not self-approve P-001 through P-005
or close Gate 1 on this below-reference workstation.

## Consequences

- The new target matrix is derived from measured month/bucket density rather than an arbitrary
  large-file convention.
- Four buckets are reintroduced as a measured alternative because 16 and 32 buckets increased
  file count without achieving the requested targets in the full v2 candidate.
- Binary Float64 remains permitted for explicitly tolerant analytics, but it is excluded from the
  revised canonical-storage shortlist because the persisted candle contract is exact.
- Monthly repair and immutable commit boundaries remain unchanged.
- A final bucket/file-size choice still requires the same matrix on declared reference hardware,
  cold-cache evidence, repair/compaction measurements, and owner/PM acceptance.
- If real source values exceed the observed precision envelope, the schema must version forward;
  values may not be rounded silently to fit this contract.

## Rejected alternatives

- Mark the 128–512 MiB v2 matrix successful because total dataset size was large: individual file
  targets, not aggregate bytes, were the acceptance condition.
- Merge multiple calendar months only to inflate files: this weakens monthly immutable repair and
  incremental-commit boundaries.
- Store exact values as bare Int64 columns without scale metadata: readers could interpret the
  same bits with different economic units.
- Use Float64 as the canonical exact representation: binary rounding can change equality,
  constraint, and downstream execution-boundary behavior.
