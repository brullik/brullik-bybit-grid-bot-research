# ADR-0096: Official lifecycle announcement record matching

- Status: accepted
- Date: 2026-08-15
- Extends: ADR-0071 through ADR-0074 and ADR-0095
- Preserves: immutable market history, no-lookahead boundaries, Gate 2 criteria, and owner authority

## Context

The bounded archive-depth evidence proves that Bybit's official announcements API exposes
`new_crypto` and `delistings` records only back to 2022. It intentionally reads just the first and
declared last pages and therefore cannot match records to the exact disjoint current-universe
campaign segments. ADR-0095 separately verifies five older instruments against three fixed posts, but it
does not measure the record-match coverage available from the API archive.

The two lifecycle partitions contain only a small number of 20-item pages. Reading each declared
page once is materially cheaper than another candle/funding download and can narrow the remaining
announcement/lifecycle blocker while the active current-universe campaign continues. Raw article
text must not become a Git artifact or historical strategy feature.

## Decision

Add `grid.phase2-announcement-lifecycle-coverage/v1` and
`grid-data announcement-lifecycle-coverage`.

The command binds one through sixteen exact, mutually disjoint
`grid.public-history-campaign-request/v1` trade/mark selections to the same receipt-verified
instrument registry and to the existing ADR-0095 artifact plus its separate private selected
identity set. It rejects overlap rather than double-counting a reused segment. It then reads every
declared 20-item page of `new_crypto` followed by every declared page of `delistings`, using fixed
`en-US` and exactly one transport attempt per response.

For each partition, every response must retain the first-page total, exact expected cardinality,
requested type, official HTTPS host, and unique URL. Exact source order is preserved and adjacent
`dateTimestamp` inversions are counted rather than locally sorted; a full scan does not depend on
pagination order to derive its true minimum/maximum. Any mid-run source-total change, incomplete
page, duplicate URL, or invalid field fails before publication. The complete validated item
sequence is represented by one canonical source hash; article titles, descriptions, tags, and
URLs are discarded after in-memory matching.

An announcement is a candidate only when its title/description/tags contain the exact registry
symbol or an exact base/USDT pair boundary and also contain a derivative/perpetual/contract marker.
No closest-date heuristic is allowed. Zero candidates remains unmatched; more than one remains
ambiguous; exactly one is reconciled only as official record-matching evidence. Registry launch
and delivery dates are compared only in aggregate UTC-date relation counts.

The public artifact contains source hashes, counts, archive bounds, the exact selected-set hash,
legacy-evidence hash, and aggregate match/relation totals. It excludes announcement text and URLs,
instrument identities, observed market timestamps, market values, runtime paths, credentials, and
account data. A complete record match still keeps
`historical-point-in-time-metadata-still-incomplete`: listings/delistings do not reconstruct
historical suspension, status, tick, quantity, fee, funding, or risk metadata.

The command makes no market-data request, performs no canonical/catalog mutation, accepts no
absence reason, removes no Gate 2 blocker, and cannot authorize Phase 3 or live execution.

## Consequences

- Available official lifecycle history is matched once without repeating candle/funding work.
- The 2022 archive boundary and the exact five-instrument legacy evidence remain explicit rather
  than being silently treated as a complete historical universe.
- Multiple plausible official posts are visible ambiguity instead of being selected by an
  arbitrary date window.
- GitHub receives a small receipt-bound aggregate while copyrighted source text remains transient.
- Any Gate 2 reinterpretation remains a separate data-quality-owner/governance decision.

## Rejected alternatives

- Accept first candle time as listing metadata: source availability is not venue lifecycle state.
- Persist the full announcement archive in Git: unnecessary, mutable, and outside the public
  evidence boundary.
- Pick the nearest announcement when several match: hides ambiguity and invents an association
  policy.
- Re-fetch the legacy Telegram posts: ADR-0095 already binds those exact one-attempt responses.
- Mark Gate 2 ready from record matching: the unchanged criterion requires broader historical
  metadata and owner acceptance.
