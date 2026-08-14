# Data and State Contracts

## Contract principles

Every persisted dataset or runtime record has:

- explicit schema and semantic version;
- stable identity and primary key;
- UTC timestamp semantics;
- numeric units and null policy;
- parent/provenance identity;
- canonical serialization or column representation;
- validation rules;
- lifecycle status and commit marker where applicable;
- migration/compatibility policy.

A matching column name is not sufficient: units, boundary rules, source category, and meaning are part of the contract.

## Instrument snapshot

Primary identity:

```text
(snapshot_time, category, instrument_id)
```

Required concepts:

- stable internal `instrument_id`;
- exchange symbol;
- category, base, quote, settle coin;
- contract type and status;
- launch/delivery/delisting times;
- tick size and price scale;
- quantity step and min/max order quantity;
- min/max leverage;
- funding interval when applicable;
- pre-listing/innovation flags where available;
- source payload hash and snapshot metadata.

Symbol strings are attributes, not the only durable identity.

`grid.instrument-registry/v1` binds one receipted Bybit linear inventory snapshot to
`bybit-linear-source-symbol-id-v1`. In this namespace the positive UInt32 `source_symbol_id` is
the internal `instrument_id`; rows are sorted and unique by that ID. The registry records exact
decimal metadata and maps source zero delivery/funding sentinels to null. This is a
dated snapshot, not permission to apply current status to past decisions.

New public inventories bind `bybit-v5-linear-status-enum-2026-08-13` and independently enumerate
the current normative `PreLaunch`, `Trading`, `Delivering`, and `Closed` partitions. Complete means
all four queries succeeded and every returned row matched its requested partition. It is
complete-current endpoint evidence, not historical point-in-time completeness. Older partial
artifacts remain immutable; see ADR-0042.

## Instrument timeline and lifecycle coverage

`grid.instrument-timeline/v1` aggregates one or more receipt-verified instrument registries in
strict source-observation order. Every snapshot retains its complete exact rows and source
artifact/content hashes under the same stable identity algorithm. Duplicate observation times,
unstable identities, malformed ordering, and substituted receipts fail closed.

The point-in-time selector returns only the latest snapshot with
`snapshot_time_ms <= decision_time_ms`. It fails before the first snapshot and may require the
selected source inventory to be complete. Later snapshot rows are not returned, so later status,
tick/quantity constraints, leverage, funding interval, and delivery knowledge cannot enter an
earlier decision.

A separate ex-post lifecycle view compares launch and non-null delivery fields across observations
for canonical data-quality accounting. Its boundaries are explicitly `ex-post-data-quality-only`:
they may explain expected history start/end but are not research features. Conflicting bounds,
closed-without-delivery records, non-positive intervals, symbol reuse, partial inventories,
suspensions, and source omissions remain blockers rather than inferred facts.

`grid.instrument-timeline-summary/v1` is a GitHub-safe hash/count projection of the runtime
timeline. It contains no instrument rows, local paths, market values, account data, or credentials
and does not close Gate 2. See ADR-0037.

## Public 1m acquisition request and Landing batch

`grid.bybit-1m-history-request/v1` contains:

- a safe job ID and exactly one kind (`trade` or `mark`);
- symbol plus inclusive minute-aligned start/end for each series;
- page, worker, global pacing, retry, and whole-run request bounds.

The request cannot contain an instrument ID. A verified registry supplies that identity, and a
verified Gate 1 capacity artifact supplies active-plus-building bytes. Every resolved job is one
dataset/month/eight-bucket partition and includes only closed candles.

`grid.bybit-1m-history-plan/v1` binds the canonical request hash, resolved request,
registry/capacity artifact hashes,
capacity budget, and deterministic pages. Each `grid.bybit-1m-history-page/v1` stores exact source
strings, request identity, row hash/count, and attempt count. The
`grid.bybit-1m-history-acquisition/v1` manifest inventories every page and is committed by a
separate `grid.history-acquisition-receipt/v1` written last. A valid Landing receipt is input
evidence for canonical publication, not a canonical dataset completion marker. Candle and funding
Landing manifests may additionally carry the backward-compatible ADR-0043
`adaptive_throttling` summary under `request_bound`. It binds classified response-header counts,
the configured/final/minimum global rate, reductions, cooldowns, and zero automatic increases.
ADR-0060 adds only an ephemeral transport failure class: regional CloudFront response bodies are
bounded, classified, discarded, and never enter this manifest or any receipt. Genuine rate-limit
403 accounting remains unchanged.
Legacy v1 manifests without that optional object or ADR-0044 `started_at_ms` remain valid; new
executions always write both.
Canonical candle rows derive `ingestion_id` from the staged page artifact SHA-256, so provenance
cannot collide between otherwise similar jobs.

