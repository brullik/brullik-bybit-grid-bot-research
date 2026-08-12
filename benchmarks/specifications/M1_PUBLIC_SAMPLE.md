# M1 public trade/mark/funding sample

## Purpose

Exercise the current official Bybit public contracts for one bounded historical interval and
record enough evidence to verify row counts, time coverage, canonical values, and content
identity. This is a feasibility sample, not a committed market dataset and not proof of full
historical coverage.

## Fixed sample

- Instrument: `BTCUSDT` linear USDT perpetual.
- Inclusive interval: `2026-07-01T00:00:00Z` through `2026-07-07T23:59:00Z`.
- Trade and mark interval: one minute.
- Funding interval: read from the same-run `GET /v5/market/instruments-info` response.
- Maximum supported command span: 31 days.

## Reproduction

```powershell
grid-data public-sample `
  --symbol BTCUSDT `
  --start-ms 1782864000000 `
  --end-ms 1783468740000 `
  --output benchmarks/results/m1-bybit-public-sample.json `
  --force

grid-data verify-evidence benchmarks/results/m1-bybit-public-sample.json
```

## Evidence policy

The report stores normalized row counts, bounds, gap summaries, and SHA-256 identities. Raw
market rows remain outside Git. A `complete` result means this bounded request contained a
non-empty sample for all three datasets, with no missing one-minute candles or internal funding
intervals. It does not establish archive-wide or ten-year completeness.
