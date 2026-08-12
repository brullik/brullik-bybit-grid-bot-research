# ADR-0022: Receipt-Last Canonical Partition Publication

- Status: accepted
- Date: 2026-08-12
- Implements: Phase 2 immutable canonical write protocol

## Context

ADR-0021 freezes the candle physical layout but deliberately does not publish files. Phase 2
needs a cross-platform transition from a validated in-memory partition to an immutable dataset
that is safe to consume after interruption. In particular, Windows prevents directory renames
while a Parquet footer handle remains open, and a directory that merely looks complete cannot be
treated as committed.

Every Phase 2 write also needs the ADR-0019/ADR-0020 evidence-based host policy. The low-level
storage package must not discover hardware by shelling out or gain a network dependency, so the
public `grid-data` application owns system probing and supplies a fresh observation. The storage
boundary independently validates that observation and checks it again immediately before its
first mutation.

## Decision

Publish each bounded canonical candle partition as an immutable dataset version under:

```text
market-store/
  .building/<dataset-id>--<request-hash-prefix>/
  datasets/<dataset-id>/
    dataset=<type>/schema=v1/year=YYYY/month=MM/bucket=BB/part-<sha256>.parquet
    audit.json
    manifest.json
    completion-receipt.json
```

The request identity binds the dataset specification, exact Arrow-buffer hash, dataset type, and
partition. Preflight performs no filesystem mutation and rejects unsafe identities, stale or
future host observations, non-NVMe/SSD storage, a target outside the observed volume, insufficient
current memory, a planned peak above 70% of total memory, insufficient evidence-derived free
space, stale building output, and a conflicting committed identity.

The capacity calculation includes active-plus-building bytes, independently bounded REST staging,
an 8 GiB operating reserve, and a bounded writer workspace. The request and audit bind separate
coverage and capacity evidence hashes. Immediately before mutation, publication requires another
fresh observation with the same storage identity and total memory and repeats the free-space and
memory checks.

After preflight, publication writes one ZSTD-3 Parquet file in the unique building directory,
closes its footer handle, verifies schema/footer, hashes the file, and writes canonical audit and
manifest JSON. It then atomically renames the building directory into `datasets/<dataset-id>` and
writes `completion-receipt.json` through a same-directory temporary file last. A final directory
without the receipt is uncommitted. No automatic deletion or overwrite is allowed.

The verifier checks canonical manifest/receipt bytes, receipt-to-manifest binding, audit hash and
identity, every Parquet hash/size/footer/schema/row count, path containment, and an exact file
allowlist. A byte-identical/evidence-identical rerun returns the existing verified commit; a
different request using the same dataset ID fails closed.

This is the bounded single-partition publication primitive. It does not yet expose a public write
CLI, implement a system-probe adapter, download Bybit pages, resolve lifecycle coverage, resume a
partially downloaded range, compact files, or update a catalog. Those remain subsequent Phase 2
work, and Gate 2 remains closed.

## Consequences

- The completion receipt, not directory presence, is the sole commit marker.
- Interrupted building/final directories remain visible for explicit repair evidence and are
  never silently deleted.
- Local host/device identifiers are reduced to a SHA-256 binding in the audit; credentials and
  private account data are not accepted.
- Small fixture inputs are explicitly classified as tail files; target-band and oversized
  single-batch results remain observable rather than being mislabeled as target attainment.
- A future multi-file writer/compactor may extend inventory cardinality without changing the
  receipt-last rule or committed files in place.
- `grid-live` remains independent of the package and historical store.

## Rejected alternatives

- Write directly into the final dataset directory: partial output could be mistaken for complete.
- Treat `manifest.json` as the commit marker: a crash can occur after the manifest but before file
  durability or final publication.
- Delete stale output automatically: it destroys evidence needed to distinguish interruption,
  collision, and operator error.
- Let the storage package invoke platform shells for hardware discovery: it couples the portable
  physical boundary to operating-system orchestration.
- Reuse an old Gate 1 free-space number: Phase 2 must bind fresh capacity evidence and REST staging.
