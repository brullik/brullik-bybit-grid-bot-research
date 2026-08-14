# M2 current-universe candle evidence specification

Run this offline builder only after every source has receipt-bound Landing, canonical publication,
and aggregate coverage evidence and the corresponding ADR-0085 catalog selection bundle is
complete:

```powershell
.venv\Scripts\python.exe -m benchmarks.current_universe_candle_evidence `
  --landing-evidence <source-1-landing.json> `
  --publication-evidence <source-1-publication.json> `
  --coverage-evidence <source-1-coverage.json> `
  --landing-evidence <source-2-landing.json> `
  --publication-evidence <source-2-publication.json> `
  --coverage-evidence <source-2-coverage.json> `
  --catalog-bundle-evidence <catalog-bundle-evidence.json> `
  --software-identity git:<merged-builder-sha> `
  --output benchmarks\results\m2-current-universe-candle-evidence-<date>.json
```

Repeat each triplet once per catalog-bundle source and preserve the exact source order. The command
must fail before output if receipts, schemas, content hashes, triplet bindings, source order,
trade/mark inventory, coverage counts, or catalog counts differ. A successful result writes the
evidence JSON followed by its receipt and returns zero even when the verified source coverage
remains blocked: `status` describes evidence integrity, while `quality.coverage_status` preserves
the unchanged audit result.

The builder reads no Landing page, Parquet file, DuckDB catalog, runtime path, or network endpoint.
It may report only hashes, aggregate counts, quality reasons, operation timing, and the explicit
funding inventory excluded from the candle-only bundle. It must keep
`performance.envelope.qualified=false`, require owner review, leave Gate 2 unchanged, and keep
Phase 3 unauthorized.
