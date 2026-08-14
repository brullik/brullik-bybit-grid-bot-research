# ADR-0076: Sanitized candle-repair execution outcome

- Status: accepted
- Date: 2026-08-14
- Extends: ADR-0028 bounded repair execution
- Preserves: immutable private repair evidence, fail-closed gap policy, and closed Gate 2

## Context

The full-history boundary diagnostic reduced 11,981,746 missing candle minutes to 76 internal
gaps. Existing child coverage audits can then isolate a genuine `rest_returned_no_data` gap and
the ADR-0027/ADR-0028 workflow can probe it without repeating the full campaign. The private
execution necessarily contains dataset, instrument, symbol, and minute identities, so it cannot
serve directly as the GitHub source-of-truth artifact used by readiness review.

A repair that receives no row is still useful measured evidence. It proves that the bounded
workflow ran, but it must not accept the missing candle, publish a replacement, or encourage
unbounded retries. Funding repair already has an identifier-free public execution projection;
candle repair needs the same separation.

## Decision

Add `grid.bybit-1m-gap-repair-execution-public/v1` and the
`grid-data history-repair-execution-evidence` command. The command re-verifies the complete
receipt-bound private execution chain and projects only aggregate limits, immutable SHA-256
bindings, the executor Git identity, and one of two classifications:

- `exact-gap-repair-completed`; or
- `source-gap-remains`.

The public artifact contains no symbol, instrument or dataset identifier, minute timestamp,
market value, account data, credential, host identity, or runtime path. It records that the parent
was not mutated and no replacement was published. A passing execution is merely replacement
eligible; publication remains a separate ADR-0028 transition.

Existing output is verified and returned unchanged. Re-running the projection performs no market
request. Re-running `execute-history-repair` with the same receipt-verified private output also
reuses that output rather than contacting Bybit, so a persistent source gap has an auditable
no-repeat marker.

## Consequences

- GitHub can retain measured positive or negative candle-repair outcomes without private market
  identities.
- A blocked execution replaces "repair not measured" with "source gap remains" evidence, but it
  does not satisfy deterministic repair or accept an absence reason.
- The original Landing, canonical parent, coverage audit, plan, and private execution remain
  immutable.
- Gate 2 and Phase 3 authority are unchanged.

## Rejected alternatives

- Commit the private execution: it exposes exact market identities that the aggregate readiness
  record does not need.
- Retry until a row appears: that would erase the first dated source observation and introduce an
  unbounded, non-deterministic workflow.
- Publish an empty replacement: exact requested coverage would still be false.
- Treat repeated no-data as accepted lifecycle evidence: first returned data is not authoritative
  historical listing metadata.
