# ADR-0008: Versioned, Bounded-Memory Layout Evidence

- Status: proposed; Gate 1 benchmark-gated
- Date: 2026-08-12

## Context

The first layout-benchmark evidence contract records scan timings and observed file sizes, but its
smoke implementation eagerly materializes the complete synthetic corpus. That execution model
cannot produce credible reference-scale evidence on data larger than RAM. It also assigns every
row to one synthetic month, so it does not exercise the provisional calendar partition boundary
from ADR-0005.

Adding memory, scratch-space, calendar-partition, validation, and restart evidence changes the
public evidence contract. Existing `grid.layout-benchmark/v1` artifacts and receipts must remain
verifiable and must not silently acquire new semantics.

## Decision

Introduce the append-only `grid.layout-benchmark/v2` evidence contract for new runs. The v2
harness:

- generates deterministic instrument/time-sorted chunks no larger than a configured bound;
- writes real UTC year/month and stable instrument-bucket partitions through a streaming
  PyArrow Parquet writer;
- preflights estimated scratch capacity before creating a layout;
- records calibration size, peak process RSS, actual file-size attainment, and calendar partition
  count;
- validates expected row counts and aggregate values independently with DuckDB and Polars;
- benchmarks a first-calendar-month universe slice rather than a one-day substitute;
- commits hash-receipted per-layout checkpoints and resumes only an identical verified run; and
- deletes only an owned benchmark work directory or an exact generated layout path.

The v1 schema and evidence remain immutable. V2 does not promote a physical layout or close Gate
1; ADR-0005 remains proposed until representative cold/warm evidence and the owner/PM decision
exist.

## Consequences

- Reference-scale runs no longer require eager construction of the complete corpus.
- Interrupted full-matrix work can resume at a committed layout boundary.
- Evidence consumers must select the schema version explicitly.
- Synthetic compression and timing remain feasibility evidence, not production guarantees.
- A full run still fails closed when any requested target file size is not materially exercised.

## Rejected alternatives

- Mutate the v1 schema in place: existing receipts would retain a version label with changed
  semantics.
- Treat checkpoints as complete evidence: partial matrix results cannot support a Gate 1 choice.
- Estimate month/bucket behavior from a single synthetic month: partition pruning and file-size
  feasibility would not be exercised.
