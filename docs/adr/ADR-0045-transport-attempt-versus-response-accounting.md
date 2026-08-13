# ADR-0045: Transport-attempt versus HTTP-response accounting

- Status: accepted
- Date: 2026-08-13
- Supersedes: the strict attempt-equals-response criterion in ADR-0044

## Context

The first measured ADR-0044 campaign completed 9,600 public pages in 9,621 bounded transport
attempts. Every one of the 9,600 successful HTTP responses had a sanitized ADR-0043 observation;
the other 21 attempts ended in a retryable connection/protocol failure before any HTTP response
existed. The original strict builder compared response observations with all transport attempts,
so it would incorrectly reject a correctly classified run by demanding response headers from a
non-response.

Weakening the check to accept any difference would also be wrong: a client that returned a
successful page without exposing its response observation must still fail qualification.

## Decision

Distinguish transport attempts from received HTTP responses in the sanitized campaign projection.
For every verified child, strict qualification requires its response-observation count to be at
least its completed page count. This proves that every page-producing successful response is
covered. The existing ADR-0043 verifier independently proves that every recorded response
observation is classified exactly once as complete, absent, or invalid.

At aggregate level record:

- `transport_attempt_count`, equal to the receipt-verified Landing attempt total;
- `response_observation_count`, summed from verified child adaptive summaries;
- `transport_attempt_without_response_count`, their non-negative difference;
- `completed_page_response_coverage_complete`;
- `response_observation_classification_complete`; and
- `transport_attempt_accounting_complete`.

The difference is described as attempts without a response observation, not as unobserved HTTP
responses. Under the production transport boundary, an application attempt always consumes the
observation in `finally`; HTTP success/error responses create an observation, while connection,
protocol, timeout, or decode failures before a usable response may not. The aggregate evidence
does not invent headers or a status code for those failures.

Strict mode still rejects a child whose observation count is lower than its completed page count,
mixed legacy/current summaries, missing timing, malformed summaries, or inconsistent aggregate
attempt arithmetic. It may accept bounded no-response retries when every completed page response
is covered.

## Consequences

- Real network failures remain visible rather than being mislabeled as missing rate-limit headers.
- Qualification does not require impossible headers from a transport attempt with no response.
- A client that silently omits observations for successful pages still fails closed.
- Existing manifests and campaign artifacts remain immutable; only the not-yet-published optional
  aggregate projection fields change.
- The measured campaign may be projected after this correction, but the result still does not
  accept coverage, close Gate 2, or authorize private/live actions.

## Rejected alternatives

- Treat every retry as an HTTP response: connection and protocol failures do not have one.
- Count no-response attempts as `header_state=absent`: that would claim an HTTP header surface that
  never existed.
- Ignore the attempt/response difference: it would hide material retry behavior.
- Require zero no-response retries: bounded transient transport failures are already an accepted
  resumable acquisition condition and are not a rate-limit-policy failure.
