# ADR-0013: Shared Reference-Host Admission for Feature Evidence

- Status: proposed; Gate 1 benchmark-gated
- Date: 2026-08-12

## Context

The original `grid.feature-benchmark/v1` contract classified a run as
`reference-scale-candidate` from requested row count, instrument count, and lookback only. The
checked-in 100-million-row artifact therefore records useful scale and bounded-memory evidence
from a below-profile laptop, but its status cannot prove execution on the documented reference
workstation.

ADR-0011 subsequently introduced strict workstation admission for the staged layout benchmark.
Keeping separate admission implementations for layout and feature evidence would allow their host
identity and volume rules to drift. The workstation snapshot also used a filesystem anchor as the
measured volume; on Linux that can collapse a nested NVMe mount to `/` even when the output is on a
different mounted device.

Adding mandatory host provenance changes the meaning of new reference feature evidence. Existing
v1 artifacts and receipts must remain immutable and retain their scale-only interpretation.

## Decision

Use one shared fail-closed reference-host admission function for Gate 1 layout and feature
benchmarks. Admission requires a receipt-verified `grid.workstation-snapshot/v1` artifact and:

- status and assessment that report the documented full research profile;
- at least 16 observed physical cores, 64 GiB RAM, and a measured NVMe volume of at least 2 TiB;
- exact agreement between snapshot and current logical/physical CPU counts, CPU model, machine,
  platform, RAM, storage kind/model, and measured-volume size;
- matching Python and psutil versions between the snapshot and the current process; and
- a timezone-aware observation timestamp that is not in the future.

Layout preparation additionally requires its work directory to resolve to the measured volume.
Feature execution re-runs the complete admission after the timed workload and rejects publication
if the admitted host summary or Polars/psutil/Python versions changed during the run.

Introduce append-only `grid.feature-benchmark/v2` for reference-profile runs. It requires the
admitted workstation summary, exactly 700 instruments, at least 99,999,900 normalized rows, a
1,440-minute window, a configured memory threshold no greater than 70%, and the existing
bounded-memory/correctness evidence. A passing memory gate is classified
`reference-host-feature-candidate`; a completed run that exceeds its configured memory limit is
published as `reference-feature-rejected-memory` and returns a non-success process status. Neither
status approves P-005 or Gate 1.

Smoke and scaled runs continue to use `grid.feature-benchmark/v1`. Supplying reference-host
evidence to a non-reference profile is rejected so it cannot imply stronger semantics.

Workstation snapshots resolve the actual volume containing their output. Windows continues to use
the drive root and physical device number. Linux selects the longest matching mounted path before
resolving the block device and NVMe identity.

## Consequences

- Selecting `--profile reference` is no longer sufficient to create candidate reference feature
  evidence.
- The current below-profile workstation fails before the feature workload or evidence publication.
- Layout and feature benchmarks apply one host-identity policy.
- A Linux snapshot measures a nested research mount rather than silently measuring `/`.
- The checked-in v1 100-million-row artifact remains valid as local scale evidence but cannot be
  promoted or relabelled as v2 reference-host evidence.
- A qualifying external host and owner/PM decision are still required to close Gate 1.

## Rejected alternatives

- Change the meaning of `grid.feature-benchmark/v1`: existing receipt-verified artifacts would
  acquire stronger semantics without new evidence.
- Trust the profile name or CLI row count: neither proves hardware identity or capacity.
- Copy ADR-0011 admission logic into the feature harness: independent safety checks would drift.
- Accept a snapshot without rechecking the current host: an artifact from another machine could be
  attached to the run.
- Suppress a failed memory result: negative Gate 1 evidence must remain auditable.
