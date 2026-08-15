# M5 Experiment Selection Implementation Plan

## Purpose and authority

This is an engineering handoff, not Phase 5 authorization and not a replacement for PM-owned Gate
5 criteria. Work below starts only after explicit Gate 4 acceptance. ADR-0101 is the architecture
authority; P-007/P-008, metric thresholds, risk policy, and gate decisions remain owner-controlled.

## Prerequisites

- Gate 4 is explicitly accepted by the independent simulator reviewer.
- P-007/P-008 are resolved and bound by complete, immutable simulator/backtest evidence.
- Feature, candidate, outcome, and portfolio inputs are complete, receipt/hash verified, and bound
  through explicit dataset/catalog/timeline/policy identities.
- The first experiment, split, metric, and search contracts are registered before affected holdout
  results are inspected.
- Final-test authorization remains separate from selection freeze and Gate 5 review.

## Reviewable implementation sequence

### M5.1 — Registry, specification, and split contracts

- Add append-only experiment specification, source bundle, split/fold, trial plan/result, selection
  freeze, final-test access/result, report manifest, and receipt schemas.
- Freeze canonical identities, lifecycle transitions, exact timestamp units, information intervals,
  outcome-boundary purge, embargo, stable-symbol holdout, reason codes, and compatibility rules.
- Add fixtures for overlapping outcome horizons, unbounded horizons, future lifecycle knowledge,
  duplicate stable IDs, mutable latest inputs, unauthorized final access, receipt tampering, and
  post-consumption spec changes.
- No search or holdout evaluation in this increment.

### M5.2 — Append-only registry and leakage verifier

- Implement whole-spec preflight and atomic receipt-last registration in `grid-research`.
- Compile chronological/walk-forward/out-of-symbol membership only from stable IDs, integer times,
  registered information intervals, and point-in-time lifecycle evidence.
- Prove purge/embargo coverage, disjoint role authority, deterministic fold membership, immutable
  transitions, stale-building detection, tamper rejection, and idempotent replay.
- Refuse final-test reads until an exact complete selection-freeze review is authorized.

### M5.3 — Bounded deterministic trial orchestration

- Materialize the complete staged trial plan before mutation.
- Execute bounded shards with deterministic seeds and one owner per trial ID.
- Resume only verified complete receipts and preserve failed/rejected/not-run trials with reasons.
- Prove equality across worker count, shard size, completion order, restart, and a clean rebuild.
- Benchmark trial density, outcome-read amplification, throughput, memory, retained size, and resume
  savings before full-scale search.

### M5.4 — Selection and robustness evidence

- Implement versioned finite metric contracts, deterministic comparison/ties, objective/constraint
  evaluation, complexity treatment, and complete selection trace.
- Run registered plateau/perturbation, fold/time/symbol/regime, cost/funding/ambiguity, stress,
  concentration, tail, capital-lock, and selection-bias methods without changing the search space.
- Publish immutable selection-freeze evidence binding every planned trial and all exclusions.
- Fail closed on missing trials, non-finite metrics, ambiguous comparison, incomplete folds, or
  unexplained nondeterminism.

### M5.5 — Authorized final and out-of-symbol evaluation

- Require a separate receipt-bound authorization over the exact selection freeze.
- Execute the frozen final time and held-out-symbol evaluation once, recording success, failure, or
  rejection as consumed evidence.
- Prevent final results from changing parameters, filters, metrics, splits, code identity, or
  primary-report policy in place.
- Label any follow-up using already-seen evidence as exploratory and preserve all prior results.

### M5.6 — Gate 5 owner-review pack

- Reconcile specification, full trial inventory, selection freeze, final result, robustness,
  concentration, costs, ambiguity, tails, capital, software/environment, and report hashes.
- Evaluate the unchanged Gate 5 criteria and publish explicit blockers without building a release.
- Require the owner/PM research decision; implementation cannot accept Gate 5 or authorize Phase 6.

## Cross-cutting verification

- No validation/final/out-of-symbol result influences an earlier search or selection decision.
- No training label/outcome interval crosses its allowed chronological boundary.
- Every planned trial has exactly one terminal receipt/status and is stable across resume/order.
- Final-test access is impossible before exact selection freeze and separate authorization.
- Failed, rejected, incomplete, and unfavorable trials/results remain immutable and reviewable.
- All metrics have frozen population, units, ambiguity/missing treatment, and deterministic compare
  semantics; floating round-off cannot silently change selection.
- `grid-release` cannot infer approval from experiment completion, and `grid-live` remains isolated
  from registry, outcomes, simulator, DuckDB, Polars, and historical stores.
- Performance evidence records exact command, scope, hardware, memory, elapsed time, trial counts,
  and software identity without inventing a Gate 5 threshold.

## Explicit non-goals

- No Phase 5 implementation or holdout evaluation while Gate 4 is closed.
- No resolution of P-007/P-008, metric/acceptance threshold, risk-limit, or gate decision.
- No deletion or suppression of failed/unfavorable trials.
- No strategy release build, verification, promotion, shadow/live integration, or trading action.
- No private endpoint, credential, order, bot, position, transfer, or account action.
- No modification of Gate 2/Gate 3/Gate 4/Gate 5 acceptance criteria or PM-owned tests.
