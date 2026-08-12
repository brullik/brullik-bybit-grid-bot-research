# ADR-0017: Bounded Public REST Throughput Evidence

- Status: proposed; Gate 1 evidence only
- Date: 2026-08-12

## Context

ADR-0016 makes public V5 REST the V1 source for trade-price 1m, mark-price 1m, and
funding history until a compatible one-minute bulk product is verified. The current-universe
assessment estimates about 1.79 million requests, but its 120 and 10 request-per-second runtimes
are arithmetic bounds rather than measurements from the owner workstation and network route.

A full downloader remains a Phase 2 deliverable and is not authorized while Gate 1 is closed.
Nevertheless, Gate 1 can safely measure the dominant full-page request workload without retaining
market values or implementing ingestion state.

## Decision

Add the append-only `grid.bybit-rest-throughput/v1` evidence contract and a bounded public-only
benchmark with these rules:

- bind the run to receipt-verified inventory, one-minute source assessment, and workstation
  snapshot artifacts;
- permit only `https://api.bybit.com`, `/v5/market/kline`, and
  `/v5/market/mark-price-kline` with `interval=1` and a 1,000-row page limit;
- select mature current Trading USDT linear perpetuals deterministically and request distinct,
  non-overlapping full pages after their launch times;
- preflight every stage and enforce a hard maximum of 2,000 total requests before any client is
  created;
- pace request launches globally per stage, run stages with nondecreasing workers and strictly
  increasing RPS, insert more than a five-second cooldown between stages, and stop the sweep after
  the first endpoint or page-validation failure;
- cap targets at 96 requests per second, retaining at least 20% headroom below Bybit's documented
  default IP limit of 600 requests per five seconds;
- disable transport retries so the request count, errors, and latency distribution remain
  observable;
- validate every returned page as exactly 1,000 unique contiguous reverse-chronological minutes;
  and
- process rows in memory and publish only counts, timings, response hashes, provenance, and a
  completion receipt—never OHLCV values, raw pages, or tick rows.

An error-free profile below 85% target attainment remains an `under-target` measurement and does
not prevent a later, higher-concurrency profile from running. The highest error-free profile
reaching at least 85% of its target becomes a local candidate for future downloader concurrency.
It is not an accepted rate limit, a service-level guarantee, a Gate 1 decision, or Phase 2
authorization. Request-only bootstrap projections explicitly exclude retry, validation, staging,
canonical writes, audits, repair, and compaction.

## Consequences

- The first bootstrap plan gains a measured local network/request envelope instead of relying only
  on arithmetic rate-limit bounds.
- The workload is deliberately short and cannot characterize long-duration throttling, regional
  routing changes, or service variability.
- Funding is excluded from the timing mix because trade and mark requests dominate the current
  estimate; projections that include funding remain approximate and say so.
- The benchmark cannot be reused as downloader state and writes no market dataset.
- The initial append-only run that paired one worker with a 5 RPS target remains negative evidence;
  the corrected default sweep starts at 1 RPS and scales target rate with worker concurrency.
- A future Phase 2 implementation must choose a lower operational rate, add adaptive throttling,
  durable resume/receipt logic, and prove behavior under long-running load.

## Rejected alternatives

- Run at 120 requests per second: Bybit explicitly recommends not operating at the edge of its IP
  limit, and other traffic may share the same address.
- Implement the production downloader to measure it: that crosses the closed Gate 1 boundary.
- Persist raw pages for later inspection: this creates unnecessary market-data staging during the
  feasibility phase.
- Retry failed requests inside the benchmark: hidden retries corrupt the measured request count
  and obscure throttling or transport failures.
