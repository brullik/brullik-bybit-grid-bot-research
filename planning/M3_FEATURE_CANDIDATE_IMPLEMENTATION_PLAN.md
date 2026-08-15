# M3 Feature and Candidate Implementation Plan

## Purpose and authority

This is an engineering handoff, not Phase 3 authorization or a replacement for PM-owned Gate 3
criteria. Work below starts only after explicit Gate 2 acceptance. ADR-0099 is the architecture
authority; the roadmap and acceptance-gate documents remain unchanged.

## Prerequisites

- Gate 2 is explicitly accepted by the data-quality owner.
- Inputs are complete, receipt/hash verified, and selected by explicit catalog revision/content
  hash and dataset IDs.
- A verified point-in-time instrument timeline is bound; missing historical metadata is not
  substituted from a future snapshot.
- The first feature/candidate contract and configuration are registered before holdout results are
  inspected.

## Reviewable implementation sequence

### M3.1 — Contracts and adversarial fixtures

- Add append-only feature-row, range-candidate, derived-dataset manifest, and receipt schemas.
- Freeze the closed-candle `decision_time_ns` rule, canonical keys, required source kinds,
  quality/warmup reasons, numeric encoding, formulas, and deterministic IDs.
- Add fixtures for future-row mutation, missing minutes, metadata-before-first-snapshot, exact
  threshold ambiguity, timestamp boundaries, duplicate keys, and manifest tampering.
- No dataset publication in this increment.

### M3.2 — Shared rolling feature kernel

- Add the dependency-light `packages/feature-kernel` package.
- Implement bounded per-instrument rolling state and versioned feature primitives.
- Prove deterministic replay, restart-state equivalence, no-future invariance, and finite/null
  behavior with golden and property-style tests.
- Keep storage, catalog, Polars, network, research orchestration, simulator, and private/live
  adapters outside the package.

### M3.3 — Batch adapter and deterministic shards

- Add read-only explicit catalog admission in `grid-research`.
- Derive `required_halo_minutes` from the frozen dependency graph.
- Implement bounded core/halo shards with one owner per output key and receipt-resumable plans.
- Require canonical equality between unsharded, sharded, and shared-kernel results on controlled
  fixtures; future-row mutation must leave earlier output bytes unchanged.
- Measure controlled-scale throughput and peak memory before the full build.

### M3.4 — Immutable feature store

- Preflight the complete build and current host capacity before mutation.
- Publish feature datasets atomically with complete parent/catalog/timeline/config/software
  lineage, hashes, audit evidence, and a receipt-last commit marker.
- Add duplicate/conflict/orphan/stale-building/hash audits and idempotent replay.
- Keep generated feature data and private runtime state outside Git; publish only sanitized small
  evidence.

### M3.5 — Range candidate baseline and store

- Register the horizontal-range rule/configuration before evaluation.
- Consume only complete feature datasets; no direct future-market or outcome access.
- Emit deterministic candidates plus every hard-filter result/reason, including indeterminate
  threshold and data-quality rejection.
- Publish an immutable candidate dataset with feature/config lineage and deterministic IDs.
- Measure density and throughput without optimizing thresholds against the final test set.

### M3.6 — Gate 3 evidence pack

- Rebuild from fixed source/feature/candidate identities.
- Reconcile batch/shared-kernel parity, shard ownership, no-future tests, lineage, density,
  throughput, memory, and negative cases.
- Preserve blockers and require the research-contract owner decision; implementation cannot accept
  its own Gate 3.

## Cross-cutting verification

- A future source or metadata mutation cannot change an earlier feature/candidate.
- Every output key appears exactly once and is stable across shard size, worker count, and rerun.
- Missing/incomplete evidence fails closed before candidate eligibility or immutable commit.
- Derived stores are immutable after receipt and never consumed while building/failed.
- `grid-live` remains installable without market-store, Polars, DuckDB, research, or historical
  corpus dependencies.
- Binary floating point never reaches tick/quantity rounding or execution payload construction.
- Performance evidence records exact command, data scope, hardware, memory, elapsed time, and
  software identity; it does not invent a new Gate 3 threshold.

## Explicit non-goals

- No Phase 3 implementation while Gate 2 is closed.
- No simulator, outcome path, grid fill, fee/funding PnL, portfolio, or parameter-search code.
- No live integration, private endpoint, credential, order, bot, transfer, or release promotion.
- No choice of profitable thresholds from final-test outcomes.
- No modification of Gate 2/Gate 3 acceptance criteria or PM-owned tests.
