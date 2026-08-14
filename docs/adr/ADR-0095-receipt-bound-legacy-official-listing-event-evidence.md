# ADR-0095: Receipt-bound legacy official listing-event evidence

- Status: accepted
- Date: 2026-08-15
- Extends: ADR-0037, ADR-0070, and ADR-0071
- Preserves: immutable canonical data, historical metadata uncertainty, unchanged Gate 2 blockers,
  and owner authority

## Context

The official Bybit announcements API assessed under ADR-0071 does not reach the 2020 launches in
the completed five-instrument oldest-history campaign. Its bounded depth result is useful negative
evidence, but it cannot associate an older launch event with any selected instrument. The current
instrument registry is also unsuitable as historical truth: it is a receipt-verified ex-post
snapshot and its `launchTime` values must not be projected backward into research decisions.

Bybit's public `Bybit_Announcements` Telegram channel retains three exact 2020 posts that together
name the five selected USDT perpetual products:

- `https://t.me/Bybit_Announcements/72`, published 2020-03-25 16:03:10 UTC;
- `https://t.me/Bybit_Announcements/312`, published 2020-10-21 10:44:58 UTC; and
- `https://t.me/Bybit_Announcements/347`, published 2020-12-16 06:55:34 UTC.

The channel is an official Bybit publication surface, although the pages are served by Telegram.
An announcement publication timestamp is not necessarily the exact product activation timestamp.
The completed canonical campaign independently shows that four first trade-candle UTC dates equal
their related post dates, while one series begins two UTC dates earlier. Mark-price observations
can also precede trading while a product is being prepared. Neither first candle kind is listing
metadata by itself.

## Decision

Add `grid.phase2-legacy-listing-event-evidence/v1` and
`grid-data legacy-listing-event-evidence`.

The command preflights its output, accepts exactly five unique receipt-registry identities, and
fully verifies the completed source campaign, aggregate publication receipts, and every canonical
dataset through the existing production verifier. It requires the campaign's registry artifact
binding to equal the supplied receipt-verified registry and accepts only single-series trade and
mark children whose symbol set equals the selected set. It reads only verified manifest bounds;
it does not read Parquet values after the production verifier or mutate the store.

The source contract fixes the three permalinks and their archive-window fetch URLs (`before=73`,
`before=313`, and `before=348`), Telegram `data-post` identities, exact UTC publication
timestamps, required visible-text markers, and expected selected-match cardinalities of one,
three, and one. Direct permalinks expose only an OpenGraph preview; the bounded archive windows
provide the target post's signed page structure and `<time datetime>`. Each window receives
exactly one credential-free HTTPS attempt. Redirects,
non-200/non-HTML responses, bodies over 1 MiB, invalid UTF-8/HTML, duplicate or missing target
posts, timestamp drift, marker drift, ambiguous symbol association, or incomplete selected-set
coverage fail closed.

Association accepts either the complete normalized pair or the registry base coin at strict
alphanumeric token boundaries. The fallback is required because the four-pair post lists three
selected base tickers before naming USDT as their shared quote; substring-only matching is not
accepted. Expected per-document cardinality and exact-once selected-set coverage remain mandatory.

Instrument-to-post matching and first observed trade/mark timestamps remain private runtime
inputs. The public artifact includes only official URLs/timestamps, response/text hashes,
receipt/lineage hashes, the selected-set hash, and aggregate day/month comparison counts. It
contains no symbol, instrument ID, observed market timestamp, market value, dataset identity,
runtime path, account data, or credential.

`verified-four-exact-and-one-bounded-legacy-listing-event` means all five first trade observations
fall in the official message month, four share its UTC date, and the remaining observation leads
the related message by exactly two UTC dates. This is a bounded source reconciliation, not proof
of exact activation time. Any other result remains
`blocked-legacy-listing-event-date-mismatch`.

The new evidence does not rewrite the current registry, turn first candles into listing metadata,
accept an absence reason, reclassify an immutable audit, remove
`historical-point-in-time-metadata-missing` or
`official-announcement-history-insufficient`, open Gate 2, or authorize Phase 3. Narrowing or
removing either blocker remains a separate owner/governance decision.

## Consequences

- Five otherwise out-of-depth legacy products gain exact official-document bindings without a
  full announcement crawl or another market-data acquisition.
- The retained two-day discrepancy remains explicit instead of being hidden by a convenient
  listing-date inference.
- The current registry's ex-post lifecycle role remains unchanged and cannot leak into historical
  strategy features.
- Future page removal or content drift blocks a new observation; the existing receipt-bound
  response/text hashes remain immutable evidence of the measured run.
- A different post, source surface, selection cardinality, association policy, or interpretation
  requires a new contract version and ADR.

## Rejected alternatives

- Treat the first trade candle as the listing timestamp: source availability and product metadata
  are different facts, and the observed two-day lead disproves that shortcut.
- Treat the first mark candle as the listing timestamp: preparation data may precede trading.
- Backfill historical `launchTime` from the current registry: ADR-0037 forbids projecting current
  metadata backward.
- Crawl or scrape the whole Telegram channel: three fixed 20-post archive windows are sufficient
  for the exact known targets and avoid an unbounded discovery workflow.
- Commit page bodies or selected symbols: response/text hashes and aggregates are sufficient for
  review while preserving the repository's public-evidence boundary.
- Remove Gate 2 blockers in the implementation PR: blocker interpretation and gate acceptance are
  owner-governed decisions, not an evidence-builder side effect.
