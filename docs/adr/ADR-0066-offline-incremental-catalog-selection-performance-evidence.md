# ADR-0066: Offline incremental catalog selection performance evidence

- Status: accepted
- Date: 2026-08-14
- Implements: measured ADR-0065 exact-key selection behavior
- Preserves: unchanged Gate 2 performance criterion and data-quality-owner authority

## Context

ADR-0065 corrected incremental catalog selection by streaming exact Parquet keys when
multi-instrument file bounds cannot prove disjointness. The fallback is bounded by 4,096 rows per
stream and 128 streams, but implementation and unit correctness alone do not show its observed
throughput or prove that the read-only selection leaves a complete store unchanged.

The retained full-history campaign cannot currently supply this measurement because its final 51
candle jobs remain blocked by the documented regional public-API restriction. A measurement
must not fabricate campaign completion, expose retained market data, or be promoted into the
unchanged full-history Gate 2 performance requirement.

## Decision

Add an offline deterministic benchmark that uses the production boundaries to:

1. publish two through 64 disjoint synthetic candle fragments in one month/bucket;
2. use two through 128 same-bucket instruments and a total ceiling of 5,000,000 rows;
3. register every receipt-verified fragment in one production DuckDB catalog transaction;
4. prove at least one ambiguous adjacent first/last bound, so the ADR-0065 exact-key path is
   exercised;
5. execute the identical snapshot-bound selection twice and require identical results;
6. fingerprint every catalog/dataset directory and file before and after both selections; and
7. remove the temporary fixture before returning public evidence.

Freeze `grid.phase2-incremental-catalog-selection-performance/v1` as the GitHub-safe projection.
It contains only bounded aggregate configuration, nanosecond durations, integer rows/second,
correctness facts, an aggregate selection fingerprint, implementation Git identity, software
versions, non-identifying CPU/RAM/platform facts, cache-state disclosure, and explicit safety
limitations. Dataset/instrument identities, timestamps, runtime paths, synthetic market values,
host/device identity, account data, credentials, and the temporary store are excluded.

The default post-merge profile is 16 fragments, 32 instruments, and 720 minutes per fragment:
368,640 exact rows within one UTC month. The evidence records measurements but defines no PM
acceptance threshold and cannot change Gate 2 status.

## Consequences

- Exact-key incremental selection has reproducible observed performance and immutability evidence.
- The benchmark exercises publication, registration, receipt/file reverification, exact-key
  selection, and deterministic repeat rather than a standalone toy merge.
- Resource scope is bounded before fixture construction, and every fixture is temporary.
- A post-merge evidence artifact must bind the immutable implementation commit; development
  timings are diagnostic only.
- Full-history end-to-end performance, coverage, lifecycle metadata, funding cadence, Gate 2,
  Phase 3, private endpoints, and live use remain unchanged and unresolved where already blocked.

## Rejected alternatives

- Publish development timing: it is not bound to immutable merged code.
- Reuse retained market data: it risks paths, identities, values, and mutable external state.
- Measure only a Python heap merge: it omits production receipt and catalog verification costs.
- Define a passing throughput threshold in the implementation PR: Gate criteria and performance
  acceptance belong to their external owner.
- Treat synthetic throughput as full-history evidence: the scopes are materially different.
