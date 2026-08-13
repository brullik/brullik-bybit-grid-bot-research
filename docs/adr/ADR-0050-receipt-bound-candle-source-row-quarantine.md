# ADR-0050: Receipt-bound candle source-row quarantine

- Status: accepted
- Date: 2026-08-13
- Implements: fail-closed continuation after a reproducible public-source OHLC anomaly

## Context

A controlled full-history candle campaign stopped twice on the same Bybit REST row because its
reported OHLC values violate the canonical `low <= open, close <= high` invariant. A separate
official Bybit one-minute bulk product disagrees with the REST values for that minute and omits
the trade-turnover field required by the canonical trade contract. Neither source therefore
provides an authoritative, lossless replacement for the other.

Silently clamping a price, copying an alternate source row, or discarding the response would
create unproved market history. Permanently stopping every independent page would also prevent
the resumable acquisition boundary from collecting otherwise valid public evidence. The source
anomaly must remain exact and auditable while canonical completeness continues to fail closed.

## Decision

Extend the existing v1 candle Landing page and acquisition manifests with an optional,
backward-compatible `exact-source-row-quarantine-v1` block. Newly written pages always record the
complete source-row count. A row may enter quarantine only when all of these conditions hold:

- its width, timestamp, page bounds, exact finite decimal fields, positive prices, and non-negative
  trade volume/turnover are otherwise valid;
- the complete source page remains unique and reverse chronological; and
- its only semantic failure is `low > high`, `open` outside `low/high`, or `close` outside
  `low/high`.

The Landing page retains the exact string array, original source index, deterministic reason, and
canonical row hash. The page receipt binds those bytes. Admitted rows and quarantined rows have
separate counts and aggregate hashes; the acquisition manifest binds per-page facts, reason
counts, and an aggregate quarantine hash. Verification reconstructs source order and re-derives
the classification. A valid row cannot be declared quarantined, and an unrecognized malformed
row still aborts the job.

Quarantined rows are never normalized, rounded, clamped, assigned a quality flag, or published as
canonical candles. Landing-to-canonical publication consumes admitted rows only. Consequently the
minute remains absent, the ADR-0026 coverage audit reports a gap, and Gate 2 stays blocked until a
separate reviewed source-reconciliation decision provides sufficient evidence. Older immutable
v1 artifacts without the optional block remain valid and imply zero quarantined rows because
their original verifier admitted every retained row.

GitHub-safe evidence may expose only aggregate counts, reason counts, and receipt-bound hashes.
Exact rows, timestamps, symbols, paths, and market values remain local under ADR-0025. This change
uses only unauthenticated public endpoints and does not alter trading, risk, promotion, or manual
approval gates.

## Consequences

- One isolated source defect no longer prevents acquisition of independent pages.
- Exact source evidence is retained without fabricating canonical market data.
- Receipt and semantic verification detect row removal, mutation, reordering, or false
  classification.
- Canonical history remains deliberately incomplete, so downstream research cannot treat the
  affected interval as accepted coverage.
- A later repair must preserve immutable lineage and pass the existing bounded repair and coverage
  gates.

## Rejected alternatives

- Clamp OHLC into a valid envelope: this invents prices and destroys source fidelity.
- Substitute the conflicting bulk row: the products disagree and the bulk record lacks required
  turnover.
- Drop the row without retaining it: the gap would have no receipt-bound cause.
- Admit it with a quality flag: canonical invariants are hard contracts, not advisory metadata.
- Retry forever: the reproduced response is semantic source data, not a transient transport
  failure.
