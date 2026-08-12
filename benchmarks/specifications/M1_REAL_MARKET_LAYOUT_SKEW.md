# M1 bounded real-market layout-skew specification

## Purpose

Measure how the two ADR-0010 exact-layout candidates compress real public Bybit trade candles
without committing raw rows or implementing the Phase 2 historical downloader. The result
calibrates capacity planning; it does not select a strategy, prove historical coverage, or close
Gate 1.

## Bounded selection

The collector receipt-verifies the current public inventory, fetches one unauthenticated ticker
snapshot, and considers current `Trading` USDT linear perpetuals launched before the sample. It
ranks the eligible universe by exact 24-hour turnover, retains a liquid pool of at least 50
contracts, and selects 3-12 evenly spaced exact mark-price ranks from that pool.

The candle window is limited to seven inclusive UTC days. Every selected symbol must return one
closed, aligned, unique trade-price 1m candle at every expected timestamp. Missing or malformed
data fails the run before public evidence is published.

## Reproducible command

The checked-in evidence used 2026-07-01 00:00 through 2026-07-07 23:59 UTC:

```powershell
python -m benchmarks.real_market_skew `
  --instrument-inventory benchmarks/results/m1-bybit-public-inventory.json `
  --work-dir .benchmark-work/real-market-skew `
  --start-ms 1782864000000 --end-ms 1783468740000 `
  --sample-size 8 --row-group-rows 100000 `
  --output benchmarks/results/m1-real-market-layout-skew.json
```

The work directory is ownership-marked and Git-ignored. `--force` may replace only a directory
whose verified marker matches this benchmark. The command uses public market endpoints only and
does not read API credentials.

## Checked-in result

The run collected 80,640 candles across eight contracts selected from an 80-contract liquid pool:
`1000BONKUSDT`, `BICOUSDT`, `ARBUSDT`, `TRXUSDT`, `LITUSDT`, `SOLUSDT`, `AAPLUSDT`, and
`BTCUSDT`. It covered close prices from `0.003998` to `64703.2`, a dynamic range of
`16183891.94597298649324662331`.

The four-bucket/32 MiB layout occupied 2,018,591 bytes (`25.032130456` bytes/row); the
eight-bucket/16 MiB layout occupied 2,049,946 bytes (`25.420957341` bytes/row). Both reopened with
the exact schema and produced the same DuckDB/Polars logical hash. Compared with the deterministic
synthetic measurements, real values used `3.883673175` and `3.905117385` times more bytes/row.

Only bounded aggregates, request counts, distribution statistics, tree/logical hashes, and
receipt-linked provenance are committed. Raw normalized candles and Parquet files remain under
`.benchmark-work/` and outside Git.

## Interpretation limits

- Current liquidity selection has survivorship bias and is not a historical universe.
- Seven current days and eight contracts cannot represent every volatility or lifecycle regime.
- Trade-price rows contain volume and turnover; mark-price rows require a separate physical-size
  estimate.
- Small samples do not exercise the shortlisted 16/32 MiB file targets. That remains a mandatory
  condition of the 100-million-row reference protocol.
- The artifact cannot approve P-001 through P-005 or Gate 1.
