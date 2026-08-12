# ADR-0003: Immutable Datasets and Explicit Receipts

- Status: accepted
- Date: 2026-07-28

## Context

Long batch jobs will be restarted, repaired, compacted, and reproduced. File presence alone cannot distinguish a complete result from a partial write or crash. In-place mutation makes lineage and audit unreliable.

## Decision

Every dataset/shard uses lifecycle states:

```text
building → complete | failed
```

Only an explicit verified `complete` receipt/manifest commits output. Accepted datasets are immutable. Repairs, migrations, and compaction create new dataset identities and parent lineage. Staging is isolated and atomically published.

## Consequences

- restart reuses only verified complete shards;
- stale `.building`/staging artifacts are detectable;
- audits and backtests can reproduce exact parents;
- storage temporarily needs compaction/build headroom;
- garbage collection requires reachability and retention rules.

## Rejected alternatives

- Append/edit Parquet files in place: weak atomicity and lineage.
- Infer completion from expected filenames: vulnerable to partial/corrupt files.
- Mutable “latest” dataset path as identity: breaks reproducibility.
