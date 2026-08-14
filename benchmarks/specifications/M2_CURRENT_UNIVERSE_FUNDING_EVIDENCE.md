# M2 current-universe funding evidence specification

Run this offline builder only after the ADR-0085 catalog bundle, ADR-0089 candle evidence, and
every funding Landing/publication/coverage triplet have receipt-last completion markers:

```powershell
.venv\Scripts\python.exe -m benchmarks.current_universe_funding_evidence `
  --source-manifest reports\private\m2-current-universe-funding-sources-<date>.json `
  --artifact-root . `
  --software-identity git:<merged-builder-sha> `
  --output benchmarks\results\m2-current-universe-funding-evidence-<date>.json
```

The private source manifest uses `grid.current-universe-funding-evidence-request/v1`, canonical
JSON plus LF, and safe-relative paths under `--artifact-root`. Its candle sources must preserve
the exact ADR-0085 bundle order. Each funding source is either `boundary-backed`, with its exact
ADR-0048 request/evidence pair, or `reused-bounded`, with no boundary substitution.

The command must fail before output when a receipt, schema, content hash, governance binding,
source-boundary count, Landing/publication/coverage count, reason policy, or per-symbol interval
differs. Funding intervals may be adjacent but cannot overlap; after adjacency normalization they
must equal the private candle bundle's per-symbol minute union exactly. A reused mixed-kind source
must have passed non-funding coverage so its aggregate blocked reasons remain funding-attributable.

A successful result writes canonical evidence JSON followed by its receipt and returns zero even
when verified funding coverage remains blocked. It reports only hashes, aggregate inventory,
quality, boundary totals, and timing. Reused mixed-kind timing may include candle work and never
qualifies the owner-reviewed end-to-end envelope. The command performs no Bybit request or store
mutation and cannot change Gate 2 or authorize Phase 3/live behavior.
