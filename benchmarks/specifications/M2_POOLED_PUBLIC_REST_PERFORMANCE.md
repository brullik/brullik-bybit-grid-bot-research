# M2 pooled public REST performance evidence

## Purpose

Measure the merged ADR-0083 transport against the earlier 24-worker/10-RPS confirmation without
changing the request-rate ceiling or persisting response rows. The result is component evidence
for downloader throughput, not a Gate 2 threshold or a full-campaign timing.

## Fixed workload

- implementation identity: merge `6fc48f1af3244c4c73e4455f5f3ddbc9c1af889b`;
- 24 workers and at most 24 pooled HTTPS connections;
- global target: 10 requests/second;
- one transport attempt per application attempt;
- 100 requests over eight deterministically selected public linear instruments;
- 50 trade-price and 50 mark-price 1m pages, each requiring exactly 1,000 rows;
- response rows validated and hashed in memory, then discarded;
- baseline: receipt-verified `m1-bybit-rest-throughput-20260812-confirmation.json`.

The wrapper verifies that the selected workload and aggregate response hash match the baseline.
GitHub receives no command, symbol, instrument ID, request time bound, runtime path, market value,
account data, or credential.

## Result

The 2026-08-14 run completed 100/100 requests and validated 100,000 rows with zero errors. It
measured 9.709345 requests/second and 10,299,356,000 ns wall time, compared with 7.764397
requests/second and 12,879,301,000 ns for the baseline. The observed request-rate ratio is
1.250496 and wall time fell 20.031716%. The response-hash aggregate is identical.

The measurement used one host and network route. It does not guarantee future Bybit latency,
measure canonical publication, change adaptive throttling, close Gate 2, authorize Phase 3, or
enable any private/live capability.
