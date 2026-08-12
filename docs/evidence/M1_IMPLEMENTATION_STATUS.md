# M1 feasibility and benchmark status

**Status:** implementation in progress; Gate 1 remains closed.

## Implemented evidence tooling

- Cursor-safe inventory for Bybit V5 `GET /v5/market/instruments-info`.
- Reverse-chronological pagination guards for trade and mark 1m klines.
- Funding page contract with the documented 200-row maximum.
- Bounded public trade/mark/funding sampling with current instrument metadata, exact-decimal
  normalization, gap accounting, and raw-row exclusion from Git.
- Owner-controlled, testnet-first Futures Grid validate-only tooling. Its adapter has one allowed
  endpoint, hard-coded official origins, HMAC signing, no retries or redirects, environment-only
  credentials, private evidence receipts, and no create/close/transfer implementation.
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

## Measured public evidence

- The 2026-08-12 inventory observed 1,748 linear instrument/status records, including 1,006 USDT
  linear perpetual records. It is explicitly `partial` because Bybit rejected the documented
  `Settling` filter with `retCode=10001`; the rejection is retained in the artifact.
- The official archive index exposed 1,889 trading symbol directories. BTCUSDT daily trade files
  covered 2020-03-25 through 2026-08-11 and ETHUSDT covered 2020-10-21 through 2026-08-11, with no
  missing calendar dates inside either observed span.
- The fixed BTCUSDT public sample for 2026-07-01 through 2026-07-07 contained 10,080 trade candles,
  10,080 mark candles, and 21 funding events at the metadata-derived 480-minute interval. The
  report found no duplicate timestamps, missing candles, or missing internal funding intervals.
- Each evidence artifact has a verified SHA-256 receipt. The public sample additionally validates
  against `grid.bybit-public-sample/v1`; raw market rows were not committed.

## Validate-only readiness

- Official Bybit sources identify `POST /v5/fgridbot/validate` as the pre-create validation call.
- The V1 probe fixes `grid_mode="1"` (Neutral) and `grid_type="2"` (Geometric), passes all numeric
  fields as exact decimal/integer strings, and requires an explicit stop loss below the range.
- Success requires both `retCode=0` and
  `check_code=FGRID_CHECK_CODE_UNSPECIFIED`; any malformed response fails closed.
- The owner runbook is `ops/runbooks/M1_VALIDATE_ONLY_PROBE.md`. No authenticated probe has been
  performed by this implementation and no private result belongs in Git.

## Evidence still required to close Gate 1

- Extend official bulk archive coverage beyond the BTCUSDT/ETHUSDT daily-trade sample and document
  dataset/symbol/month gaps, especially mark-price and funding availability.
- Run the full layout matrix on declared reference hardware and decide P-001 through P-005.
- Run the missing feature-throughput/memory benchmark and produce an updated storage/hardware
  recommendation for the 700-instrument capacity envelope.
- Perform an owner-controlled, authenticated validate-only probe for native Futures Grid. No
  private credentials may be added to the repository, logs, or research artifacts.
- Record the owner/PM Gate 1 decision. This implementation does not self-approve its gate.
