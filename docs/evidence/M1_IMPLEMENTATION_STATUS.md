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
- Owner-approved one-minute-only source contract and append-only v2 assessment covering
  trade-price 1m, mark-price 1m, and funding REST capacity while proving that no tick or market
  rows were downloaded or retained by the assessment.
- Bounded REST history-boundary probe with deterministic equal-status launch-time stratification,
  exact 84-request preflight, no transport retry, in-memory launch pages, annual/terminal
  checkpoints, explicit exact-versus-sampled semantics, and no persisted market values.
- Bounded, globally paced public REST throughput sweep with receipt-bound inventory/source/host
  provenance, exact request preflight, full-page continuity validation, no hidden retry, explicit
  error/under-target semantics, and no persisted market values.
- Staged ADR-0010 shortlist benchmark protocol with reboot-separated engine/query legs,
  post-timing content verification, immutable monthly repair, fragmented-input compaction, and
  cross-engine exact logical parity. Unverified local timing is forced to `local-smoke-only`.
- Bounded public real-market skew collector that receipt-verifies its inventory, selects a
  current-liquid exact-price-stratified sample, requires complete closed 1m candles, writes both
  exact shortlist layouts outside Git, and publishes only schema-validated aggregates and hashes.
- V3 capacity calibration that binds the real-market artifact and retains the independent
  24/40/64-byte planning envelopes and its legacy provisional 2 TiB recommendation. ADR-0019 does
  not rewrite that immutable evidence and supersedes the device size as a future admission gate.
- Legacy fail-closed reference-host admission that requires a receipt-verified fixed-profile
  workstation snapshot, matches current CPU/RAM/platform and storage identity, binds the measured
  work volume, and freezes Python/DuckDB/Polars/PyArrow/psutil versions across reboot-separated
  legs. ADR-0019 leaves those v1/v2 receipts immutable and requires an append-only successor.
- Shared legacy reference-host admission for the 100-million-row feature benchmark.
  `grid.feature-benchmark/v2` verifies the same fixed-profile host before and after the workload,
  freezes Polars/psutil/Python versions, and publishes a candidate only when the memory gate
  passes. Linux snapshots measure the actual longest matching mount.
- Append-only `grid.gate1-review-pack/v1` aggregation that accepts only receipt/schema-verified
  host-bound layout and feature v2 artifacts, re-verifies their workstation/ADR-0010/real-market
  sources, rejects cross-host/version/scale evidence, calculates documented provisional query,
  write, memory, and capacity checks, preserves negative results, and always leaves P-001—P-005
  plus Gate 1 pending for owner/PM review.
- Append-only `grid.current-universe-capacity/v1` aggregation that receipt/schema/hash-verifies a
  fresh lifecycle assessment, v3 storage calibration, and same-volume workstation snapshot;
  separates first bootstrap, full rebuild, daily append, and bounded monthly repair; rejects
  stale/cross-layout/internally inconsistent evidence before output replacement; and leaves raw
  source-archive headroom explicitly unmeasured.
- Fail-closed external reference-campaign handoff that admits the host/volume and pinned source
  evidence before publishing an immutable eight-step plan, exposes one next command or reboot at
  a time, rejects invalid/out-of-order receipts, and can never accept Gate 1 automatically.
- Read-only reference-environment bootstrap admission with CI-shared exact direct dependency
  constraints, explicit editable monorepo-package checks, Python 3.12/venv enforcement, clean
  canonical-main/source-manifest verification, `pip check`, required-import checks, and
  secret-name-only rejection of Bybit credential variables before a campaign plan can exist.
- Owner-accepted ADR-0019 evidence-based host policy. It removes fixed CPU/RAM/total-volume
  blockers for future append-only contracts while retaining same-host 100-million-row trials,
  the 70% memory gate, current free-space admission, stable local SSD/NVMe identity, and every
  existing performance/correctness/reboot gate.
- Append-only `grid.reference-host-qualification/v1` implementation that verifies the legacy
  100-million-row layout/feature receipts and schemas, proves their same-laptop hardware, binds
  the current-universe capacity to its exact workstation snapshot, rechecks current CPU/RAM/NVMe
  identity and free bytes, and publishes either qualified or auditable insufficient-space status
  without accepting Gate 1.
- Append-only feature/layout v3 workload admission that consumes a fresh measured-host
  qualification, forbids ambiguous legacy-plus-successor admission, binds the measured volume,
  rechecks current identity and required free space before and after timed work, preserves the 70%
  feature-memory and four-distinct-reboot gates, and cannot accept Gate 1.
