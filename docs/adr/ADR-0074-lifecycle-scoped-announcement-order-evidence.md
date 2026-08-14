# ADR-0074: Lifecycle-scoped announcement order evidence

- Status: accepted
- Date: 2026-08-14
- Amends: ADR-0071/ADR-0072 announcement-order scope

## Context

After ADR-0073 admitted missing legacy `publishTime`, the next post-merge run failed closed on a
current first page whose `dateTimestamp` values were not strictly descending. A bounded
metadata-only check of all eight first and declared-last pages found one adjacent inversion in
`latest_activities`; both lifecycle-relevant `new_crypto` and `delistings` pages were internally
descending and their first-page minimum was not older than their last-page maximum.

The official endpoint therefore preserves source page order but does not provide one universal
strict ordering invariant across all announcement types. Reordering the page locally would hide
that fact. Requiring lifecycle-quality ordering from activity/news partitions would make the
depth diagnostic fail for evidence it does not use.

## Decision

The public client validates the announcement envelope, requested type, required integer
`dateTimestamp`, and optional integer `publishTime`, but preserves item order without asserting
global monotonicity.

The evidence builder designates only `new_crypto` and `delistings` as lifecycle-depth types. For
those two types, the first and declared-last pages must each have zero adjacent
`dateTimestamp` inversions and, when distinct, the first-page minimum must be at least the
last-page maximum. Any failure remains fatal. For every type, the artifact records first/last
adjacent inversion counts, whether the declared-page bounds are consistent, and whether the type
participates in lifecycle depth.

Rename aggregate coordinates to say exactly what was observed:
`new_crypto_declared_last_page_min_date_timestamp_ms`,
`delistings_declared_last_page_min_date_timestamp_ms`, and
`documented_types_declared_last_page_min_date_timestamp_ms`. These are bounded endpoint
observations, not a claim that every middle page was scanned or every instrument was matched.

The failed attempt published no artifact or receipt. Request count, one-attempt transport,
response hashing, redaction, and closed Gate 2 remain unchanged.

## Consequences

- Non-lifecycle source inversions are visible evidence instead of hidden or fatal noise.
- Listing/delisting depth remains fail-closed at the only partitions used for lifecycle review.
- Field names no longer overstate a declared-last-page observation as proven global archive age.
- Per-instrument lifecycle matching and Gate 2 acceptance remain separate.

## Rejected alternatives

- Sort every page locally: destroys source-order evidence.
- Ignore all ordering: would allow a lifecycle last-page bound with no ordering support.
- Require all eight types to be monotonic: contradicts observed valid activity-page behavior and
  does not improve listing/delisting evidence.
