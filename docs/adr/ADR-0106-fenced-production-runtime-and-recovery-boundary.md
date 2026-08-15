# ADR-0106: Fenced production runtime and recovery boundary

- Status: accepted
- Authority: design-only; implementation gated by Gate 9 and production activation separately
  owner-approved
- Date: 2026-08-15
- Extends: ADR-0001, ADR-0004, ADR-0006, ADR-0102, ADR-0103, ADR-0104, ADR-0105
- Preserves: Gate 2 through Gate 9 authority, owner-signed final acceptance, unresolved operational
  questions, exact risk/scale envelopes, one-attempt mutation, and no autonomous-entry capability

## Context

Phase 10 hardens an evidence-accepted live system for production operation. The roadmap may require
a dedicated host/subaccount, IP allowlisting, hardened secrets, signed artifacts, backup/DR,
promotion protections, and an operational/on-call process. It defines no Gate 10 and explicitly
states that autonomous trading is not an automatic outcome.

Earlier ADRs isolate live from research, verify promoted releases, separate exchange mutation,
precommit one-attempt requests, and bind controlled scale to exact owner-approved envelopes. They do
not yet freeze the trust chain from source commit to running process, prevent two recovered/failover
hosts from mutating the same account, define which state can be restored without replaying an
exchange action, or separate backup/operator/deployment authority. A conventional active-active or
automatic failover can duplicate exposure during a network partition even when both local databases
are individually consistent.

Several required owner inputs remain open: the exact production host/region and subaccount, command
authorities/control channels, freshness and uncertainty intervention limits, emergency policy,
backup destination/retention, manual sample, legal/account restrictions, branch protections, and
promotion/risk/incident ownership. This ADR cannot resolve them by implementation convention.

## Decision

### Authority and production-readiness boundary

ADR-0106 authorizes no schema/package/CLI implementation, host provisioning, account/key creation,
secret access, network/private request, deployment, failover, promotion, rollback, restore into an
active account, order/bot/position mutation, scale increase, autonomous entry, or Gate/final
acceptance decision. Phase 10 implementation starts only after explicit Gate 9 acceptance.

Production activation is a later owner-signed decision over an exact evidence pack. There is no
invented Gate 10. Green CI, an artifact signature, a successful restore, elapsed soak time, or an
available deployment command cannot activate production or autonomous entry.

Before production readiness, all blocking live/operations questions have explicit owner evidence,
including legal/account eligibility. A temporary main-account/minimal-host exception may remain a
pilot but cannot be represented as the target production-hardened deployment. Exact provider,
region, retention, RPO/RTO refinement, approver roles, and control channels stay owner decisions.

### Source-to-runtime trust chain

One immutable `build_attestation` binds the protected source commit, source manifest, reviewed PR and
required checks, build workflow/runner identity, reproducible build inputs, dependency locks, SBOM,
secret/dependency/license scan results, exact artifact members/digests, runtime/dependency versions,
and signature/provenance statement. Artifacts are content-addressed; mutable branch, tag, filename,
container tag, or registry location is never an identity.

Signing, release promotion, deployment approval, and exchange mutation are distinct authorities and
credentials even when one owner temporarily performs several roles. A signature proves artifact
provenance, not strategy promotion, risk acceptance, deployment approval, or permission to trade.
The trust-root/signing technology, branch-protection settings, role assignment, and exception policy
must be explicitly recorded rather than inferred by code.

`grid-live` starts only from an exact `deployment_bundle` that binds:

- signed live artifact/SBOM/provenance digests and compatibility contract;
- promoted, verified, non-expired/non-revoked strategy release and active scale envelope;
- environment/account/key/host/deployment fingerprints and execution epoch;
- redacted configuration/policy hashes, required schemas, network/time/secret-store policy;
- state/audit/backup lineage, restore or predecessor deployment, and rollback candidate;
- owner deployment approval, effective/expiry times, and complete preflight inventory.

Every member is verified before secrets are unsealed. Any missing, stale, conflicting, untrusted,
unsupported, revoked, expired, or mutable identity leaves the process `ready_paused` or failed; it
cannot enter an entry-capable state.

### Dedicated host, subaccount, and least privilege

The production reference deployment is `grid-live` only on a dedicated supported host and dedicated
restricted Bybit subaccount/key, with no withdrawal/transfer permission. Data/research/release build
tools, historical stores, notebooks, compilers, and mutation-unrelated credentials are absent from
the live distribution and host runtime identity.