`grid.public-history-campaign-request/v1` expresses up to 700 named symbols, at most 120 calendar
months, one or more of trade/mark/funding, and explicit bounded paging/concurrency settings. It
must select `registry-lifecycle-intersection-v1`; the resulting clipping is ex-post source
acquisition scope and cannot be used as point-in-time strategy metadata.

`grid.public-history-campaign-plan/v1` binds the exact request, registry/capacity hashes, public
endpoint policy, and every deterministic dataset/month/eight-bucket child request and plan hash.
For funding campaigns it may additionally bind a fully verified ADR-0048 source-boundary
manifest/plan/request/software identity. ADR-0052 clips each funding series to its source-proven
canonical start and binds the exact discovered predecessor into the first child boundary task.
Aggregate preflight accounts for all incomplete child Landing bounds before mutation, while
execution is sequential so per-child pacers do not multiply the configured RPS.
Within one preflight invocation, ADR-0047 verifies registry/capacity bytes once and reuses their
path-checked parsed snapshot for all child derivations. Every child and aggregate artifact retains
the same exact evidence hashes; each later command invocation reloads and reverifies the files.
`grid.public-history-campaign-manifest/v1` is written with a separate
`grid.history-campaign-receipt/v1` only after every child completion receipt verifies. It records
only aggregate job/page/row/HTTP counts and child hashes/relative roots; it is runtime acquisition
evidence, not canonical publication, accepted coverage, or Gate 2 evidence. See ADR-0038.

`grid.phase2-public-history-campaign/v1` may carry the ADR-0044 `timing` and
`adaptive_throttling` projections. They are optional so immutable legacy evidence still validates.
The strict builder mode requires every child to contain both inputs and proves that classified
observations cover every completed page response. ADR-0045 separately exposes the verified
transport-attempt total and the count of bounded attempts that produced no response observation;
it never invents response headers for a connection/protocol failure.

The same evidence may carry ADR-0051 `source_quality`: aggregate candle source/admitted/quarantine
counts, fixed reason counts, a receipt-derived quarantine binding hash, and an explicit canonical
coverage-complete flag. Exact source rows and their identities remain local. The `by_kind` array
contains exactly the one-to-three kinds requested by the campaign; older three-kind evidence
remains valid.

`grid.phase2-public-history-campaign/v1` is the GitHub-safe projection of one fully re-verified
campaign. It binds campaign/request/registry/capacity hashes, immutable implementation identity,
scope counts, measured runtime bytes, and aggregate plus per-kind job/page/row/HTTP/retry counts.
Its schema contains no symbols, instrument IDs, market values, runtime paths, device/account data,
or credentials. It may expose only the bound funding source-boundary manifest hash. It proves
public Landing acquisition and resume integrity only.

`grid.history-campaign-publication-plan/v1` binds one verified acquisition campaign, its exact
registry/capacity evidence, immutable publisher Git identity, and every source-job/canonical
input/request/dataset identity. Preflight loads at most one child Arrow batch at a time. The
resource bound is the maximum sequential child requirement; each child already includes the full
active-plus-building reservation, retained Landing budget, operating reserve, and bounded writer
workspace.

`grid.history-campaign-publication-manifest/v1`, committed by a separate
`grid.history-campaign-publication-receipt/v1`, inventories every verified canonical dataset and
its source manifest, request hash, manifest hash, rows, files, and bytes. Children run in source
sequence with one writer and resume from their immutable canonical completion receipts. The
aggregate verifier recomputes source-derived dataset/build identities and verifies every canonical
file, audit, manifest, and receipt. This is publication lineage, not coverage/lifecycle acceptance
or catalog registration. See ADR-0039.

ADR-0067 keeps that one-to-one lineage when a verified candle child has zero admitted rows. The
child publishes one schema-only Parquet file with the unchanged canonical schema, zero rows and
instruments, null key bounds, and normal audit/manifest/receipt bindings. Campaign v1 child row
counts therefore allow zero. This marker does not accept an empty requested range or quarantined
source row; the unchanged coverage audit remains blocked and classifies the exact missing reason.

