# ADR-0067: Schema-only canonical candle publication for zero-admission source partitions

- Status: accepted
- Date: 2026-08-14
- Extends: ADR-0021, ADR-0024, ADR-0039, ADR-0050, and ADR-0053

## Context

A completed full-history candle campaign can legitimately contain a source child with zero
admitted rows. The public endpoint may return no rows for the requested lifecycle-bounded range,
or every returned row may be retained only in ADR-0050 quarantine. The Landing manifest and
receipt are complete evidence, but the canonical adapter previously failed while constructing a
non-empty Arrow batch. That prevented aggregate publication of all independent children and hid
the missing-range or quarantine result from the existing fail-closed coverage audit.

Skipping the child would break the ADR-0039 one-source-child/one-canonical-child lineage. Admitting
quarantined values or inventing a candle would violate the exact physical and quality contracts.

## Decision

Permit a verified candle Landing child with zero admitted rows to publish one immutable,
schema-only canonical dataset. The adapter derives the month/bucket partition from the already
verified non-empty request series and builds an empty Arrow table with the unchanged canonical
candle schema and metadata. The ordinary logical-row builder continues to reject an unqualified
empty row sequence; the explicit empty builder is used only after semantic Landing verification.

The receipt-last writer emits exactly one schema-only ZSTD Parquet file in that partition. Its
manifest has `row_count=0`, `instrument_count=0`, null time/instrument bounds, the original source
and build hashes, a canonical audit, and a normal completion receipt. Parquet verification requires
the exact schema, a zero-row row group, file hash, partition allowlist, manifest, audit, and
receipt. A multi-file dataset may not mix an empty file with populated files.

The backward-compatible v1 campaign publication schemas now allow a child dataset `row_count` of
zero. Aggregate dataset membership, source sequence, immutable identity, resource preflight,
receipt resume, and verifier behavior remain unchanged. Funding publication is unchanged.

Coverage acceptance is also unchanged. The ADR-0026 audit compares the empty canonical table with
the verified empty admitted source table, enumerates the entire requested minute range as missing,
and classifies receipt-bound quarantine keys under ADR-0053. The result therefore remains blocked
until ordinary gap repair or separately reviewed source reconciliation supplies acceptable data.

## Consequences

- Full campaigns can publish independent valid children without fabricating or dropping a
  zero-admission source partition.
- Empty canonical datasets are explicit immutable evidence, not evidence of complete coverage.
- Catalog registration and research admission remain downstream of a passing coverage audit.
- Existing non-empty datasets and v1 campaign artifacts remain valid without migration.

## Rejected alternatives

- Omit the source child from the aggregate publication: this breaks deterministic membership and
  prevents exact child coverage auditing.
- Treat an empty child as complete coverage: source absence is not proof that venue history does
  not exist.
- Publish a quarantined row unchanged or normalized: either violates the canonical candle
  invariants and ADR-0050.
- Create a zero-file dataset marker: a schema-only Parquet file is independently verifiable by the
  existing dataset boundary and preserves one uniform receipt-last representation.
