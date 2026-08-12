# ADR-0020: Gate 1 Owner Acceptance and Canonical Layout

- Status: accepted
- Date: 2026-08-12
- Authority: explicit owner/PM decision
- Opens: Phase 2 canonical market-data MVP

## Context

The qualified Gate 1 campaign completed all eight planned steps on the owner laptop. Its
receipt-verified `grid.gate1-review-pack/v2` artifact is `ready-for-owner-review`, both paired
layout candidates pass every provisional performance gate, and the blocker list is empty.

The public evidence summary binds the preserved external artifacts through these SHA-256 values:

- final campaign plan: `fdc380c845f3c05369a5af58f6d5bd1f06610ef454fb608ed0602329cf019e50`;
- reference layout: `7746476097188e2df72b4cb121cfcc3a443a5e91b4e84f85aea6920b9d516a7f`;
- reference feature: `591fd02ae31c7dd7b64e83dacbbbd80e03194f22d25af43f3bfc267d812e3861`;
  and
- Gate 1 review pack: `06203c7cb278c0e1194e67fb76344ea88288bdc968b139319437fecab8b6a213`.

The review pack deliberately could not choose P-001 through P-005 or accept Gate 1. On
2026-08-12 the owner explicitly selected the decisions below, accepted Gate 1, authorized the
Phase 2 canonical market-data MVP and one-minute history downloader, and authorized this separate
governance change.

## Decision

Accept the following Gate 1 decisions:

1. **P-001 — exact hybrid candle representation.** Use `hybrid_int64_decimal` for the canonical
   candle physical contract: OHLC values are signed Int64 units of `1e-8`, volume is
   Decimal128(38, 4), and turnover is Decimal128(38, 12). Parquet/Arrow metadata must carry the
   versioned physical schema identity and scale; values may not be silently rounded to fit it.
2. **P-002 — eight stable symbol buckets.** A UTC calendar-month partition uses eight stable
   instrument buckets. Phase 2 must freeze and test the bucket-hash algorithm before publishing
   a canonical dataset; the count alone does not permit a mutable or implementation-dependent
   hash.
3. **P-003 — 16 MiB file target.** Canonical candle files use the measured 16 MiB target
   (`16,777,216` bytes) within the immutable month/bucket build and compaction protocol. Exact
   tail-file and target-attainment semantics remain contract- and receipt-visible.
4. **P-004 — ZSTD level 3.** Canonical Parquet candle files use ZSTD compression level 3.
5. **P-005 — evidence-admitted owner laptop.** The current laptop is the accepted reference
   research host under ADR-0019. Admission is conditional on a fresh preflight of memory,
   stable local NVMe identity, current free space, the independently bounded Phase 2 staging
   workspace, and the unchanged measured correctness/performance gates. There is no fixed
   64 GiB RAM or 2 TiB total-volume requirement.

Gate 1 is accepted. Phase 2 implementation is open for the canonical one-minute market-data MVP,
including public trade-price 1m, mark-price 1m, funding, dated instrument snapshots, manifests,
receipts, audits, incremental update/repair, compaction, and catalog work defined by the existing
roadmap.

This decision does not waive the Phase 2 scale sequence or Gate 2 criteria. It authorizes only
public, read-only Bybit history acquisition and local canonical-data mutation after preflight. It
does not authorize a Bybit bot/order create or close, transfers, any other real-money mutation,
strategy promotion, or live trading.

## Consequences

- P-001 through P-005 move from the pending decision surface into the accepted decision register.
- ADR-0010 remains the measurement/design record; its `8 buckets / 16 MiB` exact-hybrid ZSTD-3
  candidate is now the selected canonical layout.
- ADR-0014 review-pack artifacts retain `pending-owner-decision` because they are immutable
  evidence produced before this owner decision. This ADR is the later governance record.
- Every Phase 2 write run must perform a fresh ADR-0019-compatible host/capacity preflight and add
  its bounded REST staging requirement before mutation.
- Phase 2 begins with deterministic fixtures and bounded pilots. A full-universe bootstrap is not
  a substitute for the required incremental, resume, repair, audit, and fail-closed behavior.
- Gate 2 remains closed until its existing criteria are proven and accepted by the data-quality
  owner.

## Compatibility, migration, and rollback

No committed market dataset exists yet, so the selected physical layout requires no data
migration. Phase 2 contracts must reject incompatible physical schemas rather than reinterpret
them. Once a dataset is committed, changing representation, bucket count, target size,
compression, or bucket hashing requires a new dataset/schema version and a superseding ADR.

This accepted record is not rolled back by editing it. New evidence that invalidates admission
may re-close Gate 1 under the existing emergency/change-control rules; a different canonical
choice requires a superseding owner-approved ADR and an explicit migration plan.

## Alternatives considered

- **4 buckets / 32 MiB.** It passed every provisional gate and used about 1% less projected
  storage with a slightly faster reference write. It was not selected because 8/16 was faster in
  most cold query legs and roughly halved measured repair and compaction time.
- **Fixed 64 GiB RAM / 2 TiB disk admission.** Rejected by the owner through ADR-0019 because it
  is not supported by the same-host measurements or current capacity requirement.
- **Automatic acceptance from the review pack.** Rejected because implementation evidence cannot
  approve its own PM-owned gate.
