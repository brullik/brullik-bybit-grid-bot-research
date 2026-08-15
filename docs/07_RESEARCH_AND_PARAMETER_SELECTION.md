# Research and Parameter-Selection Architecture

## Objective

Identify robust conditions and parameters for horizontal-range native futures grids without lookahead, parameter leakage, or repeated full-corpus computation.

ADR-0099 freezes the design-only Phase 3 boundary while Gate 2 remains closed. A candle opened at
`t` is available only after its close; the corresponding feature key is
`decision_time_ns = (t + 60_000) * 1_000_000`. Builds bind explicit complete catalog datasets and
one point-in-time timeline, never an implicit latest snapshot. The future dependency-light shared
kernel owns semantics; `grid-research` owns read-only batch orchestration, immutable derived
stores, and parity evidence. See the
[M3 implementation plan](../planning/M3_FEATURE_CANDIDATE_IMPLEMENTATION_PLAN.md).

## Research stages

```mermaid
flowchart LR
    A[Committed 1m datasets] --> B[Reusable features]
    B --> C[Candidate detector]
    C --> D[Candidate snapshot]
    D --> E[Future path/outcome builder]
    E --> F[Coarse parameter screen]
    F --> G[Exact grid simulation]
    G --> H[Walk-forward selection]
    H --> I[Robustness and concentration checks]
    I --> J[Release-eligible parameter table]
```

## Range candidate contract

A candidate is a decision-time snapshot, not a retrospectively selected profitable interval. It includes:

- stable `signal_id`;
- instrument ID and signal timestamp;
- lookback length;
- range low/high/mid computed from past data only;
- range height in percent and ATR units;
- current location within range;
- upper/lower-zone touches;
- midpoint crossings;
- amplitude and compression measures;
- slope/horizontality measures;
- volume/liquidity context;
- BTC/market regime context;
- instrument age and metadata version;
- data-quality status;
- feature contract and parent dataset IDs.

V1 requires horizontal ranges and a current price in a configurable mid-zone. Exact thresholds are research variables, not assumptions to be tuned on the final test set.

Candidate identity is independent of shard/output order and binds the parent feature dataset and
contract, category, stable instrument ID, closed-candle decision time, rule identity, and
configuration hash. Missing warmup, source minutes, point-in-time metadata, or required quality
evidence is an explicit rejection, never a future fill or silently eligible candidate.

## Efficient feature strategy

Features are divided into:

### Shared base features

Computed once per feature version:

- returns and true range;
- ATR candidates;
- rolling extrema for candidate windows;
- location within rolling range;
- rolling volume/turnover statistics;
- volatility and trend/regime measures;
- touch/crossing primitives;
- data-quality masks.

### Candidate-derived features

Computed after a candidate window is selected:

- confirmed boundary touches;
- false-breakout counts;
- range symmetry;
- amplitude efficiency;
- fee-relative grid-step feasibility;
- distance from boundaries and liquidation constraints.

### Outcome-only data

Future candles, fills, funding, and exit results are inaccessible to candidate generation and feature selection at signal time.

## Parameter hierarchy

Avoid one giant Cartesian grid. Use staged search:

1. **Structural candidate parameters:** lookback, zones, touch/cross counts, slope, amplitude.
2. **Eligibility parameters:** liquidity, age, fee efficiency, funding context, validate feasibility.
3. **Grid geometry:** lower/upper bounds, grid count, geometric spacing, leverage/investment constraints.
4. **Risk/exit:** SL distance/buffer and blocked conditions.
5. **Portfolio selection:** ranking, concurrency, capital allocation, cooldown.

Each later stage operates on outputs that survived earlier gates.

## Search methodology

ADR-0101 freezes the design-only Phase 5 registry and selection boundary while Gate 4 remains
closed. Experiments register immutable sources, splits, complete search space, metrics, seeds, and
stopping rules before affected holdout access; every planned trial and final-test outcome remains
append-only. See the
[M5 implementation plan](../planning/M5_EXPERIMENT_SELECTION_IMPLEMENTATION_PLAN.md). A complete
experiment cannot accept Gate 5 or build/promote its own strategy release.

- Start with explicit candidate grids and interpretable rules.
- Use coarse-to-fine search around stable plateaus, not isolated maxima.
- Use walk-forward folds; select parameters using train/validation only.
- Reserve a final time test and completely held-out symbols.
- Record all tried configurations, including failures.
- Penalize complexity and parameter sensitivity.
- Correct for multiple comparisons or estimate selection bias.
- Prefer parameter regions that remain acceptable under small perturbations.

## Outcome construction

For every candidate, build future-path evidence sufficient to evaluate parameter variants:

- 1m trade and mark path;
- funding events effective during holding;
- fee schedule effective at decision/execution time;
- current instrument constraints;
- candidate-specific range bounds;
- intrabar ambiguous-event flags;
- delisting/suspension/end-of-data handling.

Where 1m OHLC cannot determine event order inside a candle, the simulator uses a documented conservative policy or marks the outcome ambiguous. It must not choose the profitable ordering.

## Grid simulation tiers

### Tier 1 — cheap feasibility

Reject combinations that cannot satisfy:

- tick-size and quantity-step constraints;
- minimum/maximum investment;
- fee-relative step profit;
- leverage/risk limits;
- maximum 5 USDT loss policy;
- Bybit validate approximations or actual validate evidence where available.

### Tier 2 — event/path simulation

Simulate grid level crossings, fills, fees, funding, realized/unrealized PnL, SL, duration, capital lock, and uncertain intrabar ordering.

### Tier 3 — portfolio simulation

Apply ranking, one-grid-per-symbol, concurrency, available capital, cooldown, approvals, and rejected/failed create scenarios.

## Reproducibility

Every experiment records:

- experiment ID and status;
- parent dataset IDs;
- feature/candidate/outcome versions;
- parameter space and selection algorithm;
- random seed where applicable;
- code/environment identity;
- hardware profile;
- fold definitions;
- metrics and artifacts;
- manifest and hashes;
- rejection/pass conclusion.

## Forbidden research practices

- choosing candidate windows because future PnL looked attractive;
- applying today's instrument list or metadata to old periods;
- tuning on the final test set;
- deleting failed experiments from the registry;
- using gross PnL while omitting fees/funding;
- reporting only average return without tails/concentration/duration;
- silently resolving ambiguous 1m event ordering in favor of the strategy;
- promoting ad hoc notebook variables into live parameters.
