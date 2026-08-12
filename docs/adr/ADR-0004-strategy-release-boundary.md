# ADR-0004: Immutable Strategy Release as Research-to-Live Boundary

- Status: accepted
- Date: 2026-07-28

## Context

Live must operate independently from research and must not consume mutable notebooks, ad hoc parameter files, or incomplete experiments. A positive backtest alone is not sufficient authorization.

## Decision

The only supported research-to-live interface is an immutable, hash-verified strategy release with lifecycle:

```text
building → failed
building → complete → verified → promoted → revoked
```

Only a `promoted` compatible release may start live. Promotion is an explicit owner/PM action and states the allowed mode: shadow, manual, or automated.

## Consequences

- live behavior is reproducible and auditable;
- research can be offline during live;
- parameter drift is prevented;
- release schema/verifier/promotion registry become critical infrastructure;
- any strategy change requires a new release.

## Rejected alternatives

- Live reads “latest successful experiment”: ambiguous, mutable, and self-promoting.
- Shared database table edited by researchers: weak authorization and rollback.
- Copy a YAML manually to the live host: insufficient provenance and integrity.
