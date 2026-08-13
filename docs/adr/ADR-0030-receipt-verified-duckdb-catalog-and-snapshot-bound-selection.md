# ADR-0030: Receipt-verified DuckDB catalog and snapshot-bound selection

- Status: accepted
- Date: 2026-08-13

## Context

Phase 2 already publishes immutable canonical candle datasets, immutable replacements, and
compacted children. Research needs a lightweight way to discover the exact files for a bounded
time/instrument request without scanning the entire store. A mutable `latest` pointer, directory
guessing, or an unbound SQL query would reintroduce substitution and duplicate-lineage risk.

The catalog is metadata, not the authoritative market corpus. Dataset manifests and completion
receipts remain the commit boundary. GitHub must describe and verify the catalog transition
without receiving the DuckDB file, market values, credentials, host identity, or absolute paths.

## Decision

Use a DuckDB metadata catalog inside the market-store root. This follows ADR-0002 and remains a
data/research dependency; `grid-live` neither imports nor opens it.

`grid-data catalog-register`:

- defaults to a no-mutation preflight;
- accepts only receipt-verified, complete canonical trade/mark 1m datasets;
- stores dataset/parent/schema identities, manifest and evidence hashes, file/object inventory,
  row/byte/key bounds, month/bucket facts, build/software identity, and logical receipt object;
- records conflicts as zero only where canonical verification proves sorted unique keys;
- records gaps as `not-assessed-by-dataset-receipt` rather than inventing completeness;
- requires every lineage parent to be registered already or in the same transaction;
- uses an exclusive lock, same-directory `.building` database, one DuckDB transaction, fsync, and
  atomic replace;
- increments one registration revision and chains its before/after logical content SHA-256; and
- is idempotent when every requested manifest binding is already present.

The DuckDB byte representation is not a stable identity. A canonical logical projection of every
registered dataset, parent, and file row plus the catalog revision is the catalog content hash.
The stored hash and registration chain are rechecked on every open.

`grid-data catalog-select` accepts only a closed
`grid.canonical-dataset-selection-request/v1` that names:

- exact catalog revision and logical content SHA-256;
- exact sorted dataset IDs and one supported dataset type;
- inclusive minute-aligned time bounds;
- either all instruments or a sorted explicit UInt32 list; and
- immutable consumer Git identity.

Selection re-verifies every named dataset receipt/file binding, requires every requested
month/bucket partition, rejects an ancestor and child in the same selection, rejects overlapping
file key ranges, and emits only canonical store-relative object keys and hashes. It never resolves
an implicit `latest`. The result proves deterministic pruning, not gap-free historical coverage;
the PM-owned coverage policy remains a separate gate.

## Consequences

- A selection can be reproduced or rejected from its request, catalog hash, manifest hashes, and
  file hashes without relying on mutable directory discovery.
- Catalog corruption, a changed manifest/file, incomplete lineage, stale lock/building output,
  missing month/bucket, or ambiguous parent/child selection fails closed.
- Registration reads key columns once to bind exact first/last file keys; values are not stored in
  the catalog or public evidence.
- The catalog is a rebuildable mutable index. Runtime backup/retention remains separate, while
  sanitized registration/selection contracts, evidence, tests, and decisions live in GitHub.
- Catalog selection does not imply lifecycle completeness, accepted gaps, or Gate 2 acceptance.

## Rejected alternatives

- Mutable `latest` aliases: selection changes without changing the request.
- Directory globbing: cannot prove receipts, lineage, substitution, or duplicate versions.
- Store candle rows in DuckDB: duplicates the immutable Parquet corpus and violates the metadata
  boundary.
- Hash the DuckDB file bytes: storage-engine serialization is not a portable logical identity.
- Automatically hide parents when a child appears: implicit lineage preference is not
  reproducible and can silently change research inputs.
