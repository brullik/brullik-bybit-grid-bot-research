# M4 Outcome Simulator Implementation Plan

## Purpose and authority

This is an engineering handoff, not Phase 4 authorization and not a replacement for PM-owned Gate
4 criteria. Work below starts only after explicit Gate 3 acceptance. ADR-0100 is the architecture
authority; P-007/P-008, the roadmap, risk policy, and acceptance gates remain owner-controlled.

## Prerequisites

- Gate 3 is explicitly accepted by the research-contract owner.
- Candidate/feature inputs are complete, immutable, receipt/hash verified, and selected by explicit
  catalog revision/content hash and dataset IDs.
- Point-in-time constraints, lifecycle, fee/funding policy inputs, and all future-path datasets are
  complete for the declared horizon or produce an explicit incomplete result.
- Parameter, simulation, latency, fill, cost, ambiguity, exit, and portfolio policy spaces are
  registered before affected holdout outcomes are inspected.
- P-007 and P-008 are explicitly resolved before any primary Gate 4 qualification result.

## Reviewable implementation sequence

### M4.1 — Contracts and adversarial fixtures

- Add append-only parameter, simulation-source bundle, single-grid outcome, event journal, outcome
  manifest/receipt, and portfolio-run schemas.
- Freeze exact units, identities, terminal statuses, sign conventions, accounting equation, event
  priorities, supported fill/cost/latency/ambiguity/exit policies, and reason codes.
- Add fixtures for high-before-low/low-before-high ambiguity, gaps, coincident funding/stop/grid
  events, boundary equality, fee and tick/step rounding, partial evidence, end-of-data, lifecycle
  termination, duplicate keys, and manifest tampering.
- No outcome publication in this increment.

### M4.2 — Shared exact strategy and risk primitives

- Implement dependency-light exact grid construction and parameter interpretation in
  `strategy-core`.
- Implement exact constraint, post-quantization risk, exposure, reserve, and intended-loss checks in
  `risk-core`.
- Prove canonical serialization, deterministic replay, rounding-direction fixtures, and identical
  research/later-live results without importing simulator or storage dependencies.

### M4.3 — Deterministic single-grid event simulator

- Implement the pure research-only `packages/simulator` state machine over explicit event streams.
- Admit no fills before activation and no events outside verified source/horizon bounds.
- Emit every required ambiguity case or an explicit indeterminate result; prove branch pruning only
  across exact-equivalent states.
- Reconcile exact event journals, accounting identities, restart-state equivalence, and shard/order
  independence on golden and generated fixtures.

### M4.4 — Bounded outcome orchestration and immutable store

- Add read-only explicit source-bundle admission in `grid-research`.
- Build receipt-resumable candidate/parameter shards with one owner for every canonical output key.
- Preflight the complete plan and current host capacity before mutation.
- Publish outcome datasets atomically with source/policy/software lineage, hashes, audits, and a
  receipt-last commit marker; add duplicate/conflict/orphan/stale-building/idempotent-replay tests.
- Benchmark representative density, throughput, peak memory, branch expansion, and retained size
  before a full build.

### M4.5 — Portfolio allocator and capital-lock replay

- Consume immutable single-grid cases and only chronologically available ranking inputs.
- Enforce one active or uncertain grid per symbol, deterministic ties, concurrency, exact available
  capital/reserves, cooldown, approval delay/rejection, and uncertain create/close scenarios.
- Produce immutable portfolio runs with exact outcome/policy lineage, event journals, capital-locked
  time, drawdown, concentration, rejection, and ambiguity attribution.
- Prove that future PnL cannot influence historical ranking/admission and that worker/order changes
  do not change the result.

### M4.6 — Backtest, stress, and Gate 4 evidence

- Run frozen chronological, walk-forward, and out-of-symbol definitions without final-test leakage.
- Report exact costs, funding, ambiguity bounds/exclusions, failures, duration/capital lock, tails,
  drawdown, concentration, and risk-of-ruin evidence.
- Exercise latency, rejected/uncertain action, stale-data, lifecycle, fee/funding, and adverse path
  scenarios plus Monte Carlo/order-resampling where the frozen methodology permits.
- Publish a non-promoting Gate 4 review pack and require the independent owner decision;
  implementation cannot accept its own gate.

## Cross-cutting verification

- No event or fill precedes candidate decision and declared activation time.
- Mutating source evidence after an event cannot change earlier journal state.
- Exact geometry/risk results match between simulator inputs and later live-compatible primitives.
- Every outcome key appears exactly once and is stable across shard size, worker count, restart, and
  output order.
- Every state transition satisfies the frozen exact accounting equation.
- Missing evidence, unsupported exchange semantics, ambiguity overflow, or unverifiable risk fails
  closed and cannot become a qualifying result.
- Derived stores are immutable after receipt and never consumed while building/failed.
- `grid-live` remains installable without simulator, market-store, DuckDB, Polars, research, or the
  historical corpus.
- Performance evidence records exact command, scope, hardware, memory, elapsed time, branch counts,
  and software identity without inventing a new Gate 4 threshold.

## Explicit non-goals

- No Phase 4 implementation while Gate 3 is closed.
- No resolution of P-007/P-008, numeric acceptance thresholds, or risk-limit changes.
- No parameter optimization, experiment registry, strategy release, shadow/live integration, or
  promotion in the initial simulator increments.
- No private endpoint, credential, order, bot, position, transfer, or account action.
- No tick-history dependency or fabricated intrabar path.
- No modification of Gate 2/Gate 3/Gate 4 acceptance criteria or PM-owned tests.
