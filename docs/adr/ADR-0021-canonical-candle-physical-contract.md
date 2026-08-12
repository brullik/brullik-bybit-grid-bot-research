# ADR-0021: Canonical Candle Physical Contract Boundary

- Status: accepted
- Date: 2026-08-12
- Implements: ADR-0020 Phase 2 physical-layout decision

## Context

ADR-0020 selects exact hybrid candle values, eight stable buckets, a 16 MiB target, and ZSTD
level 3. Before a downloader can mutate the market store, those choices need one portable,
machine-verifiable contract. The Gate 1 benchmark assigned its stable integer instrument IDs by
`instrument_id mod bucket_count`; replacing that mapping with a process-randomized language hash
or a newly invented distribution would disconnect Phase 2 from the measured layout.

The dependency-free logical contracts intentionally model exact `Decimal` values. PyArrow and
Parquet belong outside that package so `grid-live` does not inherit the historical-store stack.

## Decision

Add an independently installable `grid-market-store` package. It may depend on
`grid-contracts` and PyArrow, but it has no network, research, private-Bybit, release, or live
dependency. `grid-data` may consume it; `grid-live` may not.

Freeze `grid.canonical-candle-layout/v1` as follows:

- bucket algorithm `instrument-id-modulo-v1`: unsigned 32-bit stable internal
  `instrument_id mod 8`;
- immutable UTC calendar-month and two-digit bucket paths;
- row order `instrument_id, open_time_ms`;
- price OHLC signed Int64 units of `1e-8` with required logical-type/scale/unit metadata;
- volume Decimal128(38, 4) and turnover Decimal128(38, 12);
- a 16,777,216-byte target and ZSTD level 3 recorded in schema metadata; and
- logical category, source ID, ingestion ID, and 32-bit quality flags retained in each row.

The exact numeric metadata remains `grid.candle-exact-physical/v1`, preserving the Gate 1
benchmark contract. Conversion rejects non-finite values, excessive scale, Decimal128 overflow,
Int64 overflow, duplicate canonical keys, mismatched logical row classes, and batches spanning
more than one month/bucket. It never rounds to make a value fit.

This ADR establishes the pre-mutation physical boundary only. Dataset publication still requires
the Phase 2 manifest, audit, staging, receipt, resume, repair, compaction, and catalog work. Gate 2
criteria are unchanged and remain closed.

## Consequences

- The downloader and compactor share one tested Arrow schema instead of reconstructing metadata.
- Built-in Python `hash()` and exchange symbol text are forbidden as partition identities.
- A stable internal ID must exist before candle publication and must fit unsigned 32-bit v1.
- Small fixture/tail files need not reach 16 MiB, but their manifest must expose target/tail
  semantics; production writers may not claim target attainment from metadata alone.
- Real source/ingestion strings and wider quality flags may alter bytes/row from the Gate 1
  synthetic projection, so Phase 2 must measure its controlled pilots and refresh free-space
  preflight rather than reusing that projection blindly.
- `grid-live` remains installable without PyArrow or `grid-market-store`.

## Compatibility and migration

There is no committed canonical dataset to migrate. Readers verify the complete Arrow schema and
metadata and fail closed on another layout ID. A future change to bucket mapping, physical types,
scale, sort order, file target, or compression requires a new layout/schema version, a
superseding ADR, and a new immutable dataset identity.

## Rejected alternatives

- Python `hash(instrument_id)`: its contract is not an external cross-language storage identity.
- SHA-based rebucketing: deterministic, but it would change the mapping used by the qualified
  benchmark without a demonstrated benefit.
- Put PyArrow in `grid-contracts`: it would make a historical analytical dependency transitively
  available to slim consumers, including live.
- Round values to the selected scale: silent numeric mutation violates ADR-0020.
