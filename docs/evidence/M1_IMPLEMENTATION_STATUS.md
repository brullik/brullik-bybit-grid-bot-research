# M1 feasibility and benchmark status

**Status:** implementation in progress; Gate 1 remains closed.

## Implemented evidence tooling

- Cursor-safe inventory for Bybit V5 `GET /v5/market/instruments-info`.
- Reverse-chronological pagination guards for trade and mark 1m klines.
- Funding page contract with the documented 200-row maximum.
- Bounded public trade/mark/funding sampling with current instrument metadata, exact-decimal
  normalization, gap accounting, and raw-row exclusion from Git.
- Owner-controlled, testnet-first Futures Grid validate-only tooling. Its adapter has one allowed
  endpoint, hard-coded official Testnet/Demo/Mainnet origins, environment-isolated HMAC
  credentials, no retries or redirects, private evidence receipts, and no create/close/transfer
  implementation. Demo failure cannot fall back to mainnet.
- Public-data candidate selection for low-capital Mainnet validation, with exact-decimal filters,
  deterministic ranking, and tick-aligned parameter ranges.
- Redaction of multiple verified private Mainnet reports into a schema-validated public conclusion
  that contains no credentials, account identifiers, private hashes, or raw response bodies.
- Atomic public evidence publication with a SHA-256 completion receipt written last.
- Versioned JSON Schemas and exact-decimal domain contracts.
- Reproducible bounded-memory Parquet layout benchmark for Polars and DuckDB. V2 writes
  deterministic chunks through PyArrow into real UTC calendar/bucket partitions, preflights
  scratch space, records peak RSS and actual file-size attainment, validates aggregates in both
  engines, and resumes only identical hash-receipted per-layout checkpoints.
- Lookahead-safe Polars feature benchmark with 1,440-minute read-only halos, bounded shards, peak
  RSS sampling, and parity/no-future tests.
- Reproducible workstation snapshot and documented profile assessment.
- Receipt-linked comparison of all current USDT LinearPerpetual symbols with the official archive
  index, plus bounded direct probes for index exceptions, `PreLaunch` symbols, and a deterministic
  launch-time-stratified sample.
- Allowlisted, unauthenticated inspection of the official Historical Market Data product catalog,
  with fail-closed response validation and per-symbol REST capacity estimates linked to the
  verified current inventory.
- Staged ADR-0010 shortlist benchmark protocol with reboot-separated engine/query legs,
  post-timing content verification, immutable monthly repair, fragmented-input compaction, and
  cross-engine exact logical parity. Unverified local timing is forced to `local-smoke-only`.
- Bounded public real-market skew collector that receipt-verifies its inventory, selects a
  current-liquid exact-price-stratified sample, requires complete closed 1m candles, writes both
  exact shortlist layouts outside Git, and publishes only schema-validated aggregates and hashes.
- V3 capacity calibration that binds the real-market artifact and retains the independent
  24/40/64-byte planning envelopes and provisional 2 TiB recommendation.
- Fail-closed reference-host admission that requires a receipt-verified full-profile workstation
  snapshot, matches current CPU/RAM/platform and storage identity, binds the measured work volume,
  and freezes Python/DuckDB/Polars/PyArrow/psutil versions across all reboot-separated legs.
- Shared reference-host admission for the 100-million-row feature benchmark. New reference runs
  use `grid.feature-benchmark/v2`, verify the same ≥16-core/64 GiB/2 TiB NVMe host before and after
  the workload, freeze Polars/psutil/Python versions, and publish a candidate only when the memory
  gate passes. Linux snapshots measure the actual longest matching mount.
- Append-only `grid.gate1-review-pack/v1` aggregation that accepts only receipt/schema-verified
  host-bound layout and feature v2 artifacts, re-verifies their workstation/ADR-0010/real-market
  sources, rejects cross-host/version/scale evidence, calculates documented provisional query,
  write, memory, and capacity checks, preserves negative results, and always leaves P-001—P-005
  plus Gate 1 pending for owner/PM review.
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
  private `POST /v5/fgridbot/validate` and `POST /v5/fgridbot/create` endpoints at 10
  requests/second.