ADR-0046 makes the verifier mode explicit. Initial/pending publication and coverage auditing use
semantic source admission. A completed aggregate publication may reverify source children through
their exact artifact bytes, page receipts, task/manifest facts, child receipts, allowlists, and
aggregate receipt without decoding source rows, while still fully verifying canonical files and
receipts. Integrity-only mode cannot return a typed batch.

`grid.phase2-history-campaign-publication/v1` is the GitHub-safe projection of that fully verified
publication. It binds source request/campaign, registry, capacity, publication plan, and
publication manifest hashes; records only aggregate/per-kind datasets, rows, files, Parquet bytes,
scope counts, requested bounds, and maximum sequential child resource bounds; and binds immutable
publisher and evidence-builder Git identities. Its exact schema excludes dataset/symbol/instrument
identities, runtime paths, market values, account data, and credentials. It proves immutable
canonical publication lineage only; coverage audits, catalog registration, and Gate 2 remain
separate. New artifacts may optionally record the ADR-0046 source-reverification mode and the
monotonic elapsed milliseconds of completed-publication verification; old v1 artifacts remain
valid. See ADR-0040 and ADR-0046.

`grid.history-campaign-coverage-audit/v1` binds one verified aggregate publication and the
canonical content hash/status of every ADR-0026/ADR-0034 child audit in campaign sequence. It sums
per-kind inventory, candle/funding quality counters, and unchanged unaccepted reason counts while
excluding symbols, instrument/dataset IDs, market values, event timestamps, runtime paths, account
data, and credentials. The aggregate passes only when every child passes; it never changes gap or
funding-cadence acceptance policy. See ADR-0041.

`grid.phase2-candle-boundary-diagnostic/v1` binds a candle-only aggregate publication, the exact
receipt-verified ADR-0041 semantic coverage artifact, and the same registry/source lineage. It
reuses canonical dataset verification and scans only instrument/time columns once to classify
missing requested minutes as leading, internal, trailing, or fully absent. Public output contains
only aggregate/per-kind counts and hashes; it excludes identities, observed timestamps, values,
paths, account data, and credentials. First observed data is source-availability evidence, not
listing metadata, and no topology or reason is accepted. See ADR-0070.

`grid.phase2-announcement-archive-depth/v1` binds a receipt-verified instrument registry and a
hash-only selected identity set to a bounded probe of the official Bybit announcements API. It
requests only the first and declared last page for each of the eight documented types, with a
fixed 20-item page size and one transport attempt, so at most 16 responses replace a full archive
download. The strict contract records only counts, date/publish-time bounds, and canonical result
hashes; it excludes announcement text/URLs, instrument identifiers, market values, paths,
credentials, and account data. A selected registry launch before the official `new_crypto`
archive start is an explicit blocker. Even a depth-compatible result still requires exact
per-instrument record matching and cannot close Gate 2. ADR-0072 aligns ordering with the
source's descending `dateTimestamp`, records separate date/publish bounds, and uses only the
source-order date bound for archive-depth comparison. ADR-0073 requires that date field while
allowing unbackfilled legacy `publishTime` to remain absent; per-page presence counts and nullable
publish bounds expose the omission without synthesizing data. ADR-0074 preserves and reports
source-order inversions for every type, requires consistent date order only from `new_crypto` and
`delistings`, and names aggregate coordinates as declared-last-page observations rather than
global archive minima. See ADR-0071 through ADR-0074.

`grid.phase2-history-campaign-resume-performance/v1` is the receipt-last GitHub-safe
qualification of a partially completed campaign resume. It binds the exact campaign request and
plan, registry, capacity evidence, and merged implementation identity; publishes only aggregate
job/page/resource counts and local elapsed times; and requires a single synthetic fail-closed
first-pending client call with `network_request_performed=false`. It contains no instrument
identity, market value, runtime path, device/account data, or credential. The result measures
local resume traversal only and does not prove source coverage, endpoint performance, Gate 2, or
live/private readiness. See ADR-0059.

`grid.history-to-canonical-publication/v1` maps exactly one completed Landing manifest to one
immutable ADR-0022 candle dataset. It requires the same receipt-verified registry and capacity
artifact hashes bound by acquisition, re-derives the capacity budget, validates registry lifecycle
bounds, and binds an explicit software identity. Dataset identity is the candle kind plus the first
24 hexadecimal characters of the full Landing manifest SHA-256; the full hash remains in source
and coverage evidence. Publication receipt does not imply that gaps or lifecycle coverage are
accepted.

