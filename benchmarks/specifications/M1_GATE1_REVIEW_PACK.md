# M1 Gate 1 reference evidence review-pack specification

## Purpose

Build one owner-review artifact only after both host-bound reference benchmarks finish. The pack
independently verifies the complete evidence chain, calculates provisional performance/capacity
checks, and leaves P-001 through P-005 and Gate 1 pending for the owner/PM.

It is not a benchmark runner, acceptance signature, Phase 2 permission, or live-trading permission.

## Required inputs

- finalized `grid.reference-layout-benchmark/v2` artifact and receipt;
- finalized `grid.feature-benchmark/v2` artifact and receipt;
- the exact workstation snapshot and receipt embedded by both artifacts;
- checked-in ADR-0010 decision evidence and receipt; and
- checked-in bounded real-market layout evidence and receipt.

Legacy local `grid.feature-benchmark/v1`, smoke layout, synthetic-only reference layout, or
provisional capacity artifacts are rejected.

## Command

Run after the four reboot-separated layout legs and the host-bound feature run have completed:

```powershell
python -m benchmarks.gate1_review_pack `
  --layout D:\grid-reference\m1-reference-layout.json `
  --feature D:\grid-reference\m1-feature-reference.json `
  --workstation D:\grid-reference\reference-host.json `
  --decision benchmarks\results\m1-layout-exact-decision-candidate.json `
  --real-market benchmarks\results\m1-real-market-layout-skew.json `
  --output D:\grid-reference\m1-gate1-review-pack.json
```

All inputs are verified before the output is preflighted or replaced. `--force` permits replacement
only after the new complete input chain and calculated output validate.

## Result semantics

`ready-for-owner-review` means:

- both v2 artifacts bind the same qualifying workstation snapshot and 100-million-row scale;
- shared runtime versions match;
- all transitive receipts/hashes/content bindings verify;
- at least one exact layout passes the documented provisional cold/warm/write checks; and
- the feature memory gate passes with a configured threshold no greater than 70%.

It does **not** mean accepted, selected, or authorized. The pack always records Gate 1 as
`pending-owner-decision` and `automatic_promotion=false`.

`blocked-by-reference-results` is a completed negative evidence artifact. The CLI returns exit code
2 after publication. Blocker reason codes identify a failed feature memory gate or the absence of
an eligible layout.

## Interpretation limits

- The ten-year single-symbol values are linear projections from 142,857 observed minutes per
  symbol, not direct ten-year scans.
- The universe-month measurement is observed directly over the first 44,640 minutes × 700 symbols.
- Real-market sizing uses the bounded seven-day trade-price sample. Applying its row width to mark
  rows is a conservative like-width comparison, not a measured mark schema.
- Storage excludes raw archives, derived datasets, experiments, compaction headroom, filesystem
  overhead, and backup.
- Only an explicit owner/PM decision may select P-001 through P-005 and close or reject Gate 1.
