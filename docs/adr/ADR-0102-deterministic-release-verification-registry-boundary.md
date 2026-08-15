# ADR-0102: Deterministic release, verification, and registry boundary

- Status: accepted
- Authority: design-only; implementation gated by Gate 5
- Date: 2026-08-15
- Extends: ADR-0001, ADR-0003, ADR-0004, ADR-0006, ADR-0101
- Preserves: Gate 2 through Gate 6 authority, explicit promotion, immutable research evidence,
  live isolation, risk non-weakening, and no private execution

## Context

The strategy release is the only supported research-to-live interface. Current documents require
an immutable allowlisted bundle, independent verification, explicit promotion/revocation, rollback,
and a deterministic rebuild. They do not yet freeze a non-self-referential content identity,
canonical archive rules, verifier/live-reader ownership, or the event model for lifecycle state.

The planned release directory also lists a status and promotion record inside an immutable bundle.
Changing those members after verification would change the artifact being promoted; hashing the
manifest through itself would be circular. Leaving this unresolved until after Gate 5 would delay
release implementation and could permit mutable status, builder-trusted verification, or an
implicit latest release. Implementing any of it now would bypass the closed earlier gates.

## Decision

### Authority and activation

ADR-0102 is design-only. It authorizes no release schema/package/CLI, build, verification,
promotion, revocation, rollback, registry mutation, deployment, private request, or live startup.
Phase 6 implementation starts only after an explicit Gate 5 owner/PM research decision over the
complete ADR-0101 evidence.

Gate 6 remains a separate release/security review. A complete or verified artifact is not promoted
and cannot be consumed by live without an explicit valid promotion record. This ADR does not
change compatibility, risk, gate, or PM-owned acceptance criteria.

### Three immutable evidence layers

Release lifecycle is a logical fold over three separately immutable layers:

1. **Release payload and build receipt.** The payload contains frozen strategy semantics,
   parameters, compatibility, risk/execution policy, and approved research provenance. Its build
   state is `building -> complete | failed`; only `complete` is verifiable.
2. **Independent verification report.** The verifier recomputes identity, structure, lineage,
   compatibility, and safety checks from artifact bytes and external approved evidence. Reports are
   complete pass/fail artifacts; a pass never mutates the payload.
3. **Append-only registry events.** Promotion, revocation, expiry observation, and rollback
   selection reference exact payload and verification identities. They are never written into or
   used to rewrite the release payload.

The familiar logical lifecycle remains:

```text
building -> failed
building -> complete -> verified -> promoted -> revoked
```

but `verified`, `promoted`, and `revoked` are derived from verified external records, not mutable
files inside the content-addressed release directory. File presence or a copied status string is
never sufficient authority.

### Non-self-referential identity and canonical payload

The release content preimage contains the semantic contract/compatibility identities and an
ordered allowlist of every payload member except the manifest itself and the archive container:

```text
release_content_sha256 = sha256(canonical_json({
  release_contract,
  strategy_semantic_version,
  compatibility_contract_sha256,
  gate5_decision_id,
  parent_experiment_ids,
  ordered_members: [{normalized_path, size_bytes, sha256}]
}))

release_id = "grid-release-" + release_content_sha256
```

`release_manifest.json` stores the exact preimage and resulting ID but does not include its own byte
hash in that preimage. The receipt and archive inventory hash the manifest bytes and every archive
byte separately. Any payload, manifest, path, ordering, policy, compatibility, lineage, or member
change therefore produces a new release/artifact identity without a circular self-hash.

Member paths use one normalized relative UTF-8 representation and canonical case policy. Absolute
paths, drive prefixes, `..`, empty components, duplicate/case-colliding names, noncanonical Unicode,
symlinks/reparse links, devices, and unexpected members are rejected. The contract bounds member
count, uncompressed/compressed size, compression ratio, nesting, and parser resources before
extraction. Verification streams into an isolated staging area and never trusts archive paths.

Canonical JSON, table schemas, column/row ordering, null/finite rules, Parquet writer settings,
archive member order, permissions, timestamps, and compression are versioned. Live-consumed specs
and the bounded parameter table use canonical JSON with exact decimal strings/integer units so the
slim runtime needs no columnar research reader; bulk validation evidence may remain Parquet.
Volatile wall-clock, host, or operator observations belong in the external build receipt. Payload
provenance uses stable software/dependency/evidence identities or a declared reproducible source
epoch. Two admitted builds of the same release preimage must produce identical logical member
hashes; the archive byte hash must also match unless the versioned contract explicitly permits and
explains a container-only difference. Gate 6 decides whether that evidence is acceptable.

### Builder and independent verifier boundary

`apps/release` owns build orchestration and registry commands. The builder reads only explicit,
complete, hash-verified Gate-5-approved research evidence, copies/derives only allowlisted members,
preflights the entire plan, writes to isolated staging, and commits a receipt last. It cannot choose
parameters, reinterpret failed evidence, weaken risk, infer approval from experiment completion,
or access trade credentials.

The future `packages/release-verifier` is the dependency-light semantic authority for artifact and
registry-proof verification shared by the `grid-release verify` command and live startup. It
depends only on stable contracts and bounded archive/canonical-reader ports. It has no builder,
research, market-store, simulator, DuckDB, Polars, network, private-Bybit, live-orchestration, or
secret dependency. A full release-verification profile may receive research-evidence readers from
the release application; a slim startup profile validates all bytes/hashes plus live-consumed
canonical members and the immutable full-verification/registry proof without importing a columnar
reader. The startup profile can never mint a full verification pass.

