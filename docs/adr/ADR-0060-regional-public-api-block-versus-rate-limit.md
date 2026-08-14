# ADR-0060: Regional public-API block versus rate-limit classification

- Status: accepted
- Date: 2026-08-14
- Refines: ADR-0043 HTTP 403 handling
- Implements: Phase 2 public acquisition failure safety

## Context

ADR-0043 treated every HTTP 403 from the public Bybit origin as the documented IP-frequency ban.
Bybit's current
[`Rate Limit Rules`](https://bybit-exchange.github.io/docs/v5/rate-limit) identify the rate-limit
case specifically as `403, access too frequent` and require a ten-minute stop. A measured campaign
resume from the reference host instead received a CloudFront error stating that access from the
current country was blocked. Treating that response as an IP ban invented a ten-minute recovery
condition for a regional-access failure and produced misleading operator guidance.

The downloader must stop safely in both cases. It must not retry a regional block, suggest a
bypass, retain the response body, or weaken the documented cooldown for an actual IP rate limit.

## Decision

The public stdlib transport reads at most 64 KiB from an HTTP error body solely for in-process
classification and then discards it. An HTTP 403 is classified as
`regional-access-block` only when the bounded, case-insensitive body contains the combined
CloudFront, block, and country markers observed at the public origin. The raw body, URL, country,
IP address, symbol, and request parameters are never included in an exception, observation,
manifest, log payload, or GitHub evidence.

All other HTTP 403 responses retain ADR-0043's `rate-limit` classification and ten-minute abort
boundary. HTTP 429 and Bybit retCode 10006 are unchanged. The sanitized in-memory response
observation gains a backward-compatible failure class with `none` as its default.

On `regional-access-block`:

- the condition-based child-job pacer aborts every waiting launch;
- candle, funding, and funding-boundary page acquisition performs no application retry;
- the failure is not counted as a rate-limit event, rate reduction, cooldown, or IP-ban resume
  timestamp; and
- operator text says to resume only from an officially supported network and region. It does not
  name or attempt an alternate hostname, proxy, VPN, or evasion path.

No availability probe or additional HTTP request is added. Existing immutable plans, pages,
manifests, receipts, adaptive summaries, request accounting, and canonical contracts are
unchanged. A failed regional run remains receipt-resumable from already verified pages.

## Consequences

- The current regional blocker is reported accurately and fails after one application attempt.
- Genuine Bybit IP-frequency bans still enforce ADR-0043's ten-minute stop.
- A response body is used only as bounded ephemeral control input and cannot enter stored
  evidence.
- The remaining full-history campaign is still blocked until an officially supported network and
  region can reach the public endpoint; this decision does not bypass that blocker or close Gate
  2.

## Rejected alternatives

- Keep treating every 403 as an IP ban: it gives a false resume time for a regional block.
- Retry or rotate hosts after a regional block: that would evade an access control and multiply
  requests.
- Persist the body for diagnosis: the stable classification is sufficient and avoids retaining
  provider-generated location/network text.
- Add a separate startup probe: it would add an unneeded request and complicate ADR-0045 attempt
  accounting; the first already-planned page response is enough.
