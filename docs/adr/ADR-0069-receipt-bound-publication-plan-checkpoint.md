# ADR-0069: Receipt-Bound Canonical Publication Plan Checkpoint

- Status: accepted
- Date: 2026-08-14
- Extends: ADR-0039 and ADR-0046
- Implements: bounded full-history canonical publication startup and resume

## Context

ADR-0039 requires a whole-campaign semantic preflight before the first canonical mutation and a
fresh semantic preflight of each child immediately before that child's mutation. The original CLI
kept the aggregate plan only in memory. An operator who first ran the default no-mutation
preflight and then started `--execute` therefore decoded the entire campaign twice before the
first write. Every process restart repeated the same aggregate pass again.

On the retained full-history campaign, one aggregate pass over 978 jobs and 30,832,408 Landing
rows took about 30 minutes. The repetition supplied no new admission decision: the deterministic
plan, source hashes, evidence hashes, writer identity, input-table hashes, canonical admission
facts, and resource maxima were already known. It materially delayed first publication and every
resume.

Skipping semantic admission or trusting an unbound cache would violate ADR-0039, ADR-0046, and
the immutable source boundary. The optimization must preserve default no-mutation behavior,
receipt-last commits, fresh per-child host checks, and semantic validation before every pending
child mutation.

## Decision

Add an explicit prepared-plan checkpoint using the unchanged
`grid.history-campaign-publication-plan/v1` payload and receipt contract.

`grid-data publish-history-campaign --prepare-plan` performs the existing complete aggregate
semantic preflight exactly once. Only after all children pass does it atomically publish
`plan.json`, followed by `plan.receipt.json`, in the deterministic publication-campaign root. It
writes no canonical dataset, aggregate manifest, or completion receipt. The default command
without either mutation flag remains a no-mutation preflight.

`--execute --publication-root <prepared-root>` is the fast execution/resume path. Before execution
it verifies:

- the exact prepared-plan artifact and receipt, v1 allowlist, policy, plan-derived root, immutable
  publisher identity, and aggregate counts;
- the source campaign aggregate envelope against the exact source plan and manifest hashes frozen
  by the prepared plan;
- the supplied instrument and capacity evidence receipts and exact hashes;
- deterministic source lineage, dataset identities, canonical-admission arithmetic, request/input
  hashes, resource bounds, unique dataset identities, and current host capacity; and
- any aggregate completion marker before treating the campaign as complete.

This fast load intentionally does not decode or hash every Landing page. That work is not omitted
from admission: the prepared plan exists only after the complete semantic pass, and execution
still performs the existing full semantic child preflight from current immutable Landing bytes
immediately before each pending child mutation. The current child must reproduce every frozen
plan field exactly. A previously committed child is instead hash/receipt/audit-verified against
the frozen plan under ADR-0046 and is not decoded again; completed aggregate verification still
checks the complete source integrity chain. Changed or tampered source bytes, conflicting
canonical commits, stale building state, changed calculations, stale host evidence, or resource
shortfall therefore fail closed before a pending child can mutate or aggregate completion can
verify.

The legacy `--execute` form without `--publication-root` remains compatible and performs the
whole aggregate semantic preflight in memory before execution. A prepared root is accepted only
with `--execute`; `--prepare-plan` and `--execute` are mutually exclusive.

This boundary has no exchange endpoint, credential, order, bot, transfer, catalog promotion, risk
gate, or Gate 2 effect.

## Consequences

- A large campaign pays for aggregate semantic planning once instead of once per operator review
  and once per process start.
- Every pending canonical child still pays for one current semantic verification immediately
  before its write. A committed child is verified from immutable canonical receipts and the frozen
  plan without repeated row decoding.
- An interruption resumes from the small receipt-bound plan plus canonical child receipts instead
  of first decoding every unrelated Landing child again.
- The plan contract and schemas do not change, so existing completed publications remain valid.
- Runtime plans and datasets remain ignored local state; only sanitized receipt-bound evidence may
  be committed to GitHub.

## Rejected alternatives

- Remove the aggregate semantic pass: this would admit new source rows from unverified manifest
  claims and violate ADR-0046.
- Skip the per-child semantic preflight after plan preparation: source bytes could change between
  preparation and mutation without detection at the mutation boundary.
- Cache Arrow batches: memory and disk usage would grow with campaign size and create a second
  mutable market-data representation.
- Reuse a plan without receipt, exact software identity, evidence hashes, and source hashes: the
  cache would not be a deterministic or auditable admission checkpoint.
