# ADR-0046: Semantic admission and receipt-integrity reverification

- Status: accepted
- Date: 2026-08-13

## Context

The measured 100-instrument x 31-day campaign contains 9,600 Landing pages, 8,938,466 rows, and
591,702,449 Landing bytes. Canonical no-mutation preflight took 473.9 seconds, idempotent replay
took 707 seconds, and the GitHub-safe publication projection took 230.7 seconds. Profiling by
workflow boundary showed that completed-publication reuse repeatedly parsed the same canonical
JSON market rows and rebuilt exact Decimal/Arrow batches even though those rows had already passed
semantic admission and been committed into independently verified canonical Parquet.

Removing verification would violate immutable-data and fail-closed requirements. Repeating the
row decode at every completed-publication check is also unnecessary: immutable page receipts and
the aggregate manifest already bind the exact source bytes and facts admitted by the publication
transition.

## Decision

Separate source verification into two explicit modes:

1. **Semantic admission** remains mandatory during acquisition completion, initial or pending
   Landing-to-canonical publication, and every coverage audit. It parses every source page,
   validates the endpoint/task/row contract, reconstructs exact typed rows, and compares source
   and canonical content where required.
2. **Receipt-integrity reverification** is allowed only for a completed aggregate canonical
   publication, immutable-child reuse, and its GitHub-safe publication evidence. It does not
   decode source market rows. It must hash every source page byte, verify every page receipt,
   verify the exact page-to-task manifest facts and counts, verify child and aggregate
   plan/manifest/receipt chains and allowlists, and fully verify every canonical Parquet dataset.

Batch loading while semantic page verification is disabled is rejected. Publication preflight
and execution continue to use semantic admission for every pending child; coverage auditing is
unchanged and continues to reconstruct source rows. The integrity path therefore optimizes only
reverification after the immutable canonical commit exists.

New `grid.phase2-history-campaign-publication/v1` artifacts may expose the optional process mode
and a monotonic elapsed time for the completed-publication verifier. The fields remain optional so
existing immutable evidence stays valid. A measured artifact must use the merged implementation
identity and the same 100 x 31 campaign before the optimization is considered qualified.

## Consequences

- Repeated verification remains proportional to source bytes and canonical files, but avoids
  Python JSON/Decimal/Arrow reconstruction of millions of already admitted source rows.
- Tampering with any Landing page, receipt, manifest, task binding, aggregate chain, canonical
  file, or canonical receipt still fails closed.
- Initial conversion and coverage quality retain full semantic checks; no acceptance policy or
  risk gate changes.
- GitHub evidence can record the verifier mode and measured elapsed milliseconds without exposing
  paths, instruments, market values, device identity, account data, or credentials.
- The optimization does not accept the seven funding cadence changes, close Gate 2, register
  datasets, or authorize a private endpoint or live action.

## Rejected alternatives

- Trust file existence or modification time: neither binds immutable content.
- Trust only aggregate receipts: page-level corruption would not be localized or independently
  checked.
- Skip canonical verification: source integrity alone does not prove the published Parquet chain.
- Use integrity-only verification for first publication or coverage audit: both require exact row
  semantics and source/canonical equality.
- Cache decoded Arrow batches across jobs: this increases memory and mutable-cache complexity and
  does not improve later process restarts.
