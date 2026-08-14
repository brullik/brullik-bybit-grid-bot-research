# Changelog

All notable project-governance and architecture changes are recorded here.

## Unreleased

### Added

- ADR-0094 and `grid.phase2-funding-cadence-policy-evidence/v1`: one exact official announcement
  response and paired receipt-verified funding audit/Landing chains are replayed with Decimal
  threshold and schedule-alignment semantics, producing only sanitized aggregates and leaving the
  immutable audits, Gate 2 blocker set, owner decision, and Phase 3 authorization unchanged.
- ADR-0093 and `grid-data history-campaign-progress`: one bounded read-only invocation verifies
  receipt-bound metadata and reports page-weighted progress, recent rate, ETA, and free space for
  up to sixteen campaigns without reading Landing pages, making requests, writing runtime state,
  or changing Gate 2.
- ADR-0092 and `grid.gate2-readiness-pack/v4`: the immutable v3 decision can be chained to
  receipt-bound current-universe candle, funding, and catalog-performance observations without
  repeating prior source work, changing seven blockers, opening Gate 2, or authorizing Phase 3.
- ADR-0091 and `grid.phase2-current-universe-catalog-performance/v1`: the completed private
  catalog bundle can be selected twice through the production batch boundary with receipt/schema
  verification and before/after retained-state fingerprints, publishing only sanitized measured
  throughput without changing the owner-reviewed Gate 2 envelope.
- ADR-0090 and `grid.phase2-current-universe-funding-evidence/v1`: one offline receipt-linked pack
  proves exact per-symbol interval parity between the current candle bundle and four
  boundary-backed plus one retained bounded funding source, without repeating acquisition or
  changing Gate 2.
- ADR-0089 and `grid.phase2-current-universe-candle-evidence/v1`: one offline receipt-linked pack
  reconciles ordered Landing/publication/coverage triplets with the exact multi-campaign catalog
  bundle while keeping funding, performance-envelope acceptance, Gate 2, and Phase 3 separate.
- Receipt-verified post-merge Gate 2 readiness v3 evidence bound to `97cf471`: all fifteen source
  chains verify offline, the unchanged result remains three evidence-ready and three blocked
  criteria with seven current blockers, Gate 2 stays closed, and Phase 3 authorization is false.
- ADR-0088 receipt-bound canonical campaign publication timing: a plan-bound immutable execution
  start survives resume, current manifests and sanitized evidence expose exact wall time, and
  legacy completed publication roots remain valid without migration.
- ADR-0087 and an opt-in bounded history-campaign supervisor that automatically receipt-resumes
  only classified DNS/socket/HTTP-5xx interruptions while preserving explicit rate-limit,
  regional-access, contract, capacity, and unknown-failure stop conditions.
- ADR-0086 and a preordered, single-parse canonical candle publication path that preserves exact
  Landing/admission/Arrow contracts, rejects order drift, and avoids a global sort or full admitted
  key set on multi-million-row history children.
- ADR-0085 and a receipt-resumable multi-campaign catalog selection bundle that derives exact
  topology segments, rejects overlapping source key space, verifies one catalog snapshot, and
  publishes only an identifier-free aggregate without repeating Bybit acquisition.
- ADR-0084 sequential peak-child history-campaign admission: full-history bootstrap no longer
  reserves mutually exclusive child Landing maxima at once, while unchanged per-page bounds and
  fresh before/after-child free-space checks retain fail-closed, receipt-resumable execution.
- Receipt-verified post-merge ADR-0083 throughput evidence: the unchanged 100-page/10-RPS public
  workload completed at 9.709345 requests/second, 1.250496x the prior confirmation, with the same
  aggregate response hash, zero errors, and no retained market values.
- ADR-0083 and a bounded standard-library HTTPS/1.1 connection pool for high-volume public REST
  acquisition, preserving the existing global RPS pacer, retry ceilings, receipts, and resume
  behavior while reusing successful sessions across sequential campaign children.
- Platform-independent source-manifest hashing over Git-canonical LF bytes, eliminating false
  Windows CRLF drift without weakening file coverage or SHA-256 verification.
- Receipt-verified post-merge full-history catalog performance evidence: four concurrent
  production selectors reconcile 978 datasets and 30,832,334 rows in 22.307 seconds on the first
  pass and preserve the retained store without repeating acquisition or registration.
- ADR-0082 and `grid.phase2-full-history-catalog-performance/v1`: a read-only two-pass production
  selector measurement over the existing four receipt-bound full-history topology requests,
  without repeating download, publication, repair, or catalog registration and without changing
  Gate 2.
- ADR-0081 and append-only Gate 2 readiness v3 implementation: the complete v2 source chain plus
  measured candle-repair, funding no-candidate, and full-history catalog evidence can be verified
  offline without repeating expensive work; criteria remain unchanged and Gate 2 stays closed.
- Receipt-verified full-history catalog evidence bound to merge `bd79038`: one revision-5
  registration and four topology-scoped selections reconcile 978 datasets/objects, 268
  schema-only datasets, 30,832,334 rows, and 529,794,759 bytes without publishing identities.
