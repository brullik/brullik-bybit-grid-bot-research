# ADR-0034: Fail-closed funding source chronology audit

- Status: accepted
- Date: 2026-08-13
- Implements: Phase 2 funding coverage/source-parity audit

## Context

Funding is not a consecutive one-minute series. The official Bybit V5
[funding-history endpoint](https://bybit-exchange.github.io/docs/v5/market/history-fund-rate)
accepts `startTime`, `endTime`, and a limit of at most 200 records, but returns no historical
interval field. Current [instruments-info](https://bybit-exchange.github.io/docs/v5/market/instrument)
`fundingInterval` is not dated and ADR-0031 forbids projecting it backward. Reusing the candle
missing-minute audit would therefore report valid non-settlement minutes as gaps, while accepting
every returned event without chronology checks could hide an omitted settlement.

ADR-0032 already rejects saturated range pages and binds one predecessor per series. A separate
audit must prove exact Landing/canonical parity, exact page tiling, source-range enumeration,
registry lifecycle bounds, and settlement-derived intervals without weakening Gate 2 or silently
inventing historical schedule metadata.

## Decision

Freeze `grid.canonical-funding-coverage-audit/v1`.

The read-only audit re-verifies Landing, every page/receipt, predecessor aggregation, registry,
capacity evidence, immutable canonical manifest/audit/receipt, publisher Git identity, and exact
Arrow table equality. For every series it proves one predecessor page and complete non-overlapping
range-page tiling of the requested bounds. Saturated pages remain impossible under acquisition.

The first interval is recomputed from the receipted predecessor; every later interval is
recomputed from adjacent settlements. A series passes the v1 chronology check only when all
observed intervals have one stable source-derived value. Any empty requested range page,
predecessor/internal mismatch, or observed cadence change is an unaccepted blocker. A cadence
change may be valid, but it requires separately dated evidence or a separately governed reason
policy before acceptance; current instruments-info metadata is never sufficient.

The public receipt-last audit contains requested bounds, page/event/window counts, interval
histograms, transitive hashes, Git identities, blocker counts, and a hash of complete private
anomaly records. It contains no funding rates, observed settlement timestamps, local runtime
paths, host identity, credentials, or account data. Identical logical content is deterministic
apart from the explicit generation timestamp and auditor identity.

`passed` means the bounded official source response, retained Landing, and canonical dataset are
mutually consistent with a stable observed cadence. It does not establish an independent venue
ledger, complete historical universe, accepted future cadence changes, scale performance, or
Gate 2.

## Consequences

- Funding is audited according to settlement semantics rather than false consecutive-minute
  expectations.
- A single omitted event amid a stable cadence normally produces an unexplained interval change
  and blocks the audit.
- Legitimate historical cadence changes also block until dated evidence is introduced, preserving
  the no-future-leak boundary.
- Empty windows are preserved as evidence and are never silently interpreted as no funding.
- Repair planning can later recompute the private anomaly inventory and bind its committed hash.

## Rejected alternatives

- Reuse candle coverage: every non-settlement minute would be a false gap.
- Use current `fundingInterval`: undated metadata can leak the future.
- Accept any settlement delta: missing events become indistinguishable from schedule changes.
- Automatically accept empty pages: listing metadata alone does not explain an in-lifecycle empty
  funding window.
- Publish rates or observed settlement timestamps in Git: unnecessary for reviewable audit facts.
