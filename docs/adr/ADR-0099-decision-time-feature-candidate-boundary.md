# ADR-0099: Decision-time feature and candidate boundary

- Status: accepted
- Authority: design-only; implementation gated by Gate 2
- Date: 2026-08-15
- Extends: ADR-0001, ADR-0002, ADR-0005, ADR-0013, and ADR-0037
- Preserves: Gate 2 authority, no-lookahead, immutable lineage, and live isolation

## Context

The roadmap permits later-phase design before its implementation gate. M1 proved a bounded
lookahead-safe Polars workload with deterministic halos, but explicitly did not define the Phase 3
production contract. The repository currently has only an offline `grid-research doctor`
scaffold. Logical feature and range-candidate fields are documented, while their decision-time
meaning, input authority, shared-kernel boundary, shard ownership, deterministic identities, and
implementation order are not yet frozen.

Implementing those details ad hoc after Gate 2 would create avoidable delay and could let batch
research and future live evaluation diverge. Implementing code now would violate the closed Gate
2 boundary.

## Decision

### Authority and activation

ADR-0099 is design-only while Gate 2 is closed. No feature/candidate package, schema, CLI, derived
dataset, or acceptance result is authorized by this ADR. Phase 3 implementation starts only after
an explicit Gate 2 owner decision.

Every later research build must select explicit, complete, receipt- and hash-verified market
dataset IDs from one catalog revision/content hash. It must also bind one verified point-in-time
instrument timeline. An implicit `latest` catalog or metadata lookup is forbidden.

### Decision time

A canonical one-minute candle with `open_time_ms=t` covers `[t, t + 60_000)` and becomes logically
available only at `t + 60_000`. Its feature row therefore uses:

```text
as_of_open_time_ms = t
decision_time_ns = (t + 60_000) * 1_000_000
```

The row may use that just-closed candle and earlier evidence only. Processing, signal, approval,
and execution latency are later simulator/live inputs; they may delay action but never move the
logical decision time earlier. Mutating any source row, funding event, metadata snapshot, or
configuration strictly after `decision_time_ns` must not change the row or its candidate result.

The metadata selector is the latest snapshot satisfying
`snapshot_time_ms <= decision_time_ns // 1_000_000`. Funding and cross-market context obey the
same availability boundary. Before the first eligible snapshot, or when required evidence is
missing, the feature build may retain an explicit incomplete row for audit but the candidate
detector must reject it. Future/current metadata may not fill historical gaps.

### Component boundary

The future `packages/feature-kernel` is a deterministic, side-effect-free semantic package. It
depends only on stable contracts and has no filesystem, network, catalog, Polars, DuckDB,
`grid-data`, `grid-research`, simulator, release, private-Bybit, or live orchestration dependency.
It owns rolling state transitions, feature formulas, finite/null rules, warmup/data-quality facts,
and candidate-rule primitives shared by batch research and a later live consumer.

`apps/research` owns read-only catalog admission, bounded batch/shard orchestration, optional
Polars acceleration, immutable feature/candidate publication, audits, and performance evidence.
An accelerated batch implementation is not an independent semantic authority: golden and
generated parity fixtures must reconcile it with the shared kernel before publication.

### Shards and halos

Each feature version declares its complete dependency graph and derived
`required_halo_minutes`, including lagged rolling values. One shard may read only:

```text
[core_start - required_halo, core_end)
```

clipped to verified source availability. It writes only rows in `[core_start, core_end)`. Core
intervals are non-overlapping and gap-free for the requested build. A row is owned by exactly one
core shard; halo rows are read-only and never published by that shard. Sharded and unsharded
results over the same explicit input must reconcile in canonical key order.

Missing required minutes, unresolved quality flags, incomplete warmup, unsupported source joins,
or absent point-in-time metadata remain explicit reason codes. They are never silently
forward-filled, zero-filled, or converted into eligible candidates.

### Numeric and identity boundary

Absolute market/grid bounds retained by feature or candidate rows use exact canonical price units.
Normalized analytical fields may use a version-declared finite numeric encoding, but NaN and
infinity are forbidden and the contract must define formulas, nulls, comparison policy, and
batch/shared-kernel parity. A value within a declared comparison ambiguity band cannot be silently
classified differently; it is rejected or reported as indeterminate. No binary floating-point
value may cross the later tick/quantity execution boundary without exact Decimal/integer-step
reconstruction and validation.

Feature datasets bind their feature contract, formula/configuration hash, required halo, ordered
parent dataset IDs, catalog revision/content hash, timeline hash, kernel identity, batch adapter
identity, and audit hashes. Candidate datasets bind the complete feature dataset and rule/config
hash. Candidate identity is independent of shard/output order:

```text
candidate_id = sha256(canonical_json({
  candidate_contract,
  feature_dataset_id,
  feature_contract,
  category,
  instrument_id,
  decision_time_ns,
  candidate_rule_id,
  candidate_config_sha256
}))
```

Exact persisted schemas and formulas are delivered in the first post-Gate-2 implementation PR;
they are append-only versioned contracts and may not reinterpret the M1 benchmark artifacts.

## Consequences

- Phase 3 can begin with a fixed authority and dependency direction immediately after Gate 2.
- Batch performance can use columnar acceleration while one small semantic kernel remains suitable
  for later live parity.
- No future candle, funding event, metadata, shard overlap, implicit catalog revision, or output
  ordering can become hidden candidate input.
- Candidate thresholds, range definitions, deduplication policy, and numeric encodings remain
  versioned Phase 3 research decisions; this ADR does not choose them from future outcomes.
- Gate 2, Gate 3 criteria, PM-owned tests, Phase 3 authorization, simulator work, release work,
  private endpoints, and live permissions remain unchanged.

## Rejected alternatives

- Implement Phase 3 before Gate 2: this bypasses the accepted roadmap authority.
- Let `grid-research` own separate feature semantics: batch/live parity would become optional.
- Put Polars, DuckDB, or market-store access in the shared kernel: slim future live installation
  would inherit research/storage dependencies.
- Use candle open time as availability time: that leaks the still-forming candle.
- Select the latest catalog or current instrument registry at runtime: reruns would drift and
  historical decisions could observe future metadata.
- Hard-code candidate thresholds in this design ADR: they require registered Phase 3 evidence and
  must be frozen before final-test inspection.
