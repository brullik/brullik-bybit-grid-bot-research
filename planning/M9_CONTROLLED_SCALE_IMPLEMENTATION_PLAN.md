# M9 Controlled Scale Implementation Plan

## Purpose and authority

This is an engineering handoff, not Phase 9 implementation authority, a P-010 decision, a real-action
approval, or a replacement for PM-owned Gate 9 criteria. Work starts only after explicit Gate 8
acceptance. Every future concurrency, universe, size/risk, or automation increase remains a separate
exact owner decision under ADR-0105.

## Prerequisites

- Gate 8 is explicitly accepted with complete one-bot create/monitor/close/emergency/restart evidence.
- P-009 deployment/account/key/host authority remains current and reconciled.
- The predecessor one-bot scale envelope, promoted release/epoch, risk policy, live state/audit,
  execution adapter, and private evidence are verified, compatible, unexpired, and non-revoked.
- The effective ceiling remains one and P-010 remains unresolved until an exact proposal is
  accepted; implementation cannot select its value.
- Scale evidence window, denominator, model tolerances, incident taxonomy/budget, rollback, and
  sanitized/private publication contracts are frozen before a stage starts.

## Reviewable implementation sequence

### M9.1 — Contracts and adversarial scale fixtures

- Add append-only scale envelope/change proposal/owner decision, capacity reservation, equity
  high-water, paired-comparison, stage result, incident, and Gate 9 evidence schemas.
- Freeze exact identities, predecessor chains, Decimal/integer units, one-axis transitions,
  capacity-consuming states, strictest-wins limits, and public/private projections.
- Add fixtures for config-only expansion, unresolved P-010, competing signals, orphan reservations,
  external exposure, aggregate/concentration overflow, deposits/unrealized highs, survivor filtering,
  tolerance edits, combined-axis changes, stale approvals, restart, and rollback.
- No credential, network, private request, real mutation, or limit increase in this increment.

### M9.2 — Offline envelope, capacity, and risk core

- Implement immutable envelope/proposal/decision lifecycle and account-level transactional capacity
  reservations with synthetic adapters and an atomic audit outbox.
- Count reserved, awaiting-approval, requested, uncertain, active, and closing states; release only
  after definitive non-create or independently reconciled close evidence.
- Recompute exact per-bot/aggregate capital, intended loss, reserve, drawdown, and concentration for
  the entire account at reservation and every pre-dispatch boundary.
- Prove concurrent signals cannot oversubscribe capacity or capital across process crash/restart.

### M9.3 — Reconciliation and paired evidence

- Extend read-only account-wide reconciliation to every managed and unknown external bot/order/
  position while preserving ADR-0104 one-attempt mutation semantics.
- Build complete eligible-decision cohorts aligned to exact release epochs and mutation-free shadow
  evidence; retain filtered/rejected/expired/capacity-blocked/uncertain/missing observations.
- Compute exact live fees/slippage/funding, timing, exposure, PnL/drawdown, concentration,
  reconciliation, and incident classes against predeclared modeled tolerances.
- Prove changed epochs/tolerances/denominators segment or invalidate evidence instead of rewriting it.

### M9.4 — Separately approved one-axis manual scale stage

- Produce one non-promoting proposal that changes exactly one owner-selected axis; retain the
  effective ceiling of one and unresolved P-010 unless the owner explicitly chooses concurrency
  from complete evidence.
- Require fresh owner approval, current envelope/release/account/risk/evidence preflight, activation
  receipt, and rollback boundary before any changed policy becomes effective.
- Keep `manual_per_create`, exact validate/approval, durable request ledger, no-blind-retry,
  reconciliation, pause, close, and emergency controls unless automation is the separately approved
  axis in a later stage.
- Stop and tighten/pause on any mismatch, breach, uncertainty, stale evidence, or incident-budget
  failure; never proceed automatically to a second axis.

### M9.5 — Equity-size and bounded semi-automation proposals

- Admit a size/risk proposal only after a reconciled realized-cost and cash-flow-adjusted new equity
  high plus separate policy review; reaching the high never activates a limit.
- Define the required manual sample before collection and retain its complete denominator.
- Treat semi-automation as its own exact capability proposal with release/universe/capacity/risk,
  time/expiry, health, pause/emergency, monitoring, and rollback bounds.
- Require a separate owner decision; no generic request, automatic retry, limit mutation, or
  autonomous close/recovery path is introduced.

### M9.6 — Gate 9 owner-review pack

- Reconcile every envelope/proposal/decision/reservation, eligible signal, request/result, exposure,
  cost/funding/slippage class, drawdown/concentration observation, incident, rollback, and evidence
  receipt across complete stage cohorts.
- Publish sanitized aggregate evidence and explicit blockers without private identities, symbols,
  raw market/account values, paths, payloads, or responses.
- Produce a non-promoting Gate 9 decision input and require explicit owner disposition for every
  limit/capability increase; implementation cannot accept Gate 9 or authorize Phase 10.

## Cross-cutting verification

- Effective capacity remains one and P-010 remains unresolved until a receipt-bound owner decision
  selects an exact concurrency value for one stage.
- Local config cannot expand any envelope axis or exchange capability.
- Competing signals cannot exceed bot, capital, intended-loss, reserve, drawdown, or concentration
  limits; uncertain/orphan/external exposure fails closed.
- No binary float reaches risk, reservation, evidence, approval, or payload boundaries.
- No mutation retry or replacement reservation follows timeout, crash, restart, or empty reads.
- One risk-increasing axis changes per stage; tightening and emergency pause remain immediate.
- Deposits, transfers, unrealized profit, or missing costs cannot establish an equity high.
- Paired evidence uses a complete predeclared denominator and immutable model tolerances.
- Semi-automation is absent unless a separate exact owner decision enables a bounded stage.
- Private artifacts remain outside Git and sanitized reports expose no identities or market values.

## Explicit non-goals

- No implementation before Gate 8 and no real-funds action from this plan.
- No P-010 value, scale-envelope approval, manual-sample count, modeled-tolerance threshold, or
  incident-acceptance decision.
- No automatic concurrency/universe/size increase after time, sample count, equity high, or profit.
- No transfer/withdrawal, key-permission expansion, generic endpoint, or automatic mutation retry.
- No modification of Gate 2 through Gate 9 criteria, risk policy, PM-owned tests, or Phase 10
  production/autonomous-entry authority.
