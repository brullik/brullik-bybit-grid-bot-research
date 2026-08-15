# ADR-0101: Leakage-safe experiment registry and selection boundary

- Status: accepted
- Authority: design-only; implementation gated by Gate 4
- Date: 2026-08-15
- Extends: ADR-0001, ADR-0003, ADR-0004, ADR-0099, ADR-0100
- Preserves: Gate 2/Gate 3/Gate 4/Gate 5 authority, P-007/P-008 ownership, immutable
  evidence, no-lookahead, and release/live isolation

## Context

The roadmap permits later-phase design before implementation authority is granted. Existing
research documents require chronological walk-forward and out-of-symbol validation, complete trial
history, robustness analysis, and a final test that is not used for tuning. They do not yet freeze
the experiment registry lifecycle, deterministic specification/trial/selection identities, outcome
interval treatment at split boundaries, final-test access state, or the boundary between a complete
research result and a Gate 5 owner decision.

Implementing these details ad hoc after Gate 4 would delay selection work and could let retries,
manual retuning, failed-trial deletion, or overlapping outcome horizons leak information into the
reported result. Implementing the registry or running selection now would bypass closed earlier
gates. Choosing numeric acceptance thresholds or resolving P-007/P-008 here would change
owner-controlled governance without evidence.

## Decision

### Authority and activation

ADR-0101 is design-only. It authorizes no experiment schema, registry, split compiler, search,
trial, holdout access, report, acceptance result, strategy release, private request, or live action.
Phase 5 implementation and the parameter-selection programme start only after explicit Gate 4
acceptance by the independent simulator reviewer.

Gate 5 remains a separate owner/PM research decision. A complete experiment or favorable result
cannot accept its own gate, build a release, or become live input. P-007 and P-008 must be resolved
and bound by the qualifying outcome evidence before a primary Phase 5 specification can be
registered; this ADR does not resolve them.

### Immutable experiment specification

Every experiment uses one receipt-last immutable specification registered before its affected
holdout is evaluated. It binds exact hashes and versions for:

- complete feature, candidate, single-grid outcome, and portfolio-result inputs plus their full
  market/catalog/timeline lineage;
- chronological fold, purge, embargo, and out-of-symbol membership definitions;
- the complete staged parameter/search space, selection algorithm, deterministic tie-breaks,
  objective/constraint metrics, complexity treatment, and stopping rules;
- ambiguity, exit, fill, latency, fee/funding, portfolio, and risk policy identities;
- robustness, stress, concentration, multiple-comparison/selection-bias, and sensitivity methods;
- seed set and deterministic random-stream derivation where randomness is used;
- bounded resource/resume policy and supported software/environment compatibility.

An implicit `latest`, mutable notebook variable, undocumented manual exclusion, unregistered trial,
or post-hoc metric/threshold change is forbidden. Changing any semantic input creates a new
specification identity and preserves the prior specification and results.

```text
experiment_spec_id = sha256(canonical_json({
  experiment_contract,
  source_bundle_sha256,
  split_spec_sha256,
  search_space_sha256,
  selection_policy_sha256,
  robustness_policy_sha256,
  simulation_and_risk_policy_sha256,
  seed_policy_sha256
}))
```

Software/environment identity belongs to an execution run, not to the semantic specification, so
the same registered question can be reproduced independently without changing its meaning.

### Point-in-time splits and information intervals

Split membership is compiled from stable instrument IDs and integer timestamps, never current
symbols or future lifecycle status. Every selectable observation declares both its decision time
and the complete future-information interval used by its outcome. A training/validation row is
admissible only when its required outcome information ends within that role's allowed interval.
Rows with truncated, missing, ambiguous beyond the registered policy, or boundary-crossing evidence
are retained with explicit status but cannot silently enter a qualifying metric.

Chronological boundaries derive a conservative purge from the maximum registered future/outcome
dependency. Any additional embargo is explicit and versioned. If the implementation cannot prove a
finite bound for required future information, the split fails closed. Feature/candidate lookbacks
remain governed by the earlier closed-candle no-future contract and are bound for audit; no future
feature or current metadata is introduced by the split compiler.

Walk-forward fold order, expanding/rolling training policy, and whether earlier evaluated periods
may enter later training are frozen in the specification. Out-of-symbol membership is frozen by
stable ID before selection and is excluded from search, manual rule changes, and threshold tuning.
Universe and lifecycle eligibility remain evaluated at each historical decision time.

### Final-test state boundary

Each registered specification has an append-only logical access lifecycle:

