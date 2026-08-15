# M8 Manual Mainnet Implementation and Drill Plan

## Purpose and authority

This is an engineering handoff, not Phase 8 authorization, real-action approval, or a replacement
for PM-owned Gate 8 criteria. Implementation starts only after explicit Gate 7 acceptance. Each
future credential admission and validate/create/close/emergency mainnet action still requires the
separate owner authority defined by ADR-0104.

## Prerequisites

- Gate 7 is explicitly accepted by owner/live-safety review with complete shadow evidence.
- P-009 is explicitly resolved for account/subaccount, host, key permissions, and IP policy.
- One manual-mainnet release/promotion/deployment bundle is verified, current, compatible,
  unexpired, non-revoked, and limited to the unchanged risk policy and one global bot.
- Exact execution, proposal, validation, approval, request ledger, reconciliation, close/emergency,
  and private-evidence contracts are frozen before a credential or network call.
- Synthetic/failure-injection drills pass before any real-funds action.

## Reviewable implementation sequence

### M8.1 — Contracts, package split, and adversarial fixtures

- Add append-only account/key binding, proposal, validation, approval, create/close request ledger,
  exchange result, reconciliation, emergency plan/result, and Gate 8 evidence schemas.
- Add separate `packages/bybit-execution` with exact method/endpoint capability contracts; retain
  `bybit-private` validate-only semantics unchanged.
- Freeze canonical identities, Decimal/integer units, one-attempt states, matching/reason codes,
  expiries, environment isolation, and global one-active-or-uncertain-bot invariant.
- Add fixtures for forbidden shadow import, generic-request escape, environment fallback, float or
  rounding drift, stale validate/approval, double token use, crash around dispatch commit, lost
  response, zero/multiple matches, external exposure, close uncertainty, and emergency restart.
- No credentials, network, private request, or exchange mutation in this increment.

### M8.2 — Offline state, risk, approval, and request-ledger core

- Implement proposal/validation/approval/request state machines with transactional audit outbox and
  durable global account/symbol locks using synthetic adapters only.
- Recompute exact post-quantization risk, reserves, constraints, payload bytes, and hashes at every
  boundary; strictest limit wins and changed evidence invalidates downstream authority.
- Implement allowlisted owner identity, random one-time token hashing, expiry, replay protection,
  clear MAINNET presentation, and one proposal/approval -> one request identity.
- Prove crash/restart/idempotency and zero request dispatch before durable token consumption.
- Treat every nonterminal precommitted request found after restart as uncertain and reconcile it
  read-only; never send or resend a queued create/close request after restart.

### M8.3 — Restricted transport and read-only reconciliation

- Implement exact-origin/method/endpoint signed transport with no redirect, environment fallback,
  generic request, or automatic retry; keep secrets process/OS-store only and redacted.
- Implement independently authenticated detail/list/account/stream reads and exact response matching.
- Prove unknown/multiple/zero/mismatched objects remain uncertain, block all mutations, and cannot
  allocate a second request.
- Run synthetic and non-mainnet failure injection only until a separate owner credential/network
  authorization is recorded.

### M8.4 — Validate and single-create controlled drill

- Require a fresh explicit owner authorization for mainnet credential admission and validate-only
  call over one exact smallest-feasible promoted signal.
- Publish/inspect the private exact proposal and validate evidence; require a separate exact create
  approval and current pre-dispatch revalidation of every bound fact.
- Commit one request ledger entry, send at most one create call, independently reconcile the result,
  and remain paused with a global ceiling of one active or uncertain bot.
- Stop immediately on any stale/missing/mismatched/uncertain evidence; do not retry or select another
  signal automatically.

### M8.5 — Monitoring, close, emergency, and restart drills

- Monitor/reconcile the one admitted bot and all external exposure with complete redacted private
  evidence.
- Require a new owner approval for normal close; precommit one close attempt and reconcile ambiguity
  without retry.
- Exercise persistent pause/emergency, bounded authorized emergency close policy, process/host
  restart, backup restore, registry revocation, stream loss, and reconciliation before resume.
- Resolve every uncertainty/mismatch before any next operation; preserve all incidents.

### M8.6 — Gate 8 owner-review pack

- Reconcile release/promotion, account/key/deployment, every proposal/validation/approval/request,
  exact risk, response/detail, state/audit, uncertainty, close/emergency/restart, and incident hash.
- Publish sanitized aggregate evidence and explicit blockers without exposing private identities,
  values, paths, payloads, or responses.
- Require explicit owner continuation decision; implementation cannot accept Gate 8, increase size
  or concurrency, or authorize Phase 9.

## Cross-cutting verification

- Shadow installation cannot import/register `bybit-execution`.
- Environment/account/release/signal/payload identity is identical across proposal through result.
- No binary float reaches risk, payload, approval, request, or reconciliation.
- Every approval is single-use, exact, expiring, and grants one attempt only.
- Timeout/lost response never causes an automatic retry; uncertainty blocks the whole account.
- Phase 8 never exceeds one global active or uncertain managed bot.
- Normal close and emergency action require their own exact policy/authority.
- Private artifacts/secrets remain outside Git and sanitized public evidence leaks no identity/value.
- Performance evidence records exact command, host, latency, state transition, and software identity
  without inventing a Gate 8 threshold.

## Explicit non-goals

- No implementation before Gate 7 and no real action without separate explicit owner authority.
- No autonomous entry, retry, close, recovery mutation, size increase, or second bot.
- No transfer/withdrawal or leverage/account configuration mutation.
- No P-010 scale decision or Phase 9 implementation.
- No modification of Gate 2 through Gate 8 acceptance criteria, risk limits, or PM-owned tests.
