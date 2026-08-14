# ADR-0070: Receipt-bound fast candle-boundary diagnostic

- Status: accepted
- Date: 2026-08-14
- Implements: non-promoting Gate 2 candle-gap topology evidence

## Context

The full-history semantic coverage audit correctly replays every Landing row and compares it with
canonical Parquet under ADR-0026. That expensive proof is necessary for coverage acceptance, but
its sanitized aggregate retains only child hashes and counters. Repeating the complete Landing
decode merely to determine whether already-proven gaps are leading, internal, trailing, or fully
absent duplicates tens of millions of JSON/Decimal/Arrow conversions without adding source-parity
evidence.

The immutable aggregate publication already has a receipt/hash chain over every source page,
child, canonical file, manifest, and audit. The prior semantic coverage artifact independently
binds exact expected, observed, missing, gap-range, and reason counts. A diagnostic may reuse those
proofs, but must not turn first observed data into claimed listing metadata or accepted absence.

## Decision

Add the candle-only `grid.phase2-candle-boundary-diagnostic/v1` contract and
`grid-data diagnose-history-campaign-boundaries`.

The command performs no network call. It re-verifies the completed source/publication receipt
chain through ADR-0046 integrity mode, verifies the supplied instrument registry and prior
ADR-0041 semantic coverage receipt/content/bindings, and reuses the `PublishedDataset` objects
already produced by aggregate publication verification. It then projects only `instrument_id` and
`open_time_ms` from each canonical Parquet file once. Landing market rows are not decoded again.

Requested candle segments must remain ordered and contiguous for each kind/instrument series.
The diagnostic classifies missing requested minutes into leading, internal, trailing, and
fully-absent topology; counts consolidated per-series ranges and the original child-local ranges;
and requires exact reconciliation with the prior semantic audit's expected, observed, missing,
gap-range, and reason totals. Any substituted registry, coverage artifact, source plan, canonical
row, or non-candle child fails closed.

The GitHub-safe projection contains only aggregate/per-kind counts, hashes, immutable software
identities, elapsed time, and process facts. It excludes symbols, instrument/dataset identities,
observed timestamps, market values, runtime paths, account data, and credentials. A diagnostic
with any missing minute reports `diagnosed-unaccepted-candle-boundaries` and exits 2.

First observed candle time remains source-availability evidence only. It is not accepted as a
listing date, delisting date, historical point-in-time metadata, no-trade interval, or repair
substitute. All ADR-0026 reason codes remain unaccepted and Gate 2 remains closed until its owner
reviews separate lifecycle evidence/policy.

## Consequences

- Boundary topology can be reproduced from an existing canonical campaign without another public
  download or full Landing semantic decode.
- Canonical receipt/file verification runs once and its typed results are reused by the diagnostic
  projection.
- The prior semantic coverage artifact remains the source-parity and reason-policy authority.
- Leading legacy gaps can be separated from genuine internal/suffix gaps without publishing
  private runtime diagnostics.
- The command cannot repair, compact, catalog, promote, close Gate 2, authorize Phase 3, or call
  private/live endpoints.

## Rejected alternatives

- Re-run the full semantic audit for every diagnostic question: correct but needlessly repeats
  source decoding already bound by immutable evidence.
- Trust only manifest min/max values: cannot count internal gaps or reconcile child gap ranges.
- Accept the first returned candle as listing metadata: source availability does not prove venue
  lifecycle state.
- Publish per-symbol timestamps: unnecessary for public review and contrary to the existing
  sanitized campaign-evidence boundary.
