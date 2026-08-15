# ADR-0103: Shadow-live runtime and exactly-once decision boundary

- Status: accepted
- Authority: design-only; implementation gated by Gate 6
- Date: 2026-08-15
- Extends: ADR-0001, ADR-0004, ADR-0006, ADR-0099, ADR-0100, ADR-0102
- Preserves: Gate 2 through Gate 7 authority, release/risk non-weakening, live isolation,
  one-minute closed-candle semantics, and zero exchange mutation in shadow

## Context

Gate 7 requires at least 30 calendar days of shadow evidence and preferably at least 100 live-like
signals. The existing live architecture defines promoted-release admission, closed candles,
rolling features, risk, state, reconciliation, Telegram, and fail-closed operation. It does not yet
freeze the Phase 7 dependency/capability boundary, multi-source decision watermark, exactly-once
signal commit, checkpoint authority, correction/restart behavior, or how shadow proves private
reconciliation without exposing create/close methods.

Waiting until Gate 6 to make those decisions would delay the longest later calendar requirement.
Reusing a mutation-capable execution adapter behind a `dry_run` flag would make a configuration
mistake capable of trading. Implementing shadow now would bypass the closed Gate 6 boundary.

## Decision

### Authority and activation

ADR-0103 is design-only. It authorizes no live/shadow package, schema, CLI, deployment, credential,
network request, stream subscription, validate call, order, bot, position, transfer, create, close,
promotion, or gate decision. Phase 7 implementation starts only after explicit Gate 6 acceptance
by the independent release/security review.

Gate 7 remains a separate live-safety decision. Shadow completion never authorizes mainnet,
manual execution, mutating API permission, or a broader risk/concurrency limit. P-009/P-010 and all
deployment/risk permissions remain owner-controlled.

### Capability-separated shadow executable

Phase 7 runs `grid-live --mode shadow` from the slim live installation, but the shadow dependency
graph exposes no exchange mutation capability. Its private port may contain only read-only account,
position, order, bot-detail, server-time, capability-introspection, and explicitly allowlisted
validate-only operations. Create, amend, cancel, close, transfer, withdrawal, leverage mutation,
and generic arbitrary-request methods are absent from the interface and adapter registration.

A runtime boolean is not the safety boundary. Architecture tests inspect imports/capabilities and a
shadow startup preflight verifies the configured key/environment has no withdrawal permission and,
where the exchange exposes authoritative permission metadata, no mutating trade permission. If
permission absence cannot be proven, private shadow features remain unavailable and the runtime
fails closed according to the registered shadow policy; it never silently upgrades capability.

Validate-only is optional, separately rate-bounded, hash/audit-bound, and may call only the exact
non-mutating endpoint admitted by its versioned adapter contract. It cannot fall through to create.
Shadow emergency/pause commands persist local control state and report hypothetical actions; they
never close or alter exchange exposure.

### Slim dependency and storage boundary

The shadow installation may depend only on stable contracts, `feature-kernel`, `strategy-core`,
`risk-core`, `release-verifier`, bounded current-data/read-only-private adapters, state/audit, and
control/metrics libraries. It has no data/research/release-builder/simulator/market-store, DuckDB,
Polars, PyArrow, optimizer, notebook, bulk downloader, historical lake, outcome store, or promotion
credential dependency.

It reads one explicit deployment admission bundle and registry proof from ADR-0102, bounded current
market/metadata state, its own transactional state/audit stores, and optional current read-only
account evidence. It never selects `latest`, reads experiment directories, or writes a release.
One process has one active release epoch; release change requires pause, full verification,
reconciliation, bounded window rebuild, and a new epoch before decisions. Overlapping epochs cannot
emit competing shadow intents for one configured strategy instance.

### Release epoch and deterministic identities

Startup derives an immutable epoch identity:

```text
release_epoch_id = sha256(canonical_json({
  release_id,
  promotion_event_id,
  deployment_config_sha256,
  live_contract,
  feature_kernel_version,
  strategy_core_version,
  risk_core_version
}))
```

The unique live-like signal identity is independent of process/restart/output order:

```text
signal_id = sha256(canonical_json({
  signal_contract,
  release_epoch_id,
  category,
  instrument_id,
  decision_time_ns,
  candidate_rule_id
}))
```

The state store enforces a unique semantic key over those same fields. Replayed, duplicate, or
late source messages may update transport/audit counters but cannot emit a second decision or
shadow intent for that key.

### Current-data authority and decision watermark

WebSocket is the normal current-data transport; public REST is the sole bounded repair authority,
not an independent signal source. Every transport message is normalized into the same exact
one-minute semantic inputs used by the shared kernel. The runtime detects duplicates, conflicts,
out-of-order rows, gaps, disconnects, future timestamps, and stale metadata without filling or
guessing values.

For decision minute `t`, the cross-source watermark advances only when every release-required
trade/mark/funding/metadata input is complete and available under its versioned timing rule. A
candle opened at `t` remains usable only at `(t + 60_000) * 1_000_000`; processing latency can delay
but never advance `decision_time_ns`. Missing or conflicting required input yields a durable
`NO_TRADE`/blocked reason and bounded repair, never a partial decision.

REST repair requests are deterministic, range-bounded, rate-limited, and idempotently keyed. Their
responses pass the same timestamp, key, schema, and exact numeric admission as stream data. Until
the repaired continuous window and metadata freshness are proven, affected symbols and any shared
market-context consumers remain blocked.

