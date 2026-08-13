# Changelog

All notable project-governance and architecture changes are recorded here.

## Unreleased

### Added

- ADR-0051 sanitized candle source-quality evidence: candle-only campaigns validate, requested
  kinds are projected exactly, and receipt-verified aggregate quarantine counts/reasons/hashes
  disclose an intentional canonical gap without publishing source identities or market values.
- ADR-0050 receipt-bound candle source-row quarantine: exact source strings and source order are
  retained for the three recognized OHLC-envelope failures, receipts bind per-page and aggregate
  hashes/counts, canonical publication excludes the row, and coverage remains fail-closed without
  price repair or alternate-source substitution.
- Receipt-verified five-instrument full-history funding boundary evidence: 37,286 timestamp-only
  events, 193 classified public responses, zero retries/rate-limit events, and five proven
  predecessor-backed canonical starts in a per-series identity/observed-time/value-free GitHub
  projection.
- ADR-0049 GitHub-safe funding source-boundary evidence: full runtime receipt reverification,
  strict completed-response accounting, aggregate hash/count projection, exact schema/redaction
  tests, and no symbol, instrument ID, funding rate, observed settlement time, or runtime path.
- ADR-0048 receipt-resumable funding source-boundary discovery: bounded backward public paging,
  timestamp-only page receipts, exact-rate validation without retention, second-settlement
  canonical admission, fresh SSD/NVMe/memory/free-space gates, and no private/live capability.
- Schema-bound five-instrument full-lifecycle campaign-preflight evidence: 1,467 jobs and 46,227
  pages retained identical resource bounds while ADR-0047 reduced same-host elapsed time from
  125,600 ms to 3,284 ms (38.246x; 97.39% less).
- ADR-0047 single-snapshot campaign admission: each invocation receipt-verifies registry/capacity
  inputs once for all child derivations, keeps exact per-child hash bindings, rejects path
  substitution, reloads on execute/resume, and exposes monotonic preflight elapsed milliseconds.
- Receipt-verified 100-instrument x 31-day ADR-0046 performance evidence: the same complete
  Landing/canonical chain verified in 88,566 ms, 2.60x faster than the prior 230.7-second semantic
  projection, with source-row decode still mandatory for first publication and coverage audits.
- ADR-0046 receipt-integrity reverification for completed canonical campaigns: every source byte,
  receipt, manifest fact, allowlist, aggregate chain, and canonical dataset still verifies while
  repeated publication/evidence checks avoid rebuilding already admitted source row batches; new
  evidence may record the verifier mode and monotonic elapsed milliseconds.
- Canonical 100-instrument x 31-day publication evidence: 24 immutable ZSTD-3 datasets/files,
  8,938,466 exact rows, 114,867,201 Parquet bytes, complete aggregate lineage, and a 24-reused /
  zero-pending idempotent replay.
- Fail-closed 100-instrument x 31-day aggregate coverage evidence: all 16 candle datasets passed
  with 8,928,000 gap-free minutes; five funding buckets passed and three remain blocked by seven
  unaccepted historical cadence changes.
- Receipt-verified 100-instrument x 31-day public long-run campaign evidence: 9,600 completed
  pages, 8,938,466 Landing rows, 591,702,449 bytes, complete response classification, 21 explicit
  no-response retries, no rate-limit/reduction/cooldown events, and measured resume overhead.
- Receipt-bound long-run campaign qualification with child execution timing, exact aggregate
  adaptive-throttling counters, full HTTP-response observation coverage, strict fail-closed CLI
  mode, backward-compatible v1 schemas, and GitHub-safe disclosure.
- Decrease-only global public REST throttling for candle/funding acquisition: sanitized Bybit
  response-header observations, 20% headroom adaptation, 429/10006 cooldown and rate reduction,
  HTTP-403 run abort, no automatic increase, and backward-compatible receipt-bound manifest facts.
- Receipt-verified current-inventory policy evidence from public mainnet: all four normative
  status partitions accepted, a passed 1,015-instrument complete-current summary, and a separate
  blocked three-snapshot summary proving that two older partial observations remain immutable.
