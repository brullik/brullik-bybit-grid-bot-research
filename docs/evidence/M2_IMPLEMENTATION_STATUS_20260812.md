# M2 canonical market-data implementation status — 2026-08-12

**Status:** Phase 2 is active; the bounded public 1m Landing-to-canonical path is implemented and
verified. Gate 2 remains closed.

## GitHub source of truth

The authoritative implementation and review history is:

- PR [#16](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/16): exact canonical
  physical contract;
- PR [#17](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/17): receipt-last
  immutable canonical writer;
- PR [#18](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/18): stable instrument
  registry and resumable public 1m acquisition;
- PR [#19](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/19): fresh host-snapshot
  call-order correction;
- PR [#20](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/20): verified
  Landing-to-canonical publication;
- PR [#21](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/21): sanitized,
  receipt-verified pilot evidence;
- PR [#22](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/22): fail-closed
  canonical requested-range coverage audit; and
- PR [#23](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/23): receipt-verified
  measured coverage evidence.

The sanitized, receipt-verified measured result is
[`m2-public-1m-canonical-pilot-20260812.json`](../../benchmarks/results/m2-public-1m-canonical-pilot-20260812.json).
Local Landing pages, candle rows, and Parquet files are deliberately not in Git. Their canonical
hashes and receipt relationships are in the evidence artifact under ADR-0025.

## Verified bounded pilot

- Source: unauthenticated Bybit mainnet public `GET /v5/market/kline`, interval `1`.
- Scope: BTCUSDT and UNIUSDT, 2026-07-01 through 2026-07-07 inclusive.
- Exact requested coverage: 20,160 consecutive 1m rows, 10,080 per instrument.
- Acquisition: 22 fixed pages, 22 HTTP attempts, zero empty pages, 24 workers, global 10-RPS
  target.
- Landing manifest SHA-256:
  `4e5571d82a7acf83e10f816560703c82cdbcce18a37910c709cae72b11a2e4d0`.
- Canonical dataset: `trade-1m-4e5571d82a7acf83e10f8165`, two instruments, one 481,048-byte
  ZSTD-3 tail Parquet file.
- Canonical manifest SHA-256:
  `2b9f6cce69be8bec260b1745c4380e2278bdfdd96d6d1438f79ce5c664269117`.
- Publisher identity: `git:0f3b0a164c7f7f9765b0d77168e56f4957368fcf` (PR #20 merge commit).
- Independent canonical verification passed; an identical execution preflight returned
  `existing_commit=true` and preserved the same manifest hash.
- No API key, private endpoint, order, bot, transfer, tick archive, account identifier, or market
  value was added to GitHub.

## Coverage-audit implementation

`grid-data audit-history-1m` and `grid.canonical-1m-coverage-audit/v1` implement a read-only,
fail-closed audit for exact Landing/Parquet equality, every requested minute, duplicates,
unexpected or unrequested rows, and registry lifecycle bounds. A REST-returned missing minute is
preserved as blocked evidence and is not accepted automatically.

The receipt-verified measured audit is
[`m2-canonical-coverage-audit-20260812.json`](../../benchmarks/results/m2-canonical-coverage-audit-20260812.json).
It ran under auditor merge identity `git:374ddcc7d9763f7a991818cab4eaf4ce0cd7614b`
against publisher identity `git:0f3b0a164c7f7f9765b0d77168e56f4957368fcf`. Exact
Landing/canonical table equality passed across all 20,160 requested rows. Missing, duplicate,
conflicting, unexpected, unrequested, and lifecycle-invalid counts were all zero; the complete gap
range list was empty and hash-bound. This establishes only the bounded requested ranges, not the
complete historical universe or Gate 2.

## Gap-repair planning implementation

`grid-data plan-history-repair` and `grid.bybit-1m-gap-repair-plan/v1` provide the next fail-closed
boundary. The no-network command recomputes a receipt-verified blocked audit and permits planning
only when missing requested minutes classified as `rest_returned_no_data` are the sole blocker.
It accounts for the complete gap list and embeds bounded, standard history requests without
editing the committed canonical dataset or changing the accepted-reason policy. The measured
pilot audit passes with zero gaps, so no artificial runtime repair artifact is created.

## Still required before Gate 2

- historical lifecycle inventory beyond the current snapshot;
- measured coverage-audit evidence at each controlled scale and an owner-reviewed reason policy;
- measured repair execution and immutable replacement lineage when a genuine gap is observed;
- multi-file target-size compaction and tail policy at representative scale;
- catalog registration and reproducible range selection;
- long-run adaptive throttling evidence and controlled scale-up; and
- funding ingestion plus the remaining PM-owned Gate 2 acceptance checklist.
