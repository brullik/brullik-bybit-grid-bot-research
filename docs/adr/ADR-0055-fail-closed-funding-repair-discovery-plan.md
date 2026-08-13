# ADR-0055: Fail-closed funding repair discovery planning

- Status: accepted
- Date: 2026-08-14
- Implements: Phase 2 funding repair planning boundary

## Context

ADR-0034 deliberately blocks every unexplained funding-interval change because the public history
endpoint returns settlements and rates but no dated interval schedule. A missing response row in
an otherwise stable series commonly appears as `C, N*C, C`, but a valid historical schedule
change may also alter the observed deltas. Current `instruments-info.fundingInterval` is not dated
and cannot distinguish those cases without future leakage.

Repair must therefore begin as bounded source discovery, not as automatic cadence acceptance or
canonical mutation. The plan must be reproducible from the exact private anomaly inventory while
keeping the accepted audit blocked.

## Decision

Freeze `grid.bybit-funding-repair-plan/v1` and expose it through
`grid-data plan-funding-repair`. Planning re-verifies the receipt-committed blocked funding audit,
recomputes it from Landing, registry, capacity, canonical data, and both Git identities, and
requires byte-equivalent semantic content. The sole blocker may be
`unexplained_interval_change`; empty source windows, parity failures, duplicate/unrequested keys,
lifecycle failures, or predecessor/internal interval mismatches are not repair-plan eligible.

For each source series, every changed interval edge must belong to an isolated
`C, N*C, C` sandwich where `N` is an integer greater than one. The planner derives candidate
settlement timestamps only from the two adjacent source-observed settlements. It never reads the
current instrument funding interval, treats the inferred timestamps as accepted events, or
changes the blocked audit. An unbracketed change, a shorter interval, or any transition not fully
explained by those isolated sandwiches fails closed.

Each task embeds one ordinary `grid.bybit-funding-history-request/v1`, the exact expected
candidate timestamps, and the source-observed left settlement as predecessor evidence. Page
limits are raised only within the existing 200-row endpoint ceiling so a candidate response
cannot be accepted at saturation. One plan is bounded to 1,000 tasks, 1,000 candidate
settlements, and 100,000 maximum HTTP attempts. Planning executes no request and mutates neither
Landing nor canonical storage.

The plan binds the coverage artifact/content hash, private anomaly-record hash, funding Landing
manifest, canonical manifest, and planner Git identity. It contains exact runtime settlement
identities and is therefore private operational evidence: its schema and implementation belong
in GitHub, but real generated plans do not. A later execution transition must require every
candidate timestamp to be returned exactly once before a separate immutable child publication
can be considered.

This decision does not implement execution or publication, accept a schedule change, weaken
ADR-0034, modify a parent, close Gate 2, or authorize private/live Bybit operations.

## Consequences

- A likely omitted source row can be queried through the existing public, receipt-resumable
  funding path without inventing historical metadata.
- Legitimate or ambiguous cadence changes remain blocked when the exact candidate query returns
  no event or when their shape is not an isolated integer-multiple sandwich.
- Recomputing all bindings prevents a substituted audit or runtime dataset from producing a plan.
- Exact candidate timestamps stay out of GitHub evidence; later sanitized execution evidence must
  expose only hashes and aggregate counts.

## Rejected alternatives

- Accept `C, N*C, C` as proof of missing data: the same shape can be a real temporary schedule.
- Use current `fundingInterval`: it is undated and can leak future metadata.
- Plan from public aggregate reason counts alone: exact source series and anomaly identity would
  not be bound.
- Repair empty windows automatically: no neighboring settlement evidence proves what belongs in
  the window.
- Mutate the existing canonical file: this violates immutable receipt-last lineage.