```text
development -> selection_frozen -> final_test_authorized -> final_test_consumed
```

Development may read only registered train/validation roles. `selection_frozen` commits the chosen
parameter table, ranking/portfolio policy, complete trial inventory, code/software identity, and
all required pre-final reports. `final_test_authorized` is a separate review record proving the
freeze is complete; it changes no selection content. Final-test execution is one receipt-bound run
from that exact freeze and transitions to `final_test_consumed` whether it succeeds, fails, or
produces a rejection.

After final-test evidence has been observed, changing code, parameters, splits, exclusions,
metrics, or policies creates a new specification and records the previous holdout as already seen.
It may support exploratory follow-up but cannot be described as a fresh confirmatory test on the
same evidence. Failed or unfavorable final tests remain in the registry.

This state machine is an anti-leakage research control, not Gate 5 acceptance authority and not a
claim that local market files are cryptographically hidden from the operator.

### Trial, run, and selection identity

Every planned trial has deterministic identity before execution:

```text
trial_id = sha256(canonical_json({
  experiment_spec_id,
  search_stage_id,
  fold_id,
  parameter_id,
  seed_id,
  ambiguity_case_policy
}))
```

A run binds the specification, exact software/environment identity, ordered trial-plan hash, and
seed stream. A retry resumes the same run and reuses only hash-verified complete trial receipts; it
does not allocate a second semantic trial. Different software or semantic inputs produce a new run
or specification as appropriate. Worker count, shard size, completion order, and restart cannot
change trial results or the selected table.

Every planned trial is retained as complete, failed, rejected, or not-run with a reason. The
selection receipt binds the full planned/observed trial inventory, canonical metrics, deterministic
tie-break result, selected parameter table, and robustness evidence. Missing trials, non-finite
metrics, incompatible ambiguity cases, arithmetic disagreement, or unexplained nondeterminism
blocks selection completion.

### Registry, metrics, and component boundary

`apps/research` owns the offline registry, split compilation, bounded search orchestration,
immutable result/report publication, and review-pack construction. Stable schemas and canonical
identity helpers live in `packages/contracts`; no selection semantics are imported by data,
private-Bybit, release-builder internals, or live. The release application may later consume only a
complete Gate-5-approved evidence reference through the strategy-release contract; it cannot read
an implicit latest experiment or choose parameters.

Specifications, plans, trial results, selections, final tests, and reports use building/failed or
complete receipt-last publication and are immutable after completion. Registries are append-only;
deletion, overwrite, and status inference from file presence are forbidden. Whole-plan admission
and capacity preflight occur before mutation, and bounded resume avoids recomputing verified work.

Metric contracts define population, units, weighting, missing/ambiguous treatment, aggregation,
finite numeric encoding, and deterministic comparison/tie policy. Aggregate analytics may use
documented binary floating point only where an ambiguity band or exact comparison reconstruction
prevents a rounding difference from changing eligibility or selection. Reports include all frozen
folds, symbols/groups, periods, regimes, costs, ambiguity, failures, concentration, tails,
capital-lock, and sensitivity views required by the unchanged gates; no favorable subset may be
silently substituted.

Exact persisted schemas, state/event reason codes, split formulas, metric definitions, and
selection algorithms are delivered in the first post-Gate-4 contract increment. They are
append-only versioned contracts and do not reinterpret prior feature, candidate, or outcome data.

## Consequences

- Phase 5 can start immediately after Gate 4 with a fixed registry, split, identity, and holdout
  boundary.
- Retries reuse verified trials without duplicating semantic work or hiding failures.
- Outcome horizons, lifecycle membership, manual retuning, and repeated final-test access cannot
  become silent selection leakage.
- Complete research evidence remains separate from Gate 5 acceptance and release promotion.
- P-007/P-008, numeric thresholds, Gate 2/Gate 3/Gate 4/Gate 5 criteria, PM-owned tests, risk
  limits, private endpoints, and live permissions remain unchanged.

## Rejected alternatives

- Implement or run Phase 5 before Gate 4: bypasses the accepted roadmap authority.
- Randomly split time-dependent rows: leaks regime and overlapping future-path information.
- Assign rows by decision time while ignoring outcome end: lets future labels cross boundaries.
- Tune on the final test and relabel it validation: destroys confirmatory evidence.
- Keep only successful/best trials: hides selection effort, failures, and bias.
- Use mutable experiment folders or an implicit latest result: breaks identity and reproducibility.
- Let research build/promote its own release: bypasses Gate 5 and the independent release boundary.
