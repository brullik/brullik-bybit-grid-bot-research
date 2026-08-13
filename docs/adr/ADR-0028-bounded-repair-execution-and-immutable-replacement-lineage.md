# ADR-0028: Bounded Repair Execution and Immutable Replacement Lineage

- Status: accepted
- Date: 2026-08-13
- Implements: Phase 2 repair execution and immutable canonical replacement boundary

## Context

ADR-0027 turns a recomputed blocked coverage audit into bounded standard history requests, but it
deliberately performs no market request and cannot change a committed dataset. Executing those
requests independently without an aggregate preflight could exceed the plan's resource/request
bounds. Appending returned rows to the committed Parquet file would violate ADR-0003 and would
erase the relationship between the blocked parent, the repeated source observation, and the
replacement.

A repeated REST request may still return no candle. That outcome is evidence, not permission to
invent a value, accept an absence reason, or publish a nominally repaired dataset.

## Decision

Freeze `grid.bybit-1m-gap-repair-execution/v1` as the receipt-last execution record for one
verified `grid.bybit-1m-gap-repair-plan/v1`. `grid-data execute-history-repair`:

- re-verifies the plan receipt and recomputes it from the bound audit, original Landing job,
  registry, capacity evidence, and canonical parent;
- resolves embedded requests in memory, without writing temporary request files;
- preflights every task and the aggregate Landing bound before any public request or filesystem
  mutation;
- reuses the existing fixed-page, paced, bounded-retry, receipt-resumable history executor;
- runs repair jobs sequentially so task worker pools do not multiply the declared concurrency;
- binds each completed Landing plan/manifest to the exact embedded request, registry, capacity
  evidence, instrument, range, and request limits; and
- returns `passed` only when every planned minute is present exactly once. A repeated empty or
  partial result is preserved as `blocked` and cannot be published as a replacement.

Freeze `grid.canonical-1m-gap-replacement-publication/v1` as the adapter from a passed execution
to a new receipt-last canonical dataset. `grid-data publish-history-repair` re-verifies the full
chain, loads the hash-verified parent, proves that repair keys exactly fill the planned gaps,
rejects overlaps/duplicates/unrequested rows, and proves consecutive one-minute coverage for all
original requested series before mutation.

The replacement identity is deterministic from the parent manifest, repair plan, and execution
evidence. Its manifest contains exactly one `parent_dataset_ids` entry naming the old dataset and
binds the parent manifest, all repair Landing manifests, registry, capacity evidence, plan,
execution, build configuration, and full Git software identity. Publication uses the existing
fresh-host, atomic-directory, receipt-last writer. The parent directory and files are never
edited, renamed, or deleted.

After publication, `grid.canonical-1m-gap-replacement/v1` records a bounded, value-free proof of
the parent/replacement manifest hashes, exact row accounting, zero duplicate/conflicting/
unrequested keys, and immutable lineage. Existing identical execution and replacement evidence
is re-verified rather than overwritten.

These contracts perform public read-only Bybit requests and local market-store writes only after
explicit `--execute`. They do not change the absence-reason policy, register a catalog entry,
compact files, accept Gate 2, or authorize a private/trading endpoint.

## Consequences

- An interrupted multi-gap repair resumes from independently verified task receipts.
- Every task shares one aggregate staging budget, while actual public requests remain bounded by
  both the embedded task limits and the 100,000-request plan ceiling.
- A second `rest_returned_no_data` observation remains blocked. A later retry policy needs a new
  explicit identity/contract rather than deleting or disguising that negative evidence.
- Research can distinguish the blocked parent from the complete child through manifest lineage;
  neither a mutable `latest` path nor in-place Parquet edits are introduced.
- The current real pilot has zero gaps, so this implementation is proven with deterministic
  positive/negative fixtures; measured runtime evidence is created only when a genuine gap is
  observed.
- Compaction and catalog registration remain separate immutable transitions.

## Rejected alternatives

- Execute one embedded request at a time without a whole-plan preflight: resource and request
  admission would not cover the complete operation.
- Run every task worker pool concurrently: declared per-job concurrency would multiply silently.
- Treat an empty repair response as success: source absence is still not an accepted no-trade
  reason.
- Append to or rewrite the parent dataset in place: destroys receipt identity and reproducible
  lineage.
- Publish a child from row counts alone: counts cannot detect an overlap, duplicate, shifted
  minute, or unrequested row.