`grid.phase2-public-1m-pilot/v1` is a small GitHub-safe evidence contract for a bounded completed
pilot. It binds Landing, registry, capacity, input-table, build-configuration, and canonical
manifest hashes; records requested ranges and aggregate counts; and proves consecutive exact 1m
coverage inside each requested series. It explicitly contains no candle values, account data,
local paths, device identity, or credentials. Its `existing_commit_verified` fact proves an
idempotent publication preflight, not full lifecycle/gap acceptance or Gate 2 completion.

`grid.canonical-1m-coverage-audit/v1` re-verifies one completed Landing-to-canonical publication,
requires exact reconstructed-Arrow/Parquet equality, and accounts for every requested minute.
Per-series facts include lifecycle bounds, missing contiguous ranges, duplicates, unexpected
timestamps, and observed rows; dataset facts also include rows outside every request. The complete
gap-range list is hash-bound while only 20 diagnostic samples are embedded. In v1,
`rest_returned_no_data` is observed but never accepted: any gap blocks status and cannot be
silently classified as a no-trade interval. ADR-0053 additionally records a receipt-verified
returned-but-quarantined candle as `quarantined_source_row`, removes its missing key from the
REST-no-data reason count, and still blocks. Exact quarantine keys remain runtime-only.

ADR-0068 extends the existing v1 publication artifacts with optional canonical-admission facts.
A candle child may add `source_row_count` and `canonical_admission` containing exact
source/admitted/excluded arithmetic, its policy, complete aggregate reason counts, and a SHA-256
binding of private excluded rows. Those fields appear together only when at least one exact trade
volume exceeds the accepted Decimal128(38, 4) scale. They contain no row, key, symbol, timestamp,
or market value. The child build hash and source evidence bind the exclusion.

The coverage reason `canonical_representation_overflow` is unaccepted and is not also counted as
`rest_returned_no_data`. Public campaign-publication evidence may add an aggregate admission
summary, and aggregate coverage may add only the reason count. These extensions do not alter
P-001, accept a missing minute, register a dataset, close Gate 2, or authorize Phase 3.

`grid.bybit-1m-gap-repair-plan/v1` is a receipt-last, no-network plan derived from a recomputed,
receipt-verified blocked coverage audit. It is valid only when missing minutes classified as
`rest_returned_no_data` are the sole blocker. It hash-binds the audit artifact/content, Landing
manifest, canonical manifest, planner Git identity, and one exact standard
`grid.bybit-1m-history-request/v1` per contiguous gap. The complete plan is limited to 1,000 tasks
and 100,000 maximum HTTP attempts. It authorizes neither request execution nor mutation of a
committed canonical dataset; repaired publication needs explicit immutable replacement lineage.
`quarantined_source_row` is never eligible for this ordinary repair plan because repeating the
same source endpoint does not reconcile a stable semantic defect.
`canonical_representation_overflow` is also ineligible because retrying cannot make the same exact
source value fit the accepted physical scale.

`grid.bybit-1m-gap-repair-execution/v1` re-verifies that complete chain, preflights every embedded
standard request under one aggregate staging bound, and inventories the independently receipted
Landing results. It is `passed` only when every gap minute is returned exactly once. A repeated
empty/partial REST observation is committed as `blocked`; it is never reclassified as accepted
absence. The execution artifact contains ranges, hashes, counts, and software identity but no
market values, credentials, host identity, or local paths.

`grid.canonical-1m-gap-replacement-publication/v1` combines a passed execution with its verified
canonical parent. It rejects overlapping, duplicate, shifted, and unrequested keys and proves the
exact original requested coverage before invoking the canonical writer. The resulting manifest
has a deterministic new dataset ID, exactly one parent dataset ID, and source hashes for the
parent manifest, plan, execution, registry, and every repair Landing manifest.

`grid.canonical-1m-gap-replacement/v1` is the receipt-last, value-free post-publication proof. It
binds both manifests and records exact parent/repaired/replacement row accounting, zero key
blockers, and `parent_dataset_mutated=false`. It is not catalog registration, compaction, or Gate 2
acceptance.

`grid.canonical-candle-compaction-publication/v1` combines one or more fully verified candle
parents only when their exact schema, dataset type, UTC month, and stable bucket match. The
complete sorted parent union must have unique keys, output must reduce fragment count, and the
child manifest lists every ordered parent ID. A fixed-batch logical table hash proves values are
unchanged independently of Parquet/chunk boundaries. Target sizing is calibrated from a bounded
ZSTD-3 sample; every non-final file uses the planned row target and only the final file may be an
explicit tail.

