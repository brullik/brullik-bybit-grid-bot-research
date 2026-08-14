# ADR-0078: File-backed full-history catalog registration request

- Status: accepted
- Date: 2026-08-14
- Implements: Phase 2 full-history catalog registration
- Preserves: ADR-0030 catalog admission, transaction, and evidence semantics

## Context

`grid-data catalog-register` originally accepted one repeated `--dataset` argument per canonical
dataset. This is convenient for repair or compaction transitions, but the verified five-symbol
full-history publication contains 978 immutable datasets. Passing that inventory on Windows
exceeds the process command-line limit before the application can perform its no-mutation
preflight. Requiring an operator to split one logical registration across arbitrary batches would
create avoidable revisions and manual transcription risk.

The complete dataset inventory already exists in a receipt-verified history-campaign publication.
The catalog needs a bounded, reproducible way to consume that inventory without changing dataset
verification, lineage admission, catalog locking, or atomic publication.

## Decision

Add the closed `grid.canonical-dataset-catalog-registration-request/v1` contract. It contains:

- one sorted, unique array of 1 through 10,000 safe canonical dataset IDs;
- the immutable registrar identity `git:<40 lowercase hex>`; and
- the exact request contract identifier.

Add `grid-data catalog-registration-request`. It fully verifies one completed history campaign
publication and its source campaign, derives the exact sorted dataset inventory, rejects duplicate
identity, and publishes the request plus a receipt. An existing output is receipt-verified and
recomputed against the same publication before reuse.

Extend `grid-data catalog-register` with a mutually exclusive `--request` input. File-backed
requests must have a valid adjacent receipt and cannot be overridden by
`--software-identity`. The existing repeated `--dataset` plus `--software-identity` form remains
available for small transitions. Both forms produce the same `CatalogRegistrationPlan` and use
the unchanged preflight, complete receipt/file/footer/key verification, lineage checks, exclusive
lock, DuckDB transaction, fsync, atomic replace, and registration evidence.

Apply the same 10,000-dataset hard bound to selection requests. This exceeds the current full
capacity layout for any single-type selection while preventing unbounded request memory and
quadratic ancestor checks. Add the bound to the existing selection request/evidence schemas; all
previous valid requests remain valid.

The request file and detailed registration evidence remain runtime artifacts outside Git when
they contain dataset identities. A later sanitized aggregate may publish counts and hashes only.
This decision changes no Gate 2 criterion, coverage policy, dataset authority, or Phase 3 status.

## Consequences

- Full-history catalog registration is expressible by short, repeatable commands on Windows.
- The inventory is derived from verified publication lineage rather than copied from terminal
  output.
- Preflight and execution share one receipt-bound request and cannot disagree through argument
  truncation or identity override.
- Small repair and compaction registrations remain backward compatible.
- Catalog registration still does not imply gap, lifecycle, cadence, or Gate 2 acceptance.

## Rejected alternatives

- Increase the Windows command-line limit: it is an operating-system boundary outside the
  application contract.
- Split the publication into many manual catalog revisions: this adds failure windows and loses
  the one-request inventory binding.
- Read every directory under `datasets/`: directory discovery does not prove membership in the
  selected publication and could admit unrelated versions.
- Store the request inside the DuckDB catalog before preflight: input identity must be established
  before catalog mutation.
