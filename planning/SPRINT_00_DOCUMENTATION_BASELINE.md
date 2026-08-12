# Sprint 00 — Documentation and Architecture Baseline

## Motivation

Freeze the final goal, high-scale architecture, runtime isolation, safety boundaries, and delivery gates before production code is written.

## Scope

- final goal and measurable success criteria;
- 700 instruments × 10 years × 1m capacity model;
- independent data/research/release/live applications;
- data, performance, research, simulator, release, and live architecture;
- security/risk/recovery;
- repository layout and contracts;
- governance, roadmap, backlog, and ADR baseline;
- public GitHub-ready documentation package.

## Non-goals

- no Python or other application code;
- no API calls from repository artifacts;
- no historical data download;
- no parameter selection;
- no backtest result;
- no live/trade credential setup;
- no open-source license decision on behalf of the owner.

## Acceptance criteria

- [ ] Final goal is prominent in English and Russian READMEs.
- [ ] Exact capacity math is documented: 3,681,644,400 trade candles and 7,363,288,800 trade+mark rows.
- [ ] Real history follows listing/delisting; no fabricated pre-listing history.
- [ ] `grid-data`, `grid-research`, `grid-release`, and `grid-live` are independent.
- [ ] Live can start without historical/research dependencies.
- [ ] Parquet/DuckDB/Polars baseline and benchmark-gated physical layout are documented.
- [ ] Candidate sparsification/materialized shared features avoid combinatorial raw scans.
- [ ] Immutable dataset/release lifecycle and receipts are documented.
- [ ] Live uncertainty, reconciliation, emergency, and fail-closed behavior are documented.
- [ ] Roadmap blocks real execution until evidence gates pass.
- [ ] Repository contains documentation/governance only, no trading code.
- [ ] All relative Markdown links resolve.
- [ ] Package has a deterministic file manifest and clean initial Git commit.

## Deliverables

See repository README documentation map and `MANIFEST.sha256`.
