# ADR-0063: Receipt-bound non-promoting Gate 2 readiness pack

- Status: accepted
- Date: 2026-08-14
- Implements: reproducible Gate 2 evidence aggregation
- Preserves: unchanged Gate 2 criteria and data-quality-owner authority

## Context

Phase 2 now has many receipt-verified public artifacts spanning controlled acquisition,
publication, coverage, compaction, full-history preflight/resume, instrument timelines, and stale
write-state fault injection. The six Gate 2 criteria remain unchanged, but their current evidence
and blockers are described across a long implementation-status document. A reviewer cannot prove
the current readiness state from one schema-bound artifact, and an implementation agent must not
silently infer Gate 2 acceptance from a collection of green unit tests or selected positive runs.

The aggregation must preserve negative evidence: the five-instrument candle campaign still has 51
jobs and 2,271 pages pending, the 100-instrument funding audit retains seven unexplained cadence
changes, historical point-in-time metadata is incomplete, and no genuine-gap repair run exists.

## Decision

Add `python -m benchmarks.gate2_readiness_pack` as a no-network evidence aggregator. Version 1 is
bound to the exact SHA-256 of `docs/14_ROADMAP_AND_GATES.md`, the exact ordered text of all six
Gate 2 criteria, and eight named public source artifacts. Every source must pass its completion
receipt, versioned JSON Schema, embedded canonical content hash, expected artifact hash, contract,
and status. The builder also rechecks 100-instrument source/publication/audit lineage, scope and row
accounting before projecting any result.

The pack classifies only readiness for evidence review:

- `no mutation before preflight succeeds` and `stale building outputs detected` are
  `evidence-ready` from their bound controlled evidence;
- deterministic repair, full-history key quality, lifecycle-based coverage, and end-to-end
  performance remain `blocked`;
- seven explicit blocker codes record the missing full-history, repair, cadence, lifecycle, and
  end-to-end performance evidence.

`evidence-ready` is not an accepted criterion. The artifact always retains
`data_quality_owner_decision_required=true`, `automatic_phase3_authorization=false`, Gate 2 status
`closed-pending-data-quality-owner`, and process exit code 2 while the blocker set is non-empty.
The v1 schema fixes the source artifacts, criteria assessment, aggregate observations, and blocker
set so a substituted or newly resealed source cannot silently change the review result.

The public projection contains artifact/content hashes, contract/status identities, aggregate
counts, and readiness classifications only. It contains no market values, instrument or dataset
identities, runtime paths, account data, credentials, or private/live capability.

## Consequences

- GitHub gains a deterministic, reviewable statement of exactly what is and is not ready for Gate
  2 review.
- Negative evidence remains first-class and Phase 3 cannot be unlocked by the builder.
- A changed criterion, different evidence source, resolved blocker, or later scale result requires
  an explicit successor contract rather than reinterpretation of this immutable v1 pack.
- The pack does not replace detailed source artifacts or data-quality-owner review.

## Rejected alternatives

- Treat the implementation-status prose as the only checklist: it has no receipt or executable
  binding validation.
- Mark a criterion accepted automatically when selected counters are zero: acceptance belongs to
  the data-quality owner and must consider the required scale.
- Omit blocked source artifacts: doing so would hide known funding cadence and lifecycle gaps.
- Allow arbitrary receipt-valid substitutes: a resealed artifact could change the assessed facts
  without a new review contract.
