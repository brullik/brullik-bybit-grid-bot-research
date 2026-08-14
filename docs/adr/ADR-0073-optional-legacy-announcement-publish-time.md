# ADR-0073: Optional legacy announcement publish time

- Status: accepted
- Date: 2026-08-14
- Amends: ADR-0071/ADR-0072 legacy announcement-field semantics
- Order-validation scope amended by: [ADR-0074](ADR-0074-lifecycle-scoped-announcement-order-evidence.md)

## Context

The first ADR-0072 post-merge run passed current-page ordering and then failed closed on the
declared last `new_crypto` page. Timestamp-only shape inspection showed that every 2022 legacy row
had a valid descending integer `dateTimestamp` and the requested type, but omitted the newer
`publishTime` member entirely.

Requiring a field that the official archive did not backfill would prevent the diagnostic from
measuring exactly the legacy depth it exists to assess. Substituting `dateTimestamp` into
`publishTime` would fabricate source data and blur the ordering distinction established by
ADR-0072.

## Decision

Require every announcement row to carry a non-negative integer `dateTimestamp` and the requested
type. Accept `publishTime` as an optional legacy field: when present it must still be a
non-negative integer; when absent it remains absent and is never synthesized.

Each type probe records first/last-page counts of rows that actually contain `publishTime`.
Its oldest/latest publish bounds are nullable when the corresponding bounded page has no such
field. Archive-depth comparison continues to use only the required source-order
`dateTimestamp`. Exact response hashing includes the source omission unchanged.

The failed attempt published no evidence or receipt. The maximum request count, single-attempt
transport, source allowlist, redaction boundary, and non-promoting Gate 2 behavior remain
unchanged.

## Consequences

- Current and legacy official rows coexist without invented timestamps.
- Reviewers can distinguish a true publish-time bound from an unavailable legacy field.
- The diagnostic remains strict about the field that controls page order and archive depth.

## Rejected alternatives

- Copy `dateTimestamp` into missing `publishTime`: fabricates a source field.
- Drop legacy rows: would hide the official archive boundary being measured.
- Make both timestamps optional: removes the only stable ordering/depth coordinate.
