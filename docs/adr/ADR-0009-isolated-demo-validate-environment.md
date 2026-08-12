# ADR-0009: Isolated Demo Environment for Validate-Only Feasibility

- Status: proposed; feasibility-gated
- Date: 2026-08-12

## Context

The M1 private feasibility probe contains only Bybit's native Futures Grid validate endpoint. Its
default Testnet environment can be inaccessible through some regional website routes, while using
a production API key introduces avoidable risk even when the called endpoint is validate-only.

Bybit officially provides a Demo Trading account isolated from real funds at
`https://api-demo.bybit.com`. The published Demo endpoint list does not currently include
`/v5/fgridbot/validate`, so support must be treated as an observed feasibility question rather
than an assumed capability.

## Decision

Add `demo` as a separately selected validate-only environment with a hard-coded official origin
and dedicated `BYBIT_DEMO_API_KEY` / `BYBIT_DEMO_API_SECRET` process variables. Preserve these
safety properties:

- the package exposes no private `/v5/` literal except `/v5/fgridbot/validate`;
- redirects and retries remain disabled;
- credentials remain process-only and are excluded from reports;
- Testnet remains the default;
- mainnet continues to require an explicit validate-only acknowledgement; and
- a mainnet discovery runner requires visible owner confirmation that Unified Trading Account
  migration is complete before it requests credentials;
- a Demo failure is recorded as feasibility evidence and never triggers fallback to mainnet.

New reports use `grid.bybit-fgrid-validate-probe/v2`; the v1 schema remains immutable.

## Consequences

- The owner can test from the main Bybit website's isolated Demo Trading mode without exposing
  real funds.
- Keys from Demo, Testnet, and mainnet cannot be silently interchanged by environment-variable
  naming.
- Demo may return an unsupported-route response because the endpoint is absent from Bybit's
  published Demo availability list.
- Any future mainnet probe still requires a separate owner decision; Demo failure never grants
  that permission.

## Rejected alternatives

- Automatically fall back from Demo to mainnet: this would cross a real-funds boundary silently.
- Reuse mainnet variable names for Demo: an environment mix-up could expose a production key.
- Add create/close endpoints to obtain stronger evidence: M1 authorizes validation only.
