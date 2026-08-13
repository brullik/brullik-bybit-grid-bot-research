# ADR-0031: Exact funding layout and receipt-last publication

- Status: accepted
- Date: 2026-08-13
- Implements: Phase 2 canonical funding physical and publication boundary

## Context

Phase 2 requires canonical funding history in addition to trade-price and mark-price one-minute
candles. Bybit V5 `GET /v5/market/funding/history` returns the funding rate and settlement
timestamp, while `GET /v5/market/instruments-info` exposes an instrument's current funding
interval. The current interval is not dated historical metadata and therefore cannot be copied
onto older funding rows without introducing future information.

The logical `FundingEvent` contract already requires the applicable interval. A physical contract
must preserve the rate exactly, make interval semantics explicit, and retain the same immutable,
receipt-last and evidence-based host guarantees used by canonical candles without making
`grid-live` depend on PyArrow or the historical store.

## Decision

Freeze `grid.canonical-funding-layout/v1` and `grid.funding-exact-physical/v1`:

- the canonical key is `(category, instrument_id, funding_time_ms)`;
- `instrument_id` is UInt32 and uses `instrument-id-modulo-v1` with eight buckets;
- paths are `dataset=funding_event/schema=v1/year=YYYY/month=MM/bucket=BB`;
- rows are sorted by `instrument_id, funding_time_ms` and duplicate keys are rejected;
- settlement timestamps are non-negative exact UTC minutes;
- funding rate is exact signed Decimal128(38, 18), with no rounding to fit;
- `funding_interval_minutes` and quality flags are UInt32; and
- the 16,777,216-byte target and ZSTD level 3 are recorded in Arrow metadata.

`funding_interval_minutes` means elapsed whole minutes since the immediately preceding
authoritative funding settlement for the same instrument. Every pair of adjacent events inside a
batch must satisfy that equality. The first event for each instrument in a batch requires
hash-bound upstream evidence containing the preceding settlement. A source request must fetch
that predecessor separately from the requested range. If no predecessor or dated interval
evidence exists, the boundary event is unresolved and canonical publication fails closed. A
current registry `fundingInterval` is never accepted as historical proof.

Freeze `grid.canonical-funding-publication/v1` and `grid.canonical-funding-audit/v1`. Funding
publication:

- performs a no-mutation host, storage, memory, free-space, identity, and stale-building
  preflight;
- binds exact Arrow buffers, source/coverage/capacity evidence, an explicit predecessor-boundary
  evidence hash, build configuration, software identity, and partition path;
- writes one bounded ZSTD-3 Parquet tail/target file under a unique building identity;
- verifies schema, footer, exact keys, internal interval deltas, hashes, and key-derived
  partition before publication;
- atomically renames the building directory and writes `completion-receipt.json` last; and
- independently rejects missing receipts, tampering, orphans, path escapes, conflicting
  idempotent identities, and changed content.

This decision is the physical and immutable publication primitive. It does not yet define the
public funding request/acquisition contract, boundary-predecessor page format, gap acceptance,
repair, compaction, catalog registration, or a production campaign. Gate 2 remains closed.

## Consequences

- Historical funding intervals are derived from actual settlement chronology rather than today's
  instrument metadata.
- A single unresolved first-settlement boundary can block completeness instead of being silently
  guessed.
- Funding values share the measured month/eight-bucket/ZSTD-3 store layout while using a distinct
  schema and audit contract.
- Readers can verify an immutable funding dataset without network access or account credentials.
- `grid-live` remains independent of PyArrow, Parquet, and `grid-market-store`.

## Compatibility and migration

Readers require the complete funding Arrow schema and layout metadata. A different rate scale,
interval meaning, bucket mapping, sort order, compression, or timestamp rule requires a new
schema/layout version and immutable dataset identity. Existing candle contracts are unchanged.

## Rejected alternatives

- Copy the current instrument `fundingInterval` onto historical rows: it is undated and can leak
  future metadata.
- Omit the interval and join to the nearest funding row later: this loses the economic application
  period required by the backtest contract.
- Store funding rate as binary float: it cannot preserve exact source decimal text.
- Infer a missing predecessor from the next event without evidence: interval changes and source
  gaps would be indistinguishable.
- Reuse the candle Arrow schema or audit ID: funding has a different key, value, and boundary
  completeness rule.
