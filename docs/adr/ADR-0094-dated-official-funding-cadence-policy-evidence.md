# ADR-0094: Dated official funding-cadence policy evidence

- Status: accepted
- Date: 2026-08-15
- Extends: ADR-0034 and ADR-0037
- Preserves: immutable coverage audits, unchanged Gate 2 criteria/blockers, and owner authority

## Context

ADR-0034 correctly blocks any observed funding-interval change until separately dated evidence or
a governed reason policy exists. Four receipt-verified April/July coverage audits currently report
eleven such changes across five retained series. The current instrument `fundingInterval` cannot
explain them because it is undated and ADR-0031 forbids projecting it backward.

Bybit's official 2026-02-23 maintenance announcement, effective 2026-02-26 03:00 UTC, documents a
different source of dated evidence. It states that a perpetual contract automatically adjusted to
one-hour settlement returns to its default interval after the absolute funding rate remains at or
below 0.025% for sixteen consecutive settlements, with restoration at the seventeenth period. It
also states that funding caps and settlement frequency may be changed dynamically without further
notice and lists two-, four-, and eight-hour default schedules.

A missing settlement can resemble a cadence change. The official statement therefore cannot be
used as a blanket permission to accept arbitrary deltas or to rewrite the immutable blocked
audits. A receipt-bound, exact-decimal replay is required before the finding can enter owner
review.

## Decision

Add `grid.phase2-funding-cadence-policy-evidence/v1` and
`grid-data funding-cadence-policy-evidence`.

The command preflights its output before making exactly one credential-free HTTPS GET to the exact
official announcement URL. It rejects redirects, non-HTML/non-200 responses, responses over 2 MiB,
multiple attempts, and any page that lacks every exact title, date, effective-time, threshold,
restoration, dynamic-adjustment, and schedule marker. The public artifact binds the response and
normalized marker hashes but retains no announcement body.

Every supplied coverage audit must have a valid receipt and canonical content hash, use the
unchanged ADR-0034 v1 contract, be blocked only by `unexplained_interval_change`, and have zero
duplicate, conflict, empty-window, lifecycle, predecessor/internal mismatch, unexpected-time, and
unrequested-row contradictions. Each paired funding Landing job is fully reverified through its
plan, pages, page receipts, manifest, completion receipt, and exact file allowlist. The audit must
bind that exact funding manifest; duplicate sources and source substitution fail closed.

For each affected retained series, the verifier uses exact `Decimal` rates and settlement-derived
intervals and accepts only this state machine after the official effective time:

1. one stable documented default cadence may enter a one-hour episode;
2. a completed one-hour episode must end with sixteen or seventeen consecutive settlements at or
   below the exact decimal threshold `0.00025`;
3. the first non-hourly delta may only align forward in whole hours to one stable documented
   two-, four-, or eight-hour schedule; and
4. an episode still open at the retained boundary may not exceed the restoration boundary.

Any non-hourly change without that one-hour context, unstable post-episode schedule, missing
threshold proof, pre-policy observation, or unmatched aggregate remains unexplained. The evidence
publishes only hashes and aggregate counts: no rates, instruments, symbols, observed settlement
timestamps, runtime paths, credentials, or account data.

`verified-official-funding-cadence-policy-consistency` means all changes in the supplied audits are
consistent with the dated official mechanism. It does not modify or reclassify the original
audits, remove `funding-cadence-policy-unresolved`, open Gate 2, or authorize Phase 3. Those remain
a separate owner/governance decision.

## Consequences

- The eleven current cadence changes can be reviewed from one receipt-bound GitHub-safe artifact
  without another market-data request or canonical mutation.
- Exact rates are used privately at verification time but cannot escape into the public artifact.
- A simple missing settlement is not accepted as a dynamic schedule change because it cannot pass
  the bounded state machine and threshold/alignment proof.
- Evidence before the 2026-02-26 effective time remains unresolved by this contract.
- A later policy revision, URL, threshold, schedule set, or interpretation requires a new contract
  version and ADR; the v1 observation remains immutable.

## Rejected alternatives

- Remove the blocker from the existing audit: immutable evidence cannot be rewritten, and the
  owner has not approved a Gate 2 governance change.
- Accept every post-policy interval delta: a missing settlement would become indistinguishable
  from a legitimate dynamic adjustment.
- Use current `instruments-info` cadence: it remains undated and can leak future metadata.
- Commit raw funding rates/timestamps or the announcement body: hashes and bounded aggregates are
  sufficient for review and avoid unnecessary market-data publication.
- Search for one announcement per symbol: the official policy explicitly permits dynamic changes
  without further notice, so absence of per-symbol articles is not contrary evidence.
