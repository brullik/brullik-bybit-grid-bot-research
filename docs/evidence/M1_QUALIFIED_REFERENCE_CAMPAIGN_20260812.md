# M1 qualified reference campaign — 2026-08-12

## Outcome and governance boundary

The qualified ADR-0019 campaign completed all eight planned steps on the owner laptop. The
receipt-verified `grid.gate1-review-pack/v2` result is `ready-for-owner-review`, both paired layout
candidates satisfy every provisional performance gate, and the blocker list is empty.

This evidence does **not** choose P-001 through P-005, accept Gate 1, authorize Phase 2, or grant
any live-trading permission. The final review pack retains
`gate_1.status=pending-owner-decision`, `automatic_promotion=false`, and
`owner_decision_required=true`.

## Reproducibility and immutable recovery

- The original layout campaign was prepared and finalized from clean `main` at
  `dd1d961f1ecfa3b14a8c8f696aac6ef09dcd4ba0` after four distinct reboots.
- The completed layout exposed a validator/producer mismatch fixed by PR #12. The layout producer,
  workload, schemas, thresholds, and Gate 1 policy were unchanged.
- A recovery plan at `0de8d5a1875480eb83ad2c803d8b5a7d14aaaba2` adopted the layout byte for byte and produced the
  qualified feature result. The review builder then exposed a second optional-field mismatch fixed
  by PR #13; again, no workload, schema, threshold, or governance rule changed.
- The final recovery plan pinned clean `main` at
  `a79d51093edbf6cb38cd68ab36f0b9e3b6c652fc`, adopted 100 layout/feature files totaling
  1,295,602,200 bytes with zero SHA-256 differences, and published the review pack.
- The original and both recovery roots remain preserved outside Git. Generated Parquet data,
  private paths, and runtime artifacts are not committed.

Public correlation hashes for the preserved external evidence are:

| Artifact | SHA-256 | Receipt-file SHA-256 |
|---|---|---|
| final campaign plan | `fdc380c845f3c05369a5af58f6d5bd1f06610ef454fb608ed0602329cf019e50` | `e62af8e68d1d0d0285f9388dcb8a0bf454de7c43e4147acec1b1d9e20c867730` |
| reference layout | `7746476097188e2df72b4cb121cfcc3a443a5e91b4e84f85aea6920b9d516a7f` | `e88e0081bf0250b606b174a06997990c2f2fd01c711f05dba2ecbcad299e3795` |
| reference feature | `591fd02ae31c7dd7b64e83dacbbbd80e03194f22d25af43f3bfc267d812e3861` | `a7503ff63b25f97b630fdf67294c2c6fea1cc743c907b67c9f4046b51d3d2eed` |
| Gate 1 review pack | `06203c7cb278c0e1194e67fb76344ea88288bdc968b139319437fecab8b6a213` | `57b76371a5b6adbbb74d4af6bab02fd34627e33722d0fe5d62f940dbff22b182` |

The final plan recorded Python 3.12.10, 258 source-manifest files, and source-manifest SHA-256
`6e66675b60a52c3985deb0a6b10f86d34752e792df51602f2099d1ef1eea03a3`.

## Measured layout results

The reference input contained 99,999,900 deterministic exact rows across 700 instruments. Each
engine/query first read followed a distinct reboot; metadata was verified before timing, content
after timing, and DuckDB/Polars result hashes agreed.

| Metric | 4 buckets / 32 MiB | 8 buckets / 16 MiB |
|---|---:|---:|
| Parquet bytes | 644,547,167 | 650,964,604 |
| write seconds | 47.648869000 | 49.126355900 |
| DuckDB single-symbol first seconds | 0.068181200 | 0.055006900 |
| Polars single-symbol first seconds | 0.095830100 | 0.018735500 |
| DuckDB universe-month first seconds | 0.258981400 | 0.247888000 |
| Polars universe-month first seconds | 0.291120900 | 0.201615100 |
| repair seconds | 3.800990000 | 1.864168400 |
| compaction seconds | 3.724919900 | 1.886843400 |
| projected worst 10-year single-symbol cold seconds | 3.528127038 | 2.025160479 |
| projected real trade-history bytes | 92,159,402,914 | 93,590,925,238 |
| all provisional layout gates | pass | pass |

Both candidates preserved exact logical parity and left their source trees unchanged. The 8/16
candidate trades about 1.0% more projected storage and 1.48 seconds more write time for generally
faster cold queries and roughly half the repair/compaction time. That comparison is evidence for,
not a substitute for, the owner decision.

## Measured feature and capacity results

- 99,999,900 output rows in 30.468537400 seconds;
- 3,282,070.901112563 core rows/second;
- 1,509,040,128 bytes peak RSS, 9.158894582% of observed RAM;
- 70% memory gate passed;
- projected trade-only feature time 1,121.744322693 seconds;
- projected trade-plus-mark feature time 2,243.488645387 seconds;
- current admission requirement 100,228,313,013 bytes against the receipt-bound
  192,452,521,984-byte free-space observation.

The projections exclude Phase 2 implementation overhead that does not yet exist, including its
independently bounded REST-page staging. Phase 2 must retain a fresh preflight and measured bounds.

## Owner decision surface

The review pack presents these values without accepting them:

- P-001: `hybrid_int64_decimal`;
- P-002/P-003: paired candidates `4 buckets / 32 MiB` and `8 buckets / 16 MiB`;
- P-004: `zstd-3`;
- P-005: the measured 6-physical-core, 16,476,225,536-byte-RAM laptop with local NVMe and the
  evidence-derived 100,228,313,013-byte free-space requirement.

An explicit owner/PM record remains the only item required before Gate 1 can change state.