`grid.canonical-1m-compaction/v1` is the receipt-last GitHub-safe proof. It binds capacity, every
parent and child manifest hash, equal input/output logical hashes, file-count reduction, actual
output bytes, 16 MiB target facts, at most one tail, complete lineage, and immutable Git software
identity. It contains no market values, runtime paths, host identity, account data, or credentials.
It does not register a catalog entry, delete a parent, or close Gate 2.

`grid.canonical-funding-compaction-publication/v1` combines at least two receipt-verified funding
parents only when their exact schema, UTC month, and stable bucket match. It rejects duplicate
keys and settlement-interval mismatches across parent boundaries, binds the exact logical union
and every parent manifest, and uses the standard funding publication primitive to create one new
receipt-last child. `grid.canonical-funding-compaction/v1` is the value-free GitHub proof of
logical equality, file reduction, target classification, unchanged parents, and complete lineage.
It does not accept chronology, repair missing events, register the child, or close Gate 2.

`grid.funding-compaction-candidate-audit/v1` is a detailed private, receipt-last classification of
every bounded same-partition funding parent pair in one exact store state. The public
`grid.phase2-funding-compaction-candidate-audit/v1` projection binds the audit/store hashes,
implementation identities, inventory counts, and aggregate outcomes only. It contains no dataset,
partition, instrument, timestamp, rate, path, host, account, or credential identity. Neither
contract performs compaction or replaces measured ADR-0054 evidence.

`grid.phase2-stale-output-fault-injection/v1` binds a merged implementation identity to five
offline production-preflight cases: candle/funding publication building directories, candle
compaction building directory, catalog building file, and catalog write lock. Every case must be
detected, preserve the injected marker, and leave its target uncreated. The artifact contains no
market values, runtime paths, device/account identity, credentials, or private/live capability and
does not itself accept Gate 2.

`grid.gate2-readiness-pack/v1` binds the unchanged roadmap criteria hash and eight exact public
Phase 2 artifacts after receipt, schema, content-hash, artifact-hash, status, and lineage
verification. It records two `evidence-ready` and four blocked criteria plus seven explicit
blockers. Evidence readiness is not acceptance: data-quality-owner review remains mandatory,
Gate 2 remains closed, and automatic Phase 3 authorization is always false.

`grid.gate2-readiness-pack/v2` is the append-only current-evidence successor. It verifies twelve
exact GitHub artifacts and their campaign/publication/coverage/registry lineage in one offline
pass, then records three evidence-ready and three blocked criteria with seven current blocker
codes. It performs no Bybit request, retained-store read, or repeated benchmark. The contract
cannot accept Gate 2, authorize Phase 3, expose runtime identities/market values, or reinterpret
the immutable v1 result; see ADR-0075.

`grid.phase2-canonical-integrity-fault-injection/v1` binds a merged implementation identity to
six offline candle/funding verifier cases: orphan file, missing manifest-bound Parquet, and missing
completion receipt for each dataset type. Every case must be detected and retain an identical
filesystem fingerprint through verification. The artifact contains no market values, identities,
paths, account data, credentials, or private/live capability and does not authorize cleanup.

`grid.bybit-funding-repair-plan/v1` is a receipt-last, no-network private discovery plan. It
recomputes the exact blocked `grid.canonical-funding-coverage-audit/v1` and is valid only when
`unexplained_interval_change` is the sole blocker and every changed edge belongs to an isolated
integer-multiple `C, N*C, C` pattern. Each task binds exact candidate settlement timestamps, the
source-observed predecessor, and one bounded standard funding request. The plan accepts no
candidate or schedule change, uses no current interval metadata, mutates no dataset, and is
limited to 1,000 tasks/candidates and 100,000 maximum HTTP attempts. Real artifacts remain
private because exact instrument and settlement identities are operational evidence; see
ADR-0055.

`grid.bybit-funding-repair-execution/v1` re-verifies that complete chain, preflights all embedded
standard funding jobs under one aggregate remaining-staging bound, and inventories their ordinary
Landing receipts. It is `passed` only when every source response contains exactly the complete
ordered candidate set, with no missing or unexpected settlement. Empty or partial confirmation
is `blocked`; the parent and original audit are unchanged. Rates are excluded, but exact
instrument/range identities make the execution record private and not GitHub-eligible; see
ADR-0056.

