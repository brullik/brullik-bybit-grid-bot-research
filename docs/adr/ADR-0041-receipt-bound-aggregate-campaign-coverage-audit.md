# ADR-0041: Receipt-Bound Aggregate Campaign Coverage Audit

- Status: accepted
- Date: 2026-08-13
- Implements: representative multi-year canonical coverage orchestration

## Context

ADR-0026 and ADR-0034 define strict read-only audits for one candle or funding dataset. The
representative ADR-0039 publication contains 72 datasets. Running 72 shell commands independently
would provide no immutable aggregate membership, complete-result binding, single status, or
bounded public summary. Publishing every child audit would also expose symbols, instrument IDs,
dataset IDs, diagnostic timestamps, and runtime topology that are unnecessary for GitHub review.

Aggregation must not reinterpret a missing candle, empty funding window, or funding cadence
change. In particular, it cannot make the known no-future-leak policy less strict merely to obtain
a green multi-year result.

## Decision

Freeze `grid.history-campaign-coverage-audit/v1` as the receipt-last aggregate audit for one fully
verified ADR-0039 publication campaign.

`grid-data audit-history-campaign` first re-verifies the source campaign, aggregate publication,
and every canonical child. It then invokes the existing ADR-0026 candle or ADR-0034 funding audit
sequentially for each child in immutable campaign order. Child policy, publisher identity checks,
source/canonical equality, lifecycle checks, missing-minute rules, funding predecessor rules,
empty-window rules, and cadence-change rules remain unchanged.

Full child audit payloads exist only in process memory. The aggregate public projection records
sequence, kind, status, and the canonical content SHA-256 of each child audit plus summed
per-kind inventory, candle/funding quality counters, and unchanged observed reason counts. It
contains no symbol, instrument ID, dataset ID, market value, event timestamp, runtime path,
account data, or credential. The aggregate is `passed` only when every child is `passed`; any
child blocker is preserved in summed unaccepted reason codes and produces `blocked` with CLI exit
code 2.

The result is canonical JSON written atomically with a SHA-256 receipt last. Existing evidence is
not overwritten. The command has no exchange client, credential, repair, catalog, release, or live
dependency.

## Consequences

- One reviewed artifact proves complete audit membership for all 72 published datasets.
- A reviewer can bind every private child result by content hash without publishing runtime
  identities or detailed market diagnostics.
- Aggregation is bounded and sequential; it does not retain canonical tables for multiple children.
- Known candle gaps, empty funding windows, or cadence changes remain blockers under their original
  reason policy.
- A passed aggregate still does not prove a complete historical universe or close Gate 2.

## Rejected alternatives

- Shell-only audit loop: no aggregate receipt, membership, or deterministic overall result.
- Commit every child payload: unnecessarily exposes runtime identities and detailed diagnostics.
- Accept funding cadence changes at aggregate level: bypasses ADR-0034 and may introduce future
  metadata leakage.
- Stop at the first blocker: loses bounded complete negative evidence for the remaining children.
