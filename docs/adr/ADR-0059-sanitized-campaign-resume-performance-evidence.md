# ADR-0059: Sanitized history-campaign resume performance evidence

- Status: accepted
- Date: 2026-08-14
- Implements: Phase 2 receipt-safe campaign resume qualification

## Context

ADR-0046 permits receipt-integrity reverification of immutable completed Landing children, while
semantic admission remains mandatory for partial children, initial completion, canonical
publication, coverage auditing, and the explicit campaign verifier. PR #74 applied that boundary
to acquisition resume after a real 978-job campaign spent about 30.5 minutes reprocessing 927
completed children before reaching its first pending request.

The post-merge qualification must prove the exact campaign scope, completed/pending inventory,
aggregate resource bounds, implementation identity, verifier mode, in-process reuse, and
fail-closed first-pending handoff without publishing paths, host/device identity, instruments,
market values, or runtime data.

## Decision

Freeze `grid.phase2-history-campaign-resume-performance/v1` as a receipt-last, GitHub-safe
performance evidence contract. It binds the campaign request/plan, registry, capacity artifact,
and merged implementation SHA. It records only aggregate job/page counts, resource bounds,
preflight elapsed time, executor time to a local synthetic first-pending HTTP 403, and the exact
one-call fail-closed outcome.

The measurement must perform no network request. It uses the real immutable Landing corpus for
completed-child integrity verification and a local client stub only at the first pending page.
The evidence explicitly states that the campaign remains incomplete and that the result measures
local resume traversal rather than Bybit latency or throughput.

## Consequences

- The resume optimization has reviewable post-merge evidence bound to its exact data scope.
- GitHub receives no symbol, instrument ID, observed row timestamp, market value, runtime path,
  device identity, account data, or credential.
- The evidence does not replace full semantic verification, prove coverage, close Gate 2, or
  authorize any private/live action.

## Rejected alternatives

- Commit raw resume logs: they contain job identifiers and runtime paths.
- Use a real Bybit failure as the performance boundary: network latency and regional access would
  make the local traversal measurement non-deterministic.
- Publish only elapsed time: it would not prove identical scope, integrity mode, or fail-closed
  handoff.
