# ADR-0014: Gate 1 Reference Evidence Aggregation

- Status: proposed; Gate 1 owner-review-gated
- Date: 2026-08-12

## Context

ADR-0011 and ADR-0013 define separate host-bound reference layout and feature evidence. A reviewer
still needs one deterministic artifact that proves those results came from the same workstation,
row scale, and shared runtime; rechecks their transitive inputs; applies the documented provisional
performance thresholds; and presents P-001 through P-005 without allowing implementation code to
approve its own gate.

The existing `grid.capacity-projection/v1` through `/v3` artifacts are immutable local/provisional
evidence. Extending their meaning to accept host-bound results would silently reinterpret existing
receipts. Merely trusting hashes embedded inside two final JSON files would also be insufficient for
independent review because the referenced workstation, layout-decision, and real-market artifacts
would not themselves be reverified.

## Decision

Introduce append-only `grid.gate1-review-pack/v1` and a dedicated builder. It accepts only:

- receipt- and schema-verified `grid.reference-layout-benchmark/v2` evidence;
- receipt- and schema-verified `grid.feature-benchmark/v2` evidence;
- the original receipt-verified `grid.layout-benchmark/v3` decision artifact;
- the original receipt-verified `grid.real-market-layout-skew/v1` artifact; and
- the original receipt-verified `grid.workstation-snapshot/v1` artifact.

Before output preflight/publication, the builder requires the layout and feature artifacts to bind
the same workstation summary, current hardware, 99,999,900-row/700-instrument scale, and identical
Polars/psutil/Python versions. Their basic hardware must match the full workstation snapshot. The
actual SHA-256, schema, status, and relevant content of all three transitive artifacts must match
the references embedded in the final layout evidence.

For each exact shortlisted layout, the pack records both engines' first and warm query timings,
cross-engine result hashes, immutable repair/compaction evidence, synthetic and bounded real-market
row widths, capacity projections, and these provisional checks from the performance plan:

- linearly projected ten-year single-symbol cold scan at most 15 seconds;
- linearly projected ten-year single-symbol warm scan at most 5 seconds;
- observed full-universe month cold scan at most 15 seconds; and
- write of the 100-million-row reference corpus at most 20 minutes.

Feature throughput is projected to the theoretical trade and trade-plus-mark envelopes, and its
configured memory gate may not exceed 70% RAM. If no layout passes or feature memory fails, the
builder still publishes `blocked-by-reference-results` and returns a non-success process status so
negative evidence is auditable. Otherwise it publishes `ready-for-owner-review`.

Both outcomes retain:

- `owner_decision_required=true`;
- Gate 1 status `pending-owner-decision`;
- `automatic_promotion=false`; and
- explicit P-001 through P-005 candidate/blocked entries.

The builder cannot write an accepted Gate 1 record, modify decision status, promote a layout, or
authorize Phase 2.

## Consequences

- Reviewers receive one deterministic, receipt-linked summary instead of manually joining several
  artifacts.
- A copied or newly receipted but unbound source artifact is rejected even when its JSON schema is
  valid.
- Cross-host, cross-version, incomplete-row-scale, tampered, and missing-transitive evidence fails
  before an existing output can be replaced.
- Negative performance results remain public evidence rather than disappearing as command errors.
- Single-symbol ten-year timings remain linear projections because the 100-million-row reference
  corpus covers about 142,857 minutes per symbol; the pack states this limitation and owner review
  decides whether stronger direct evidence is required.
- V1-v3 provisional capacity projections remain unchanged and reproducible.
- A qualifying external run and explicit owner/PM acceptance are still required to close Gate 1.

## Rejected alternatives

- Modify an existing capacity-projection schema: it would change the semantics of immutable
  receipt-verified evidence.
- Mark Gate 1 accepted when all numeric checks pass: implementation does not own acceptance.
- Treat embedded hashes as independently verified provenance: the referenced files and receipts
  must be supplied and checked.
- Drop failed runs: negative capacity evidence is required for honest decisions.
- Claim a direct ten-year scan from the reference corpus: its per-symbol time span is shorter.
