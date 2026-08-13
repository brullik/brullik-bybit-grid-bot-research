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
  measured coverage evidence; and
- PR [#24](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/24): verified,
  bounded standard-request planning for blocked 1m gaps; and
- PR [#25](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/25): whole-plan-admitted
  repair execution and immutable parent-to-child replacement lineage.
- PR [#26](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/26): target-size
  immutable compaction, multi-file/tail verification, and complete parent lineage.
- PR [#27](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/27): receipt-verified
  DuckDB catalog registration and snapshot-bound reproducible range selection.
- PR [#28](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/28): representative
  catalog registration/selection evidence for the existing receipt-verified public pilot.
- PR [#29](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/29): exact canonical
  funding physical contract and receipt-last immutable publication primitive.
- PR [#30](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/30): predecessor-bound,
  receipt-resumable public funding acquisition and verified Landing-to-canonical adapter.
- PR [#31](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/31): funding-specific,
  GitHub-safe pilot evidence with exact Landing/Parquet and predecessor-interval verification.
- PR [#32](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/32): receipt-verified,
  measured public funding pilot evidence and its sanitized acceptance assertions.
- PR [#33](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/33): fail-closed funding
  source-parity and stable observed-chronology audit.
- PR [#34](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/34): receipt-verified
  measured funding source-parity/chronology evidence.
- PR [#35](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/35): receipt-verified
  canonical funding registration and snapshot-bound single-type selection.
- PR [#36](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/36): measured,
  receipt-verified funding catalog registration/selection evidence and redaction assertions.
- PR [#37](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/37): receipt-verified
  trade/mark/funding evidence for controlled scale step 2 (10 instruments x 7 days).
- PR [#38](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/38): receipt-verified
  trade/mark/funding evidence for controlled scale step 3 (50 instruments x 90 days) and the
  ADR-0036 candle-audit schema-bound correction.

The funding path now includes `grid.canonical-funding-layout/v1`, exact signed Decimal128(38, 18),
minute-aligned settlement keys, settlement-derived interval semantics, month/eight-bucket
partitioning, ZSTD-3, receipt-last publication, and a separate public acquisition contract. Every
series captures a receipted predecessor, range pages are fixed and resumable, and saturated
200-row responses fail closed. The funding-specific sanitized evidence contract and builder now
verify exact Landing/Parquet equality and predecessor/internal interval derivation without
publishing rates or observed settlement timestamps. Funding registration/selection is implemented
against the same receipt-verified catalog with strict type isolation; funding-specific repair,
compaction, controlled scale evidence, and Gate 2 remain pending.

The receipt-verified measured funding result is
[`m2-public-funding-canonical-pilot-20260813.json`](../../benchmarks/results/m2-public-funding-canonical-pilot-20260813.json).
It used the public unauthenticated `GET /v5/market/funding/history` endpoint for BTCUSDT and
UNIUSDT over 2026-07-01 through 2026-07-07 inclusive. Two predecessor pages and two fixed range
pages completed in four HTTP attempts, with no application retry or accepted saturated response.
The requested windows total 20,160 minutes; the source returned 42 exact funding events, 21 per
instrument.

The Landing manifest is
`5c377afcbf8754a6a705676e718d2b4c797e1f4587f63c4faaaf4c13f005b620`, its predecessor aggregate
is `d39bfaa6abb377cc6553b5b55de4eabb7d5df91a373eb5c134945583424229de`, and the canonical
manifest is `55ccedfaa84e611ab704553843027b7054e389b7f4930239351a75406703e50f`.
The committed dataset contains 42 rows for two instruments in one 5,050-byte ZSTD-3 tail file and
is bound to publisher identity `git:cbe8391db0b9d5b9bdeb9ebae5af4035e570a7e2` (PR #30). The
evidence builder was merged as `44bf5233c93a3cc184de2675d6ed8a58cb74197c` (PR #31).

Exact Landing/Parquet table equality, every first predecessor-derived interval, every internal
interval, sorted unique keys, canonical receipt, content hash, and evidence receipt verify. No
rate, observed settlement timestamp, local path, host/account data, credential, private endpoint,
order, bot, or transfer is in GitHub. This proves only the bounded source return and immutable
publication; it does not prove complete funding chronology, lifecycle coverage, scale behavior,
or Gate 2.

`grid-data audit-funding-history` and `grid.canonical-funding-coverage-audit/v1` now provide the
funding-specific read-only boundary. They prove exact Landing/Parquet parity, predecessor and
internal interval derivation, range-page tiling, lifecycle bounds, and stable observed cadence.
Empty source windows and cadence changes are unaccepted blockers; current undated
`fundingInterval` is never historical evidence. The audit publishes counts, interval histograms,
transitive hashes, and a complete private-anomaly hash without rates or observed settlement
timestamps. Gate 2 remains closed.

The receipt-verified measured audit is
[`m2-canonical-funding-coverage-audit-20260813.json`](../../benchmarks/results/m2-canonical-funding-coverage-audit-20260813.json).
It ran with auditor merge identity `git:97bce032b351f95e11d78352b74fe5f2098f8834`
against publisher identity `git:cbe8391db0b9d5b9bdeb9ebae5af4035e570a7e2`. Exact
Landing/canonical equality passed for all 42 events and both 10,080-minute source windows. Each
series had one predecessor and one unsaturated range page, 21 events, and one stable observed
480-minute cadence. Empty windows, predecessor/internal mismatches, cadence changes, duplicates,
conflicts, unexpected/unrequested rows, and lifecycle failures were all zero; the complete
anomaly inventory was empty and hash-bound. No absence or cadence-change reason was accepted.
This establishes only the retained bounded Bybit source response, not an independent venue ledger,
complete funding history, scale behavior, or Gate 2.

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

## Repair execution and immutable replacement implementation

`grid-data execute-history-repair` re-verifies the complete plan chain and performs a whole-plan
resource preflight before running the existing fixed-page downloader sequentially for each gap.
Every task binds the embedded request, registry, capacity evidence, Landing plan/manifest, and full
executor Git identity. Exact returned coverage produces `passed`; an empty or partial repeated
observation is preserved as `blocked`.

`grid-data publish-history-repair` accepts only a passed execution, proves that parent plus repair
rows exactly cover all original requested minutes with no overlap/duplicate/unrequested key, and
publishes a deterministic receipt-last child dataset whose manifest names the old dataset as its
sole parent. The value-free replacement proof records both manifests and exact row accounting.
Positive, blocked, substitution, parent-immutability, and idempotent-rerun fixtures pass. The real
pilot has no genuine gap, so no synthetic result is represented as measured runtime evidence.

## Immutable compaction implementation

`grid-data compact` accepts one or more receipt-verified parents only when they form one exact
month/bucket partition. It rejects duplicate/conflicting keys instead of deduplicating them,
preflights estimated and actual memory/free-space bounds before mutation, and publishes a new
receipt-last child only when file count is reduced. Deterministic multi-file fixtures prove ordered
16 MiB target planning, one explicit final tail, logical input/output equality, complete parent
lineage, unchanged parents, idempotent rerun, insufficient-resource blocking, and substitution
detection. `grid.canonical-1m-compaction/v1` provides the value-free receipt-bound proof. A
representative measured runtime artifact is still required before Gate 2.

## Dataset catalog and reproducible selection implementation

`grid-data catalog-register` preflights and atomically registers only receipt-verified canonical
trade/mark 1m or funding datasets in a DuckDB metadata index. It binds complete parent lineage,
manifest/evidence/build/software hashes, file counts/hashes/key bounds, canonical month/bucket,
honest gap/conflict summary, and logical receipt/object identity. Funding reads the strict
`funding_time_ms` key while candles retain `open_time_ms`. Catalog state uses a monotonic revision
and canonical logical SHA-256 rather than unstable DuckDB file bytes; a lock, same-directory
building file, transaction, fsync, and atomic replace protect mutation. Identical registration is
idempotent.

`grid-data catalog-select` accepts a closed request containing the exact catalog revision/hash,
explicit dataset IDs, minute range, instrument filter, and consumer Git identity. It re-verifies
every selected manifest and file, rejects mutable-latest behavior, missing month/bucket partitions,
ancestor-plus-child inputs, mixed dataset types, and overlapping key ranges, and publishes
receipt-bound store-relative object keys. The result proves deterministic pruning, not historical
completeness. Runtime DuckDB and market data remain outside Git; schemas, tests, ADR-0030, and
sanitized evidence contracts are authoritative in GitHub. ADR-0035 records the backward-compatible
funding extension.

The receipt-verified representative run is
[`m2-canonical-catalog-registration-20260813.json`](../../benchmarks/results/m2-canonical-catalog-registration-20260813.json)
plus
[`m2-canonical-catalog-selection-20260813.json`](../../benchmarks/results/m2-canonical-catalog-selection-20260813.json).
It used implementation merge identity `git:15c58b2aeba7c605df4c59f80a124673bb9cc156`
and registered the existing two-instrument, 20,160-row pilot manifest
`2b9f6cce69be8bec260b1745c4380e2278bdfdd96d6d1438f79ce5c664269117`.
The resulting catalog is revision 1 with logical content SHA-256
`154c1e644466a44e93945473208823fda19ccf1f6ea39b0becd50636cc70c122`.
An exact request for instrument IDs 5 and 29 over 2026-07-01 through 2026-07-07 selected one
hash-bound object with a 20,160-row/481,048-byte inventory; request SHA-256 is
`da456e1b7569938326d1d350177bf0f7fc959a8a7f2d3177f4fed702947baec4`.
Identical registration and selection reruns retained revision/hash and re-verified their existing
evidence. No candle values, absolute paths, credentials, account data, or runtime DuckDB bytes are
in GitHub. This proves representative catalog/selection operation only, not full-history coverage.

The receipt-verified measured funding registration is
[`m2-canonical-funding-catalog-registration-20260813.json`](../../benchmarks/results/m2-canonical-funding-catalog-registration-20260813.json)
and its exact selection is
[`m2-canonical-funding-catalog-selection-20260813.json`](../../benchmarks/results/m2-canonical-funding-catalog-selection-20260813.json).
They use implementation merge identity `git:e3437d9a8d6f5a17cb5255504d289e2138692d4e`.
The existing catalog advanced from revision 1 to revision 2 with logical content SHA-256
`ee0fdb3f2d4261eaf41d56c402f31180bf515467cc37fb88399ea84d1a5acb62` and now contains the
receipt-verified candle and funding pilots. The exact BTC/UNI funding request selected one
42-row/5,050-byte hash-bound object; request SHA-256 is
`afff155e0a3b64cfc894ecc366e55134d13e284ae2ce3b036e4127a0af9ef9a7`. Identical
registration/selection reruns preserved revision/hash and verified the existing evidence. The
published chain is bound to the measured funding pilot and chronology manifest, but remains a
bounded two-series result and does not prove full-history lifecycle coverage, repair, compaction,
scale, or Gate 2.

## Controlled scale step 2: 10 instruments x 7 days

The second PM-owned scale step has been executed for one stable July 2026 month/bucket partition.
The exact public request specs are
[`trade`](../../benchmarks/specifications/m2-trade-10x7-history-request-20260813.json),
[`mark`](../../benchmarks/specifications/m2-mark-10x7-history-request-20260813.json), and
[`funding`](../../benchmarks/specifications/m2-funding-10x7-history-request-20260813.json).
They use the accepted maximum page sizes, 24 workers, and a measured 15-RPS profile. Every flow is
unauthenticated and calls only its public Bybit V5 market endpoint.

Trade and mark each completed 110 fixed pages/HTTP requests and produced 100,800 exact one-minute
rows: 10 instruments x 10,080 requested minutes. Their canonical pilots are
[`trade`](../../benchmarks/results/m2-public-trade-10x7-canonical-scale-20260813.json) and
[`mark`](../../benchmarks/results/m2-public-mark-10x7-canonical-scale-20260813.json); their
fail-closed audits are
[`trade`](../../benchmarks/results/m2-trade-10x7-coverage-audit-20260813.json) and
[`mark`](../../benchmarks/results/m2-mark-10x7-coverage-audit-20260813.json). Both prove exact
Landing/Parquet equality, complete requested-minute coverage, lifecycle fit, and zero missing,
duplicate, conflicting, unexpected, or unrequested keys.

Funding completed 10 predecessor plus 10 range requests in one attempt each and retained 231 exact
events. Nine series have a stable observed 480-minute cadence; IMXUSDT has a stable 240-minute
cadence. The
[`funding pilot`](../../benchmarks/results/m2-public-funding-10x7-canonical-scale-20260813.json)
and
[`funding chronology audit`](../../benchmarks/results/m2-funding-10x7-coverage-audit-20260813.json)
prove exact source/canonical equality, complete unsaturated range enumeration, and zero empty
windows, cadence changes, predecessor/internal interval mismatches, lifecycle failures,
duplicates, conflicts, unexpected timestamps, or unrequested events.

The three datasets were atomically added in
[`catalog revision 3`](../../benchmarks/results/m2-10x7-catalog-registration-20260813.json), whose
logical content SHA-256 is
`dcbc0e430e9b7aea72f7c7d9e7b2187644e191bf90ccfc096bed0ad7c43d686f`. Exact single-type
[`trade`](../../benchmarks/results/m2-trade-10x7-catalog-selection-20260813.json),
[`mark`](../../benchmarks/results/m2-mark-10x7-catalog-selection-20260813.json), and
[`funding`](../../benchmarks/results/m2-funding-10x7-catalog-selection-20260813.json) selections
each returned one receipt/hash-bound object. Registration and all selections were rerun
idempotently without changing revision or hash.

This closes only scale sequence step 2. It does not provide a historical universe timeline, a
genuine-gap repair run, multi-file target-size compaction, long-run throttling, the 50 x 90-day or
larger steps, or Gate 2 acceptance. Runtime Landing, Parquet, and DuckDB remain outside Git; the
request/evidence schemas, hashes, counts, receipts, tests, and limitations above are the GitHub
source of truth.

## Controlled scale step 3: 50 instruments x 90 days

The third PM-owned scale step ran over 2026-04-01 through 2026-06-29 inclusive, split into the
canonical April, May, and partial-June month partitions in stable bucket 5. Each request contains
the same 50 lifecycle-admitted USDT linear perpetuals. The GitHub-authoritative public specs are:

- trade
  [April](../../benchmarks/specifications/m2-trade-2026-04-50x90-history-request-20260813.json),
  [May](../../benchmarks/specifications/m2-trade-2026-05-50x90-history-request-20260813.json), and
  [June](../../benchmarks/specifications/m2-trade-2026-06-partial-50x90-history-request-20260813.json);
- mark
  [April](../../benchmarks/specifications/m2-mark-2026-04-50x90-history-request-20260813.json),
  [May](../../benchmarks/specifications/m2-mark-2026-05-50x90-history-request-20260813.json), and
  [June](../../benchmarks/specifications/m2-mark-2026-06-partial-50x90-history-request-20260813.json);
  and
- funding
  [April](../../benchmarks/specifications/m2-funding-2026-04-50x90-history-request-20260813.json),
  [May](../../benchmarks/specifications/m2-funding-2026-05-50x90-history-request-20260813.json), and
  [June](../../benchmarks/specifications/m2-funding-2026-06-partial-50x90-history-request-20260813.json).

All nine jobs use 24 workers and a per-job 15-RPS target. Candle page size is the accepted maximum
1,000 rows; funding uses 10,080-minute unsaturated range pages plus one predecessor per series.
The month-aligned canonical datasets contain 6,480,000 exact trade rows and 6,480,000 exact mark
rows. Their six receipt-verified audits are
[trade April](../../benchmarks/results/m2-trade-2026-04-50x90-coverage-audit-20260813.json),
[May](../../benchmarks/results/m2-trade-2026-05-50x90-coverage-audit-20260813.json),
[June](../../benchmarks/results/m2-trade-2026-06-partial-50x90-coverage-audit-20260813.json),
[mark April](../../benchmarks/results/m2-mark-2026-04-50x90-coverage-audit-20260813.json),
[May](../../benchmarks/results/m2-mark-2026-05-50x90-coverage-audit-20260813.json), and
[June](../../benchmarks/results/m2-mark-2026-06-partial-50x90-coverage-audit-20260813.json).
Every candle audit proves exact Landing/Parquet equality, complete requested-minute coverage,
lifecycle fit, and zero missing, duplicate, conflicting, unexpected, or unrequested keys.

Funding retained 21,421 exact events: 7,201 in April, 7,347 in May, and 6,873 in June. The
[May](../../benchmarks/results/m2-funding-2026-05-50x90-coverage-audit-20260813.json) and
[June](../../benchmarks/results/m2-funding-2026-06-partial-50x90-coverage-audit-20260813.json)
chronology audits pass with complete unsaturated enumeration and zero interval/key/lifecycle
blockers. The
[April audit](../../benchmarks/results/m2-funding-2026-04-50x90-coverage-audit-20260813.json)
correctly remains `blocked`: ONTUSDT and PIPPINUSDT contain four observed cadence transitions.
Exact source/canonical equality, boundaries, keys, and page coverage pass, but v1 accepts no
undated schedule-change reason. No current `fundingInterval` value was misused as historical
evidence and no PM/risk gate was weakened.

The nine immutable datasets were atomically added through
[catalog revision 4](../../benchmarks/results/m2-50x90-catalog-registration-20260813.json), with
14 total datasets/files and logical content SHA-256
`f7883c006fff2a8eaa5c897964fb69b1fbdd4a7f6baa00d8ce9b00293d6595bc`.
The exact 90-day [trade](../../benchmarks/results/m2-trade-50x90-catalog-selection-20260813.json),
[mark](../../benchmarks/results/m2-mark-50x90-catalog-selection-20260813.json), and
[funding](../../benchmarks/results/m2-funding-50x90-catalog-selection-20260813.json) selections
each returned three receipt/hash-bound month objects. Their selected inventories are 6,480,000,
6,480,000, and 21,421 rows respectively. Registration and all selections were rerun idempotently
without changing revision or hash.

ADR-0036 corrects the candle audit JSON Schema from the stale 16-series pilot limit to the existing
700-series request bound. The pilot evidence contract remains limited to 16 series; the scale run
was not relabelled as a pilot. Runtime Landing, Parquet, and DuckDB remain outside Git, while exact
specs, sanitized audit/catalog evidence, hashes, receipts, tests, and the unresolved funding
blocker are committed as the source of truth.

This closes scale sequence step 3 only. It does not provide a dated historical funding-schedule
source, an accepted cadence-change policy, a historical universe timeline, a genuine missing-candle
repair, measured multi-file compaction, the representative multi-year step, or Gate 2 acceptance.

## Still required before Gate 2

- historical lifecycle inventory beyond the current snapshot;
- measured coverage-audit evidence for the representative multi-year and full-history controlled
  scales;
- dated historical evidence or a separately owner-reviewed policy for the blocked April funding
  cadence transitions;
- measured repair execution/replacement evidence when a genuine gap is observed;
- measured multi-file compaction/target-attainment evidence at representative scale;
- long-run adaptive throttling evidence and controlled scale-up; and
- funding repair/compaction and the remaining PM-owned Gate 2 acceptance checklist.
