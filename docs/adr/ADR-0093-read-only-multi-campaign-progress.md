# ADR-0093: Read-only multi-campaign progress observation

- Status: accepted
- Date: 2026-08-14
- Extends: ADR-0046, ADR-0059, ADR-0084, and ADR-0087
- Preserves: immutable Landing, explicit full verification, and unchanged Gate 2 authority

## Context

Long current-universe history downloads run as several independent, receipt-resumable campaigns.
The acquisition command emits one JSON event after each child, but an operator checking several
processes later must manually combine logs, campaign plans, completion markers, page weights,
free space, and timestamps. Re-running ordinary campaign preflight is not a status operation: it
rechecks completed children and can take many minutes before reaching the pending child.

The project needs one bounded status command that uses existing immutable metadata and does not
repeat Bybit acquisition, page decoding, semantic admission, publication, or catalog work. A
status estimate must also remain distinct from authoritative campaign verification and Gate 2
performance evidence.

## Decision

Add the transient `grid.history-campaign-progress/v1` observation and
`grid-data history-campaign-progress`. One invocation accepts one through sixteen distinct
campaign roots and a 60-through-86,400-second recent-rate window. It performs no network request
and no write. For each campaign it:

1. verifies canonical campaign-plan bytes, the plan receipt, deterministic root identity,
   request hash, bounded ordered jobs, and unique child roots;
2. verifies each present child plan and its receipt against the exact campaign descriptor;
3. treats an allowlisted `.run-lock` as an active pending child and never reads its partial pages;
4. for a completed child, verifies both manifest receipts, hashes the manifest, and reconciles
   the child contract, plan/request identities, page count, row count, and execution timestamps;
5. when the aggregate completion pair exists, reconciles every aggregate child entry and total;
   and
6. reports integer job/page/row totals, millionths progress, minimum observed free bytes, recent
   milli-pages/second, and a ceiling-rounded descriptive ETA.

No Landing page artifact is opened. The recent rate uses receipt-bound completion times: with at
least two events, the first is the wall-clock baseline and only later completed page weight is
credited. A single event uses its execution interval when available. If the sample is
insufficient, ETA is null rather than guessed.

The JSON is terminal/runtime state, not a receipt-last evidence artifact and not intended for
Git. `authoritative_campaign_verification_performed=false` and
`rate_is_descriptive_not_acceptance_evidence=true` are mandatory. The explicit
`verify-history-campaign` command remains the authoritative page-level verifier.

## Consequences

- One command replaces repeated manual log/plan arithmetic across concurrent campaigns.
- Existing active and completed v1 campaign/child artifacts remain unchanged and require no
  migration or sidecar write.
- Manifest tampering, receipt drift, unsafe roots, unknown metadata, invalid timestamps, and
  inconsistent aggregate totals fail closed.
- The observation may temporarily undercount the child holding `.run-lock`, which is safer than
  treating an in-flight write as committed. A child committed after the snapshot cutoff is also
  deferred to the next observation.
- The command does not resume a process, make a Bybit request, prove source semantics, qualify the
  end-to-end performance envelope, change Gate 2, or authorize Phase 3/private/live behavior.

## Rejected alternatives

- Re-run campaign preflight for status: it repeats expensive integrity work and host admission.
- Parse process logs only: logs may be rotated or start after earlier receipt-resumed work.
- Trust file existence or modification time as completion: neither binds the immutable manifest.
- Read every Landing page: that is the job of explicit authoritative verification, not progress.
- Persist a mutable status database: immutable receipts already contain the required facts and a
  second state store would introduce reconciliation and recovery work.
