# ADR-0049: Sanitized funding source-boundary evidence

- Status: accepted
- Date: 2026-08-13
- Implements: GitHub source-of-truth evidence for ADR-0048

## Context

ADR-0048 runtime output must retain symbols, stable instrument IDs, and the exact first two
source-observed settlement timestamps so later acquisition can use a proved predecessor. Those
facts are necessary locally but are outside the repository-safe aggregate boundary established by
ADR-0025. GitHub nevertheless needs a reproducible record that the discovery completed under
merged code, that every source page and receipt still verifies, and that every requested series
has a predecessor-backed canonical start.

The evidence must also distinguish application attempts from classified HTTP responses. A
successful runtime manifest with missing response observations is valid resumable Landing state,
but it is not sufficient for strict public long-run qualification under ADR-0044/ADR-0045.

## Decision

Freeze `grid.phase2-funding-source-boundary/v1` and add
`grid-data funding-source-boundary-evidence`.

The builder first invokes the complete ADR-0048 verifier. It then projects only:

- request, registry, plan, and manifest SHA-256 bindings;
- immutable discovery and evidence-builder Git identities;
- requested scan bounds and aggregate symbol/event/page/attempt/retry counts;
- aggregate predecessor-proven and canonical-start-proven counts;
- the exact sanitized decrease-only throttling counters and transport-attempt accounting; and
- fixed public-source, storage-redaction, process, and limitation facts.

Strict evidence requires the classified response-observation count to cover every completed page
response. Transport attempts without a response remain explicit and bounded. The payload carries
an embedded canonical content hash and is published atomically with the standard evidence receipt.

The schema and redaction tests reject symbols, instrument IDs, per-series counts, observed
settlement timestamps, funding rates, runtime paths, device/account data, credentials, and private
endpoint facts. Requested aggregate scan bounds are permitted, consistent with existing campaign
evidence. Runtime pages and manifests remain ignored and are never copied into Git.

## Consequences

- GitHub can bind measured source-boundary progress to exact merged code and private runtime
  receipts without disclosing per-instrument boundary data.
- Aggregate counts prove every requested series obtained both required settlements, but do not
  reveal which settlement belongs to which market.
- The evidence proves the retained public endpoint response and verification chain only. It does
  not prove an independent venue ledger, accept gaps/cadence changes, publish canonical data, or
  close Gate 2.
- No API key, account identifier, private endpoint, order, grid bot, or transfer is used.

## Rejected alternatives

- Commit the runtime manifest: it contains symbols, IDs, and exact observed timestamps.
- Publish per-symbol hashed aliases: small candidate sets make such aliases linkable and add no
  acceptance value.
- Omit response accounting: successful pages alone do not prove the ADR-0044/0045 observation
  boundary.
- Treat source-boundary completion as coverage acceptance: availability and historical cadence
  remain separate fail-closed audits.
