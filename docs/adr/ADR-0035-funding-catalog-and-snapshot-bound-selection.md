# ADR-0035: Funding catalog and snapshot-bound selection

- Status: accepted
- Date: 2026-08-13
- Implements: Phase 2 funding metadata registration and deterministic selection

## Context

ADR-0030 introduced a receipt-verified DuckDB catalog for canonical candle datasets. Canonical
funding now has the same immutable manifest/file/receipt envelope, UTC month/eight-bucket
partitioning, key statistics, and content-addressed Parquet objects, but the catalog rejects its
dataset type and assumes the candle `open_time_ms` key column.

Research must select funding from the same exact catalog snapshot as other market inputs without
making `latest` mutable, mixing dataset types, weakening receipt verification, or introducing a
second divergent metadata index.

## Decision

Extend the backward-compatible v1 catalog and selection allowlists with `funding_event`.

Registration tries the strict canonical candle verifier and then the strict canonical funding
verifier; a dataset is admitted only when one verifier proves its complete receipt, manifest,
audit, schema, Parquet footer, file hashes, and no-orphan allowlist. Funding files read
`instrument_id, funding_time_ms` for first/last key facts; candle files continue to read
`instrument_id, open_time_ms`.

The existing partition grammar adds `dataset=funding_event` while retaining schema v1, UTC month,
and bucket `00` through `07`. DuckDB schema, logical snapshot hashing, revision semantics,
atomic-replace workflow, locks, lineage validation, and object bindings do not change.

A selection request still names exactly one dataset type. Every named dataset must match that
type; candle and funding datasets cannot be combined in one request. Exact catalog revision/hash,
explicit dataset IDs, range, instrument filter, required month/bucket partitions, file hashes,
ancestor/child exclusion, and overlapping-key rejection remain mandatory. Output object keys are
store-relative and type-specific.

Dataset receipts still report `not-assessed-by-dataset-receipt`. Catalog registration or
selection does not consume or imply funding chronology acceptance; consumers must bind the
separate applicable coverage audit.

## Consequences

- One rebuildable catalog can index trade, mark, and funding while preserving strict type
  isolation at selection.
- Existing candle catalog files and requests remain compatible and retain the same logical hashes.
- Funding selection becomes deterministic and hash-bound without reading rates into catalog
  metadata or GitHub evidence.
- The runtime DuckDB remains outside Git; sanitized registration/selection evidence remains the
  GitHub source of truth.
- Funding compaction, repair, scale qualification, and Gate 2 remain separate work.

## Rejected alternatives

- Separate funding catalog: creates divergent revision/snapshot semantics for research joins.
- Infer the time column without dataset type: weakens the physical contract boundary.
- Permit mixed-type selection requests: one request would no longer have one key/time semantic.
- Treat a passed funding coverage artifact as a catalog receipt field: coverage policy has a
  separate lifecycle and must be selected explicitly by consumers.
