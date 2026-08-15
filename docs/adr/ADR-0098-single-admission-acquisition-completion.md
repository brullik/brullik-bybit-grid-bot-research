# ADR-0098: Single-admission acquisition completion

- Status: accepted
- Date: 2026-08-15
- Extends: ADR-0046 and ADR-0086
- Preserves: semantic source admission, receipt-last commits, immutable page verification, and Gate 2

## Context

A newly completed candle or funding child semantically validates every receipted page while it
builds the completion manifest. After atomically publishing the manifest and completion receipt,
the executor called the full semantic verifier again only to construct its return value. The
second pass reparsed every exact decimal and source row even though the same invocation had just
admitted those immutable bytes.

A read-only sample of the last twenty completed children in each active current-universe candle
shard showed request phases near 12.8 requests/second, with no rate-limit event or adaptive
reduction, but wall rates of about 7.1--7.2 requests/second. Median between-child time was 33.5
and 72.0 seconds. The duplicate post-commit semantic traversal is therefore material to future
resume and incremental acquisition even though already loaded processes are not restarted.

ADR-0046 already permits receipt-integrity reverification after semantic admission, but did not
apply that mode to the return path of a newly committed acquisition child.

## Decision

For both candle and funding acquisition completion:

1. retain the existing exact semantic validation of every page before the manifest is built;
2. retain the receipt-last manifest commit and removal of the active run lock;
3. after commit, run the existing integrity verifier, which hashes every page and verifies every
   page receipt, plan/manifest binding, aggregate fact, completion receipt, and file allowlist;
4. do not decode the same source rows a second time merely to return the completed-job object; and
5. preserve candle quarantine source keys captured from the already validated page payloads so
   callers observe the same completed-job semantics.

Explicit semantic verification, canonical publication, and coverage audits remain unchanged and
continue to decode source rows. Existing completed-child reuse remains integrity-only. No active
campaign is restarted or migrated by this decision.

## Consequences

- Newly completed children perform one semantic admission plus one byte-integrity traversal,
  instead of two semantic traversals.
- Page, manifest, receipt, source-quality, quarantine, request-bound, and canonical contracts are
  unchanged; no existing artifact requires migration.
- Any post-admission byte, receipt, manifest, allowlist, or aggregate drift still fails before the
  executor returns success.
- Current already-loaded Python processes keep their loaded implementation until they naturally
  exit; the project does not trade receipt-safe continuity for an invasive restart.
- The optimization changes no request rate, retry budget, source policy, coverage acceptance,
  Gate 2 criterion, Phase 3 authority, private endpoint, or live behavior.

## Rejected alternatives

- Skip post-commit verification: this would weaken the receipt-last completion boundary.
- Keep two semantic passes: measured between-child cost directly delays recurring acquisition.
- Restart active campaigns to pick up the optimization: their current receipt-safe single paths
  are healthy, and an intervention would add avoidable coordination and duplicate-work risk.
- Cache decoded rows across children: this increases mutable memory state and is unnecessary for
  the completion return path.
