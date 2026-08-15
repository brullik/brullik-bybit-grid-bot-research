# Prioritized Backlog

This backlog describes future work; it does not authorize implementation or live execution.

## P0 — Next after documentation acceptance

1. **Feasibility: Bybit universe and historical-source inventory**
   - Resolve current linear instrument pagination, listing metadata, archive coverage, and gaps.
2. **Benchmark: representative canonical schema and storage layout**
   - Compare encoding, compression, bucket count, file size, scan patterns, and memory.
3. **Feasibility: native Futures Grid validate/account behavior**
   - Read/validate only; no create.
4. **Governance: configure branch protection and required checks**
   - Protect PM acceptance files and secrets.
5. **License decision**
   - Owner selects an explicit license or keeps no-grant policy.

## P1 — Canonical data MVP

6. Instrument snapshot and stable identity contract.
7. Bulk archive acquisition with evidence/checksums.
8. REST incremental/gap-repair path.
9. Trade-price 1m canonical store.
10. Mark-price 1m canonical store.
11. Funding store and interval semantics.
12. Dataset manifests, receipts, and atomic publication.
13. Coverage/duplicate/conflict/orphan/integrity audits.
14. Compaction and retention policy.

## P2 — Research platform

15. Frozen decision-time and feature contract. Design authority: ADR-0099 and
    [M3 implementation plan](M3_FEATURE_CANDIDATE_IMPLEMENTATION_PLAN.md); implementation remains
    gated by Gate 2.
16. Batch/live parity feature-kernel fixtures.
17. Horizontal-range candidate baseline.
18. Candidate density/throughput benchmark.
19. Outcome/simulator specification and adversarial cases.
20. Portfolio allocator and capital-lock model.
21. Experiment registry and split governance.
22. Robustness/review pack.

## P3 — Release and shadow live

23. Strategy release schema/builder/verifier.
24. Promotion/revocation/rollback registry.
25. Slim live runtime boundary test.
26. Current market-data gateway and rolling features.
27. Signal/risk/state/audit/reconciliation.
28. Telegram control plane.
29. Failure-injection suite.
30. 30-day/100-signal shadow run.

## P4 — Manual mainnet and operations

31. Dedicated subaccount/key/host decision.
32. Validate/create/detail/close adapter.
33. Exact approval and uncertain-result handling.
34. Minimal one-bot mainnet drill.
35. Emergency/restart/backup recovery drill.
36. Controlled scale decision pack.

## Deferred until evidence

- Rust/C++ optimization;
- distributed compute/Spark;
- Kubernetes;
- ML strategy selection;
- other exchanges;
- trailing grid;
- autonomous live entries;
- web dashboard.
