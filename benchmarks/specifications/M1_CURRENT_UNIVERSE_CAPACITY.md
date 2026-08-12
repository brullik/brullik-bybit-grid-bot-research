# M1 current-universe bootstrap and incremental capacity specification

## Purpose

Project a fresh, receipt-pinned Bybit lifecycle estimate onto the existing M1 synthetic and
bounded-real-market storage measurements. The report separates the one-time bootstrap from normal
incremental updates and measures disk headroom on the exact output volume.

It is not a downloader, raw-archive size inventory, Gate 1 acceptance, or Phase 2 permission.

## Command

```powershell
python -m benchmarks.current_universe_capacity `
  --history-source benchmarks/results/m1-owner-storage-review-history-20260812.json `
  --capacity benchmarks/results/m1-real-market-capacity-projection.json `
  --workstation benchmarks/results/m1-owner-storage-review-workstation-20260812.json `
  --output benchmarks/results/m1-owner-storage-review-capacity-20260812.json
```

The default maximum source age is 24 hours and may be configured from 1 through 168 hours. Source
receipt/schema/hash verification, freshness, transitive layout binding, exact projection math, and
output-schema validation all occur before output replacement. The CLI also resolves the actual
output volume and rejects a workstation snapshot captured from a different volume.

## Projection semantics

- The lifecycle estimate uses the mark-price per-symbol minute count from the current instrument
  snapshot and applies equal coverage to trade and mark for a like-row-count comparison.
- Bootstrap is one canonical `building` version because no prior canonical version exists.
- Full rebuild is two canonical equivalents: accepted `active` plus its replacement `building`.
- Incremental daily rows include only instruments whose current status is `Trading`.
- The maintenance bound is one 31-day calendar partition; unchanged immutable partitions are not
  rewritten.
- Every measured layout is reported separately. Disk preflight uses the larger real-width result.
- The independent 64-byte planning row width remains visible as a conservative rebuild scenario.

## 2026-08-12 owner storage review

The immutable public evidence chain is:

1. `m1-owner-storage-review-inventory-20260812.json`;
2. `m1-owner-storage-review-history-20260812.json`;
3. `m1-owner-storage-review-workstation-20260812.json`;
4. `m1-real-market-capacity-projection.json`;
5. `m1-owner-storage-review-capacity-20260812.json`.

It observed 1,010 USDT linear perpetual records, including 702 `Trading`, and estimated
1,770,106,722 equal-coverage trade+mark lifecycle rows, or `24.039621018%` of the formal capacity
envelope. On the measured volume with 193,679,237,120 free bytes:

| Scenario | Required bytes | Approximate GiB | Fits observed free |
|---|---:|---:|:---:|
| Bootstrap canonical building | 44,997,807,469 | 41.907 | yes |
| Full rebuild active + building | 89,995,614,938 | 83.815 | yes |
| Incremental one day | 51,395,075 | 0.048 | yes |
| Incremental maximum 31-day partition | 1,593,247,317 | 1.484 | yes |
| 64-byte planning rebuild | 226,573,660,416 | 211.013 | no |

## Interpretation limits

- Lifecycle minutes are not downloaded, gap-audited history.
- The inventory is partial because Bybit rejected the documented `Settling` filter.
- Current metadata is not a dated historical universe registry.
- The real-market calibration contains eight current-liquid symbols over seven days.
- Applying the trade row width to mark rows is conservative because mark rows omit volume and
  turnover.
- Raw tick-trade archives, partial HTTP files, retry staging, filesystem overhead, derived stores,
  experiments, and backup are excluded.
- A full download is unsafe to authorize until the downloader measures raw source bytes and passes
  its own free-space preflight.
