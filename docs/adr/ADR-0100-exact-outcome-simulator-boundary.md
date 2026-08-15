# ADR-0100: Exact outcome simulator and portfolio boundary

- Status: accepted
- Authority: design-only; implementation gated by Gate 3
- Date: 2026-08-15
- Extends: ADR-0001, ADR-0003, ADR-0006, ADR-0008, ADR-0099
- Preserves: Gate 2/Gate 3/Gate 4 authority, unresolved P-007/P-008, immutable lineage,
  exact execution arithmetic, and live isolation

## Context

The roadmap permits a later phase to be designed before its implementation gate. The repository
already assigns outcome simulation to `grid-research`, exact reusable strategy/risk semantics to
dependency-light packages, and immutable outcomes to a research-only store. It does not yet freeze
the boundary between decision-time inputs and future-path evidence, the authority for exact grid
math, one-minute intrabar ambiguity, deterministic outcome identity, or the order in which Phase 4
must be implemented.

Leaving those decisions until after Gate 3 would delay outcome work and risks an optimistic
simulator whose behavior cannot be reconciled with later live payload/risk calculations. Writing
simulator code now would bypass the closed Gate 2 and Gate 3 boundaries. Choosing an ambiguity or
exit policy here would also improperly resolve P-007 or P-008 without owner evidence.

## Decision

### Authority and activation

ADR-0100 is design-only. It authorizes no simulator, strategy/risk package, schema, CLI, outcome
dataset, portfolio result, acceptance result, private request, or live action. Phase 4
implementation starts only after an explicit Gate 3 owner decision. Gate 2, Phase 3, and Gate 3
remain governed independently.

P-007 (intrabar ambiguity policy) and P-008 (V1 exit policy) remain unresolved. The first
post-Gate-3 contract increment must expose the supported policy choices and adversarial evidence;
an owner decision must freeze the primary-result policies before a qualifying outcome build.
Until then, no simulator result may claim Gate 4 qualification.

### Explicit source and time authority

Every outcome build binds only explicit, complete, receipt- and hash-verified inputs:

- one candidate dataset and its complete feature/market/timeline lineage;
- trade-price 1m, mark-price 1m, and funding dataset IDs selected from one declared catalog
  revision/content hash;
- point-in-time instrument constraints, lifecycle evidence, and fee/funding policy inputs effective
  at each simulated event;
- one registered parameter set, simulation contract, latency/fill/cost/ambiguity/exit policy set,
  and software identity.

An implicit `latest`, current metadata substituted for historical constraints, or an unversioned
fee/funding assumption is forbidden. Missing, conflicting, unsupported, or incomplete evidence
fails admission before immutable publication.

The candidate's `decision_time_ns` remains the earliest logical decision time. A simulation case
declares non-negative decision-to-intent and intent-to-activation latency. No order, fill, position,
fee, funding charge, or exit may occur before its derived activation time. Future path data is
allowed only inside the outcome/simulation boundary after the decision because it is the object
being measured. It cannot feed back into feature construction, candidate eligibility, candidate
ranking, parameter registration, or historical universe selection. Later experiment splits must
prevent outcome evidence from crossing train/validation/test authority.

### Component and dependency boundary

`packages/strategy-core` is the dependency-light authority for versioned exact grid construction,
parameter interpretation, and deterministic strategy state transitions that must agree between
research and later live payload preparation. `packages/risk-core` is the dependency-light authority
for exact constraint checks, post-quantization intended loss, exposure, and capital reservation.
Both are side-effect free and depend only on stable contracts.

The future `packages/simulator` is research-only. It consumes `contracts`, `strategy-core`, and
`risk-core` and owns deterministic historical event replay, fill/cost accounting, ambiguity
branches, and single-grid outcome state. It has no filesystem, catalog, network, Polars, DuckDB,
application, release, private-Bybit, or live-adapter dependency.

`apps/research` owns read-only catalog admission, bounded orchestration, optional acceleration,
deterministic shards, immutable outcome publication, portfolio simulation, audits, benchmarks, and
reports. Any accelerated path must reconcile with the pure simulator on golden and generated
fixtures. `grid-live` may use compatible `strategy-core` and `risk-core` contracts but cannot
import `packages/simulator` or read candidate/outcome stores.

### Exact parameter and outcome identity

A registered `parameter_id` is independent of output order and source layout:

```text
parameter_id = sha256(canonical_json({
  parameter_contract,
  strategy_family,
  grid_geometry_spec,
  leverage_and_investment_spec,
  risk_and_exit_policy,
  latency_fill_cost_and_ambiguity_policy_versions
}))
```

The exact source bundle includes ordered dataset IDs and manifests, catalog revision/content hash,
timeline/constraint/fee-policy hashes, candidate lineage, and simulator/software identity. Each
persisted case has a deterministic identity:

