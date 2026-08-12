# ADR-0015: Current-Universe Bootstrap and Incremental Capacity Evidence

- Status: proposed; Gate 1 evidence only
- Date: 2026-08-12

## Context

The 700-instrument, ten-year capacity objective is deliberately conservative. It proves that the
architecture can grow without redesign, but it is not a claim that every current instrument has
ten years of history. Current Bybit lifecycle metadata already shows a materially smaller
point-in-time row envelope.

The existing v3 capacity projection applies measured synthetic and bounded real-market bytes per
row to the full design envelope. It does not answer two operational questions:

1. how much canonical storage the currently observed lifecycle envelope may require; and
2. how the one-time bootstrap differs from routine incremental updates.

Using a canonical candle ratio to size raw tick-trade archives would be unsafe. A high-throughput
downloader also needs its own measured source-byte inventory, staging budget, resumability, and
free-space preflight before Phase 2 can run.

## Decision

Add an append-only `grid.current-universe-capacity/v1` evidence contract. Its builder accepts only:

- a receipt-, schema-, and embedded-hash-verified
  `grid.bybit-history-source-assessment/v1` no older than the configured limit;
- the receipt- and schema-verified `grid.capacity-projection/v3` calibration; and
- a fresh receipt- and schema-verified `grid.workstation-snapshot/v1` for the output volume.

The builder rechecks the v3 layout-to-metric bindings and tolerates only the few-byte projection
difference implied by publishing bytes per row to nine decimal places. It rejects stale,
future-dated, tampered, cross-layout, or internally inconsistent evidence before replacing an
existing output.

The output keeps these storage scenarios separate:

- `bootstrap-canonical-building`: the first canonical version being built before its receipt;
- `full-rebuild-active-plus-building`: an accepted version plus a replacement being built;
- `incremental-one-day`: new closed minutes for current `Trading` instruments;
- `incremental-maximum-31-day-partition`: the bounded rewrite of one calendar-month partition;
- `planning-64-byte-active-plus-building`: the conservative design-envelope row width applied to
  the current lifecycle estimate.

Routine updates append only new closed intervals and repair detected gaps. They do not redownload
or rewrite unaffected immutable partitions. Raw source-archive headroom remains explicitly
`unknown-headroom-requires-downloader-preflight`; none of the canonical scenarios may be used to
declare a full archive bootstrap safe.

The point-in-time projection does not reduce the formal 700 × ten-year capacity objective, change
the provisional hardware recommendation, select P-001 through P-005, close Gate 1, or authorize
Phase 2.

## Consequences

- The one-time initial load and small recurring updates are no longer conflated.
- Disk purchases can distinguish measured current canonical needs from design capacity and raw
  archive/staging uncertainty.
- A later downloader can consume the scenario vocabulary for its own free-space preflight while
  retaining a separately measured raw-source budget.
- Current launch/delivery fields remain undated metadata and cannot prove historical eligibility
  or actual gap-free coverage.
- A new immutable evidence chain is required whenever the inventory or measured volume changes.

## Rejected alternatives

- Replace the formal capacity envelope with the current snapshot: this would weaken an accepted
  scale requirement and make future growth a redesign risk.
- Treat three full canonical copies as permanent storage: bootstrap and incremental operation have
  different lifetimes and bounded rewrite scopes.
- Treat one canonical copy as sufficient for every operation: immutable replacement requires the
  accepted source and building target to coexist during a full rebuild.
- Infer raw tick-archive size from candle bytes per row: source trades have a different cardinality
  and compression distribution.
- Start full-history download because measured canonical rows fit: raw source/staging headroom and
  the Phase 2 downloader contract remain unproved.
