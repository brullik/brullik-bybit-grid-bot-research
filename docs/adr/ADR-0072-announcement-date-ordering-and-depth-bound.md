# ADR-0072: Announcement date ordering and archive-depth bound

- Status: accepted
- Date: 2026-08-14
- Amends: ADR-0071 announcement ordering semantics

## Context

The first post-merge ADR-0071 execution failed closed before publishing evidence. The official
`new_crypto` page was strictly descending by `dateTimestamp`, while nearby items contained small
inversions in `publishTime`. This is valid source behavior: the endpoint page order follows its
display/date field and does not promise strict `publishTime` order.

Rejecting that response would make the bounded diagnostic unusable. Silently sorting by
`publishTime` would be worse: it could imply that the last API page contains the globally oldest
publish time even though pagination is not ordered by that field.

## Decision

Validate page order using `dateTimestamp`, the field that actually determines the source page
sequence. Continue validating both `dateTimestamp` and `publishTime` as non-negative integer
milliseconds. Retain oldest/latest bounds for both fields in each type probe, but compare selected
registry launch boundaries only with the oldest `new_crypto` `dateTimestamp` from the declared
last page.

Do not reorder source items before hashing. First/last response hashes continue to bind the exact
validated result. A total mismatch, wrong type, invalid timestamp, non-descending
`dateTimestamp`, or unexpected page cardinality still fails closed.

The failed attempt created no evidence or receipt and made no private/live request or market-data
mutation. The unchanged maximum remains 16 one-attempt public responses.

## Consequences

- The contract now matches observed official API pagination without weakening structural checks.
- Published evidence distinguishes source-order date bounds from publication-time bounds.
- Archive depth remains a capability diagnostic, not per-instrument lifecycle proof or Gate 2
  acceptance.

## Rejected alternatives

- Require strict `publishTime` order: contradicted by a valid official response.
- Sort by `publishTime` locally: changes source order and cannot establish the endpoint's global
  oldest publication time.
- Drop `publishTime`: it remains useful bounded source evidence even though it does not drive
  pagination.
