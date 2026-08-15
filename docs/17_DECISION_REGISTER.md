# Decision Register

## Accepted decisions

| ID | Decision | Status | Rationale / evidence required |
|---|---|---|---|
| D-001 | Capacity target is 700 instruments × 10 years × 1m | accepted | Forces architecture for billions of rows from the start |
| D-002 | Real per-instrument history begins at listing and ends at delisting | accepted | Never fabricate unavailable history |
| D-003 | Data, research, release, and live are separate deployables | accepted | Live-only startup and failure isolation |
| D-004 | Live does not require the historical lake or research dependencies | accepted | Small, bounded, safer live runtime |
| D-005 | Research-to-live interface is an immutable promoted strategy release | accepted | Prevent mutable parameter drift and preserve auditability |
| D-006 | Canonical analytical store uses Parquet; DuckDB/Polars are baseline engines | accepted | Columnar, pushdown, parallel, streaming execution; Gate 1 evidence and ADR-0020 |
| D-007 | Partition by UTC calendar month plus eight stable instrument buckets; target 16 MiB files | accepted | Qualified 8-bucket/16-MiB layout and owner decision in ADR-0020 |
| D-008 | Shared features are materialized once; simulation runs on sparse candidates | accepted | Avoid raw-minute × full-parameter cross product |
| D-009 | Core execution/risk arithmetic uses exact Decimal/scaled integers | accepted | Tick/step rounding can change risk and validity |
| D-010 | V1 strategy family is horizontal range, Neutral + Geometric | accepted baseline | Controlled initial scope |
| D-011 | Trailing up/down is disabled in V1 | accepted baseline | Keep research/execution semantics bounded |
| D-012 | One active or uncertain grid per symbol | accepted baseline | Prevent duplicate/conflicting exposure |
| D-013 | Initial real execution requires manual approval | accepted baseline | Reduce early operational risk |
| D-014 | Emergency stop persists until explicit authorized resume | accepted | Restart cannot clear a safety state |
| D-015 | Public data/research runtimes receive no trade credentials | accepted | Least privilege |
| D-016 | Implementation PRs cannot modify their own PM-owned acceptance criteria | accepted | Prevent scope/acceptance drift |
| D-017 | Optimize architecture with measurement before native extensions | accepted | Avoid premature Rust/C++ while retaining stable extension boundaries |
| D-018 | Repository starts documentation-only | accepted | Freeze target architecture before implementation |
| D-019 | V1 downloads and retains one-minute candles and funding, never tick-trade archive bodies | accepted | Owner decision; ADR-0016 and append-only source assessment v2 |
| D-020 | Canonical candle physical representation is `hybrid_int64_decimal` | accepted | Exact physical-contract benchmark and owner decision; ADR-0010/ADR-0020 |
| D-021 | Canonical candle Parquet compression is ZSTD level 3 | accepted | Qualified reference campaign and owner decision; ADR-0020 |
| D-022 | Current owner laptop is the reference research host under evidence-based admission | accepted | Fresh memory/NVMe/free-space/staging preflight remains mandatory; ADR-0019/ADR-0020 |
| D-023 | Gate 1 is accepted and Phase 2 canonical one-minute market-data implementation is open | accepted | Empty-blocker qualified review pack plus explicit owner/PM decision; ADR-0020 |
| D-024 | Bybit-linear v1 uses verified `source_symbol_id` as stable UInt32 `instrument_id`; 1m acquisition uses fixed receipted pages | accepted | Current inventory uniqueness/range evidence and fail-closed resume contract; ADR-0023 |
| D-025 | A completed 1m Landing manifest deterministically identifies one evidence-bound immutable canonical publication | accepted | Receipt/hash substitution resistance, fresh host admission, and idempotent receipt-last publication; ADR-0024 |
| D-026 | GitHub is authoritative for implementation, decisions, contracts, and sanitized receipt-bound runtime evidence; market datasets remain outside Git | accepted | Owner direction, public-repository safety, and reproducible hash bindings; ADR-0025 |
| D-027 | Canonical 1m requested-range audit requires exact Landing parity and accepts no missing-minute reason in v1 | accepted | Gap hashes/samples, lifecycle bounds, negative evidence, and fail-closed Gate 2 separation; ADR-0026 |
| D-028 | A gap repair plan is derived only from a recomputed blocked audit and embeds bounded standard history requests without network or canonical mutation | accepted | Complete gap accounting, Git/hash bindings, standard executor compatibility, and immutable replacement separation; ADR-0027 |
| D-029 | Repair executes only after whole-plan admission; exact returned gaps create a new receipt-last child dataset with explicit parent lineage | accepted | Standard resumable tasks, repeated-empty blocking, exact key-union proof, unchanged parent hashes, and ADR-0028 |
| D-030 | Canonical compaction creates a receipt-last child from one same-partition parent union and exposes observed 16 MiB target/tail facts | accepted | Duplicate rejection, deterministic calibration, logical-hash parity, complete parent lineage, and ADR-0029 |
| D-031 | Canonical metadata registration uses a logical-hash DuckDB catalog; range selection binds an exact catalog snapshot and explicit dataset IDs | accepted | Receipt re-verification, complete lineage, atomic revision chain, no implicit latest, partition/key-overlap rejection, and ADR-0030 |
| D-032 | Canonical funding uses exact Decimal128(38,18) and settlement-derived intervals with receipt-last immutable publication | accepted | Current interval metadata is not historical evidence; predecessor binding, internal delta checks, exact schema, and ADR-0031 |
| D-033 | Public funding acquisition uses a receipted predecessor plus fixed bounded range pages and rejects saturated responses | accepted | Deterministic resume, historical interval derivation, no silent 200-row truncation, fresh capacity admission, and ADR-0032 |
| D-034 | GitHub funding pilot evidence re-verifies exact Landing/Parquet equality and predecessor-derived intervals without publishing rates or observed settlement times | accepted | Reviewable transitive hashes/counts, funding-specific sparse semantics, explicit non-Gate-2 limitations, and ADR-0033 |
| D-035 | Funding coverage audits exact source/canonical parity and stable predecessor-derived cadence; empty windows or undated cadence changes block | accepted | Funding is sparse, current interval metadata is not historical evidence, complete anomaly hashing, and ADR-0034 |
| D-036 | The receipt-verified canonical catalog admits `funding_event` while every snapshot-bound selection remains single-type | accepted | Shared revision/hash semantics, strict funding verifier and key column, no mixed candle/funding request, and ADR-0035 |
| D-037 | Instrument metadata accumulates in an immutable timeline with point-in-time selection separated from ex-post lifecycle coverage | accepted | Later snapshot fields never enter earlier decisions; lifecycle conflicts and partial inventories remain blockers; ADR-0037 |
| D-038 | Multi-month public history acquisition is a receipt-resumable sequential campaign of immutable month/type/eight-bucket child jobs | accepted | Aggregate preflight, deterministic membership, exact child attempt bounds, no pacer multiplication, and ADR-0038 |
| D-039 | A completed public history campaign publishes as a receipt-resumable sequence of immutable canonical child datasets with one aggregate commit | accepted | Maximum single-writer resource bound, fresh child admission, deterministic receipt reuse, full source/canonical lineage verification, and ADR-0039 |
| D-040 | Canonical campaign publication results enter GitHub only through a schema-bound aggregate/per-kind hash projection | accepted | Full source/canonical re-verification without paths, identities, market values, account data, credentials, or implicit Gate 2 acceptance; ADR-0040 |
| D-041 | Multi-dataset coverage is a sequential receipt-bound aggregate of unchanged candle/funding child audits | accepted | Complete campaign membership, child content hashes, summed quality/reasons, strict blocked propagation, and no runtime identity disclosure; ADR-0041 |
| D-042 | Complete-current Bybit linear inventory enumerates the dated normative `PreLaunch`, `Trading`, `Delivering`, and `Closed` status policy | accepted | Exact policy binding, per-filter status parity, genuine rejection remains partial, immutable older evidence, and ADR-0042 |
| D-043 | Public candle/funding acquisition applies one receipt-evidenced global decrease-only pacer to response headers and rate-limit outcomes | accepted | 20% headroom cap, no automatic increase, 429/10006 cooldown, 403 abort/resume boundary, backward-compatible manifests, and ADR-0043 |
| D-044 | Long-run public acquisition evidence requires receipt-bound timing and one sanitized adaptive observation per verified HTTP response | accepted | Strict campaign projection, legacy compatibility, aggregate-only GitHub disclosure, and ADR-0044 |
| D-045 | Long-run evidence distinguishes transport attempts without an HTTP response from classified response observations | accepted | Every completed page response must be covered; bounded no-response retries remain explicit; ADR-0045 |
| D-046 | Completed canonical campaign reuse and evidence may reverify Landing through the full receipt/hash chain without decoding rows | accepted | First publication and coverage retain semantic admission; every source byte/receipt/fact and canonical dataset still verifies; ADR-0046 |
| D-047 | One campaign invocation admits one receipt-verified registry/capacity snapshot and reuses it for every child plan | accepted | Child paths and hashes remain exact; every new execute/resume invocation reloads and reverifies inputs; ADR-0047 |
| D-048 | Full-history funding begins only at the second source-observed settlement after a bounded receipt-resumable backward scan | accepted | The oldest observed event is predecessor-only; registry launch time/current cadence never fabricate boundary evidence; ADR-0048 |
| D-049 | Funding source-boundary results enter GitHub only through a strict aggregate hash/count projection | accepted | Runtime symbols, IDs, rates, observed settlement times, paths, and private facts remain excluded; response accounting must cover every completed page; ADR-0049 |
| D-050 | Narrow exact OHLC envelope violations remain receipt-bound in Landing quarantine and are never admitted to canonical candles | accepted | Re-derived classification, exact source retention, immutable counts/hashes, and blocked canonical coverage; ADR-0050 |
| D-051 | GitHub candle source-quality evidence contains only verified aggregate quarantine counts and binding hashes | accepted | Exact rows, timestamps, identities, paths, and market values remain local; ADR-0051 |
| D-052 | Funding campaigns consume only a receipt-verified discovered source boundary and query the predecessor exactly once | accepted | Boundary/request/registry identity equality, clipped series, and no launch-time or current-cadence inference; ADR-0052 |
| D-053 | Coverage audits classify receipt-bound quarantined candle rows separately and ordinary gap repair rejects them | accepted | Exact runtime key matching, sanitized aggregate reasons, no double-counted missing minute, and ADR-0053 |
| D-054 | Funding compaction creates one receipt-last child from an exact same-partition parent union and validates settlement intervals across parent boundaries | accepted | Deterministic parent/hash lineage, duplicate rejection, unchanged parents, sanitized proof, and ADR-0054 |
| D-055 | Funding repair begins as private, bounded source discovery and does not accept an inferred settlement or cadence | accepted | Recomputed blocked audit, complete isolated `C, N*C, C` admission, ordinary funding requests, fixed limits, and ADR-0055 |
| D-056 | Funding repair discovery executes only after whole-plan admission and passes only on exact source confirmation | accepted | Standard receipt-resumable funding jobs, strict candidate equality, private execution evidence, unchanged parent/audit, and ADR-0056 |
| D-057 | A passed funding repair publishes only as an immutable parent-to-child replacement with sanitized public lineage evidence | accepted | Exact source-confirmed union, recomputed adjacent intervals, receipt-last child, unchanged parent/audit, and ADR-0057 |
| D-058 | A committed funding repair child requires a separate private post-publication source-parity and chronology audit | accepted | Complete lineage reverification, shared fail-closed chronology rules, no mutable-host write gates, and ADR-0058 |
| D-059 | Campaign-resume performance enters GitHub only as scope-bound aggregate evidence with a local fail-closed first-pending stub | accepted | Exact request/plan/input/implementation hashes, no network, no identities/values/paths, and ADR-0059 |
| D-060 | A CloudFront country block is a terminal regional-access failure, not an inferred Bybit IP-frequency ban | accepted | Bounded ephemeral classification, one-attempt global abort, no body retention/bypass/cooldown invention, and ADR-0060 |
| D-061 | Funding compaction candidates are admitted only by an all-pair receipt-verified audit using unchanged ADR-0054 union semantics | accepted | Bounded inventory, no dedup/subset fabrication, private actionable bindings, sanitized aggregate counts, and ADR-0061 |
| D-062 | Gate 2 stale-output behavior is evidenced by offline post-merge fault injection against named production preflights | accepted | Five canonical/catalog cases, marker preservation, zero target mutation, temporary fixtures, sanitized proof, and ADR-0062 |
| D-063 | Current Gate 2 readiness is aggregated without changing criteria, accepting the gate, or authorizing Phase 3 | accepted | Eight fixed receipt/schema/content-hash sources, exact roadmap hash, four blocked criteria, two evidence-ready criteria, and ADR-0063 |
| D-064 | Canonical orphan and partial-write detection is evidenced only in temporary cloned commits | accepted | Candle/funding production verifiers, six named faults, complete tree-fingerprint preservation, sanitized post-merge proof, and ADR-0064 |
| D-065 | Ambiguous same-partition incremental catalog fragments require bounded streaming exact-key admission | accepted | Receipt/file reverification, candle/funding key-column merge, exact duplicate rejection, 4,096-row batches, 128-stream ceiling, and ADR-0065 |
| D-066 | Incremental exact-key selection performance is measured only in bounded temporary production-path fixtures | accepted | Two deterministic selection passes, unchanged store fingerprint, sanitized aggregate evidence, no PM threshold, and ADR-0066 |
| D-067 | A verified zero-admission candle child publishes as one schema-only immutable canonical dataset | accepted | Exact request-derived partition, zero-row Parquet and null bounds, unchanged source lineage, fail-closed coverage, and ADR-0067 |
| D-068 | Exact trade volumes outside Decimal128(38, 4) remain immutable in Landing and are hash-bound exclusions from canonical publication | accepted | No rounding or Landing rewrite; aggregate admission lineage, unaccepted `canonical_representation_overflow`, ordinary-repair rejection, unchanged P-001/Gate 2, and ADR-0068 |
| D-069 | Full-history canonical execution reuses a receipt-bound semantic plan checkpoint | accepted | One aggregate decode, immutable plan bindings, per-child mutation preflight, and ADR-0069 |
| D-070 | Candle-gap topology is diagnosed by one receipt-bound key-only scan | accepted | Exact coverage reconciliation, no source download or gap acceptance, and ADR-0070 |
| D-071 | Official announcement depth is measured with bounded first/declared-last-page requests | accepted | At most 16 public responses, no body persistence, no lifecycle inference, and ADR-0071 |
| D-072 | Announcement archive order uses source `dateTimestamp` without local reordering | accepted | Separate date/publish bounds, lifecycle cross-page checks, and ADR-0072 |
| D-073 | Missing legacy announcement `publishTime` remains absent | accepted | Required `dateTimestamp`, nullable publish bounds, explicit presence counts, and ADR-0073 |
| D-074 | Strict announcement order validation is limited to lifecycle partitions | accepted | Source-order preservation, explicit inversion counts, `new_crypto`/`delistings` checks, and ADR-0074 |
| D-075 | Current Gate 2 readiness is rebuilt from existing evidence without repeating source work | accepted | Twelve exact receipt-bound sources, three evidence-ready and three blocked criteria, seven current blockers, unchanged owner authority, and ADR-0075 |
| D-076 | Verified candle-repair executions receive an identifier-free GitHub projection | accepted | Aggregate limits and hashes, explicit repaired/source-gap-remains classification, immutable parent, idempotent reuse, and ADR-0076 |
| D-077 | Funding repair candidates are classified by replaying the unchanged ADR-0055 planner over explicit receipt-verified audits | accepted | Bounded exact inputs, no request or chronology acceptance, private actionable audit, sanitized aggregate projection, and ADR-0077 |
| D-078 | Full-history catalog registration consumes one receipt-bound file request derived from a verified campaign publication | accepted | Windows-safe 10,000-dataset bound, exact inventory/identity, unchanged catalog preflight and atomic transaction, and ADR-0078 |
| D-079 | A receipt-verified schema-only canonical candle dataset remains explicit in catalog registration and selection | accepted | Zero rows/instruments, null logical bounds, row-qualified DuckDB v1 sentinel encoding, no overlap keys, unchanged coverage policy, and ADR-0079 |
| D-080 | Full-history catalog selection follows the campaign's changing bucket topology and publishes only a sanitized aggregate | accepted | Two contiguous segments per trade/mark kind, exact four-selection union, identifier-free counts/hashes, unchanged missing-partition and Gate 2 policy, and ADR-0080 |
| D-084 | Sequential history campaigns reserve the largest incomplete child rather than summing mutually exclusive Landing peaks | accepted | Unchanged 512 KiB page bounds, fresh before/after-child free-space checks, receipt-safe stop/resume, no request or Gate 2 change, and ADR-0084 |
| D-085 | Reused and disjoint candle campaigns are selected through one receipt-resumable topology-derived bundle | accepted | Whole-month source clips, one catalog verification, unchanged v1 selectors, cross-source instrument/minute disjointness, sanitized aggregate, and ADR-0085 |
| D-090 | Current-universe funding evidence must exactly equal the candle interval union without repeating retained July acquisition | accepted | Boundary-backed new sources, one disjoint reused bounded source, private identity comparison, sanitized receipt-linked aggregate, unchanged cadence/Gate 2 policy, and ADR-0090 |
| D-091 | Current-universe catalog performance is measured by replaying the exact completed private bundle read-only | accepted | Two one-snapshot production batch passes, receipt/schema/hash binding, unchanged catalog/dataset fingerprints, sanitized timings, unchanged owner-reviewed Gate 2 envelope, and ADR-0091 |
| D-092 | Current-universe observations extend the exact immutable v3 Gate 2 decision without repeating its fifteen-source build | accepted | Four receipt/schema/canonical/content-hash sources, exact cross-bindings, unchanged six criteria/seven blockers/closed gate, owner review required, and ADR-0092 |
| D-093 | Concurrent history-campaign progress is observed from receipt-bound metadata without page reads | accepted | One bounded read-only multi-root snapshot, integer progress/rate/ETA, active-lock undercount, explicit non-authoritative scope, and ADR-0093 |
| D-094 | Post-2026-02-26 funding-cadence changes are reviewed against Bybit's dated automatic restoration policy | accepted | Exact official-page markers, receipt-verified audits/Landing, Decimal threshold replay, strict default-hourly-alignment state machine, sanitized aggregates, unchanged Gate 2 owner authority, and ADR-0094 |
| D-095 | Legacy listing-event evidence binds exact official posts to a fully verified oldest-five publication | accepted | Three fixed posts and one-attempt reads, exact private selected-set mapping, aggregate first-candle date reconciliation, explicit two-date ambiguity, unchanged registry/blockers/Gate 2, and ADR-0095 |
| D-096 | Available official lifecycle pages are matched exactly once to the selected campaign without retaining article text | accepted | Complete `new_crypto`/`delistings` page scan, stable totals, exact-order hashing/inversion counts, URL uniqueness, exact symbol-or-pair plus derivative matching, explicit unmatched/ambiguous counts, ADR-0095 binding, unchanged Gate 2 authority, and ADR-0096 |
| D-097 | Gate 2 v4 and later funding/lifecycle evidence are consolidated in one non-promoting owner-review pack | accepted | Exact receipt/schema/content/artifact verification, v4 decision preservation, ADR-0095/0096 cross-binding, reconciled aggregate counts, pending owner dispositions, unchanged seven blockers, and ADR-0097 |
| D-098 | A newly committed acquisition child is semantically admitted once and then receipt-integrity reverified | accepted | Unchanged pre-commit page semantics, receipt-last commit, post-commit page hashes/receipts/allowlist, preserved quarantine keys, no active restart, and ADR-0098 |
| D-099 | Phase 3 features and candidates use one closed-candle decision-time and shared semantic-kernel boundary after Gate 2 | accepted | Explicit catalog/timeline inputs, exact availability time, derived halos, deterministic IDs, batch/kernel parity, immutable lineage, and ADR-0099; implementation remains gated by Gate 2 |
| D-100 | Phase 4 outcomes use exact shared grid/risk authorities and a research-only deterministic simulator after Gate 3 | accepted | Explicit future-path/policy inputs, activation boundary, ambiguity cases, exact accounting, immutable outcome/portfolio lineage, and ADR-0100; P-007/P-008 remain unresolved and implementation gated by Gate 3 |
| D-101 | Phase 5 selection uses an immutable experiment registry, information-interval splits, and append-only final-test lifecycle after Gate 4 | accepted | Registered complete search authority, deterministic trials, purged chronological/out-of-symbol roles, full failure retention, separate Gate 5 decision, and ADR-0101; implementation remains gated by Gate 4 |
| D-102 | Phase 6 separates deterministic release payload, independent verification, and append-only lifecycle registry after Gate 5 | accepted | Non-self-referential content identity, exact allowlist/path bounds, shared dependency-light verifier, explicit promotion/revocation/rollback IDs, risk non-weakening, and ADR-0102; implementation remains gated by Gate 5 |
| D-103 | Phase 7 shadow uses a mutation-free capability graph and transactional exactly-once live-like decisions after Gate 6 | accepted | Explicit release epoch, multi-source closed-candle watermark, bounded kernel replay, read-only reconciliation/control, full parity/soak evidence, and ADR-0103; implementation remains gated by Gate 6 |
| D-104 | Phase 8 manual mainnet uses a separate mutation package, exact single-use approval, and one-attempt uncertainty ledger after Gate 7 | accepted | Environment/account/release/payload binding, fresh validate-before-create, no blind retry, global one active-or-uncertain bot, separate close/emergency authority, and ADR-0104; implementation and every real action remain separately gated |
| D-105 | Phase 9 controlled scale uses immutable one-axis envelopes and atomic account-capacity reservations after Gate 8 | accepted | Complete live/shadow/model cohorts, aggregate/concentration risk, realized cash-flow-adjusted equity highs, separately approved semi-automation, unresolved P-010, non-promoting Gate 9 evidence, and ADR-0105 |