- ADR-0080 and `grid.phase2-full-history-catalog/v1`: four receipt-bound topology-scoped private
  selections reconcile exactly to one 978-dataset catalog registration while GitHub receives only
  hashes, aggregate counts, safety claims, and unchanged Gate 2 limitations.
- ADR-0079 and backward-compatible catalog admission for receipt-verified schema-only candle
  partitions, including coherent null-bound evidence, deterministic empty-object selection, and
  fail-closed zero-row physical encoding in existing DuckDB v1 catalogs.
- ADR-0078 and a receipt-bound file-backed catalog registration request derived from a fully
  verified campaign publication, removing the Windows command-line limit for 978 full-history
  datasets while preserving the existing preflight and atomic catalog transaction.
- Receipt-verified funding repair candidate evidence: all four retained blocked audits and 11
  cadence transitions were recomputed offline, none admits ADR-0055 discovery, and the resulting
  zero-request aggregate prevents repeated Bybit attempts without accepting chronology.
- ADR-0077 and a receipt-verified funding repair candidate audit that replays unchanged ADR-0055
  admission over all explicitly supplied blocked audits, prevents repeated ineligible Bybit
  attempts, and emits an identifier-free aggregate without changing Gate 2.
- Receipt-verified candle repair outcome: one bounded public request returned zero rows for the
  genuine one-minute gap; the source gap remains, the parent is unchanged, no replacement was
  published, and the sanitized artifact prevents wasteful retries.
- ADR-0076 and `grid.bybit-1m-gap-repair-execution-public/v1`: a receipt-reverified,
  identifier-free GitHub projection records exact repair completion or a persistent source gap,
  while preserving the private execution as the no-repeat marker and keeping Gate 2 closed.
- Receipt-verified Gate 2 readiness v2 evidence bound to merge `847de3e`: all twelve source chains
  verify offline, three criteria are evidence-ready, three remain blocked by seven current codes,
  Gate 2 stays closed, and automatic Phase 3 authorization remains false.
- ADR-0075 and `grid.gate2-readiness-pack/v2`: one offline pass verifies twelve existing
  receipt-bound artifacts, retires only the now-false incomplete-campaign/publication blockers,
  preserves seven current repair/lifecycle/cadence/absence/performance blockers, and keeps Gate 2
  closed without repeating Bybit downloads or retained-store scans.
- Receipt-verified official announcement-depth evidence: 15 one-attempt public responses prove
  all five selected registry launch bounds precede the `new_crypto` declared-last-page minimum in
  June 2022; exact instrument lifecycle remains unproven and Gate 2 stays closed.
- ADR-0074 lifecycle-scoped order evidence: source order is preserved for all announcement types,
  inversions are counted, and strict first/last date ordering is required only for the
  `new_crypto`/`delistings` partitions used by the depth diagnostic.
- ADR-0073 legacy announcement compatibility: `dateTimestamp` remains required, absent historical
  `publishTime` stays absent, and public evidence exposes presence counts plus nullable bounds.
- ADR-0072 source-order correction: official announcement pages are validated by descending
  `dateTimestamp`, retain separate date/publish bounds, and never locally reorder source items.
- ADR-0071 and a bounded official-announcement archive-depth command that replaces full archive
  downloads with at most 16 first/last-page responses, hashes but does not persist announcement
  bodies, and fails closed without turning archive depth into lifecycle acceptance.
- Receipt-verified ADR-0070 full-history boundary evidence: one 203,043 ms offline diagnostic
  reused 978 verified canonical datasets, scanned 30,832,334 instrument/time keys once, and
  reconciled 11,981,670 leading, 76 internal, zero trailing, and zero fully absent minutes to the
  unchanged blocked semantic audit.
- ADR-0070 and a receipt-bound candle boundary diagnostic that reuses already verified canonical
  datasets, scans only instrument/time columns once, reconciles exact topology with the prior
  semantic coverage audit, performs no download or Landing row decode, and keeps every absence
  unaccepted.
- Receipt-verified full-history Landing evidence: five current linear symbols, 103 months, 978
  jobs, 43,328 pages, 30,832,408 admitted rows, one quarantined source row, 96 retries, and
  explicit incomplete response-header coverage without private identities or market values.
- Receipt-verified full-history canonical publication evidence: 978 immutable datasets/files,
  30,832,334 admitted rows, 74 exact representation exclusions, 529,794,759 Parquet bytes, and a
  complete source/canonical integrity chain bound to merge `85440ea`.
- Receipt-verified full-history coverage evidence: 696 datasets passed and 282 remain blocked by
  11,981,671 REST no-data minutes, 74 canonical representation overflows, and one quarantined
  source row; no unknown, duplicate, conflicting, unrequested, lifecycle, or timestamp reasons
  were observed, and Gate 2 remains closed.
- ADR-0069 prepared canonical-campaign plans: one explicit full semantic planning pass persists
  only a receipt-bound aggregate checkpoint, while fast execute/resume verifies its immutable
  bindings and retains a fresh full semantic preflight immediately before every child mutation.
