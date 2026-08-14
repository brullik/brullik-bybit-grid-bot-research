# ADR-0080: Topology-scoped full-history catalog selection evidence

- Status: accepted
- Date: 2026-08-14
- Extends: ADR-0025, ADR-0030, ADR-0067, ADR-0078, and ADR-0079

## Context

The receipt-verified full-history publication registered 978 trade/mark candle datasets into one
catalog snapshot. Its campaign topology is not constant: four instrument buckets are present for
the first 26 months, while a fifth selected instrument/bucket begins in the following month and is
present for the remaining 77 months.

A single selection request naming all five current instrument identities over the entire range
correctly fails closed because ADR-0030 would require the fifth bucket in the 26 pre-launch
months. Weakening missing-partition validation would hide genuine omissions. Publishing the four
detailed topology-scoped requests or their selected object lists to GitHub would disclose runtime
dataset and instrument identities.

## Decision

Keep the ADR-0030 selector unchanged. Express the campaign as two contiguous topology segments for
each of the two candle kinds, producing exactly four receipt-bound selections:

- segment 1 names the four identities/buckets present in its 26-month range;
- segment 2 names all five identities/buckets present in its 77-month range; and
- trade and mark use identical segment boundaries and topology counts.

Add `grid-data full-history-catalog-evidence`. It accepts one receipt-bound ADR-0078 registration
request, its receipt-bound catalog-registration evidence, and exactly four receipt-bound selection
artifacts. Before projecting a result it verifies:

- request/registration inventory and software-identity equality;
- one catalog revision/content hash across the entire chain;
- sorted, disjoint dataset inventories whose union equals the registration;
- exact manifest, object, row, byte, and required-partition reconciliation;
- required partitions recomputed from each private time/instrument request;
- two contiguous segments per kind with identical trade/mark topology; and
- selected row/byte/empty-object totals equal registered dataset totals.

The GitHub-safe `grid.phase2-full-history-catalog/v1` artifact exposes only hashes, catalog
revision, aggregate per-kind inventory, aggregate topology segment counts, safety flags, and
limitations. It contains no dataset IDs, instrument IDs, symbols, object keys, timestamps,
runtime paths, market values, account data, or credentials. Detailed requests, selections,
DuckDB, and canonical datasets remain ignored runtime artifacts.

Schema-only objects remain explicit in aggregate empty counts but never imply accepted coverage.
The artifact proves registration and deterministic topology-scoped selection only; it changes no
coverage/lifecycle policy, Gate 2 criterion, research promotion rule, or live authorization.

## Consequences

- Full-history selection remains fail-closed without inventing pre-launch bucket partitions.
- Four private selections are reproducibly reconciled into one reviewable GitHub source-of-truth
  result.
- A later topology change requires new private segments and a separately reviewed evidence
  contract version if it no longer fits this exact two-segment/two-kind shape.
- Catalog success remains independent of the blocked coverage and lifecycle evidence.

## Rejected alternatives

- Request all five identities from 2018: this correctly fails the missing-partition check.
- Use `instrument_filter=all`: this would require all eight buckets, including four never present
  in the campaign.
- Remove the fifth identity or its later datasets: this silently drops verified campaign scope.
- Relax missing-partition validation before a launch date: the selector has no accepted historical
  lifecycle authority from which to infer that exception.
- Commit detailed registration or selection artifacts: they contain runtime identities and object
  bindings prohibited by ADR-0025.
