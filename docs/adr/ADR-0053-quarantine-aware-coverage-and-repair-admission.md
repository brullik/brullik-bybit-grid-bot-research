# ADR-0053: Quarantine-aware coverage and repair admission

- Status: accepted
- Date: 2026-08-13
- Extends: ADR-0026, ADR-0027, and ADR-0050

## Context

ADR-0050 preserves a narrowly recognized invalid OHLC source row in receipt-bound Landing while
excluding it from the canonical candle table. The ADR-0026 coverage auditor previously saw only
the resulting absent canonical minute. It therefore classified that absence as
`rest_returned_no_data`, even though the verified Landing page had returned an exact source row.
ADR-0027 could then authorize another ordinary request to the same endpoint for a stable semantic
source defect. That loses the distinction between an absent response row and a rejected response
row and can create a pointless repair loop.

## Decision

Semantic Landing verification exposes the exact `(instrument_id, open_time_ms)` keys of verified
quarantined rows only as an in-process runtime result. Integrity-only verification does not claim
those keys. The coverage auditor already requires semantic verification, so it uses the keys to
classify the complete missing-minute inventory without another page read.

Extend `grid.canonical-1m-coverage-audit/v1` backward-compatibly with the unaccepted reason
`quarantined_source_row`:

- every verified quarantined source row contributes to that reason count and blocks the audit;
- a missing requested minute whose key matches a quarantined row is not also counted as
  `rest_returned_no_data`;
- every other missing requested minute remains `rest_returned_no_data`;
- a quarantined row still blocks if another admitted row happens to carry the same key; and
- every quarantine key must belong to exactly one requested series or the audit fails without
  producing evidence.

Gap ranges, missing-minute totals, and their complete binding hash remain unchanged. The reason
classification explains those gaps; it does not accept, fill, delete, or rewrite one. Existing v1
audits remain valid because the new reason is optional and their immutable bytes are unchanged.

The ADR-0027 planner remains deliberately strict: only a blocked audit whose sole reason is
`rest_returned_no_data` may produce an ordinary REST repair plan. Any
`quarantined_source_row` reason requires a separate reviewed source-reconciliation decision.
Aggregate campaign coverage may expose only the reason count. Exact keys, source rows, symbols,
paths, and market values remain local under ADR-0025 and ADR-0050.

## Consequences

- Coverage evidence distinguishes a returned-but-rejected row from a genuinely absent REST row.
- Stable source anomalies cannot enter an automatic same-endpoint repair loop.
- Canonical data and Gate 2 remain blocked until source reconciliation produces separately
  reviewed evidence and immutable lineage.
- Semantic coverage verification retains exact provenance while GitHub receives only bounded,
  sanitized aggregate facts.

## Rejected alternatives

- Keep `rest_returned_no_data`: it is factually false when the receipt-bound page contains a row.
- Permit ordinary repair anyway: the same stable response is expected to reproduce the defect.
- Publish the quarantine key in aggregate GitHub evidence: it violates the sanitized boundary.
- Mark the minute accepted because the defect is known: explanation is not canonical validity.
