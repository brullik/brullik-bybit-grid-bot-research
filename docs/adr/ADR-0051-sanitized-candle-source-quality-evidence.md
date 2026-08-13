# ADR-0051: Sanitized candle source-quality evidence

- Status: accepted
- Date: 2026-08-13
- Implements: GitHub source-of-truth projection for ADR-0050

## Context

ADR-0050 retains exact anomalous source rows only in local receipt-bound Landing artifacts. The
existing campaign evidence proves child receipts and aggregate acquisition counts, but it neither
states whether any candle row was quarantined nor supports a candle-only campaign in its schema.
GitHub therefore cannot distinguish a fully admitted source inventory from one whose canonical
coverage is intentionally incomplete without exposing private runtime rows.

## Decision

Extend `grid.phase2-public-history-campaign/v1` backward-compatibly with optional
`source_quality`. New evidence builders always produce it after re-verifying the complete campaign
and every child receipt. The projection contains only:

- aggregate candle job, source-row, admitted-row, and quarantined-row counts;
- aggregate counts for the three ADR-0050 reason codes;
- the quarantine policy identifier and a canonical binding hash over only affected child manifest
  hashes, quarantine counts, and quarantine hashes; and
- `canonical_coverage_complete`, which is false whenever any row is quarantined.

Legacy candle child manifests without the optional ADR-0050 extension count all their verified
rows as admitted and zero as quarantined. Funding children do not participate in candle source
quality. A malformed or arithmetically inconsistent child source-quality block fails evidence
generation.

The evidence schema now permits the one-to-three kinds already allowed by the campaign request.
`landing.by_kind` includes exactly the requested kinds in canonical trade/mark/funding order; it no
longer fabricates a zero-count entry for an unrequested endpoint. Existing three-kind evidence
remains valid and byte-immutable.

Exact rows, source indices, symbols, instrument IDs, timestamps, market values, and runtime paths
remain forbidden. The aggregate flag is disclosure, not acceptance: a quarantined row remains
absent from canonical data and must block complete coverage under ADR-0026.

## Consequences

- GitHub records that a complete acquisition contains a receipt-bound source anomaly without
  publishing the anomaly itself.
- Candle-only full-history evidence validates against the same versioned schema.
- Aggregate arithmetic proves `source = admitted + quarantined` across candle children.
- Existing evidence consumers may ignore the optional block; new builders always emit it.

## Rejected alternatives

- Publish the quarantined row or its timestamp: this violates the sanitized evidence boundary.
- Report only a boolean: it cannot verify aggregate arithmetic or classify the failure.
- Include zero-count unrequested kinds: it misstates which endpoint families the campaign ran.
- Treat the aggregate as accepted coverage: quarantine deliberately preserves a canonical gap.
