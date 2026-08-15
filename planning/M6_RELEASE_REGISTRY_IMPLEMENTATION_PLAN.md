# M6 Release Registry Implementation Plan

## Purpose and authority

This is an engineering handoff, not Phase 6 authorization and not a replacement for PM-owned Gate
6 criteria. Work below starts only after explicit Gate 5 acceptance. ADR-0102 is the architecture
authority; promotion, risk, environment/mode limits, and gate decisions remain owner-controlled.

## Prerequisites

- Gate 5 is explicitly accepted by the owner/PM research decision.
- The selected experiment/final/robustness evidence is complete, immutable, receipt/hash verified,
  and bound to explicit ADR-0101 identities.
- Release member, canonicalization, compatibility, verifier-check, registry-event, and authority
  contracts are frozen before any build or registry mutation.
- Promotion identity/credentials are isolated from builder and trading credentials.

## Reviewable implementation sequence

### M6.1 — Contracts and adversarial fixtures

- Add append-only release preimage/manifest, member inventory, build plan/receipt, verification
  report, registry event/chain, promotion, revocation, rollback, and deployment-admission schemas.
- Freeze normalized paths, member allowlist/bounds, canonical serialization/archive settings,
  self-excluding identities, lifecycle folds, compatibility matrix, and reason/check codes.
- Add fixtures for self-hash mistakes, missing/unexpected/duplicate/case-colliding/traversal members,
  symlinks, oversized/compression-bomb archives, noncanonical encodings, lineage substitution,
  risk weakening, registry gaps/forks, stale promotion, expiry, revocation, and invalid rollback.
- No release build or registry mutation in this increment.

### M6.2 — Deterministic receipt-last builder

- Implement whole-build admission from one exact Gate-5-approved evidence pack.
- Materialize only the frozen allowlist in isolated staging with canonical bytes and bounded memory.
- Compute the non-self-referential preimage/ID, member hashes, and archive hash; commit the build
  receipt last and preserve failed/stale staging evidence.
- Prove idempotent resume, deterministic logical member/archive hashes on clean rebuilds, immutable
  parents, no mutable/runtime paths, and no secret/private data.

### M6.3 — Independent dependency-light verifier

- Add `packages/release-verifier` without builder, research, storage, network, private, or live
  orchestration dependencies.
- Recompute all structure, hashes, identities, schemas, lineage, Gate 5 decision, policy
  non-weakening, compatibility, path/resource bounds, and secret/mutable-path checks from bytes.
- Keep full research-evidence adapters in the release application; prove the slim startup profile
  needs no Parquet/columnar reader and cannot issue a full verification pass.
- Publish immutable pass/fail reports and prove builder cannot inject/alter a verifier result.
- Use the same verifier contract for the release CLI and later live-startup admission fixtures.

### M6.4 — Append-only registry and promotion

- Implement preflight-first compare-and-append event publication with monotonic sequence and hash
  chain.
- Admit promotion only for one exact complete release and passed verifier report with valid owner
  authority, target environment/mode, expiry, and equal-or-tighter limits.
- Prove idempotency, concurrent predecessor conflict rejection, broken-chain/gap/fork detection,
  explicit-ID lookup, and no implicit latest behavior.
- Keep registry runtime data, identities, and credentials outside public Git.

### M6.5 — Revocation, rollback, and deployment admission

- Publish revocation without rewriting the release and fold it ahead of every earlier promotion.
- Admit rollback only to an explicit verified/promoted/compatible/unexpired/non-revoked pair through
  a new authorized event; never auto-start live.
- Export a bounded deployment admission bundle containing exact payload, verifier report,
  promotion, and registry-chain proof without research artifacts or secrets.
- Prove revocation/rollback verification with research/data offline and reject stale, forked,
  incomplete, expired, or locally weakened bundles.

### M6.6 — Gate 6 evidence pack

- Rebuild the same release independently and reconcile logical/archive hashes or publish every
  allowed container-only difference under the frozen contract.
- Run tamper, missing/unexpected member, self-hash, lineage, secret, compatibility, registry fork,
  revocation, rollback, and offline-consumer fixtures.
- Publish a non-promoting Gate 6 review pack with explicit blockers and require independent
  release/security review; implementation cannot accept Gate 6 or authorize Phase 7.

## Cross-cutting verification

- Payload bytes never change after their complete receipt.
- Verification recomputes builder claims and cannot import builder internals.
- Promotion/revocation/rollback are external append-only events over exact identities.
- Every command requires explicit release/event IDs; no latest lookup exists.
- Local configuration cannot loosen release or promotion risk/mode limits.
- Registry retries append at most one semantic event and reject predecessor races.
- Revocation remains verifiable while data/research are offline.
- `grid-live` remains installable without builder, research, simulator, market-store, DuckDB,
  Polars, historical data, promotion credentials, or trade credentials during verification tests.
- Performance evidence records exact command, artifact size/member count, hardware, memory, elapsed
  time, and software identity without inventing a Gate 6 threshold.

## Explicit non-goals

- No Phase 6 implementation or registry mutation while Gate 5 is closed.
- No Gate 5/Gate 6 decision, promotion, signing-key policy, or risk-limit change.
- No shadow/live implementation, startup, deployment, private endpoint, credential, order, bot,
  position, transfer, or account action.
- No strategy/parameter choice by release tooling.
- No modification of Gate 2 through Gate 6 acceptance criteria or PM-owned tests.
