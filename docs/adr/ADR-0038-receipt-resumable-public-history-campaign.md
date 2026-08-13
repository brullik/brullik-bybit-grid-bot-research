# ADR-0038: Receipt-Resumable Public History Campaign

- Status: accepted
- Date: 2026-08-13
- Implements: Phase 2 representative multi-year acquisition orchestration

## Context

ADR-0023 and ADR-0032 make one trade/mark or funding acquisition job deterministic, bounded,
receipt-resumable, and immutable after completion. One job intentionally owns one dataset type,
UTC month, and `instrument_id mod 8` bucket. That boundary is safe, but a representative
multi-year run otherwise requires an operator to construct and invoke dozens of requests by hand.
Manual enumeration can omit a month, multiply the effective request rate by launching jobs in
parallel, understate aggregate staging space, or lose the exact campaign membership needed to
prove a deterministic resume.

The current instrument registry contains present-day lifecycle evidence. It can bound source
acquisition, but it is not historical point-in-time metadata and must not be exposed to a
historical strategy decision. ADR-0037 keeps that distinction explicit.

## Decision

Add four runtime contracts:

- `grid.public-history-campaign-request/v1` for bounded operator intent;
- `grid.public-history-campaign-plan/v1` for the deterministic child-job inventory; and
- `grid.public-history-campaign-manifest/v1` for the aggregate result; and
- `grid.history-campaign-receipt/v1` for receipt-last plan and completion commits.

A campaign:

- contains 1 through 700 unique USDT linear perpetual symbols, one or more of trade, mark, and
  funding, an inclusive minute-aligned range, and at most 120 UTC calendar months;
- explicitly selects `registry-lifecycle-intersection-v1`; this clips source acquisition to the
  verified registry launch/delivery interval and is labelled ex-post acquisition evidence, never
  point-in-time research truth;
- deterministically groups child requests by month, dataset type, and the accepted eight-bucket
  identity, deriving every `instrument_id` from the verified registry;
- derives the exact per-child HTTP-attempt ceiling from page count times the requested application
  attempt bound, retaining the existing 100,000-attempt hard ceiling;
- preflights every child without mutation, then admits the campaign only if current free space can
  hold active-plus-building data, the operating reserve, and the conservative remaining Landing
  bound for all incomplete children;
- executes child jobs sequentially so independent per-job pacers cannot multiply the effective
  target rate; and
- writes the campaign plan before child mutation, reuses each verified child receipt on rerun, and
  writes the aggregate manifest receipt last only after every child verifies.

The campaign root contains only `plan.json`, `plan.receipt.json`, `manifest.json`, and
`completion-receipt.json`. Child Landing directories retain their existing exact allowlists.
Verification rechecks the campaign receipts, deterministic child paths, child plan and manifest
hashes, request hashes, page/row/HTTP totals, and every completed child allowlist.

The measured error-free 15-RPS controlled-scale setting may be requested explicitly for the
representative run, but this ADR does not raise the 10-RPS default or claim a venue rate limit.
Adaptive response-header throttling and longer-duration variability evidence remain separate
Phase 2 work.

No authenticated endpoint, API credential, account identifier, tick row, order, bot, or transfer
is permitted. A completed campaign proves retained public source responses and deterministic
resume only; canonical publication, lifecycle completeness, accepted gaps, catalog registration,
or Gate 2 require their existing separate evidence.

## Consequences

- The first multi-year iteration becomes one reproducible command rather than a manually managed
  request list.
- Re-running the same campaign fetches only child pages without valid receipts; a fully completed
  campaign performs no network calls.
- A new registry snapshot, range, symbol set, or rate setting produces a different campaign and
  cannot silently mutate an earlier result.
- Aggregate admission is conservative because it retains per-job metadata bounds. Actual Landing
  bytes are expected to be lower and remain measured evidence, not an excuse to weaken preflight.
- A partial registry can acquire explicitly named known instruments, but the campaign manifest
  cannot prove a complete historical universe.

## Rejected alternatives

- Run one shell loop over handwritten request files: it has no immutable aggregate membership,
  aggregate resource admission, or receipt-last completion marker.
- Execute monthly children concurrently: each child has its own pacer, so concurrency would
  multiply the configured request rate and invalidate the measured operating envelope.
- Put multiple months or buckets into one child job: that weakens the accepted immutable
  partition ownership and repair boundary.
- Treat current launch/delivery/status metadata as historical strategy input: that introduces
  future knowledge and violates the point-in-time contract.
- Automatically remove stale child locks after interruption: process ownership cannot be proven
  safely; stale-lock recovery remains an explicit audited repair action.
