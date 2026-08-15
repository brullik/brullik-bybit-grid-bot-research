# ADR-0107: Receipt-resumable campaign repair preparation

- Status: accepted
- Date: 2026-08-15
- Extends: ADR-0027, ADR-0041, and ADR-0053
- Implements: Phase 2 blocked-candle repair handoff

## Context

ADR-0041 deliberately publishes only each child audit's sequence, kind, status, and canonical
content hash. Exact symbols, dataset identities, gap ranges, and diagnostics remain private. That
is the correct GitHub boundary, but the existing single-child ADR-0027 planner needs the exact
receipt-verified private audit and Landing root. After a large aggregate audit, an operator would
otherwise have to rediscover and rerun child audits manually before planning repairs.

Repeating every already-passed child would waste the dominant semantic scan and contradict the
project's no-repeat objective. Automatically executing repair would be worse: a blocked result may
be a stable quarantined/overflow source defect, an unsupported blocker, or a plan beyond the
existing task/request ceilings. Funding chronology already has a distinct ADR-0055 through
ADR-0058 repair pipeline and must not be routed through candle repair.

## Decision

Add `grid-data prepare-history-campaign-repairs` and freeze three private receipt-last contracts:

- `grid.history-campaign-repair-preparation-request/v1`;
- `grid.history-campaign-repair-preparation-child/v1`; and
- `grid.history-campaign-repair-preparation/v1`.

The command fully verifies the completed ADR-0039 publication, its source campaign, the exact
registry/capacity/store bindings, and the receipt/content hash of the ADR-0041 aggregate audit.
It uses the aggregate's immutable ordered child results as the work inventory:

- passed children are not semantically recomputed;
- blocked funding children are recorded as delegated to the existing funding-repair pipeline;
- only blocked trade/mark children are semantically recomputed;
- each recomputed private audit must reproduce the exact child content hash already committed by
  the aggregate audit; and
- only an ADR-0027-compatible `rest_returned_no_data` result within the unchanged 1,000-task and
  100,000-attempt ceilings receives an ordinary v1 repair plan.

Unsupported reason policy, non-gap blockers, zero missing minutes, or task/request-limit overflow
produce an explicit ineligible child checkpoint and no plan. This classification does not accept
the blocker.

The preparation namespace is caller-selected private runtime storage and contains:

```text
<preparation-root>/
  request.json
  request.json.receipt.json
  children/<six-digit-sequence>/
    coverage-audit.json
    coverage-audit.json.receipt.json
    repair-plan.json                 # eligible children only
    repair-plan.json.receipt.json    # eligible children only
    result.json
    result.json.receipt.json
  manifest.json
  manifest.json.receipt.json
```

The request receipt is written before child work. Child artifacts and results are atomic and
receipt-last; a final manifest receipt commits the exact ordered preparation. Matching completed
children and a completed manifest are verified and reused without another semantic audit.
Incomplete pairs, unexpected paths, changed source/publication/audit bindings, changed content
hashes, or conflicting checkpoints fail closed. `verify-history-campaign-repairs` verifies the
completed checkpoint without repeating child semantic scans.

The shared ADR-0027 planner now accepts an already recomputed `CoverageAudit` only after its newly
written audit artifact/receipt exactly equals that result. This avoids a second scan of the same
blocked child inside one preparation invocation. The existing standalone planner keeps its full
recompute behavior. Later `execute-history-repair` still independently re-verifies the plan and
all runtime inputs before any public request.

Preparation makes no Bybit request, executes no repair, writes no canonical dataset, changes no
catalog, and has no private/live dependency. Runtime outputs contain private identities and exact
gaps and therefore remain outside Git. Gate 2 criteria, blocker meanings, owner authority, and
Phase 3 authorization are unchanged.

## Consequences

- A large campaign pays the repeated semantic cost only for candle children already proven
  blocked by the aggregate audit.
- A crash resumes from exact request/child receipts instead of restarting completed repair
  preparation.
- Eligible plans are immediately available for separate operator inspection and the existing
  explicit execution preflight.
- Stable source defects and boundedness failures cannot enter an automatic same-endpoint loop.
- Funding repair remains isolated under its chronology-specific contracts.
- This implementation shortens the Gate 2 evidence path but cannot open the gate or authorize
  repair execution.

## Rejected alternatives

- Recompute all children: repeats already-passed semantic work without producing new evidence.
- Store exact child audits in the public aggregate: exposes private market/runtime identities and
  violates ADR-0041.
- Build requests from aggregate examples or counts: the complete gap inventory is intentionally
  absent and cannot be reconstructed safely.
- Execute every eligible plan automatically: planning is not approval to issue market requests or
  publish replacement datasets.
- Treat funding blockers as candle gaps: funding cadence/predecessor semantics require their
  separate accepted pipeline.
