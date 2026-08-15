# ADR-0104: Manual minimal-mainnet execution and uncertainty boundary

- Status: accepted
- Authority: design-only; implementation gated by Gate 7 and real actions separately approved
- Date: 2026-08-15
- Extends: ADR-0001, ADR-0004, ADR-0006, ADR-0009, ADR-0102, ADR-0103
- Preserves: Gate 2 through Gate 8 authority, exact risk, explicit owner approval, shadow mutation
  isolation, one-bot Phase 8 ceiling, and no current real execution

## Context

Phase 8 introduces the first real-funds mutation only after a successful Gate 7 shadow review. The
current private package intentionally exposes one hard-coded validate endpoint with no redirect,
retry, create, or close path. The target live documents require validate-before-create, exact
payload approval, uncertain-result reconciliation, a single initial bot, close/emergency drills,
and complete evidence, but do not yet freeze package capabilities, mainnet/account binding,
approval/request identities, dispatch durability, or the no-blind-retry protocol.

Adding create/close into the existing validate transport would invalidate its M1 safety proof and
make those methods reachable by shadow installation. Treating a network timeout as permission to
retry can create duplicate exposure. Waiting until Gate 7 to resolve this boundary would delay the
first controlled drill. Implementing or calling it now would bypass the closed gates and the
owner's current no-real-trading authorization.

## Decision

### Authority and activation

ADR-0104 is design-only. It authorizes no package/schema/CLI, credential access, private request,
validate, create, detail, close, cancel, transfer, withdrawal, leverage change, deployment,
approval, bot/order/position mutation, or Gate 8 evidence. Phase 8 implementation starts only after
explicit Gate 7 acceptance by the owner/live-safety review.

Implementation authority does not itself authorize a real request. Mainnet credential admission,
each validate/create/close/emergency drill, and continuation remain separately explicit owner
actions under the future Phase 8 workflow. Gate 8 is a later owner decision and no Phase 9 scaling
is implied.

P-009 must be resolved before any credential is admitted. A dedicated restricted subaccount/key and
stable host/IP allowlist remain preferred; any temporary main-account exception requires recorded
owner risk acceptance. Phase 8 hard-codes a global ceiling of one active **or uncertain** managed
bot across the admitted account/environment. This does not resolve P-010 for later scale above one.

### Capability-separated private packages

`packages/bybit-private` retains its existing non-mutating validate-only boundary and cannot acquire a
mutating endpoint or generic arbitrary-request method. The future `packages/bybit-execution` is a
separate manual-mainnet-only artifact containing only versioned exact create/read/reconcile/close
capabilities required by the accepted Phase 8 contract. It is absent from the shadow distribution,
resolved dependency and runtime import graphs, entry points, adapter registry, and installation
tests.

The mutating transport has an exact endpoint/method allowlist, rejects redirects and origin changes,
never falls back between testnet/demo/mainnet, exposes no generic HTTP escape hatch, and performs no
automatic transport retry. Environment is a typed configuration and is redundantly bound by the
release promotion, deployment, credential fingerprint, proposal, approval, request ledger, audit,
and response. A Demo/Testnet failure can never select Mainnet.

Credentials remain OS-secret-store/process-only, redacted from representations/errors/evidence,
and inaccessible to data/research/release/shadow artifacts. Withdrawal and transfer permissions are
forbidden. Startup verifies key/account/environment capability where authoritative evidence exists;
unknown or broader-than-approved capability fails closed.

### Mainnet admission and minimum-exposure selection

Before a Phase 8 proposal, live must prove exact Gate 7 decision, manual-mainnet release promotion,
registry freshness/revocation, deployment/account/key binding, state/audit durability, clock/data
freshness, bounded current window, feature/signal parity identity, exchange/local reconciliation,
global zero-active-or-uncertain managed bot state, no conflicting external/manual exposure, balance
and reserves, current constraints, and strictest-wins risk capacity.