`grid.bybit-funding-repair-execution-public/v1` is a receipt-last GitHub-safe projection of that
private execution. It binds the private artifact plus parent/audit/plan/registry/capacity hashes
and publishes only aggregate request, task, candidate, missing, observed, and unexpected counts.
Its exact schema excludes task records, dataset/instrument identifiers, settlement timestamps,
market values, runtime paths, account data, and credentials.

`grid.canonical-funding-repair-publication/v1` consumes only a complete `passed` execution. It
requires the parent and repair rows to share one exact funding schema and month/bucket, rejects
overlap and duplicates, recomputes interval minutes over the complete sorted union, and preserves
the existing first-event predecessor boundary. The receipt-last child has one immutable parent
and binds every upstream manifest and the full publisher Git identity.

`grid.canonical-funding-repair-replacement/v1` is the value- and identifier-free public lineage
proof. It binds parent, plan, execution, replacement, registry, and capacity hashes; exact row
accounting; source-confirmed inserted-settlement and restated-interval counts; zero key blockers;
and `parent_dataset_mutated=false`. It does not update the original audit, accept a cadence
policy, register the child, or close Gate 2; see ADR-0057.

`grid.canonical-funding-repair-coverage-audit/v1` is the private receipt-last verdict over a
committed repair child. It re-verifies the original Landing/publication/audit, plan, execution,
immutable parent/child lineage, registry, capacity evidence, and replacement evidence; requires
exact canonical equality with the reconstructed original-plus-repair source union; and reuses the
ADR-0034 predecessor/internal chronology, page coverage, lifecycle, duplicate, empty-window, and
cadence-change rules. Current interval metadata remains excluded. The contract contains exact
series identifiers and time bounds, so `github_commit_eligible=false`; a pass neither rewrites the
original blocked audit nor accepts cadence policy, catalog registration, Gate 2, or live use. See
ADR-0058.

`grid.canonical-dataset-catalog/v1` is a DuckDB-backed logical metadata projection. It stores only
complete receipt-verified dataset, parent, schema, evidence/build/software, file/hash/count/bounds,
month/bucket, gap/conflict-summary, and logical receipt/object identities. A monotonically
increasing revision plus canonical logical content SHA-256 identifies a snapshot independently of
DuckDB bytes. The catalog is rebuildable metadata; manifests and completion receipts remain
authoritative.

`grid.canonical-dataset-catalog-registration/v1` is the GitHub-safe proof that explicitly named
datasets are present in one verified catalog snapshot. It contains hashes, counts, lineage,
partition facts, and limitations but no candle values, credentials, account/host identity, or
absolute path. `not-assessed-by-dataset-receipt` must not be treated as complete coverage.

`grid.canonical-dataset-selection-request/v1` binds the exact catalog revision/content hash,
sorted explicit dataset IDs, one candle type, inclusive minute-aligned range, explicit all/include
instrument filter, and consumer Git SHA. `grid.canonical-dataset-selection/v1` re-verifies the
selected datasets and produces hash-bound store-relative object keys. It rejects implicit latest,
missing month/bucket partitions, ancestor-plus-child inputs, and overlapping exact keys.
ADR-0065 retains the metadata-only fast path for provably separated file bounds. Ambiguous
multi-instrument bounds are admitted only by a bounded exact-key merge over receipt-verified
Parquet key columns, with a 4,096-row batch per stream and 128-stream ceiling; exact duplicates
and over-fragmented partitions fail closed. The external v1 schemas remain unchanged. Selection
proves deterministic range pruning and exact selected-object key disjointness only; separate
coverage acceptance remains mandatory.

`grid.phase2-incremental-catalog-selection-performance/v1` is ADR-0066's receipt-last,
GitHub-safe synthetic measurement of the ADR-0065 fallback. It binds immutable implementation
identity, bounded fragment/instrument/minute counts, exact selector constants, two measured
selection passes, aggregate correctness, deterministic equality, and unchanged store
fingerprints. Software versions, non-identifying CPU/RAM/platform facts, and explicit cache state
make the measurement interpretable. It contains no dataset/instrument identity, timestamp,
runtime path, market value, host/device/account identity, or credential. It is not full-history
performance or Gate 2 evidence.

ADR-0035 extends these catalog contracts with `funding_event`. Funding registration invokes the
strict funding receipt/manifest/audit/Parquet verifier and extracts first/last keys from
`instrument_id, funding_time_ms`; candle behavior is unchanged. A selection request still carries
exactly one dataset type, so candle and funding IDs cannot be mixed. Funding catalog/selection
evidence contains only metadata, hashes, and store-relative objects and does not imply chronology
coverage, compaction, repair, scale qualification, or Gate 2.