A source correction received after a committed decision never rewrites or re-emits that decision.
It creates a correction/parity incident, recomputes an audit-only comparison, and pauses affected
new intents when the registered materiality policy cannot prove equivalence. The historical lake is
not mounted for repair or comparison.

### Rolling state and batch parity

The shared dependency-light `feature-kernel` remains the only feature/candidate semantic authority.
Live owns only bounded orchestration and state. Required window size is derived from the promoted
feature graph plus declared repair/replay margin; configuration cannot enlarge it into a historical
corpus or shrink it below warmup.

A rolling checkpoint is a cache, never decision authority. It binds release epoch, kernel contract,
last complete source/watermark keys, exact rolling state hash, state-store transaction ID, and audit
sequence. Restart verifies the checkpoint, repairs current source continuity through REST, and
deterministically replays from the last committed boundary. Missing, stale, future, corrupted, or
incompatible checkpoints are discarded and rebuilt from bounded current evidence without clearing
pause/emergency/reconciliation state.

Gate 7 parity compares online feature/candidate/signal outputs with offline replay of the exact same
captured closed-candle sequence through the same kernel and release. It reports every mismatch and
source correction; aggregate equality cannot hide per-key drift.

### Transactional exactly-once shadow decisions

Runtime workflow state and an audit outbox commit in one durable transaction. The decision record
contains the release/signal identities, complete input/watermark hashes, feature snapshot/hash,
parameter-row hash, every hard-filter/risk/validate verdict, exact hypothetical payload hash,
account-evidence hash where used, timestamps, and reason/status.

The unique semantic key is acquired before evaluation publication. A committed `filtered_out`,
`blocked`, `shadow_eligible`, `shadow_validate_failed`, or `shadow_intent_recorded` state is terminal
for that epoch/key except for append-only audit annotations. Crash before commit leaves no decision;
replay evaluates once. Crash after commit reuses the verified record and drains the idempotent audit
outbox; it never reevaluates into a different intent.

Risk uses the strictest release, promotion, deployment, current exchange/account, data-quality,
reconciliation, pause/emergency, and operational-health result with exact post-quantization
arithmetic. Missing optional account/validate evidence remains explicit and cannot be counted as a
fully feasible Gate 7 signal.

### Read-only reconciliation and control plane

At startup, reconnect, private-stream loss, periodic boundary, and operator request, reconciliation
reads current exchange objects and compares them with local expected shadow state plus any declared
external/manual exposure. Exchange-only, local-only, mismatch, duplicate, unknown, stale, or
unauthorized objects pause new shadow intents and create incidents. Shadow never claims ownership
of or mutates external exposure.

The Phase 7 control surface is limited to authenticated/replay-protected status, pause, resume after
clean reconciliation, and persistent shadow emergency-stop operations. Approve/create/close/
close-all/transfer commands are structurally unavailable and rejected/audited. Telegram is an
optional adapter over the same durable command state machine, not source of truth. Display names
are never identities; tokens/secrets and account identifiers are redacted.

### Startup, registry freshness, and evidence

Shadow reaches `running` only through `starting -> reconciling -> ready_paused -> explicit_resume ->
running`. Preflight verifies exact shadow mode, deployment bundle/member hashes, full-verification
pass, promotion mode/limits/expiry, registry-chain integrity/freshness/revocation, dependency
capabilities, config non-weakening, state/audit durability, clock policy, optional read-only private
capability, exchange reconciliation, required streams, continuous repaired warmup, and control
authorization. Any failure stays paused; restart never clears pause/emergency state.

Gate 7 evidence is receipt-bound and sanitized: calendar duration, eligible/live-like signal count,
per-key feature/signal parity, duplicates prevented, restarts/replays, gaps/repairs, correction and
reconciliation outcomes, release/revocation tests, latency/freshness/uptime, audit durability,
resource bounds, alerts, and failure injection. Public Git receives no symbols, market values,
account/bot/order IDs, runtime paths, raw logs, credentials, or state databases.

Exact persisted schemas, capability lists, source timing/watermark rules, state machines,
transaction/outbox protocol, correction materiality, registry freshness, and shadow evidence
contracts are delivered in the first post-Gate-6 contract increment. They are append-only and do
not reinterpret release/research evidence.

## Consequences

- Phase 7 can start immediately after Gate 6 and begin the required 30-day clock without designing
  mutation safety on the fly.
- Shadow cannot trade even when configuration is wrong because mutation methods are absent.
- Exact identities, transactional uniqueness, and replay prevent duplicate live-like signals.
- The same feature/strategy/risk/release authorities support parity without installing research.
- Gate 2 through Gate 7 criteria, PM-owned tests, P-009/P-010, risk limits, credentials, private
  access, real orders/bots/transfers, and mainnet permission remain unchanged.

## Rejected alternatives

- Implement/deploy Phase 7 before Gate 6: bypasses the accepted roadmap authority.
- Use the production mutating adapter with `dry_run=true`: one flag error could trade.
- Treat WebSocket and REST as competing signal sources: permits duplicate/conflicting decisions.
- Trust checkpoints without bounded REST repair/replay: can preserve stale or gapped state.
- Recompute and overwrite a decision after late correction: destroys exactly-once audit history.
- Use process ID/time as signal identity: duplicates after restart or parallelism.
- Mount historical/research stores on live: violates slim runtime and failure isolation.
- Count blocked or evidence-incomplete intents as fully feasible Gate 7 signals: overstates readiness.
