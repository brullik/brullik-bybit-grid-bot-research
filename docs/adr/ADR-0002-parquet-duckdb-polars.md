# ADR-0002: Parquet, DuckDB, and Polars Baseline

- Status: accepted pending benchmark validation
- Date: 2026-07-28

## Context

The capacity objective is approximately 3.68 billion trade-price candles and 7.36 billion candle rows when mark-price data is retained. CSV/pandas-centric designs and repeated eager full scans are unsuitable.

## Decision

Use:

- Parquet as the canonical analytical file format;
- ZSTD as the initial compression candidate;
- DuckDB for SQL/catalog/audit and set-oriented queries;
- Polars lazy/streaming execution for high-throughput transformations;
- Arrow-compatible columnar interfaces between components.

The benchmark spike may change physical encoding, compression level, row group, file target, or engine allocation. It may not replace columnar/streaming principles without a superseding ADR.

## Consequences

Positive:

- column/projection and predicate pushdown;
- compression and portable immutable files;
- parallel/vectorized processing;
- execution larger than memory through lazy/streaming paths;
- low-operational-overhead local development.

Costs:

- schema/semantic versioning must be disciplined;
- small-file and partition design matters;
- exact execution arithmetic still needs a stricter representation than arbitrary floats.

## Rejected alternatives

- CSV as canonical store: poor typing, compression, pruning, and scan efficiency.
- PostgreSQL for all historical candles: operational/write/index overhead is unnecessary for immutable analytical scans.
- pandas-only processing: eager memory model and Python-centric limitations at target scale.
- Native custom database first: excessive implementation risk before benchmark evidence.
