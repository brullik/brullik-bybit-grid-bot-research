# ADR-0025: GitHub Truth with Sanitized Runtime Evidence

- Status: accepted
- Date: 2026-08-12
- Owner direction: GitHub is the project source of truth

## Context

Phase 2 produces large local market rows, Parquet datasets, Landing pages, host observations, and
receipts. The public repository must remain the authoritative record of implementation, decisions,
contracts, and results, while the project charter forbids committing market datasets, local paths,
device identifiers, account data, and secrets. Merely describing a successful local run in chat
would leave GitHub incomplete; committing the runtime lake would violate the security and
repository boundaries.

## Decision

GitHub is the source of truth for source code, ADRs, versioned schemas, runbooks, status reports,
small sanitized evidence summaries, their receipts, CI results, and accepted decisions. Every
material implementation or measured result is represented by a reviewed PR.

Large or sensitive runtime artifacts remain outside Git. A GitHub evidence summary instead binds
them by canonical SHA-256 and records only the minimum reproducibility facts needed to detect
substitution: source/coverage/registry/capacity hashes, dataset and manifest identities, requested
ranges, counts, layout, immutable software commit, source policy, limitations, and receipt status.
It contains no OHLC, volume, turnover, account data, local paths, host/device identity, or
credentials.

Freeze `grid.phase2-public-1m-pilot/v1` for bounded public pilot summaries. Its builder must:

- re-verify the complete Landing job and immutable canonical dataset;
- reproduce the exact publication preflight and require `existing_commit=true`;
- prove every requested series has its exact start, end, row count, and consecutive 1m interval;
- bind the canonical manifest and all upstream evidence hashes;
- publish canonical JSON and a SHA-256 receipt last; and
- refuse to overwrite an existing artifact or receipt; and
- state that bounded requested coverage is not historical lifecycle/gap acceptance or Gate 2.

Runtime artifacts may be backed up separately under a future retention policy, but a local file or
conversation is never the authoritative project decision or implementation record.

## Consequences

- A clone of GitHub explains what ran, under which immutable code, and which external runtime
  receipts/hashes must verify, without containing the market lake.
- Replacing a local Landing page, registry, capacity artifact, canonical manifest, or Parquet file
  changes a committed binding or fails verification.
- GitHub cannot reconstruct candle values from hashes alone; runtime data availability and backup
  remain a separate operational concern to be designed before full-history production.
- CI can validate the public evidence schema, embedded content hash, and receipt independently.
- Chat updates are informative only; merged GitHub state is authoritative.

## Rejected alternatives

- Commit Parquet or raw JSON pages: violates repository policy and makes the public source tree a
  market-data distribution channel.
- Keep results only locally or in chat: decisions and measured progress cannot be reviewed,
  reproduced, or recovered from GitHub.
- Publish counts without hashes: a different dataset could claim the same counts.
- Publish host paths or device identity: unnecessary for result verification and leaks local
  environment details.
