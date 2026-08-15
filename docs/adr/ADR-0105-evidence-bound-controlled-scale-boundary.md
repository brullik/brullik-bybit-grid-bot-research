# ADR-0105: Evidence-bound controlled-scale boundary

- Status: accepted
- Authority: design-only; implementation gated by Gate 8 and every scale/capability increase
  separately approved
- Date: 2026-08-15
- Extends: ADR-0001, ADR-0004, ADR-0006, ADR-0100, ADR-0102, ADR-0103, ADR-0104
- Preserves: Gate 2 through Gate 9 authority, unresolved P-010, exact risk, one-bot Phase 8 ceiling,
  explicit owner approval, and no current real execution or scale-up

## Context

Phase 9 may widen concurrency, the eligible liquid universe, size, or entry automation only after a
successful Gate 8 decision. The roadmap requires stable reconciliation, modeled live costs,
respected drawdown/concentration limits, acceptable incidents, and formal approval for every limit
increase. It intentionally leaves the maximum concurrent-bot choice P-010 unresolved.

ADR-0104 makes one active or uncertain bot the global Phase 8 ceiling and gives each mutation one
precommitted request attempt. That prevents duplicate requests but does not yet define how several
independently eligible signals compete for scarce account capacity, how a scale limit is proposed
and activated, how aggregate/concentration risk is reserved atomically, or how live evidence is
compared with shadow/backtest without favorable filtering. A plain configuration edit could race
two creates past the limit or silently combine concurrency, universe, size, and automation changes.

Choosing a P-010 number or implementing scale before Gate 8 would bypass owner evidence. Deferring
all design until Gate 8 would delay a controlled product rollout. This ADR freezes the safety and
evidence boundary only.

## Decision

### Authority and unchanged initial state

ADR-0105 authorizes no schema/package/CLI implementation, credential admission, private request,
deployment, create/close/cancel, order/bot/position, transfer/withdrawal, limit increase,
semi-automatic action, Gate 9 evidence, or Gate decision. Phase 9 implementation starts only after
explicit Gate 8 acceptance and owner continuation.

The effective concurrency ceiling remains exactly one active **or uncertain** managed bot until an
owner resolves an exact P-010 stage proposal from live evidence. This ADR does not select 3, 10, or
any other target. Every concurrency, universe, size, aggregate-risk, or automation increase is a
separate append-only owner decision. Implementing the mechanism does not approve any increase or
any real-funds action.

Phase 9 reuses the separately installed `bybit-execution` capability boundary from ADR-0104. Scale
is policy and state authority in `grid-live`, `contracts`, `strategy-core`, and `risk-core`; it does
not add a broader exchange transport, generic endpoint, automatic retry, or new key permission.

### Immutable scale envelope and one-axis stages

The current authority is one immutable, receipt-last `scale_envelope` bound to:

- Gate 8 decision, owner, environment, account/key/deployment fingerprints, host, and software;
- release, promotion, release epoch, execution/risk/approval/reconciliation contract identities;
- entry mode (`manual_per_create` unless separately changed), admitted universe policy/hash, and
  current exact instrument constraints;
- maximum capacity-consuming bots, per-bot intended loss/investment/leverage, aggregate intended
  loss/capital reservation, collateral reserve, drawdown, symbol/asset/sector/correlation
  concentration, and external-exposure policy;
- data/clock/audit/reconciliation/emergency health, effective/expiry times, and predecessor hash;
- predeclared observation window/sample denominator, modeled cost/funding/slippage tolerances,
  incident taxonomy/budget, comparison rules, and required evidence inventory.

All values are Decimal or scaled integers and the strictest of release, deployment, account,
exchange, emergency, and scale-envelope limits wins. Local configuration can tighten but cannot
expand the envelope. Any missing, stale, incompatible, conflicting, expired, or revoked binding
blocks new entries.

A risk-increasing stage changes exactly one axis: concurrency, eligible-universe policy, per-bot or
aggregate size/risk, or automation mode. Its evidence window and denominator are declared before
activation. A second risk-increasing axis waits for the first stage's complete evidence and owner
disposition. Emergency pause and risk-tightening changes may reduce several axes immediately but
never authorize a new entry or force an unapproved exposure mutation.

