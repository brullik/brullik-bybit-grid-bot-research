# ADR-0001: Separate Deployable Applications

- Status: accepted
- Date: 2026-07-28
- Decision owners: project owner and architecture/PM

## Context

The system must support very large historical ingestion and parameter research while allowing the owner to run only live trading. Batch workloads can consume large CPU, RAM, disk, and I/O; live requires bounded latency, private credentials, and strict safety.

## Decision

Create four independently startable applications:

- `grid-data`;
- `grid-research`;
- `grid-release`;
- `grid-live`.

Use a monorepo for shared governance and contracts, but enforce one-way dependencies. Live cannot import or mount the historical/research stores.

## Consequences

Positive:

- live-only deployment is small and safer;
- batch failure/load cannot directly disrupt live;
- private credentials stay outside data/research;
- components can be benchmarked and released independently;
- research can remain offline while promoted live runs.

Costs:

- explicit contracts and compatibility management are required;
- cross-component integration tests are necessary;
- local developer setup has more than one command/artifact.

## Rejected alternatives

- One all-in-one daemon: couples resource usage, credentials, and failure domains.
- Independent repositories from day one: increases contract/version drift before the team/project warrants it.
