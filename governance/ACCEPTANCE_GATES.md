# Acceptance Gates

This is the governance summary. Detailed phases are in [Roadmap and Acceptance Gates](../docs/14_ROADMAP_AND_GATES.md).

| Gate | Permission unlocked | Required evidence owner |
|---|---|---|
| G0 Documentation | begin feasibility implementation | owner/PM + architecture |
| G1 Feasibility/benchmark | implement canonical data MVP | PM acceptance + performance review |
| G2 Canonical data | implement feature/candidate platform | data quality owner |
| G3 Features/candidates | implement outcome/backtest | research contract owner |
| G4 Simulator/backtest | run parameter-selection programme | independent simulator review |
| G5 Robust strategy | build strategy release | owner/PM research decision |
| G6 Release registry | build shadow live | release/security review |
| G7 Shadow live | permit minimal manual mainnet | owner + live safety review |
| G8 Manual mainnet | permit controlled concurrency/size increase | explicit owner decision |
| G9 Controlled scale | consider autonomous entry/production hardening | formal governance decision |

## Current gate status

| Gate | Status | Decision record |
|---|---|---|
| G0 Documentation | accepted | architecture baseline |
| G1 Feasibility/benchmark | accepted 2026-08-12 | owner/PM decision and ADR-0020 |
| G2 Canonical data | closed; Phase 2 in progress | requires the unchanged Gate 2 evidence |

Acceptance of G1 opens only the canonical market-data MVP. It grants no live or real-money
mutation permission.

## Gate invariants

- A gate is closed by default.
- Passing one gate does not waive later criteria.
- An implementation PR cannot change the gate it is being evaluated against.
- Evidence must point to immutable commits/artifacts, not screenshots alone.
- “Works on my machine” is not a gate result.
- A failed or incomplete required audit blocks the gate.
- Scope reductions or exceptions require a recorded owner decision and cannot be hidden in implementation.
- Gate 1 host admission follows owner-accepted ADR-0019: nominal CPU/RAM/total-volume values are
  descriptive, while same-host scale, memory, current free-space, and performance evidence are
  mandatory.
- Live permissions are tied to a release ID, environment, mode, and limits—not granted globally.

## Emergency gate closure

Any of the following can re-close a live gate:

- credential/security incident;
- unexplained exchange/local state mismatch;
- release tampering/revocation;
- material live/backtest divergence;
- risk limit breach;
- repeated reconciliation or emergency failure;
- exchange/API behavior change invalidating assumptions;
- owner decision.