The first drill may choose the smallest currently feasible investment only among signals already
eligible under the promoted strategy, liquidity/universe policy, exact risk, and current exchange
constraints. Minimum capital never overrides ranking, data quality, stop-loss, intended-loss,
account exposure, or validate requirements. Instrument/market values and account facts stay private.

### Immutable proposal and exact validation

One proposal is a receipt-last immutable object binding:

- environment and non-secret account/key/deployment fingerprints;
- release, promotion, epoch, signal, strategy/risk/adapter contract, and software identities;
- stable instrument/category and complete current constraint/metadata evidence hashes;
- exact pre- and post-quantization bounds, grid count/type/mode, leverage, investment, stop-loss,
  optional take-profit, quantity/price units, rounding policies, and canonical payload bytes/hash;
- fees/funding/slippage assumptions, balance/reserve/exposure snapshot hashes, and exact worst
  intended loss after rounding;
- current data/reconciliation/audit/clock health, proposal expiry, and reason/check inventory.

Binary floating point is forbidden in proposal, validation, risk, approval, request, reconciliation,
or exchange serialization. Every numeric transformation is named and reproduced from Decimal or
scaled integers.

Validate uses only the existing allowlisted non-mutating contract over the exact proposal payload.
Its response/receipt binds request hash, environment, constraint/account evidence, server/client
time, adapter identity, ret/check codes, returned exact limits/minimum investment, and expiry. A
payload, release, constraint, account, balance/exposure, risk, environment, software, or freshness
change invalidates validation and requires a new proposal; stale validation cannot be reused.

### Human approval boundary

A passed validation transitions to `awaiting_approval`, never directly to create. The operator is
shown an unambiguous MAINNET banner and exact human-readable values plus proposal/payload hash,
release, account fingerprint, intended-loss cap, total investment, leverage, stop/TP, expiry, and
current global bot/exposure state.

Approval is an append-only durable event by an allowlisted owner identity. It binds the exact
proposal and validate receipt, environment/account/release/signal/payload hashes, maximum loss,
single-bot ceiling, approval expiry, and one cryptographically random single-use token hash. Raw
tokens are never logged. Any changed byte/fact, expiry, already-consumed token, revoked release,
pause/emergency, failed reconciliation, or newly observed exposure invalidates approval and returns
to a new proposal/validation cycle.

Approval commits durably before dispatch but grants exactly one create attempt for exactly one
request identity. It grants no close, second bot, changed payload, retry, different account,
different environment, or later-mode authority.

### Durable request ledger and one-attempt create

Before network mutation, one transaction consumes the approval token and commits an immutable
canonical request identity, payload bytes/hash, endpoint/method, attempt number fixed to one,
`create_requested` state, global account/symbol lock, and audit outbox record. If that commit
fails, no request is sent. Once it succeeds, neither restart nor operator repetition can allocate a
second create request for the same approval/proposal.

```text
create_request_id = sha256(canonical_json({
  execution_contract,
  environment,
  account_fingerprint,
  release_epoch_id,
  signal_id,
  proposal_id,
  validation_id,
  approval_id,
  method,
  endpoint,
  canonical_payload_sha256
}))
```

A definitive exchange rejection requires an authenticated, fully parsed response whose allowlisted
business code is contract-classified as non-creating; only then may it become `create_rejected`. A
successful response is not `active` until its returned bot identity and independently read
detail/account state reconcile to the exact request. Any timeout, disconnect, parse error, process
loss after dispatch, HTTP ambiguity, missing response, mismatched response, unclassified code, or
uncertain persistence becomes `create_uncertain`. A restart that finds a nonterminal precommitted
`create_requested` state also enters reconciliation as uncertain, even when the crash may have
preceded network dispatch; it never attempts to send the queued request. The transport and
supervisor never automatically resend.

### Uncertain-result reconciliation

