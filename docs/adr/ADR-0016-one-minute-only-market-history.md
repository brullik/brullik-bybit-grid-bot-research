# ADR-0016: One-Minute-Only Market History

- Status: accepted
- Date: 2026-08-12
- Authority: owner decision D-019

## Context

V1 research and live feature contracts operate on closed one-minute candles. The official Bybit
Historical Market Data catalog advertises a contract public-trade product, but the corresponding
daily archives contain individual trades rather than one-minute candles. Using those archives
would require downloading and retaining a much larger source corpus and then aggregating it into
the only granularity V1 consumes.

The owner has explicitly decided that tick data is unnecessary and that one-minute data is
sufficient. The source contract must reflect that decision without weakening the formal
700-instrument, ten-year, one-minute capacity objective or any risk and acceptance gate.

## Decision

V1 ingests and retains only these historical market datasets:

- trade-price OHLCV at one-minute granularity;
- mark-price OHLC at one-minute granularity;
- funding events;
- dated instrument, fee, and risk metadata required for honest historical decisions.

Tick-level public-trade archive bodies are outside the V1 ingestion and retention boundary. They
must not be downloaded to landing storage, retained as Bronze evidence, or used as an implicit
intermediate for one-minute candle construction.

Until Bybit advertises and the project verifies a compatible one-minute bulk product, the
bootstrap and incremental source plan is:

- `/v5/market/kline` with `interval=1` for trade-price candles;
- `/v5/market/mark-price-kline` with `interval=1` for mark-price candles;
- `/v5/market/funding/history` for funding events.

A future official one-minute bulk source may be admitted only after its schema, semantics,
coverage, provenance, and conflict policy are verified. A tick archive is not a compatible
one-minute bulk source.

The Phase 2 downloader must stream bounded REST pages through preflighted staging, resume from
verified receipts, respect rate limits, and commit canonical partitions atomically. Request
receipts and provenance are retained; retaining every raw response page remains optional.

This decision resolves P-006 source-policy selection. It does not prove actual historical REST
coverage, select P-001 through P-005, close Gate 1, or authorize Phase 2 execution.

## Consequences

- Source storage no longer needs capacity for compressed tick-trade archives.
- Initial bootstrap becomes REST-request intensive, so bounded concurrency, resume, retry, and
  deterministic gap evidence are first-class requirements.
- Canonical and derived storage estimates remain relevant; REST staging, compaction, experiments,
  and backups still require independent preflight capacity.
- Tick-level microstructure, trade ordering within a minute, and tick-derived intrabar execution
  models remain unavailable in V1, consistent with the existing scope.
- Existing v1 source-assessment evidence remains immutable. The owner-approved policy is recorded
  in the append-only `grid.bybit-history-source-assessment/v2` contract.

## Rejected alternatives

- Download tick archives and aggregate locally: this spends storage and transfer capacity on data
  outside the accepted V1 granularity.
- Retain tick archives only temporarily: even temporary bootstrap staging violates the explicit
  no-tick download boundary and still requires large free-space headroom.
- Treat the advertised contract trade product as one-minute bulk data: its source semantics do not
  match the canonical candle contract.
- Remove the formal ten-year capacity objective: source granularity does not change the accepted
  architecture scale target.
