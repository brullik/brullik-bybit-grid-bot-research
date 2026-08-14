# M2 Gate 2 readiness-pack specification

This offline command aggregates the current public Phase 2 evidence without contacting Bybit or
reading the retained market store:

```powershell
.venv\Scripts\python.exe -m benchmarks.gate2_readiness_pack `
  --implementation-identity git:<merged-implementation-sha> `
  --output benchmarks\results\m2-gate2-readiness-pack-<date>.json
```

Run it only after the builder is merged so `implementation_identity` names an immutable `main`
commit. Exit code 2 is expected for the current v1 source set because four of six criteria remain
blocked. The JSON and receipt are still published first as auditable negative evidence.

The builder verifies the unchanged criteria source plus receipt, JSON Schema, artifact SHA-256,
content SHA-256, contract, status, and cross-source lineage for all eight named inputs. It refuses
source substitution and never accepts Gate 2, authorizes Phase 3, mutates market data, or exposes
runtime identities or market values.

## Current successor (v2)

The v1 artifact remains immutable historical evidence. Build the current successor only after its
implementation is merged:

```powershell
.venv\Scripts\python.exe -m benchmarks.gate2_readiness_pack_v2 `
  --implementation-identity git:<merged-implementation-sha> `
  --output benchmarks\results\m2-gate2-readiness-pack-v2-<date>.json
```

The v2 builder performs one offline verification pass over twelve exact GitHub artifacts. It does
not repeat a Bybit download, canonical publication, coverage scan, or benchmark. The expected exit
code remains 2: three criteria are evidence-ready, while deterministic repair, lifecycle coverage,
and the reviewed full-history end-to-end performance envelope remain blocked by seven explicit
evidence/policy codes. Gate 2 stays closed and Phase 3 stays unauthorized.

## Current successor (v3)

The v1 and v2 artifacts remain immutable historical evidence. Build v3 only after its
implementation is merged:

```powershell
.venv\Scripts\python.exe -m benchmarks.gate2_readiness_pack_v3 `
  --implementation-identity git:<merged-implementation-sha> `
  --output benchmarks\results\m2-gate2-readiness-pack-v3-<date>.json
```

The v3 builder reuses the complete v2 verification and adds the exact public candle-repair,
funding-repair-candidate, and full-history-catalog chains. It performs no network call, market-store
scan, repair retry, publication, or catalog mutation. Exit code 2 remains required: the same three
criteria remain blocked by seven codes, but the two stale evidence-missing descriptions are
replaced by measured negative outcomes. Gate 2 stays closed and Phase 3 stays unauthorized.

## Current-universe successor (v4)

The v1 through v3 artifacts remain immutable. Build v4 only after the ADR-0089 candle, ADR-0090
funding, and ADR-0091 catalog-performance evidence pairs exist and the v4 implementation is
merged:

```powershell
.venv\Scripts\python.exe -m benchmarks.gate2_readiness_pack_v4 `
  --implementation-identity git:<merged-v4-implementation-sha> `
  --prior-readiness benchmarks\results\m2-gate2-readiness-pack-v3-20260814.json `
  --candle-evidence data\evidence\m2-current-universe-candle-evidence-<date>.json `
  --funding-evidence data\evidence\m2-current-universe-funding-evidence-<date>.json `
  --catalog-performance data\evidence\m2-current-universe-catalog-performance-<date>.json `
  --output data\evidence\m2-gate2-readiness-pack-v4-<date>.json
```

The builder reuses the exact v3 decision rather than rebuilding its fifteen sources, verifies all
four receipt/schema/canonical/content-hash chains, and reconciles current-universe scope,
candle/funding lineage, bundle/catalog bindings, and catalog inventory. Exit code 2 remains
required: v3's same three blocked criteria and seven blockers are preserved, owner review remains
required, Gate 2 stays closed, and Phase 3 stays unauthorized.