- The official [Trading MCP create contract](https://github.com/bybit-exchange/trading-mcp/blob/562291168e9fd3d679275bf28c16056d562cefce/src/tools/bot/createFGridBot.ts)
  requires the validated fields plus `total_investment` and identifies `bot_id` as the handle for
  detail and close operations. Its existence is capability evidence, not a live permission.
- The official [Historical Market Data page](https://www.bybit.com/en/derivative-activity/history-data)
  and its public
  [product catalog](https://api2.bybit.com/quote/public/support/download/list-products) advertised
  five products when observed on 2026-08-12. Public trades include contracts; mark-price klines
  are advertised for options only; no funding product is advertised. Linear-contract mark-price
  1m and funding therefore remain REST datasets unless a later catalog version adds an explicit
  compatible bulk product.

## Measured public evidence

- The 2026-08-12 inventory observed 1,748 linear instrument/status records, including 1,006 USDT
  linear perpetual records. It is explicitly `partial` because Bybit rejected the documented
  `Settling` filter with `retCode=10001`; the rejection is retained in the artifact.
- The official archive index exposed 1,889 trading symbol directories. BTCUSDT daily trade files
  covered 2020-03-25 through 2026-08-11 and ETHUSDT covered 2020-10-21 through 2026-08-11, with no
  missing calendar dates inside either observed span.
- Of 1,006 current USDT LinearPerpetual symbols, 1,002 appeared in the observed `/trading/` index:
  all 699 `Trading`, all 5 `PreLaunch`, and 298 of 302 `Closed` records. The index also contained
  887 symbols outside that current snapshot, so it is not interchangeable with a current universe.
- Direct probes resolved the four current index exceptions: `BITUSDT` retained 632 daily files
  from 2021-10-11 through 2023-07-04 despite not being listed; `MONPROUSDT` had an accessible path
  with no daily files; `LAYERUSDT` and `LITENTRYUSDT` returned HTTP 404.
- The 20-symbol detailed sample found no internal calendar gaps within any observed non-empty
  daily-trade span and no archive start before the current metadata launch date. These findings do
  not replace dated historical metadata snapshots.
- The observed root advertised `kline_for_metatrader4`, `premium_index`, `spot`, `spot_index`, and
  `trading`; no product named for mark price or funding was advertised. This is an observed index
  limitation, not proof that no unlisted bulk path exists, so mark/funding history remains a REST
  coverage and capacity concern.
- The fixed BTCUSDT public sample for 2026-07-01 through 2026-07-07 contained 10,080 trade candles,
  10,080 mark candles, and 21 funding events at the metadata-derived 480-minute interval. The
  report found no duplicate timestamps, missing candles, or missing internal funding intervals.
- Each evidence artifact has a verified SHA-256 receipt. The public sample additionally validates
  against `grid.bybit-public-sample/v1`; raw market rows were not committed.
- The 700-instrument, ten-year planning envelope contains 3,681,644,400 instrument-minutes. At
  documented per-page limits, linear mark-price 1m needs 3,682,000 requests and conservative
  60-minute funding needs 307,300 requests, for 3,989,300 combined requests. Request-only time is
  398,930 seconds at the 10 requests/second planning rate or at least 33,245 seconds at the
  documented default IP limit of 120 requests/second; both exclude operational overhead.
- Applying current lifecycle fields to the verified partial inventory gives 884,733,307
  mark-price rows and 885,222 per-symbol requests across 1,006 USDT linear perpetual records. The
  current observed funding intervals imply 2,772,401 events and 14,394 requests; using the
  observed 60-minute minimum conservatively gives 14,746,066 events and 74,232 requests. These
  current fields are not dated historical metadata and do not replace the planning envelope.
- The bounded 2026-07-01 through 2026-07-07 real-market sample contains 80,640 complete closed
  trade-price 1m candles across eight current-liquid contracts selected at exact price ranks from
  an 80-contract pool. The close-price range is `0.003998` through `64703.2`, a dynamic range of
  `16183891.94597298649324662331`; selection is current and therefore not historical-universe
  evidence.

## Measured local benchmark evidence

- The layout smoke run used 200,000 rows and 50 instruments. All eight 1 MiB smoke layouts were
  measured, but none reached 80% of the requested file size; its status therefore remains
  `smoke-only` and it supports no P-001 through P-004 decision.
- The V2 out-of-core smoke repeated all eight layouts with exact row-count and aggregate parity in
  DuckDB and Polars. Its maximum observed RSS increase was 74,072,064 bytes; the evidence receipt
  verifies and the status remains `smoke-only`.
- The V2 scaled full matrix wrote and scanned all 54 combinations over 10,000,000 rows and 700
  instruments. Aggregate write time was 227.562 s and the six measured scans per layout totaled
  7.819 s. Both engines matched expected counts and aggregate values for every layout. Peak
  process RSS was 701,689,856 bytes and the largest baseline-relative increase was 315,822,080
  bytes.
- None of the scaled layouts produced a non-tail file at least 80% of its requested 128/256/512
  MiB target, so the artifact correctly reports `scaled-only`. The smallest observed layout was
  54,638,328 bytes for scaled Int64, 8 buckets, and ZSTD level 3. These results do not choose a
  physical layout; the full calendar-spanning run and reference-hardware evidence remain required.
- The full-profile local candidate completed all 54 layouts over 99,999,900 rows, 700 instruments,
  and four real UTC calendar months. Aggregate write time across the entire matrix was
  2,705.069363100 s and all six scans per layout totaled 35.566339300 s. Every DuckDB/Polars
  row-count and aggregate comparison passed. Peak process RSS was 1,089,785,856 bytes and the
  largest baseline-relative increase was 356,229,120 bytes.
- Per-layout compressed size ranged from 631,822,933 to 1,182,975,174 bytes. The smallest layout
  was scaled Int64, 8 buckets, ZSTD level 3; the fastest write was scaled Int64, 16 buckets,
  Snappy at 32.568810500 s. These are local-host candidate results, not an accepted physical
  choice.
- The largest individual file across the matrix was only 45,730,398 bytes. No layout created a
  non-tail file reaching 80% of a 128/256/512 MiB target, so the artifact correctly fails closed
  as `full-matrix-insufficient-file-scale`. The evidence rejects the current month × 8/16/32
  bucket × 128–512 MiB matrix as internally incompatible at this row density and motivates the
  ADR-backed revised matrix recorded below.
- The ADR-0010 exact decision matrix completed all 16 combinations over 99,999,900 rows and 700
  instruments. All DuckDB/Polars counts and exact aggregates matched, all Parquet numeric
  contracts reopened and verified, 14 layouts materially exercised their requested target, and
  the artifact reports `decision-matrix-candidate`. Aggregate write and scan time were
  819.498028500 s and 10.996928900 s; maximum process RSS was 1,676,791,808 bytes.
- The deterministic reference rerun shortlist is hybrid Int64-price/Decimal128 volume and
  turnover with ZSTD level 3: four buckets at 32 MiB and eight buckets at 16 MiB. Their observed
  sizes were 6.445478115 and 6.509652550 bytes/row. Projecting those measurements to 7.363 billion
  trade+mark rows gives 47,459,916,819 and 47,932,451,711 bytes, respectively. These synthetic
  projections do not reduce the independent planning envelopes or the provisional 2 TiB storage
  recommendation.
- On the identical 80,640 real candles, the four-bucket/32 MiB and eight-bucket/16 MiB layouts
  occupied 2,018,591 and 2,049,946 bytes, or `25.032130456` and `25.420957341` bytes/row. Exact
  schemas reopened successfully and DuckDB/Polars produced one common logical hash. Real values
  used `3.883673175` and `3.905117385` times the bytes/row of the deterministic synthetic data.
- The scaled feature run processed 9,999,500 core rows across all 700 instruments in 2.930438400 s
  (3,412,288.072664424 core rows/s). Five bounded shards read 14,031,500 rows including halos; the
  largest input shard was 3,024,000 rows.
- Peak feature-build RSS was 1,472,802,816 bytes, or 8.938957608% of the observed 16,476,225,536
  bytes RAM. This passes the configured 70% limit for this scaled run only; it is not a full-scale
  feature-memory result.
- The 100-million-row reference-scale candidate processed 99,999,900 core rows across 700
  instruments and 50 shards in 31.165589400 s (3,208,663.847698684 core rows/s). Peak RSS was
  1,511,342,080 bytes, or 9.172865938% of observed RAM; the largest input shard remained bounded at
  3,024,000 rows. This immutable v1 artifact predates host admission; its
  `reference-scale-candidate` status means reference row scale only and is not accepted reference
  hardware evidence.
- The measured workstation is an AMD Ryzen 5 5600H (6 physical/12 logical cores), 16.48 GB RAM,
  and a 511.44 GB NVMe system volume with about 199 GB free at capture time. It is below both the
  documented local-feasibility/storage envelope and the full research-workstation profile.
- The current provisional recommendation remains 16-32 physical/high-performance cores, 64-128
  GiB RAM, and at least 2 TiB NVMe plus separately sized backup storage for the full Gate 1 run.
- Linear projection at the 100-million-row synthetic candidate rate is 1,147.407324279 s for
  3.681B trade rows and 2,294.814648559 s for 7.363B trade+mark rows. It excludes I/O publication, audits,
  compaction, concurrency, and real-market skew and is not a runtime commitment.
- Applying observed real trade-row widths to all 7.363B theoretical trade+mark rows projects
  184,318,805,827 and 187,181,850,475 bytes for the two shortlisted layouts. This is a conservative
  like-width comparison because mark rows omit volume and turnover and still require their own
  physical estimate. The independent 24/40/64-byte planning envelopes remain
  176.72/294.53/471.25 GB. Neither estimate includes raw archives, derived stores, experiments,
  compaction headroom, backup, or filesystem overhead; the 2 TiB recommendation remains unchanged.
- The staged reference-layout protocol smoke retained both exact shortlisted layouts over 200,000
  rows and 50 instruments. All four DuckDB/Polars by single-symbol/universe-month legs verified
  file metadata before timing, content hashes afterward, expected row counts, and cross-engine
  result hashes. Its cache mode was explicitly unverified and its status is `local-smoke-only`.
- For the first monthly bucket in each shortlist layout, immutable repair and eight-fragment
  compaction preserved exact schema, row count, timestamp bounds, and OHLC/volume/turnover sums in
  both DuckDB and Polars. Source tree hashes were unchanged. These small synthetic maintenance
  timings validate the protocol only; they are not reference-hardware or real-market evidence.

## Validate-only readiness

- Official Bybit sources identify `POST /v5/fgridbot/validate` as the pre-create validation call.
- The probe fixes `grid_mode="1"` (Neutral) and `grid_type="2"` (Geometric), passes all numeric
  fields as exact decimal/integer strings, and requires an explicit stop loss below the range.
- Success requires both `retCode=0` and
  `check_code=FGRID_CHECK_CODE_UNSPECIFIED`; any malformed response fails closed.
- On 2026-08-12 the owner created an isolated Demo key and performed one signed request against
  `api-demo.bybit.com`. Bybit returned `retCode=10032`, `Demo trading are not supported.` The
  private report and receipt verified, remained Git-ignored, persisted no credentials, called no
  mutating endpoint, made no retry, and did not fall back to Testnet or mainnet.
- The redacted public conclusion is `m1-bybit-demo-validate-conclusion.json`; it contains no prices,
  credentials, account identifiers, or private-artifact hash. The outcome matches Bybit's
  published Demo service list, which does not advertise `/v5/fgridbot/validate`.
- The owner runbook is `ops/runbooks/M1_VALIDATE_ONLY_PROBE.md`. Demo feasibility is now resolved
  as unsupported.
- After the owner confirmed completed UTA migration, the owner-controlled Mainnet runner sent one
  validate request each for XRPUSDT, DOGEUSDT, and LINKUSDT with two cells and leverage 1. All
  three returned `retCode=0` and `FGRID_CHECK_CODE_UNSPECIFIED`; every private receipt verified,
  no request retried, and no mutating endpoint was called.
- Bybit reported minimum investments of 0.1389 USDT for XRPUSDT, 0.0989 USDT for DOGEUSDT, and
  1.1887 USDT for LINKUSDT. These values are feasibility observations only: `total_investment` was
  not submitted and `create` was not called.
- `m1-mainnet-validate-candidates.json` records the unauthenticated public shortlist snapshot.
  `m1-bybit-mainnet-validate-conclusion.json` records only the redacted successful Mainnet result
  and the pinned official create contract. Private reports and credentials remain outside Git.
- Native Futures Grid validate-only feasibility is resolved successfully on Mainnet. This does
  not close Gate 1 and does not open implementation or execution of the Phase 8 create workflow.

## Evidence still required to close Gate 1

- Run the staged ADR-0010 shortlist protocol on declared reference hardware with four distinct
  reboot-separated measurement legs using the now receipt-verified real-market-skew binding, then
  decide P-001 through P-005. The protocol now rejects the checked-in below-profile workstation
  snapshot before mutation; a qualifying ≥16-core/64 GiB/2 TiB NVMe host remains external evidence.
  The local maintenance/cold-read smoke result satisfies none of those reference claims.
- Repeat the 100-million-row feature and full layout benchmarks on declared reference hardware and
  replace the provisional runtime/storage/hardware projection with accepted evidence. The feature
  CLI now rejects the checked-in below-profile workstation snapshot before computation or output
  replacement and requires a v2 host-bound result.
- Build the v1 Gate 1 review pack from the completed external layout/feature reference artifacts;
  immutable v1-v3 provisional projections intentionally retain their original local semantics.
- Record the owner/PM Gate 1 decision. This implementation does not self-approve its gate.
