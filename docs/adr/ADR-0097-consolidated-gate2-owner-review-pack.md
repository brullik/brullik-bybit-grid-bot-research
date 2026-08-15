# ADR-0097: Consolidated Gate 2 owner-review pack

- Status: accepted
- Date: 2026-08-15
- Extends: ADR-0092, ADR-0094, ADR-0095, and ADR-0096
- Preserves: immutable prior evidence, all seven Gate 2 blockers, owner authority, and Phase 3 isolation

## Context

The already-running downstream chain will publish Gate 2 readiness v4 after the current-universe
candle, funding, and catalog-performance pairs exist. Its pinned contract intentionally preserves
the exact v3 decision and predates three later receipt-bound results: official funding-cadence
policy consistency, bounded legacy listing-event evidence, and full available official lifecycle
announcement matching.

Leaving those results separate would require the owner to repeat receipt/schema/hash verification
and manual aggregate reconciliation during the Gate 2 decision. Editing v4 or its pinned watcher
would weaken immutable evidence and risk disturbing the only active downstream chain.

## Decision

Add `grid.gate2-readiness-pack/v5` and
`python -m benchmarks.gate2_readiness_pack_v5` as an offline, append-only owner-review successor.
It runs only after v4 exists and verifies four artifact/receipt pairs by canonical JSON, JSON
Schema, content hash, artifact hash, contract, and status:

1. the v4 artifact produced by the exact merged ADR-0092 implementation;
2. the exact accepted ADR-0094 funding-cadence artifact;
3. the exact accepted ADR-0095 legacy listing-event artifact; and
4. the exact accepted ADR-0096 official lifecycle-coverage artifact.

The builder requires v4 to preserve the six criteria, three/three readiness split, seven ordered
blockers, closed Gate 2 state, unqualified performance envelope, and mandatory owner decision. It
also verifies that lifecycle evidence binds the exact legacy artifact and the same registry,
reconciles eligible listing/delisting matches, and requires all eleven measured funding cadence
changes to remain explained with zero unexplained changes.

The v5 output exposes only source hashes and review-safe aggregate counts. Funding-cadence,
lifecycle, and performance dispositions remain `pending`; no blocker is removed. The builder
makes no network request, reads no market dataset, mutates no retained state, publishes its
negative artifact atomically, and returns exit code 2.

## Consequences

- The Gate 2 owner receives one receipt-bound review input without repeating acquisition or four
  separate verification workflows.
- The existing v4 watcher and all immutable v1 through v4 artifacts remain untouched.
- Later owner-approved blocker dispositions require a separate governance change; v5 cannot make
  that decision implicitly.
- Source substitution, changed v4 semantics, lifecycle/legacy cross-binding drift, or funding
  policy contradiction fails before publication.
- Gate 2 remains closed and Phase 3 remains unauthorized.

## Rejected alternatives

- Modify v4 to include later evidence: its implementation and runtime watcher are already pinned.
- Rebuild all v3/v4 source chains: v4 already binds and verifies them, so this repeats expensive
  offline work without adding decision evidence.
- Remove the funding or lifecycle blockers from measured positive/partial evidence: only a
  separately authorized owner/governance decision may change Gate 2 classification.
- Wait and assemble the owner pack manually: manual source selection and arithmetic are slower and
  not receipt-reproducible.
