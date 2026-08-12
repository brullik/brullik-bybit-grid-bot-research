# ADR-0026: Fail-Closed Canonical Coverage Audit

- Status: accepted
- Date: 2026-08-12
- Implements: Phase 2 source-parity and requested-range audit boundary

## Context

A valid canonical receipt proves immutable files, schemas, hashes, and aggregate statistics. It
does not prove that the canonical values equal their verified Landing source or that every minute
inside the requested ranges is present. Gate 2 separately requires duplicate/conflict freedom and
coverage explained by lifecycle metadata; the implementation may not declare an unexplained
absence acceptable merely because Bybit returned no row.

Audits must remain useful on incomplete data. A detected gap is evidence to preserve, not a reason
to throw away the entire audit or silently synthesize a candle.

## Decision

Freeze `grid.canonical-1m-coverage-audit/v1` for one completed monthly/bucket publication. The
read-only auditor re-verifies the Landing job, registry and capacity receipts, deterministic
publication specification, canonical manifest/receipt, Parquet hashes/footer/schema, and both the
publisher and auditor full Git commit identities.

It reads the canonical Parquet table and compares it exactly with the Arrow table reconstructed
from the verified Landing pages. For every requested series it records expected and observed row
counts, duplicate keys, timestamps outside the range, registry lifecycle-bound result, missing
minutes, and contiguous gap-range count. It also counts rows belonging to no requested series.

The complete deterministic gap-range list is bound by SHA-256. At most 20 ranges are embedded as
diagnostic examples, keeping GitHub evidence bounded; repair recomputes and verifies the full list
rather than trusting a truncated sample.

No absence reason is accepted in v1. A minute absent from a complete, receipt-verified REST page
is observed as `rest_returned_no_data`, remains in `unaccepted_reason_codes`, and produces
`status=blocked`. `status=passed` requires exact Landing/canonical equality, exact requested row
coverage, zero missing/duplicate/conflicting/unexpected/unrequested rows, and all requested bounds
inside the verified registry snapshot. The audit writes canonical evidence and a receipt last even
when blocked, and its CLI exits non-zero for blocked status.

This is requested-range evidence only. It does not prove that the current registry contains the
complete historical universe or that the requested start/end are the exchange's exact historical
lifecycle boundaries. It does not repair, compact, catalog, or close Gate 2.

## Consequences

- Canonical publication and data-quality acceptance are separate, independently verified steps.
- Missing REST rows cannot be treated as confirmed no-trade intervals without a later governance
  decision and evidence contract.
- A source/canonical value mismatch, extra row, or substituted software/evidence identity fails
  closed.
- Blocked audits are immutable negative evidence suitable for deterministic repair planning.
- The current successful two-symbol pilot can be audited after this code is merged and identified
  by its immutable merge SHA; that measured result belongs in a separate evidence PR.

## Rejected alternatives

- Infer completeness from manifest row count: it cannot locate internal missing minutes.
- Accept every empty REST minute: source absence does not prove a legitimate market interval.
- Store every gap in the public summary: pathological input can make the evidence unbounded.
- Audit only Parquet metadata: metadata cannot prove exact value parity with Landing.
- Modify or delete a canonical dataset after a failed audit: committed data remains immutable and
  repair must publish explicit lineage.
