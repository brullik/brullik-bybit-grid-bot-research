# ADR-0056: Bounded funding repair discovery execution

- Status: accepted
- Date: 2026-08-14
- Implements: Phase 2 funding repair discovery execution boundary

## Context

ADR-0055 produces private candidate settlement timestamps and ordinary public funding requests,
but deliberately makes no network call and accepts no inference. A separate transition is needed
to execute the entire plan under one resource bound, preserve standard Landing receipts, and
distinguish exact source confirmation from an empty, partial, or unexpected response.

Calling tasks independently would allow a partially preflighted plan to mutate storage before
the remaining work is admitted. Treating an empty response as confirmation would also erase the
ambiguity between a missing source row and a legitimate historical cadence change.

## Decision

Add `grid-data execute-funding-repair` and freeze
`grid.bybit-funding-repair-execution/v1`. The default command performs no mutation. It re-verifies
the ADR-0055 plan and every upstream receipt/hash, resolves every embedded
`grid.bybit-funding-history-request/v1` with its separately bound source-observed predecessor,
and preflights every resulting job plus the complete remaining Landing staging requirement before
the first request.

Execution requires an explicit `--execute`. Tasks run sequentially through the existing public
funding acquisition primitive, including exact response normalization, unsaturated-page policy,
decrease-only shared pacing inside each job, bounded retries, fresh host evidence, page receipts,
manifest, completion receipt, resume, and file allowlist. There is no credential or private Bybit
dependency.

A task passes only when its observed settlement timestamps equal the complete ordered candidate
list exactly once. Missing candidates, unexpected events, duplicates, saturation, predecessor
failure, or any other source validation failure remain blocked or abort fail closed. The aggregate
passes only when every task passes. A source-confirmed candidate is evidence for a later immutable
repair child; it is not acceptance of an interval schedule and does not alter the original blocked
audit.

The receipt-last execution record binds the plan/audit/anomaly hashes, original Landing and
canonical manifests, registry, capacity evidence, every repair Landing plan/manifest, executor
Git identity, request counts, and exact private task identities. Funding rates are omitted, but
instrument symbols and settlement bounds remain operationally sensitive. The record is therefore
private runtime evidence with `github_commit_eligible=false`; only a later sanitized aggregate
projection may be committed.

This transition does not publish canonical data, mutate or supersede the parent, accept a cadence
change, register a catalog entry, close Gate 2, or authorize private/live operations.

## Consequences

- One aggregate resource gate precedes all public requests in the plan.
- Standard funding Landing receipts provide deterministic resume and independent verification.
- Empty or partial source confirmation is retained as blocked evidence rather than retried into an
  invented settlement.
- A later publication boundary can consume only a fully verified `passed` execution and must
  create a new immutable child with complete lineage.

## Rejected alternatives

- Execute each embedded request ad hoc: whole-plan admission and deterministic evidence are lost.
- Accept a subset of candidates: the inferred gap is not fully source-confirmed.
- Store results only in the execution JSON: standard page-level receipt/resume semantics are lost.
- Commit exact execution artifacts: symbols and settlement identities are unnecessary public
  disclosure.
- Publish directly after a successful request: immutable repair lineage needs a separate review.
