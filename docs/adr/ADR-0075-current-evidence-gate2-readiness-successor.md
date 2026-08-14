# ADR-0075: Current-evidence Gate 2 readiness successor

- Status: accepted
- Date: 2026-08-14
- Supersedes for current review: ADR-0063 readiness classification
- Preserves: immutable v1 evidence, unchanged Gate 2 criteria, and data-quality-owner authority

## Context

The immutable `grid.gate2-readiness-pack/v1` correctly recorded the evidence available when it was
published. It now contains two obsolete blockers: the five-instrument candle campaign is complete,
and its 978 canonical datasets plus aggregate coverage audit are published in GitHub. Re-running
Bybit acquisition or the retained-store audits would waste time and could produce a different
dated observation instead of reviewing the already committed evidence.

New receipt-bound artifacts also quantify the full-history candle boundary topology, the limited
depth of the official announcements API, canonical corruption detection, and incremental catalog
selection. They do not resolve the historical lifecycle, funding cadence, genuine repair, or
end-to-end performance-review requirements. The accepted v1 schema cannot be reinterpreted or
modified in place.

## Decision

Add `grid.gate2-readiness-pack/v2` and
`python -m benchmarks.gate2_readiness_pack_v2` as a no-network successor. It verifies twelve exact
GitHub artifacts by completion receipt, JSON Schema, artifact SHA-256, embedded content SHA-256,
contract, status, and cross-source lineage. It reuses the unchanged roadmap hash and ordered six
Gate 2 criteria from v1.

The source set includes completed full-history Landing, canonical publication, coverage and
boundary evidence; controlled funding coverage; current instrument timeline and official
announcement depth; full-history preflight and incremental catalog performance; stale-output and
canonical-integrity fault injection; and immutable compaction evidence. Cross-checks bind the
campaign, publication, registry, coverage, boundary, and announcement scopes before projection.

The classification changes only where committed evidence makes the old statement false:

- preflight-before-mutation, duplicate/conflicting-key freedom, and stale-output detection are
  `evidence-ready`;
- deterministic repair remains blocked until genuine candle and funding repair executions exist;
- lifecycle coverage remains blocked by unresolved funding cadence, incomplete historical
  point-in-time metadata, insufficient official announcement depth, and unaccepted candle absence
  reasons; and
- performance remains blocked because the measured component and campaign timings have not been
  qualified against an owner-reviewed full-history end-to-end envelope.

`evidence-ready` remains evidence for review, not acceptance. The builder always records Gate 2 as
`closed-pending-data-quality-owner`, requires the owner decision, disables automatic Phase 3
authorization, publishes negative evidence before returning exit code 2, and performs no network
or market-store access.

## Consequences

- Current readiness can be rebuilt from GitHub in one offline pass without repeating history
  downloads or retained-store scans.
- The completed campaign and canonical publication are no longer reported as missing.
- Seven current evidence/policy blockers remain explicit, so the successor cannot weaken Gate 2.
- ADR-0063, its v1 schema, builder, artifact, and receipt remain immutable historical evidence.
- Any later blocker removal requires another reviewed source set or owner decision; source
  substitution and resealing fail closed.

## Rejected alternatives

- Edit or overwrite the v1 artifact: this would invalidate its receipt and historical meaning.
- Re-run every source command before aggregation: receipt and hash verification already proves the
  committed inputs, while a rerun would add cost and temporal drift.
- Mark performance ready from elapsed times alone: no reviewed end-to-end acceptance envelope is
  bound to those measurements.
- Infer lifecycle from first returned candles or archive depth: both are explicitly non-accepting
  diagnostics.
