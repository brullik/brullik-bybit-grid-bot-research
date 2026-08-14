# ADR-0077: Receipt-verified funding repair candidate audit

- Status: accepted
- Date: 2026-08-14
- Implements: Phase 2 funding repair admission diagnostics
- Preserves: ADR-0055 repair-plan semantics and the unchanged Gate 2 criteria

## Context

ADR-0055 admits funding repair discovery only for a complete isolated integer-multiple cadence
sandwich `C, N*C, C`. A blocked coverage audit can contain interval changes without that topology.
Calling the repair planner separately for every such audit produces the same fail-closed answer and
encourages repeated manual work. It must not be replaced by a weaker chronology inference or a
Bybit request made merely to see whether data happens to exist.

The current retained corpus has multiple receipt-verified blocked funding audits. GitHub needs a
reproducible aggregate explanation when none is eligible, while dataset, instrument, settlement,
rate, and local-path identities must remain private.

## Decision

Add `grid-data audit-funding-repair-candidates`. The command accepts parallel explicit lists of
coverage audits, completed Landing job roots, and instrument registries, plus one capacity artifact
and canonical store. It receipt-verifies every audit and delegates eligibility to the unchanged
ADR-0055 production planner. Only the planner's exact complete-sandwich rejection is classified as
`non-isolated-or-non-integer-chronology`; every other error fails closed. Eligible inputs retain
only plan counts and its content hash in the private audit.

The no-mutation default computes the audit without writing it. `--execute` publishes one detailed
private receipt-last audit. Inputs are bounded to 1,000 unique audit artifacts. The command makes
no market request, accepts no settlement or cadence, publishes no canonical child, and changes no
parent.

Add `grid.phase2-funding-repair-candidate-audit/v1` as a GitHub-safe projection. It includes only
receipt/hash/software bindings, aggregate classification and task/request-bound counts, explicit
non-mutation assurances, and limitations. It excludes dataset, instrument, timestamp, rate,
runtime-path, host, account, and credential identities. Verification rebuilds the detailed audit
from the exact immutable inputs before publication.

This evidence prevents repeated ineligible discovery attempts. It neither changes nor satisfies a
Gate 2 criterion, removes a blocker, accepts any funding chronology, or authorizes Phase 3. A new
or changed blocked audit requires a new candidate audit.

## Consequences

- Operators can distinguish a genuine ADR-0055 repair opportunity from an ineligible chronology
  before any Bybit request.
- A zero-candidate result is reproducible and safe to publish on GitHub without revealing market
  identities.
- Future eligible audits still require the existing plan, bounded execution, immutable
  replacement, post-publication audit, and owner acceptance workflow.
- Any unsupported audit defect remains an error rather than being folded into the no-candidate
  classification.

## Rejected alternatives

- Treat every interval change as a candidate: this would infer missing settlements without the
  required surrounding cadence evidence.
- Query Bybit before topology admission: this spends requests without an authorized deterministic
  candidate set.
- Publish the detailed private audit: its actionable dataset and input identities are unnecessary
  for GitHub governance.
- Replace a Gate 2 blocker from this diagnostic: that is a separate owner-governed decision and is
  outside this ADR.
