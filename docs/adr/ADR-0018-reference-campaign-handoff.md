# ADR-0018: Fail-Closed Reference Campaign Handoff

- Status: proposed; Gate 1 owner-review-gated
- Date: 2026-08-12

## Context

The remaining Gate 1 measurements require a qualifying external workstation, one retained
100-million-row layout preparation, four reboot-separated first-read legs, a host-bound feature
run, finalization, and an independent review pack. Each underlying command already fails closed,
but manually reconstructing paths, fixed scales, dependencies, and reboot order creates avoidable
operator error and weakens handoff auditability.

The current workstation cannot run the reference campaign: its receipt-verified snapshot reports
6 physical cores, 16.48 GB RAM, and a 511 GB NVMe volume, below the required 16 cores, 64 GiB, and
2 TiB NVMe profile. Orchestration must not disguise that external dependency or approve Gate 1.

## Decision

Add the append-only `grid.reference-campaign-plan/v1` contract and a two-command campaign helper:

- `plan` admits the current host and measured campaign volume, validates receipt/schema-pinned
  decision, real-market, workstation, and repository source-manifest inputs, and requires the
  read-only reference-environment doctor to prove Python 3.12, the reviewed exact direct
  dependency constraints, every editable monorepo package, a clean canonical `main` checkout,
  consistent dependencies, required imports, and absence of Bybit credential variables before
  it rejects reserved output collisions and publishes an immutable eight-step plan;
- the plan fixes the 100,000,000 requested rows, 700 instruments, two ADR-0010 layouts, four
  engine/query measurement legs, feature reference run, and Gate 1 review-pack command;
- command `argv` arrays are authoritative; display strings are informational;
- no generated command contains `--force`, and the campaign root must be a dedicated directory
  outside the repository on the workstation snapshot's measured volume;
- `status` is read-only, accepts only receipt-marked artifacts in plan order, verifies pinned
  sources and the current host again, cross-binds the final layout, feature, and review artifacts
  to the campaign preparation, scale, host, and exact source hashes, detects invalid/out-of-order
  evidence, and identifies the next command or required reboot;
- every measurement must bind the current preparation and have a distinct boot marker; and
- even a complete ready review pack reports Gate 1 as `pending-owner-decision` with automatic
  acceptance disabled.

The helper executes no benchmark, reboot, promotion, download, or owner decision. Operators run
the returned command explicitly and call `status` again afterward.

## Consequences

- External-host handoff becomes deterministic and machine-readable.
- A clean-machine install cannot begin the expensive campaign with missing monorepo packages,
  dependency drift, a feature branch, stale `origin/main`, or private exchange credentials.
- A below-profile or mismatched host fails before campaign-root creation or benchmark mutation.
- Reboots remain manual and explicit; the helper never attempts to restart the machine.
- Existing benchmark and review evidence contracts remain authoritative; the campaign plan does
  not weaken their validation.
- Changing repository source files, pinned inputs, host identity, volume identity, or an artifact
  receipt blocks continuation rather than silently regenerating a plan.
- A new campaign or deliberate repair uses a new dedicated root; the helper never deletes or
  overwrites an existing campaign.

## Rejected alternatives

- One script automatically executes every stage and reboots the host: this obscures cache
  boundaries, failure review, and operator control.
- Let status trust file presence: incomplete or tampered outputs could appear complete.
- Generate a plan on the current below-profile workstation for later copying: paths, interpreter,
  volume, runtime, and host identity would not bind the actual execution environment.
- Mark Gate 1 accepted after numeric checks pass: only owner/PM governance can make that decision.