## Canonical trade-price 1m candle

Primary key:

```text
(category, instrument_id, open_time_ms)
```

Required fields:

- open time and fixed 60-second interval;
- open/high/low/close;
- volume and turnover;
- source identity;
- ingestion/batch identity;
- quality flags;
- source archive/object or API range evidence.

Invariants:

- timestamps exactly minute-aligned;
- `low <= open, close <= high` and `low <= high`;
- one canonical row per key;
- no candle before instrument launch;
- numeric values finite, non-negative where required;
- conflicting duplicate source rows are not silently resolved.

## Canonical mark-price 1m candle

Same time/instrument key pattern, distinct dataset/source contract. Fields include OHLC and quality/provenance. It must never be joined to trade candles by row order; join uses explicit category, instrument ID, and timestamp.

## Funding event

Primary key:

```text
(category, instrument_id, funding_time_ms)
```

Fields:

- exact signed funding rate, physically Decimal128(38, 18) in v1;
- applicable funding interval as elapsed whole minutes since the immediately preceding
  authoritative settlement;
- source and ingestion identity;
- quality flags.

Settlement timestamps are exact UTC minutes. Within each instrument, every event after the first
event present in a canonical batch must equal the preceding settlement time plus its declared
interval. The first event requires hash-bound predecessor or dated interval evidence; current
instrument metadata is not historical proof. Missing boundary evidence blocks publication.

Funding files use `grid.canonical-funding-layout/v1`: UTC month plus
`instrument_id mod 8`, sorted by `instrument_id, funding_time_ms`, exact Decimal128 values, the
16 MiB target, and ZSTD level 3. Backtests join funding by the exact economic application
interval, not nearest-row convenience. See ADR-0031.

`grid.bybit-funding-history-request/v1` names only symbols and requested bounds. Its resolved plan
adds stable IDs, dated launch bounds, one predecessor task per series, and fixed requested-range
pages. Page artifacts preserve normalized exact rate/timestamp pairs and reject a saturated
response. The acquisition manifest binds all page receipts and a canonical predecessor aggregate;
see ADR-0032.

`grid.bybit-funding-source-boundary-request/v1` names sorted symbols and one closed scan range.
Its plan adds receipt-verified registry identities and launch/delivery intersections. Execution
uses bounded backward pagination and persists only `fundingRateTimestamp` values in individually
receipted pages; each returned exact-decimal rate is validated and discarded. The completion
manifest binds every page, the shared decrease-only throttling summary, and per-series oldest and
second-oldest settlements. The oldest is predecessor-only; the second-oldest is the earliest
canonical start this evidence can admit. These runtime identities and timestamps stay outside
Git, and the result does not imply cadence/coverage acceptance or Gate 2; see ADR-0048.

`grid.phase2-funding-source-boundary/v1` is the GitHub-safe projection of one complete ADR-0048
discovery. It re-verifies the private plan, every timestamp page/receipt, manifest, adaptive
summary, completion receipt, and allowlist, then exposes only request/registry/plan/manifest
hashes, immutable Git identities, requested scan bounds, aggregate counts, strict response
accounting, and fixed policy/limitations. It excludes symbols, instrument IDs, per-series facts,
funding rates, observed settlement timestamps, runtime paths, device/account data, credentials,
and private endpoints; see ADR-0049.

`grid.phase2-public-funding-pilot/v1` re-verifies one immutable funding publication, exact
Landing/Parquet table equality, and every predecessor/internal interval derivation. The
GitHub-safe receipt-bound summary contains requested ranges, observed event counts, page/process
facts, layout facts, immutable Git identity, and transitive hashes, but no rates, observed
settlement timestamps, local paths, host identity, account data, credentials, or runtime market
files. Sparse event counts do not establish complete historical settlement chronology, lifecycle
coverage, accepted gaps, or Gate 2; see ADR-0033.

`grid.canonical-funding-coverage-audit/v1` re-verifies exact Landing/Parquet equality, one
predecessor per series, complete range-page tiling, registry lifecycle bounds, and every
settlement-derived interval. Its v1 reason policy accepts nothing automatically: an empty source
window, predecessor/internal mismatch, or cadence change blocks until separately dated evidence
or governance explains it. Current `fundingInterval` is explicitly unused. Public evidence keeps
requested bounds, counts, interval histograms, hashes, and identities but excludes rates, observed
settlement timestamps, runtime paths, host/account data, and credentials. `passed` is bounded
source-parity/stable-cadence evidence, not full-history or Gate 2 acceptance; see ADR-0034.

