# ADR-0091: Receipt-bound current-universe catalog performance

- Status: accepted
- Date: 2026-08-14
- Extends: ADR-0030, ADR-0066, ADR-0085, and ADR-0089
- Preserves: immutable retained data, unchanged Gate 2 criteria, and data-quality-owner authority

## Context

ADR-0085 produces one receipt-bound private selection bundle for the current candle universe and
an identifier-free public aggregate. Its creation exercises the production batch selector once,
but the resulting evidence intentionally contains no repeat measurement or retained-state
fingerprint. ADR-0089 exposes acquisition and available publication timing, while explicitly
leaving the owner-reviewed end-to-end performance envelope unqualified.

Repeating acquisition or publication to measure selection would waste the most expensive Phase 2
work. Reusing ADR-0066's synthetic result would not measure the actual current-universe object
inventory. A retained-data benchmark must therefore prove that it consumes exactly the completed
ADR-0085 bundle, exercises the production batch boundary, and leaves every selected dataset and
the DuckDB catalog unchanged.

## Decision

Add `grid.phase2-current-universe-catalog-performance/v1` and the read-only
`python -m benchmarks.current_universe_catalog_performance` runner. Output preflight completes
before retained-store access. The runner then:

1. receipt- and schema-verifies the private bundle plan, completion manifest, every selection,
   and the public ADR-0085 projection;
2. verifies plan/manifest/catalog/request/content/artifact hashes, contiguous sequence numbers,
   unique dataset membership, the public selection-chain hash, and exact per-kind aggregates;
3. fingerprints the catalog bytes and all selected dataset directory/file metadata;
4. executes two complete `select_catalog_ranges` passes, each using the production rule of one
   verified catalog snapshot for the bounded request bundle;
5. requires every runtime selection fingerprint and inventory to equal its receipt-bound source;
6. requires the immediate repeat to be identical, verifies the catalog again, and requires the
   before/after catalog and selected-dataset fingerprints to match; and
7. publishes only hashes, aggregate counts, nanosecond timing, integer rows/second, non-identifying
   environment facts, cache-state disclosure, and explicit limitations.

The benchmark is bounded to the unchanged ADR-0085 maxima of 512 selections and 10,000 datasets;
the public contract additionally bounds objects, rows, and bytes. Dataset/campaign/instrument
identities, time bounds, object keys, paths, market values, account data, and credentials remain
private. The result is descriptive component evidence. It neither defines nor qualifies the
owner-reviewed Gate 2 performance envelope and has no Gate 2 or Phase 3 authority.

## Consequences

- Current-universe selection throughput and deterministic repeat behavior can be measured without
  another Bybit request, publication, registration, or catalog-bundle build.
- One public artifact is cryptographically bound to the exact private bundle and selected object
  inventory while exposing no runtime identities.
- State mutation, source substitution, request drift, non-contiguous selections, count drift, or
  a changed catalog snapshot fails closed before evidence publication.
- Acquisition/publication timing from ADR-0089 and this catalog measurement become a stronger
  owner-review input, but repair, lifecycle, cadence, and end-to-end envelope decisions remain
  separate.

## Rejected alternatives

- Time the original bundle command from logs: logs are not receipt-bound and mix preflight with
  resumable output work.
- Run each selection through the single-request entrypoint: it would reverify the whole catalog
  per request and would not measure the ADR-0085 production batch boundary.
- Publish the private plan or per-selection results: they contain identities and time ranges that
  GitHub evidence deliberately excludes.
- Mark the Gate 2 performance criterion ready from this component timing: the owner-reviewed
  envelope includes more than catalog selection.
