# ADR-0057: Immutable funding repair publication and sanitized execution evidence

- Status: accepted
- Date: 2026-08-14
- Implements: Phase 2 funding repair publication boundary

## Context

ADR-0056 can prove that the official public source returned every settlement inferred by an
ADR-0055 discovery plan. The result remains private because it contains exact instrument and
settlement identities, and it deliberately leaves the incomplete canonical parent unchanged.
Appending the confirmed rows to that parent would violate ADR-0003. Publishing the source rows
without rebuilding the following interval would also retain the very `N*C` chronology defect
that the confirmed settlement explains.

The source-confirmed execution is stronger than an inferred schedule, but it does not retroactively
change the immutable blocked audit or authorize a general historical cadence policy.

## Decision

Add `grid-data publish-funding-repair` and freeze
`grid.canonical-funding-repair-publication/v1`. The default command performs no mutation. It
re-verifies the private plan, execution, original Landing input, registry, capacity evidence, and
canonical parent. Only a complete `passed` execution is eligible.

Publication loads the receipt-verified parent and every receipt-verified repair Landing child,
requires the same exact funding schema and UTC month/bucket, rejects duplicate/overlapping keys,
and proves exact parent-plus-candidate row accounting. It sorts the complete union and recomputes
`funding_interval_minutes` from adjacent source-observed settlement timestamps. The first event
for each instrument must already belong to the parent, so its existing predecessor-boundary
evidence is preserved. Any newly introduced partition boundary or non-whole-minute chronology
fails closed.

The deterministic replacement identity binds the parent manifest, private plan, private
execution, full publication Git identity, and standard funding layout. The child manifest names
the old parent exactly once and binds every repair Landing manifest plus the inherited boundary
evidence. The existing funding writer performs fresh host/resource checks, atomic publication,
and writes the completion receipt last. Parent files are never edited, renamed, or deleted.

Freeze `grid.canonical-funding-repair-replacement/v1` as a receipt-last, GitHub-safe replacement
proof. It exposes only hashes, row counts, inserted/restated interval counts, immutable lineage,
and zero duplicate/unexpected-key facts. It excludes instrument identifiers, settlement
timestamps, funding rates, runtime paths, account data, and credentials.

Add `grid-data funding-repair-execution-evidence` and freeze
`grid.bybit-funding-repair-execution-public/v1` as the separately receipt-verified projection of
either a passed or blocked private execution. It binds the private artifact and upstream hashes,
publishes only aggregate task/request/candidate/result counts, and enforces the same identifier,
timestamp, value, path, account, and credential exclusions.

This transition does not modify or supersede the original blocked audit, accept a historical
schedule change, register a catalog entry, run a private/live endpoint, or close Gate 2. A new
coverage audit over the child remains mandatory.

## Consequences

- Source-confirmed settlements can repair canonical chronology without mutable storage aliases.
- A formerly inflated interval is explicitly restated from the now-complete adjacent chronology;
  funding rate and all other parent values remain exact.
- Negative and positive real executions can be reviewed on GitHub without exposing operational
  market identities.
- Idempotent reruns verify the committed child and evidence instead of overwriting them.

## Rejected alternatives

- Append to the parent: destroys immutable lineage and reproducibility.
- Keep the following parent's old interval: preserves a known chronology inconsistency.
- Copy current `fundingInterval`: undated metadata can leak future information.
- Commit the private execution after removing rates only: symbols and settlement bounds remain
  unnecessary public disclosure.
- Treat publication as cadence acceptance: source confirmation of specific rows is not a dated
  general schedule policy.
