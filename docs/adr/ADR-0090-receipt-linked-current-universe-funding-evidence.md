# ADR-0090: Receipt-linked current-universe funding evidence

- Status: accepted
- Date: 2026-08-14
- Extends: ADR-0034, ADR-0041, ADR-0048, ADR-0049, ADR-0052, ADR-0085, and ADR-0089
- Preserves: immutable source evidence, unchanged Gate 2 criteria, and Phase 3 prohibition

## Context

The current-universe candle scope is an exact union of five retained campaign clips. Funding for
the same instruments and minute-inclusive ranges is assembled from four boundary-backed
funding-only campaigns plus a bounded July funding slice already present in a retained mixed-kind
campaign. Treating those artifacts as unrelated files would not prove that the funding scope
matches the candle scope, and repeating the retained July acquisition would create overlapping
immutable evidence without improving coverage.

ADR-0048 and ADR-0052 require a discovered predecessor-backed source boundary before a new
full-history funding campaign. The retained July campaign predates that workflow but already has
receipt-verified Landing, canonical publication, and aggregate coverage evidence. A final public
projection therefore needs to distinguish newly boundary-backed sources from a narrowly reused
bounded source while failing closed on every gap, overlap, substitution, or count mismatch.

## Decision

Add the private `grid.current-universe-funding-evidence-request/v1` source manifest, the public
`grid.phase2-current-universe-funding-evidence/v1` contract, and the offline
`python -m benchmarks.current_universe_funding_evidence` builder. Every path in the private
manifest is safe-relative to an explicit artifact root. The builder performs no network request
and reads no Landing page, Parquet object, DuckDB catalog, or market value.

The builder first verifies the ADR-0085 bundle request/evidence and ADR-0089 candle evidence. It
then receipt- and schema-verifies the ordered candle request/evidence chain and privately rebuilds
the exact per-symbol, minute-inclusive candle interval union from the bundle clips. Funding source
requests are verified with their Landing/publication/coverage triplets and are normalized by
symbol. Overlap is rejected before adjacent intervals are merged; the normalized funding union
must equal the candle union exactly.

Two funding source modes are admitted:

- `boundary-backed` is funding-only and must bind an ADR-0048 boundary request/evidence pair with
  the same symbols and range, complete predecessor and canonical-start counts, and exactly one
  predecessor event per symbol beyond the campaign's Landing funding rows;
- `reused-bounded` may reuse a receipt-verified mixed-kind campaign but may not carry substitute
  boundary inputs. Its exact request interval must fill only a disjoint portion of the target
  union, and every non-funding coverage component must be passed so aggregate reasons remain
  attributable to funding.

Every source must share the candle chain's registry and capacity evidence. Landing, canonical,
and coverage funding rows/datasets must reconcile; accepted or unknown reason codes fail closed.
The public projection contains only content/artifact hashes, aggregate counts, quality totals,
source-boundary totals, and receipt-bound timing. Timing from a reused mixed-kind campaign is
explicitly not funding-only. Symbols, IDs, time bounds, paths, rates, settlement timestamps,
market values, accounts, and credentials remain private.

The evidence-integrity status may be verified while unchanged coverage remains blocked. The
output always leaves the performance envelope unqualified, performs no Gate 2 decision, and
cannot authorize Phase 3, research promotion, or live execution.

## Consequences

- One receipt-bound artifact proves that retained current-universe funding evidence covers
  exactly the candle decision scope without redownloading the retained July source.
- Boundary admission remains explicit for every new full-history funding campaign; legacy reuse
  is narrow, non-overlapping, and fully hash-bound.
- Funding cadence anomalies and empty source windows remain visible owner-policy inputs rather
  than being converted into accepted history.
- The private manifest can be regenerated from immutable receipts, while only its canonical hash
  and sanitized aggregate reach GitHub.

## Rejected alternatives

- Download July funding again: it repeats expensive immutable source work and introduces an
  overlapping evidence chain.
- Compare only symbol counts: equal counts do not prove equal identities or time coverage.
- Publish symbol/range membership to GitHub: exact equality can be proven privately and committed
  through hashes and aggregate counts.
- Infer funding history from candle availability or current `fundingInterval`: neither proves
  historical settlement chronology.
- Accept Gate 2 from an exact funding union: lifecycle, cadence, repair, and performance policies
  remain separate owner decisions.
