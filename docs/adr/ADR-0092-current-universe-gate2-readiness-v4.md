# ADR-0092: Current-universe Gate 2 readiness v4

- Status: accepted
- Date: 2026-08-14
- Extends: ADR-0081, ADR-0089, ADR-0090, and ADR-0091
- Preserves: immutable prior evidence, unchanged Gate 2 criteria/blockers, and owner authority

## Context

The accepted `grid.gate2-readiness-pack/v3` remains the current six-criterion Gate 2 decision:
three criteria are evidence-ready, three are blocked, and seven blocker codes keep Gate 2 closed.
The current-universe candle, funding, and catalog-performance workflows will produce later
receipt-bound observations over a materially broader retained dataset. Rebuilding v3's fifteen
older source chains after those workflows finish would repeat verification without changing their
accepted classification, while interpreting the new observations as automatic acceptance would
bypass the data-quality owner.

A successor therefore needs to bind the new evidence to the exact immutable v3 decision, expose
only review-safe aggregates, and reject any attempt to alter criteria, blocker codes, readiness
counts, or Phase 3 authorization.

## Decision

Add `grid.gate2-readiness-pack/v4` and the offline
`python -m benchmarks.gate2_readiness_pack_v4` builder. It verifies the exact v3 artifact plus the
current-universe candle, funding, and catalog-performance artifacts by receipt, JSON Schema,
canonical encoding, content hash, contract, status, and artifact hash. It then requires:

1. candle and funding capacity/registry bindings and instrument counts to agree;
2. funding evidence to bind the supplied candle artifact;
3. catalog-performance evidence to bind the candle bundle and exact catalog revision/hash;
4. trade/mark catalog inventory to equal the measured dataset/object/row/byte inventory;
5. deterministic repeat and before/after retained-state equality to be true;
6. candle and funding duplicate, conflict, lifecycle, unexpected-time, and unrequested-row
   contradictions to remain zero; and
7. the complete v3 criteria, readiness counts, ordered blocker set, closed Gate 2 decision, and
   storage policy to remain unchanged.

The output contains only source hashes, aggregate counts/timings, quality totals, and explicit
owner-review state. It records that the current-universe evidence was reconciled, but does not
reinterpret it as a qualified end-to-end envelope or lifecycle/cadence/absence policy. The
builder publishes the negative readiness artifact before returning exit code 2.

## Consequences

- The post-download owner review can start from one receipt-bound GitHub artifact without
  repeating the fifteen v3 source operations or any Bybit request.
- Source substitution, catalog drift, inconsistent universe scope, data-quality contradiction,
  or modified Gate 2 semantics fails closed before publication.
- V1 through v3 artifacts and schemas remain immutable historical evidence.
- Gate 2 remains closed with three blocked criteria and seven blockers until separately reviewed
  evidence/policy changes justify a new governance decision; v4 cannot authorize Phase 3.

## Rejected alternatives

- Rebuild v3 from all historical sources: correct but redundant and slower after the expensive
  current-universe work finishes.
- Edit or reinterpret the v3 artifact: violates immutable evidence and owner authority.
- Mark performance ready from component throughput alone: the reviewed end-to-end envelope is
  intentionally broader than catalog selection.
- Embed private bundle, dataset, instrument, or time-range details: GitHub evidence needs only
  cryptographic bindings and sanitized aggregates.
