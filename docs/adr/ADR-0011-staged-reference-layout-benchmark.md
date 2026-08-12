# ADR-0011: Staged Reference Layout Benchmark

- Status: proposed; Gate 1 benchmark-gated
- Date: 2026-08-12

## Context

ADR-0010 produced a deterministic two-layout shortlist, but its single-process scan sequence does
not prove cold-cache performance. Hashing a retained dataset immediately before a scan would also
warm its contents and invalidate a cold-read claim. The remaining Gate 1 evidence additionally
requires bounded monthly repair and compaction measurements without mutating the source dataset.

Operating-system cache eviction is privileged and platform-specific. A benchmark must not claim a
cold cache merely because a query is the first query issued by its own process.

## Decision

Add a staged reference benchmark with three explicit phases:

1. `prepare` writes only the receipt-verified ADR-0010 shortlist, verifies its exact Parquet
   contracts, records content and metadata manifests, and measures immutable monthly-bucket repair
   and fragmented-input compaction.
2. Four separate `measure` legs run one query shape and engine each: DuckDB single-symbol, DuckDB
   universe-month, Polars single-symbol, and Polars universe-month. A reference-profile leg is
   accepted only after a boot different from preparation and every other leg. Before the first
   query it checks only file paths, sizes, and modification times. Content hashes are verified
   after the timed reads.
3. `finalize` accepts only a verified preparation receipt and all four verified measurement
   receipts. It rejects duplicate boot markers, changed hardware or software, changed dataset
   content, missing query legs, or incomplete maintenance parity evidence.

Reference preparation additionally requires a receipt-verified workstation snapshot that reports
the documented full research profile: at least 16 observed physical cores, 64 GiB RAM, and a
2 TiB NVMe measured volume. The current CPU/RAM/platform/storage identity must match the snapshot,
and the retained work directory must be on that measured volume. The snapshot hash, summarized
hardware, and exact Python/DuckDB/Polars/PyArrow/psutil versions are bound into the v2 preparation,
every measurement leg, and the final artifact. Input verification occurs before an existing work
directory can be replaced. On Windows, the storage model is resolved from the physical device
number backing the measured drive rather than assumed from `PhysicalDrive0`; on Linux it is
resolved from the longest matching mount and its `/sys/class/block` device.

Local development may use an explicit `unverified-smoke` cache mode. Its result is always
`local-smoke-only`; it cannot be relabelled as reference evidence.

Monthly repair is modeled as an immutable rewrite of one calendar-month/symbol-bucket unit into a
new target. Compaction first creates deterministic small fragments and then rewrites them into a
compact target. DuckDB and Polars must agree on exact logical aggregates for source, repair, and
compacted outputs, and the original source tree hash must remain unchanged. Temporary maintenance
targets are deleted only after their evidence has been captured; the prepared shortlist datasets
remain for the post-reboot measurement legs.

The first implementation uses the existing deterministic exact synthetic generator. The v2
evidence contract also requires the receipt-verified ADR-0012 real-market skew input; this
calibrates value-distribution compression but does not turn the synthetic timed rows into real
historical paths.

## Consequences

- A cold-read claim is tied to independently observable boot markers rather than process-local
  wording.
- Dataset content verification occurs after the timed first read, avoiding self-warming by the
  verifier while still detecting tampering.
- Reference execution requires four reboot-separated measurement legs and retained scratch data.
- A caller cannot obtain reference status by selecting `--profile reference` on a below-profile
  or different host/volume, and cannot mix engine versions between measurement legs.
- Repair and compaction evidence preserves ADR-0003 immutability and measures a bounded ADR-0005
  monthly-bucket unit.
- The protocol is slower operationally but makes cache semantics and mutation boundaries auditable.
- Synthetic preparation, below-reference hardware, or unverified cache semantics remain explicit
  blockers; the harness cannot approve P-001 through P-005 or Gate 1.

## Rejected alternatives

- Call the first query in a process cold: the operating-system cache may already contain the data.
- Hash every Parquet file before timing: content verification itself warms the files.
- Use a privileged cache-drop command: behavior is platform-specific and expands operator risk.
- Measure DuckDB and Polars sequentially under one cold claim: the first engine warms data for the
  second.
- Rewrite source files in place for repair/compaction: this violates immutable dataset semantics.
