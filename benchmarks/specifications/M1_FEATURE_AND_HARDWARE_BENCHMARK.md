# M1 feature and workstation benchmark specification

## Purpose

Measure a lookahead-safe Polars rolling-feature workload with a 1,440-minute lookback halo while
keeping peak memory bounded by one shard. Record the workstation separately so a laptop run cannot
be mistaken for reference-hardware evidence.

The spike computes rolling mid/high/low, ATR, volume mean, range width/position, boundary touches,
and mid crossings. It is benchmark code, not the Phase 3 production feature contract.

## Commands

All-universe scaled run used for the checked-in evidence:

```powershell
python benchmarks/feature_benchmark.py `
  --profile scaled --rows 10000000 --instruments 700 `
  --core-minutes 2880 --window-minutes 1440 `
  --output benchmarks/results/m1-feature-scaled.json --force
```

Reference candidate (minimum scale):

```powershell
python benchmarks/workstation_snapshot.py `
  --output D:\grid-reference\reference-host.json --force

python benchmarks/feature_benchmark.py `
  --profile reference --rows 100000000 --instruments 700 `
  --core-minutes 2880 --window-minutes 1440 `
  --reference-host-evidence D:\grid-reference\reference-host.json `
  --output D:\grid-reference\m1-feature-reference.json --force
```

The command above preserves the immutable legacy v2 path. The ADR-0019 successor consumes the
fresh measured-host qualification instead:

```powershell
python benchmarks/feature_benchmark.py `
  --profile reference --rows 100000000 --instruments 700 `
  --core-minutes 2880 --window-minutes 1440 `
  --reference-host-qualification `
    benchmarks/results/m1-owner-measured-host-qualification-20260812.json `
  --output D:\grid-reference\m1-feature-qualified-reference.json --force
```

Because 100,000,000 is not divisible by 700, the recorded core row count is 99,999,900. The
profile threshold applies to the requested scale; the exact normalized count is always retained in
the artifact. The reference command requires a receipt-verified snapshot from the current host
that reports at least 16 physical cores, 64 GiB RAM, and a measured NVMe volume of at least 2 TiB.
This sentence defines the immutable legacy v1/v2 contract only. Owner-accepted ADR-0019 replaces
those fixed thresholds for a future append-only contract with same-host 99,999,900-row evidence,
the 70% memory gate, suitable local SSD/NVMe identity, and evidence-derived current free space.
It verifies the host before and after the workload and freezes Polars, psutil, and Python versions.
A memory-passing v2 run is `reference-host-feature-candidate`; owner/PM acceptance is still required.
The append-only v3 command requires exactly one legacy or qualified-host admission, requires the
qualification to be no more than 24 hours old, binds the output volume, rechecks current identity
and required free space before and after the workload, and publishes
`qualified-host-feature-candidate` only when the unchanged 70% memory gate passes.

The checked-in `m1-feature-reference-candidate.json` is an immutable v1 artifact produced before
reference-host admission existed. It remains useful 100-million-row local scale evidence, but its
`reference-scale-candidate` status is not reference-hardware evidence and cannot close Gate 1.

Workstation snapshot:

```powershell
python benchmarks/workstation_snapshot.py `
  --output benchmarks/results/m1-workstation-snapshot.json --force
```

Deterministic provisional capacity projection from the verified reports:

```powershell
python benchmarks/capacity_projection.py `
  --output benchmarks/results/m1-capacity-projection.json --force
```

That command reproduces the immutable legacy v1 provisional projection from the checked-in local
feature evidence. It does not consume or downgrade a host-bound v2 feature artifact. A later
append-only Gate 1 aggregation contract binds the reference layout, feature, workstation,
ADR-0010 decision, and real-market artifacts without changing v1-v3 semantics; see
[M1_GATE1_REVIEW_PACK.md](M1_GATE1_REVIEW_PACK.md).

## Correctness and resource interpretation

- A shard reads no row after its core end and reads exactly 1,440 prior minutes when available.
- Tests compare a halo shard with an unsharded calculation and prove that modifying future rows
  cannot change past features.
- Every core row is counted exactly once; halo rows are read-only and excluded from output counts.
- Peak RSS is sampled every 10 ms and compared with the configured 70% RAM limit.
- `smoke-only`, `scaled-only`, legacy `reference-scale-candidate`, v2
  `reference-host-feature-candidate`, and v3 `qualified-host-feature-candidate` are evidence
  inputs, not a Gate 1 or P-005 owner decision.
- A v2 run that exceeds its configured memory limit is preserved as
  `reference-feature-rejected-memory` and exits non-successfully.
- A v3 run that exceeds the limit is preserved as `qualified-feature-rejected-memory` and exits
  non-successfully.
- Synthetic results do not justify production compression, skew, or hardware-purchase claims.
- The capacity projection verifies all three source receipts and retains their artifact hashes.
  It reports both the measured synthetic extrapolation and the documented 24/40/64-byte planning
  envelopes rather than substituting one for the other.
- Every JSON artifact is schema-validated and committed only by its verified SHA-256 receipt.
