# ADR-0065: Bounded exact-key admission for incremental catalog selection

- Status: accepted
- Date: 2026-08-14
- Implements: Phase 2 incremental canonical dataset selection
- Preserves: ADR-0030 explicit catalog-snapshot and no-overlap rules

## Context

ADR-0030 permits a selection to name multiple independently committed canonical fragments from
one month and bucket. This is required for routine daily or otherwise bounded incremental
publication before later compaction. Every individual dataset is receipt-verified and strictly
sorted, but the v1 catalog stores only each file's first and last composite key.

Those bounds are sufficient to prove that two files are disjoint when the earlier last key is
strictly below the later first key. They are not sufficient for multi-instrument time fragments.
For example, two files may both span instruments 9 through 17 while containing disjoint earlier
and later minutes for each instrument. Their lexicographic bounding ranges overlap even though
their exact `(instrument_id, open_time_ms)` keys do not. Rejecting every such case makes the
documented incremental workflow unusable for ordinary multi-instrument partitions. Accepting the
ambiguous bounds without a stronger check could hide duplicate or conflicting canonical keys.

## Decision

Keep the external catalog, selection-request, and selection-evidence v1 schemas unchanged.
Selection continues to reverify every named dataset receipt, file hash, lineage rule, partition,
and catalog binding before key admission.

Within each selected month/bucket partition:

1. Sort files by their stored first composite key. If every adjacent last/first bound is strictly
   disjoint, retain the metadata-only fast path.
2. If any bounds are ambiguous, stream the exact key columns from the already verified Parquet
   files. Candle files use `(instrument_id, open_time_ms)` and funding files use
   `(instrument_id, funding_time_ms)`.
3. Read at most 4,096 rows per file stream at a time, disable threaded Parquet reads, and merge the
   sorted streams. A file that is not itself strictly sorted and unique fails closed.
4. Reject the selection on the first exact key repeated across streams. Identical and conflicting
   values are both forbidden; no market-value column is required to make that decision.
5. Admit at most 128 simultaneous streams for an ambiguous partition. A larger fragmented input
   fails closed and must be compacted before selection rather than consuming unbounded resources.

The exact-key fallback is read-only. It creates no catalog revision, dataset, receipt, temporary
market artifact, network request, credential use, private endpoint call, or live action.

## Consequences

- Disjoint multi-instrument daily/incremental fragments can be selected reproducibly before
  compaction.
- Duplicate or conflicting keys across independently valid dataset receipts remain fail-closed.
- Common compacted or naturally disjoint layouts retain the existing metadata-only cost.
- The ambiguous path has an explicit resource ceiling: 128 streams times a 4,096-row key batch,
  processed one partition at a time.
- The behavior proves only exact selected-object key disjointness. It does not accept gaps,
  lifecycle coverage, funding cadence, Gate 2, Phase 3, or live use.

## Rejected alternatives

- Accept overlapping file bounds as disjoint: bounds cannot prove exact key uniqueness.
- Keep rejecting every ambiguous bound: this contradicts the Phase 2 incremental operation
  requirement for ordinary multi-instrument fragments.
- Load every key from every file into one Python set: memory grows with total selected rows.
- Add per-instrument bounds to catalog v1: that changes the logical catalog contract and requires
  a migration even though the receipt-verified Parquet keys already provide authoritative proof.
- Deduplicate during selection: it would hide source/publication conflicts and weaken Gate 2.
