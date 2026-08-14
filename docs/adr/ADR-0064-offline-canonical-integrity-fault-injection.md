# ADR-0064: Offline canonical integrity fault-injection evidence

- Status: accepted
- Date: 2026-08-14
- Implements: canonical orphan, missing-file, and partial-write detection evidence
- Preserves: immutable receipt-last dataset semantics

## Context

ADR-0022 and ADR-0031 require canonical candle and funding readers to accept only an exact
manifest allowlist committed by a completion receipt. Unit tests cover orphan files, missing
receipts, and tampered Parquet, but the data-pipeline definition of done and final data criteria
also require reviewable evidence that orphan and partial outputs are detected. The retained market
store must not be damaged to obtain that evidence.

## Decision

Add `python -m benchmarks.canonical_integrity_fault_injection` as a fully offline runner. It
publishes one minimal valid candle dataset and one minimal valid funding dataset under an
automatically removed temporary root, clones each pristine commit, and injects three failures per
dataset type:

1. an orphan file outside the manifest allowlist;
2. the absence of the manifest-bound Parquet file; and
3. the absence of `completion-receipt.json`, representing an uncommitted partial final directory.

Each of the six cases invokes the real production verifier and requires its exact fail-closed
`PublicationError` classification. A canonical fingerprint of every directory, file, file size,
and file SHA-256 is taken immediately before and after verification. Any verifier mutation or
unexpected classification aborts before evidence publication.

Freeze `grid.phase2-canonical-integrity-fault-injection/v1` as the public post-merge evidence. It
binds a merged implementation identity, the six named cases, aggregate detection/preservation
counts, and explicit no-network/no-live/no-retained-store assurances. It contains no market
values, dataset or instrument identities, runtime paths, account data, or credentials.

This proves detection behavior for the named canonical verifier boundaries only. It does not
repair or delete corrupted data, scan the retained store, accept Gate 2, authorize Phase 3, or
grant live permissions.

## Consequences

- Receipt-last and exact-allowlist behavior has a deterministic post-merge runtime proof.
- The verifier is demonstrated to preserve the observed failure state for operator diagnosis.
- Faults remain isolated from the retained canonical corpus.
- A new canonical dataset type or integrity condition requires an explicit successor case and
  contract.

## Rejected alternatives

- Inject faults into retained datasets: unnecessary risk to immutable evidence.
- Treat unit tests alone as post-merge proof: they do not publish a receipt-bound artifact.
- Delete orphan or partial paths automatically: their origin may be a crash, collision, or active
  writer and must be diagnosed explicitly.
- Report only a pass count: named dataset types and failure classes prevent accidental scope
  reduction.
