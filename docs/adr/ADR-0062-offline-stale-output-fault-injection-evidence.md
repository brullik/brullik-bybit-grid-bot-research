# ADR-0062: Offline stale-output fault-injection evidence

- Status: accepted
- Date: 2026-08-14
- Implements: Gate 2 stale building-output detection evidence
- Preserves: unchanged Gate 2 acceptance ownership

## Context

Canonical candle/funding publication, candle compaction, and DuckDB catalog registration already
fail closed when their deterministic building path or catalog lock exists. Unit tests cover those
branches, but Gate 2 explicitly requires stale building outputs to be detected. A reviewable
post-merge runtime artifact must therefore exercise the real production preflight functions rather
than infer this criterion from source code or a green test count alone.

The measurement must not touch the retained market store, require network/private credentials, or
publish synthetic market values and temporary paths.

## Decision

Add `python -m benchmarks.stale_output_fault_injection` as a fully offline, temporary-directory
fault-injection runner. It constructs the minimum exact canonical fixtures required to reach five
production boundaries:

1. candle publication building directory;
2. funding publication building directory;
3. candle compaction building directory;
4. catalog registration building file; and
5. catalog registration write lock.

Each case obtains or derives the deterministic production target, writes one known marker to the
stale location, invokes the real preflight function, and requires the exact fail-closed
`PublicationError` or `CatalogError` classification. It then proves that the marker bytes remain
unchanged and that the target dataset/catalog does not exist. Any missing classification, changed
marker, or target mutation aborts before evidence publication.

The temporary fixture is removed after all cases. No acquired/public market data, Bybit client,
private endpoint, credential, account, order, bot, transfer, or live component is involved.

Freeze `grid.phase2-stale-output-fault-injection/v1` as the GitHub-safe proof. It binds the merged
implementation Git identity, five named boundary/case classifications, detection/preservation/
mutation counts, and explicit no-network/no-live assurances. It contains no synthetic market
values, runtime paths, device/host identity, account data, or credentials. A canonical content
hash and ordinary evidence receipt bind the artifact.

The result is decision evidence for one unchanged Gate 2 criterion only. It does not accept Gate
2, prove full-history coverage, exercise acquisition run locks, authorize cleanup, or grant live
permission.

## Consequences

- The data-quality owner can inspect one deterministic post-merge artifact rather than relying on
  implementation intent.
- Stale evidence is preserved for operator diagnosis; the runner proves no automatic cleanup.
- The retained local market store remains untouched because all injected artifacts live under an
  automatically removed temporary root.
- New canonical write boundaries will require an explicit successor case/contract rather than
  being silently covered by this v1 evidence.

## Rejected alternatives

- Treat unit tests as the only runtime evidence: they do not provide a schema-bound post-merge
  artifact.
- Inject stale files into the retained market store: unnecessary operational risk.
- Delete stale output automatically: it could destroy recovery evidence or another writer's lock.
- Report only a total passed count: named production boundaries are needed to prevent accidental
  scope shrinkage.
