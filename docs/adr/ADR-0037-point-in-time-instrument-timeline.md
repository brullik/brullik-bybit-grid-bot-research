# ADR-0037: Point-in-time instrument timeline and ex-post lifecycle coverage

- Status: accepted
- Date: 2026-08-13
- Implements: Phase 2 dated universe snapshots and no-lookahead selection boundary

## Context

`grid.instrument-registry/v1` binds one receipt-verified Bybit linear inventory snapshot and its
stable `symbolId` identities. The public
[`/v5/market/instruments-info`](https://bybit-exchange.github.io/docs/v5/market/instrument)
response includes `launchTime`, perpetual `deliveryTime`, status, and current trading constraints;
the public status filter also exposes closed instruments. One current snapshot is useful ex-post
coverage evidence, but it is not permission to apply its status, tick/quantity limits, leverage,
funding interval, or known future delisting facts to earlier research decisions.

Gate 2 requires expected history coverage to be explained by listing/delisting metadata, while the
project's no-lookahead rule requires research to use only metadata known at the decision time. A
single interface for both purposes would either leak the future or unnecessarily discard valid
ex-post data-quality evidence. Public trade archive bodies cannot be used to fill this gap because
ADR-0016 excludes tick-level download and retention.

## Decision

Freeze `grid.instrument-timeline/v1` as an immutable, receipt-last aggregate of one or more
receipt-verified `grid.instrument-registry/v1` artifacts. Snapshots are strictly increasing by
their source observation timestamp, bind the complete source artifact/content hashes, retain exact
registry rows, and preserve `bybit-linear-source-symbol-id-v1`. Duplicate timestamps, duplicate
source artifacts, unstable source IDs, malformed rows, and non-canonical ordering fail closed.

The timeline exposes two deliberately separate views:

1. Point-in-time selection chooses exactly the latest snapshot whose observation timestamp is at
   or before the decision timestamp. It fails before the first snapshot, can require a complete
   source inventory, rejects requested IDs absent from that snapshot, and never returns fields
   from a later snapshot.
2. Ex-post lifecycle coverage compares launch and non-null delivery bounds across all observations
   for data-quality accounting only. A normal `deliveryTime=null` to one later non-null delivery
   transition is accepted. Conflicting launch times, conflicting non-null delivery times, closed
   instruments without delivery time, non-positive intervals, and symbol reuse across stable IDs
   remain explicit blockers.

The ex-post view must not be imported as research decision metadata. In particular, a later
delisting boundary may explain why canonical rows end, but it cannot be exposed to a decision made
before that boundary. Undated trading constraints and funding intervals remain available only
through the point-in-time snapshot selected above. Suspensions and source omissions are not
inferred from missing candles or missing archive files.

Freeze `grid.instrument-timeline-summary/v1` as bounded GitHub-safe evidence. It binds the runtime
timeline and every source registry hash; reports snapshot, current-status, delivery-bounded,
open-ended, partial-inventory, and blocker counts; records the immutable implementation commit;
and contains no full instrument rows, local paths, credentials, account data, or market values.
Any partial source inventory or lifecycle conflict produces `status=blocked`; it is evidence to
preserve, not a reason to guess.

The timeline reads only public instrument-registry artifacts. It does not download public-trade
archive bodies or tick rows, call private endpoints, mutate canonical market data, authorize
research/live execution, or close Gate 2.

## Consequences

- Repeated inventory snapshots can accumulate without rewriting older evidence.
- Research has a small explicit API that fails closed instead of silently using today's metadata.
- Data-quality review can use exchange-reported lifecycle boundaries without making them future
  features.
- Historical periods before the first available snapshot remain unavailable to strict as-of
  metadata selection until separately dated evidence is added.
- A partial Bybit status inventory remains a visible Gate 2 blocker even when all observed rows and
  identities verify.
- Suspension intervals, historical fee schedules, funding cadence changes, and retrospective
  universe gaps still require separate dated evidence.

## Rejected alternatives

- Apply the latest registry to every historical timestamp: leaks future status and constraints.
- Treat launch/delivery fields as general metadata effective from their event timestamp: this
  would improperly backdate unrelated fields carried in the same current response.
- Infer delisting or suspension from a missing candle/archive file: source absence is not an
  authoritative lifecycle event.
- Download raw public-trade archives to infer activity: violates ADR-0016 and the owner's 1m-only
  decision.
- Mutate one timeline file in place: destroys reproducibility and receipt identity.
