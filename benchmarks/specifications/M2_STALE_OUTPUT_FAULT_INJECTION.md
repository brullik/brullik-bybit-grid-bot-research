# M2 stale-output fault-injection specification

This offline benchmark exercises production preflight functions against temporary injected stale
markers. It never contacts Bybit or mutates `data/market-store`.

Run only after the implementation is merged so the evidence binds an immutable Git identity:

```powershell
.venv\Scripts\python.exe -m benchmarks.stale_output_fault_injection `
  --implementation-identity git:<merged-commit-sha> `
  --output benchmarks\results\m2-stale-output-fault-injection-<date>.json
```

The command succeeds only when all five production boundaries reject the marker, preserve its
bytes, and leave the target uncreated. The temporary fixture is removed automatically. The public
artifact contains case names and aggregate outcomes, not market values or runtime paths.

This evidence supports only the unchanged Gate 2 stale-building-output criterion. It does not
accept Gate 2 or authorize cleanup/live behavior.
