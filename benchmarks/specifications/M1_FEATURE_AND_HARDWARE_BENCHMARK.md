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
python benchmarks/feature_benchmark.py `
  --profile reference --rows 100000000 --instruments 700 `
  --core-minutes 2880 --window-minutes 1440 `
  --output benchmarks/results/m1-feature-reference.json --force
```

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

## Correctness and resource interpretation

- A shard reads no row after its core end and reads exactly 1,440 prior minutes when available.
- Tests compare a halo shard with an unsharded calculation and prove that modifying future rows
  cannot change past features.
- Every core row is counted exactly once; halo rows are read-only and excluded from output counts.
- Peak RSS is sampled every 10 ms and compared with the configured 70% RAM limit.
- `smoke-only` and `scaled-only` are feasibility evidence, not a full-scale Gate 1 pass.
- Synthetic results do not justify production compression, skew, or hardware-purchase claims.
- The capacity projection verifies all three source receipts and retains their artifact hashes.
  It reports both the measured synthetic extrapolation and the documented 24/40/64-byte planning
  envelopes rather than substituting one for the other.
- Every JSON artifact is schema-validated and committed only by its verified SHA-256 receipt.
