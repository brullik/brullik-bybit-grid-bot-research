# M2 full-history catalog performance specification

This command reuses the existing receipt-verified catalog and four topology-scoped private
selection chains. It downloads, publishes, repairs, and registers nothing:

```powershell
.venv\Scripts\python.exe -m benchmarks.full_history_catalog_performance `
  --implementation-identity git:<merged-implementation-sha> `
  --repo-root . `
  --catalog-result benchmarks\results\m2-full-history-catalog-<date>.json `
  --selection-request <trade-segment-1-request.json> `
  --selection-request <trade-segment-2-request.json> `
  --selection-request <mark-segment-1-request.json> `
  --selection-request <mark-segment-2-request.json> `
  --selection-evidence <trade-segment-1-selection.json> `
  --selection-evidence <trade-segment-2-selection.json> `
  --selection-evidence <mark-segment-1-selection.json> `
  --selection-evidence <mark-segment-2-selection.json> `
  --store-root <canonical-market-store> `
  --catalog <canonical-market-store>\catalog\canonical.duckdb `
  --output benchmarks\results\m2-full-history-catalog-performance-<date>.json
```

Run the official measurement only after implementation merge. The four request/evidence pairs may
be supplied in any order; request hashes map them to the exact public bindings, and the benchmark
requires both topology segments for trade and mark. Output preflight happens before retained-store
access.

The first pass runs four production selections concurrently from uncontrolled cache state; the
second immediately repeats them. Every selector invocation includes catalog, receipt, manifest,
and Parquet hash verification. Success additionally requires exact equality with the prior
receipt-bound selections, a complete public inventory match, unchanged catalog bytes and dataset
metadata, and a post-run production catalog verification.

Only the sanitized artifact and receipt enter Git. Private requests, detailed selections, catalog,
datasets, identities, time bounds, object keys, market values, paths, account data, and credentials
remain outside Git. This is a descriptive component measurement, not a Gate 2 threshold or an
owner-qualified end-to-end performance envelope.
