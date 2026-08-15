# ADR-0108: Complete Gate 2 owner-review docket

- Status: accepted
- Date: 2026-08-15
- Extends: ADR-0081, ADR-0092, and ADR-0097
- Preserves: the unchanged six Gate 2 criteria, seven blockers, closed gate, and owner authority

## Context

ADR-0097 consolidates the future current-universe v4 result and later funding/lifecycle evidence
into one receipt-bound v5 owner-review input. Its explicit owner-review fields cover funding
cadence, lifecycle, and performance. The two measured-negative deterministic-repair blockers
remain present in the criteria and gate object, but are not assigned to a separate owner-review
item. An operator would therefore still have to reconcile the seven blocker codes manually before
asking the data-quality owner for one complete decision.

That manual step is small compared with acquisition, but it is both avoidable and gate-sensitive.
Omitting one blocker from the request could accidentally make an incomplete review look complete;
asking for separate decisions would add unnecessary delay after the current downloads finish.

## Decision

Add `grid.gate2-owner-review-docket/v1` and
`python -m benchmarks.gate2_owner_review_docket` as an offline, non-promoting successor to the
exact merged v5 artifact. The builder verifies the v5 artifact/receipt, canonical JSON, v5 JSON
Schema, embedded content hash, artifact hash, contract, status, and exact ADR-0097 implementation
identity. It also requires the unchanged six criteria, three/three readiness split, seven ordered
blockers, closed Gate 2 state, and all v5 dispositions to remain pending.

The docket assigns every blocker exactly once to four review items:

1. deterministic-repair evidence sufficiency: the candle source gap and unavailable eligible
   funding-repair candidate;
2. funding-cadence policy: the eleven explained and zero unexplained measured changes;
3. lifecycle and absence policy: incomplete point-in-time metadata, partial official archive
   matching, and unaccepted candle absences; and
4. performance-envelope qualification: deterministic measured catalog performance while the
   end-to-end envelope remains unqualified.

Every item has `owner_disposition=pending` and `owner_decision_required=true`. The output records
that no decision, blocker removal, gate change, or Phase 3 authorization occurred. The builder
makes no network request, reads no retained market dataset, publishes atomically, and returns exit
code 2 after producing the artifact and receipt.

After merge, one passive runtime invocation may wait for the existing v5 artifact/receipt and then
publish this docket once. It must reuse v5 rather than repeat acquisition, policy lookup,
lifecycle matching, canonical verification, or performance measurement.

## Consequences

- The data-quality owner receives one four-item request that covers all seven blockers without
  manual set arithmetic or repeated evidence work.
- The deterministic-repair blockers can no longer be silently absent from the final review
  handoff.
- V1 through v5 evidence remains immutable and the only runtime input is the exact v5 pair.
- A later owner decision still requires a separately authorized governance change. This docket
  cannot record acceptance, open Gate 2, or authorize Phase 3.

## Rejected alternatives

- Edit v5: its implementation and waiting runtime are already immutable and pinned.
- Treat the two repair blocker names as an implicit disposition: presence is not an explicit owner
  review item and is easy to overlook.
- Ask for four independent decisions at different times: slower and more error-prone than one
  complete docket.
- Let the docket accept dispositions or open the gate: an implementation artifact cannot approve
  the gate it is being evaluated against.
