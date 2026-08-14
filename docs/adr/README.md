# Architecture Decision Records

ADRs capture decisions that materially constrain implementation, data compatibility, risk, or operations.

Status values:

- `proposed`;
- `accepted`;
- `superseded`;
- `deprecated`.

An ADR is immutable after acceptance except for status/supersession references and clerical corrections. A changed decision is recorded in a new ADR.

## Index

- [ADR-0070 - Receipt-bound fast candle-boundary diagnostic](ADR-0070-receipt-bound-fast-candle-boundary-diagnostic.md)
- [ADR-0069 - Receipt-bound canonical publication plan checkpoint](ADR-0069-receipt-bound-publication-plan-checkpoint.md)
- [ADR-0068 - Receipt-bound canonical representation admission quarantine](ADR-0068-canonical-representation-admission-quarantine.md)
- [ADR-0067 - Schema-only canonical candle publication for zero-admission source partitions](ADR-0067-schema-only-canonical-candle-publication.md)
- [ADR-0066 - Offline incremental catalog selection performance evidence](ADR-0066-offline-incremental-catalog-selection-performance-evidence.md)
- [ADR-0065 - Bounded exact-key admission for incremental catalog selection](ADR-0065-bounded-exact-incremental-catalog-key-admission.md)
- [ADR-0064 - Offline canonical integrity fault-injection evidence](ADR-0064-offline-canonical-integrity-fault-injection.md)
- [ADR-0063 - Receipt-bound non-promoting Gate 2 readiness pack](ADR-0063-receipt-bound-gate2-readiness-pack.md)
- [ADR-0062 - Offline stale-output fault-injection evidence](ADR-0062-offline-stale-output-fault-injection-evidence.md)
- [ADR-0061 - Receipt-verified funding compaction candidate audit](ADR-0061-receipt-verified-funding-compaction-candidate-audit.md)
- [ADR-0060 - Regional public-API block versus rate-limit classification](ADR-0060-regional-public-api-block-versus-rate-limit.md)
- [ADR-0059 - Sanitized history-campaign resume performance evidence](ADR-0059-sanitized-campaign-resume-performance-evidence.md)
- [ADR-0058 - Post-publication funding repair coverage audit](ADR-0058-post-publication-funding-repair-coverage-audit.md)
- [ADR-0057 - Immutable funding repair publication and sanitized execution evidence](ADR-0057-immutable-funding-repair-publication.md)
- [ADR-0056 - Bounded funding repair discovery execution](ADR-0056-bounded-funding-repair-discovery-execution.md)
- [ADR-0055 - Fail-closed funding repair discovery planning](ADR-0055-fail-closed-funding-repair-discovery-plan.md)
- [ADR-0054 - Immutable canonical funding compaction](ADR-0054-immutable-canonical-funding-compaction.md)
- [ADR-0053 - Quarantine-aware coverage and repair admission](ADR-0053-quarantine-aware-coverage-and-repair-admission.md)
- [ADR-0052 - Receipt-bound funding source-boundary admission](ADR-0052-receipt-bound-funding-source-boundary-admission.md)
- [ADR-0051 - Sanitized candle source-quality evidence](ADR-0051-sanitized-candle-source-quality-evidence.md)
- [ADR-0050 - Receipt-bound candle source-row quarantine](ADR-0050-receipt-bound-candle-source-row-quarantine.md)
- [ADR-0049 - Sanitized funding source-boundary evidence](ADR-0049-sanitized-funding-source-boundary-evidence.md)
- [ADR-0048 - Receipt-resumable funding source-boundary discovery](ADR-0048-receipt-resumable-funding-source-boundary-discovery.md)
- [ADR-0047 - Single-snapshot campaign input admission](ADR-0047-single-snapshot-campaign-input-admission.md)
- [ADR-0046 - Semantic admission and receipt-integrity reverification](ADR-0046-semantic-admission-and-receipt-integrity-reverification.md)
- [ADR-0045 - Transport-attempt versus HTTP-response accounting](ADR-0045-transport-attempt-versus-response-accounting.md)
- [ADR-0044 - Receipt-bound long-run throttling evidence](ADR-0044-receipt-bound-long-run-throttling-evidence.md)
- [ADR-0043 - Decrease-only global public REST throttling](ADR-0043-decrease-only-global-public-rest-throttling.md)
- [ADR-0042 - Dated current linear-status inventory policy](ADR-0042-dated-current-linear-status-inventory-policy.md)
- [ADR-0041 - Receipt-bound aggregate campaign coverage audit](ADR-0041-receipt-bound-aggregate-campaign-coverage-audit.md)
- [ADR-0040 - Sanitized canonical campaign publication evidence](ADR-0040-sanitized-canonical-campaign-publication-evidence.md)
- [ADR-0039 - Receipt-resumable canonical campaign publication](ADR-0039-receipt-resumable-canonical-campaign-publication.md)
- [ADR-0038 - Receipt-resumable public history campaign](ADR-0038-receipt-resumable-public-history-campaign.md)
- [ADR-0037 - Point-in-time instrument timeline and ex-post lifecycle coverage](ADR-0037-point-in-time-instrument-timeline.md)
- [ADR-0036 - Scale-aligned candle audit series bound](ADR-0036-scale-aligned-candle-audit-series-bound.md)
- [ADR-0035 - Funding catalog and snapshot-bound selection](ADR-0035-funding-catalog-and-snapshot-bound-selection.md)
- [ADR-0034 - Fail-closed funding source chronology audit](ADR-0034-fail-closed-funding-chronology-audit.md)
- [ADR-0033 - Sanitized public funding pilot evidence](ADR-0033-sanitized-public-funding-pilot-evidence.md)
- [ADR-0032 - Resumable public funding acquisition and boundary evidence](ADR-0032-resumable-public-funding-acquisition-and-boundary-evidence.md)
- [ADR-0031 - Exact funding layout and receipt-last publication](ADR-0031-exact-funding-layout-and-receipt-last-publication.md)

