# ADR-0024: Verified Landing to Canonical Publication

- Status: accepted
- Date: 2026-08-12
- Implements: Phase 2 Landing-to-canonical publication boundary

## Context

ADR-0023 produces a receipt-verified Landing batch and ADR-0022 provides a receipt-last immutable
canonical writer. Neither decision defines how one completed download is bound to one canonical
dataset without allowing an operator to substitute registry, capacity, coverage, code identity,
or candle rows between those boundaries.

The integration must remain a public-data operation with no private credentials. It must also
preserve the evidence-based host policy: an old capacity projection may constrain the calculation,
but current memory, storage identity, and free space are observed again before any write.

## Decision

Freeze `grid.history-to-canonical-publication/v1` as the adapter from one completed
`grid.bybit-1m-history-acquisition/v1` batch to one ADR-0022 candle publication.

Before planning publication, the adapter:

- fully verifies the Landing plan, pages, manifest, and completion receipt;
- verifies the supplied instrument registry and Gate 1 capacity receipts and requires their
  artifact hashes to match the bindings in the Landing manifest;
- re-derives active-plus-building bytes from the accepted layout in the capacity evidence and
  requires it to equal the Landing plan budget;
- loads the exact canonical Arrow batch and checks every instrument identity and observed time
  bound against the bound registry snapshot; and
- requires an explicit safe software identity and binds it into the build-configuration hash.

The immutable dataset identity is deterministic:

```text
trade-1m-<first 24 hex characters of Landing manifest SHA-256>
mark-1m-<first 24 hex characters of Landing manifest SHA-256>
```

The publication specification records the Landing manifest and registry artifact as source
evidence, the Landing manifest as coverage evidence, and the capacity artifact separately. The
canonical request hash additionally binds the accepted physical layout, adapter contract,
dataset identity, full Landing manifest hash, semantic version, and software identity.

`grid-data publish-history-1m` is no-mutation by default. It verifies all evidence, probes the
current host, and prints the planned identity and resource bounds. `--execute` takes a new host
snapshot before its execution clock, repeats ADR-0022 admission, and invokes receipt-last
publication. `grid-data verify-canonical-candle` independently verifies the committed dataset.

This decision publishes source-confirmed rows; it does not classify missing lifecycle ranges,
accept unresolved gaps, compact tail files, register a catalog entry, or open Gate 2.

## Consequences

- Substituting a different registry or capacity artifact after acquisition fails before mutation.
- The same completed Landing batch, software identity, and evidence are idempotent; a conflicting
  attempt cannot overwrite the committed dataset.
- Changing publication software identity requires a new source batch or an explicit future
  migration decision; committed canonical bytes are never edited in place.
- The current registry snapshot prevents rows before its recorded launch or after delivery, but a
  separate lifecycle/gap audit remains mandatory for historical completeness.
- Local history, Parquet output, and host identifiers remain ignored runtime data; no credentials,
  account identifiers, or market rows enter Git.

## Rejected alternatives

- Accept an operator-supplied dataset ID: it permits aliases and collisions for identical source
  evidence.
- Trust paths without receipts: a stale or modified Landing, registry, or capacity file could be
  published as canonical.
- Reuse the acquisition-time host observation for the write: current memory, NVMe/SSD identity,
  and free space can change between stages.
- Treat successful publication as gap acceptance: returned rows do not prove that every expected
  lifecycle minute exists.
