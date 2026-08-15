# Strategy Release Contract

## Purpose

The strategy release is the only supported interface from research to live. Live does not read notebooks, experiment directories, arbitrary YAML, or the historical data lake.

ADR-0102 freezes the design-only Phase 6 boundary while Gate 5 remains closed. The immutable
content-addressed payload, independent verification report, and append-only lifecycle registry are
separate artifacts; exact implementation starts only after Gate 5. See the
[M6 implementation plan](../planning/M6_RELEASE_REGISTRY_IMPLEMENTATION_PLAN.md).

## Lifecycle

```text
building → failed
building → complete → verified → promoted → revoked
```

Only `promoted` is eligible for live startup. Revocation blocks new startup and, according to policy, may pause new entries in already-running live instances.

This lifecycle is derived from immutable build/verification artifacts and append-only registry
events. Verification, promotion, revocation, expiry, and rollback never rewrite the payload.

## Immutable directory

```text
strategy-releases/<release-id>/
  release_manifest.json
  artifact_hashes.json
  release_status.json      # immutable build-state snapshot; registry lifecycle is external
  strategy_spec.json
  feature_spec.json
  parameter_table.json
  universe_policy.json
  risk_policy.json
  fee_and_funding_policy.json
  execution_policy.json
  compatibility.json
  validation_summary.json
  validation_evidence/
    fold_metrics.parquet
    stress_summary.json
    concentration_summary.json
    ambiguity_summary.json
    validate_feasibility.json
  provenance/
    dataset_ids.json
    experiment_ids.json
    build_environment.json
```

The exact member set is versioned and allowlisted. Unexpected files are rejected unless the schema explicitly permits them.

## Required identity

- release ID;
- schema version;
- strategy semantic version;
- feature-kernel version;
- parent experiment IDs;
- parent dataset IDs;
- reproducible builder/software identity and external build-receipt reference;
- validity/start policy;
- Gate 5 decision reference; owner promotion is an external registry event;
- content hashes for all required members.

## Strategy specification

Contains immutable decision semantics:

- candle interval and closed-candle rule;
- required rolling warmup;
- candidate formula and thresholds;
- ranking formula;
- one-grid-per-symbol and cooldown behavior;
- native grid mode/type;
- SL and no-entry rules;
- numeric precision/rounding policy reference;
- expected feature names, types, and units.

## Parameter table

Parameters may be global, regime-specific, or instrument-group-specific, but the lookup rules are
explicit and deterministic. The live-consumed table is bounded canonical JSON rather than a
research Parquet dependency. Exact prices, quantities, rates, leverage, investment, and risk values
use declared integer units or canonical decimal strings; binary JSON numbers cannot carry
execution-boundary values.

Each row contains:

- parameter key/group identity;
- applicability conditions;
- range/window parameters;
- grid geometry parameters;
- leverage/investment/risk constraints;
- score thresholds;
- validity and fallback behavior;
- provenance to validation results.

A missing match fails closed unless an explicit safe no-trade fallback is defined.

## Compatibility contract

Live checks:

- release schema version supported;
- feature-kernel version compatible;
- risk-policy version supported;
- native-grid adapter capability present;
- required Bybit fields/endpoints available;
- live configuration does not weaken release limits;
- release has not expired or been revoked;
- all hashes match;
- status and promotion record are valid.

## Independent verification

The verifier is separate from the builder and checks:

- canonical member allowlist;
- no self-referential hash error;
- complete lifecycle status;
- all required hashes;
- dataset/experiment lineage;
- validation gates;
- no missing or failed audits;
- consistent IDs across files;
- parameter/risk compatibility;
- no live secrets or mutable paths;
- deterministic canonical serialization.

The verification report is itself immutable and referenced by the promotion record.

ADR-0102 assigns bounded artifact verification to dependency-light `release-verifier`, shared by
the release verification command and later live admission without importing builder internals.

## Promotion

Promotion is an explicit owner/PM action after review. It records:

- release ID and hash;
- verifier report ID and hash;
- environment target;
- allowed start mode: shadow, manual, or automated;
- active-bot/risk limits;
- approval timestamp and owner identity;
- optional expiry;
- rollback release.

## Revocation

Revocation is append-only and does not alter the release. It records reason, time, owner, and required live response. Revoked releases remain available for audit and replay.
