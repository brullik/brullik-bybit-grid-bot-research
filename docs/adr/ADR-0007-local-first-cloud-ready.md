# ADR-0007: Local-First, Cloud-Ready Architecture

- Status: accepted
- Date: 2026-07-28

## Context

The project begins on a local workstation and may later move live to a VPS/dedicated host and data to object storage. Starting with distributed infrastructure would add cost and operational complexity without measured need.

## Decision

Build first for:

- local NVMe and filesystem/object abstractions;
- single-node Polars/DuckDB batch processing with deterministic sharding;
- SQLite or equivalent small transactional live state initially;
- independently packaged applications;
- portable manifests/contracts that can later address S3-compatible storage and PostgreSQL without changing domain semantics.

Distributed orchestration, Kubernetes, Spark, and a network database are deferred until a measured requirement exists.

## Consequences

- fast and understandable initial delivery;
- lower operational burden;
- architecture remains migratable through explicit storage/state interfaces;
- full-scale build duration may be longer than a cluster;
- benchmark determines whether vertical scaling is sufficient.

## Rejected alternatives

- Cloud/distributed first: premature cost and complexity.
- Local-only assumptions embedded in contracts: blocks later safe migration.