- Receipt-bound aggregate coverage auditing for canonical history campaigns: sequential unchanged
  candle/funding child audits, complete child content-hash membership, summed quality/reason
  counters, strict blocker propagation, and a GitHub-safe identity/value-free result.
- Receipt-verified representative aggregate coverage evidence: all 72 canonical datasets passed,
  with 10,526,400 complete candle minutes, 10,965 chronology-consistent funding events, zero
  quality/reason blockers, and 72 sanitized child content-hash bindings.
- Schema-bound GitHub-safe canonical campaign publication evidence that re-verifies every source
  and canonical receipt/file while exposing only aggregate/per-kind counts, Parquet bytes,
  resource bounds, immutable Git identities, and transitive hashes.
- Receipt-verified representative canonical campaign evidence: 72 immutable trade/mark/funding
  datasets, 10,537,365 rows, 72 Parquet files, 187,352,531 bytes, independent aggregate
  verification, and an idempotent replay with 72 reused commits and zero pending datasets.
- Receipt-resumable canonical publication for a completed public history campaign: bounded
  one-child-at-a-time preflight, sequential candle/funding writers, immutable child-receipt reuse,
  receipt-last aggregate lineage verification, and no network/credential/live dependency.
- GitHub-safe, receipt-verified public history campaign evidence with exact aggregate hashes,
  kind/job/page/row/HTTP/retry counts, measured Landing bytes, immutable implementation identity,
  and schema-enforced exclusion of market values, runtime paths, account data, and credentials.
- Receipt-resumable public history campaign orchestration for up to 700 instruments and 120
  calendar months across trade, mark, and funding: deterministic month/type/eight-bucket child
  jobs, aggregate no-mutation host admission, sequential pacing, exact attempt bounds, child
  receipt reuse, receipt-last aggregate verification, and no credential/tick/live dependency.

### Fixed

- Long-run throttling qualification now distinguishes receipt-verified transport attempts from
  actual HTTP responses: every completed page response must be classified, while bounded
  connection/protocol attempts without a response remain separately visible instead of causing a
  false missing-header failure.
- Current linear instrument inventories now query exactly the dated normative Bybit status enum
  (`PreLaunch`, `Trading`, `Delivering`, `Closed`), bind that policy in evidence, reject
  cross-filter status leakage, and no longer create a false partial-inventory blocker by sending
  the non-normative mainnet `Settling` filter.
- Canonical campaign publication now hands each typed, receipt-verified Landing child directly
  from its single page-verification pass into bounded publication preflight. This removes repeated
  JSON/Decimal/Arrow decoding while preserving every page digest, manifest, receipt, source
  substitution, and final aggregate lineage check.
- Public REST transport now classifies direct stdlib connection/protocol failures such as
  `RemoteDisconnected`, `IncompleteRead`, and connection resets as bounded retryable transport
  errors. Non-retryable HTTP responses remain immediate failures.
- Immutable receipt-verified instrument timeline with stable cross-snapshot identities, strict
  point-in-time selection, separate ex-post lifecycle coverage, fail-closed conflict/partial-source
  accounting, and a bounded GitHub-safe summary that never exposes future snapshot fields.
- Measured two-snapshot instrument timeline over 1,015 stable USDT perpetual IDs with zero
  lifecycle conflicts, 303 delivery-bounded and 712 open-ended instruments, verified as-of growth
  from 1,010 to 1,015 IDs, and an explicit `partial_source_inventory` blocker for Bybit's rejected
  `Settling` status query.
- Receipt-verified measured April trade compaction over five independently acquired 10-instrument
  parents: 2,160,000 exact rows compacted from five files to two 16-MiB target-band files plus one
  explicit tail, with equal logical hashes, immutable parent lineage, and idempotent rerun.
- Receipt-verified Phase 2 scale-step evidence for 50 instruments over 90 days across three
  monthly partitions: 12,960,000 complete trade/mark candles, 21,421 funding events, revision-4
  three-object catalog selections, and an honestly blocked April funding audit for four undated
  cadence transitions on ONTUSDT/PIPPINUSDT while all candle and later funding audits pass.
