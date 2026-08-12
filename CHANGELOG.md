# Changelog

All notable project-governance and architecture changes are recorded here.

## Unreleased

### Added

- Fail-closed canonical 1m coverage audit with exact Landing/Parquet equality, per-series minute
  accounting, bounded hash-bound gap evidence, lifecycle/duplicate/unexpected/unrequested checks,
  immutable blocked evidence, and no automatically accepted absence reason.
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