Host evidence binds supported OS/patch state, disk/state/audit protection, least-privileged service
identity, filesystem ACLs, process supervision, outbound allowlist/firewall, stable time
synchronization, resource limits, secure boot/storage controls where supported, and monitoring. IP
allowlisting is required once the stable host is selected. Unknown inbound control exposure,
unapproved egress, interactive developer state, unsupported patches, clock failure, or policy drift
blocks entries.

Secrets are injected from a protected OS/external secret store after deployment verification,
cannot be printed/serialized/backed up with ordinary state, and are fingerprinted without value.
Key rotation/revocation is a paused, receipt-bound workflow: reconcile, disable/fence the old key or
host, admit and verify the new least-privileged/IP-bound key, restore read capability, reconcile
again, and require explicit resume. Rotation never retries a mutation or clears uncertainty.

### Single-writer fencing and active-passive recovery

Production mutation is single-writer per account/environment. Read-only monitoring/shadow replicas
may coexist, but only one exact deployment epoch may possess a usable mutation credential/network
path. A local database lock, PID file, heartbeat, DNS record, clock lease, or optimistic leader
election alone is not a sufficient fence across hosts.

A standby starts without usable mutation authority and remains `ready_paused`. Planned switch or
disaster failover requires durable proof that the old writer is isolated and its mutation credential
or IP path is revoked/disabled, followed by a monotonically increasing `execution_epoch`, verified
state/audit restore, fresh release/envelope/deployment verification, authoritative exchange/account
reads, complete request/reservation/exposure reconciliation, and explicit owner resume. If the old
writer cannot be conclusively fenced, the standby may monitor read-only but cannot mutate.

All requests, approvals, reservations, state transitions, audits, and exchange reconciliation bind
the execution epoch and deployment identity. A restored nonterminal request remains uncertain and
is never replayed. An epoch increase cannot create a replacement attempt, free an uncertain capacity
reservation, or adopt exposure without exact reconciliation.

Automatic failover may provision, restore, verify, alert, and reach `ready_paused`; it cannot unseal
mutation authority, promote a release, change a scale envelope, send create/close/cancel, or resume
entries. Active-active mutation and shared-network-filesystem runtime databases are forbidden.

### Durable state, backup, restore, and disaster recovery

One versioned `backup_set` is application-consistent and hash-links transactional runtime state,
audit/outbox chain, request and capacity ledgers, release/promotion/revocation/scale registries,
deployment/configuration hashes excluding secrets, emergency/pause state, and prior backup lineage.
It records schema/software compatibility, completed-at time, encryption/key fingerprint, storage
class, retention policy identity, and immutable completion receipt.

Backups are client-side encrypted, integrity checked, immutable/versioned, off-host, and stored in a
separate failure/credential domain. The owner separately selects destination and retention; this ADR
does not claim Q-032 resolved. Exchange credentials, raw approval tokens, and secret-store values are
not copied into the ordinary backup. Recovery obtains new/verified secret authority through the
fenced credential workflow.

Restore writes only to a new isolated target, verifies every hash/schema/predecessor and rejects
truncation, rollback, mixed deployments, unknown files, or incompatible downgrade. It starts paused,
preserves emergency/uncertain states, and reconciles the full exchange account before any resume.
Restore success means receipt-verified state plus exchange reconciliation, not merely readable files
or service startup.

RPO/RTO values remain the provisional targets in the observability document until owner/deployment
evidence refines them. Scheduled drills cover clean restore, corrupt/missing/stale backup, lost host,
compromised credentials, unavailable backup service, schema migration, and old-writer uncertainty.
No drill performs an unapproved real mutation.

### Protected promotion, deployment, update, and rollback

Build completion cannot promote or deploy. Promotion consumes independently verified research/release
evidence and an owner decision; deployment consumes an exact promoted release, signed runtime,
scale envelope, host/account binding, and deployment approval. Protected CI/tests and source manifest
are required inputs but cannot approve their own governance/risk/acceptance changes.

A running binary/config/release is never edited in place. Update creates a new immutable deployment
bundle, pauses entries, verifies compatibility/migration and backup, fences/switches the writer under
the single-writer protocol, reconciles, and requires explicit resume. A rollback is another signed,
compatible, non-revoked deployment decision; it cannot revive a revoked release, loosen risk/scale,
downgrade state silently, or erase the failed deployment/evidence.