## Dataset manifest

Required fields:

- dataset ID;
- dataset type;
- schema and semantic contract version;
- status: `building`, `failed`, or `complete`;
- parent dataset IDs;
- coverage bounds and instrument count;
- partition inventory;
- row counts and key statistics;
- file/object hashes;
- source evidence hashes;
- build configuration hash;
- software/environment identity;
- audit report IDs and hashes;
- commit timestamp.

Only `complete` datasets are consumable.

## Feature row

Primary key:

```text
(feature_dataset_id, category, instrument_id, decision_time_ns)
```

Required concepts:

- feature version;
- decision/availability timestamp;
- warmup completeness;
- data-quality status;
- normalized ATR/volatility/range position;
- boundary touches/crossings;
- amplitude/compression/volume/regime fields declared by version;
- parent market dataset ID.

Every feature must document its exact lookback and whether the current closed candle is included.

## Range candidate

Primary key:

```text
(candidate_dataset_id, candidate_id)
```

`candidate_id` is deterministic from instrument, decision time, candidate-rule identity, and feature version.

Fields include:

- category/instrument/symbol;
- decision time;
- lookback/window identity;
- lower/upper/mid range;
- range height in price, percent, and ATR units;
- touch/crossing/amplitude measurements;
- current position in range;
- hard-filter results and reason codes;
- ranking inputs;
- parent feature dataset and configuration hash.

## Grid outcome

Primary key:

```text
(outcome_dataset_id, candidate_id, parameter_id, ambiguity_case)
```

Fields include:

- exact grid geometry and constraints;
- entry/activation semantics;
- stop-loss and exit policy;
- leverage/investment/risk values;
- fees/funding/slippage assumptions;
- fill/event counts;
- gross/net PnL and PnL in risk units;
- max adverse/favorable excursion;
- liquidation/SL/exit results;
- duration and capital-locked time;
- intrabar ambiguity classification;
- validate-feasibility or constraint status;
- simulator version and parent candidate/market IDs.

## Experiment record

Fields include:

- experiment ID and lifecycle status;
- immutable specification hash;
- dataset/feature/candidate/outcome parent IDs;
- split/fold and embargo definitions;
- parameter search space and algorithm;
- selected candidates and rationale;
- per-fold/time/symbol/regime metrics;
- concentration, stress, ambiguity, and cost evidence;
- environment/software identity;
- report and artifact hashes.

## Strategy release

Defined in [Strategy Release Contract](09_STRATEGY_RELEASE_CONTRACT.md). It is immutable and is the only research-to-live interface.

## Live signal

Primary identity:

```text
signal_id = deterministic(release_id, category, instrument_id, decision_time, rule_id)
```

Fields include:

- release/strategy/feature version;
- complete feature snapshot or its canonical hash;
- selected parameter row and hash;
- hard-filter and risk results;
- Bybit validate evidence;
- projected exposure/loss;
- status and state-transition sequence;
- approval identity/expiry/payload hash where applicable.

## Live bot state

Required concepts:

- local bot workflow ID;
- exchange bot ID(s);
- signal/release identity;
- canonical request identity;
- exact requested and observed parameters;
- current exchange/local state;
- creation/close uncertainty flags;
- last reconciliation evidence/time;
- position, PnL, fees, funding, liquidation/SL fields where available;
- state transition version.

## Audit event

Defined by the structured envelope in [Observability, Audit, and Recovery](13_OBSERVABILITY_AUDIT_AND_RECOVERY.md). Audit records are append-only.

## Numeric policy

- Canonical market timestamps use signed integer Unix milliseconds; candle open times are exact
  multiples of 60,000. A new unit requires a new semantic/physical contract version.
- Prices/quantities/rates use Decimal/scaled integer at exact boundaries.
- Binary floats may be used only in explicitly documented analytics where round-off cannot change execution semantics.
- No implicit coercion from strings, booleans, floats, or nulls to exact contract fields.
- Every rounding direction is named and tested.

## Schema evolution

- Additive compatible changes require explicit version policy.
- Semantic changes always bump the semantic contract version even if physical columns look compatible.
- Consumers declare supported versions and fail clearly on unsupported versions.
- Migrations produce new immutable datasets; they do not rewrite an accepted dataset in place.
