# M1 feasibility and benchmark status

**Status:** implementation in progress; Gate 1 remains closed.

## Implemented evidence tooling

- Cursor-safe inventory for Bybit V5 `GET /v5/market/instruments-info`.
- Reverse-chronological pagination guards for trade and mark 1m klines.
- Funding page contract with the documented 200-row maximum.
- Atomic public evidence publication with a SHA-256 completion receipt written last.
- Versioned JSON Schemas and exact-decimal domain contracts.
- Reproducible Parquet layout benchmark for Polars and DuckDB.
- Automated import-boundary checks that keep research/data engines out of `grid-live`.

## Authoritative API findings

- [Instruments info](https://bybit-exchange.github.io/docs/v5/market/instrument) requires cursor
  pagination for the linear universe because the default page is 500 and the universe is larger.
- [Trade-price klines](https://bybit-exchange.github.io/docs/v5/market/kline) return reverse-sorted
  rows and allow at most 1,000 rows per request.
- [Mark-price klines](https://bybit-exchange.github.io/docs/v5/market/mark-kline) use a distinct
  endpoint and the same 1,000-row futures limit.
- [Funding history](https://bybit-exchange.github.io/docs/v5/market/history-fund-rate) allows at
  most 200 events and requires the contemporaneous instrument funding interval.
- The official [rate-limit table](https://bybit-exchange.github.io/docs/v5/rate-limit) lists the
  private `POST /v5/fgridbot/validate` endpoint at 10 requests/second.

## Evidence still required to close Gate 1

- Run and review the current public universe/coverage inventory.
- Inventory official bulk archive coverage per dataset, symbol, and month.
- Run the full layout matrix on declared reference hardware and decide P-001 through P-005.
- Perform an owner-controlled, authenticated validate-only probe for native Futures Grid. No
  private credentials may be added to the repository, logs, or research artifacts.
- Record the owner/PM Gate 1 decision. This implementation does not self-approve its gate.
