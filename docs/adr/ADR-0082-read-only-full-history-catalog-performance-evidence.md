# ADR-0082: Read-only full-history catalog performance evidence

- Status: accepted
- Date: 2026-08-14
- Extends: ADR-0066 and ADR-0080
- Preserves: unchanged Gate 2 performance criterion and data-quality-owner authority

## Context

The 978-dataset candle campaign is now registered and selected from one receipt-verified catalog
revision. Existing performance evidence measures acquisition, canonical verification, the candle
boundary scan, preflight, and a synthetic incremental selector. It does not measure the production
selector across the retained full-history topology, and repeating download or registration would
waste time.

## Decision

Add a bounded, read-only benchmark over the four exact topology-scoped selection requests already
used by `grid.phase2-full-history-catalog/v1`. Before timing, the benchmark verifies the public
catalog result, all four private selection receipts and hashes, their request bindings, the catalog
snapshot, and aggregate inventory. It then runs the production selector concurrently for all four
requests, immediately repeats the same run, and requires identical outputs plus an unchanged
cryptographic fingerprint of the catalog and selected canonical datasets.

Freeze `grid.phase2-full-history-catalog-performance/v1` as the GitHub-safe projection. It contains
only source/catalog hashes, aggregate scope, wall/worker durations, integer throughput, an
aggregate selection fingerprint, non-identifying software/hardware facts, cache disclosure, and
safety limitations. Dataset/instrument identities, request time bounds, object keys, runtime
paths, market values, device identity, account data, and credentials remain private.

The operation performs no network request and no market-store or catalog write. Measurements are
descriptive evidence only: the implementation defines no acceptance threshold, cannot qualify the
owner-reviewed end-to-end envelope, cannot close Gate 2, and cannot authorize Phase 3.

## Consequences

- Full-history selector cost is measured without repeating acquisition, publication, coverage, or
  registration.
- Both uncontrolled-first and immediate-repeat cache states are visible.
- Receipt/file verification remains inside the timed production selector path.
- An input substitution, result mismatch, mutation, incomplete topology, or changed inventory
  fails closed before public evidence is accepted.

## Rejected alternatives

- Re-run the full download: existing receipts already prove the immutable input and the extra
  network cost would not isolate catalog selection.
- Publish the earlier shell wall time: it was not captured by a merged, receipt-bound benchmark.
- Use only synthetic data: ADR-0066 already covers that scope and cannot represent retained
  full-history topology.
- Define a Gate 2 threshold in this implementation: acceptance belongs to a separate owner review.
