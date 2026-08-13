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