- ADR-0036 and a backward-compatible correction aligning the canonical candle coverage-audit
  schema with the existing 700-series acquisition bound while retaining the separate 16-series
  pilot limit and every fail-closed quality rule.
- Receipt-verified Phase 2 scale-step evidence for 10 instruments over 7 days across trade 1m,
  mark 1m, and funding: exact public requests, 201,600 complete candles, 231 chronology-verified
  funding events, zero gap/key/lifecycle blockers, and revision-3 catalog selections.
- Receipt-verified measured funding catalog evidence: revision 2 over the existing candle/funding
  datasets, one exact BTC/UNI funding selection, idempotent reruns, and no rates, local paths,
  runtime DuckDB, credentials, account data, or Gate 2 implication.
- Backward-compatible funding registration and snapshot-bound selection in the receipt-verified
  DuckDB catalog, with strict funding verification/key extraction, type-specific partitions, and
  rejection of mixed candle/funding selection requests.
- Fail-closed funding source-chronology audit with exact Landing/Parquet parity, complete range-page
  tiling, private predecessor/internal interval recomputation, stable observed-cadence policy,
  hash-bound anomaly inventory, and explicit blocking of empty windows or undated cadence changes.
- Receipt-verified measured funding chronology audit for the two-instrument pilot: stable observed
  480-minute cadence, exact source/canonical parity, zero empty windows or interval/key/lifecycle
  blockers, and explicit bounded-source/non-Gate-2 limitations.
- GitHub-safe funding pilot evidence with exact Landing/Parquet equality, private predecessor and
  internal interval recomputation, sparse event/window accounting, transitive receipts/hashes,
  immutable publisher identity, and no rates, observed settlement times, paths, host/account data,
  credentials, or Gate 2 implication.
- Receipt-verified measured funding pilot evidence for BTCUSDT and UNIUSDT: 42 exact events from
  four unauthenticated public requests, predecessor-derived intervals, a verified 5,050-byte
  canonical tail file, and explicit non-coverage/non-scale limitations.
- Public-only funding acquisition with one receipted predecessor per series, fixed unsaturated
  range pages, bounded retries/concurrency/capacity, durable resume, exact normalization, boundary
  aggregate evidence, and a verified Landing-to-canonical adapter.
- Exact canonical funding Arrow/Parquet contract with Decimal128(38,18) rates,
  settlement-derived interval semantics, minute/eight-bucket partitioning, ZSTD-3, no-rounding
  conversion, and receipt-last immutable publication with independent tamper/orphan verification.
- Receipt-verified DuckDB dataset catalog registration with atomic revision/content-hash chaining,
  complete parent lineage, idempotent binding, and snapshot-bound reproducible range selection
  that rejects implicit latest, missing partitions, ancestor/child ambiguity, and key overlap.
- Sanitized representative catalog evidence for the existing two-instrument 20,160-row canonical
  pilot, including idempotent revision/hash verification and one exact hash-bound range selection.
- Fail-closed, target-size immutable canonical compaction with deterministic multi-file/tail
  semantics, complete parent lineage, logical hash parity, and receipt-last public evidence.
- Whole-plan-admitted, receipt-resumable public 1m repair execution plus fail-closed repeated-empty
  evidence, exact gap closure, immutable parent-to-child replacement lineage, and a value-free
  post-publication proof; no parent Parquet file is edited or deleted.
- Deterministic no-network 1m gap-repair planning from a recomputed receipt-verified blocked
  coverage audit, with missing-only fail-closed policy, complete gap accounting, bounded standard
  history requests, Git/hash bindings, and explicit canonical no-mutation semantics.
- Fail-closed canonical 1m coverage audit with exact Landing/Parquet equality, per-series minute
  accounting, bounded hash-bound gap evidence, lifecycle/duplicate/unexpected/unrequested checks,
  immutable blocked evidence, and no automatically accepted absence reason.
- Receipt-verified measured coverage audit for the two-symbol public pilot: exact parity across
  20,160 rows with zero gaps, duplicates, conflicts, unexpected/unrequested rows, or lifecycle
  violations, while retaining bounded-range and Gate 2 limitations.
