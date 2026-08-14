# ADR-0061: Receipt-verified funding compaction candidate audit

- Status: accepted
- Date: 2026-08-14
- Implements: Phase 2 funding maintenance admission
- Preserves: ADR-0054 compaction acceptance rules

## Context

ADR-0054 requires at least two receipt-verified canonical funding parents from one month/bucket,
with no duplicate key and no settlement-interval mismatch across the union. The local store can
contain multiple datasets for the same partition because controlled campaigns overlap in symbols
or time. A repeated partition name or file count is therefore not evidence that a genuine
compaction candidate exists.

Manual pair selection is error-prone and does not give GitHub a reproducible explanation when all
available pairs are overlapping. Fabricating disjoint parents solely to obtain a successful
benchmark would not measure a real maintenance need.

## Decision

Add `grid-data audit-funding-compaction-candidates` with a no-mutation default and explicit
`--execute` publication. The audit enumerates direct `funding-*` dataset roots under one market
store, fails closed on symlinks or any incomplete/invalid funding dataset, receipt-verifies every
manifest/file/footer, and loads every exact canonical table once. Inventory is bounded to 10,000
datasets and 100,000 same-partition pairs.

Datasets are grouped by exact canonical month/bucket partition. Every unordered pair in a group
is classified using the same Arrow-schema, sorted-key, and later-row interval semantics as
ADR-0054:

- `eligible`;
- `duplicate-or-conflicting-keys`;
- `unresolved-settlement-interval`; or
- `schema-mismatch`.

There is no deduplication, gap filling, subset selection, or search for a pair that merely passes
after discarding rows. The detailed receipt-last private audit contains dataset/partition
bindings and pair classifications so an operator can select a real eligible pair. It contains no
funding rates or account credentials, but remains outside Git because runtime identities are
detailed.

Add `grid.phase2-funding-compaction-candidate-audit/v1` as the GitHub-safe projection. It binds
the private audit hash, exact store-state hash, auditor/publisher Git identities, inventory counts,
and all four aggregate classification counts. It contains no dataset, partition, instrument,
timestamp, funding-rate, runtime-path, host, account, or credential identity. Verification
rebuilds the private audit against the current receipt-verified store before projection.

A no-candidate result proves only that the bound store state has no eligible pair. It does not
qualify compaction, waive measured ADR-0054 evidence when a genuine candidate later appears,
accept funding chronology, register a catalog entry, or close Gate 2.

## Consequences

- Overlapping controlled campaigns cannot be misrepresented as a compaction opportunity.
- A future incremental or repair fragment becomes discoverable without manual pair guessing.
- Invalid or newly changed store state invalidates the detailed audit instead of silently changing
  its meaning.
- Current no-candidate evidence can enter GitHub as aggregate counts while actionable identities
  remain private.

## Rejected alternatives

- Compact overlapping parents after deduplication: this hides duplicate canonical ownership and
  violates ADR-0054.
- Split an existing dataset artificially to manufacture benchmark input: it does not evidence a
  genuine incremental/repair maintenance transition.
- Inspect only manifests and time bounds: aggregate ranges cannot prove key disjointness or
  cross-parent settlement chronology.
- Publish detailed pair identities: aggregate counts and binding hashes are sufficient for GitHub
  governance; exact operational candidates remain local.
