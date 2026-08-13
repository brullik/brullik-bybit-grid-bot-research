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
evidence for canonical publication, not a canonical dataset completion marker. Canonical candle
rows derive `ingestion_id` from the staged page artifact SHA-256, so provenance cannot collide
between otherwise similar jobs.

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
silently classified as a no-trade interval.

`grid.bybit-1m-gap-repair-plan/v1` is a receipt-last, no-network plan derived from a recomputed,
receipt-verified blocked coverage audit. It is valid only when missing minutes classified as
`rest_returned_no_data` are the sole blocker. It hash-binds the audit artifact/content, Landing
manifest, canonical manifest, planner Git identity, and one exact standard
`grid.bybit-1m-history-request/v1` per contiguous gap. The complete plan is limited to 1,000 tasks
and 100,000 maximum HTTP attempts. It authorizes neither request execution nor mutation of a
committed canonical dataset; repaired publication needs explicit immutable replacement lineage.

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
missing month/bucket partitions, ancestor-plus-child inputs, and overlapping key ranges. It proves
deterministic range pruning only; separate coverage acceptance remains mandatory.

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
