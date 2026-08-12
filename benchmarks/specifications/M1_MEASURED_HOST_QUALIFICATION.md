# M1 measured reference-host qualification

## Purpose

Implement the first append-only ADR-0019 contract without changing any legacy workstation,
layout, feature, review-pack, or campaign-plan receipt. The qualification answers only whether the
current host has demonstrated the full-scale trial and current storage headroom required to begin
the successor reference campaign.

It does not run a benchmark, download history, call Bybit, accept Gate 1, or authorize Phase 2.

## Verified inputs

- `grid.layout-benchmark/v3` with status `decision-matrix-candidate`, at least 99,999,900 rows,
  exactly 700 instruments, the complete two-layout shortlist, exact numeric schema verification,
  exercised file targets, peak RSS, and measured scratch;
- `grid.feature-benchmark/v1` with status `reference-scale-candidate`, the same row/instrument
  scale and hardware, correct halo/no-future semantics, a passing configured memory limit no
  greater than 70%, and measured peak RSS;
- `grid.current-universe-capacity/v1` with the current active-plus-building scenario; and
- the exact `grid.workstation-snapshot/v1` artifact transitively bound by that capacity evidence.

Every source requires its completion receipt and full JSON Schema validation. Layout and feature
basic hardware must match the workstation exactly. Capacity must bind the exact workstation hash
and measured volume, and must be no more than 24 hours old at qualification time.

## Current-host preflight

Before output preflight, the command rechecks current CPU/RAM/platform identity, CPU model,
storage kind/model, volume total, and output-volume placement. Only local `nvme` or `ssd` is
eligible. It reads current free bytes rather than trusting the older workstation observation.

Required free bytes are:

```text
current-universe active-plus-building
+ sum(measured scratch for both shortlisted reference layouts)
+ 8 GiB operating reserve
```

Insufficient free space is an auditable negative result with exit code 2. Invalid, tampered,
cross-host, cross-volume, or incomplete source evidence fails before output replacement.

## Command

Run on the measured volume without Bybit credentials:

```powershell
python -m benchmarks.measured_host_qualification `
  --output benchmarks/results/m1-owner-measured-host-qualification-20260812.json
```

The checked-in run reported `qualified-measured-reference-host`: 100,228,313,013 required bytes,
192,452,521,984 current free bytes, and 92,224,208,971 bytes of headroom. Gate 1 remains
`pending-owner-decision`.

## Remaining boundary

Qualification does not prove the pinned Python 3.12 environment or reboot-separated cold-cache
measurements. A later append-only implementation must consume this artifact in successor layout,
feature, review-pack, and campaign-plan contracts before the reference campaign can start.