Compromise, provenance failure, critical dependency finding, release revocation, branch-protection
failure, or deployment drift blocks new entries and initiates the versioned incident/revoke/rotate/
restore workflow. Existing exposure remains monitored and follows only separately authorized
close/emergency policy.

### Operations, alerting, and incident authority

Versioned runbooks cover deploy/update/rollback, release revoke, credential rotation, entry pause,
uncertain create/close, exchange/data/control-channel outage, unknown exposure, emergency, host loss,
backup/restore, failover, compromise, evidence preservation, and explicit resume. Each runbook binds
authorized roles, prerequisites, commands/capabilities, expected state transitions, stop conditions,
evidence, escalation, and post-incident review.

On-call/owner identities, secondary control channel, severity/response expectations, legal contact,
and final restart authority remain explicit owner inputs. Monitoring and alert delivery are outside
the failed live host where practical, include dead-man/backup/clock/audit/reconciliation/provenance/
capacity health, and never expose secrets or raw private values. Alert acknowledgement cannot mutate
trading state unless it is a separately authenticated, authorized control command.

Failure-injection and game-day evidence proves process/host loss, network partitions, split-brain
attempts, stale/compromised artifacts, secret rotation, state/audit corruption, backup loss/restore,
alert failure, emergency persistence, and owner-controlled recovery. Every drill begins with a
declared non-mutating/synthetic/shadow/private-test authority; real-funds actions require separate
exact approval.

### Autonomous-entry capability remains absent

Production hardening is complete without autonomous entry. The production reference profile retains
only the entry mode separately accepted under the active Phase 9 envelope. A broader autonomous
entry scheduler/approval bypass is absent from the distribution, dependency graph, entry points,
configuration schema, deployment bundle, and credentials. It cannot be enabled by a flag.

Any future autonomous-entry proposal requires a separate governance/architecture decision and
owner authority after adequate manual/semi-automatic production evidence. It must define a finite
release/universe/risk/scale/time envelope, independent watchdog and pause/emergency path, incident
and rollback budgets, legal/account review, and evidence denominator. ADR-0106 does not define,
implement, approve, deploy, or test that capability.

### Production-readiness and final-acceptance evidence

Private build/deployment/host/key/state/backup/restore/failover/incident evidence remains immutable,
permission-restricted, and outside public Git. Public evidence contains sanitized hashes, counts,
result classes, drill coverage, RPO/RTO classes, provenance/scan status, blocker inventory, and owner
decision references without host/account/network identities, raw values, paths, payloads, logs,
secrets, or recovery material.

The Phase 10 implementation produces a non-activating production-readiness pack reconciled against
the existing final success criteria. Owner-signed live approval remains the final authority. The
implementation cannot declare the project accepted, activate production, change Gate 2 through Gate
9, infer acceptance from green checks, or authorize autonomous entry.

## Consequences

- Source, release, scale, deployment, host, and writer authority become independently verifiable.
- Active-passive recovery cannot create two mutation writers merely because both hosts are healthy.
- Backups restore workflow truth without replaying nonterminal exchange mutations or copying secrets.
- Promotion, deployment, update, and rollback remain explicit immutable decisions rather than tags
  or in-place edits.
- Production can be safely operated with manual or separately accepted bounded semi-automatic entry;
  autonomy is neither required nor present.
- Gate 2 through Gate 9 criteria, PM-owned tests, unresolved operational questions, risk/scale limits,
  real-action authority, and owner-signed final acceptance remain unchanged.

## Rejected alternatives

- Invent a Gate 10 in this ADR: the accepted roadmap defines none.
- Treat a signed artifact as permission to deploy/trade: provenance is not promotion or risk authority.
- Use active-active mutation for availability: a partition can duplicate account exposure.
- Elect a writer from host heartbeats/clock leases alone: the old host may still reach Bybit.
- Copy API keys into state backups: expands compromise and split-brain risk.
- Restore over the failed live directory and auto-resume: hides corruption and unreconciled exposure.
- Roll back by mutable tag or revive a revoked release: breaks provenance and lifecycle authority.
- Auto-promote after green CI or a successful DR drill: acceptance remains an owner decision.
- Include autonomous entry in the standard production build behind a flag: configuration error could
  cross a governance boundary.