`create_uncertain` blocks every new create across the whole admitted account, not only the symbol.
Reconciliation performs only
independent read/list/detail/account/stream operations and compares canonical environment/account,
symbol, mode/type, bounds, grids, leverage, investment/quantity, stop/TP, timing, and request
evidence. Exactly one unambiguous match may be adopted as active with a durable reconciliation
receipt. Zero, multiple, stale, or conflicting matches remain uncertain and require an owner
incident decision; absence in one read is never proof that create failed and never permits retry.

Exchange state is authoritative for actual exposure; local state/request ledger is authoritative
for expected workflow and attempt history. Unknown external bots/orders/positions, any second
active/uncertain object, or identity/amount/price mismatch pauses all mutations and raises a SEV-1
incident. Resolution appends evidence and never overwrites the original request/uncertainty.

### Separate close and emergency boundary

Normal close is a new exact proposal/approval/request workflow over one reconciled bot identity,
current exposure, close policy, expected fees/slippage, and canonical close payload. Create approval
cannot approve close. The close transport also performs one attempt with a precommitted request
ledger; ambiguous outcomes become `close_uncertain`, block further mutations, and reconcile through
independent reads without blind retry. A close response cannot become `closed` until independent
detail/account evidence proves the target state and reconciles remaining exposure; a restart that
finds nonterminal `close_requested` follows the same uncertain protocol and never resends.

Emergency policy is versioned, release/promotion/deployment-bound, rehearsed before the mainnet
drill, and explicitly accepted for the admitted account. An emergency command first durably enters
the persistent emergency state and blocks creates, then executes only its separately authorized
bounded close/cancel plan. ADR-0104 does not preapprove or execute that plan. Restart never clears
emergency or uncertainty and must reconcile before any owner-authorized resume.

### Evidence and Gate 8 boundary

Private proposal/validation/approval/request/response/reconciliation/state/audit artifacts are
receipt-last, hash-linked, encrypted/permission-restricted, backed up, and retained outside public
Git. Public evidence is sanitized aggregate only: explicit approvals, attempts, result classes,
uncertainty durations/resolutions, exact-risk pass/fail counts, restart/emergency/close drill status,
and Gate 8 blockers. It includes no symbols, market values, account/key/bot/order/position IDs,
payloads, responses, balances, runtime paths, logs, credentials, or approval tokens.

Gate 8 requires every creation manually approved, intended loss within unchanged policy, no
unresolved mismatch/uncertainty, emergency/restart persistence proven, and explicit owner
continuation. Implementation cannot accept Gate 8 or increase concurrency/size.

Exact schemas, endpoint/capability allowlists, account/key evidence, proposal/validation expiry,
state machines, request/response matching, close/emergency policy, and sanitized evidence contracts
are delivered in the first post-Gate-7 contract increment. They are append-only and do not
reinterpret shadow/release/research evidence.

## Consequences

- Phase 8 can begin after Gate 7 with a fixed exact approval, dispatch, uncertainty, close, and
  evidence boundary.
- Validate-only safety remains intact; shadow cannot import the mutation package.
- A lost response cannot cause an automatic duplicate bot because every approval permits one
  precommitted attempt and uncertainty blocks retries.
- The first drill minimizes feasible capital only after strategy/risk eligibility and retains one
  global active-or-uncertain bot ceiling.
- Gate 2 through Gate 8 criteria, PM-owned tests, P-009/P-010, risk limits, credentials, real
  requests, orders/bots/transfers, mainnet permission, and Phase 9 scaling remain unchanged.

## Rejected alternatives

- Implement/call Phase 8 before Gate 7 and separate owner approvals: bypasses accepted authority.
- Add create/close to the proven validate-only package: makes mutation reachable by shadow.
- Protect a mutating adapter only with `dry_run`: configuration error can trade.
- Automatically fall back from Demo/Testnet to Mainnet: silently crosses funds boundary.
- Retry create/close after timeout or an empty first read: can duplicate/change exposure.
- Approve editable fields instead of canonical payload bytes: permits approval/request drift.
- Count one active bot per symbol instead of globally in Phase 8: exceeds the initial gate scope.
- Choose the lowest-minimum instrument outside promoted eligibility: bypasses strategy/risk review.
