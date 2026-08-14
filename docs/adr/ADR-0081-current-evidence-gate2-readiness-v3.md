# ADR-0081: Current-evidence Gate 2 readiness v3

- Status: accepted
- Date: 2026-08-14
- Supersedes for current review: ADR-0075 readiness classification
- Preserves: immutable v1/v2 evidence, unchanged Gate 2 criteria, and data-quality-owner authority

## Context

The immutable `grid.gate2-readiness-pack/v2` correctly classified the evidence available at its
publication. Three later receipt-bound results now make two v2 blocker descriptions stale:

- one genuine internal candle gap was executed through the bounded repair workflow, but the
  public source returned no row and no replacement was eligible;
- all four retained blocked funding audits were replayed through the unchanged repair admission
  policy, and none contains an eligible isolated integer-multiple cadence sandwich; and
- the 978 canonical candle datasets were registered and selected from one catalog revision with
  exact topology-scoped reconciliation.

Repeating acquisition, repair requests, canonical publication, or catalog registration would add
cost without changing those receipt-bound observations. The Gate 2 criteria and owner authority
must not be edited merely because newer negative evidence exists.

## Decision

Add `grid.gate2-readiness-pack/v3` and
`python -m benchmarks.gate2_readiness_pack_v3` as an append-only, no-network successor. It first
rebuilds the complete v2 verification, then verifies the candle-repair outcome, funding-repair
candidate audit, and full-history catalog result by exact artifact hash, receipt, JSON Schema,
content hash, contract, and status. Cross-checks bind the new evidence to the same capacity,
registry, canonical row, byte, kind, and dataset inventory.

The ordered six Gate 2 criteria and their readiness counts remain unchanged. Only stale blocker
descriptions are replaced:

- `genuine-candle-gap-repair-evidence-missing` becomes
  `candle-repair-source-gap-remains`; and
- `measured-funding-repair-evidence-missing` becomes
  `eligible-funding-repair-candidate-unavailable`.

The deterministic-repair criterion remains blocked: the candle source gap was not repaired, and
the retained funding evidence offers no eligible repair candidate. Lifecycle/cadence/absence
policy and the owner-reviewed end-to-end performance envelope remain blocked exactly as before.
The builder always publishes a negative result before returning exit code 2, keeps Gate 2 closed,
and cannot authorize Phase 3.

## Consequences

- GitHub can reconstruct the current readiness result without repeating any expensive market-data
  or repair operation.
- Reviewers can distinguish missing evidence from measured negative evidence.
- Full-history catalog completion is part of the current source chain but does not imply coverage,
  lifecycle, performance-envelope, research-promotion, or live acceptance.
- The v1 and v2 builders, schemas, artifacts, receipts, and historical classifications remain
  immutable.
- A later positive repair, new eligible funding candidate, owner policy, or qualified performance
  envelope requires another reviewed source set rather than reinterpretation of v3.

## Rejected alternatives

- Edit the v2 artifact or schema: this would invalidate immutable historical evidence.
- Keep evidence-missing blocker names: both would misstate the receipt-bound work already done.
- Mark deterministic repair ready from a blocked candle request or no-candidate funding audit:
  neither proves a successful immutable replacement.
- Mark performance ready from catalog completion without a reviewed envelope: the catalog result
  contains no qualifying end-to-end threshold decision.
