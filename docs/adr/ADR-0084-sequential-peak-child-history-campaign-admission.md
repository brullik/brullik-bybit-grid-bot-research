# ADR-0084: Sequential peak-child history-campaign admission

- Status: accepted by owner; implemented
- Date: 2026-08-14
- Supersedes in part: ADR-0038 aggregate Landing admission only

## Context

ADR-0023 conservatively bounds every candle Landing page at 512 KiB plus 64 MiB of metadata per
child job. ADR-0038 summed those bounds for every incomplete child before starting a campaign,
even though its executor runs exactly one child at a time. That sum is a useful worst-case bound
for simultaneous retention, but it became an artificial host requirement for the initial
full-history bootstrap: roughly 1.79 million current-universe requests would reserve about 936 GB
of page capacity before the first request.

Retained same-host evidence shows why the sum is not a useful execution peak. The completed
five-instrument full-history candle campaign contains 43,328 pages and 30,832,408 Landing rows in
1,993,091,754 bytes. Across the retained Landing namespace, 78,880 page artifacts total
4,260,720,298 bytes and the largest is 92,805 bytes. These observations do not justify reducing
the 512 KiB page contract: it intentionally remains independent of source decimal-string width.
They do show that summing every future child's independent maximum rejects the owner laptop even
though actual Landing, canonical active-plus-building storage, and the operating reserve fit.
Applied to that immutable 978-job/43,328-page plan before download, the former aggregate formula
requires 186,934,368,986 bytes (174.096 GiB). The peak-child formula keeps the same 45-page largest
child bound and requires 98,676,251,354 bytes (91.899 GiB), a 1.894x reduction without using the
smaller observed page sizes for admission.

Every standard candle and funding child already performs a fresh same-volume host snapshot
immediately before mutation and again before completion. Its `required_free_bytes` includes the
full remaining Landing bound for that child, active-plus-building bytes, and the operating
reserve. Completed child bytes are retained, so they naturally reduce the next snapshot's
observed free space. A failed child retains verified page receipts and a later campaign invocation
fetches only missing pages.

The owner explicitly authorized evidence-based correction of machine requirements and prioritized
the shortest safe path to a finished product. This decision changes storage admission only; it
does not accept Gate 2, authorize Phase 3, or change any trading or risk gate.

## Decision

Keep every ADR-0023/ADR-0032 child page, metadata, memory, request, retry, endpoint, and receipt
bound unchanged. Keep ADR-0038 child execution strictly sequential.

For a campaign no-mutation preflight:

1. deterministically resolve and preflight every child exactly as before;
2. set campaign `required_free_bytes` to active-plus-building plus the operating reserve when all
   children are already complete;
3. otherwise set it to the maximum `required_free_bytes` among incomplete child plans; and
4. reject before campaign mutation when the fresh snapshot is below that peak-child requirement.

Execution continues to obtain a fresh snapshot immediately before and after every child. If prior
retained Landing or any unrelated disk use leaves too little space for the next child's complete
conservative bound, that child fails before its first public request. The campaign remains
incomplete and receipt-resumable; completed pages and children are not fetched again.

The initial campaign preflight proves safe admission of the next sequential unit, not guaranteed
one-shot completion of every later unit under arbitrary intervening disk growth. The unchanged
per-child refresh is the authoritative mutation gate. Operators may reclaim or migrate data only
through separately governed lifecycle procedures; this decision adds no deletion behavior.

## Consequences

- Full-history bootstrap can start on the evidence-qualified owner laptop without reserving
  mutually exclusive theoretical Landing maxima for millions of future pages.
- Actual retained Landing consumption is charged by the next fresh free-space observation.
- Disk pressure stops before the next child request and preserves deterministic resume, so
  progress does not require repeated downloads.
- The 512 KiB candle page bound, funding bound, 64 MiB child metadata allowance, active/building
  requirement, 8 GiB reserve, 70% memory gate, SSD/NVMe identity, and same-volume checks remain.
- Campaign plan/manifest schemas and immutable historical receipts remain compatible because the
  aggregate requirement is runtime admission state, not a serialized v1 contract field.
- Gate 2 remains closed and no live, authenticated, private, order, bot, or transfer behavior is
  introduced.

## Rejected alternatives

- Reduce the page bound to the observed maximum: retained observations cannot prove a future
  upper bound on exact source decimal-string width.
- Keep the whole-campaign sum: it reserves mutually exclusive peaks and blocks a host whose
  relevant execution units are independently bounded and freshly rechecked.
- Skip initial aggregate admission: the campaign must still prove that at least its largest
  pending child can run before committing the campaign plan.
- Delete completed Landing automatically: deletion would be a separate destructive lifecycle
  transition and would discard retained source evidence.
