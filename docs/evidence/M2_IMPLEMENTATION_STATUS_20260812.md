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

The funding path now includes `grid.canonical-funding-layout/v1`, exact signed Decimal128(38, 18),
minute-aligned settlement keys, settlement-derived interval semantics, month/eight-bucket
partitioning, ZSTD-3, receipt-last publication, and a separate public acquisition contract. Every
series captures a receipted predecessor, range pages are fixed and resumable, and saturated
200-row responses fail closed. A measured funding pilot, funding-specific coverage/repair,
compaction, and catalog evidence remain pending; Gate 2 is not accepted.

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
candle datasets in a DuckDB metadata index. It binds complete parent lineage, manifest/evidence/
build/software hashes, file counts/hashes/key bounds, canonical month/bucket, honest gap/conflict
summary, and logical receipt/object identity. Catalog state uses a monotonic revision and canonical
logical SHA-256 rather than unstable DuckDB file bytes; a lock, same-directory building file,
transaction, fsync, and atomic replace protect mutation. Identical registration is idempotent.

`grid-data catalog-select` accepts a closed request containing the exact catalog revision/hash,
explicit dataset IDs, minute range, instrument filter, and consumer Git identity. It re-verifies
every selected manifest and file, rejects mutable-latest behavior, missing month/bucket partitions,
ancestor-plus-child inputs, and overlapping key ranges, and publishes receipt-bound store-relative
object keys. The result proves deterministic pruning, not historical completeness. Runtime DuckDB
and market data remain outside Git; schemas, tests, ADR-0030, and sanitized evidence contracts are
authoritative in GitHub.

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

## Still required before Gate 2

- historical lifecycle inventory beyond the current snapshot;
- measured coverage-audit evidence at each controlled scale and an owner-reviewed reason policy;
- measured repair execution/replacement evidence when a genuine gap is observed;
- measured multi-file compaction/target-attainment evidence at representative scale;
- long-run adaptive throttling evidence and controlled scale-up; and
- funding ingestion plus the remaining PM-owned Gate 2 acceptance checklist.