- GitHub-authoritative Phase 2 pilot evidence with a strict sanitized schema, exact per-series 1m
  coverage proof, transitive Landing/canonical hashes, immutable publisher identity, receipt-last
  publication, and an explicit ban on market values, local paths, device/account data, and secrets.
- Verified Landing-to-canonical publication with deterministic dataset identity, transitive
  registry/capacity bindings, fresh no-mutation and execution host admission, explicit software
  identity, receipt-last immutable output, independent verification, and idempotent reruns.
- Stable Bybit-linear instrument registry evidence with deterministic UInt32 identities, exact
  dated metadata, source receipt binding, and rejection of caller-supplied candle identities.
- Bounded public trade/mark 1m acquisition with no-mutation host/capacity preflight, fixed
  1,000-minute pages, conservative global pacing, explicit retries, per-page receipts, durable
  resume, exact-decimal validation, and a receipt-last verified Landing batch.
- Snapshot-before-clock ordering for both execution-time host rechecks, preventing a freshly
  observed host timestamp from being misclassified as future-dated by call-order skew.
- Receipt-last immutable candle-partition publication with a no-mutation/fresh-recheck host
  preflight, content-addressed Parquet files, canonical manifests/audits, idempotent verification,
  stale-output detection, and Windows-safe closed-handle directory publication.
- Independently installable `grid-market-store` package with the accepted exact-hybrid Arrow
  schema, deterministic eight-bucket mapping, UTC month partition paths, strict no-rounding
  conversion, and cross-platform physical-contract tests.

### Governance

- Owner/PM acceptance of Gate 1 and the Phase 2 canonical one-minute market-data MVP.
- Canonical candle selection: exact hybrid Int64/Decimal representation, eight stable instrument
  buckets, 16 MiB file target, and ZSTD level 3.
- Evidence-based selection of the current owner laptop as the reference research host under
  ADR-0019, retaining fresh memory, NVMe, free-space, and bounded-staging preflight requirements.

## 0.2.0 — 2026-08-12

### Added

- Independently installable `grid-data`, `grid-research`, `grid-release`, and slim `grid-live` package boundaries.
- Dependency-free exact-decimal market/dataset contracts and versioned JSON Schemas.
- Public-only Bybit V5 adapter with cursor and reverse-time pagination guards.
- Bounded trade/mark/funding feasibility sampler with metadata-derived funding interval,
  exact-decimal validation, gap summaries, content hashes, and a versioned evidence schema.
- Owner-controlled HMAC Futures Grid validate-only package with hard-coded Bybit origins, testnet
  default, exact Neutral + Geometric payload, redirect rejection, private receipts, and no
  create/close/transfer endpoint.
- Atomic feasibility evidence publication and SHA-256 receipts.
- DuckDB/Polars Parquet layout benchmark harness and architecture tests.
- Fail-closed layout benchmark profiles with compressed-size calibration, observed target
  attainment, sequential representations, and bounded scratch retention.
- Sharded Polars feature-throughput benchmark with a 1,440-minute halo, no-future parity tests,
  peak-RSS measurement, JSON Schema, and checked-in 700-instrument scaled evidence.
- Reproducible workstation snapshot and profile assessment with a verified evidence receipt.
- Receipt-linked capacity projection that keeps synthetic extrapolation separate from the
  documented 24/40/64-byte planning envelopes and provisional hardware recommendation.
- Bounded official-archive coverage matrix for every current USDT LinearPerpetual symbol, direct
  probes for index exceptions, top-level product summaries, current-metadata mismatch guards, and
  schema-verified evidence without raw archive downloads.
- A 100-million-row, 700-instrument reference-scale feature candidate proving 50-shard halo
  execution with bounded peak RSS, plus corrected non-divisible row-count validation in both
  benchmark harnesses.
- CI checks for lint, formatting, strict typing, tests, schema/evidence validation, manifest
  integrity, and slim live installation.
- Staged ADR-0010 shortlist protocol with reboot-separated cold-read legs, post-timing content
  verification, immutable monthly repair/compaction probes, and fail-closed smoke classification.
