# ADR-0042: Dated current linear-status inventory policy

- Status: accepted
- Date: 2026-08-13
- Implements: Phase 2 complete-current instrument inventory boundary

## Context

`grid.bybit-public-inventory/v1` queries every configured status partition of public
`GET /v5/market/instruments-info`. The original implementation included `Settling`, based on an
older API explorer/change-history enumeration. Mainnet rejects that value for the current linear
endpoint with retCode 10001, so otherwise complete snapshots were labelled
`partial_source_inventory`.

The current normative Bybit V5
[`status` enumeration](https://bybit-exchange.github.io/docs/v5/enum#status) contains exactly
`PreLaunch`, `Trading`, `Delivering`, and `Closed`. The current
[`Get Instruments Info`](https://bybit-exchange.github.io/docs/v5/market/instrument) documentation
also describes `status` as the instrument status filter and exposes `deliveryTime` as the
perpetual delisting time. Treating a value absent from the current normative enum as mandatory
does not make the inventory safer; it creates a false incompleteness signal.

## Decision

Freeze `bybit-v5-linear-status-enum-2026-08-13` as the dated current-status query policy for new
`grid.bybit-public-inventory/v1` observations. It requires exactly four independently paginated
linear queries, in canonical order: `PreLaunch`, `Trading`, `Delivering`, and `Closed`.

The inventory records the policy identity and normative documentation URL. `inventory_status` is
`complete` only when every policy query is accepted. A rejected policy query remains `partial`.
Every returned row must have the status requested for its partition; leakage across a status
filter fails the build instead of being silently deduplicated. A future normative enum change
requires a new dated policy identity and review before new snapshots can claim complete-current
coverage.

Existing evidence is immutable. Earlier snapshots that queried `Settling` remain valid negative
evidence and retain their `partial` classification. A complete-current snapshot proves only that
all status values in this dated endpoint policy were enumerated at its observation time. It does
not reconstruct metadata before the first snapshot, prove that Bybit retains every historically
delisted instrument forever, infer suspension intervals, resolve funding cadence history, or
close Gate 2.

## Consequences

- New mainnet inventories no longer manufacture a partial-source blocker from a non-normative
  request value.
- The exact completeness policy is carried inside the hashed source evidence rather than living
  only in implementation code.
- `Closed` and `Delivering` remain explicit queries; the endpoint's default `Trading` result is
  never treated as a complete current universe.
- Timeline summaries still fail closed for any genuinely rejected policy status and for all
  lifecycle conflicts defined by ADR-0037.
- Historical point-in-time coverage before the first snapshot remains a separate Gate 2 blocker.

## Rejected alternatives

- Continue querying `Settling`: current normative documentation omits it and mainnet rejects it.
- Ignore the rejected query while retaining it in the policy: the artifact would claim a policy
  different from the one used to classify completeness.
- Use one unfiltered request: linear defaults to current `Trading` instruments and cannot prove
  closed, delivering, or pre-launch enumeration.
- Reclassify older partial artifacts: committed evidence is immutable; a correction is a new
  observation.
