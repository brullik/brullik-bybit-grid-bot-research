# M7 Shadow Live Implementation Plan

## Purpose and authority

This is an engineering handoff, not Phase 7 authorization and not a replacement for PM-owned Gate
7 criteria. Work below starts only after explicit Gate 6 acceptance. ADR-0103 is the architecture
authority; private credentials, deployment, risk limits, P-009/P-010, and gate decisions remain
owner-controlled.

## Prerequisites

- Gate 6 is explicitly accepted by independent release/security review.
- One explicit release/promotion/deployment admission bundle is complete, immutable, compatible,
  unexpired, non-revoked, receipt/hash verified, and authorized for shadow only.
- Shadow capability, current-data timing/watermark, state/audit, correction, reconciliation,
  registry-freshness, and evidence contracts are frozen before network or state mutation.
- Any optional private credential is separately authorized, least-privileged/read-only, has no
  withdrawal permission, and is never committed/logged.

## Reviewable implementation sequence

### M7.1 — Contracts, capability boundary, and adversarial fixtures

- Add append-only release-epoch, current-input/watermark, checkpoint, signal decision, shadow intent,
  state/outbox/audit, reconciliation, control command, and shadow-evidence schemas.
- Freeze exact identities, timing/availability, source precedence, terminal states/reasons,
  capability allowlist, registry freshness, correction, and compatibility rules.
- Define read-only/validate-only ports with no generic request, create, amend, cancel, close,
  transfer, withdrawal, or leverage-mutation method.
- Add fixtures for forbidden imports/capabilities, duplicate/out-of-order/conflicting/future rows,
  cross-source gaps, late corrections, stale checkpoints, clock jumps, revoked releases, state/audit
  failure, restart boundaries, unauthorized control commands, and secret redaction.
- No network, credential, deployment, or exchange action in this increment.

### M7.2 — Slim startup and release admission

- Build/install live with only contracts, kernel/strategy/risk/release-verifier, bounded adapters,
  state/audit, control, and metrics dependencies.
- Verify explicit deployment bundle and registry proof under the startup verifier profile; reject
  implicit latest, stale/forked/revoked/expired evidence and local limit weakening.
- Implement durable control lifecycle through `ready_paused`; restart preserves pause/emergency.
- Prove startup with no history/research/simulator/columnar packages or mounted corpus.

### M7.3 — Current-data gateway and rolling parity

- Implement public stream normalization, closed-candle assembly, deterministic multi-source
  watermark, bounded REST repair, metadata freshness, and release-derived bounded warmup.
- Add verified rolling checkpoints as disposable caches and deterministic restart replay.
- Run golden/generated parity against offline replay of the exact same captured sequence through
  the shared feature kernel.
- Benchmark memory, startup/warmup, repair, and closed-candle-to-decision latency before soak.

### M7.4 — Exactly-once signal/risk/shadow state

- Commit semantic-key uniqueness, decision state, and audit outbox transactionally.
- Apply deterministic strategy/parameter lookup and exact strictest-wins risk calculations.
- Record all filter/block/validate/eligibility facts and hypothetical payload hashes without an
  exchange mutation port.
- Prove crash-before/after-commit replay, duplicate message/restart suppression, durable outbox
  delivery, correction incidents, and no binary float at execution/risk boundaries.

### M7.5 — Read-only reconciliation and control plane

- Add separately authorized read-only private snapshot/stream reconciliation and optional bounded
  validate-only evidence; remain functional in public-only degraded policy where explicitly allowed.
- Pause on unknown/mismatched/external exposure, private-stream loss, auth degradation, or stale
  reconciliation without claiming/mutating exchange objects.
- Implement authenticated status/pause/resume/shadow-emergency commands with replay protection;
  reject and audit every mutation command as unsupported.
- Exercise reconnect, rate-limit, clock, audit/state, registry revocation, Telegram, and backup
  restore failure injection.

### M7.6 — Soak and Gate 7 evidence

- Run at least 30 calendar days and preferably at least 100 complete live-like signals under one or
  explicitly reconciled release epochs.
- Publish receipt-bound sanitized parity, duplicate-prevention, restart, gap/repair, correction,
  reconciliation, release/revocation, latency, freshness, uptime, resource, alert, and incident
  evidence.
- Reconcile every missing/incomplete interval and signal denominator; no favorable subset replaces
  the declared observation window.
- Publish a non-promoting Gate 7 review pack and require owner/live-safety review; implementation
  cannot accept Gate 7 or authorize Phase 8/manual mainnet.

## Cross-cutting verification

- Shadow installation exposes no exchange mutation method or generic private-request escape hatch.
- No decision precedes complete required-input watermark or closed-candle availability.
- Every release/instrument/minute/rule key has at most one committed decision across restart.
- State and audit outbox commit atomically; unavailable durability blocks decisions.
- Checkpoints are never trusted without release/time/source verification and bounded replay.
- Late corrections append incidents and never rewrite/re-emit committed decisions.
- Local config cannot loosen release/promotion/risk/capability limits.
- Public Git evidence contains no runtime paths, symbols, market values, account/order/bot IDs,
  credentials, raw logs, private state, or deployment bundle.
- Performance evidence records exact command, release scope, host, memory, elapsed/latency, signal
  count, and software identity without inventing a Gate 7 threshold.

## Explicit non-goals

- No Phase 7 implementation/deployment/network/private access while Gate 6 is closed.
- No create, amend, cancel, close, transfer, withdrawal, leverage change, or real exposure.
- No Gate 6/Gate 7 decision, promotion, risk/concurrency change, P-009/P-010 resolution, or mainnet
  permission.
- No research, parameter selection, release build/promotion, or historical-lake access from live.
- No modification of Gate 2 through Gate 7 acceptance criteria or PM-owned tests.
