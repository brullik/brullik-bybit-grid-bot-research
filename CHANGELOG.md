# Changelog

All notable project-governance and architecture changes are recorded here.

## 0.2.0 — 2026-08-12

### Added

- Independently installable `grid-data`, `grid-research`, `grid-release`, and slim `grid-live` package boundaries.
- Dependency-free exact-decimal market/dataset contracts and versioned JSON Schemas.
- Public-only Bybit V5 adapter with cursor and reverse-time pagination guards.
- Bounded trade/mark/funding feasibility sampler with metadata-derived funding interval,
  exact-decimal validation, gap summaries, content hashes, and a versioned evidence schema.
- Atomic feasibility evidence publication and SHA-256 receipts.
- DuckDB/Polars Parquet layout benchmark harness and architecture tests.
- CI checks for lint, formatting, strict typing, tests, schema/evidence validation, manifest
  integrity, and slim live installation.

### Safety

- No authenticated trading client or mutating Bybit operation was added.
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
