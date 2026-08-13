# ADR-0033: Sanitized public funding pilot evidence

- Status: accepted
- Date: 2026-08-13
- Implements: GitHub-authoritative Phase 2 funding pilot evidence

## Context

ADR-0032 deliberately leaves sanitized pilot evidence as a separate transition. Funding Landing
pages and canonical Parquet contain exact rates and settlement timestamps and therefore remain
outside Git under ADR-0025. A chat transcript or local success message is not a durable project
record, while publishing those runtime rows would violate the repository boundary.

Funding evidence also differs from the consecutive candle pilot. Funding settlements are sparse,
and the current public endpoint does not prove that an arbitrary requested window contains every
historical settlement. The evidence must not turn a successful bounded acquisition into an
implicit lifecycle, chronology, or Gate 2 acceptance.

## Decision

Freeze `grid.phase2-public-funding-pilot/v1` as the GitHub-safe summary for one already committed
canonical funding pilot.

Its builder re-verifies the complete Landing job, every page receipt, predecessor aggregate,
registry and capacity bindings, canonical manifest/audit/receipt, immutable publisher Git SHA,
and an identical publication preflight with `existing_commit=true`. It loads the committed
Parquet and requires exact Arrow table equality with the table reconstructed from Landing.

For each requested series, the builder privately re-reads the receipted predecessor timestamp and
recomputes the first interval. Every later interval is recomputed from adjacent settlements. The
public summary records only requested bounds, requested-window minutes, observed event counts,
process/page counts, layout facts, and transitive SHA-256 bindings. It never records a funding
rate, observed settlement timestamp, local path, device identity, account data, credential, or
runtime market artifact.

Canonical JSON is published atomically with a SHA-256 receipt written last. An existing output is
not overwritten. The schema requires explicit limitations stating that the bounded run does not
prove full settlement chronology, historical lifecycle coverage, gap acceptance, compaction,
catalog readiness, scale behavior, or Gate 2.

## Consequences

- GitHub can review and verify the exact implementation identity, source/canonical bindings,
  counts, and safety boundary without distributing funding data.
- Substituting Landing, predecessor, registry, capacity, Parquet, audit, manifest, or publisher
  identity breaks a binding or fails re-verification.
- Sparse event counts are reported honestly and are never described as consecutive-minute
  coverage.
- Hashes alone cannot reconstruct funding values; retention and backup of runtime data remain
  separate operational work.
- Gate 2 remains closed.

## Rejected alternatives

- Reuse the candle pilot schema: consecutive-minute completeness is the wrong funding semantic.
- Publish settlement timestamps or rates for convenience: unnecessary for GitHub review and
  outside the sanitized evidence boundary.
- Treat an unsaturated response as proof of complete historical chronology: the endpoint supplies
  no such acceptance evidence.
- Record only aggregate counts without hashes: a substituted dataset could claim the same counts.
