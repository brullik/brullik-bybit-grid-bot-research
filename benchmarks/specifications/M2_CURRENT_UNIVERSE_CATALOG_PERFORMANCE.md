# M2 current-universe catalog performance specification

Run this benchmark only after the ADR-0091 implementation commit is merged and the ADR-0085
bundle artifact/receipt pair is complete:

```powershell
.venv\Scripts\python.exe -m benchmarks.current_universe_catalog_performance `
  --implementation-identity git:<merged-implementation-sha> `
  --repo-root . `
  --bundle-root reports\private\m2-current-universe-catalog-selection-bundle-<date> `
  --bundle-evidence data\evidence\m2-current-universe-catalog-selection-bundle-<date>.json `
  --store-root data\market-store `
  --catalog data\market-store\catalog\canonical.duckdb `
  --output benchmarks\results\m2-current-universe-catalog-performance-<date>.json
```

The output target must be absent. Preflight occurs before retained-store access. The benchmark
verifies every private plan/manifest/selection receipt and schema, binds them to the sanitized
bundle evidence, and executes the unchanged production batch selector twice. Each pass verifies
one catalog snapshot; the second is an immediate repeat after an uncontrolled-cache first pass.

Success requires exact selection fingerprints and counts, deterministic repeat equality, a final
catalog verification, and unchanged catalog plus selected-dataset metadata fingerprints. Only the
sanitized artifact and receipt enter Git. Private bundle files, catalog, datasets, identities,
time bounds, object keys, paths, and market values remain outside Git.

This measurement does not define an acceptance threshold or qualify the owner-reviewed Gate 2
end-to-end performance envelope. Review it together with the current-universe candle/funding
packs and the unchanged PM checklist.
