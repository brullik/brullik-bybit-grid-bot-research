# Changelog

All notable project-governance and architecture changes are recorded here.

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
- CI checks for lint, formatting, strict typing, tests, schema/evidence validation, manifest
  integrity, and slim live installation.

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
