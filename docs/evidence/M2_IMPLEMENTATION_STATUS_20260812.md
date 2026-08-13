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
- PR [#39](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/39): receipt-verified
  measured multi-parent April trade compaction with target-band and immutable-lineage evidence.
- PR [#40](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/40): immutable
  point-in-time instrument timeline with separate ex-post lifecycle coverage and sanitized
  partial-inventory evidence.
- PR [#41](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/41): receipt-resumable
  multi-month public history campaigns with aggregate preflight and deterministic child reuse.
- PR [#42](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/42): bounded retry
  classification for direct stdlib connection/protocol failures observed by the real campaign.
- PR [#43](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/43): receipt-verified,
  GitHub-safe measured evidence for the completed 5-instrument, 24-month Landing campaign.
- PR [#44](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/44): receipt-resumable,
  sequential canonical publication of every completed campaign child with aggregate verification.

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
source, an accepted cadence-change policy, a genuine missing-candle repair, the representative
multi-year step, or Gate 2 acceptance.

## Measured multi-file compaction

Representative trade compaction has now been executed on the same 50-instrument April scope as
scale step 3. Five non-overlapping 10-instrument public requests are committed as
[g01](../../benchmarks/specifications/m2-trade-april-compaction-g01-history-request-20260813.json),
[g02](../../benchmarks/specifications/m2-trade-april-compaction-g02-history-request-20260813.json),
[g03](../../benchmarks/specifications/m2-trade-april-compaction-g03-history-request-20260813.json),
[g04](../../benchmarks/specifications/m2-trade-april-compaction-g04-history-request-20260813.json),
and
[g05](../../benchmarks/specifications/m2-trade-april-compaction-g05-history-request-20260813.json).
Each independently acquired and published parent contains 432,000 exact requested minutes in one
canonical file. Their receipt-verified sanitized summaries are
[g01](../../benchmarks/results/m2-public-trade-april-compaction-g01-20260813.json),
[g02](../../benchmarks/results/m2-public-trade-april-compaction-g02-20260813.json),
[g03](../../benchmarks/results/m2-public-trade-april-compaction-g03-20260813.json),
[g04](../../benchmarks/results/m2-public-trade-april-compaction-g04-20260813.json), and
[g05](../../benchmarks/results/m2-public-trade-april-compaction-g05-20260813.json). Together they
cover 50 disjoint instruments and 2,160,000 rows.

The
[measured compaction evidence](../../benchmarks/results/m2-trade-april-50x90-compaction-20260813.json)
binds every parent manifest and the compacted child manifest. The accepted ZSTD-3 calibration
selected 1,024,000 rows per target file. Five input files became three output files: two non-tail
`target-band` files measured 18,673,836 and 18,343,136 bytes, followed by one explicit
1,531,918-byte/112,000-row tail. Total output is 38,548,890 bytes for 2,160,000 rows. Input and
output logical table SHA-256 are both
`c1c9d6b26bf5313d581a4d1e0a9aa39fdde90a95ba3cc4d7bf84d598ee4d24fc`; duplicate and conflict
counts are zero. All five parents re-verified byte-identically after publication,
`parent_datasets_mutated=false`, and the reordered-parent rerun preserved the same child manifest
`60fac7b0867d6e13900bdad99a6b51aa19594f875ea7cecd4e095619f6af601b`.

The successful transition is bound to the accepted capacity evidence and passed the mandatory
fresh same-host admission on the current laptop. This proves that the measured month/bucket unit
and 16 MiB target operate within the evidence-based laptop policy; it is not permission to bypass
fresh admission on later partitions. Parents and child remain outside Git, while requests,
sanitized summaries, exact hashes, counts, target classifications, receipts, tests, and
limitations are the source of truth. Compaction did not update the catalog, delete parents,
accept a gap reason, or close Gate 2.

## Point-in-time instrument timeline

ADR-0037 and `grid.instrument-timeline/v1` now separate research-safe point-in-time metadata from
ex-post lifecycle coverage. The research selector returns only the latest registry snapshot whose
observation time is not later than the decision time; a request before the first snapshot fails,
and later delivery/status/tick-size fields are not exposed. Ex-post launch/delivery bounds are
available only to data-quality review. Conflicting launch/non-null-delivery values, closed records
without delivery time, non-positive lifecycles, and symbol reuse remain blockers.

The first measured timeline combines the receipt-verified 2026-08-12 registry artifact SHA-256
`4024ded8a34718e6658dcddd34b290f757b030e6c34b07401568b8aeadae910d` with a fresh 2026-08-13
registry artifact SHA-256
`a351fd4a28e143b84ca7bc1f3449601f4f07904bd9c0dda1d31a9dfd9e3e3c88`. The runtime timeline
artifact SHA-256 is
`8f595d182f333c6173a899aa0e29ae8fd412af3e55cbac8ecd325224d45b1cf9`; its full rows remain
outside Git. The receipt-verified
[sanitized summary](../../benchmarks/results/m2-instrument-timeline-20260813.json) binds those
hashes and implementation commit `f532ce8aa1ce025218d685035e7f8270f3f5d41c`.

Across the two snapshots, stable lifecycle coverage contains 1,015 USDT linear perpetual IDs,
303 delivery-bounded and 712 open-ended, with zero lifecycle-conflicted instruments and no
identity conflict. The latest snapshot contains 303 `Closed`, five `PreLaunch`, and 707 `Trading`
eligible records. A real as-of selection returns 1,010 IDs at the first timestamp and 1,015 at the
second, proving that later additions do not appear retroactively.

The summary deliberately remains `blocked` with `partial_source_inventory`: Bybit accepted
`Trading`, `PreLaunch`, `Delivering`, and `Closed` status queries but rejected `Settling` with
retCode 10001. Strict selection with `require_complete_inventory=true` therefore fails. No missing
status was inferred, no archive absence was treated as delisting, and no public-trade archive body
or tick row was downloaded. Two recent snapshots establish the append-only mechanism and current
lifecycle consistency; they do not provide point-in-time metadata for decisions before
2026-08-12 or close Gate 2.

## Resumable multi-year campaign implementation

ADR-0038 and `grid-data history-campaign` now turn one bounded request into deterministic
trade/mark/funding children grouped by UTC month and `instrument_id mod 8`. Campaign preflight
verifies the registry and capacity evidence, preflights every child without mutation, and admits
the run only when fresh free space covers active-plus-building, the operating reserve, and the
conservative remaining Landing bound for all incomplete children. Children execute sequentially,
so their independent pacers cannot multiply the configured rate.

The committed next-step
[request](../../benchmarks/specifications/m2-representative-5x24-history-campaign-request-20260813.json)
selects five long-lived, varied bucket-5 instruments over all of 2024-2025: 1,052,640 requested
minutes per instrument and each candle family. A fresh no-mutation preflight on the current laptop
resolved 72 child jobs and 11,365 public pages, with a 146,800,640-byte peak-memory bound and a
109,094,771,418-byte aggregate free-space requirement. It passed the evidence-based NVMe, memory,
and free-space gates. The deterministic campaign plan SHA-256 is
`ab32162397e396975071ee3a64cdc372b58938c3f1865439b9e93501611d8f4e`; the request SHA-256 is
`2c93143e6cec6bf402994cb23dac98ff25bffd3b8319e19de029f5ec378fc120`. This is planning evidence
only: no campaign directory or public request was created by that preflight.

The plan is receipt-committed before child mutation. A rerun reuses every verified page and
completed child; the aggregate manifest receipt is written last only after every child manifest,
plan hash, request hash, relative root, allowlist, and page/row/HTTP total verifies. The request is
limited to 700 symbols and 120 calendar months and derives exact per-child HTTP ceilings. It uses
only unauthenticated public kline, mark-price-kline, and funding-history endpoints and explicitly
records that tick rows were not requested.

`registry-lifecycle-intersection-v1` clips source acquisition to current receipt-verified
launch/delivery evidence. That is an ex-post data-quality bound, not historical point-in-time
strategy truth. The implementation does not publish canonical datasets, accept a gap/cadence
reason, repair or compact data, update the catalog, or close Gate 2. A measured representative
multi-year campaign remains the next controlled-scale evidence step.

The first execution attempt completed 51 of 72 child jobs before Bybit closed one HTTPS
connection without a response during the June 2025 trade child. The aggregate receipt was not
written, completed children and page receipts were preserved, and no stale run lock remained.
That negative evidence exposed a narrow stdlib boundary: `RemoteDisconnected` escaped the
transport wrapper and therefore did not consume the child's explicit application retry. The
transport now wraps direct connection/protocol failures as retryable `TransportError` values;
bounded fault-injection tests cover disconnect-then-success, exhausted disconnect/reset, and the
unchanged immediate failure for non-retryable HTTP responses. The unchanged campaign can resume
without refetching its verified children.

The resumed execution completed all 72 children and the independent no-network verifier passed.
The aggregate contains 11,365 pages, 10,537,365 returned rows, and 11,367 recorded HTTP attempts,
so the entire run required two explicit retries. The completed manifest SHA-256 is
`cef361cb5eb04cee9f2c645a5281b06f50b050eaaf327c58d170b725f558485a`. Runtime campaign files
measure 693,425,484 bytes and remain under ignored `data/` storage. A separate schema-bound
summary publishes only those safe aggregate facts and transitive hashes; no price, volume,
funding rate, symbol/instrument identity, path, host/account data, or credential enters Git.
The receipt-verified
[sanitized evidence](../../benchmarks/results/m2-public-history-campaign-5x24-20260813.json)
has artifact SHA-256
`9bc405aece11e2e7f312600b2ef4533155f6656cf08c728dd7c8bbd49a2a1ebe`, content SHA-256
`ea2074b1449a1baea1e0eb78697e908aa8f3a34ca180b9c9ed5717072a9e7b5e`, and binds evidence
builder identity `git:2089d77820078b72d1dd5c405b2a91f51d2b9034`. Trade and mark each contain
5,263,200 rows over 5,325 pages and 5,326 HTTP attempts; funding contains 10,965 events over 715
predecessor/range pages and 715 attempts.

## Resumable canonical campaign publication implementation

ADR-0039 and `grid-data publish-history-campaign` compose the existing verified candle and
funding publication boundaries over a completed ADR-0038 campaign. Aggregate preflight resolves
each child one at a time, freezes the source manifest, exact Arrow input hash, canonical request,
deterministic dataset identity, publisher Git identity, and writer resource bound, then releases
the batch before examining the next child. It performs no mutation by default.

Execution writes the aggregate plan receipt before the first child, invokes only one canonical
writer at a time, and uses each canonical completion receipt as its resume marker. The aggregate
free-space requirement is the maximum child requirement rather than a false sum of 72 identical
active-plus-building/operating reserves. Every child still receives a fresh preflight and the
existing second host check before mutation. The aggregate completion receipt is written last only
after every source job, canonical audit/file/manifest/receipt, and total verifies. Fault-injection
tests cover interruption after a committed child, receipt-based resume without rewrite, complete
idempotency, resource failure before mutation, source substitution, and outer/canonical tampering.

The first no-mutation run over the representative 72-child campaign exposed redundant work rather
than a host-capacity failure: the initial implementation did not finish within the 900-second
diagnostic limit because aggregate verification, publication preparation, and batch loading each
decoded the same receipt-verified pages again. The typed verified-child handoff now performs one
page pass per child during aggregate preflight while retaining all artifact digests, manifests,
receipts, range/boundary checks, and source-plan bindings. A repeated no-mutation preflight over
10,537,365 rows completed successfully in 544.333 seconds on 2026-08-13. No publication campaign,
canonical dataset, exchange request, order, bot, or transfer was created by either diagnostic run.
The implementation and its regression proof are tracked in
[PR #45](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/45).

ADR-0040 adds a separate GitHub-safe evidence transition for the completed aggregate publication.
The builder re-verifies the original campaign plus every canonical Parquet file, audit, manifest,
and receipt, then projects only aggregate/per-kind counts and bytes, maximum sequential-child
resource bounds, immutable publisher/builder identities, and transitive hashes. Its exact schema
forbids runtime paths, dataset/symbol/instrument identities, market values, account data, and
credentials. The measured evidence artifact must be generated only after this builder is merged,
using that immutable merge commit as the evidence-builder identity.
The builder contract and redaction tests are tracked in
[PR #46](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/46).

The representative publication completed all 72 immutable datasets (24 trade, 24 mark, and 24
funding) from 10,537,365 verified source rows. It produced 72 Parquet files totaling 187,352,531
bytes: 119,694,112 trade bytes, 67,476,126 mark bytes, and 182,293 funding bytes. The aggregate
publication manifest SHA-256 is
`0a5f8b24fd5cfd11d790528dde808fd23c3264100fe25243ec0615d56eeb281d`; the plan SHA-256 is
`a127ee5abb5dd74e7be033b60fea5a5140403212b35b8dec53f7a916ae9aae1f`. The measured maximum
single-child bounds were 199,020,064 planned peak-memory bytes and 98,858,563,994 required free
bytes. Independent aggregate verification returned valid, and an execute replay found 72 existing
commits, zero pending datasets, and left the aggregate completion receipt timestamp unchanged.

The receipt-verified
[sanitized canonical evidence](../../benchmarks/results/m2-canonical-history-campaign-5x24-20260813.json)
has artifact SHA-256
`c4ced7244633c62a574b23262a95f8b3705da3ff474f0c2e69e20ea618df3547`, content SHA-256
`e7355d29615fbbd1c62d1342989001c9ba622b52fae756ca7e4e01d685914085`, binds publisher identity
`git:9887c9d5d4aec51966495e6618ffa67909d59743` and evidence-builder identity
`git:c6c5c8a29de4628647c1562164522efb9604e64e`, and contains no runtime path, market value,
instrument/dataset identity, account data, or credential.

This implementation contains no public or private Bybit client and cannot create an order, bot,
or transfer. A completed publication campaign still requires separate candle/funding coverage
audits and catalog registration. Measured publication of the 72-child representative runtime
campaign belongs in a subsequent evidence commit using the immutable merged publisher identity.

## Still required before Gate 2

- broader dated lifecycle evidence covering representative historical decision periods and a
  resolution for the partial source inventory; the current timeline begins on 2026-08-12;
- canonical publication and coverage-audit evidence for the representative multi-year and
  full-history controlled scales;
- dated historical evidence or a separately owner-reviewed policy for the blocked April funding
  cadence transitions;
- measured repair execution/replacement evidence when a genuine gap is observed;
- long-run adaptive throttling evidence and controlled scale-up; and
- funding repair/compaction and the remaining PM-owned Gate 2 acceptance checklist.
