# M1 bounded Bybit REST history-boundary specification

## Purpose

Test whether the three owner-approved V1 public sources expose historical data near current
instrument lifecycle boundaries and at sampled intermediate dates. The probe is read-only,
unauthenticated, bounded before network access, and does not persist market values or rows.

This is feasibility evidence, not a substitute for the Phase 2 full-universe gap audit.

## Command

```powershell
grid-data rest-history-boundary `
  --instrument-inventory benchmarks/results/m1-owner-storage-review-inventory-20260812.json `
  --sample-size 8 `
  --workers 8 `
  --max-requests 84 `
  --output benchmarks/results/m1-bybit-rest-history-boundary-20260812.json
```

The command receipt-verifies the input inventory and preflights output paths and the exact request
upper bound before creating a client. The published run used eight workers, one transport attempt
per request, and exactly 84 of the allowed 84 public requests.

## Deterministic selection

Only current-inventory records meeting all of these conditions are eligible:

- `LinearPerpetual`;
- quote and settle coin are both USDT;
- current status is `Trading` or `Closed`;
- lifecycle and positive funding-interval metadata are present.

The `equal-status-launch-time-stratified-v1` algorithm selects equal Trading/Closed groups when
available and samples within each group by launch-time rank. The published evidence selected four
of each status from 702 Trading and 303 Closed eligible records.

## Probe protocol

For each symbol and dataset:

1. Request the first 1,000 lifecycle minutes. Kline pages use the documented 1,000-row limit;
   funding uses its documented 200-event limit. The page is validated and processed in memory.
2. Request one row from seven-day windows at annual offsets.
3. Request one row from a terminal seven-day window unless an annual window already ends at the
   lifecycle boundary.
4. Validate reverse-ordered unique minute-aligned timestamps and requested bounds.
5. Persist timestamps, availability states, and canonical response hashes only.

If data is present in the launch window, the earliest returned timestamp is exact within that
window. If the launch window is empty but a checkpoint is non-empty, the result is explicitly
classified `sampled-checkpoint-not-exact-boundary`. No interpolation is performed.

## Published observation

The 2026-08-12 run completed without endpoint errors:

| Dataset | Available symbols | Exact in launch window | Sampled later | None observed |
|---|---:|---:|---:|---:|
| trade-price 1m | 7/8 | 4 | 3 | 1 |
| mark-price 1m | 8/8 | 5 | 3 | 0 |
| funding | 6/8 | 3 | 3 | 2 |

`DATAOLD01USDT` had mark-price data in the launch window but no trade or funding observation.
`RIOTUSDT`, a very recent Trading record at inventory capture, had no funding observation. BCHUSDT,
MATICUSDT, and STPTUSDT had sampled later observations for all three datasets but empty launch
windows. These are observed source/lifecycle mismatches requiring explicit gap reasons; they are
not permission to synthesize missing history.

## Safety and interpretation limits

- The transport allowlist permits only `/v5/market/*`; there is no authentication or trading path.
- Tick endpoints and archives are not requested.
- Raw OHLCV, turnover, and funding-rate values are neither serialized nor committed.
- An annual/terminal sampled window cannot prove continuous coverage between windows.
- Current lifecycle fields do not replace dated historical metadata.
- A source response hash records a content fingerprint without disclosing its market values.
- Full-universe exact range discovery, gap audit, and deterministic repair remain Phase 2 work.
- This artifact does not select P-001 through P-005, close Gate 1, or authorize a bulk download.
