# ADR-0047: Single-snapshot campaign input admission

- Status: accepted
- Date: 2026-08-13

## Context

The first full-lifecycle preflight for five instruments over 2018-01-01 through 2026-07-31
resolved 1,467 deterministic month/type/bucket jobs and 46,227 pages. It passed the fresh host
gates but took 125.6 seconds before any mutation or network request. Inspection showed that every
child request independently reopened, parsed, receipt-verified, and hashed the same 1,757-record
instrument registry and capacity evidence. The child outputs correctly shared the same hashes, so
the repeated I/O did not add evidence strength within one preflight invocation.

The campaign boundary must still reject stale, mismatched, or mutated evidence and must recheck
inputs on every operator invocation. Caching across invocations or trusting an unverified object
would weaken that boundary.

## Decision

At the start of each `preflight_history_campaign` invocation, load and receipt-verify the exact
instrument-registry and capacity artifacts once. Retain their resolved paths, parsed payloads, and
artifact SHA-256 values in one immutable in-process `VerifiedRequestEvidence` snapshot. Every
generated candle/funding child resolver must consume that snapshot and reject it unless its paths
match the explicit campaign inputs.

All child specs, budgets, request hashes, registry/capacity hashes, plans, page tasks, lifecycle
intersections, and aggregate resource calculations remain unchanged. Execute and resume still
call the complete campaign preflight again, creating a new verified snapshot from current bytes.
Nothing is cached across processes or persisted as an authority.

The operator summary records `preflight_elapsed_ms` using a monotonic clock so the same full-scope
preflight can be compared after merge. The initial 125.6-second observation is the baseline; a
post-merge run on the same 1,467-job/46,227-page scope is required before qualification.

## Consequences

- Registry/capacity I/O and receipt verification are constant per campaign invocation rather than
  proportional to child-job count.
- All children are derived from one internally consistent immutable evidence snapshot.
- A new invocation still observes and rejects changed or invalid evidence; there is no durable
  cache to invalidate.
- No page bound, storage/memory gate, request rate, retry policy, source validation, receipt,
  coverage rule, funding-cadence rule, or Gate 2 criterion changes.
- No exchange request, market-data mutation, credential, or live/private capability is added.

## Rejected alternatives

- Cache verified evidence across commands: file bytes could change between invocations.
- Skip child evidence bindings: every child plan must retain exact transitive hashes.
- Reduce job/page/resource bounds to improve planning time: this would alter safety rather than
  remove redundant work.
- Increase concurrent child execution: child pacers must remain sequential and globally bounded.