- Append-only `grid.gate1-review-pack/v2` and `grid.reference-campaign-plan/v2` contracts that bind
  the exact ADR-0019 qualification to layout/feature v3, preserve all legacy schemas, embed the
  full clean Python 3.12 environment/source manifest, expose one run-or-reboot action at a time,
  and leave Gate 1 pending explicit owner/PM review.
- A passing Python 3.12.10 reference-environment doctor on the owner laptop and a standalone
  qualified feature v3 run over 99,999,900 rows: 29.047963300 seconds,
  3,442,578.709124216 core rows/s, 1,515,790,336 bytes peak RSS, and 9.199863966% of observed RAM.
  The later immutable campaign also completed the feature leg, all four reboot-separated layout
  measurements, finalization, and Gate 1 review-pack build. Its public evidence summary is
  [M1 qualified reference campaign](M1_QUALIFIED_REFERENCE_CAMPAIGN_20260812.md).
- Read-only inventory of the owner's older 1m archive: 29,098,027 trade/mark rows across 123
  symbols in 541,389,842 bytes. Its separate legacy run report measured 29,120,414 rows in 372.558
  seconds with zero failures. The observation informs capacity and throughput expectations but is
  not imported as canonical evidence because it lacks current receipts and stores prices as
  binary floating point.
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
  five products when observed on 2026-08-12. Public tick trades include contracts; mark-price
  klines are advertised for options only; no funding product is advertised. ADR-0016 classifies
  the tick product as incompatible with V1. Trade-price 1m, mark-price 1m, and funding therefore
  use public V5 REST unless a later catalog version adds an explicit compatible one-minute product.

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
  limitation, not proof that no unlisted bulk path exists. ADR-0016 nevertheless excludes the
  tick-trade product, so all three accepted historical datasets remain REST coverage concerns.
- The fixed BTCUSDT public sample for 2026-07-01 through 2026-07-07 contained 10,080 trade candles,
  10,080 mark candles, and 21 funding events at the metadata-derived 480-minute interval. The
  report found no duplicate timestamps, missing candles, or missing internal funding intervals.
- Each evidence artifact has a verified SHA-256 receipt. The public sample additionally validates
  against `grid.bybit-public-sample/v1`; raw market rows were not committed.
- The immutable v1 source assessment covered only mark-price and funding REST gaps. It recorded
  3,989,300 requests for that narrower envelope. It remains reproducible historical evidence but
  is superseded for current source planning by the owner-approved v2 assessment below.
- Applying current lifecycle fields to the verified partial inventory gives 884,733,307
  mark-price rows and 885,222 per-symbol requests across 1,006 USDT linear perpetual records. The
  current observed funding intervals imply 2,772,401 events and 14,394 requests; using the
  observed 60-minute minimum conservatively gives 14,746,066 events and 74,232 requests. These
  current fields are not dated historical metadata and do not replace the planning envelope.
- The owner-approved v2 assessment binds the later 1,010-record inventory and adds trade-price 1m
  to the source envelope. It estimates 885,053,361 rows and 885,570 per-symbol requests for each
  of trade-price and mark-price. With current funding intervals the total is 1,785,544 requests;
  the conservative 60-minute funding case is 1,845,401. Request-only bounds are 14,880/178,555
  seconds at 120/10 requests per second for the current case, and 15,379/184,541 seconds for the
  conservative case.
- For the formal 700-instrument, ten-year envelope, v2 records 7,671,300 total REST requests:
  3,682,000 each for trade-price and mark-price plus 307,300 for conservative funding. The
  request-only bounds are 63,928 seconds at 120 requests/second and 767,130 seconds at the
  10 requests/second planning rate. No market row was downloaded to produce this evidence.
- The immutable owner storage-review refresh later on 2026-08-12 observed 1,010 USDT linear
  perpetual records, including 702 `Trading`, and 885,053,361 per-dataset lifecycle minutes. An
  equal-coverage trade+mark comparison is 1,770,106,722 rows, or `24.039621018%` of the formal
  7,363,288,800-row design envelope. This is a current-metadata estimate, not downloaded history.
- The bounded 2026-07-01 through 2026-07-07 real-market sample contains 80,640 complete closed
  trade-price 1m candles across eight current-liquid contracts selected at exact price ranks from
  an 80-contract pool. The close-price range is `0.003998` through `64703.2`, a dynamic range of
  `16183891.94597298649324662331`; selection is current and therefore not historical-universe
  evidence.
