# M10 Production Hardening Implementation Plan

## Purpose and authority

This is an engineering handoff, not Phase 10 implementation authority, production activation, a new
Gate 10, a real-action approval, or autonomous-entry authority. Work starts only after explicit Gate
9 acceptance. Every host/account/key admission, deployment/failover/restore into a live environment,
resume, and real mutation remains separately owner-authorized under ADR-0106.

## Prerequisites

- Gate 9 is explicitly accepted with complete controlled-scale operations, cost, drawdown,
  concentration, incident, reconciliation, and limit-increase evidence.
- The production host/region/subaccount, command and incident roles, control channels, freshness/
  uncertainty/emergency policy, backup destination/retention, manual sample, legal/account status,
  branch protection, and final approval ownership have explicit evidence.
- Signed-build trust roots, deployment/fencing authority, state/audit schemas, compatibility/migration,
  RPO/RTO targets, runbook policy, and private/public evidence contracts are frozen before activation.
- The exact promoted release, scale envelope, runtime artifact, deployment bundle, and rollback target
  are verified, current, compatible, non-expired, and non-revoked.

## Reviewable implementation sequence

### M10.1 — Build, deployment, and fencing contracts

- Add append-only build attestation, SBOM/provenance/signature verification, deployment bundle,
  execution epoch/writer fence, host/key admission, backup/restore, failover, runbook/drill, and
  production-readiness evidence schemas.
- Freeze content-addressed identities, predecessor chains, compatibility rules, redacted projections,
  role separation, exact lifecycle states, and fail-closed reason codes.
- Add adversarial fixtures for mutable tags, unsigned/mixed members, self-approved promotion, stale
  scale/release, old writer reachability, split brain, restored nonterminal requests, rollback attacks,
  secret-in-backup, autonomous flag/config, and missing owner evidence.
- No host, secret, network, credential, deployment, private request, or real mutation in this increment.

### M10.2 — Reproducible supply chain and protected promotion/deployment

- Build slim live-only artifacts from protected commits with pinned dependencies, source manifest,
  reproducible metadata, SBOM, secret/dependency/license scans, content digests, and verifiable
  signatures/provenance.
- Implement independent bounded verification for artifact, release, scale envelope, host/account, and
  deployment approval before secret unsealing.
- Prove build completion cannot promote/deploy, local configuration cannot replace immutable members,
  and revoked/expired/incompatible artifacts fail closed.
- Implement pause-first immutable update/rollback plans without in-place binary/config/release edits.

### M10.3 — Hardened host, subaccount, secret, and network profile

- Provision the owner-selected dedicated live-only host/service identity and dedicated restricted
  subaccount/key with no withdrawal/transfer permission and stable IP allowlisting.
- Verify OS/patch/storage/ACL/process/time/resource/egress/monitoring policy and absence of research,
  history, build tools, generic exchange capability, or autonomous-entry artifacts.
- Integrate protected secret injection/redaction/fingerprinting; ordinary backup and telemetry cannot
  read or serialize values.
- Drill paused key rotation/revocation, old-host fencing, fresh admission, read-only reconciliation,
  and explicit resume without replaying mutations.

### M10.4 — Single-writer active-passive and disaster recovery

- Implement external credential/network fencing plus monotonic execution epochs; standby has no
  usable mutation authority and can reach only `ready_paused` automatically.
- Bind every request/reservation/state/audit/reconciliation record to deployment and epoch; restored
  nonterminal actions remain uncertain and never resend or allocate replacement capacity.
- Prove old-writer-unreachable ambiguity, network partition, simultaneous startup, delayed packets,
  clock drift, and stale state cannot yield two mutation writers.
- Require owner-authorized failover only after old writer isolation, restore verification, complete
  exchange/account reconciliation, and current release/scale/deployment preflight.

### M10.5 — Encrypted backup, clean restore, and migration drills

- Publish application-consistent encrypted immutable off-host backup sets in a separate credential/
  failure domain with complete hashes, audit/request/capacity lineage, retention identity, and receipt.
- Exclude exchange credentials, raw approval tokens, and secret-store values.
- Restore only to clean isolated targets; reject corruption, truncation, replay/downgrade, mixed
  deployment, unknown files, stale emergency/uncertainty, and incompatible schema/software.
- Measure declared RPO/RTO classes and reconcile exchange state before explicit resume across clean,
  corrupt, unavailable, compromised-host, and schema-migration drills.

### M10.6 — Operations, monitoring, and incident game days

- Implement versioned runbooks for deploy/update/rollback/revoke/rotate/pause/uncertainty/outage/
  unknown exposure/emergency/host loss/backup/restore/failover/compromise/evidence/resume.
- Bind exact roles, channels, preconditions, stop conditions, state transitions, escalation, and
  evidence; unresolved owner-role/control/legal inputs fail production readiness.
- Exercise external alerts/dead-man, clock/data/private API/audit/state/backup/provenance/capacity
  health and alert-channel failure without leaking private data.
- Run synthetic/shadow/private-test game days first; any real-funds drill requires separate exact
  owner approval and preserves one-attempt/uncertainty semantics.

### M10.7 — Non-activating production-readiness pack

- Reconcile protected source/build/SBOM/signature, release/promotion/scale, host/account/key/network,
  deployment/fencing, state/audit, backup/restore/RPO/RTO, failover, runbooks/roles/alerts/incidents,
  legal/account, and every private/public receipt.
- Publish sanitized aggregate evidence and explicit blockers without private identities, raw values,
  paths, payloads, logs, secrets, or recovery material.
- Require owner-signed final live approval; implementation cannot activate production, invent Gate 10,
  change Gate 2 through Gate 9, or authorize autonomous entry.

## Cross-cutting verification

- Mutable refs/locations never identify a runtime, release, scale envelope, or deployment.
- Signing, promotion, deployment, writer fencing, and exchange mutation remain distinct authorities.
- Exactly one externally fenced mutation writer can exist per account/environment; no automatic
  failover unseals credentials or resumes entries.
- Live distribution/host remains independent of history/research/build tooling and has no autonomous
  entry capability or generic exchange request path.
- Backups are encrypted/off-host/immutable, exclude secrets, and restore paused without replaying
  nonterminal requests.
- Update/rollback cannot revive revoked releases, loosen risk/scale, silently downgrade state, or
  overwrite evidence.
- Every operation and drill is role-bound, stop-condition-bound, receipt-evidenced, and fail closed.
- Public evidence reveals no host/account/network identity, raw private value, secret, or recovery key.

## Explicit non-goals

- No implementation before Gate 9 and no production activation or real action from this plan.
- No Gate 10, host/provider/region, backup destination/retention, role/channel, RPO/RTO refinement,
  legal/account decision, branch-protection setting, or final owner approval.
- No active-active mutation, automatic failover resume, in-place deployment edit, mutation replay,
  secret backup, transfer/withdrawal, or key-permission expansion.
- No autonomous-entry scheduler, approval bypass, dependency, entry point, configuration flag,
  deployment member, credential, or test authority.
- No modification of Gate 2 through Gate 9 criteria, risk/scale policy, PM-owned tests, or owner-signed
  final acceptance.