- ADR-0066 and an offline incremental catalog-selection benchmark that measures two production
  exact-key passes over bounded temporary fragments, proves deterministic output and unchanged
  store fingerprints, and emits only sanitized aggregate evidence without a Gate 2 threshold.
- Receipt-bound ADR-0066 post-merge evidence over 368,640 exact keys: 451,584 rows/second on the
  first selection and 457,972 rows/second on the immediate repeat, with deterministic selection,
  unchanged store fingerprints, and automatic fixture removal.
- ADR-0065 bounded exact-key catalog admission: disjoint multi-instrument incremental candle and
  funding fragments now use a 4,096-row streaming merge only when file bounds are ambiguous,
  reject exact duplicates/conflicts, and fail closed above 128 simultaneous fragment streams.
- Post-merge canonical integrity evidence bound to merge `d38ed8e`: all six candle/funding orphan,
  missing-Parquet, and missing-receipt cases were detected and preserved byte-for-byte at the tree
  level without retained-store or network access.
- ADR-0064 offline canonical integrity fault injection: six candle/funding orphan, missing-Parquet,
  and missing-receipt cases against production verifiers, with complete injected tree preservation
  and no retained-store, network, private, or live access.
- Post-merge Gate 2 readiness evidence bound to merge `b58e039`: all eight fixed source chains
  verify, two of six criteria are evidence-ready, four remain blocked by seven explicit blockers,
  Gate 2 remains closed, and automatic Phase 3 authorization remains false.
- ADR-0063 and a non-promoting Gate 2 readiness-pack builder that verifies the unchanged six
  criteria and eight exact receipt/schema/content-hash evidence sources, retaining four blocked
  criteria, two evidence-ready criteria, seven blockers, and mandatory data-quality-owner review.
- Post-merge stale-output fault-injection evidence bound to merge `5ba2811`: all five named
  production preflight cases detected and preserved their injected marker, with zero target
  mutations, zero network access, and a receipt-verified sanitized artifact.
- ADR-0062 offline stale-output fault injection: five named production preflight boundaries,
  unchanged marker preservation, zero target mutation, temporary fixtures, and schema-bound
  post-merge evidence without network, private/live capability, paths, or market values.
- Receipt-verified current-store funding compaction candidate evidence: 37 canonical datasets,
  35 partitions, three duplicate/conflicting pairs, zero eligible pairs, and no published runtime
  identities, funding values, paths, private calls, mutation, or fabricated compaction input.
- ADR-0061 funding compaction candidate audit: bounded all-pair receipt verification, unchanged
  duplicate/interval rejection, private actionable identities, sanitized aggregate evidence, and
  no fabricated compaction input or Gate 2 implication.
- ADR-0060 regional public-API block classification: bounded ephemeral CloudFront-body
  classification, one-attempt global abort, no invented IP-ban cooldown, no stored response body,
  no alternate-host retry, and unchanged handling for genuine Bybit rate-limit 403 responses.
- ADR-0059 sanitized campaign-resume performance evidence: exact scope/input/implementation
  bindings, aggregate integrity/reuse timing, local one-call fail-closed stub, and no network,
  instrument identity, market value, path, device, account, credential, or Gate 2 implication.
- ADR-0058 post-publication funding repair coverage audit: receipt-verifies the complete repair
  lineage, proves exact source-union/canonical parity, re-runs fail-closed chronology checks, and
  keeps detailed identifier/time evidence private without mutable-host write gates.
- ADR-0057 immutable funding repair publication and sanitized execution evidence: passed-only
  exact parent-plus-confirmed-row union, recomputed adjacent settlement intervals, receipt-last
  child lineage, unchanged parent/audit, and GitHub-safe identifier/value-free projections.
- ADR-0056 bounded funding repair discovery execution: no-mutation whole-plan preflight,
  sequential standard public funding Landing jobs, exact candidate confirmation, receipt-based
  resume, private rate-free execution evidence, and unchanged canonical parent/audit.
- ADR-0055 fail-closed funding repair discovery planning: a receipt-verified blocked audit may
  produce bounded ordinary public funding requests only when every interval change is an isolated
  integer-multiple `C, N*C, C` sandwich; candidates remain private, unaccepted, and unexecuted.
- ADR-0052 funding source-boundary admission: campaign preflight re-verifies ADR-0048 receipts,
  requires exact registry/symbol/range/identity compatibility, clips each funding series to its
  proven start, and binds the exact oldest predecessor into the first child boundary request.
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

- Current-universe funding evidence now compares the boundary's required sorted symbol list with
  the campaign's unique source-order list by exact membership, preventing a false scope mismatch
  without weakening range or identity checks.
- Resumed history campaigns now use ADR-0046 receipt-integrity verification for already completed
  Landing children and reuse each verified result within the same preflight/execute invocation;
  partial children and explicit semantic verifiers still decode and validate every source row.
- Public REST transport now classifies TLS record/read failures (`ssl.SSLError`) as bounded
  retryable transport failures, preserving page-level attempt ceilings and campaign resume.
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
