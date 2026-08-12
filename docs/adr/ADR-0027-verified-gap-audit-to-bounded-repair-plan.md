# ADR-0027: Verified Gap Audit to Bounded Repair Plan

- Status: accepted
- Date: 2026-08-12
- Implements: Phase 2 deterministic gap-repair planning boundary

## Context

ADR-0026 preserves a complete, hash-bound gap inventory but embeds only bounded diagnostic
examples. A repair operator must not construct requests from those truncated examples, trust a
stale audit, accept a missing-minute reason implicitly, or mutate an already committed canonical
dataset. The existing acquisition application already has a strict, receipt-bound request
contract and bounded public REST executor; repair planning should reuse that boundary instead of
creating a second download protocol.

## Decision

Freeze `grid.bybit-1m-gap-repair-plan/v1` as a receipt-last, no-market-mutation evidence contract.
`grid-data plan-history-repair` accepts one receipt-verified blocked
`grid.canonical-1m-coverage-audit/v1`, the original completed Landing job, its registry and
capacity evidence, and the immutable canonical store. It recomputes the complete audit from those
runtime inputs and requires byte-equivalent canonical JSON facts before planning any task.

V1 is deliberately narrow. Planning is allowed only when every blocker is a missing requested
minute observed as `rest_returned_no_data`; source/canonical inequality, conflicts, duplicates,
lifecycle failures, unexpected timestamps, unrequested rows, accepted reasons, or unknown
reasons fail closed. A passing audit also produces no repair plan.

Each deterministic contiguous gap becomes one embedded
`grid.bybit-1m-history-request/v1` containing one symbol and the exact inclusive minute range.
The request reuses the verified original plan's kind, page limit, workers, global request rate,
and retry count. Request bytes and the source audit, Landing manifest, and canonical manifest are
hash-bound. The plan must account for every missing minute, is limited to 1,000 tasks and 100,000
maximum HTTP attempts, and records the full Git commit identity of the planner implementation.

Planning performs no market request and no canonical mutation. Execution of embedded requests,
validation of returned rows, and publication of a new immutable dataset or partition-replacement
lineage require later explicit contracts. The old canonical dataset remains committed and is
never edited in place.

## Consequences

- A repair plan is reproducible from GitHub-identified code plus receipt-verified runtime inputs.
- The standard history executor can consume each extracted embedded request without a repair-only
  network client or relaxed bounds.
- Truncated public gap examples cannot omit work because the planner recomputes the complete list.
- The planner cannot convert missing data into accepted data or close any PM/risk gate.
- A successful current pilot correctly has no measured repair-plan artifact; negative-path tests
  provide contract evidence without fabricating a production gap.

## Rejected alternatives

- Plan from the audit's diagnostic samples: samples are intentionally incomplete.
- Combine multiple gaps for one symbol in a single v1 request: the acquisition request forbids
  duplicate symbol identities, and one-gap requests keep retry and lineage units bounded.
- Download while planning: preflight and network mutation must remain separate operator intents.
- Append rows directly to a committed Parquet file: canonical datasets are immutable.
- Treat `rest_returned_no_data` as an accepted no-trade interval: ADR-0026 explicitly rejects that
  inference.
