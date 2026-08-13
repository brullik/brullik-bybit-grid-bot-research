# ADR-0052: Receipt-bound funding source-boundary admission

- Status: accepted
- Date: 2026-08-13
- Implements: full-history funding campaign admission from ADR-0048

## Context

The registry `launchTime` is lifecycle metadata, not proof that the public funding endpoint has a
settlement immediately after launch. ADR-0048 discovers the first two source-observed settlements
and defines the second as canonical start with the first as its exact predecessor. The campaign
coordinator previously generated funding children from `launchTime + one minute`; for historical
instruments this could create many empty jobs and ask the first child to find an unspecified last
settlement anywhere between launch and start.

## Decision

Add optional `--funding-source-boundary-root` admission to `grid-data history-campaign`. When
provided, preflight fully verifies the completed ADR-0048 plan, timestamp-only pages, manifest,
receipts, and allowlist before deriving any child plan. Admission fails unless:

- the discovery and campaign use the exact same registry artifact;
- discovery scan bounds cover the complete campaign request range;
- discovery symbols exactly equal the requested campaign symbols;
- each result binds the same stable instrument ID;
- predecessor equals the first observed settlement and strictly precedes canonical start; and
- canonical start lies inside the campaign range.

Funding lifecycle intersections are clipped to each proven canonical start. The first generated
funding child receives the proven predecessor timestamp in its immutable `FundingSeries`; its
boundary REST task requests exactly that aligned minute. Later monthly children retain the
existing predecessor query because their predecessor is established by the immediately preceding
source chronology, not the global discovery edge.

The campaign plan optionally records only discovery manifest, plan, request, and implementation
identity hashes. The GitHub-safe campaign evidence may project the discovery manifest hash. Exact
per-symbol starts and predecessors remain local in the verified discovery and child plans. Legacy
campaign plans and funding jobs without this extension remain valid.

The option is rejected for campaigns that do not request funding. It changes no candle scope,
funding values, cadence audit, canonical acceptance, Gate 2 decision, or live/risk gate. All
requests remain unauthenticated public market-data calls.

## Consequences

- Full-history funding download begins at a source-proven settlement instead of an inferred launch
  boundary.
- The first funding interval has an exact receipt-bound predecessor and cannot silently accept a
  different settlement.
- Empty pre-source monthly funding jobs are eliminated.
- Boundary tampering, registry substitution, partial symbol discovery, or insufficient scan range
  fails before campaign mutation.

## Rejected alternatives

- Use `launchTime + one minute`: lifecycle metadata is not source-availability evidence.
- Copy timestamps into the public campaign request: that duplicates private runtime facts and
  weakens the discovery receipt chain.
- Query any predecessor before canonical start: it does not prove the intended first interval.
- Apply the discovery boundary to every month: later children require the immediately preceding
  settlement for that month, not the global oldest predecessor.
