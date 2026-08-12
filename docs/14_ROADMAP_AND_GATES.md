# Roadmap and Acceptance Gates

## Delivery rule

Work advances through evidence-based gates. A later phase may be designed early, but implementation and especially live permissions are not opened until the preceding acceptance criteria are proven. Implementation pull requests may not edit their own PM-owned acceptance tests or weaken scope.

## Phase 0 — Documentation and governance baseline

Deliverables:

- final goal and scope;
- architecture and runtime boundaries;
- data/performance model;
- research/backtest/release/live contracts;
- risk, security, observability, and recovery policies;
- repository controls and planned layout;
- decision/open-question registers.

Gate 0:

- no production code included;
- all documentation links resolve;
- exact 700 × 10-year × 1m capacity stated;
- separate data/research/release/live run modes documented;
- architecture review accepted by owner/PM.

## Phase 1 — Feasibility and benchmark spike

Purpose: replace assumptions with measured evidence before full implementation.

Deliverables:

- public Bybit instruments/pagination study;
- official bulk-history coverage inventory;
- representative 1m trade/mark/funding sample;
- row-width/compression/file-layout benchmark;
- DuckDB/Polars scan and feature benchmark;
- native Futures Grid validate/account feasibility study with no create;
- hardware and disk recommendation.

Gate 1:

- authoritative data sources and coverage gaps documented;
- canonical schema decision recorded;
- partition/bucket/file-size choice supported by benchmark;
- full-scale runtime/storage estimate updated;
- no unresolved blocker to a 700-instrument capacity design.

## Phase 2 — Canonical market-data MVP

Deliverables:

- instrument universe snapshots;
- bulk and REST ingestion paths;
- canonical trade-price 1m, mark-price 1m, and funding datasets;
- idempotent manifests, receipts, gap/duplicate/conflict audits;
- incremental update and repair;
- compaction and catalog.

Scale sequence:

1. synthetic and two-symbol fixtures;
2. 10 instruments × 7 days;
3. 50 instruments × 90 days;
4. representative multi-year subset;
5. full available universe/history.

Gate 2:

- deterministic re-run and repair;
- no mutation before preflight succeeds;
- no duplicate/conflicting canonical keys;
- stale building outputs detected;
- expected coverage explained by listing/delisting metadata;
- performance remains within measured envelope.

## Phase 3 — Feature and candidate platform

Deliverables:

- versioned feature contract;
- lookahead-safe rolling feature kernel;
- horizontal-range candidate detector;
- amplitude/narrow-range classification;
- deterministic sharding with halos;
- feature and candidate stores with lineage.

Gate 3:

- synthetic/golden boundary tests pass;
- full feature parity for batch and future live kernel;
- no future data access;
- candidate density and throughput benchmarked;
- every row has dataset/config/version provenance.

## Phase 4 — Outcome simulation and backtest

Deliverables:

- exact geometric-grid math;
- path-dependent fill/fee/funding/SL simulation;
- intrabar ambiguity policy;
- exchange precision and min/max feasibility;
- portfolio allocator and concurrent-capital model;
- train/validation/test and out-of-symbol framework;
- stress, concentration, and Monte Carlo evidence.

Gate 4:

- simulator invariants and adversarial fixtures pass;
- conservative ambiguity results reported;
- costs cannot be disabled silently;
- portfolio max drawdown and risk-of-ruin reported from 500 USDT baseline;
- no strategy promotion solely from in-sample performance.

## Phase 5 — Parameter selection and robustness

Deliverables:

- reproducible experiment specifications;
- efficient search over sparse candidate outcomes;
- stability/plateau analysis rather than single best point;
- regime/symbol/time robustness;
- experiment registry and review pack.

Gate 5:

- positive out-of-sample expectancy after all modeled costs;
- hard validation gates satisfied;
- no unacceptable profit concentration;
- parameter perturbations do not destroy the edge;
- independent review accepts the evidence or rejects the strategy.

## Phase 6 — Strategy release registry

Deliverables:

- immutable release builder;
- independent verifier;
- promotion/revocation workflow;
- compatibility and rollback policy;
- signed/hashed release evidence.

Gate 6:

- tamper, missing-member, unexpected-member, lineage, and self-hash tests pass;
- live accepts only promoted release;
- revocation works with research offline;
- release rebuild is deterministic or differences are fully explained.

## Phase 7 — Live shadow mode

Deliverables:

- slim live package with no historical dependency;
- public/private stream and REST gap repair;
- rolling feature parity;
- signal/risk/reconciliation/state/audit;
- Telegram status/pause/resume controls;
- no mutating create/close permission.

Gate 7:

- at least 30 calendar days and preferably at least 100 live-like signals;
- live/backtest feature and signal parity explained;
- no duplicate signals across restart;
- uncertain states/reconciliation proven through failure injection;
- latency, freshness, and uptime targets met.

## Phase 8 — Manual minimal-mainnet execution

Deliverables:

- dedicated restricted API key, preferably subaccount;
- validate-before-create;
- exact payload approval;
- one active bot maximum initially;
- close and emergency drills;
- full request/response and state evidence.

Gate 8:

- every creation manually approved;
- per-grid intended loss does not exceed current policy;
- no unresolved state mismatch;
- emergency stop and restart persistence proven;
- owner explicitly accepts continuation.

## Phase 9 — Controlled scale-up

Possible steps:

- one to three concurrent bots;
- wider liquid universe;
- size increases only after new equity highs and policy review;
- semi-automation only after the required manual execution sample;
- independent live performance versus shadow/backtest monitoring.

Gate 9:

- stable operations and reconciliation;
- live costs/slippage/funding within modeled tolerance;
- drawdown/concentration limits respected;
- incident rate acceptable;
- formal owner approval for each limit increase.

## Phase 10 — Production hardening

Deliverables may include:

- dedicated live host and subaccount;
- IP allowlisting, hardened secrets, signed artifacts;
- HA/backup/DR maturity;
- automated promotion protections;
- operational runbooks and on-call process;
- carefully governed autonomous entry, if evidence supports it.

Autonomous trading is not an automatic outcome of the roadmap. It remains an explicit governance decision.