### Evidence-bound scale proposal and owner decision

One immutable `scale_change_proposal` binds the predecessor envelope, exact changed axis and old/new
values, P-010 status where relevant, complete prior-stage denominator, live/shadow/model results,
cost/funding/slippage distributions, drawdown/concentration/capacity utilization, reconciliation
latency, incidents/uncertainties, equity high-water evidence where required, rollback plan, and all
source receipt hashes.

Evidence is never selected by profitable bot, surviving symbol, favorable interval, or completed
request alone. Every eligible, filtered, rejected, expired, approved, dispatched, uncertain,
external, closed, and missing-observation case belongs to the declared denominator. Model tolerance
and incident acceptability are frozen before the stage; the implementation cannot retrofit them to
observed results or accept Gate 9.

The owner decision is append-only and binds the exact proposal/envelope hash, changed axis, new
limit/capability, environment/account/release, activation/expiry, rollback boundary, and approver.
Rejection or expiry leaves the predecessor envelope active. Approval activates only after a fresh
preflight proves every binding and current exposure fit; there is no automatic promotion after an
equity high, elapsed time, sample count, green dashboard, or successful request.

### Atomic account-capacity reservation

Before a signal can await create approval, one account-level transaction reserves one capacity
unit and aggregate/concentration capital under the active envelope, records exact signal/release/
proposal identities, and appends the audit outbox event. The transaction serializes competing
signals and recomputes the entire admitted account from authoritative local workflow and fresh
exchange evidence.

Capacity-consuming states include reserved/awaiting-approval, create-requested, create-uncertain,
active, close-requested, and close-uncertain. An expired/rejected proposal releases capacity only
when no request was precommitted. A contract-classified definitive non-creating rejection may
release it after the rejection receipt is durable. A closed bot releases it only after independent
detail/account reconciliation proves the target state and remaining exposure. Orphan, stale,
conflicting, or unreadable reservations fail closed and consume capacity until incident resolution.

Unknown external/manual bot, order, or position exposure does not become managed spare capacity. It
pauses new entries account-wide until explicitly reconciled under the envelope. Capacity reservation
does not authorize create: manual single-use approval and one-attempt dispatch from ADR-0104 remain
mandatory unless a later exact automation-mode decision explicitly replaces per-create approval.
Timeouts and restarts never allocate replacement capacity or resend a request.

### Aggregate risk, concentration, and equity high-water evidence

Every pre-entry boundary recomputes exact post-quantization per-bot and aggregate intended loss,
capital reservation, collateral/free-balance reserve, liquidation/stop interaction, existing and
pending exposure, symbol/underlying/collateral/correlation concentration, drawdown, and emergency
state. Passing each bot separately is insufficient; the complete account must pass atomically.

A size/risk increase additionally requires a reconciled, finalized account-snapshot equity high
above the predecessor stage's deposit/withdrawal/transfer-adjusted high-water mark after known fees,
funding, and realized losses, plus a separate policy review. Unrealized profit, an external deposit,
missing costs, or an unreconciled exchange value cannot establish the high. Reaching a high-water
mark is evidence only and never changes a limit automatically.

Wider-universe admission consumes only a promoted release's already eligible, liquid instruments
and current metadata. It cannot bypass ranking, data quality, release promotion, risk, or exchange
validation, and `grid-live` still cannot read the historical corpus or select/tune parameters.

### Manual sample and bounded semi-automation

`manual_per_create` remains the default. A future semi-automation proposal is a separate capability
increase after a predeclared complete manual-execution sample and owner review. The proposal binds
the exact release/universe, maximum capacity and risk, time window, eligible-signal rules, approval
policy, pause/expiry controls, monitoring, and rollback. ADR-0105 does not define the sample size,
declare it complete, approve semi-automation, or authorize any automatic request.

