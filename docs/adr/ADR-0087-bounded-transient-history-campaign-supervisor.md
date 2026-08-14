# ADR-0087: Bounded transient history-campaign supervisor

- Status: accepted
- Date: 2026-08-14
- Extends: ADR-0023, ADR-0038, ADR-0043, ADR-0059, and ADR-0060
- Preserves: immutable request identity, per-page attempts, explicit rate-limit resume, and Gate 2

## Context

A receipt-resumable history campaign intentionally exits when one page exhausts its application
attempts. Re-running the same command safely verifies completed children and fetches only missing
page identities, but the operator must notice and manually restart after an ordinary DNS or socket
outage. During the current-universe bootstrap, one temporary `getaddrinfo` failure stopped both
independent candle campaign shards even though the public endpoint became reachable again and all
completed receipts remained valid.

Blind shell loops are not acceptable. They can retry contract, capacity, regional-access, IP-ban,
or malformed-source failures; hide the number of campaign invocations; and run forever. ADR-0043
and ADR-0060 also require HTTP 403 rate limits and regional blocks to remain explicit operator
resume boundaries rather than ordinary automatic retries.

## Decision

Add `grid-data supervise-history-campaign` as an opt-in wrapper around the unchanged production
`history-campaign` command. Every invocation performs the normal fresh preflight, creates a new
bounded HTTPS pool, and uses the same immutable campaign request and existing page/child receipts.
The standard command remains unchanged.

The supervisor accepts one through 16 total campaign invocations (default eight) and a base
cooldown from 10 through 600 seconds (default 30). A failed retry waits an exponential cooldown,
capped at 600 seconds. It emits only `grid.history-campaign-supervisor-event/v1` JSON objects with
the invocation number, safe failure class, cooldown, retry decision, and fixed invocation bound.
Runtime paths, page/job identity, exception text, request parameters, market values, and response
bodies are excluded.

Automatic resume is allowed only when the bounded exception chain proves one of:

- DNS resolution failure;
- an allowlisted connection reset/abort/refusal, timeout, unreachable network/host, broken pipe,
  remote disconnect, incomplete response, or TLS EOF; or
- an HTTP 5xx response already exhausted by the existing transport/application attempt layers.

Everything else fails closed on the first supervisor invocation. In particular, the supervisor
never retries an adaptive IP-rate-limit abort, HTTP 403/429 classification, Bybit retCode 10006,
regional-access block, HTTP client error, stale lock, capacity rejection, receipt/contract drift,
invalid JSON/decimal/OHLC, or any unclassified exception. It adds no availability probe and cannot
increase configured RPS, worker count, transport attempts, or application attempts per page.

A new invocation can repeat attempts for the first still-missing page, so the outer invocation
count is a distinct explicit request bound. When it is exhausted the original exception is
re-raised. Successfully receipted pages and children are never requested again.

## Consequences

- Short DNS, route, connection, and upstream 5xx interruptions no longer require repeated manual
  campaign commands.
- The exact retry envelope and cooldown decisions are visible in ignored operational JSONL logs.
- Receipt verification and fresh capacity checks still precede every resumed mutation.
- Extended outages stop after a finite bound; the operator can inspect the safe classification
  before choosing any later invocation.
- The supervisor changes no dataset, Landing, manifest, receipt, evidence, canonical, catalog,
  coverage, risk, Gate 2, Phase 3, private API, or live contract.

## Rejected alternatives

- Retry every non-zero CLI exit: it would bypass explicit rate-limit, region, contract, and
  capacity stop conditions.
- Run forever until success: request and elapsed-time exposure would be unbounded.
- Probe Bybit before every restart: the first already-planned missing page is sufficient and an
  extra probe would complicate request accounting.
- Change per-page attempts in the immutable campaign request: that creates a new campaign rather
  than safely supervising the existing receipt-resumable one.
- Persist exception text as evidence: stack traces contain private runtime paths and are not needed
  for the stable failure classification.
