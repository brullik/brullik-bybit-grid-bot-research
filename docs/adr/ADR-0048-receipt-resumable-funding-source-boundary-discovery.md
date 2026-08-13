# ADR-0048: Receipt-resumable funding source-boundary discovery

- Status: accepted
- Date: 2026-08-13
- Implements: Phase 2 full-history funding source admission

## Context

The current instrument registry carries a dated observation of Bybit `launchTime`, but that field
does not prove that `GET /v5/market/funding/history` returns a settlement before an arbitrary
historical campaign boundary. ADR-0032 correctly requires exactly one preceding settlement for
each canonical funding series. A five-instrument full-lifecycle attempt therefore stopped at its
first funding child when the registry-bounded predecessor query returned no row. Eight already
receipted candle children remained reusable; the missing predecessor was not invented or ignored.

The public funding endpoint accepts an inclusive `endTime`, returns at most 200 rows in reverse
chronology, and does not expose dated historical interval metadata. Full-history acquisition needs
a separate way to establish the earliest source-returned settlement and the earliest settlement
that has a source-returned predecessor. That discovery must not retain funding rates merely to
find a timestamp boundary, and it must remain independently bounded, resumable, and verifiable.

## Decision

Add the read-only `grid-data funding-source-boundary` workflow and freeze the request, plan,
timestamp-page, manifest, and receipt v1 contracts.

An operator request supplies sorted unique symbols, an inclusive minute-aligned closed scan range,
and explicit page/concurrency/rate/retry limits. No instrument ID or claimed source boundary is
caller-controlled. No-mutation preflight receipt-verifies the current Bybit-linear registry,
admits only USDT-settled linear perpetuals, intersects the scan with observed launch/delivery
bounds, binds an immutable Git identity, and checks a fresh same-device SSD/NVMe snapshot,
available memory, the 70% total-memory ceiling, and free space including the operating reserve.

For each symbol, execution requests public `GET /v5/market/funding/history` backward with both
`startTime` and `endTime`, a maximum 200-row page, and the next inclusive end equal to the oldest
returned timestamp minus one millisecond. Saturated pages are valid because their cursor is
advanced explicitly; discovery continues until an empty page or the closed lower bound is
reached. The hard bounds are 700 symbols, 32 workers, 96 configured RPS, five application
attempts, and 512 pages per symbol. The 512-page ceiling covers more than 6.1 million minutes
(over 11 years) at a one-hour settlement cadence while still failing closed if the source
requires more.

Every response must contain the requested symbol, unique reverse-chronological minute timestamps,
and a finite exact-decimal funding-rate string inside the requested range. Only timestamps are
persisted. The rate is validated and discarded. Each normalized page is committed atomically with
its SHA-256 receipt; identical reruns resume from consecutive verified pages. One global
ADR-0043 decrease-only pacer covers all workers, and its sanitized response-accounting summary is
bound into the final manifest.

Completion requires at least two source-returned settlements per symbol. The oldest observed
settlement is predecessor-only evidence; the second-oldest is the earliest canonical start with a
provable predecessor. The manifest is committed with a separate receipt, followed by a final
completion receipt. Verification rechecks the exact plan, every page byte and receipt, pagination,
chronology, derived boundary, adaptive summary, manifest, root identity, and complete file
allowlist. Orphans, symlinks, partial pairs, stale locks, changed inputs, resource loss, invalid
rates, exhausted bounds, or fewer than two settlements fail closed.

The runtime discovery contains symbols, instrument IDs, and observed settlement timestamps and
therefore remains outside Git. Only a separate schema-bound aggregate projection that excludes
those identities and timestamps may be committed under ADR-0025. Discovery does not change the
ADR-0032 predecessor rule, accept source gaps, establish historical funding cadence, publish a
canonical dataset, or close Gate 2.

## Consequences

- Registry `launchTime` remains a conservative query bound, not source-availability proof.
- Full-history funding requests can begin only at a source-observed settlement whose predecessor
  is also receipt-proven; absence before that point remains explicit.
- A process failure retains completed page receipts. A crash that leaves `.run-lock` is stale
  evidence requiring explicit repair, consistent with existing Landing workflows.
- Exact funding values are never added to this discovery store or its future GitHub projection.
- The workflow uses no API key, account identifier, private endpoint, order, grid bot, or transfer.

## Rejected alternatives

- Treat registry launch time as the first funding settlement: metadata is not endpoint evidence.
- Start canonical funding at the first returned settlement: its interval has no predecessor.
- Use current `fundingInterval` to synthesize the predecessor: undated metadata may leak future
  cadence and cannot prove a source event.
- Stop on an underfilled page: the endpoint contract does not make underfill a terminal proof;
  an empty page or the explicit lower bound is required.
- Persist rates in discovery pages: values are unnecessary for boundary selection and enlarge the
  sensitive runtime surface.
- Automatically delete stale locks or partial artifacts: ambiguous crash state must be repaired
  explicitly rather than silently rewritten.
