# M2 incremental catalog selection performance specification

This offline command publishes deterministic synthetic multi-instrument candle fragments into an
automatically removed temporary store, registers them in the production DuckDB catalog, and runs
the ADR-0065 exact-key selection twice:

```powershell
.venv\Scripts\python.exe -m benchmarks.incremental_catalog_selection `
  --implementation-identity git:<merged-implementation-sha> `
  --fragment-count 16 `
  --instrument-count 32 `
  --minutes-per-fragment 720 `
  --output benchmarks\results\m2-incremental-catalog-selection-performance-<date>.json
```

Run it only after implementation merge so evidence binds an immutable `main` commit. The default
profile contains 16 disjoint same-partition fragments and 368,640 exact keys. Its file bounds are
intentionally ambiguous, forcing the production bounded streaming fallback rather than the
metadata-only fast path.

Success requires complete selection on both runs, identical selection results, at least one
ambiguous adjacent bound, and a byte-level store fingerprint unchanged before/after selection.
The fixture is removed before the public evidence is returned. The result contains only aggregate
configuration, durations, throughput, correctness facts, hashes, software versions,
non-identifying CPU/RAM/platform facts, and explicit cache state; it contains no path,
instrument/dataset identity, market value, device identity, account data, or credential.

This is a measured synthetic incremental-selection result. It is not full-history performance,
coverage/lifecycle acceptance, Gate 2 acceptance, Phase 3 authorization, or live evidence.