- The 2026-08-12 REST-boundary probe selected four Trading and four Closed records from the
  receipt-verified 1,010-record inventory. It completed exactly 84 preflighted public requests in
  one attempt each with eight workers and zero endpoint errors. Mark was observed for 8/8 symbols,
  trade for 7/8, and funding for 6/8. Launch-window observations were
  exact within the first 1,000 lifecycle minutes for 5 mark, 4 trade, and 3 funding series; three
  series per dataset were observed only at sampled later checkpoints and are not claimed as exact
  boundaries.
- `DATAOLD01USDT` exposed launch-window mark data but no trade/funding in any probed window;
  `RIOTUSDT` exposed launch-window trade/mark but no funding; BCHUSDT, MATICUSDT, and STPTUSDT had
  empty launch windows and later sampled observations across all datasets. The downloader must
  record these as source/lifecycle evidence and must not invent missing minutes.
- The corrected public REST throughput sweep attempted all 424 preflighted trade/mark 1m page
  requests. Its 24-worker stage returned 120/120 full pages without error at 15.027812 finite-run
  RPS; the 32-worker/40-RPS stage returned 158 full pages plus two transport timeouts and is
  rejected. No request retried.
- The separate 24-worker/10-RPS confirmation returned 100/100 full pages with zero endpoint
  errors. It included an 8.078-second maximum response latency and measured 7.764397 strict
  end-to-end RPS, so it remains `under-target` and emits no automatic rate recommendation.
  Applying that observed rate gives about 63.88 current-case or 66.02 conservative request-only
  hours; downloader work, validation, publication, retry, and long-run variability remain
  excluded.

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
  projections do not reduce the independent planning envelopes. Their provisional 2 TiB storage
  recommendation is retained as historical evidence but superseded as an admission threshold by
  ADR-0019.
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
  and a 511.44 GB NVMe system volume. The owner storage-review snapshot observed
  193,679,237,120 bytes (180.378 GiB) free.
- ADR-0019 supersedes the provisional 16-32-core/64-128-GiB/2-TiB values as admission thresholds.
  They may still be convenient for concurrency, derived stores, and future growth, but are not
  required when measured same-host scale, memory, free-space, and performance evidence pass.
- Linear projection at the 100-million-row synthetic candidate rate is 1,147.407324279 s for
  3.681B trade rows and 2,294.814648559 s for 7.363B trade+mark rows. It excludes I/O publication, audits,
  compaction, concurrency, and real-market skew and is not a runtime commitment.
- Applying observed real trade-row widths to all 7.363B theoretical trade+mark rows projects
  184,318,805,827 and 187,181,850,475 bytes for the two shortlisted layouts. This is a conservative
  like-width comparison because mark rows omit volume and turnover and still require their own
  physical estimate. The independent 24/40/64-byte planning envelopes remain
  176.72/294.53/471.25 GB. Tick archives are excluded by ADR-0016. Neither estimate includes
  bounded REST staging, derived stores, experiments, compaction headroom, backup, or filesystem
  overhead. ADR-0019 requires those applicable working sets to be added to a fresh free-space
  preflight rather than assuming a 2 TiB device.
- On the owner storage-review volume, 193,679,237,120 bytes were free. The larger real-width
  current-universe projection requires 44,997,807,469 bytes (41.907 GiB) for the first canonical
  build, 89,995,614,938 bytes (83.815 GiB) for active plus building during a full rebuild,
  51,395,075 bytes (about 49 MiB) for one day, and 1,593,247,317 bytes (1.484 GiB) for a maximum
  31-day partition. All measured canonical scenarios fit; the independent 64-byte
  active-plus-building scenario requires 226,573,660,416 bytes and does not fit. Tick archives are
  no longer part of the source plan; REST staging remains unmeasured, and Gate 1 still does not
  authorize the full download.
- The current ADR-0019 Gate 1 calculation adds 89,995,614,938 bytes for active plus building,
  1,642,763,483 bytes of measured retained shortlist scratch, and an 8 GiB operating reserve.
  The resulting 100,228,313,013-byte (93.345 GiB) requirement fits the 180.378 GiB observation.
  It must be recalculated from fresh lifecycle/free-space evidence and does not yet include the
  future Phase 2 downloader's independently bounded REST-page staging.
- The live ADR-0019 qualification reran the disk/identity preflight and observed
  192,452,521,984 free bytes. It published `qualified-measured-reference-host` with
  92,224,208,971 bytes of headroom. Its source receipts and public qualification receipt verify;
  the artifact explicitly leaves the Python 3.12 environment and cold-cache campaign pending.
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

- Record the owner/PM decisions for P-001 through P-005 and Gate 1. The receipt-verified review
  pack is `ready-for-owner-review`, both layout candidates pass, and its blocker list is empty;
  implementation still cannot self-approve the gate.
