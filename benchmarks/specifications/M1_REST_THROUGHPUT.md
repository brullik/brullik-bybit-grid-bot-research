# M1 bounded public REST throughput specification

## Purpose

Measure the practical full-page request rate for the one-minute-only Bybit V5 REST source plan on
the owner workstation and network route. This is Phase 1 feasibility evidence. It does not
implement or authorize the Phase 2 downloader.

## Fixed source and workload

- Origin: `https://api.bybit.com` only.
- Endpoints: `/v5/market/kline` and `/v5/market/mark-price-kline` only.
- Category: linear; interval: one minute; page limit: 1,000.
- Default stages: `1:1,4:5,8:10,16:20,24:30,32:40` as `workers:target-RPS`.
- Default duration: four seconds per stage; the first request launches immediately.
- Cooldown: 5.25 seconds after every non-failed non-final stage.
- Hard ceilings: 32 workers, 96 target RPS, eight stages, and 2,000 total requests.
- Retries: disabled (`max_attempts=1`).

The 96 RPS ceiling retains 20% headroom below the officially documented default IP limit of 600
requests per five seconds. A stage launches requests through one global pacer rather than allowing
each worker to rate-limit independently.

## Preflight and selection

Before creating a client or sending a request, the command:

1. rejects an existing output/receipt unless `--force` is explicit;
2. verifies completion receipts for the inventory, one-minute source assessment, and workstation
   snapshot;
3. verifies that the source assessment is hash-bound to the supplied inventory;
4. calculates the exact request total for all planned stages and rejects it above `--max-requests`;
5. selects the oldest mature current Trading USDT LinearPerpetual records deterministically; and
6. assigns distinct, non-overlapping 1,000-minute trade/mark pages that do not predate launch.

## Validation and stop behavior

Every successful response must contain exactly 1,000 unique, contiguous, reverse-chronological
minute timestamps inside the requested range. Any transport, Bybit, short-page, timestamp, or
continuity error fails the profile and prevents later profiles from starting. A fully valid
profile below 85% target attainment is labeled `under-target` but does not block a later profile
with more workers. No benchmark retry is made.

A profile passes only when:

- every planned request was attempted exactly once;
- every response is a valid full page;
- there are no errors; and
- observed wall-clock request rate reaches at least 85% of the target.

The highest passing profile is reported as a local concurrency candidate, not an operational
limit or acceptance decision.

## Evidence boundary

The schema is `grid.bybit-rest-throughput/v1`. The artifact contains aggregate request/row counts,
wall duration, observed RPS/rows per second, latency percentiles, aggregate response hashes,
provenance, and request-only bootstrap projections. Rows are parsed and hashed in memory, then
discarded. OHLCV values, funding rates, raw pages, credentials, account data, and tick rows are
never persisted.

Bootstrap projections apply the measured candidate RPS to the receipt-bound current and
conservative request counts. They exclude retry, gap repair, staging, schema validation,
canonical writes, audit, compaction, and service/network changes.

## Reproduction command

```powershell
grid-data rest-throughput `
  --instrument-inventory benchmarks/results/m1-owner-storage-review-inventory-20260812.json `
  --source-assessment benchmarks/results/m1-bybit-one-minute-source-assessment-20260812.json `
  --workstation-snapshot benchmarks/results/m1-owner-storage-review-workstation-20260812.json `
  --output benchmarks/results/m1-bybit-rest-throughput-YYYYMMDD-operator.json
```

## Published observations

Three append-only artifacts preserve the protocol correction and its results:

- `m1-bybit-rest-throughput-20260812.json`: the initial 15-request diagnostic used the former
  `1:5,4:20,8:40,16:70,32:90` defaults and stopped because one worker delivered 1.211243 RPS,
  below the incorrectly paired 5 RPS target. It remains negative evidence and is not a candidate.
- `m1-bybit-rest-throughput-20260812-r2.json`: the corrected six-stage sweep attempted all 424
  requests. The 24-worker stage completed 120/120 full pages without error at 15.027812 finite-run
  RPS. The 32-worker/40-RPS stage returned 158 full pages and two transport timeouts, so the
  artifact is intentionally partial and does not recommend that profile.
- `m1-bybit-rest-throughput-20260812-confirmation.json`: one explicit
  `--profiles 24:10 --stage-seconds 10 --max-requests 100` confirmation completed 100/100 full
  pages without endpoint errors. The run included an 8.078-second maximum response latency and
  measured 7.764397 strict end-to-end finite-run RPS, so the profile is `under-target` and the
  implementation emits no automatic concurrency recommendation.

Applying 7.764397 RPS mechanically to the receipt-bound current request estimate gives about
63.88 request-only hours; the conservative 60-minute funding estimate gives about 66.02 hours.
These are observations, not downloader commitments. The Phase 2 implementation must start below
the measured envelope and adapt from explicit rate/latency evidence.