If separately approved later, semi-automation may act only inside the active immutable envelope;
it cannot change limits, choose another release, bypass fresh validation/risk/capacity reservation,
retry an ambiguous mutation, close outside the accepted policy, or continue through stale data,
unresolved exposure, incident budget breach, audit failure, emergency, expiry, or revocation.
Human status/pause/emergency control remains available and fail-closed.

### Paired live, shadow, and model evidence

Each stage retains the exact eligible-decision population and aligns live outcomes with the same
release epoch's mutation-free shadow decisions and the promoted model assumptions. Evidence records
selection/approval delay, capacity rejection, execution timing, realized fees, slippage, funding,
grid behavior, intended/actual exposure, PnL/drawdown, close path, and all unavailable observations
with exact units and provenance.

Comparisons distinguish strategy/model variance from operator selection, capacity censoring,
exchange constraints, transport/reconciliation uncertainty, and data/runtime failure. Shadow or
backtest is not rewritten to mimic favorable live choices. A release/epoch/model change ends or
explicitly segments the observation cohort; it cannot be silently pooled.

### Breach, pause, rollback, and recovery

Any envelope breach, uncertain/mismatched exposure, aggregate/concentration failure, model-tolerance
breach, unacceptable incident state, stale evidence, or durability failure atomically blocks new
entries and raises an audit incident. Read-only reconciliation, monitoring, and separately
authorized close/emergency risk reduction remain available; automatic liquidation of managed
objects is not implied.

Rollback appends a tighter successor envelope or returns to a still-compatible predecessor after
fresh reconciliation. It never deletes the active stage or its evidence. If current exposure exceeds
a tightened cap, no new capacity is granted; existing exposure follows the accepted close/emergency
policy rather than an invented retry or forced mutation. Restart restores the last durable envelope,
reservations, incidents, and pause state, then reconciles before any resume.

### Gate 9 and public/private evidence

Private envelopes, proposals, approvals, account/exchange snapshots, requests, responses, bot/order/
position identities, values, and incident details remain receipt-last, permission-restricted, and
outside public Git. Public evidence is sanitized aggregate only and hash-binds the private pack. It
contains complete denominator counts, result/tolerance classes, normalized cost/funding/slippage
summaries, drawdown/concentration and reconciliation classes, incident rates/resolutions, stage
transitions, and explicit blockers without symbols, raw market/account values, identities, paths,
or payloads.

Gate 9 still requires stable operations/reconciliation, live costs/slippage/funding within the
predeclared modeled tolerance, respected drawdown/concentration limits, acceptable incident rate,
and formal owner approval for every increase. The implementation produces a non-promoting review
pack; it cannot accept Gate 9, authorize Phase 10, or infer acceptance from green tests.

## Consequences

- Phase 9 can be implemented after Gate 8 without treating a configuration edit as scale authority.
- P-010 remains unresolved until the owner accepts one exact evidence-bound concurrency proposal.
- Atomic reservations prevent concurrent signals from oversubscribing bot, capital, or
  concentration limits.
- One risk-increasing axis per stage preserves attribution while emergency tightening stays fast.
- Size cannot grow from deposits or unrealized/missing-cost equity and never grows automatically.
- Semi-automation remains a separately evidenced capability increase, not a consequence of elapsed
  time or implementation availability.
- Gate 2 through Gate 9 criteria, PM-owned tests, risk limits, credentials, real actions, and Phase
  10 production/autonomy authority remain unchanged.

## Rejected alternatives

- Select three or another P-010 cap in this ADR: lacks the required live capital/risk evidence.
- Read concurrency from editable local config: bypasses owner authority and durable lineage.
- Count only active bots: pending and uncertain requests can oversubscribe the account.
- Reserve per symbol independently: misses aggregate capital and concentration races.
- Increase concurrency, universe, size, and automation together: destroys causal evidence.
- Raise size immediately after a deposit or unrealized equity peak: is not earned live evidence.
- Drop rejected, capacity-blocked, uncertain, or missing cases from comparison: creates survivor bias.
- Automatically promote after N trades/days or a green dashboard: Gate 9 remains an owner decision.
- Give the scale layer a generic exchange request/retry path: breaks ADR-0104 capability safety.
