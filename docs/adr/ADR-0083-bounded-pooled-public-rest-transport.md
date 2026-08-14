# ADR-0083: Bounded pooled public REST transport

- Status: accepted
- Date: 2026-08-14
- Extends: ADR-0023, ADR-0038, and ADR-0043
- Preserves: request identity, retry ceilings, global pacing, receipts, and Gate 2 criteria

## Context

The receipt-resumable downloader currently creates a thread-local `urllib` transport inside every
monthly child job. `urllib` does not provide an application-owned connection pool, and a history
campaign creates a new worker pool for every immutable child. The completed five-instrument
campaign therefore repeatedly paid DNS/TCP/TLS setup cost and materially underused its already
approved 10-RPS launch budget. Raising RPS would not remove that overhead and would require new
operating evidence.

## Decision

Add a public-only `PooledHttpsJsonTransport` implemented with the Python standard library. One CLI
execution owns one transport and shares it across its worker clients and, for a campaign, across
sequential immutable children. The transport:

- accepts only an HTTPS origin and the existing `/v5/market/*` or exact public announcement path;
- limits simultaneous checked-out connections to the existing worker bound, never above 32;
- reuses only fully consumed successful HTTP/1.1 responses and closes a connection after a
  protocol failure, non-2xx response, oversized response, or server close signal;
- caps every public JSON response at 8 MiB;
- retains the existing bounded retry/backoff behavior and exposes the same thread-local sanitized
  rate-limit observation contract; and
- closes all idle connections when the CLI operation completes.

The acquisition and throughput commands use one shared pool per operation. Low-volume inventory,
announcement, and public-sample commands retain the existing simple transport. The ADR-0043
condition-based pacer still owns launch rate and cooldown decisions. Target RPS, worker ceiling,
application-attempt ceiling, page ownership, immutable artifacts, receipt-last completion,
resume behavior, response validation, and public endpoint scope do not change.

## Consequences

- A campaign can reuse established TLS sessions across monthly children instead of paying a new
  handshake for nearly every page group.
- Connection concurrency remains bounded independently of the executor and cannot multiply the
  configured global launch rate.
- Rate-limit observations remain isolated by worker thread even though the connection pool is
  shared.
- Unit tests cover keep-alive reuse, failure eviction, concurrency bounds, regional-block
  classification, observation isolation, and deterministic close behavior.
- A bounded post-merge public throughput measurement is still required before a speedup is cited
  as evidence. This change cannot close Gate 2 or authorize Phase 3 or live execution.

## Rejected alternatives

- Raise the campaign RPS: this changes the reviewed operating rate without eliminating connection
  setup cost.
- Add an unbounded global session: it could exceed the worker limit and make shutdown ambiguous.
- Add a third-party HTTP dependency only for pooling: the standard library provides the required
  bounded HTTP/1.1 behavior without expanding the public adapter dependency set.
- Change Landing or campaign contracts to name the transport: immutable evidence is already bound
  to the implementation identity, while the data and retry contracts remain unchanged.
