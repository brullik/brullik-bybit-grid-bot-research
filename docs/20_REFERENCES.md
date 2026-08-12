# Authoritative References

Accessed: 2026-07-28.

The implementation phase must re-check current documentation and record exact API behavior because exchange interfaces, rate limits, and product availability can change.

## Bybit V5

- [Integration Guidance](https://bybit-exchange.github.io/docs/v5/guide)
- [Get Instruments Info](https://bybit-exchange.github.io/docs/v5/market/instrument)
- [Get Kline](https://bybit-exchange.github.io/docs/v5/market/kline)
- [Get Mark Price Kline](https://bybit-exchange.github.io/docs/v5/market/mark-kline)
- [Get Funding Rate History](https://bybit-exchange.github.io/docs/v5/market/history-fund-rate)
- [Public WebSocket Kline](https://bybit-exchange.github.io/docs/v5/websocket/public/kline)
- [Private WebSocket Order](https://bybit-exchange.github.io/docs/v5/websocket/private/order)
- [Private WebSocket Execution](https://bybit-exchange.github.io/docs/v5/websocket/private/execution)
- [Private WebSocket Position](https://bybit-exchange.github.io/docs/v5/websocket/private/position)
- [Rate Limit Rules](https://bybit-exchange.github.io/docs/v5/rate-limit)
- [Demo Trading Service](https://bybit-exchange.github.io/docs/v5/demo)
- [Bybit API Documentation Home / Historical Data reference](https://bybit-exchange.github.io/docs/v5/intro)
- [Bybit Public Historical Data](https://public.bybit.com/)

Native Futures Grid endpoint references must be verified against the current account/region before implementation and must be captured in the feasibility report.

## Data platform

- [Apache Parquet](https://parquet.apache.org/)
- [DuckDB — Reading and Writing Parquet Files](https://duckdb.org/docs/stable/data/parquet/overview)
- [DuckDB — Partitioned Writes](https://duckdb.org/docs/stable/data/partitioning/partitioned_writes)
- [DuckDB — Hive Partitioning](https://duckdb.org/docs/stable/data/partitioning/hive_partitioning)
- [Polars — `scan_parquet`](https://docs.pola.rs/api/python/stable/reference/api/polars.scan_parquet.html)
- [Polars — Streaming](https://docs.pola.rs/user-guide/concepts/streaming/)
- [Polars — Optimizations](https://docs.pola.rs/user-guide/lazy/optimizations/)

## Security and operations references to add during implementation

The implementation phase should select and version specific authoritative references for:

- secret management and host hardening;
- SBOM and dependency provenance;
- backup encryption and restore verification;
- time synchronization;
- structured logging/metrics;
- incident response;
- relevant jurisdiction/account compliance.
