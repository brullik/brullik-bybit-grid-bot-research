# ADR-0019: Evidence-Based Reference-Host Admission

- Status: accepted by owner; qualification, workloads, review pack, and campaign admission implemented
- Date: 2026-08-12
- Supersedes in part: ADR-0011, ADR-0013, ADR-0015, and ADR-0018 (fixed hardware thresholds only)

## Context

The original Gate 1 reference profile required at least 16 physical/high-performance CPU cores,
64 GiB RAM, and a 2 TiB NVMe volume. Those values were conservative purchase-planning estimates,
not thresholds derived from a failed run on smaller hardware.

Subsequent receipt-marked evidence changed the basis for the decision:

- the owner laptop completed the 99,999,900-row, 700-instrument exact layout matrix;
- its shortlisted layouts observed peak RSS of 1,105,104,896 and 1,108,500,480 bytes;
- its 99,999,900-row, 700-instrument feature run completed in 31.165589400 seconds with peak RSS
  of 1,511,342,080 bytes, 9.172865938% of observed RAM;
- the current-universe trade-plus-mark estimate requires 89,995,614,938 bytes for an immutable
  active-plus-building rebuild; and
- the two retained reference layouts require 1,642,763,483 bytes of measured scratch.

Adding an explicit 8 GiB operating reserve produces a current admission requirement of
100,228,313,013 bytes (93.345 GiB) free on the campaign volume. The receipt-bound owner storage
snapshot observed 193,679,237,120 bytes (180.378 GiB) free. A fixed 2 TiB total-volume rule would
therefore reject a host that has already demonstrated the relevant 100-million-row workloads and
has almost twice the measured current free-space requirement.

The formal 700-instrument, ten-year, one-minute capacity target remains an architecture envelope.
It is not evidence that every instrument has ten years of history, nor that every intermediate
artifact must coexist permanently. V1 also excludes tick/public-trade archives.

On 2026-08-12 the owner explicitly authorized replacing the fixed hardware admission with
evidence-based requirements. This is a governance change; it does not accept Gate 1 or authorize
the Phase 2 downloader.

## Decision

Replace CPU-count, installed-RAM, and total-volume capacity as hard Gate 1 admission thresholds.
They remain reported characteristics and affect elapsed time, but they do not prove or disprove
fitness by themselves.

A host qualifies for a reference campaign only when a new append-only admission contract proves
all of the following before campaign mutation:

1. **Same-host full-scale evidence.** Receipt- and schema-verified layout and feature trials from
   the same hardware identity completed at least 99,999,900 rows across exactly 700 instruments,
   passed correctness checks, and reported bounded peak RSS.
2. **Memory headroom.** The qualifying feature trial used no more than 70% of observed total RAM.
   Every reference rerun retains the same 70% runtime gate and publishes a negative result if it
   is exceeded.
3. **Evidence-derived free space.** Current free bytes on the measured campaign volume are at
   least the sum of:
   - the latest verified current-universe `full-rebuild-active-plus-building` requirement;
   - measured retained scratch for every shortlisted reference layout; and
   - an explicit 8 GiB operating reserve for environment, receipts, logs, and bounded temporary
     files.
4. **Suitable local storage.** The measured campaign volume is local non-rotating storage
   (`nvme` or `ssd`), retains a stable device identity, and contains the campaign root.
5. **Stable identity and environment.** Current CPU/RAM/platform/storage identity matches the
   qualifying evidence, and the clean, pinned reference environment passes its doctor.
6. **Measured acceptance.** Existing cold/warm scan, write-time, correctness, memory, reboot,
   immutable repair, and compaction gates remain unchanged. More CPU may make a run faster, but
   does not waive any numeric gate.

The free-space calculation is re-evaluated from current lifecycle and disk evidence. It therefore
grows with listed history and blocks when the volume no longer fits the active-plus-building
operation. It is not frozen at 93.345 GiB.

Phase 2 downloader admission must add its independently bounded REST-page staging and download
workspace to the same free-space preflight. It may not cache the full history as a second raw
corpus merely to simplify implementation. Tick data remains out of scope.

Existing `grid.workstation-snapshot/v1`, reference layout/feature, review-pack, and campaign-plan
artifacts retain their original fixed-profile semantics. Implementation of this decision must use
append-only versioned contracts; it may not reinterpret old receipts.

The implemented successor chain is `grid.reference-host-qualification/v1`, layout/feature v3,
`grid.gate1-review-pack/v2`, and `grid.reference-campaign-plan/v2`. The plan embeds the complete
pinned environment report and repository source-manifest hash; status rechecks those bindings and
the current host/free-space admission before exposing the next command. All legacy schemas remain
unchanged.

On the currently checked-in evidence, the owner laptop is a **hardware candidate** for the new
admission: 6 physical/12 logical cores, 16,476,225,536 bytes RAM, a 511,439,781,888-byte NVMe
volume, and 193,679,237,120 observed free bytes. It is not admitted until the append-only contract
is implemented, fresh evidence verifies the current free space and identity, and the pinned
Python 3.12 environment passes.

## Consequences

- A 2 TiB disk and 64-128 GiB RAM are optional convenience/capacity purchases, not Gate 1 facts.
- The already demonstrated laptop can run the campaign if fresh preflight and every benchmark
  gate pass; lower core count may increase wall-clock time.
- Free-space safety is stricter operationally because it checks available bytes for the actual
  lifecycle and immutable rebuild, not nominal device capacity.
- Growth, new derived stores, or a wider staging contract can raise the required free space and
  force migration without changing the 700-instrument design.
- Gate 1 remains pending explicit owner/PM review; this decision changes admission evidence only.

## Rejected alternatives

- Keep 16/64/2 TiB because it is conservative: it contradicts measured same-host evidence and
  turns a purchase suggestion into an unsupported blocker.
- Admit every machine with enough total disk: total capacity does not prove current free space,
  memory boundedness, correctness, or performance.
- Use the current 180.378 GiB free-space observation as a permanent threshold: admission must be
  derived from current lifecycle, scratch, and staging evidence.
- Replace the formal 700-by-ten-year design envelope with today's inventory: that would make
  future market growth an architecture change.
- Modify existing evidence schemas in place: historical receipts must retain their original
  semantics.
