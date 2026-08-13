# ADR-0032: Resumable public funding acquisition and boundary evidence

- Status: accepted
- Date: 2026-08-13
- Implements: Phase 2 public funding Landing-to-canonical path

## Context

ADR-0031 requires every canonical funding event to carry the elapsed minutes since its preceding
authoritative settlement. Bybit V5 `GET /v5/market/funding/history` returns at most 200 events and
does not return a historical interval field. The current `fundingInterval` from instrument info is
not dated and cannot prove an older event's interval.

Funding acquisition must therefore capture the predecessor outside the requested range, avoid
silent endpoint truncation, resume after interruption, preserve exact source evidence, and pass
the same fresh host/capacity admission as candle acquisition. It remains a public-data operation
with no account credentials.

## Decision

Freeze `grid.bybit-funding-history-request/v1`, plan/page/acquisition contracts, and the
`grid.funding-history-to-canonical/v1` adapter.

An operator request names symbols and inclusive, minute-aligned ranges but never supplies an
instrument ID, launch time, interval, or source identity. Resolution uses a receipt-verified
Bybit-linear registry and accepts only USDT-settled `LinearPerpetual` records. One job fits exactly
one UTC month and `instrument_id mod 8` bucket.

For every series, the deterministic plan creates:

1. one predecessor task over `[registry launchTime, requested start - 1 ms]` with `limit=1`; and
2. fixed, non-overlapping requested-range windows of at most 10,080 minutes, each with an explicit
   limit no greater than 200.

The predecessor response must contain exactly one settlement. Every range response is normalized
to canonical non-exponent decimal text plus an exact UTC-minute timestamp, must be unique reverse
chronological data, and must contain fewer rows than its requested limit. A full/saturated range
page is rejected because the client cannot prove that Bybit did not truncate additional events.
The window size can be reduced in a new request identity if saturation is observed; it is never
silently changed during a run.

Defaults remain 24 workers and one global 10-RPS pacer. Hard ceilings are 32 workers, 96 requested
RPS, five explicit application attempts, 100,000 HTTP attempts, 200 rows, and seven days per
range page. The transport itself performs one attempt. Only transport/Bybit failures are retried;
schema, boundary, ordering, range, or saturation failures stop immediately.

No-mutation preflight verifies the registry and accepted capacity evidence, bounds every page at
128 KiB plus 64 MiB job metadata, reserves 8 GiB for the operating system, requires fresh memory
and local SSD/NVMe evidence, and rejects future settlements, cross-partition requests, unsafe
paths, stale locks, partial receipts, and retry-budget overflow.

Execution stores canonical JSON plus a SHA-256 receipt per page under
`.funding-landing/<job-id>--<plan-prefix>/pages`. Resume fetches only missing verified page
identities. The manifest records every page hash, source range, attempt count, predecessor row,
resource facts, and a canonical aggregate `boundary_evidence_sha256`; the completion receipt is
written last. Orphans, symlinks, tampering, changed plans, and stale run locks fail closed.

Canonical loading sorts all returned events per instrument and derives each interval from the
previous settlement, beginning with the separately receipted predecessor. Every requested series
must contain at least one event. The publication adapter re-verifies Landing, registry, capacity,
boundary aggregation, lifecycle bounds, exact Arrow rows, and immutable Git identity before
invoking ADR-0031 receipt-last publication.

## Consequences

- Today's instrument funding interval is never projected backward into historical events.
- Boundary evidence is explicit, resumable, hash-bound, and independently re-verifiable.
- A saturated page, missing predecessor, missing entire requested series, or non-minute settlement
  blocks canonical publication instead of producing a partial dataset.
- Empty individual range windows remain source evidence; a later funding-specific coverage audit
  must decide whether the settlement chronology is complete for Gate 2.
- No API key, account identifier, private endpoint, order, grid bot, or transfer is used.
- Funding compaction, catalog registration/selection, gap repair, sanitized pilot evidence, and
  full-universe coverage remain separate Phase 2 work. Gate 2 remains closed.

## Rejected alternatives

- Use current `fundingInterval`: undated metadata can leak the future.
- Paginate one mutable reverse cursor per instrument: page ownership and resume would depend on
  previously returned state.
- Accept exactly 200 rows: the endpoint supplies no proof that the page was not truncated.
- Retry semantic validation failures: repeated malformed evidence does not become trustworthy.
- Store raw API response objects indefinitely: normalized receipted rows retain the required
  source values with a smaller, versioned attack surface.
- Merge funding into the candle Landing contract: funding has predecessor and saturation rules
  that candles do not.