- Bounded public real-market layout-skew collector with liquid/price-stratified selection, complete
  closed-candle checks, exact two-layout parity, ignored raw work files, and receipt-linked summary.
- Real-market-calibrated v3 capacity projection and a v2 reference-protocol contract that binds the
  skew artifact and requires actual shortlisted target-file attainment.
- Receipt-bound reference-host admission that rejects below-profile or mismatched machines/volumes
  before mutation and freezes engine/runtime versions across reboot-separated measurements.
- Volume-aware Windows storage identity using the measured drive's physical device number instead
  of assuming every benchmark volume is backed by `PhysicalDrive0`.
- Volume-aware Linux block-device/model detection for reference evidence on NVMe research hosts.
- Shared fail-closed reference-host admission for layout and feature benchmarks, append-only v2
  feature evidence, pre/post-run host and software binding, auditable memory-gate rejection, and
  actual mounted-volume discovery for Linux workstation snapshots.
- Receipt-linked Gate 1 owner-review aggregation with transitive source verification, same-host/
  scale/runtime binding, provisional scan/write/memory/capacity checks, explicit P-001—P-005
  candidates, preserved negative evidence, and no automatic gate or Phase 2 approval.
- Receipt-linked current-universe capacity evidence that separates the one-time canonical
  bootstrap, active-plus-building rebuild, daily incremental append, and bounded monthly repair;
  retains the formal planning envelope; and leaves raw archive headroom explicitly unmeasured.
- Owner-approved ADR-0016 one-minute-only source boundary, append-only v2 source evidence, and a
  REST capacity envelope covering trade-price 1m, mark-price 1m, and funding without downloading
  or retaining tick-trade archive bodies.
- Bounded public REST history-boundary evidence with deterministic Trading/Closed selection,
  launch/annual/terminal observations, strict request accounting, exact-versus-sampled semantics,
  and hashes/timestamps only instead of retained market values.
- Bounded public 1m REST throughput evidence with global pacing, documented IP-limit headroom,
  exact preflight, full-page continuity checks, zero hidden retries, append-only negative and
  confirmation runs, and no persisted market values.
- Immutable external reference-campaign plans with qualifying-host/source admission, exact
  eight-step argv handoff, read-only receipt-aware progress status, explicit reboot boundaries,
  and permanent owner/PM control of the Gate 1 decision.
- Reproducible clean-host reference bootstrap with CI-shared exact dependency constraints,
  explicit monorepo editable installs, a read-only environment doctor, canonical clean-main
  enforcement, and rejection of private Bybit environment variables before plan publication.
- Owner-approved ADR-0019 replacement of the provisional 16-core/64-GiB/2-TiB blocker with
  evidence-based same-host scale, memory, current free-space, storage-identity, and measured
  performance admission. Existing fixed-profile evidence remains immutable; append-only
  implementation is deliberately separated from this governance change.
- Append-only measured-host qualification with receipt/schema verification of same-laptop 100M
  layout and feature evidence, transitive current-universe/workstation binding, live free-space
  and NVMe identity preflight, auditable insufficient-space results, and a checked-in qualified
  owner-laptop artifact that leaves Gate 1 pending.

### Safety

- Authenticated access is limited to `POST /v5/fgridbot/validate`; no mutating Bybit operation was
  added and the probe was not run without owner-provided process credentials.
- Raw public market rows remain outside Git; only the bounded sample summary and hashes are kept.
- `grid-live doctor` remains fail-closed while release/live gates are closed.

## 0.1.0 — 2026-07-28

### Added

- Final goal and measurable success criteria.
- Capacity target of 700 instruments × 10 years × 1m.
- High-throughput data-platform architecture.
- Separate history, research, release, and live run modes.
- Immutable strategy-release contract between research and live.
- Backtest, robustness, risk, security, observability, and recovery plans.
- PM-owned acceptance gates and change-control policy.
- Initial ADR set and implementation roadmap.

### Not included

- No application code.
- No API credentials.
- No market data.
- No deployable live system.
