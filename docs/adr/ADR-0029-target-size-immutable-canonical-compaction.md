# ADR-0029: Target-Size Immutable Canonical Compaction

- Status: accepted
- Date: 2026-08-13
- Implements: Phase 2 multi-fragment canonical compaction boundary

## Context

Canonical acquisition and repair already publish receipt-committed datasets without editing their
parents. Incremental operation can therefore leave several small immutable fragments for the same
UTC month and stable instrument bucket. Reading those fragments forever would accumulate file-open
and planning overhead, while rewriting any committed file in place would violate ADR-0003.

The accepted layout targets 16 MiB ZSTD-3 files but also requires honest tail semantics. A writer
cannot infer target attainment from schema metadata, discard duplicate keys during maintenance, or
combine unrelated partitions merely to make larger files.

## Decision

Add `grid-data compact` and freeze
`grid.canonical-candle-compaction-publication/v1` as an immutable transition over one or more
receipt-verified canonical candle parents. Every parent must have the same dataset type, v1 exact
Arrow schema, UTC calendar month, and stable bucket. Parent IDs are sorted for deterministic
identity and recorded in full in the child manifest.

Before loading the complete bounded partition, compaction verifies every parent, derives a
conservative uncompressed-byte estimate from Parquet row-group metadata, and applies the current
host, 70% total-memory, available-memory, NVMe/SSD, free-space, and active-plus-building capacity
checks. It repeats the resource check against the actual Arrow footprint and obtains another fresh
host snapshot immediately before its first filesystem mutation.

The parent tables are combined and sorted by `instrument_id, open_time_ms`. Duplicate keys,
including byte-identical duplicates, block the transition; compaction never silently deduplicates
or chooses a conflicting value. All input fragments must describe exactly one month/bucket
partition, and the planned output file count must be lower than the input file count.

Rows per output file are calibrated deterministically from at most the first 1,000,000 logical
rows encoded in memory with the accepted ZSTD-3 writer settings. The 16,777,216-byte target is
converted to a row target rounded upward to the 128,000-row-group boundary. Every non-final file
has that row target. Only the final file may be smaller and is explicitly recorded as the sole
tail; if the complete partition is smaller than one target, its one output file is an explicit
tail. Actual bytes and `tail-below-target`, `target-band`, or `oversized-single-batch`
classification are recorded for every file, so target attainment is never claimed from metadata.

The child dataset ID is content-addressed from the ordered parent manifest identities, accepted
layout, target, and full Git software identity. Output files use ordered names plus their SHA-256,
the complete logical table hash is independent of source/output chunk boundaries, and publication
uses the existing same-volume building directory, atomic rename, and completion-receipt-last
protocol. Existing identical output is independently reverified; a conflicting identity is not
overwritten.

Freeze `grid.canonical-1m-compaction/v1` as the small value-free public proof. It binds capacity,
all parent manifests, child manifest, input/output logical hashes, file counts, target/tail facts,
lineage, and software identity. Parent manifests and files are reverified after publication and
must remain byte-identical.

This transition does not register the child in a catalog, accept a coverage gap, delete an
unreferenced parent, or close Gate 2.

## Consequences

- Incremental immutable fragments can be consolidated without a mutable `latest` path.
- One command may compact several one-file parents or one already fragmented parent, provided the
  complete union is one month/bucket and the output actually reduces file count.
- The current in-memory sort is bounded by the month/bucket unit and fail-closed host admission;
  a future streaming external sort requires a new implementation contract if measured scale makes
  this bound inadequate.
- Garbage collection remains a separate reachability/retention decision; compaction never deletes
  parents or working branches automatically.
- Catalog registration remains the next separate immutable metadata transition.

## Rejected alternatives

- Rewrite or delete parent Parquet files in place: this destroys reproducible lineage.
- Deduplicate identical keys during compaction: it hides an upstream duplicate and weakens Gate 2.
- Compact across months or buckets: it breaks the accepted partition and repair boundary.
- Always emit one large file: it violates the measured 16 MiB target and reduces parallelism.
- Treat every final file as target-sized because schema metadata says 16 MiB: observed compressed
  bytes and explicit tail classification are required.