```text
outcome_id = sha256(canonical_json({
  outcome_contract,
  candidate_id,
  parameter_id,
  simulation_config_sha256,
  source_bundle_sha256,
  ambiguity_case
}))
```

The outcome records both the registered specification and the exact post-quantization geometry,
constraints, investment, leverage, and risk used by the event engine. A source, policy, software,
or quantization change produces a distinct identity; it never rewrites a complete outcome.

### Event ordering and one-minute ambiguity

Events are processed in nondecreasing exchange time with a versioned deterministic priority for
events that share a timestamp. Candle open is first and candle close is last, but one-minute OHLC
does not reveal the path between high and low. A gap between consecutive candles is not an
invented continuous trade path.

Whenever two or more materially different grid, stop, liquidation, exit, or funding sequences are
compatible with the same evidence, the simulator must not select the profitable ordering. The
contract emits a declared set of deterministic ambiguity cases such as resolved, conservative
lower bound, upper bound, excluded, or indeterminate according to the still-owner-controlled
P-007 policy. Branch pruning is allowed only when it proves equivalent exact state and accounting.
Branch caps, unsupported order semantics, and unresolved event priority fail closed or produce an
explicit indeterminate result; they cannot silently collapse to a favorable case.

A price level touch is not automatically a fill. Fill eligibility, maker/taker classification,
partial-fill support, order replenishment, activation, close behavior, slippage, and native-grid
approximations are versioned policy inputs with adversarial fixtures. Exchange-internal behavior
that cannot be supported by the retained evidence is stated as a limitation or indeterminate
case, not guessed. The one-minute-only decision in ADR-0016 remains unchanged; no tick history is
fabricated or required by this ADR.

### Exact accounting and terminal states

All price, quantity, grid, fee, funding, PnL, exposure, liquidation-distance, stop-loss, and capital
reservation calculations use Decimal or explicitly scaled integers with named units and rounding
policies. Binary floating point may be used only for declared aggregate analytics where it cannot
change fill, constraint, risk, eligibility, or qualification. Risk is recomputed after final
quantization and the case fails closed when the intended-loss cap cannot be proven.

Every state-changing event is journaled sufficiently to reproduce exact balances and prove an
accounting invariant that reconciles starting capital, realized/unrealized PnL, fees, funding,
slippage, transfers internal to the simulated grid, and ending equity. The exact sign convention
and equation are frozen with the first implementation contract.

Terminal status is explicit: preflight-rejected, completed under a declared case, truncated by
end-of-data, lifecycle-terminated, indeterminate, or failed. End-of-data, delisting, suspension,
missing close evidence, and a simulation horizon are never silently converted into a profitable
close. P-008 governs which supported exit policy becomes the V1 primary result.

### Deterministic shards, publication, and portfolio replay

Single-grid cases are shardable only by canonical candidate/parameter ownership. One output key is
owned by exactly one core shard; worker count, shard size, restart, and output order cannot change
the canonical result. Whole-build preflight precedes mutation. Outcomes publish as an immutable
receipt-last dataset with exact input/policy/software lineage, duplicate/conflict/orphan/stale
building audits, and idempotent replay.

Portfolio replay consumes only immutable single-grid outcomes and chronologically available
ranking inputs. It enforces one active or uncertain grid per symbol, deterministic tie-breaking,
available capital and reserves, concurrency, cooldown, approval delay/rejection, and uncertain
create/close scenarios. It cannot choose a later-known favorable ambiguity branch or reorder
signals with future outcome knowledge. Portfolio policy and identity are versioned separately from
single-grid outcomes.

Exact persisted schemas, formulas, event priorities, supported policies, ambiguity representation,
and accounting equations are delivered in the first post-Gate-3 contract increment. They are
append-only versioned contracts and do not reinterpret benchmark or candidate artifacts.

## Consequences

- Phase 4 can start from a fixed dependency, time, identity, and publication boundary after Gate 3.
- Research and later live use the same exact grid/risk authorities without installing the
  research-only simulator on the live host.
- One-minute uncertainty remains measurable and cannot become hidden optimistic PnL.
- Outcome and portfolio builds are deterministic, resumable, immutable, and fully lineage-bound.
- P-007/P-008, Gate 2/Gate 3/Gate 4 criteria, PM-owned tests, risk limits, release promotion,
  private endpoints, and live permissions remain unchanged.

## Rejected alternatives

- Implement Phase 4 before Gate 3: bypasses the accepted roadmap authority.
- Put simulation in `strategy-core` or live: couples future-path research to the live runtime.
- Maintain separate research/live grid or risk arithmetic: permits payload and backtest drift.
- Treat every touched level as a known ordered fill: invents information absent from 1m OHLC.
- Pick one favorable intrabar sequence: creates optimistic and non-auditable results.
- Use current constraints/fees or an implicit latest catalog: introduces historical leakage and
  rerun drift.
- Mutate prior outcomes after policy or source changes: breaks reproducibility and reviewability.
