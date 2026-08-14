# M2 canonical market-data implementation status — 2026-08-12

**Status:** Phase 2 is active; the bounded public 1m Landing-to-canonical path is implemented and
verified. Gate 2 remains closed.

ADR-0076 adds a receipt-reverified, identifier-free public outcome for genuine candle-gap repair.
It makes a blocked source observation durable in GitHub without repeating the request, accepting
the missing candle, mutating the parent, or publishing an empty replacement.

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
- PR [#50](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/50): dated current
  Bybit linear-status inventory policy aligned with the normative V5 enum and strict
  response-partition validation.
- PR [#51](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/51): receipt-verified
  complete-current mainnet inventory evidence plus preserved cumulative partial-snapshot evidence.
- PR [#52](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/52): shared
  decrease-only public REST response-header throttling and resumable IP-ban abort behavior.
- PR [#53](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/53): receipt-bound
  child execution timing and strict GitHub-safe long-run adaptive-throttling qualification.
- PR [#54](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/54): measured
  transport-attempt versus HTTP-response accounting correction for strict qualification.
- PR [#55](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/55): receipt-verified
  100-instrument x 31-day public long-run throttling and resume evidence.
- PR [#56](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/56): receipt-verified
  100-instrument canonical publication plus preserved blocked funding-cadence audit evidence.
- PR [#57](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/57): ADR-0046
  receipt-integrity fast path for completed canonical campaign verification, with semantic
  admission retained for first publication and coverage audits.
- PR [#58](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/58): receipt-bound
  100-instrument x 31-day performance evidence for the ADR-0046 completed-publication verifier.
- PR [#59](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/59): ADR-0047
  single-snapshot input admission for full-history campaign preflight with unchanged child hashes
  and resource gates.
- PR [#60](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/60): schema-bound
  same-host qualification evidence for the ADR-0047 full-history campaign preflight.
- PR [#61](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/61): ADR-0048 bounded,
  receipt-resumable public funding source-boundary discovery with timestamp-only retention.
- PR [#62](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/62): ADR-0049 strict,
  GitHub-safe aggregate funding source-boundary evidence projection.
- PR [#63](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/63): receipt-verified,
  schema-bound measured five-instrument funding source-boundary evidence.
- PR [#64](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/64): receipt-bound
  quarantine for recognized invalid candle source rows without alternate-source substitution.
- PR [#65](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/65): sanitized aggregate
  source-quality evidence for candle-only campaigns containing quarantined source rows.
- PR [#66](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/66): exact
  receipt-verified funding source-boundary admission into full-history campaign children.
- PR [#67](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/67): quarantine-aware
  coverage classification and strict exclusion from ordinary same-source gap repair.
- PR [#68](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/68): exact immutable
  canonical funding compaction with cross-parent settlement-interval verification.
- PR [#69](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/69): fail-closed private
  funding repair discovery planning without cadence acceptance or market execution.
- PR [#70](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/70): bounded public
  funding repair discovery execution with exact candidate confirmation and private evidence.
- PR [#71](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/71): bounded retry
  classification for TLS record/read failures observed during the candle-only full-history resume.
- PR [#72](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/72): passed-only
  immutable funding repair publication and identifier/value-free execution evidence.

ADR-0048 now defines the fail-closed source-boundary discovery required after the first
five-instrument full-lifecycle execution reached a funding month with no registry-bounded
predecessor. The workflow scans only public funding history, commits timestamp-only page receipts,
validates but does not retain exact rates, and admits the second-oldest observed settlement only
after retaining the oldest as predecessor evidence. Its measured five-instrument result and
GitHub-safe aggregate projection remain pending a post-merge run; Gate 2 remains closed.

ADR-0049 defines that GitHub-safe projection. Its builder re-verifies the complete private
ADR-0048 receipt chain and requires classified response observations to cover every completed
page, then retains only aggregate counts, requested scan bounds, hashes, and immutable code
identities. The receipt-verified measured result is
[`m2-funding-source-boundary-5xfull-20260813.json`](../../benchmarks/results/m2-funding-source-boundary-5xfull-20260813.json).
It binds discovery merge `git:149fe395d0ae7efede2dc91bb60f12e70325bee7` and builder merge
`git:d05ff84dca929e7b40a6edc7c42224293b3ed5ec`. Five of five requested series have both
a source-observed predecessor and a second settlement admitted as the earliest canonical start.
The private runtime retained 37,286 timestamp-only events across 193 pages/HTTP attempts, with
zero retries, rate-limit events, rate reductions, cooldowns, invalid headers, or unclassified
completed responses. The GitHub artifact contains no symbol, instrument ID, per-series fact,
funding rate, observed settlement timestamp, runtime path, device/account data, credential, or
private endpoint result. This is source-boundary evidence only; source completeness, historical
cadence, canonical publication, and Gate 2 remain separate.

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

ADR-0042 resolves the false current-inventory part of that blocker prospectively. The current
normative Bybit V5 enum contains `PreLaunch`, `Trading`, `Delivering`, and `Closed`; it does not
contain the rejected `Settling` filter. New observations bind the dated
`bybit-v5-linear-status-enum-2026-08-13` policy, require every one of those four independently
paginated queries to succeed, and reject any row whose returned status differs from its requested
partition. Older partial artifacts remain immutable. The implementation and decision are tracked in
[PR #50](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/50).

The fresh mainnet observation built from merge identity
`git:c558a056337915ed83d9d3ce598d463f8af56cac` accepted all four policy queries:
`PreLaunch=5`, `Trading=815`, `Delivering=0`, and `Closed=937` across all linear products. It
contains 1,015 USDT linear perpetuals and is `complete`. The receipt-verified
[complete-current summary](../../benchmarks/results/m2-instrument-timeline-complete-current-20260813.json)
passes with 1,015 stable lifecycle IDs, 303 delivery-bounded and 712 open-ended instruments, zero
lifecycle conflicts, zero partial snapshots, and no blocker code.

The separate
[three-snapshot summary](../../benchmarks/results/m2-instrument-timeline-current-policy-20260813.json)
proves that evidence immutability was not weakened: its latest inventory is complete and its
lifecycle conflict count is zero, but it remains `blocked` because it includes the two earlier
partial snapshots. This is intentional negative-evidence preservation. The new observation
resolves the false complete-current blocker only; it does not reconstruct point-in-time metadata
before 2026-08-12, infer suspensions, or close Gate 2. Both measured summaries and their exact
contract/redaction assertions are tracked in
[PR #51](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/51).

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

The five-instrument candle-only full-history resume later exposed the corresponding TLS record
read boundary: Python raised `ssl.SSLError` for a bad-record-MAC/decryption failure after 853 of
978 child jobs had committed. Existing receipts remained reusable and no canonical data was
involved. TLS read failures are now classified through the same bounded `TransportError` path;
the acquisition layer still owns the fixed per-page attempt ceiling and non-retryable HTTP
responses remain immediate. The narrow transport correction is tracked in
[PR #71](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/71).

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
The measured artifact and its contract-level redaction assertions are tracked in
[PR #47](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/47).

ADR-0041 and `grid-data audit-history-campaign` now compose the unchanged ADR-0026 candle and
ADR-0034 funding audits over all 72 publication children. The read-only coordinator verifies
aggregate membership, runs one child at a time, retains detailed child payloads only in memory,
and publishes their content hashes plus aggregate per-kind quality and reason counts. Any child
blocker produces aggregate `blocked`; no gap, empty-window, lifecycle, or cadence reason is newly
accepted. Measured execution belongs in a subsequent evidence PR using the merged auditor identity.
The aggregate coordinator, schema, governance decision, and blocker-propagation tests are tracked
in [PR #48](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/48).

The receipt-verified representative aggregate audit completed all 72 children in 835.100 seconds
and returned `passed`: 24/24 trade, 24/24 mark, and 24/24 funding datasets passed with zero
blocked children. Candle quality proves 10,526,400 expected and observed minutes, exact
source/canonical equality for every child, and zero missing minutes, gap ranges, duplicates,
conflicts, lifecycle failures, unexpected timestamps, or unrequested rows. Funding quality proves
120 predecessor pages, 595 range pages, 10,965 events, and zero empty windows, cadence changes,
predecessor/internal interval mismatches, lifecycle failures, duplicates, unexpected timestamps,
or unrequested rows. No reason code was observed or accepted.

The [sanitized aggregate audit](../../benchmarks/results/m2-history-campaign-coverage-audit-20260813.json)
has artifact SHA-256
`98d6b6d36e9cbd94ac1e76e1061a38a42a04e7565ee4828b2cd436888ccb92c8`, content SHA-256
`b37ad854b2f447de1144e53c0f01741937c34c0cf868e2d43a8a9c9c40381d3f`, and auditor identity
`git:04296296916335797ba97716700103993a1bafdd`. Its 72 child content hashes bind the private
diagnostic results without publishing symbols, instrument/dataset identities, market values,
event timestamps, runtime paths, account data, or credentials. This closes representative
multi-year publication/coverage evidence only; it does not erase the separate April 50x90 funding
cadence blocker, prove a complete historical universe, or close Gate 2.
The measured aggregate audit and its exact contract assertions are tracked in
[PR #49](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/49).

This implementation contains no public or private Bybit client and cannot create an order, bot,
or transfer. A completed publication campaign still requires separate candle/funding coverage
audits and catalog registration. Measured publication of the 72-child representative runtime
campaign belongs in a subsequent evidence commit using the immutable merged publisher identity.

## Decrease-only public REST throttling

ADR-0043 extends the existing global child-job pacer without changing request identities, page
ownership, retry ceilings, source validation, or campaign serialization. Each thread-local public
transport exposes a sanitized `X-Bapi-Limit*` observation after its one HTTP attempt. Waiting
workers share one condition-based schedule, so a low-headroom or rate-limit response affects the
whole child before later launch slots are claimed.

The policy never increases configured RPS. Complete headers at or below 20% remaining capacity
cap effective RPS at 80% of the reported limit. HTTP 429 and retCode 10006 halve effective RPS and
apply the valid reset/one-second cooldown. HTTP 403 records Bybit's ten-minute resume boundary and
aborts all waiting work; verified pages and the immutable plan remain resumable. Missing or
invalid headers are counted, not treated as unlimited capacity.

New candle/funding Landing manifests include exact policy/rate/observation/reduction/cooldown
facts under optional backward-compatible `request_bound.adaptive_throttling`; all existing v1
receipts without the extension still verify. Tests prove low-headroom reduction, no recovery to a
higher rate, 403 abort after one application attempt, resumable plan preservation, malformed
summary rejection, and unchanged candle/funding schemas. A measured long-duration public run
under the merged implementation remains required before full-history scale. The implementation,
ADR, and fault-injection proof are tracked in
[PR #52](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/52).

ADR-0044 adds the evidence boundary needed for that measured run. New child manifests bind their
execution start while legacy v1 manifests remain valid. The campaign evidence builder aggregates
only re-verified child timing and adaptive summaries, and strict mode refuses publication unless
every child is timed and classified observations exactly cover the verified HTTP-attempt count.
The projection contains no response headers, request identities, symbols, market values, runtime
paths, host identity, credentials, or private endpoint results. Implementation and review are
tracked in [PR #53](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/53); measured
long-run evidence remains a subsequent PR and does not close Gate 2.

The first 100-instrument measured campaign exposed a strict-accounting error before evidence was
published: 9,600 completed pages used 9,621 transport attempts, with 21 retryable attempts that
produced no HTTP response. ADR-0045 requires an observation for every completed page response and
separately records attempts without a response; it does not invent absent headers for connection
or protocol failures. A client that returns a completed page without an observation still fails
closed. The correction and its tests are tracked in
[PR #54](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/54).

The corrected strict builder independently verified and published
[`m2-public-history-long-run-100x31-20260813.json`](../../benchmarks/results/m2-public-history-long-run-100x31-20260813.json).
It binds 100 instruments, all 31 days of July 2026, all eight buckets, and trade/mark/funding
public sources. The 24 receipt-committed child jobs contain 9,600 pages, 8,938,466 rows, and
591,702,449 Landing bytes. There were 9,621 bounded transport attempts: 9,600 completed page
responses were classified and 21 attempts produced no response before retry. All classified
responses had absent rate headers; malformed headers, rate-limit events, rate reductions,
cooldowns, and automatic increases were zero. The configured, minimum, and final rate remained
15 RPS.

Summed child execution time was 849,023 ms (14:09). Campaign wall span was 2,643,108 ms (44:03),
including two process/resume boundaries and their full receipt re-verification. The final strict
evidence pass required another measured 233.6 seconds. This qualifies the ADR-0043/0045 adaptive
accounting at this controlled scale and demonstrates deterministic resume, while also exposing
small-file re-verification as the next measured local optimization target. It is Landing evidence
only: canonical publication/audit, broader historical scale, Gate 2, and private/live permissions
remain unchanged. The result and exact contract assertions are tracked in
[PR #55](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/55).

The same completed Landing campaign was published under publisher identity
`git:eafb4b422e8467085122fb84ea7a4c983bee141d`. Its 24 immutable canonical datasets contain the
same 8,938,466 rows in 24 ZSTD-3 Parquet files totaling 114,867,201 bytes. Aggregate manifest SHA
is `46df7b00d0a4e42782e3a098676a8bffd46180089dde2521ba2994c257389152`.
No-mutation preflight took 473.9 seconds, publication including repeated preflight/final verify
took 1,185.2 seconds, and an idempotent replay took 707 seconds while proving 24 reused commits
and zero pending datasets. The GitHub-safe publication projection independently verified the
source/canonical chain in 230.7 seconds and is
[`m2-canonical-history-campaign-100x31-20260813.json`](../../benchmarks/results/m2-canonical-history-campaign-100x31-20260813.json).

The subsequent aggregate coverage audit is deliberately
[`blocked`](../../benchmarks/results/m2-history-campaign-coverage-audit-100x31-20260813.json).
All 16 candle datasets passed: 8,928,000 expected and observed minutes with zero missing minutes,
gaps, duplicate/conflicting keys, lifecycle failures, unexpected timestamps, or unrequested rows.
Five of eight funding datasets passed. Three remain blocked by seven
`unexplained_interval_change` observations; no reason is accepted. Funding otherwise has 10,466
events, 100 predecessor and 500 range pages, with zero empty pages, duplicate keys, interval
mismatches, lifecycle failures, unexpected timestamps, or unrequested rows. This is preserved
negative evidence: resolving it requires dated cadence evidence or a separately owner-reviewed
policy, not an implementation change to the accepted audit.
The canonical and audit artifacts plus exact assertions are tracked in
[PR #56](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/56).

ADR-0046 was merged as `git:10031a3e9603d031f7d806adc0d5fe20307d501e`. On the identical
100-instrument x 31-day source/publication chain, the receipt-integrity verifier hashed and
verified all 9,600 Landing page/receipt pairs, source child/aggregate lineage, and all 24 canonical
datasets without source-row decoding in 88,566 ms. The prior full semantic publication projection
took 230.7 seconds, so the completed-publication verification boundary is 2.60x faster (61.6%
less elapsed time) while retaining first-publication and coverage semantics. The new
[`integrity-fastpath evidence`](../../benchmarks/results/m2-canonical-history-campaign-100x31-integrity-fastpath-20260813.json)
contains the measured monotonic duration and mode, but no path, instrument identity, market value,
device/account data, credential, or new Gate 2 claim.

The first five-instrument full-lifecycle preflight (103 calendar months, trade/mark/funding)
resolved 1,467 children and 46,227 fixed pages in 125,600 ms under
`git:f14df8fe8eff4741ca7c488b97ad28704c1d1372`. ADR-0047 was merged as
`git:8bb04ef4e21b84c7a3461c95d95fba70e28888f2`; its same-host post-merge preflight used the
same scope, job/page inventory, 146,800,640-byte peak-memory bound, and 220,130,581,210-byte
free-space gate but completed in 3,284 ms. The
[`schema-bound performance evidence`](../../benchmarks/results/m2-history-campaign-preflight-performance-5xfull-20260813.json)
records a 38.246x speedup and 97.39% elapsed reduction while excluding paths, device identity,
instrument identities, market values, account data, credentials, and any Gate 2 implication.

The later five-instrument candle-only full-history resume exposed a different completed-child
cost: 927 of 978 children were already complete, yet the 2026-08-14 failed resume spent about
30.5 minutes before the first pending job returned HTTP 403 because completed Landing rows were
semantically decoded again during both planning and execution. The ADR-0046 resume implementation
now hashes and receipt-verifies each completed child during preflight and reuses that immutable
result only inside the same command. On the unchanged 978-job/43,328-page local campaign,
development preflight measured 72,018 ms and 70,399 ms in two runs; after the second preflight,
the executor traversed 927 verified children and reached a synthetic first-pending HTTP 403 in
1,257 ms with exactly one client call. These are pre-merge diagnostic measurements, not Gate 2
acceptance evidence; a schema-bound post-merge measurement remains required. The implementation,
regression proofs, and review are tracked in
[PR #74](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/74).

The post-merge run is now captured in the receipt-verified
[`grid.phase2-history-campaign-resume-performance/v1` evidence](../../benchmarks/results/m2-history-campaign-resume-performance-5xfull-20260814.json),
bound to merge identity `git:60363277432a2bdcfb8d2a23ea05060057eb3aaa`, the unchanged campaign
plan/request, registry, and capacity hashes. It reverified 927 completed children across the
978-job/43,328-page campaign, measured 72,762 ms for preflight, and reached a local synthetic
fail-closed HTTP 403 at the first pending page in another 1,283 ms with exactly one client call and
no network request. The remaining 51 jobs/2,271 pages are still pending; this qualifies the local
resume handoff only and does not prove coverage or close Gate 2. The evidence contract, ADR, and
review are tracked in [PR #75](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/75).

ADR-0055 adds funding repair discovery planning without changing ADR-0034 acceptance. A planner
re-verifies and recomputes a blocked audit, admits only a complete set of isolated integer-multiple
`C, N*C, C` interval sandwiches with no other blocker, and embeds bounded ordinary public funding
requests for the inferred candidate settlements. It does not execute those requests, use current
interval metadata, accept a candidate or schedule change, mutate canonical data, or publish exact
runtime identities to GitHub. Execution and immutable repair-child publication remain separate.
The implementation, exact contract, ADR, and synthetic failure proofs are tracked in
[PR #69](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/69).

ADR-0056 adds the separate execution boundary. It re-verifies every plan/upstream binding,
preflights all standard public funding jobs plus their aggregate remaining staging requirement,
then executes sequentially with ordinary page and completion receipts. Only exact equality between
source-returned timestamps and the complete candidate list passes; empty, partial, unexpected, or
invalid responses remain blocked. The rate-free record is private because it retains exact runtime
instrument/range identities. Parent publication, the blocked audit, cadence acceptance, and Gate 2
remain unchanged.
The execution implementation, contract, ADR, and synthetic exact/empty/resume proofs are tracked
in [PR #70](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/70).

ADR-0057 adds the passed-only immutable publication boundary and a separate sanitized execution
projection. Publication re-verifies the complete private chain, rejects parent overlap and
partition/schema mismatch, recomputes interval minutes over the exact parent-plus-source-confirmed
union, preserves the parent's first-event boundary evidence, and creates one receipt-last child
whose sole parent remains byte-identical. Its public proofs contain hashes and aggregate counts
but no instrument identity, settlement timestamp, funding rate, runtime path, account data, or
credential. The original blocked audit remains unchanged and a post-publication audit is still
required. The implementation and synthetic proofs are tracked in
[PR #72](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/72).

ADR-0058 adds the mandatory post-publication coverage boundary. It re-verifies the complete
private repair chain and immutable parent/child lineage, reconstructs the exact
original-plus-repair source union, and re-runs the unchanged ADR-0034 source-parity and chronology
rules. The receipt-last detailed result is private because it contains exact series identities and
observed time bounds. Read-only verification is independent of current free-space/memory write
gates. A synthetic repaired child passes with zero chronology blockers while the original blocked
audit remains byte-identical. Catalog transition, a public sanitized measured projection, and
Gate 2 acceptance remain separate. The implementation, ADR, schema, and synthetic proof are
tracked in [PR #73](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/73).

## Regional public-API failure classification

ADR-0060 corrects the operational interpretation of the measured CloudFront HTTP 403 returned at
the first pending full-history page. The public transport inspects at most 64 KiB only to classify
the combined CloudFront/block/country markers, discards the body, exposes no location or request
identity, and stops all child workers after one application attempt. The result is not counted as
a Bybit rate-limit event and does not invent ADR-0043's ten-minute IP-ban cooldown. Unrecognized
403 responses retain the existing fail-closed rate-limit behavior. No probe, alternate hostname,
private endpoint, retry, proxy, or bypass is added. The remaining 51 candle jobs therefore remain
blocked until an officially supported network and region can reach the public endpoint. Tests
cover the sanitized transport classification, unchanged genuine-403 cooldown, global pacer abort,
and one-attempt candle/funding resume preservation. The implementation, ADR, and fault-injection
proof are tracked in
[PR #76](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/76).

## Funding compaction candidate admission

ADR-0061 adds a bounded read-only audit before ADR-0054 compaction. It receipt-verifies every
canonical funding dataset, groups exact month/bucket partitions, and classifies every unordered
same-partition parent pair with the unchanged schema, duplicate-key, and cross-parent settlement
interval rules. Detailed dataset and partition identities remain in a receipt-last private audit;
the public contract exposes only audit/store hashes, implementation identities, inventory counts,
and aggregate classifications. The audit never deduplicates, subsets, splits, compacts, or mutates
a parent. The implementation, ADR, schema, and synthetic proofs are tracked in
[PR #77](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/77).

The post-merge audit under implementation identity
`git:b57e6b6c328ee7fa5db3812a2fe2b1b7753e07f6` reverified 37 canonical funding
datasets across 35 partitions. Exactly one partition had multiple parents, producing three
unordered pairs; all three were `duplicate-or-conflicting-keys`, while eligible, schema-mismatch,
and unresolved-interval counts were zero. The private receipt-last audit retains actionable
bindings outside Git. The public
[candidate evidence](../../benchmarks/results/m2-funding-compaction-candidate-audit-20260814.json)
binds that audit and exact store state without dataset/instrument/time/rate/path identities. No
network request or parent mutation occurred. This proves there is no genuine ADR-0054 input in the
bound current store; it does not qualify compaction and measured execution remains required when
an eligible incremental or repair fragment appears. The aggregate artifact, receipt, and strict
redaction/contract assertions are tracked in
[PR #78](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/78).

## Stale output fault-injection boundary

ADR-0062 adds a fully offline temporary-store runner for the unchanged Gate 2 stale-building
criterion. It invokes the production candle publication, funding publication, candle compaction,
and catalog registration preflights after injecting five deterministic building/lock markers.
Every case must raise the expected fail-closed error, preserve the marker byte-for-byte, and leave
the target dataset/catalog absent; any mismatch prevents evidence publication. Temporary fixtures
are removed, while the public contract retains only named boundaries, aggregate outcomes, and the
merged implementation identity. No retained market store, network request, private/live endpoint,
credential, account, order, bot, or transfer is involved. A post-merge measured artifact remains
required; implementation alone does not accept the Gate 2 criterion. The implementation, schema,
ADR, and offline contract tests are tracked in
[PR #79](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/79).

The post-merge runner was then executed against merge commit
`5ba281181e9c92da1aa30cd85dd520e888e11498`. The receipt-verified public result records five of
five stale markers detected, five of five markers preserved byte-for-byte, and zero target
mutations across the named production preflights. It also records that no network request or
private/live capability was used and that the temporary fixture was removed. The measured
[artifact](../../benchmarks/results/m2-stale-output-fault-injection-20260814.json) and
[receipt](../../benchmarks/results/m2-stale-output-fault-injection-20260814.json.receipt.json)
provide runtime evidence only for the unchanged stale-building-output criterion. They do not
accept the remainder of Gate 2. Publication and its pinned contract assertions are tracked in
[PR #80](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/80).

## Gate 2 readiness aggregation

ADR-0063 adds an offline, non-promoting readiness builder over the unchanged six Gate 2 criteria
and eight exact public Phase 2 evidence artifacts. It requires every input receipt, JSON Schema,
artifact SHA-256, embedded content SHA-256, expected contract/status, and the cross-source
100-instrument campaign lineage to verify before producing a result. The fixed v1 assessment
classifies no-mutation-before-preflight and stale-building detection as `evidence-ready`; the
remaining four criteria stay blocked by seven explicit full-history, repair, funding cadence,
lifecycle, and end-to-end performance blockers. `evidence-ready` is not acceptance. The builder
keeps Gate 2 closed, requires a data-quality-owner decision, disables automatic Phase 3
authorization, performs no network or market-store mutation, and returns exit code 2 for the
current blocked set. A post-merge receipt-verified pack remains required; implementation alone
does not change Gate 2 status. The implementation, ADR, schema, and fail-closed tests are tracked
in [PR #81](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/81).

The post-merge builder was executed against merge commit
`b58e03933096cc35cf4aa3d774147457f13e5e77`. All eight fixed source receipts, schemas,
artifact/content hashes, statuses, and cross-source bindings verified. The resulting
[readiness pack](../../benchmarks/results/m2-gate2-readiness-pack-20260814.json) and
[receipt](../../benchmarks/results/m2-gate2-readiness-pack-20260814.json.receipt.json) record two
of six criteria as `evidence-ready`, four as blocked, and seven unique blockers. Gate 2 remains
`closed-pending-data-quality-owner`; automatic Phase 3 authorization and automatic gate
acceptance are false. This is a reproducible negative readiness result, not a Gate 2 decision.
Publication and pinned contract assertions are tracked in
[PR #82](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/82).

## Canonical orphan and partial-write fault injection

ADR-0064 adds a fully offline temporary-store runner for canonical integrity failure detection.
It publishes minimal valid candle and funding fixtures, clones their immutable commits, then
injects an orphan file, a missing manifest-bound Parquet file, and a missing completion receipt
for each dataset type. All six cases invoke the real production verifier and must raise the exact
fail-closed error. A canonical fingerprint of every injected directory, file, size, and SHA-256
must remain identical before and after verification, proving that detection does not silently
clean or mutate diagnostic state. The retained market store, network, private/live endpoints,
credentials, account, order, bot, and transfer capabilities are absent. A post-merge measured
artifact remains required; implementation alone is not data-quality acceptance or Gate 2 closure.
The implementation, ADR, schema, and mutation-detection regression proof are tracked in
[PR #83](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/83).

The post-merge runner was then executed against merge commit
`d38ed8e618de9580623aba3de8b26f1ccd5d9c37`. The receipt-verified public result records six of
six faults detected and six of six complete injected filesystem states preserved during
verification. The measured
[artifact](../../benchmarks/results/m2-canonical-integrity-fault-injection-20260814.json) and
[receipt](../../benchmarks/results/m2-canonical-integrity-fault-injection-20260814.json.receipt.json)
contain no runtime path, dataset/instrument identity, or market value and record no retained-store,
network, private, or live access. This proves the named verifier behaviors only; it does not
authorize cleanup, repair, Gate 2 acceptance, or Phase 3. Publication and pinned contract
assertions are tracked in
[PR #84](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/84).

## Incremental catalog exact-key admission

ADR-0065 closes a functional gap in the documented immutable incremental workflow without
changing the external catalog/selection v1 schemas. The prior selector rejected every pair of
same-partition files whose first/last composite bounds overlapped. That was safe but incorrect
for ordinary multi-instrument daily fragments: earlier and later files can have disjoint exact
keys while both span the same instrument range.

The selector now retains the metadata-only path when bounds prove separation. Ambiguous candle
or funding partitions stream only their exact key columns in 4,096-row batches and merge at most
128 files at once. Any repeated exact key, internally unsorted file, or input above that bound
fails closed; the operator must compact an over-fragmented partition. Tests cover disjoint
two-instrument candle and funding fragments, duplicates across candle fragments, multi-batch
streaming, and the hard stream ceiling. No catalog/dataset mutation, network, credential,
private endpoint, or live capability is added. This enables bounded incremental selection but
does not prove coverage, accept Gate 2, or authorize Phase 3. The implementation, ADR, and
regression proofs are tracked in
[PR #85](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/85).

## Incremental catalog selection performance boundary

ADR-0066 adds an offline temporary-store benchmark for the ADR-0065 exact-key fallback. The
runner publishes bounded synthetic same-partition fragments through the production candle writer,
registers them through the production DuckDB catalog, requires ambiguous file bounds, and then
executes the identical exact snapshot-bound selection twice. A complete tree fingerprint before
and after both passes must remain equal, both selections must be identical and complete, and the
temporary fixture must be removed before evidence publication.

The default post-merge profile is 16 fragments x 32 instruments x 720 minutes, or 368,640 rows.
The schema exposes only aggregate configuration, durations, integer throughput, correctness
facts, hashes, immutable implementation identity, software versions, non-identifying CPU/RAM
facts, and explicit cache state. It excludes dataset/instrument identities, timestamps, paths,
market values, host/device/account identity, credentials, private endpoints, and live capability.
The receipt-bound 2026-08-14 post-merge artifact is bound to merge commit
`9b68150b740d9bd8988ed791c98dbd9bf4a90a72`. It measured 368,640 rows across 16 fragments and
32 instruments: 816,325,700 ns (451,584 rows/second) on the first pass and 804,938,400 ns
(457,972 rows/second) on the immediate repeat. Both passes selected the same 16 objects, all 15
ambiguous adjacent bounds exercised the exact-key fallback, and the complete store fingerprint
remained unchanged. This qualifies only the synthetic incremental boundary; full-history
end-to-end performance and Gate 2 remain blocked. The implementation and regression proofs are
tracked in
[PR #86](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/86); the immutable measured
artifact and receipt are tracked in
[PR #87](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/87).

## Zero-admission canonical candle publication

The full-history no-mutation publication preflight exposed a previously untested valid Landing
state: a child may contain no admitted candle rows because the endpoint returned no data or every
returned row is retained only in quarantine. ADR-0067 preserves the ADR-0039 one-to-one child
lineage by publishing an exact schema-only Parquet file with zero rows, zero instruments, null key
bounds, and the normal immutable audit/manifest/receipt chain. The generic logical-row builder
still rejects an unqualified empty input; only a semantically verified Landing request supplies
the deterministic month/bucket partition.

Coverage policy is unchanged. An empty canonical child remains exact source parity but its
requested minutes are missing, and a quarantined source row remains an unaccepted ADR-0053 reason.
The implementation does not accept a gap, register the child, close Gate 2, or authorize Phase 3.

## Canonical representation admission quarantine

The completed full-history candle campaign contains 30,832,408 Landing-admitted rows. A read-only
aggregate semantic scan found 74 trade rows whose exact volume scale exceeds the accepted
Decimal128(38, 4) physical contract; OHLC and turnover fit their accepted scales, and no
non-plain decimal was observed. The initial canonical preflight failed before mutation, so neither
Landing nor the canonical store was changed.

ADR-0068 preserves P-001 and immutable Landing. Canonical publication excludes only those exact
rows without rounding, binds aggregate admission counts and an exclusion hash into immutable
lineage, and reports the missing minutes as unaccepted
`canonical_representation_overflow`. Ordinary REST repair rejects that reason. This enables the
remaining independent children to proceed but does not accept the 74 minutes, close Gate 2, or
authorize Phase 3. Post-merge full-campaign publication and coverage evidence remain required.

## Receipt-bound publication startup and resume

The first full-history no-mutation publication preflight verified 978 jobs and 30,832,408 source
rows in about 30 minutes. The original `--execute` path then began repeating the same aggregate
semantic scan before any canonical mutation. It was stopped before plan or dataset publication.

ADR-0069 makes the complete semantic aggregate result an explicit receipt-bound checkpoint.
`--prepare-plan` writes only the deterministic plan/receipt after all children pass; a subsequent
`--execute --publication-root` verifies that frozen plan and starts per-child work without another
whole-campaign decode. Every pending child still undergoes the unchanged current semantic
preflight immediately before mutation; committed children are receipt/hash/audit-verified without
row decoding. All resource, receipt-last, immutable lineage, final source-integrity verification,
coverage, and Gate 2 constraints remain unchanged. Post-merge full-history prepared-plan and
execution measurements remain required. The implementation and regression proofs are tracked in
[PR #90](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/90), merged as
`85440ea1febfc9ada3b72c04a6b5f4e4b92ffebc`.

## Full-history Landing, canonical publication, and coverage evidence

The receipt-verified 2026-08-14 Landing projection covers five current linear symbols, two candle
kinds, 103 months, 978 jobs, and 43,328 retained pages from 2018-01-01 through the dated acquisition
cutoff. It records 30,832,408 admitted rows from 30,832,409 source rows, one quarantined source row,
43,424 transport attempts, 96 retries, and 1,994,193,097 retained artifact bytes. Response
classification is complete for observed responses, but only 43,246 of 43,328 completed pages carry
the current sanitized observation, so complete response-header coverage remains false. This is
Landing evidence only and does not accept missing venue history.

The full semantic plan was persisted through ADR-0069 and executed from its exact prepared root
using publisher merge `85440ea1febfc9ada3b72c04a6b5f4e4b92ffebc`; the legacy aggregate
preflight was not repeated. The completed aggregate receipt independently verifies 978 immutable
canonical datasets/files, 30,832,334 rows, and 529,794,759 Parquet bytes. Trade contributes 489
datasets and 15,413,811 rows; mark contributes 489 datasets and 15,418,523 rows. Exact canonical
admission excludes 74 trade rows solely for volume scale above Decimal128(38, 4), without rounding,
and binds those exclusions under ADR-0068. The sanitized publication projection reverified the
complete source/canonical integrity chain in 90,912 ms without source-row decoding.

The separate full semantic coverage audit remains fail closed: 696 datasets pass and 282 are
blocked. It observes 42,814,080 requested candle minutes, 30,832,334 canonical rows, 11,981,746
missing minutes across 353 gap ranges, zero duplicate/conflicting keys, zero unexpected or
unrequested timestamps, and zero lifecycle failures. The missing-minute reasons reconcile exactly
to 11,981,671 `rest_returned_no_data`, 74 `canonical_representation_overflow`, and one
`quarantined_source_row`; unknown reason count is zero. No reason is accepted. These artifacts
prove immutable publication and quantify the remaining data-quality blockers; they do not close
Gate 2, repair history, register datasets, or authorize Phase 3.

ADR-0070, merged through
[PR #92](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/92) as
`060ba5fe2a6c2de2f99c8135bae1a73647dc0a2a`, adds a receipt-bound follow-up diagnostic for this
already-proven candle coverage. The post-merge
[sanitized diagnostic](../../benchmarks/results/m2-candle-boundary-diagnostic-20260814.json)
reused all 978 canonical objects returned by the aggregate verifier and scanned 30,832,334
instrument/time keys once in 203,043 ms, without a public download or Landing semantic decode. It
reconciles the 353 child-local gap ranges into 10 leading ranges containing 11,981,670 minutes and
75 internal ranges containing 76 minutes; there are zero trailing and zero fully absent ranges.
All ten leading ranges belong to series whose requested start was clipped to the current registry
launch boundary. The sanitized result remains bound to the unchanged blocked ADR-0041 audit:
current launch metadata and first returned data do not prove historical listing time, so no minute
or reason is accepted.

## Official announcement archive-depth evidence

ADR-0071 through ADR-0074 add a bounded official Bybit announcement-depth diagnostic. The final
contract reflects the source behavior observed during fail-closed post-merge runs: pages are not
universally date-ordered across all announcement types, and legacy rows may omit the newer
`publishTime`. Source order is never rewritten; `publishTime` is never synthesized; inversion and
field-presence counts remain explicit. Strict first/declared-last date ordering applies only to
the lifecycle-relevant `new_crypto` and `delistings` partitions.

The receipt-verified 2026-08-14 artifact used 15 one-attempt public responses for all eight types
(one type reused its single page), retained no announcement body, and bound implementation merge
`777f3c8745da3b83125f9178734538d700a0accd`. All five selected current-registry launch bounds are
earlier than the official `new_crypto` declared-last-page minimum `1654063851000` (June 2022); the
corresponding `delistings` bound is `1660194000000`. Seven last pages have no `publishTime`, and
one non-lifecycle `latest_activities` first page exposes one date inversion. The result is
`blocked-insufficient-official-announcement-history`: it proves that this bounded official API
view cannot supply the required legacy lifecycle evidence, not that any missing candle is
accepted.

Implementation and observed-source compatibility are tracked in
[PR #94](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/94),
[PR #95](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/95),
[PR #96](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/96), and
[PR #97](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/97). The immutable
measured artifact and receipt are tracked in
[PR #98](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/98).

## Current Gate 2 readiness successor

ADR-0075 adds `grid.gate2-readiness-pack/v2` instead of modifying the immutable v1 result. The
offline builder verifies twelve exact GitHub evidence artifacts and their campaign, publication,
coverage, boundary, registry, and announcement bindings. It performs no Bybit request, retained
market-store read, publication, audit, or benchmark rerun.

The successor removes only the obsolete claims that the representative candle campaign and its
canonical publication/audit are missing. Preflight-before-mutation, duplicate/conflicting-key
freedom, and stale-output detection are evidence-ready. Deterministic repair, lifecycle coverage,
and performance remain blocked by seven explicit current evidence/policy codes. Gate 2 remains
closed, data-quality-owner review remains mandatory, and Phase 3 authorization remains false.

The receipt-verified 2026-08-14
[v2 readiness artifact](../../benchmarks/results/m2-gate2-readiness-pack-v2-20260814.json) is bound
to implementation merge `847de3e43c0c8411c609eca5f65a279adc42dcbe`. Its twelve exact source
chains verify, the artifact SHA-256 is
`d28041effc793e2a5c7daf81b3a1f5ae5035804ca342a2efe21632383ffbcc52`, and the embedded canonical
content SHA-256 is `306e7aadf51fa8591b62858a45c23152c117ddcdfb7d0990502e796393e89e46`.
It is the current GitHub readiness result and remains a reproducible negative gate result, not a
Gate 2 decision.

## Genuine candle-gap repair outcome

ADR-0076 was merged through
[PR #101](https://github.com/brullik/brullik-bybit-grid-bot-research/pull/101) as
`ad27ab26044a842059f8679d6ccaf9c078225d85`. The bounded private workflow isolated one genuine
internal `rest_returned_no_data` minute, admitted one task with at most three attempts, and made
one public request. Bybit returned zero rows, so the immutable execution is `blocked`; the parent
was not mutated and replacement publication was not eligible.

The receipt-verified
[sanitized outcome](../../benchmarks/results/m2-candle-gap-repair-execution-20260814.json) contains
no market identity, timestamp, value, path, account data, or credential. Its artifact SHA-256 is
`f7d3efd6bab544c02ab63171040d99c364c94531c7e9fc08f31776f820d42cd5` and embedded content
SHA-256 is `fb71a2e26afb3b209fda7d44d0d5e1de080e99eb998b8cc33491bf8d9811cea8`.

## Funding repair candidate admission

ADR-0077 adds one bounded offline audit over explicit receipt-verified blocked funding audits. It
replays the unchanged ADR-0055 production planner and records whether each input has a complete
isolated integer-multiple cadence sandwich before any public request. The detailed output remains
private; its public contract exposes only binding hashes and aggregate counts.

This is a no-repeat diagnostic, not Gate 2 acceptance. It makes no Bybit request, accepts no
settlement or cadence, changes no parent, and does not replace the required measured funding
repair workflow when a genuine eligible candidate exists.

## Still required before Gate 2

- broader dated lifecycle evidence covering representative historical decision periods; the
  timeline begins on 2026-08-12 and does not reconstruct earlier point-in-time metadata, while
  ADR-0071 through ADR-0074 prove that the official announcements API's declared last pages begin
  only in 2022 for the required lifecycle partitions;
- owner-reviewed lifecycle evidence/policy for 11,981,671 historical `rest_returned_no_data`
  minutes across the current-universe bootstrap; ADR-0070 now proves aggregate topology but does
  not turn first returned data into listing metadata, and 74 canonical representation overflows
  plus one quarantined source row remain unaccepted;
- dated historical evidence or a separately owner-reviewed policy for the blocked April funding
  cadence transitions;
- measured repair execution/replacement evidence when a genuine gap is observed;
- further controlled scale-up and dated evidence/policy for the seven blocked July funding
  cadence transitions; and
- measured funding repair publication/execution evidence when a genuine candidate exists,
  measured ADR-0054 funding-compaction execution when a genuine eligible pair appears (the current
  receipt-bound store has none), and the remaining PM-owned Gate 2 acceptance checklist;
  implementation alone is not measured acceptance.
