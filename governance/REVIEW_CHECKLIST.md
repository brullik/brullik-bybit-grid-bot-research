# Review Checklist

## Scope and governance

- [ ] Motivation and final outcome are clear.
- [ ] Change stays within approved scope and non-goals.
- [ ] Acceptance criteria were not weakened by the implementation.
- [ ] A new/superseding ADR exists for material decisions.
- [ ] Owner approval exists for risk/live changes.

## Contracts and correctness

- [ ] Identities, units, time boundaries, nulls, and rounding are explicit.
- [ ] No lookahead or row-order joins.
- [ ] Mutable/partial artifacts cannot be consumed as complete.
- [ ] Error/uncertain/restart paths are covered.
- [ ] Exact execution arithmetic is preserved.

## Architecture

- [ ] Data/research/release/live boundaries remain intact.
- [ ] Live does not depend on historical/research storage or packages.
- [ ] Private credentials are not introduced outside live.
- [ ] Side effects are isolated behind explicit adapters.
- [ ] No unnecessary distributed/native complexity was added without benchmark evidence.

## Performance

- [ ] Representative benchmark or complexity analysis is included.
- [ ] Predicate/projection/partition pruning is preserved.
- [ ] No raw-minute × full-parameter cross product was introduced.
- [ ] Memory remains bounded/streamable.
- [ ] File/partition count and compaction impact are understood.

## Security and safety

- [ ] No secrets, authorization headers, or private payloads are exposed.
- [ ] Least privilege and fail-closed behavior remain.
- [ ] Mutating API calls have uncertain-result reconciliation.
- [ ] Emergency/pause/revocation behavior remains durable.
- [ ] Dependency/provenance changes are recorded.

## Evidence and operations

- [ ] Tests include boundary, malformed, corruption, and failure cases.
- [ ] Manifests, hashes, lineage, and receipts are validated.
- [ ] Logs/metrics/audit changes are documented.
- [ ] Runbook, migration, recovery, and rollback are sufficient.
- [ ] Documentation and changelog are updated.
