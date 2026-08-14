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
