# ADR-0036: Scale-Aligned Candle Audit Series Bound

- Status: accepted
- Date: 2026-08-13
- Extends: ADR-0026 fail-closed canonical coverage audit
- Implements: Phase 2 controlled-scale evidence compatibility

## Context

The `grid.bybit-1m-history-request/v1` contract permits 1 through 700 series so one bounded
monthly/bucket job can represent the planned historical universe. The implementation of
`grid.canonical-1m-coverage-audit/v1` audits every verified series from that request and has no
smaller pilot-only limit. Its JSON Schema nevertheless retained `maxItems: 16`, copied from the
separate sanitized pilot-evidence contract.

The mismatch was exposed by the controlled 50-instrument x 90-day run: the auditor correctly
produced exact, receipt-bound results for 50 series, but the public artifact could not validate
against its declared schema. Reducing the run or splitting one immutable monthly/bucket audit
solely to satisfy the stale schema would make GitHub evidence diverge from the executed job.

## Decision

Keep `grid.canonical-1m-coverage-audit/v1` and raise only its `series.maxItems` JSON Schema bound
from 16 to 700. This is a backward-compatible validation correction aligned with the existing
request contract and executor bound. The audit remains exactly one completed monthly/bucket
publication and must still evaluate every requested series.

The separate `grid.phase2-public-1m-pilot/v1` contract retains its 16-series and 1,000,000-row
limits. Large controlled runs must not be relabelled as pilots. Gap examples remain capped at 20;
the complete gap inventory remains hash-bound as required by ADR-0026.

## Consequences

- Existing audit artifacts remain valid without modification.
- Controlled jobs of up to 700 series can publish schema-valid, receipt-verified audit evidence.
- The correction does not accept any gap reason, alter pass/fail rules, relax lifecycle checks,
  mutate canonical data, or close a PM/risk gate.
- Public audit size grows linearly with the already bounded request inventory; market values,
  runtime paths, credentials, and full gap inventories remain excluded.

## Rejected alternatives

- Raise the pilot contract to 700 series: that would erase the intentional pilot/scale boundary.
- Split one monthly/bucket audit into artificial 16-series summaries: each summary would no
  longer describe the complete publication checked by the auditor.
- Remove the maximum entirely: the acquisition contract already provides an explicit 700-series
  operational bound, so the evidence contract should preserve it.