The verifier treats all builder-generated indexes, counts, IDs, and hashes as claims and recomputes
them from bytes. It validates the exact member allowlist, sizes/hashes, manifest preimage/ID,
canonical serialization, schema compatibility, cross-member identities, complete Gate 5 decision
and lineage, parameter-to-validation provenance, risk/execution non-weakening, secret/mutable-path
absence, and declared live capability matrix. Builder code cannot inject a pass, omit a check, or
write a verifier report. Negative reports are immutable evidence and cannot be overwritten by a
later pass.

### Verification and registry identities

A verification report identity is calculated from a canonical report preimage that excludes its
own ID and binds the exact artifact plus verifier contract/software identity and every check result:

```text
verification_id = sha256(canonical_json({
  verification_contract,
  release_id,
  release_manifest_sha256,
  artifact_sha256,
  verifier_software_sha256,
  ordered_check_results
}))
```

Registry events form an append-only sequence/hash chain. Each event binds registry contract,
monotonic sequence, previous event ID, event kind, release/verification identities, exact owner or
security-review authority, target environment/mode, constraints, timestamps/expiry where required,
reason, and optional rollback target. Single-writer admission or compare-and-append prevents two
events from claiming the same predecessor. Gaps, forks, duplicate sequence, unknown event kind,
invalid authority, or broken hash chain fail verification.

### Promotion, revocation, expiry, and rollback

Promotion is an explicit owner/PM event over one passed independent verification report and one
exact release. It declares the target environment, allowed start mode, active-bot/risk ceiling,
expiry policy, compatibility scope, and optional rollback candidate. Promotion constraints may
equal or tighten release risk/execution limits but can never loosen them. Promotion does not start
live, grant private credentials, or imply permission for a later mode.

Revocation is an append-only security/owner event referencing exact active promotion/release
identity and required consumer response. It takes precedence over every earlier promotion and does
not mutate/delete the artifact. A revoked release cannot silently become promoted again; continued
use requires a new explicitly authorized release/promotion path under the versioned registry
policy. Expiry is evaluated from exact policy and trusted time and cannot be extended by local live
configuration.

Rollback selects one explicit, already verified, promoted, compatible, unexpired, and non-revoked
release/promotion pair. It is a new authorized registry event, not an implicit `previous`, mutable
pointer, file copy, or automatic live action. Failed rollback admission leaves the current safety
state unchanged and blocks unsafe startup/entries.

No consumer may request `latest`. Build, verify, promote, revoke, rollback, export, and live startup
all bind explicit release and registry-event identities. A deployment admission bundle may carry
the exact payload, verification report, promotion event, and registry-chain proof so research can
remain offline; freshness/revocation distribution and fail-closed live behavior remain Phase 7
implementation evidence under unchanged Gate 6/Gate 7 authority.

### Publication, audit, and compatibility

Build plans, payloads, receipts, verification reports, registry events, and deployment admission
bundles are preflight-first, atomic/receipt-last, immutable, idempotently verifiable, and retained
for reconstruction. Runtime registry data, promotion identities, signatures/keys, and deployed
bundles remain outside public Git; only schemas, synthetic fixtures, and sanitized aggregate
evidence are commit-eligible.

Compatibility is an exact fail-closed matrix covering release/schema, feature-kernel,
strategy-core, risk-core, release-verifier, live-state/audit, adapter capabilities, required public
and private endpoint fields, and allowed mode. Unknown, missing, expired, revoked, stale-registry,
or locally weakened compatibility/risk evidence blocks admission. A signature policy may be added
by a later version/ADR, but hashes or an optional signature never replace owner promotion and
revocation authority.

Exact persisted schemas, canonicalization/archive settings, event types, authority model,
compatibility matrix, and verifier check catalog are delivered in the first post-Gate-5 contract
increment. They are append-only versioned contracts and do not reinterpret prior research evidence.

## Consequences

- Phase 6 can start immediately after Gate 5 with a noncircular identity and deterministic build,
  independent verification, and append-only registry boundary.
- Promotion/revocation/rollback never changes the artifact that was reviewed.
- One dependency-light verifier can enforce identical artifact semantics during release review and
  later live startup without importing research or builder internals.
- Explicit identities and receipt verification eliminate implicit latest selection and duplicate
  semantic builds.
- Gate 2 through Gate 6 criteria, PM-owned tests, risk limits, promotion decisions, private
  endpoints, credentials, and live permissions remain unchanged.

## Rejected alternatives

- Implement Phase 6 before Gate 5: bypasses the accepted roadmap authority.
- Store mutable promoted/revoked status inside the release payload: changes verified bytes.
- Hash a manifest through its own byte hash: creates a circular, implementation-dependent ID.
- Trust builder-computed hashes or reuse builder internals as verification authority: defeats
  independent verification.
- Promote `latest successful experiment` or `latest release`: makes selection mutable and
  non-auditable.
- Repackage on promotion/revocation/rollback: breaks content identity and reproducibility.
- Let local live configuration loosen release/promotion limits: bypasses reviewed risk authority.
