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
