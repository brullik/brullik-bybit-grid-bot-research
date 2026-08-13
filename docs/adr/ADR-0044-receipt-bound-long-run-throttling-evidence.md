# ADR-0044: Receipt-bound long-run throttling evidence

- Status: accepted
- Date: 2026-08-13
- Implements: Phase 2 measured long-duration public acquisition evidence

## Context

ADR-0043 receipts the adaptive state of each candle or funding child job, but the existing
campaign evidence projected only aggregate page, row, HTTP, retry, and byte counts. Those facts
cannot prove how many HTTP responses supplied a sanitized rate-limit observation, whether any
child reduced its rate, or how long the measured campaign ran. Chat output and local runtime
manifests are not GitHub source-of-truth evidence under ADR-0025.

The existing child and campaign artifacts are immutable. Their v1 schemas therefore cannot make
new fields mandatory retroactively, and the public evidence must not expose symbols, instrument
identities, page contents, runtime paths, device identity, raw headers, or market values.

## Decision

New candle and funding Landing executions add `started_at_ms` to their v1 manifests. Verification
accepts legacy manifests without it, but validates every present start as a non-negative timestamp
no later than `completed_at_ms`. The existing ADR-0043 adaptive summary remains optional for
legacy compatibility and mandatory in every new execution.

Extend `grid.phase2-public-history-campaign/v1` backward-compatibly with optional `timing` and
`adaptive_throttling` projections. The builder first re-verifies the aggregate receipt and every
child plan, page, manifest, and receipt, then reads only those verified child manifests. It:

- rejects a mixture of legacy and current child summaries or timings;
- sums classified response observations, reductions, cooldowns, and rate-limit events;
- proves observation coverage against the verified aggregate HTTP-attempt count;
- records the minimum/final child rates, maximum cooldown, and zero automatic increases; and
- derives campaign wall time and summed child execution time from receipt-bound start/completion
  timestamps.

`history-campaign-evidence --require-complete-throttling-evidence` is the qualification boundary.
It fails unless every child has both timing and an ADR-0043 summary and unless the number of
sanitized response observations equals the verified HTTP-attempt count. Long-run evidence intended
for GitHub must use this flag.

The projected evidence remains receipt-last and contains no market values, symbols, instrument
identities, runtime paths, host/device identity, raw headers, account data, credentials, or private
endpoint results. A successful projection proves the measured public Landing run only; it does not
accept gaps, prove complete lifecycle coverage, close Gate 2, or authorize live/private actions.

## Consequences

- GitHub can review the duration and complete adaptive-observation accounting of a measured run
  without receiving the runtime lake.
- Existing v1 child manifests and campaign evidence remain valid and immutable.
- A post-ADR-0043 campaign created before `started_at_ms` can still produce ordinary campaign
  evidence, but cannot pass the strict long-run qualification flag.
- A long elapsed run is not automatically a successful scale result; measured evidence must still
  be reviewed against scope, errors, rate reductions, and the Gate 2 performance envelope.

## Rejected alternatives

- Publish local console timing: it is not receipt-bound or reproducible from GitHub evidence.
- Infer duration from file modification times or host preflight observations: neither represents
  the child execution interval reliably.
- Require the new fields in all v1 manifests: this would invalidate immutable completed evidence.
- Store per-response headers or request identities in GitHub: aggregate counters are sufficient and
  avoid unnecessary operational and market-data disclosure.
