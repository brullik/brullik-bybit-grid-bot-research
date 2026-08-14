# ADR-0088: Receipt-bound history-campaign publication timing

- Status: accepted
- Date: 2026-08-14
- Extends: ADR-0039, ADR-0040, and ADR-0069
- Implements: resumable canonical publication wall-time evidence

## Context

The canonical history-campaign publisher already writes a receipt-bound prepared plan before any
child dataset and an aggregate manifest/completion receipt after every child verifies. The
manifest recorded only `completed_at_ms`. Publication performance therefore could not be derived
from immutable artifacts: process logs and file timestamps are mutable local observations, while
re-running a completed publication is both wasteful and impossible without violating immutable
dataset identity.

A long campaign may stop and resume many times. Measuring only the final process invocation would
hide the actual publication interval, while replacing a start timestamp on resume would make the
result non-auditable. Adding a required field to every existing v1 manifest would also invalidate
already committed publication roots.

## Decision

Add `grid.history-campaign-publication-start/v1` as a small canonical artifact named
`execution-start.json`. It binds one non-negative `started_at_ms` to the exact prepared-plan
SHA-256 and is committed with `execution-start.receipt.json` under the existing
`grid.history-campaign-publication-receipt/v1` contract.

The executor writes the start artifact and its receipt after source-envelope verification and the
receipt-bound plan commit, but before traversing or mutating the first canonical child. Resume
reuses the exact start artifact; it never advances or replaces the timestamp. An artifact without
its receipt, a receipt without its artifact, a changed plan binding, or any unexpected file fails
closed.

Every new completed publication manifest repeats the receipt-verified `started_at_ms` alongside
`completed_at_ms`. Verification requires the two values to agree with the start checkpoint and
rejects completion before start. `grid.phase2-history-campaign-publication/v1` may project only
these two timestamps and their exact non-negative `elapsed_ms` after full publication
reverification.

Compatibility is explicit. A legacy completed root with only plan, plan receipt, manifest, and
completion receipt remains valid when its manifest has no start field; its public evidence omits
`timing`. A prepared plan root and a plan plus complete start-checkpoint root both remain valid
resume states. Mixed, orphaned, or partially upgraded roots are rejected.

The checkpoint contains no market value, symbol, instrument or dataset identity, runtime path,
host identity, account data, or credential. It changes neither coverage/lifecycle acceptance nor
catalog registration, Gate 2, Phase 3, risk policy, exchange access, or live behavior.

## Consequences

- A publication spanning several process invocations has one immutable wall-time interval.
- Current campaigns can emit receipt-derived performance evidence without repeating acquisition
  or canonical publication.
- Existing immutable publication roots remain verifiable without migration.
- An interruption between the start artifact and its receipt leaves an explicit fail-closed
  orphan that requires operator investigation rather than silent timestamp replacement.
- Elapsed wall time includes intentional stops and host contention; reviewers must interpret it
  together with scope and resource evidence rather than as isolated throughput.

## Rejected alternatives

- Infer start from file creation/modification time: filesystem metadata is mutable and is not part
  of the publication hash chain.
- Use process logs: they are private runtime evidence and are not deterministic commit markers.
- Write the start only into the final manifest: a restart could choose a new value and erase the
  earlier execution interval.
- Make timing mandatory for all v1 roots: this would invalidate immutable legacy publications.
- Repeat publication solely to measure it: immutable child receipts make the rerun unnecessary,
  and repeated work would delay the current-universe milestone.
