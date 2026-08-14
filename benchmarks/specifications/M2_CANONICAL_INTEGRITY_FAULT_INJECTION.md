# M2 canonical integrity fault-injection specification

This offline command exercises production candle/funding verifiers against temporary orphan and
partial canonical datasets:

```powershell
.venv\Scripts\python.exe -m benchmarks.canonical_integrity_fault_injection `
  --implementation-identity git:<merged-implementation-sha> `
  --output benchmarks\results\m2-canonical-integrity-fault-injection-<date>.json
```

Run it after implementation merge so evidence binds an immutable `main` commit. Success requires
all six orphan/missing-Parquet/missing-receipt cases to fail closed and the complete injected tree
fingerprint to remain unchanged during verification.

The retained market store and network are not accessed. The result proves detection, not cleanup,
repair, Gate 2 acceptance, Phase 3 authorization, or live capability.