- [ADR-0030 — Receipt-verified DuckDB catalog and snapshot-bound selection](ADR-0030-receipt-verified-duckdb-catalog-and-snapshot-bound-selection.md)

- [ADR-0029 — Target-size immutable canonical compaction](ADR-0029-target-size-immutable-canonical-compaction.md)
- [ADR-0028 — Bounded repair execution and immutable replacement lineage](ADR-0028-bounded-repair-execution-and-immutable-replacement-lineage.md)
- [ADR-0027 — Verified gap audit to bounded repair plan](ADR-0027-verified-gap-audit-to-bounded-repair-plan.md)
- [ADR-0026 — Fail-closed canonical coverage audit](ADR-0026-fail-closed-canonical-coverage-audit.md)
- [ADR-0025 — GitHub truth with sanitized runtime evidence](ADR-0025-github-truth-with-sanitized-runtime-evidence.md)
- [ADR-0024 — Verified Landing to canonical publication](ADR-0024-verified-landing-to-canonical-publication.md)
- [ADR-0023 — Stable linear registry and resumable public 1m acquisition](ADR-0023-stable-linear-registry-and-resumable-1m-acquisition.md)
- [ADR-0022 — Receipt-last canonical partition publication](ADR-0022-receipt-last-canonical-partition-publication.md)
- [ADR-0021 — Canonical candle physical contract boundary](ADR-0021-canonical-candle-physical-contract.md)
- [ADR-0020 — Gate 1 owner acceptance and canonical layout](ADR-0020-gate1-owner-acceptance-and-canonical-layout.md)
- [ADR-0019 — Evidence-based reference-host admission](ADR-0019-evidence-based-reference-host-admission.md)
- [ADR-0018 — Fail-closed reference campaign handoff](ADR-0018-reference-campaign-handoff.md)
- [ADR-0017 — Bounded public REST throughput evidence](ADR-0017-bounded-public-rest-throughput-evidence.md)
- [ADR-0016 — One-minute-only market history](ADR-0016-one-minute-only-market-history.md)
- [ADR-0015 — Current-universe bootstrap and incremental capacity evidence](ADR-0015-current-universe-bootstrap-and-incremental-capacity.md)
- [ADR-0014 — Gate 1 reference evidence aggregation](ADR-0014-gate1-reference-evidence-aggregation.md)
- [ADR-0013 — Shared reference-host admission for feature evidence](ADR-0013-shared-reference-host-feature-admission.md)
- [ADR-0012 — Bounded real-market layout-skew evidence](ADR-0012-bounded-real-market-layout-skew.md)
- [ADR-0011 — Staged reference layout benchmark](ADR-0011-staged-reference-layout-benchmark.md)
- [ADR-0010 — Density-derived exact monthly layout matrix](ADR-0010-density-derived-exact-layout-matrix.md)

- [ADR-0001 — Separate deployable applications](ADR-0001-separate-deployable-applications.md)
- [ADR-0002 — Parquet, DuckDB, and Polars baseline](ADR-0002-parquet-duckdb-polars.md)
- [ADR-0003 — Immutable datasets and receipts](ADR-0003-immutable-datasets-and-receipts.md)
- [ADR-0004 — Strategy release boundary](ADR-0004-strategy-release-boundary.md)
- [ADR-0005 — Time and symbol-bucket partitioning](ADR-0005-time-symbol-bucket-partitioning.md)
- [ADR-0006 — Exact execution arithmetic](ADR-0006-exact-execution-arithmetic.md)
- [ADR-0007 — Local-first, cloud-ready architecture](ADR-0007-local-first-cloud-ready.md)
- [ADR-0008 — Versioned, bounded-memory layout evidence](ADR-0008-versioned-bounded-layout-evidence.md)
- [ADR-0009 — Isolated Demo environment for validate-only feasibility](ADR-0009-isolated-demo-validate-environment.md)