## Decisions requiring benchmark or owner evidence

| ID | Topic | Options | Decision evidence |
|---|---|---|---|
| P-007 | intrabar fill ambiguity policy | conservative bounds, lower timeframe unavailable, event model | simulator review and sensitivity evidence |
| P-008 | exact V1 exit policy | SL-only baseline versus time/condition exit | capital-lock and OOS evidence |
| P-009 | live deployment | dedicated subaccount/host versus temporary main account | owner risk acceptance and API feasibility |
| P-010 | maximum concurrent bots by stage | 1, 3, 10, other | capital/risk/live evidence |
| P-011 | licensing | explicit open-source license or no grant | owner decision before external contributions |

P-006 is resolved by D-019 and ADR-0016: V1 uses verified one-minute sources and excludes
tick-trade archive bodies. Actual per-symbol REST coverage and gaps remain evidence requirements,
not an unresolved source-policy choice.

P-001 through P-005 are resolved by D-006, D-007, D-020 through D-023, and ADR-0020. The selected
pair is eight buckets / 16 MiB with the exact hybrid candle representation and ZSTD level 3. The
reference host remains subject to fresh evidence-based admission rather than fixed nominal
hardware totals.

## Change rule

An accepted decision changes only through:

1. a new or superseding ADR;
2. stated motivation and alternatives;
3. impact on contracts, acceptance tests, migration, and rollback;
4. owner/PM approval;
5. updated references across affected documentation.
