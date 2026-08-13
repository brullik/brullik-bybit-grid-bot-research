# ADR-0058: Post-publication funding repair coverage audit

- Status: accepted
- Date: 2026-08-14
- Implements: Phase 2 funding repair verification boundary

## Context

ADR-0057 publishes a new immutable funding child only after the public source confirms every
candidate settlement. Its replacement evidence proves exact row accounting and lineage, but it
does not independently re-run the ADR-0034 source-parity and chronology rules over the repaired
child. The original blocked audit is intentionally immutable and therefore cannot be changed to
`passed` after publication.

The repaired source projection is the exact union of the original receipt-verified Landing rows
and the receipt-verified repair Landing rows. It contains instrument identifiers, requested
bounds, observed settlement timestamps, and interval histograms, so the detailed audit is private
runtime evidence rather than a public GitHub artifact.

## Decision

Add `grid-data audit-funding-repair` and freeze
`grid.canonical-funding-repair-coverage-audit/v1`.

The command re-verifies the repair plan, passed execution, original blocked audit, original
Landing input, registry, capacity evidence, immutable parent, committed repair child, and
receipt-last replacement evidence. It reconstructs the exact original-plus-repair source union
and requires byte-equivalent Arrow schema and row equality with the committed canonical child.

The shared ADR-0034 chronology kernel then recomputes predecessor intervals, adjacent internal
intervals, range-page tiling, lifecycle bounds, duplicates, unexpected timestamps, empty source
windows, and unexplained interval changes. No current `fundingInterval` metadata or general
cadence policy is admitted. A pass requires every existing fail-closed reason count to be zero.

Verification is read-only. It verifies the already committed child against all immutable inputs
without applying current free-space or memory gates that are meaningful only for publication.
The audit itself is written with a receipt last. If the output already exists, reruns verify and
rebuild it instead of overwriting it.

The contract marks the detailed artifact `private_runtime_artifact=true` and
`github_commit_eligible=false`. Public progress may report only a separately designed sanitized
projection; this ADR does not create one.

## Consequences

- The repaired child has an independent, reproducible source-parity and chronology verdict.
- The original blocked audit and immutable parent remain byte-identical historical evidence.
- Low current free space cannot invalidate a read-only verification of an existing commit.
- A passing audit still does not register the child, accept a general historical funding cadence,
  close Gate 2, or authorize private/live operations.

## Rejected alternatives

- Rewrite the original audit to `passed`: destroys immutable evidence and historical causality.
- Treat ADR-0057 replacement evidence as coverage acceptance: row lineage alone does not re-run
  chronology and source-window checks.
- Reuse publication host-resource preflight for verification: makes a read-only verdict depend on
  mutable free-space and memory observations.
- Commit the detailed audit to GitHub: exposes unnecessary market identities and observed times.
