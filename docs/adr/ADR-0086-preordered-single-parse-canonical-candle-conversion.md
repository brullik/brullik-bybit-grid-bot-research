# ADR-0086: Preordered single-parse canonical candle conversion

- Status: accepted
- Date: 2026-08-14
- Extends: ADR-0024, ADR-0039, ADR-0067, and ADR-0068
- Preserves: Landing receipts, canonical schemas, admission hashes, and unchanged Gate 2 ownership

## Context

A canonical candle publication fully re-verifies every immutable Landing page before it may write.
The verifier previously decoded every admitted decimal string repeatedly: once while classifying
source quality, again while constructing logical rows, and again while loading the publication
batch. The physical adapter then globally sorted the complete logical batch and built a second
full-size set only to reject duplicate keys.

Those operations are correct but unnecessarily expensive for the first multi-year 1m bootstrap.
The existing contracts already provide stronger ordering facts. A page is unique and reverse
chronological; page tasks are ascending, non-overlapping time windows; and series are unique and
sorted by stable instrument ID. Reversing each verified page while retaining task order therefore
produces the exact canonical `(instrument_id, open_time_ms)` order.

Optimization must not reinterpret old receipts. In particular, source-quality quarantine and
ADR-0068 canonical-admission bindings are hashed in original source/task order, not physical
Arrow order. It must also remain fail-closed if any stored page or future caller violates the
ordering premise.

## Decision

Decode and validate each staged source row exactly once per semantic verification. The page
validator returns both its unchanged source-quality facts and the admitted logical rows. It still
checks exact decimal values, timestamp range/alignment, row width, OHLC invariants, non-negative
trade quantities, and strict reverse chronology.

When loading a publication batch:

1. process tasks in their already verified canonical sequence;
2. update quarantine and canonical-admission bindings in original page/source order;
3. retain only excluded canonical keys for ADR-0068 filtering, never a set of every admitted key;
4. append each page's logical rows in reverse order to one preordered batch; and
5. pass that batch to a new strict physical-adapter entrypoint.

The preordered physical entrypoint validates the dataset type, logical row class, non-empty input,
and strictly increasing unique canonical keys before calling the same exact Decimal128/integer
conversion and partition validation as the general adapter. The existing general adapter remains
available for arbitrary callers and continues to sort before conversion.

This is an internal execution fast path. Landing page bytes and receipts, logical and Arrow
schemas, partition paths, source-quality facts, admission counts/order/hashes, dataset IDs, file
hashes, publication manifests, and receipts retain their existing contracts.

## Consequences

- Publication semantic verification performs one exact decimal parse per source field instead of
  up to three and removes the global `O(n log n)` sort from this contract-proven path.
- Peak logical-row bookkeeping remains one full list of row references plus the normally sparse
  excluded-key inventory; it does not add a full admitted-key set or a second source-order list.
- A preliminary retained 160,043-row trade-child measurement on the owner laptop reduced the
  measured load from 9,480,584,000 ns to 7,672,455,000 ns (1.236x), with equal schema, metadata,
  partition, admission facts, and serialized Arrow table. This is descriptive component evidence;
  cache state was warm/uncontrolled and the post-merge run remains the reproducible reference.
- The implementation still materializes one child batch before immutable publication. Streaming
  Parquet construction would change the writer boundary and requires a separate decision.
- No public request rate, history coverage, lifecycle policy, Gate 2 criterion, Phase 3 authority,
  private API, or live behavior changes.

## Rejected alternatives

- Trust the derived order without checking it: a changed task/page contract could silently create
  non-canonical or duplicate output.
- Keep reparsing and sorting because publication is offline: the initial corpus contains millions
  of rows and this cost directly delays the product-critical bootstrap.
- Build a set of every admitted key: it removes a sort check but materially increases peak memory
  on the constrained owner laptop.
- Change admission hashes to physical order: that would invalidate immutable evidence rather than
  optimize its implementation.
- Introduce streaming publication in the same change: it would alter the writer and atomic-build
  design, expanding both architecture and verification scope.
