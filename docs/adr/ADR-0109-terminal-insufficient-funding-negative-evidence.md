# ADR-0109: Terminal-insufficient funding negative evidence

- Status: proposed
- Date: 2026-08-24
- Extends: ADR-0048, ADR-0090, ADR-0092, ADR-0097, and ADR-0108
- Preserves: immutable v1 evidence, the full candle universe, seven Gate 2 blocker codes, closed Gate 2, and owner authority

## Context

The completed current-universe candle acquisition exposed a funding condition that the accepted
ADR-0048 and ADR-0090 contracts intentionally fail closed on but cannot carry into owner review.
One public funding source-boundary scan reached a terminal result for every one of its 181 series:
174 series have at least two source-observed settlements, six have exactly one, and one has none
inside the closed historical range. The scan is complete and receipt-resumable; repeating it cannot
change the source result.

ADR-0048 requires two settlements for every completed boundary. The oldest is predecessor-only and
the second-oldest is the earliest admissible canonical event. This rule correctly prevents the
seven insufficient series from receiving an invented predecessor. It also prevents a completion
receipt for the whole 181-series boundary, so ADR-0090 cannot produce its funding evidence pair and
the v4/v5/docket watcher chain cannot publish the otherwise-blocked owner handoff.

Silently removing the seven series would narrow the receipt-bound candle universe. Extending the
historical end would use observations after the decision boundary. Treating the first settlement as
canonical would weaken the predecessor contract. None is admissible. The remaining safe option is
to preserve the terminal negative result as evidence while acquiring and publishing only the
predecessor-proven partition.

This is a data-contract and owner-review handoff change. Under the governance rule it cannot amend
issue acceptance criteria or be accepted by the same implementation change that consumes it.

## Proposed decision

Add a successor, non-promoting funding handoff with two disjoint private partitions:

1. `predecessor-proven`: series with at least two receipt-verified source settlements; and
2. `terminal-insufficient`: terminal series with zero or one source settlement in the original
   closed range.

The partition is derived only from a fully verified ADR-0048 plan and page/receipt inventory. Its
private artifact retains the exact series membership and any observed timestamps outside Git. A
GitHub-safe projection contains only immutable input hashes, aggregate counts, response-accounting
totals, and a complete private-partition hash. Zero, one, and at-least-two counts must reconcile to
the original request exactly. Nonterminal scans, missing page receipts, partial pairs, duplicate
membership, changed inputs, or unclassified responses fail before output.

Only the `predecessor-proven` partition may be converted into a new ADR-0048 request and admitted to
history acquisition. The derived request must retain the original closed time bounds, registry,
capacity evidence, software identity, and source order. Its symbols must equal the proven partition
exactly. Existing v1 boundary, Landing, publication, coverage, and catalog contracts remain
unchanged and immutable.

Add `grid.phase2-current-universe-funding-evidence/v2` as an offline successor to ADR-0090. It must:

- verify the original candle bundle and exact full target universe;
- verify the terminal partition artifact/receipt and its sanitized projection;
- verify all ordinary v1 triplets for the predecessor-proven partition;
- prove privately that the proven and terminal-insufficient partitions are disjoint and complete;
- report that canonical funding coverage does **not** equal the candle universe when the terminal
  partition is nonempty;
- publish aggregate unavailable-series counts and a private-anomaly hash without identities,
  timestamps, rates, values, or runtime paths; and
- return a blocked, non-promoting result while still committing its artifact and receipt.

Add successor readiness and docket contracts rather than editing immutable v4, v5, or docket v1.
They bind the v2 funding artifact, retain the exact six criteria, ordered seven blocker codes,
three/three readiness split, pending owner dispositions, closed Gate 2, and false Phase 3
authorization. The terminal-insufficient count is an explicit funding/lifecycle owner-review fact;
it does not silently remove, rename, or add a blocker code.

Acceptance of this ADR only authorizes implementation of the new offline/private contracts and the
bounded public acquisition for the proven partition. It does not authorize changing the PM-owned
completion checklist. That checklist must be updated in a separate reviewed governance change to
name the successor evidence/readiness/docket pairs before they can satisfy issue #126.

## Consequences

- Terminal public-source absence becomes receipt-bound negative evidence instead of an infinite
  restart loop or an unreviewable runtime failure.
- The full candle universe remains intact and no future observation or synthetic predecessor enters
  a historical decision.
- Useful funding history for predecessor-proven series can finish without presenting partial
  coverage as complete.
- Existing v1 artifacts and accepted Gate 2 blocker codes remain immutable.
- The new chain remains blocked and non-promoting until a separate data-quality-owner and governance
  decision; it cannot open Gate 2 or authorize Phase 3.

## Rejected alternatives

- Retry the terminal scan: all series are terminal and the source result is already receipted.
- Drop the seven series from the candle universe: that changes the accepted target scope and hides
  measured source absence.
- Extend the historical end until two settlements appear: later observations cannot prove earlier
  availability without future leakage.
- Admit the first settlement without a predecessor: this violates ADR-0032 and ADR-0048.
- Edit v1, v4, v5, or docket v1 in place: accepted evidence contracts are immutable.
- Treat the runtime exception as the owner handoff: an exception is neither schema-bound nor
  receipt-linked public evidence.
