# ADR-0071: Bounded official announcement archive-depth evidence

- Status: accepted
- Date: 2026-08-14
- Implements: non-promoting lifecycle-source discovery for Gate 2
- Ordering semantics amended by: [ADR-0072](ADR-0072-announcement-date-ordering-and-depth-bound.md)

## Context

Gate 2 requires expected candle coverage to be explained by listing/delisting metadata. The
current instrument registry exposes exchange-reported `launchTime` and `deliveryTime`, but
ADR-0037 correctly limits that current snapshot to ex-post data-quality use. ADR-0070 classifies
the full-history candle-gap topology without claiming that the first observed candle is a listing
date.

Bybit documents the public `/v5/announcements/index` endpoint and eight announcement types. A
manual full download or repeated ad-hoc browser searches would be slow, mutable, and difficult to
audit. Before building record matching, the project first needs to determine whether the official
archive is even deep enough to reach the selected registry lifecycle boundaries.

## Decision

Add `grid-data announcement-archive-depth` and
`grid.phase2-announcement-archive-depth/v1`.

The command receipt-verifies one instrument registry and a bounded selected identity set. It uses
the fixed `en-US` locale, the documented maximum page size of 20, all eight documented
announcement types, and exactly one transport attempt per request. For each type it requests only
page one and the last page derived from the declared total. A single-page type reuses page one.
The maximum is therefore 16 responses instead of a full archive download.

The first and last responses must agree on total count; both pages must have the exact expected
item count; every item must carry the requested type plus non-negative `dateTimestamp` and
`publishTime`; and page order must be reverse chronological. Any source mutation, malformed
field, empty type, or inconsistent bound fails before publication.

The evidence retains per-type totals, page counts, oldest/latest publication times, and canonical
result hashes. Announcement titles, descriptions, tags, and URLs stay in memory only long enough
to hash the validated result and are never persisted. The public projection contains no selected
instrument IDs/symbols, market values, account data, credentials, local paths, or raw response
bodies. A hash of the selected identity set binds the scope without publishing it.

Archive depth is only source-capability evidence. If any selected registry launch precedes the
oldest `new_crypto` publication returned by the API, status is
`blocked-insufficient-official-announcement-history`. Otherwise status is
`source-depth-compatible-needs-record-matching`; this still does not prove a per-instrument
listing or delisting event. Neither status accepts a candle gap, changes Gate 2 criteria,
authorizes Phase 3, or calls private/live endpoints.

The public transport allowlist is widened only for the exact
`/v5/announcements/index` path. Adjacent announcement/private paths remain rejected.

## Consequences

- One bounded command replaces repeated full-archive and browser depth checks.
- Mutable source totals fail closed rather than producing a mixed-snapshot result.
- The project can prove an official archive limitation without storing copyrighted announcement
  text or introducing a large runtime dataset.
- A blocked result establishes why this endpoint cannot reconstruct older lifecycle dates; it
  does not authorize a third-party substitute.
- Per-instrument announcement matching, independently sourced legacy evidence, and the unchanged
  data-quality-owner Gate 2 review remain separate work.

## Rejected alternatives

- Download every announcement: unnecessary for a depth decision and repeats thousands of
  requests.
- Search only `new_crypto`: misses the documented delisting and other lifecycle-adjacent source
  partitions and cannot prove enum-wide archive depth.
- Treat the first candle as a listing date: source availability is not venue lifecycle metadata.
- Automatically accept third-party articles or web archives: provenance policy requires separate
  owner review and an explicit contract.
- Retry each request: this diagnostic prefers an exact bounded response count and fails closed for
  a later rerun.
