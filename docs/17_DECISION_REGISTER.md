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
