# ADR-0043: Decrease-only global public REST throttling

- Status: accepted
- Date: 2026-08-13
- Implements: Phase 2 long-running public acquisition safety

## Context

ADR-0023 and ADR-0032 use a global fixed-rate pacer, explicit application retries, and one
transport attempt for each candle or funding page. ADR-0038 executes campaign children
sequentially, so their per-job pacers cannot multiply the requested rate. The representative
24-month campaign completed at 15 requested RPS with two transport retries, but that bounded run
does not prove that one fixed rate is safe through long venue/network variability.

Bybit's current
[`Rate Limit Rules`](https://bybit-exchange.github.io/docs/v5/rate-limit) document a default IP
limit of 600 requests per five seconds, warn against operating at the edge, identify HTTP 403 as
an IP-frequency ban requiring at least ten minutes without HTTP sessions, identify retCode 10006
as an API-rate limit, and define `X-Bapi-Limit`, `X-Bapi-Limit-Status`, and
`X-Bapi-Limit-Reset-Timestamp` response headers. A production-scale downloader must react to
those signals without converting a temporary high allowance into an unreviewed operating-rate
increase.

## Decision

Add `bybit-v5-response-header-decrease-only-v1` to the candle and funding Landing execution
boundary. Every thread-local public transport exposes one sanitized observation after its single
HTTP attempt: HTTP status, integer Bybit return code, header state (`absent`, `complete`, or
`invalid`), and the three parsed non-negative limit integers when all are consistent. Raw headers,
request URLs, symbols, account data, and response bodies are not part of this observation.

One condition-based pacer remains shared by every worker in a child job. A worker claims a launch
slot only when it is due, so a later observation can reschedule all workers that have not yet
launched. The policy is strictly decrease-only:

- missing or malformed headers never raise the rate and remain counted;
- when complete headers report remaining capacity at or below 20%, effective RPS is capped at the
  lower of its current value and 80% of the reported limit, with a floor of one RPS;
- HTTP 429 or retCode 10006 halves the current effective RPS, never below one, and applies at
  least a one-second global cooldown or a valid future reset delay, capped at ten minutes;
- HTTP 403 records the official ten-minute resume boundary and aborts every waiting launch in the
  current run instead of retrying through an IP ban; verified pages remain resumable; and
- no response can automatically restore or raise RPS. A higher configured target requires a new
  request identity and the existing operator/preflight review.

New v1 Landing manifests add an optional backward-compatible `adaptive_throttling` object under
`request_bound`. It records only the policy, configured/final/minimum RPS, classified observation
counts, reduction/low-headroom/rate-limit/cooldown counts, maximum cooldown, and the invariant
`automatic_increase_count=0`. Verification checks exact fields and internal arithmetic. Older
receipt-committed v1 manifests without the optional object remain valid and immutable.

This decision changes no request/page ownership, application-attempt ceiling, source validation,
canonical schema, gap policy, or campaign concurrency. It uses only unauthenticated public market
endpoints and cannot create an order, bot, transfer, or authenticated request.

## Consequences

- Long campaigns can slow down globally before exhausting a documented response allowance.
- A completed job carries receipt-bound evidence of the signals observed and every decrease made.
- Header absence is visible rather than silently interpreted as unlimited capacity.
- The first HTTP 403 stops current work quickly; resume remains explicit after Bybit's documented
  cooling period and reuses only verified page receipts.
- Successful short runs never tune the operating rate upward.
- A measured long-duration run is still required; implementation alone does not close the Gate 2
  performance criterion.

## Rejected alternatives

- Automatically increase toward the observed header limit: transient allowance is not an
  approved operating rate and may share an IP with other processes.
- Reserve all worker launch times in advance: already reserved slots cannot honor a newly observed
  cooldown promptly.
- Retry HTTP 403 with ordinary exponential backoff: Bybit documents a ten-minute IP-ban response,
  not a normal transient request failure.
- Make the new manifest field mandatory: it would invalidate immutable v1 Landing evidence that
  predates this backward-compatible extension.
- Store raw headers per page: aggregate counters are sufficient and avoid unnecessary runtime
  metadata in committed contracts.
