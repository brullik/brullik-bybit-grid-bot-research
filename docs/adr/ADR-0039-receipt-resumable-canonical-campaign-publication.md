# ADR-0039: Receipt-Resumable Canonical Campaign Publication

- Status: accepted
- Date: 2026-08-13
- Implements: Phase 2 representative multi-year Landing-to-canonical orchestration

## Context

ADR-0038 makes a multi-month trade, mark, and funding acquisition campaign deterministic and
receipt-resumable, while ADR-0024 and ADR-0031 publish exactly one verified Landing job as one
immutable canonical dataset. The measured representative campaign contains 72 completed child
jobs. Invoking those writers through a shell loop would lose aggregate membership, whole-campaign
preflight, deterministic resume state, and an independently verifiable completion boundary.

The single-child writers intentionally materialize one bounded Arrow batch during preflight. An
aggregate coordinator must not retain all child batches simultaneously or sum mutually exclusive
writer workspaces as though every child were written concurrently. It also cannot weaken the
fresh host observation, immutable dataset identity, receipt-last commit, source evidence, or
funding predecessor rules already enforced by the child boundaries.

## Decision

Freeze three runtime contracts:

- `grid.history-campaign-publication-plan/v1`;
- `grid.history-campaign-publication-manifest/v1`; and
- `grid.history-campaign-publication-receipt/v1`.

`grid-data publish-history-campaign` accepts one completed ADR-0038 campaign, the exact bound
instrument registry and capacity evidence, a canonical store, and an immutable full Git publisher
identity. Its default mode performs no mutation. It re-verifies the aggregate campaign and each
child, invokes the existing candle or funding publication preflight one child at a time, records
the deterministic canonical dataset/request/input identities, and releases each Arrow batch
before resolving the next child.

The aggregate resource requirement is the maximum required free-space and peak-memory value of
one child writer, not the sum of all writers. Children execute strictly in source-campaign
sequence with `max_concurrent_writers=1`. Every child budget already includes the complete
evidence-derived active-plus-building reservation, its retained Landing bound, the 8 GiB operating
reserve, and a bounded write workspace. Summing those complete reserves 72 times would be false;
using the maximum remains conservative for sequential execution. Every actual child is
preflighted again from a fresh host snapshot immediately before its own mutation, and its
receipt-last writer performs the existing second host check.

The coordinator writes its deterministic plan and plan receipt before the first canonical
mutation. A child with a matching valid canonical completion receipt is verified and reused; a
missing child alone is written. Conflicting identities, stale building outputs, changed source
artifacts, changed writer calculations, insufficient current resources, or tampered canonical
datasets fail closed. After every child verifies, an aggregate manifest records source and
canonical hashes, dataset types, rows, file counts, and Parquet bytes, then writes its completion
receipt last.

The campaign namespace is:

```text
market-store/
  .publication-campaigns/<source-campaign-id>--<plan-hash-prefix>/
    plan.json
    plan.receipt.json
    manifest.json
    completion-receipt.json
```

The aggregate verifier requires the original completed acquisition campaign, re-verifies its
receipts and children, derives every canonical dataset identity from the child Landing manifest,
verifies every canonical dataset/file/audit/receipt, recomputes publication build-configuration
hashes, and checks the exact aggregate allowlist and totals.

This boundary uses no network endpoint or credential and creates no Bybit order, bot, or transfer.
It publishes retained public-source rows only. Coverage/lifecycle acceptance remains a separate
ADR-0026/ADR-0034 audit, catalog registration remains separate, and Gate 2 remains closed.

## Consequences

- An interrupted 72-child canonical run resumes from immutable canonical completion receipts
  without rewriting committed data.
- Aggregate preflight remains bounded to one Arrow child at a time and one sequential writer.
- Publisher code identity and every source/canonical relationship are frozen before mutation.
- A completed aggregate receipt proves publication and lineage, not gap-free history or complete
  historical universe coverage.
- Runtime plans and canonical market data remain ignored local artifacts; only a later sanitized,
  hash-bound evidence projection may be committed to GitHub.

## Rejected alternatives

- Run `publish-history-1m` and `publish-funding-history` in a shell loop: it has no immutable
  aggregate plan, resume proof, or receipt-last campaign completion.
- Retain all Arrow batches during aggregate preflight: memory would grow with campaign size and
  contradict bounded-memory operation.
- Sum each child's complete `active+building` and operating reserve: those reserves represent the
  same sequential capacity envelope and summing them would invent concurrent writers.
- Publish children concurrently: it multiplies memory and temporary-space demand and makes failure
  recovery more complex without a measured need.
- Treat publication as coverage acceptance: source-returned rows can still contain unexplained
  candle gaps, funding chronology blockers, or incomplete lifecycle scope.
