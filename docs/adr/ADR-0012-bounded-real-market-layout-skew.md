# ADR-0012: Bounded Real-Market Layout-Skew Evidence

- Status: proposed; Gate 1 benchmark-gated
- Date: 2026-08-12

## Context

The ADR-0010 decision matrix and ADR-0011 staged reference protocol use deterministic synthetic
rows. They prove exact physical contracts and harness behavior, but synthetic price/volume patterns
may compress differently from real Bybit candles. Gate 1 therefore still lacks measured
real-market skew for the shortlisted physical layouts.

Committing raw market rows or generated Parquet data to the public repository is prohibited. A
full history downloader is a Phase 2 deliverable and is not authorized while Gate 1 is closed.

## Decision

Add a bounded, public-only M1 collector for closed Bybit linear-USDT trade-price 1m candles:

- verify the receipt-pinned current instrument inventory before network access;
- obtain one current unauthenticated ticker snapshot;
- form a deterministic liquid pool ranked by 24-hour turnover;
- select 3-12 symbols at evenly spaced exact-price ranks within that pool;
- require every selected instrument to have launched before the requested window;
- bound the inclusive window to at most seven days and reject any missing, duplicate, unaligned,
  out-of-range, malformed, or invalid-OHLC candle;
- write the exact ADR-0010 two-layout shortlist under an ignored operator work directory;
- reopen and verify every exact Parquet schema and compare DuckDB/Polars exact aggregates;
- publish only bounded selection, distribution, compression, imbalance, provenance, and content
  hash evidence plus its completion receipt.

Raw normalized rows and Parquet files remain outside Git. A verified ownership marker permits safe
replacement of only the explicitly named work directory. The public evidence records tree hashes
and reproducible request bounds but cannot reconstruct raw rows by itself.

The selection ticker snapshot occurs after the historical sample and is used only to choose a
liquid, price-stratified compression sample. It is not decision-time universe evidence and cannot
be used by a historical strategy decision.

## Consequences

- Both ADR-0010 shortlisted layouts are measured on identical real values.
- Price, volume, turnover, symbol, bucket, and file-size skew become explicit rather than inferred
  from synthetic projections.
- The collector remains small and bounded and does not implement Phase 2 ingestion, catalog,
  repair, or canonical dataset publication.
- Current-liquidity selection can introduce survivorship bias; the artifact states this and cannot
  support strategy profitability or historical-universe claims.
- Trade-price evidence does not select a separate mark-price physical schema.
- Gate 1 still requires the reference-hardware run, feature rerun, PM decisions, and any broader
  historical-regime evidence requested by the performance review.

## Rejected alternatives

- Commit the raw sample for review: violates the repository data policy.
- Treat the existing one-symbol summary hash as layout skew: it contains no physical-size evidence.
- Download a multi-year/full-universe corpus during Gate 1: that is Phase 2 scope and unnecessary
  for bounded value-distribution calibration.
- Select only the largest contracts by turnover: this under-samples low-price/high-quantity value
  representations.
- Use binary floating-point during exact conversion: it can change scaled integers and decimals.
