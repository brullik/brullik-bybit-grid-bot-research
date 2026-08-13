# ADR-0054: Immutable canonical funding compaction

- Status: accepted
- Date: 2026-08-13
- Implements: Phase 2 funding maintenance boundary

## Context

ADR-0031 publishes each canonical funding month/bucket write unit as one immutable ZSTD-3 Parquet
file. Incremental acquisition or separately reviewed funding repair can therefore leave multiple
receipt-committed parents for the same partition. The candle compactor cannot safely consume them:
funding uses a different exact schema, timestamp key, sparse settlement chronology, boundary
evidence, and publication verifier.

Rewriting a parent in place would violate ADR-0003. Combining funding rows without checking the
interval carried by the first row of each fragment could also hide a missing settlement or an
unresolved cadence transition.

## Decision

Add `grid-data compact-funding` and freeze
`grid.canonical-funding-compaction-publication/v1` as a no-mutation preflight plus receipt-last
publication transition. It accepts at least two unique, receipt-verified canonical funding
parents. Parent IDs are sorted for deterministic identity. Every parent must use the exact v1
funding schema and all files must belong to one UTC month and stable instrument bucket.

The complete parent union is sorted by `instrument_id, funding_time_ms`. Duplicate keys,
including byte-identical duplicates, block publication. For every adjacent event of one
instrument, the timestamp delta must equal the later row's `funding_interval_minutes`; this check
also crosses former parent boundaries. Thus compaction cannot erase an unexplained settlement
gap or cadence mismatch.

The parent manifest hashes, exact logical union hash, funding layout, 16 MiB target, and full Git
software identity determine a new `funding-compact-<hash>` identity. One month/bucket of funding
is intentionally sparse and the existing ADR-0031 funding writer emits one explicitly classified
target/tail file. At least two input files are therefore reduced to exactly one output file.
The normal funding host, memory, NVMe/SSD, free-space, stale-building, atomic rename, and
completion-receipt-last checks remain unchanged.

The compaction parent-union hash is used as the new child boundary and coverage binding, while
every parent manifest hash remains source evidence. This is transitive provenance, not a new
claim that chronology is accepted. Parent receipts are reverified before publication and again
when output/evidence is verified. Exact logical equality between the parent union and output is
mandatory.

Freeze `grid.canonical-funding-compaction/v1` as the GitHub-safe proof. It contains capacity,
parent/child manifest hashes, input/output logical hashes, file/count/target facts, lineage, and
software identity. It contains no funding rates, event timestamps, local paths, host identity,
account data, or credentials.

This transition does not accept a funding coverage reason, repair a missing settlement, register
a catalog entry, delete a parent, or close Gate 2.

## Consequences

- Incremental or repaired funding fragments can be consolidated without mutable storage aliases.
- Settlement interval validation crosses parent boundaries and remains fail closed.
- The existing exact funding writer/verifier and host admission remain the single publication
  primitive.
- A larger-than-target monthly funding union remains one honestly classified file; a measured need
  for multi-file funding output requires a later contract.

## Rejected alternatives

- Route funding through candle compaction: the schemas and temporal semantics differ.
- Deduplicate equal funding keys: this hides upstream overlap and weakens quality gates.
- Trust each parent's internal interval checks independently: the fragment boundary could conceal
  a missing event.
- Modify or delete parent datasets: immutable lineage would be lost.
- Treat successful compaction as chronology acceptance: logical preservation does not resolve an
  already blocked coverage reason.
