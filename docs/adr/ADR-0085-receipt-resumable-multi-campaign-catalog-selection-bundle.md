# ADR-0085: Receipt-resumable multi-campaign catalog selection bundle

- Status: accepted
- Date: 2026-08-14
- Extends: ADR-0030, ADR-0065, ADR-0080, and ADR-0084
- Preserves: immutable campaign/catalog contracts and unchanged Gate 2 ownership

## Context

The current-universe bootstrap intentionally reuses several independently committed sources: the
five-instrument full-history campaign before July 2026, the existing 100-instrument July campaign,
and disjoint new campaign shards. This avoids millions of repeated Bybit rows, but the resulting
catalog scope no longer fits ADR-0080's fixed one-registration/four-selection evidence shape.

The v1 catalog selector correctly requires explicit dataset IDs and every requested month/bucket.
As instruments enter the source plans over time, manually transcribing topology boundaries into
dozens of private requests would be slow and error-prone. Running each request as an unrelated
command would also re-open and logically verify the same DuckDB snapshot repeatedly. Relaxing the
missing-partition rule, using an implicit `latest`, or selecting both reused and replacement
campaigns over the same instrument/minute keys would weaken the existing safety boundary.

## Decision

Add the closed private `grid.canonical-catalog-selection-bundle-request/v1` contract. It binds:

- one exact catalog revision/content hash and immutable consumer Git identity;
- 1 through 16 sorted unique source campaign IDs; and
- one inclusive, whole-UTC-month clip per source.

`grid-data catalog-selection-bundle` receives matching completed source/publication roots and one
receipt-verified instrument registry. Its no-mutation preflight:

1. fully verifies every named campaign publication and its source campaign;
2. maps each candle publication dataset back to the exact source job and current stable identity;
3. omits funding datasets and jobs because funding chronology remains a separate contract;
4. groups consecutive months only while the exact instrument inventory is unchanged, with
   identical trade/mark topology;
5. rejects any repeated dataset ID or any source pair sharing an instrument in the same month;
6. bounds the result to 10,000 datasets and 512 v1 selection requests; and
7. runs every unchanged ADR-0030/ADR-0065 selection against one verified catalog snapshot.

The existing single-request selector remains authoritative for receipt/file binding, required
partitions, lineage exclusion, and exact-key disjointness. The new batch entrypoint only reuses
one verified catalog snapshot; it does not weaken any per-request check.

With `--execute`, the command writes a deterministic private plan, one receipt-bound selection per
derived segment, and a receipt-last completion manifest. Existing plan/selection receipts are
verified and reused on resume. Orphan files, partial receipt pairs, changed plans, substituted
catalog snapshots, and changed source publications fail closed before further output.

`grid-data catalog-selection-bundle-evidence` re-preflights the same sources and completed bundle,
then emits `grid.phase2-catalog-selection-bundle/v1`. The GitHub-safe projection contains only
hashes, catalog identity, aggregate source/selection/instrument/dataset/object/row/byte counts,
safety claims, and limitations. Campaign, dataset, instrument, object, timestamp, path, market,
account, and credential identities remain in ignored runtime storage.

## Consequences

- Existing and new immutable campaigns can form one exact research-ready object inventory without
  repeating Bybit acquisition or copying hundreds of identifiers by hand.
- Disjoint instrument shards may share month/bucket partitions, while repeated instrument/minute
  scope is rejected before any bundle artifact is written.
- Interrupted local selection work resumes from receipts; the canonical store and DuckDB catalog
  remain read-only throughout bundle selection.
- ADR-0080's four-selection evidence remains valid and immutable for its original five-instrument
  campaign. The generalized bundle is a separate v1 contract rather than a reinterpretation.
- The bundle proves deterministic candle selection only. It does not accept gaps, lifecycle
  explanations, funding cadence, Gate 2, Phase 3, research promotion, or live execution.

## Rejected alternatives

- Manually author every topology request: transcription and repeated catalog verification grow
  with the universe and invite omitted or duplicated scope.
- Relax missing-partition validation: the selector has no authority to infer lifecycle absence.
- Select every registered dataset: the catalog also contains pilots and overlapping retained
  campaigns, so this would create ambiguous canonical keys.
- Merge or rewrite existing Parquet datasets before research: committed datasets are immutable,
  and selection can express the exact disjoint union without a destructive transition.
- Add a private multi-range query directly to DuckDB: that would bypass the production selector's
  receipt, lineage, partition, and exact-key checks.
