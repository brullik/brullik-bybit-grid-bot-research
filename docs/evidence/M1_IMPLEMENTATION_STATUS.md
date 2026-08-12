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
- Reproducible Parquet layout benchmark for Polars and DuckDB. Its scale labels fail closed,
  actual file-size attainment is recorded, and scratch layouts are deleted after each scan.
- Lookahead-safe Polars feature benchmark with 1,440-minute read-only halos, bounded shards, peak
  RSS sampling, and parity/no-future tests.
- Reproducible workstation snapshot and documented profile assessment.
- Receipt-linked comparison of all current USDT LinearPerpetual symbols with the official archive
  index, plus bounded direct probes for index exceptions, `PreLaunch` symbols, and a deterministic
  launch-time-stratified sample.
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
- The official [developer portal](https://bybit-exchange.github.io/docs/) advertises public OHLCV
  and trade-history CSV downloads. It does not identify that OHLCV as canonical mark-price data or
  advertise funding-event bulk data, so the implementation does not infer either semantic.

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

## Measured local benchmark evidence

- The layout smoke run used 200,000 rows and 50 instruments. All eight 1 MiB smoke layouts were
  measured, but none reached 80% of the requested file size; its status therefore remains
  `smoke-only` and it supports no P-001 through P-004 decision.
- The scaled feature run processed 9,999,500 core rows across all 700 instruments in 2.930438400 s
  (3,412,288.072664424 core rows/s). Five bounded shards read 14,031,500 rows including halos; the
  largest input shard was 3,024,000 rows.
- Peak feature-build RSS was 1,472,802,816 bytes, or 8.938957608% of the observed 16,476,225,536
  bytes RAM. This passes the configured 70% limit for this scaled run only; it is not a full-scale
  feature-memory result.
- The measured workstation is an AMD Ryzen 5 5600H (6 physical/12 logical cores), 16.48 GB RAM,
  and a 511.44 GB NVMe system volume with about 199 GB free at capture time. It is below both the
  documented local-feasibility/storage envelope and the full research-workstation profile.
- The current provisional recommendation remains 16-32 physical/high-performance cores, 64-128
  GiB RAM, and at least 2 TiB NVMe plus separately sized backup storage for the full Gate 1 run.
- Linear projection at the observed synthetic feature rate is 1,078.937159349 s for 3.681B trade
  rows and 2,157.874318697 s for 7.363B trade+mark rows. It excludes I/O publication, audits,
  compaction, concurrency, and real-market skew and is not a runtime commitment.
- The small synthetic layout projects 49.16-185.36 GB for trade+mark, while the independent
  documented 24/40/64-byte planning envelopes remain 176.72/294.53/471.25 GB. Neither includes
  raw archives, derived stores, experiments, compaction headroom, backup, or filesystem overhead;
  the 2 TiB recommendation is intentionally not reduced from smoke compression.

## Validate-only readiness

- Official Bybit sources identify `POST /v5/fgridbot/validate` as the pre-create validation call.
- The V1 probe fixes `grid_mode="1"` (Neutral) and `grid_type="2"` (Geometric), passes all numeric
  fields as exact decimal/integer strings, and requires an explicit stop loss below the range.
- Success requires both `retCode=0` and
  `check_code=FGRID_CHECK_CODE_UNSPECIFIED`; any malformed response fails closed.
- The owner runbook is `ops/runbooks/M1_VALIDATE_ONLY_PROBE.md`. No authenticated probe has been
  performed by this implementation and no private result belongs in Git.

## Evidence still required to close Gate 1

- Obtain authoritative Bybit confirmation whether any bulk OHLCV product is canonical mark-price
  history and whether funding-event bulk data exists, then size the remaining REST backfill;
  neither dataset is advertised by name in the observed archive root/developer summary.
- Run the full layout matrix on declared reference hardware and decide P-001 through P-005.
- Repeat the feature-throughput/memory benchmark at representative scale on that hardware and
  replace the provisional runtime/storage/hardware projection with accepted evidence.
- Perform an owner-controlled, authenticated validate-only probe for native Futures Grid. No
  private credentials may be added to the repository, logs, or research artifacts.
- Record the owner/PM Gate 1 decision. This implementation does not self-approve its gate.
