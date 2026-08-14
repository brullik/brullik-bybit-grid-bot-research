# ADR-0079: Schema-only canonical dataset catalog admission

- Status: accepted
- Date: 2026-08-14
- Extends: ADR-0030, ADR-0065, ADR-0067, and ADR-0078

## Context

ADR-0067 permits a fully verified candle source partition with zero admitted rows to publish one
immutable schema-only Parquet object. Its complete manifest correctly has zero rows, zero
instruments, and null time/instrument bounds. The full-history publication contains 268 such
datasets among 978 verified children.

The ADR-0030 catalog predated that representation. Registration rejected null manifest bounds and
required positive rows plus first/last keys for every file. As a result, the receipt-bound
full-history request could not pass catalog preflight even though every dataset and object had
already passed the canonical publication verifier. Omitting those children would break exact
publication membership and make requested month/bucket presence implicit.

## Decision

The catalog admits a schema-only candle dataset only after the ordinary canonical verifier proves
its manifest, audit, receipt, exact schema, Parquet footer, hash, and object inventory. The catalog
record must have:

- `row_count=0`, `instrument_count=0`, and null dataset time bounds;
- one or more non-empty object files whose individual row counts are zero and whose time,
  instrument, and first/last key bounds are all null; and
- the unchanged complete status, partition, lineage, evidence, build, and receipt bindings.

All non-empty datasets and files retain the existing positive-count and complete-bound rules. A
mixed or partially null record fails closed.

The logical `grid.canonical-dataset-catalog/v1` projection and registration/selection evidence use
JSON nulls for absent bounds. To remain compatible with already-created DuckDB v1 catalogs, the
physical `NOT NULL` key-bound columns encode an absent bound as zero only when the corresponding
row count is zero. Catalog reads normalize that sentinel back to null and reject every nonzero
bound on a zero-row record. A non-empty record never receives sentinel semantics.

Range selection treats a verified schema-only object as explicit evidence that its requested
month/bucket partition exists. The object and its hash remain in the deterministic selection even
though its selected row inventory is zero. Empty objects contribute no keys and are excluded from
ADR-0065 exact-key overlap merging; populated objects retain the existing metadata fast path and
bounded exact-key fallback.

The backward-compatible v1 registration and selection evidence schemas now allow coherent
zero-row/null-bound records and reject partially populated forms. No coverage, lifecycle, gap,
research-admission, or Gate 2 policy changes.

## Consequences

- One file-backed request can register the exact 978-child full-history publication without
  dropping 268 valid schema-only datasets or rebuilding the existing catalog.
- Selection preserves explicit immutable empty partitions and can produce a positive object count
  with a zero selected-row inventory.
- Logical catalog hashes remain representation-independent; physical sentinel values never appear
  in public evidence or consumer objects.
- An empty selected object proves source/canonical lineage and partition presence, not that missing
  history is acceptable or complete.

## Rejected alternatives

- Omit empty datasets during request generation: this changes verified publication membership and
  hides missing/quarantined partitions.
- Treat an empty partition as having fabricated time or instrument bounds: this invents keys that
  do not exist.
- Rebuild or migrate the existing DuckDB before registration: the row-count-qualified v1 encoding
  is unambiguous and avoids a needless mutable transition.
- Return no object for an empty-only selection: consumers would lose the exact file/receipt binding
  that proves the partition was explicitly published.
