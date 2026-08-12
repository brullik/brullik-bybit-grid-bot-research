# Decision Register

## Accepted decisions

| ID | Decision | Status | Rationale / evidence required |
|---|---|---|---|
| D-001 | Capacity target is 700 instruments × 10 years × 1m | accepted | Forces architecture for billions of rows from the start |
| D-002 | Real per-instrument history begins at listing and ends at delisting | accepted | Never fabricate unavailable history |
| D-003 | Data, research, release, and live are separate deployables | accepted | Live-only startup and failure isolation |
| D-004 | Live does not require the historical lake or research dependencies | accepted | Small, bounded, safer live runtime |
| D-005 | Research-to-live interface is an immutable promoted strategy release | accepted | Prevent mutable parameter drift and preserve auditability |
| D-006 | Canonical analytical store uses Parquet; DuckDB/Polars are baseline engines | accepted pending benchmark | Columnar, pushdown, parallel, streaming execution |
| D-007 | Partition primarily by time plus stable symbol hash bucket | provisional | Avoid a tiny file/partition per symbol; benchmark 8/16/32 buckets |
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

## Decisions requiring benchmark or owner evidence

| ID | Topic | Options | Decision evidence |
|---|---|---|---|
| P-001 | canonical numeric physical representation | Float64, Decimal, scaled integer hybrid | compression, scan speed, exactness benchmark |
| P-002 | symbol bucket count | 8, 16, 32 | single-symbol and all-universe scan benchmark |
| P-003 | target Parquet file size | 128, 256, 512 MB | cold/warm scan and repair/compaction cost |
| P-004 | compression | ZSTD levels; optional Snappy comparison | size/throughput benchmark |
| P-005 | reference research hardware | 32/64/128 GB RAM; core count; NVMe size | end-to-end benchmark and budget |
| P-006 | source coverage | official bulk archives versus REST gaps | authoritative inventory by symbol/time/source |
| P-007 | intrabar fill ambiguity policy | conservative bounds, lower timeframe unavailable, event model | simulator review and sensitivity evidence |
| P-008 | exact V1 exit policy | SL-only baseline versus time/condition exit | capital-lock and OOS evidence |
| P-009 | live deployment | dedicated subaccount/host versus temporary main account | owner risk acceptance and API feasibility |
| P-010 | maximum concurrent bots by stage | 1, 3, 10, other | capital/risk/live evidence |
| P-011 | licensing | explicit open-source license or no grant | owner decision before external contributions |

## Change rule

An accepted decision changes only through:

1. a new or superseding ADR;
2. stated motivation and alternatives;
3. impact on contracts, acceptance tests, migration, and rollback;
4. owner/PM approval;
5. updated references across affected documentation.
