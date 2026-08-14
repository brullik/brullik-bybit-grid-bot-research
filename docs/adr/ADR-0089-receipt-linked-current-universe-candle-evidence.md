# ADR-0089: Receipt-linked current-universe candle evidence

- Status: accepted
- Date: 2026-08-14
- Extends: ADR-0040, ADR-0041, ADR-0085, and ADR-0088
- Preserves: unchanged Gate 2 criteria, data-quality-owner authority, and Phase 3 prohibition

## Context

The current-universe candle scope reuses five disjoint or time-clipped campaign publications.
ADR-0085 proves that their private dataset union is exact, non-overlapping, and selectable from
one catalog snapshot, but its public projection deliberately does not contain Landing,
publication, coverage, or performance facts. Reviewing those facts as unrelated files would make
cross-source substitution and count drift difficult to detect and would invite repeated runtime
verification or retained-store scans.

Each campaign already has a GitHub-safe Landing, canonical publication, and aggregate coverage
contract. New publications can additionally expose the ADR-0088 receipt-bound execution interval,
while immutable legacy publications remain valid without timing. Funding present in one reused
campaign is outside the candle-only ADR-0085 selection and must not be silently counted as candle
inventory.

## Decision

Add `grid.phase2-current-universe-candle-evidence/v1` and the offline
`python -m benchmarks.current_universe_candle_evidence` builder. The caller supplies one ordered
Landing/publication/coverage triplet for every ADR-0085 source plus the completed public catalog
bundle. Order is significant and must match the private bundle request.

The builder receipt- and schema-verifies every input, recomputes every embedded content hash, and
requires each triplet to share its exact campaign request/plan/manifest, capacity, registry,
publication plan/manifest, and publisher bindings. It recomputes ADR-0085's ordered source-chain
hash from those public bindings. For trade and mark separately, Landing rows, canonical
datasets/files/rows/bytes, coverage datasets/rows, and catalog datasets/objects/rows/bytes must
reconcile exactly. Repeated campaigns, reordered sources, catalog substitution, unknown reasons,
accepted coverage reasons, or any count drift fail closed.

The projection aggregates only identifier-free counts, hashes, quality reasons, acquisition wall
time, and available publication timing. Funding counts are reported separately as excluded from
the candle scope. Legacy publication sources without ADR-0088 timing remain valid and reduce the
reported timing coverage instead of receiving an inferred filesystem or log timestamp.

The pack verifies the evidence chain even when the unchanged coverage audits remain blocked. It
always records `performance.envelope.qualified=false`, requires owner review, performs no gate
decision, and cannot authorize Phase 3. It reads only small public evidence files: no network,
retained market store, DuckDB catalog, private endpoint, credential, order, bot, or transfer is
used.

## Consequences

- One receipt-bound public artifact proves exact current-universe candle inventory and the
  relationship between acquisition, publication, quality, and selection evidence.
- Runtime market data and private topology remain outside GitHub, while source order substitution
  is detected by the existing ADR-0085 chain hash.
- Measured campaign timing becomes reviewable without pretending that incomplete legacy
  publication timing is a qualified end-to-end envelope.
- Funding chronology, missing-history/lifecycle policy, Gate 2 acceptance, research promotion,
  and live execution remain separate decisions.

## Rejected alternatives

- Treat the catalog bundle as coverage evidence: exact selection does not explain missing source
  history or lifecycle bounds.
- Re-open every runtime campaign during the final review: the public receipts and hashes already
  provide the required immutable chain and avoid repeated disk scans.
- Infer legacy publication duration from logs or file timestamps: neither is receipt-bound.
- Sum funding into the candle catalog inventory: ADR-0085 intentionally excludes funding and its
  chronology remains separately governed.
- Mark performance or Gate 2 ready from measured durations alone: the acceptance envelope remains
  an owner-reviewed governance decision.
